'use strict'

const http = require('http')
const mineflayer = require('mineflayer')
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder')
const collectBlock = require('mineflayer-collectblock').plugin
const mcDataFactory = require('minecraft-data')
const furnaceRuns = new Map()
// 32 deu NoPath ao sair de cavernas (27/10 13:02 e 13:09); com limite, heap medido ~40 MB.
const PATH_SEARCH_RADIUS = 64
const cell = p => p ? [Math.floor(p.x), Math.floor(p.y), Math.floor(p.z)].join(',') : null
const PATH_FAILURES = ['NoPath', 'Timeout']
// O que o bloco solta em sobrevivência quando difere do nome (minecraft-data lista o drop de Toque de Seda).
const BLOCK_DROPS = { coal_ore: 'coal', stone: 'cobblestone', diamond_ore: 'diamond', emerald_ore: 'emerald',
  lapis_ore: 'lapis_lazuli', redstone_ore: 'redstone', nether_quartz_ore: 'quartz', grass_block: 'dirt' }
// collectBlock pode não resolver depois de pegar o item (27/10 13:37): abaixo dos 90 s do cliente.
const COLLECT_BUDGET_MS = 75000
const STATION_BLOCKS = new Set(['crafting_table', 'furnace'])  // 30/10: recolher ao quebrar
const DIG_BUDGET_MS = 20000, PICKUP_BUDGET_MS = 8000  // equipar+quebrar, andar até o item: cabem nos 45 s do cliente
const COLLECT_CANCEL_WAIT_MS = 8000  // 30/10: encerrar a coleta cancelada; 75 + 8 s cabe nos 90 s do RPC
const HUNT_BUDGET_MS = 30000
// Medida por pedido: localiza crescimento de memória antes de um OOM fatal.
const heapMb = () => { const m = process.memoryUsage?.(); return m ? Math.round(m.heapUsed / 1048576) : null }
const { Vec3 } = require('vec3')
const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const { AsyncLocalStorage } = require('async_hooks')
const rpcContext = new AsyncLocalStorage()

const HOST = process.env.HOSHINO_MC_BRIDGE_HOST || '127.0.0.1'
const PORT = Number(process.env.HOSHINO_MC_BRIDGE_PORT || 8765)
const DEFAULT_VERSION = process.env.HOSHINO_MC_VERSION || '1.16.5'
const BRIDGE_PROTOCOL = 3

let bot = null
let mcData = null
let movements = null
let fleeLog = []  // 30/10: instantes das fugas de arqueiro desta sessão, para não repetir sem fim
let fleeNoDig = null  // 30/10: { until, moves } — fuga em andamento com Movements próprios, sem cavar nem empilhar
let lastError = null
let lastEvent = null
let recentChat = []
// Morte (28/10): onde caiu e o que levava; itens caídos somem 5 min (6000 ticks) depois no 1.16.
let lastAlive = null, lastDeath = null
// Reflexos de sobrevivência (28/10: sufocou sob cascalho enquanto o modelo pensava; antes morreu
// várias vezes para monstros). Mecânica de autopreservação, como os modos do Mindcraft; não decide o jogo.
const REFLEX_HOSTILE = new Set(['zombie','husk','drowned','skeleton','stray','creeper','spider','cave_spider',
  'enderman','witch','slime','phantom','pillager','vindicator','zombie_villager','silverfish'])
let reflexes = [], reflexSeq = 0, reflexBusy = false, lastHealth = null, lastDanger = null
// Etapa "matar um mob" (pedido humano 27/10): só golpes da ação attack contam; o reflexo não.
const attackedAt = new Map(); let kills = []
const NOT_A_TARGET = new Set(['villager', 'wandering_trader'])
const ITEM_DESPAWN_MS = 5 * 60 * 1000
let chatSequence = 0
let activeAction = null
let connectionState = 'idle'
let sessionId = null
let connectionTarget = null
let eventSeq = 0
const PROJECT_ROOT = path.resolve(__dirname, '..', '..', '..')
const DIAG_DIR = path.join(process.env.HOSHINO_RUNTIME_DIR ||
  path.join(PROJECT_ROOT, 'entidades', 'hoshino', 'runtime'), 'diagnostics')
fs.mkdirSync(DIAG_DIR, { recursive: true })
// O minério já está no forno do mundo: a fundição sobrevive ao sono/recarga da
// ponte (27/10 17:37). Chave sem sessão: mesmo jogador, dimensão e bloco.
const FURNACE_RUNS_FILE = path.join(DIAG_DIR, '..', 'minecraft_furnace_runs.json')
try { for (const [k, v] of Object.entries(JSON.parse(fs.readFileSync(FURNACE_RUNS_FILE, 'utf8')))) furnaceRuns.set(k, v) } catch (_) {}
function saveFurnaceRuns() {
  try {
    fs.writeFileSync(FURNACE_RUNS_FILE + '.tmp', JSON.stringify(Object.fromEntries(furnaceRuns)), 'utf8')
    fs.renameSync(FURNACE_RUNS_FILE + '.tmp', FURNACE_RUNS_FILE)
  } catch (error) { diag('furnace.runs_save_error', { error: String(error?.message || error) }) }
}
const furnacePrefix = b => `${b.username}|${b.game?.dimension || null}|`

function safe(value) {
  if (value === undefined || value === null) return value
  if (typeof value === 'string') return value.length > 1600 ? value.slice(0, 1600) + '…' : value
  if (Array.isArray(value)) return value.slice(0, 32).map(safe)
  if (typeof value === 'object') { const out = {}; for (const [k,v] of Object.entries(value)) { if (/token|password|secret|cookie|authorization/i.test(k)) out[k] = '[REDACTED]'; else out[k] = safe(v) } return out }
  return value
}
function diag(event, data = {}) {
  const record = { ts: new Date().toISOString(), event, pid: process.pid, seq: ++eventSeq, data: safe({ ...(rpcContext.getStore() || {}), ...data }) }
  const day = new Date().toISOString().slice(0,10)
  const file = path.join(DIAG_DIR, `minecraft_${day}.jsonl`)
  const human = path.join(DIAG_DIR, `minecraft_${day}.log`)
  try { fs.appendFileSync(file, JSON.stringify(record) + '\n', 'utf8') } catch (_) {}
  try { fs.appendFileSync(human, `${record.ts} | ${event} | ${JSON.stringify(record.data)}\n`, 'utf8') } catch (_) {}
  console.log(`[diag] ${event} ${JSON.stringify(record.data)}`)
}
function newSession() { return crypto.randomBytes(5).toString('hex') }

function setEvent(type, detail = '') {
  lastEvent = { type, detail, at: new Date().toISOString() }
}

function vecToJSON(v) {
  return v ? { x: v.x, y: v.y, z: v.z } : null
}

function distance(a, b) {
  if (!a || !b) return null
  return a.position.distanceTo(b.position)
}

function inventorySummary() {
  if (!bot?.inventory?.items) return []
  const map = new Map()
  for (const item of bot.inventory.items()) {
    map.set(item.name, (map.get(item.name) || 0) + item.count)
  }
  return Array.from(map.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => a.name.localeCompare(b.name))
}

function entityLineOfSight(entity) {
  if (typeof bot?.canSeeBlock !== 'function') return null
  try {
    const height=Number.isFinite(entity.height)&&entity.height>0?entity.height:1.8
    // canSeeBlock também aceita qualquer objeto com position (plugin blocks).
    // Pés, corpo e cabeça: uma parte visível basta; desconhecido não vira seguro.
    const values=[0.1,height*0.5,height*0.9].map(dy=>bot.canSeeBlock({position:
      new Vec3(Math.floor(entity.position.x),Math.floor(entity.position.y+dy),Math.floor(entity.position.z))}))
    if (values.some(v=>v===true)) return true
    return values.every(v=>v===false)?false:null
  } catch (_) { return null }
}

function nextToLava(b, pos) {
  for (const [dx, dy, dz] of [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]])
    if (b.blockAt(new Vec3(pos.x + dx, pos.y + dy, pos.z + dz))?.name === 'lava') return true
  return false
}

function recordReflex(entry) {
  reflexes.push({ id: `${sessionId}:reflex:${++reflexSeq}`, at: new Date().toISOString(), ...entry })
  reflexes = reflexes.slice(-12)
  diag('reflex', entry)
}

const FOOD_ORDER = ['cooked_beef', 'cooked_porkchop', 'cooked_mutton', 'cooked_salmon', 'baked_potato', 'cooked_chicken',
  'cooked_rabbit', 'cooked_cod', 'bread', 'pumpkin_pie', 'golden_apple', 'apple', 'carrot', 'melon_slice', 'sweet_berries', 'cookie']
function edible(b) {
  const items = b.inventory?.items?.() || []
  return FOOD_ORDER.map(name => items.find(i => i.name === name)).find(Boolean) || null
}

// 28/10: caçando salmão ela ficava parada na água, afundava e tomava dano; sai para o chão firme mais próximo.
function landNear(b, maxDistance = 12) {
  try {
    return b.findBlock?.({ maxDistance, matching: block => block && block.boundingBox === 'block' && block.name !== 'water',
      useExtraInfo: block => ['air', 'cave_air'].includes(b.blockAt(block.position.offset(0, 1, 0))?.name) &&
        ['air', 'cave_air'].includes(b.blockAt(block.position.offset(0, 2, 0))?.name) }) || null
  } catch (_) { return null }
}

// 29/10: afogou em (-198,60,-219) com o reflexo dizendo "fui para terra firme" três vezes sem sair do lugar.
// Agora nada para cima conferindo se a cabeça saiu da água, cava o que tampar a subida e só diz o que mediu.
const WATER_AT_EYES = new Set(['water', 'bubble_column', 'kelp', 'kelp_plant', 'seagrass', 'tall_seagrass'])
function headInWater(b) {
  const p = b.entity.position
  const eyes = b.blockAt(new Vec3(Math.floor(p.x), Math.floor(p.y + 1.62), Math.floor(p.z)))
  return !!eyes && WATER_AT_EYES.has(eyes.name)
}

async function leaveWater(b, still = () => {}) {
  let dug = ''
  b.setControlState('jump', true)
  for (let i = 0; i < 24 && headInWater(b); i++) {  // até 6 s subindo
    const p = b.entity.position
    const above = b.blockAt(new Vec3(Math.floor(p.x), Math.floor(p.y) + 2, Math.floor(p.z)))
    if (above && above.boundingBox === 'block' && !WATER_AT_EYES.has(above.name)) {
      try { await b.dig(above, true); dug += `cavei ${above.name} que tampava a subida; ` } catch (_) {}
      still()
    }
    await ticks(1); still()
  }
  const breathing = !headInWater(b)
  const land = landNear(b)
  if (land) { clearPendingStop(b); b.pathfinder.setGoal(new goals.GoalNear(land.position.x, land.position.y + 1, land.position.z, 0)) }
  await ticks(8); still()
  b.setControlState('jump', false)
  const at = vecToJSON(b.entity.position.floored())
  const where = land ? `estou indo para terra firme em (${land.position.x},${land.position.y + 1},${land.position.z})`
    : 'não vi terra firme a até 12 blocos'
  return dug + (breathing ? `nadei para cima e ${where}`
    : `nadei para cima, mas continuo com a cabeça na água em (${at.x},${at.y},${at.z}), ar ${b.oxygenLevel}/20; ${where}`)
}

function dangerOf(b) {
  const p = b.entity.position
  const head = b.blockAt(new Vec3(Math.floor(p.x), Math.floor(p.y) + 1, Math.floor(p.z)))
  if (head && head.boundingBox === 'block') return { tipo: 'sufocamento', bloco: head }
  // 28/10: queimou 40 vezes durante a coleta e nada disparou: lava nos pés/cabeça ou corpo em chamas.
  const feet = b.blockAt(new Vec3(Math.floor(p.x), Math.floor(p.y), Math.floor(p.z)))
  if (b.entity.isInLava || [feet?.name, head?.name].includes('lava')) return { tipo: 'lava' }
  if (((b.entity.metadata?.[0] ?? 0) & 1) || [feet?.name, head?.name].includes('fire')) return { tipo: 'fogo' }
  if (b.entity.isInWater && typeof b.oxygenLevel === 'number' && b.oxygenLevel <= 12) return { tipo: 'afogamento' }
  // 28/10 (Fácil): parada, quase morreu para 2 creepers, 3 esqueletos e 1 zumbi; o reflexo só agia com dano
  // e só a 5 blocos. Alcance por tipo: corpo a corpo 5, creeper 7, arqueiros 12.
  const reach = { creeper: 5, skeleton: 12, stray: 12, witch: 10 }
  // 30/10 (pedido humano): o alvo da caça não conta como perigo — ela foi atrás dele (a aranha a fazia fugir da caça).
  const prey = activeAction?.type === 'hunt' ? activeAction.entityId : undefined
  const near = Object.values(b.entities).filter(e => e && e !== b.entity && REFLEX_HOSTILE.has(e.name) && e.position &&
    (prey === undefined || e.id !== prey) &&
    b.entity.position.distanceTo(e.position) <= (reach[e.name] || 5))
    .sort((a, c) => b.entity.position.distanceTo(a.position) - b.entity.position.distanceTo(c.position))
  if (near.length) return { tipo: 'monstro', mob: near[0], todos: near }
  // 28/10: vida 4 e fome 2 com 20 pães; o modelo pegou a bancada. Comer com vida e fome baixas é reflexo.
  if (b.health <= 12 && b.food <= 17 && edible(b)) return { tipo: 'fome' }
  return null
}

const ticks = async n => { for (let i = 0; i < n; i++) await new Promise(r => setTimeout(r, 250)) }

// Revisão Codex: a trava do reflexo é da sessão que o começou e vence em REFLEX_MAX_MS — um dig preso não recusa as
// ações para sempre nem atravessa reconexões.
const REFLEX_MAX_MS = 30000
class ReflexExpired extends Error {}
function reflexActive() {
  return Boolean(reflexBusy) && reflexBusy.session === sessionId &&
    (reflexBusy.equipping || Date.now() - reflexBusy.since < REFLEX_MAX_MS)
}

async function survivalReflex(b, ownSession) {
  if (reflexActive() || !b?.entity || bot !== b || sessionId !== ownSession) return
  const danger = dangerOf(b)
  if (!danger) return
  const mine = reflexBusy = { session: ownSession, since: Date.now() }
  // Revisão Codex: vencido o prazo (ou trocada a sessão), o reflexo para depois da espera em curso e não mexe em mais
  // nada — nem devolve o item da mão (o pão que ela equipou depois continuava sendo trocado pela picareta).
  const live = () => reflexBusy === mine && bot === b && sessionId === ownSession &&
    Date.now() - mine.since < REFLEX_MAX_MS
  const still = () => { if (!live()) throw new ReflexExpired('o reflexo passou do prazo; parei sem mexer em mais nada') }
  // A troca pode envolver vários cliques assíncronos no inventário. Enquanto
  // estiver em curso, o prazo impede novas etapas, mas não libera outra RPC.
  const equipHand = async item => {
    still()
    mine.equipping = true
    try { await b.equip(item, 'hand') } finally { mine.equipping = false }
  }
  // 28/10: o reflexo trocava o item da mão (pão, espada) e a colocação seguinte usou a picareta.
  const heldBefore = b.heldItem?.name || null
  const before = b.health, where = vecToJSON(b.entity.position.floored())
  lastDanger = { tipo: danger.tipo, at: Date.now() }
  let acao = ''
  try {
    try { b.pathfinder.setGoal(null) } catch (_) {}
    if (danger.tipo === 'sufocamento') {
      // Cava o bloco da cabeça e o que estiver caindo acima (areia/cascalho), depois pula.
      for (let dy = 1; dy <= 3; dy++) {
        const block = b.blockAt(new Vec3(Math.floor(where.x), Math.floor(where.y) + dy, Math.floor(where.z)))
        if (!block || block.boundingBox !== 'block') break
        await b.dig(block, true); acao += `cavei ${block.name} acima; `; still()
      }
      b.setControlState('jump', true); await ticks(2); still(); b.setControlState('jump', false)
    } else if (danger.tipo === 'lava' || danger.tipo === 'fogo') {
      // Afasta-se da lava mais próxima (ou só pula para fora do fogo) sem esperar o modelo.
      const lava = b.findBlock?.({ matching: block => block?.name === 'lava', maxDistance: 4 })
      b.setControlState('jump', true)
      if (lava) {
        const dx = where.x - lava.position.x, dz = where.z - lava.position.z, norm = Math.max(1, Math.hypot(dx, dz))
        clearPendingStop(b)
        b.pathfinder.setGoal(new goals.GoalNear(Math.floor(where.x + 5 * dx / norm), where.y, Math.floor(where.z + 5 * dz / norm), 1))
      }
      await ticks(4); still(); b.setControlState('jump', false)
      acao = lava ? `pulei e me afastei da lava em (${lava.position.x},${lava.position.y},${lava.position.z})` : 'pulei para sair do fogo'
    } else if (danger.tipo === 'afogamento') {
      acao = await leaveWater(b, still)
    } else if (danger.tipo === 'fome') {
      const food = edible(b), before = b.food
      await equipHand(food); still(); await b.consume(); still()
      acao = `comi ${food.name} (fome ${before} → ${b.food}/20)`
    } else if (danger.tipo === 'monstro') {
      const mob = danger.mob, all = danger.todos || [mob]
      const creeper = all.find(e => e.name === 'creeper'), ranged = all.filter(e => ['skeleton', 'stray', 'witch'].includes(e.name))
      const crowd = all.filter(e => b.entity.position.distanceTo(e.position) <= 8).length
      // 30/10: só o arqueiro a distância repetia a fuga sem fim; 4 fugas dele em 1 min sem sair do alcance → fica.
      // Revisão Codex: com outro monstro a ≤4 blocos não é "arqueiro sozinho" (o zumbi colado continua tratado).
      const meleeMob = all.filter(e => !ranged.includes(e) && b.entity.position.distanceTo(e.position) <= 4)
        .sort((p, q) => b.entity.position.distanceTo(p.position) - b.entity.position.distanceTo(q.position))[0]
      const melee = Boolean(meleeMob)
      const archerOnly = !creeper && !melee && crowd < 3 && b.health > 8 && ranged.length && b.entity.position.distanceTo(ranged[0].position) > 6
      fleeLog = fleeLog.filter(t => Date.now() - t < 60000)
      const tiredOfFleeing = archerOnly && fleeLog.length >= 4
      if (tiredOfFleeing) {
        acao = `não fugi de ${ranged[0].name} a ${b.entity.position.distanceTo(ranged[0].position).toFixed(1)} blocos: já fugi ${fleeLog.length} vezes em 1 min sem sair do alcance`
      } else if (creeper || crowd >= 3 || b.health <= 8 || (ranged.length && !melee && b.entity.position.distanceTo(ranged[0].position) > 4)) {
        // Foge do centro do grupo: creeper explode, arqueiro acerta de longe, muitos de uma vez cercam.
        // 30/10: fuga sem cavar nem empilhar por 3 s (numa caverna ela gastou as duas picaretas cavando a fuga).
        // Revisão Codex: com Movements próprios; os compartilhados (coleta e demais ações) continuam cavando.
        // Revisão Codex: não segura o reflexo durante a fuga — afogamento, lava e fome continuam sendo atendidos.
        const cx = all.reduce((s, e) => s + e.position.x, 0) / all.length, cz = all.reduce((s, e) => s + e.position.z, 0) / all.length
        const dx = b.entity.position.x - cx, dz = b.entity.position.z - cz, norm = Math.max(1, Math.hypot(dx, dz))
        if (archerOnly) fleeLog.push(Date.now())
        noDigFor(b, FLEE_NO_DIG_MS)
        clearPendingStop(b)
        b.pathfinder.setGoal(new goals.GoalNear(Math.floor(where.x + 16 * dx / norm), where.y, Math.floor(where.z + 16 * dz / norm), 2))
        acao = `fugi de ${all.map(e => e.name).join(', ')}` + (creeper ? ' (creeper explode)' : b.health <= 8 ? ' com vida baixa' : '')
      } else {
        // Revisão Codex: arqueiro longe + zumbi colado → defende-se do zumbi (antes fugia com ele junto).
        const target = meleeMob || mob
        const sword = ['netherite_sword', 'diamond_sword', 'iron_sword', 'stone_sword', 'wooden_sword']
          .map(name => b.inventory.items().find(i => i.name === name)).find(Boolean)
        if (sword && b.heldItem?.name !== sword.name) { try { await equipHand(sword); acao += `empunhei ${sword.name}; ` } catch (_) {} }
        still()
        for (let i = 0; i < 4 && target.isValid !== false && b.entity.position.distanceTo(target.position) <= 4; i++) {
          b.attack(target); await ticks(2); still()
        }
        acao += `me defendi atacando ${target.name}`
      }
    }
  } catch (err) {
    acao += err instanceof ReflexExpired ? `interrompido: ${err.message}` : `falhou: ${err?.message || err}`
  } finally {
    if (live() && heldBefore && b.heldItem?.name !== heldBefore) {
      const item = b.inventory.items().find(i => i.name === heldBefore)
      if (item) { try { await equipHand(item); acao += `; voltei a segurar ${heldBefore}` } catch (_) {} }
    }
    if (reflexBusy === mine) reflexBusy = false
  }
  recordReflex({ tipo: danger.tipo, posicao: where, vida_antes: before, vida_depois: b.health,
    detalhe: danger.bloco ? `cabeça dentro de ${danger.bloco.name}` : danger.mob ? `${danger.mob.name} a ${b.entity.position.distanceTo(danger.mob.position).toFixed(1)} blocos` : '',
    acao: acao.trim() })
}

function nearbyEntities(maxDistance = 24, limit = 24) {
  if (!bot?.entity) return []
  return Object.values(bot.entities)
    .filter(e => e && e !== bot.entity && e.position && distance(bot.entity,e)<=maxDistance)
    .map(e => ({
      id: e.id,
      name: e.name || e.displayName || e.type || 'entity',
      username: e.username || null,
      type: e.type || null,
      distance: Number(distance(bot.entity, e)?.toFixed(2)),
      position: vecToJSON(e.position.floored()),
      health: typeof e.health === 'number' ? e.health : null,
      lineOfSight: entityLineOfSight(e),
    }))
    .filter(e => e.distance != null && e.distance <= maxDistance)
    .sort((a, b) => a.distance - b.distance)
    .slice(0, limit)
}

// 30/10 (pedido humano): rastrear o alvo mais próximo mesmo fora da lista curta. A lista só levava as 32 mais perto
// (até 48 blocos); com muitos morcegos e zumbis, a aranha a 40 blocos ficava de fora. Junta o mais próximo de cada
// espécie que o jogo conhece (o servidor só envia as que estão no alcance de rastreio dele), marcado longe=true.
function trackedEntities(maxDistance = 48, limit = 32) {
  const near = nearbyEntities(maxDistance, limit)
  if (!bot?.entity) return near
  const names = new Set(near.map(e => e.name)), extra = new Map()
  for (const e of Object.values(bot.entities)) {
    if (!e || e === bot.entity || !e.position || e.type === 'object' || e.name === 'item') continue
    const name = e.name || e.displayName || e.type || 'entity', d = distance(bot.entity, e)
    if (names.has(name) || d == null || (extra.has(name) && extra.get(name).d <= d)) continue
    extra.set(name, { e, d })
  }
  return [...near, ...[...extra.values()].sort((a, b) => a.d - b.d).slice(0, 12).map(({ e, d }) => ({
    id: e.id, name: e.name || e.displayName || e.type || 'entity', username: e.username || null, type: e.type || null,
    distance: Number(d.toFixed(2)), position: vecToJSON(e.position.floored()), health: typeof e.health === 'number' ? e.health : null,
    lineOfSight: entityLineOfSight(e), longe: true }))]
}

function state() {
  if (!bot) return {
    connected: false,
    spawned: false,
    host: null,
    port: null,
    version: null,
    lastError,
    lastEvent,
    activeAction,
    connectionState,
    bridgeProtocol: BRIDGE_PROTOCOL,
    sessionId,
    recentChat: [],
  }
  return {
    connected: connectionState === 'ready',
    transportConnected: ['logged_in', 'spawned', 'ready'].includes(connectionState),
    verified: connectionState === 'ready',
    connectionState,
    sessionId,
    spawned: !!bot.entity,
    host:connectionTarget?.sessionId===sessionId?connectionTarget.host:null,
    port:connectionTarget?.sessionId===sessionId?connectionTarget.port:null,
    username: bot.username,
    version: bot.version,
    position: vecToJSON(bot.entity?.position?.floored()),
    health: bot.health,
    // Luz do céu na cabeça (15 = céu aberto); 28/10: caçava morcegos no subsolo sem saber onde há animais.
    skyLight: (() => { try { const p = bot.entity.position; return bot.blockAt(new Vec3(Math.floor(p.x), Math.floor(p.y) + 1, Math.floor(p.z)))?.skyLight ?? null } catch (_) { return null } })(),
    food: bot.food,
    oxygen: bot.oxygenLevel,
    dimension: bot.game?.dimension || null,
    gameMode: bot.game?.gameMode || null,
    heldItem: bot.heldItem ? { name: bot.heldItem.name, count: bot.heldItem.count } : null,
    inventory: inventorySummary(),
    equipment: Array.isArray(bot.inventory?.slots) ? Object.fromEntries(
      [['head',5],['torso',6],['legs',7],['feet',8]].map(([slot,index])=>{
        const item=bot.inventory.slots[index]
        return [slot,item?{name:item.name,count:item.count}:null]
      })) : null,
    nearbyEntities: trackedEntities(48, 32),  // pedido humano 28/10: visão maior; 30/10: + mais próximo de cada espécie
    // 12/11 (humano: "qual o sentido dela perguntar no chat se não tem ninguém para responder?"): quem mais está no
    // servidor agora, a qualquer distância (lista de jogadores do servidor), sem ela mesma.
    onlinePlayers: Object.keys(bot.players || {}).filter(name => name !== bot.username).sort(),
    // 12/11: mochila cheia travava a coleta ("inventário cheio (36 pilhas)") e ela ia procurar o bloco em outro lugar.
    freeSlots: typeof bot.inventory?.emptySlotCount === 'function' ? bot.inventory.emptySlotCount() : null,
    recentChat: recentChat.map(message => ({ ...message })),
    lastDeath: lastDeath ? { ...lastDeath } : null,
    reflexes: reflexes.map(entry => ({ ...entry })),
    kills: kills.map(entry => ({ ...entry })),
    // Fatos do depósito, sem fase: o forno não é reaberto a cada estado (27/10 18:03,
    // "processing" antigo a fez buscar carvão para um forno já pronto).
    furnaceRuns: [...furnaceRuns].filter(([k]) => k.startsWith(furnacePrefix(bot))).map(([, run]) => ({
      position: run.position, input: run.input, expectedOutput: run.expectedOutput, count: run.count,
      remaining: run.remaining, fuel: run.fuel ?? null, fuelCount: run.fuelCount ?? null, depositedAt: run.startedAt })),
    pathfinding: activeAction,
    lastError,
    lastEvent,
  }
}

function requireBot() {
  if (!bot || !bot.entity || connectionState !== 'ready') throw new Error('bot não conectado/verificado no Minecraft')
  return bot
}

function confirmSession(ownBot, ownSession) {
  if (bot !== ownBot || sessionId !== ownSession) throw new Error('sessão substituída durante ação; resultado incerto')
}

async function connect(args) {
  const previous = bot
  bot = null  // torna callbacks antigos inertes antes de quit emitir end
  sessionId = newSession()
  fleeLog = []  // revisão Codex: o contador de fugas não atravessa reconexões
  fleeNoDig = null
  reflexBusy = false  // o reflexo da sessão antiga não trava a nova
  const ownSession = sessionId
  if (previous) { try { previous.quit('reconectando') } catch (_) {} }
  connectionState = 'connecting'
  lastError = null
  lastEvent = null
  recentChat = []
  chatSequence = 0
  lastHealth = null
  activeAction = null
  mcData = null
  movements = null
  const host = args.host || '127.0.0.1'
  const port = Number(args.port || 25565)
  const username = args.username || process.env.HOSHINO_MINECRAFT_USERNAME || 'HoshinoMC'
  const version = args.version || DEFAULT_VERSION
  const auth = args.auth || 'offline'
  const startedAt = Date.now()
  diag('connect.start', { sessionId, host, port, username, version, auth })

  return await new Promise((resolve, reject) => {
    let settled = false
    let ended = false
    const ownBot = mineflayer.createBot({ host, port, username, version, auth, logErrors: true, hideErrors: false })
    bot = ownBot
    connectionTarget={sessionId:ownSession,host,port}
    const current = () => bot === ownBot && sessionId === ownSession
    ownBot.on('error', () => {}) // setup pode falhar antes de instalar o handler diagnóstico
    let watching = null
    const on = (event, callback, once = false) => {
      ownBot[once ? 'once' : 'on'](event, (...values) => {
        if (!current()) {
          diag('event.stale_ignored', { event, sessionId: ownSession })
          if (!settled && ['end', 'error', 'spawn'].includes(event)) {
            settled = true
            reject(new Error('sessão substituída; não confirmada'))
          }
          return
        }
        return callback(...values)
      })
    }
    try {
      ownBot.loadPlugin(pathfinder)
      ownBot.loadPlugin(collectBlock)
    } catch (err) {
      connectionState = 'error'
      lastError = String(err?.stack || err)
      settled = true
      diag('spawn.setup_error', { sessionId: ownSession, error: lastError })
      reject(err)
      try { ownBot.quit('setup falhou') } catch (_) {}
      return
    }

    on('inject_allowed', () => { diag('event.inject_allowed', { sessionId: ownSession }) })
    on('login', () => { connectionState = 'logged_in'; setEvent('login', `${username} registrou no servidor`); diag('event.login', { sessionId: ownSession }) }, true)
    on('spawn', async () => {
      if (ended) return  // timeout/erro não pode virar ready com spawn tardio
      try {
        mcData = mcDataFactory(bot.version)
        movements = new Movements(bot, mcData)
        // 28/10: coletando pedra, o pathfinder quebrou o forno dela que estava no caminho;
        // estações de trabalho não são obstáculo a cavar (o padrão só protege o baú).
        for (const name of ['crafting_table', 'furnace']) {
          const id = mcData.blocksByName?.[name]?.id
          if (id != null) movements.blocksCantBreak?.add(id)
        }
        bot.pathfinder.setMovements(movements)
        // collect() reaplica seu próprio Movements antes de navegar. Compartilhar
        // o objeto protegido evita perder essas restrições durante a coleta.
        bot.collectBlock.movements = movements
        // Padrão -1 = busca ilimitada; cavando no subsolo, uma coleta levou a ponte a OOM.
        // Limita só o desvio além da distância direta (maxCost = h + raio), não o destino.
        bot.pathfinder.searchRadius = PATH_SEARCH_RADIUS
        // 28/10: subir 41 blocos pelo subsolo estourava os 5 s padrão para decidir a rota.
        bot.pathfinder.thinkTimeout = 15000
        if (typeof setInterval === 'function') {  // uma vigia por conexão (vale também depois de renascer)
          if (gazeTimer) clearInterval(gazeTimer)
          gazeTimer = setInterval(() => {
            // Revisão Codex: em end/erro/kick current() pode seguir verdadeiro; a conexão encerrada também para.
            if (!current() || ended || !ownBot.entity) { clearInterval(gazeTimer); gazeTimer = null; return }
            try { restoreDigging(false); gaze(ownBot) } catch (_) {} }, GAZE_MS)  // religa o cavar depois da fuga
        }
      } catch (err) {
        ended = true
        lastError = String(err?.stack || err)
        connectionState = 'error'
        diag('spawn.setup_error', { sessionId: ownSession, error: lastError })
        if (!settled) { settled = true; reject(err) }
        return
      }
      connectionState = 'spawned'
      setEvent('spawn', `${bot.username} entrou no mundo`)
      diag('event.spawn', { sessionId, state: state() })
      await new Promise(r => setTimeout(r, 250))
      if (current() && !ended && ownBot.entity && connectionState === 'spawned') {
        connectionState = 'ready'
        diag('connect.verified', { sessionId, elapsed_ms: Date.now() - startedAt, state: state() })
        if (!settled) {
          settled = true
          resolve({ verified: true, connection_state: connectionState, session_id: sessionId, state: state(), message: `Conexão verificada como ${bot.username} em ${host}:${port} (${bot.version}).` })
        }
      }
    }, true)
    on('messagestr', message => { setEvent('message', message); diag('event.message', { sessionId, message }) })
    on('actionBar', msg => { diag('event.actionBar', { sessionId, message: String(msg) }) })
    on('chat', (username2, message) => { diag('event.chat', { sessionId, username: username2, message }) })
    on('message', (packet, position) => {
      // O evento chat legado também vem de regex sobre avisos de servidor.
      // Só a mensagem tipada do protocolo atribui uma fala ao remetente aqui.
      if (position !== 'chat' || packet?.translate !== 'chat.type.text' || !Array.isArray(packet.with) || packet.with.length < 2) return
      const username2 = packet.with[0]?.toString(), message = packet.with[1]?.toString()
      if (typeof username2 !== 'string' || !/^[A-Za-z0-9_]{1,16}$/.test(username2) || typeof message !== 'string' ||
          username2.toLowerCase() === ownBot.username.toLowerCase() || !message.trim()) return
      const seq = ++chatSequence
      recentChat.push({ id: `${ownSession}:chat:${seq}`, seq, sessionId: ownSession,
        username: username2, message: message.replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, 512),
        at: new Date().toISOString() })
      recentChat = recentChat.slice(-32)
    })
    on('health', () => {
      if (ownBot.health > 0 && ownBot.entity?.position) lastAlive = { position: vecToJSON(ownBot.entity.position.floored()),
        dimension: ownBot.game?.dimension || null, items: inventorySummary() }
      const dropped = lastHealth != null && ownBot.health < lastHealth
      lastHealth = ownBot.health
      if (dropped && ownBot.health > 0) survivalReflex(ownBot, ownSession).catch(e => diag('reflex.error', { error: String(e?.message || e) }))
      if (!watching && typeof setInterval === 'function') {
        // Vigia ativa: monstro perto age antes do dano (sem tarefa, ela ficava parada até apanhar).
        watching = setInterval(() => {
          if (!current()) { clearInterval(watching); watching = null; return }
          restoreDigging(false)  // 30/10: fim da fuga sem cavar
          // 28/10: fugindo a cada segundo de um creeper distante, ela não conseguia subir e dava voltas.
          // Durante uma ação, só ameaça a até 3 blocos interrompe; dano continua disparando o reflexo.
          const danger = ownBot.health > 0 ? dangerOf(ownBot) : null
          if ((danger?.tipo === 'monstro' && (!activeAction || ownBot.entity.position.distanceTo(danger.mob.position) <= 3))
              || (danger?.tipo === 'fome' && !activeAction) || danger?.tipo === 'afogamento')
            survivalReflex(ownBot, ownSession).catch(e => diag('reflex.error', { error: String(e?.message || e) }))
        }, 1000)
      }
      setEvent('health', `${ownBot.health} HP / ${ownBot.food} fome`); diag('event.health', { sessionId, health: ownBot.health, food: ownBot.food, oxygen: ownBot.oxygenLevel }) })
    on('entityDead', entity => {
      const hit = attackedAt.get(entity?.id)
      if (!hit || Date.now() - hit.at > 15000) return
      attackedAt.delete(entity.id)
      kills = [...kills, { name: hit.name, entityId: entity.id, at: new Date().toISOString(), sessionId: ownSession }].slice(-10)
      setEvent('kill', `${hit.name} morreu depois dos meus golpes`)
    })
    on('death', () => {
      const at = new Date()
      lastDeath = { ...(lastAlive || {}), at: at.toISOString(), itemsDespawnAt: new Date(at.getTime() + ITEM_DESPAWN_MS).toISOString(), sessionId: ownSession,
        causa_provavel: lastDanger && at.getTime() - lastDanger.at < 30000 ? lastDanger.tipo : 'desconhecida' }
      recordReflex({ tipo: 'morte', causa_provavel: lastDeath.causa_provavel, posicao: lastDeath.position || null,
        itens_que_cairam: lastDeath.items || [], itens_somem_em: lastDeath.itemsDespawnAt })
      lastHealth = null
      setEvent('death', `${ownBot.username} morreu`); diag('event.death', { sessionId, lastDeath, state: state() }) })
    on('respawn', () => { setEvent('respawn', `${ownBot.username} mudou de dimensão/ressurgiu`); diag('event.respawn', { sessionId, state: state() }) })
    on('playerJoined', player => { diag('event.playerJoined', { sessionId, username: player?.username }) })
    on('playerLeft', player => { diag('event.playerLeft', { sessionId, username: player?.username }) })
    on('kicked', reason => {
      ended = true
      lastError = `kick: ${typeof reason === 'string' ? reason : JSON.stringify(reason)}`
      connectionState = 'error'
      setEvent('kicked', lastError)
      diag('event.kicked', { sessionId, error: lastError, loggedIn: true })
      if (!settled) { settled = true; reject(new Error(lastError)) }
    })
    on('end', reason => {
      ended = true
      connectionState = 'disconnected'
      setEvent('end', String(reason || 'conexão encerrada'))
      activeAction = null
      diag('event.end', { sessionId, reason: String(reason || 'socketClosed') })
      if (!settled) { settled = true; reject(new Error(`conexão terminou antes de ficar pronta: ${String(reason || 'socketClosed')}`)) }
    })
    on('error', err => {
      ended = true
      lastError = String(err?.stack || err)
      connectionState = 'error'
      diag('event.error', { sessionId, error: lastError, state: state() })
      if (!settled) { settled = true; reject(err) }
    })
    on('game', game => { diag('event.game', { sessionId, gameMode: game?.gameMode, dimension: game?.dimension }) })
    on('path_stop', () => {
      if (['goto','follow'].includes(activeAction?.type)) activeAction = null
      setEvent('path_stop', 'pathfinder confirmou término da navegação')
      diag('event.path_stop', { sessionId: ownSession })
    })
    on('resourcePack', (url, hash) => { diag('event.resourcePack', { sessionId, url, hash }) })

    setTimeout(() => {
      if (!settled) {
        settled = true
        ended = true
        if (!current()) { reject(new Error('sessão substituída; não confirmada')); return }
        connectionState = 'error'
        const err = new Error('timeout aguardando spawn/verificação do bot')
        lastError = err.message
        diag('connect.timeout', { sessionId, elapsed_ms: Date.now() - startedAt, state: state() })
        reject(err)
      }
    }, 20000)
  })
}

async function disconnect() {
  if (!bot) return 'Bot já estava desconectada.'
  try { bot.quit('desconectando por decisão da Hoshino') } catch (_) {}
  bot = null
  mcData = null
  movements = null
  activeAction = null
  connectionState = 'disconnected'
  diag('disconnect', { sessionId })
  setEvent('disconnect', 'desconectada')
  return 'Desconectada.'
}

function inventory() {
  requireBot()
  return inventorySummary()
}

// Percepção textual pedida pela entidade/ciclo: o que há por perto e o que cada receita
// pede contra o inventário. Só lê; não escolhe nem executa nada.
const USEFUL_BLOCKS=/(_log$|^stone$|^cobblestone$|_ore$|^crafting_table$|^furnace$|^water$|^lava$|^sand$|^gravel$)/

function direction(dx,dy,dz) {
  const h=[dz<-0.5?'norte':dz>0.5?'sul':'',dx>0.5?'leste':dx<-0.5?'oeste':''].filter(Boolean).join('-')
  return [h||'aqui',dy>1?'acima':dy<-1?'abaixo':''].filter(Boolean).join(', ')
}

// Uma busca por tipo: numa só busca limitada, blocos abundantes (pedra) ocupavam todas
// as vagas e escondiam minério a poucos blocos (27/10: só "stone" com ferro a 9,7).
// Ferramentas que fazem o bloco soltar item (minecraft-data harvestTools). Quebrar
// minério sem elas destrói o bloco sem drop: recusar antes do envio, com explicação.
function harvestTools(name) {
  const tools=mcData?.blocksByName?.[name]?.harvestTools
  return tools?Object.keys(tools).map(id=>mcData.items?.[id]?.name).filter(Boolean):null
}

function canHarvest(name) {
  const tools=harvestTools(name)
  if (!tools) return {ok:true,tools:null}
  const have=new Set(inventorySummary().map(i=>i.name))
  return {ok:tools.some(t=>have.has(t)),tools}
}

function requireHarvest(name) {
  const need=canHarvest(name)
  if (!need.ok) throw new NoEffectError(`quebrar ${name} sem ${need.tools.join(' ou ')} destrói o bloco sem soltar nada; `+
    'fabrique ou equipe uma dessas ferramentas antes',{block:name,ferramentas:need.tools,inventory:inventorySummary()},'harvest_preconditions')
}

function surroundings(b) {
  const types=Object.values(mcData?.blocksByName||{}).filter(x=>USEFUL_BLOCKS.test(x.name))
  if (!types.length||!b.findBlocks||!b.entity) return {}
  const me=b.entity.position,out={}
  for (const type of types) {
    const found=b.findBlocks({matching:type.id,maxDistance:32,count:64})
    if (!found.length) continue
    const near=found.map(p=>[Math.hypot(p.x-me.x,p.y-me.y,p.z-me.z),p]).sort((a,c)=>a[0]-c[0])[0]
    const need=canHarvest(type.name)
    out[type.name]={mais_proximo:vecToJSON(near[1]),distancia:Number(near[0].toFixed(1)),
      direcao:direction(near[1].x-me.x,near[1].y-me.y,near[1].z-me.z),quantidade:found.length>=64?'64+':found.length,
      // 28/10: um bloco por decisão deixava o resto do veio para trás; veio = iguais a até 3 blocos do mais próximo.
      veio:found.filter(p=>Math.hypot(p.x-near[1].x,p.y-near[1].y,p.z-near[1].z)<=3).length,
      ferramenta_ok:need.ok,...(need.tools?{ferramentas:need.tools.slice(0,3)}:{})}
  }
  return out
}

// Fundição é regra do jogo que não aparece em recipesAll: informar como fato da receita.
const SMELTING={iron_ingot:['iron_ore'],gold_ingot:['gold_ore'],stone:['cobblestone'],glass:['sand','red_sand'],
  charcoal:['oak_log','spruce_log','birch_log','jungle_log','acacia_log','dark_oak_log'],
  // 28/10: carnes cruas assam no forno (pedido humano: 30 carnes assadas).
  cooked_beef:['beef'],cooked_porkchop:['porkchop'],cooked_chicken:['chicken'],cooked_mutton:['mutton'],
  cooked_rabbit:['rabbit'],cooked_cod:['cod'],cooked_salmon:['salmon']}
const FUELS=['coal','charcoal']

function smeltingVariants(b,name,have) {
  const furnaceId=mcData?.blocksByName?.furnace?.id
  const furnace=furnaceId==null?null:b.findBlock({matching:furnaceId,maxDistance:4})
  const fuel=FUELS.some(f=>(have[f]||0)>0)
  return (SMELTING[name]||[]).map(input=>({processo:'fornalha',exige_forno:true,forno_a_4_blocos:!!furnace,
    ingredientes:[{nome:input,precisa:1,tem:have[input]||0}],combustivel:'coal ou charcoal (1 funde 8 itens)',
    tem_combustivel:fuel,faltam_unidades:Math.max(0,1-(have[input]||0)),
    pode_agora:(have[input]||0)>=1&&!!furnace&&fuel}))
}

function craftAnalysis(b,name) {
  const id=mcData?.itemsByName?.[name]?.id
  if (id==null) return {item:name,erro:'item desconhecido nesta versão'}
  const tableId=mcData?.blocksByName?.crafting_table?.id
  const table=tableId==null?null:b.findBlock({matching:tableId,maxDistance:4})
  const have=Object.fromEntries(inventorySummary().map(i=>[i.name,i.count]))
  const variants=b.recipesAll(id,null,true).slice(0,12).map(r=>{
    const needs=(r.delta||[]).filter(i=>i.count<0).map(i=>{
      const n=mcData.items?.[i.id]?.name||String(i.id);return {nome:n,precisa:-i.count,tem:have[n]||0}})
    const missing=needs.reduce((sum,x)=>sum+Math.max(0,x.precisa-x.tem),0)
    return {exige_bancada:!!r.requiresTable,ingredientes:needs,faltam_unidades:missing,
      pode_agora:missing===0&&(!r.requiresTable||!!table)}
  }).concat(smeltingVariants(b,name,have)).sort((a,b)=>a.faltam_unidades-b.faltam_unidades).slice(0,3)
  return {item:name,bancada_a_4_blocos:!!table,variantes:variants}
}

function perception(names) {
  const b=requireBot()
  return {arredores:surroundings(b),receitas:names.slice(0,6).map(n=>craftAnalysis(b,String(n).trim().toLowerCase()))}
}

function findBlocks(args) {
  const b = requireBot()
  const name = String(args.name || '').trim().toLowerCase()
  if (!name) throw new Error('nome do bloco vazio')
  const id = mcData?.blocksByName?.[name]?.id
  if (id == null) throw new Error(`bloco '${name}' não existe em minecraft-data ${b.version}`)
  const count = Math.max(1, Math.min(64, Number(args.count || 16)))
  const maxDistance = Math.max(1, Number(args.maxDistance || 64))
  const positions = b.findBlocks({ matching: id, maxDistance, count })
  return positions.map((p, i) => ({ index: i, position: vecToJSON(p), distance: Number(b.entity.position.distanceTo(p).toFixed(2)) }))
}

// 30/10: caminhada de ~60 blocos passou dos 60 s do cliente; a ponte seguia andando sem responder e a ação virava
// "incerta" (tarefa pausada). Com orçamento próprio abaixo desse prazo, devolve o trecho medido.
const GOTO_BUDGET_MS = 50000

async function gotoPoint(args) {
  const b = requireBot()
  const ownSession = sessionId
  const x = Number(args.x), y = Number(args.y), z = Number(args.z)
  const range = Number(args.range ?? 1)
  if (![x, y, z].every(Number.isFinite)) throw new Error('coordenadas inválidas')
  clearPendingStop(b)  // antes de registrar a ação: o path_stop da limpeza apaga activeAction de goto/follow
  activeAction = { type: 'goto', target: { x, y, z, range } }
  setEvent('action', `indo para ${x}, ${y}, ${z}`)
  const from = cell(b.entity?.position)
  const start = b.entity?.position ? { x: b.entity.position.x, z: b.entity.position.z } : null
  try {
    let timer
    const walking = b.pathfinder.goto(new goals.GoalNear(x, y, z, range))
    const budget = new Promise(resolve => { timer = setTimeout(() => resolve('budget'), GOTO_BUDGET_MS) })
    const outcome = await Promise.race([walking.then(() => 'arrived'), budget])
    clearTimeout(timer)
    if (outcome === 'budget' && bot === b && sessionId === ownSession) {
      walking.catch(() => {})  // o objetivo é limpo abaixo; a rejeição tardia (GoalChanged) é esperada
      try { b.pathfinder.setGoal(null) } catch (_) {}
      activeAction = null
      const here = vecToJSON(b.entity.position.floored())
      const left = Math.round(Math.hypot(x - here.x, z - here.z))
      setEvent('action', `caminhada pausada após ${GOTO_BUDGET_MS / 1000} s`)
      // 30/10: 50 s pulando no lugar voltavam como "Andei ... de A até A" e ela repetia a mesma caminhada. O avanço é
      // medido na horizontal (um salto muda Y); não afirma "sem efeito": o pathfinder pode ter cavado ou posto andaime.
      const moved = start ? Math.hypot(b.entity.position.x - start.x, b.entity.position.z - start.z) : null
      if (moved != null && moved < 1.5)
        return `Tentei andar ${GOTO_BUDGET_MS / 1000} s rumo a ${x}, ${y}, ${z}, mas fiquei presa perto de ${from}: ` +
          `avancei menos de 2 blocos e faltam cerca de ${left}. O caminho parece bloqueado (subida alta, folhas, buraco); ` +
          `repetir o mesmo destino tende a dar no mesmo. Estado: ${JSON.stringify(state())}`
      return `Andei ${GOTO_BUDGET_MS / 1000} s rumo a ${x}, ${y}, ${z}: de ${from} até ${here.x}, ${here.y}, ${here.z}; ` +
        `faltam cerca de ${left} blocos. Continue daqui. Estado: ${JSON.stringify(state())}`
    }
    confirmSession(b, ownSession)
    activeAction = null
    setEvent('goal_reached', `cheguei perto de ${x}, ${y}, ${z}`)
    return `Cheguei perto de ${x}, ${y}, ${z}. Estado: ${JSON.stringify(state())}`
  } catch (err) {
    const error = String(err?.stack || err)
    // 28/10: a vigia de reflexo fugiu de um creeper no meio da subida; o objetivo trocado é a fuga,
    // não falha: devolve a posição medida e mantém a fuga em andamento (sem limpar o objetivo).
    if (err?.name === 'GoalChanged' && lastDanger && Date.now() - lastDanger.at < 10000 && bot === b && sessionId === ownSession) {
      activeAction = null
      const here = vecToJSON(b.entity.position.floored())
      setEvent('action', `navegação interrompida pelo reflexo (${lastDanger.tipo})`)
      return `Navegação até ${x}, ${y}, ${z} interrompida pelo reflexo de sobrevivência (${lastDanger.tipo}: ` +
        `${reflexes.at(-1)?.acao || 'agi para me proteger'}); estou em ${here.x}, ${here.y}, ${here.z}. Estado: ${JSON.stringify(state())}`
    }
    if (bot === b && sessionId === ownSession) {
      activeAction = null; lastError = error
      // goto() da biblioteca não limpa o objetivo ao falhar: sem isto o bot pode andar mais tarde.
      try { b.pathfinder.setGoal(null) } catch (_) {}
      if (err?.name === 'Timeout' && from && cell(b.entity?.position) !== from) {
        const here = vecToJSON(b.entity.position.floored())
        return `O caminho até ${x}, ${y}, ${z} é longo demais para decidir de uma vez; andei de ${from} até ` +
          `${here.x}, ${here.y}, ${here.z}. Continue daqui ou escolha um ponto intermediário. Estado: ${JSON.stringify(state())}`
      }
      // 12/11: o pathfinder andou um trecho e depois deu NoPath (de -170,42,-135 a -169,42,-133). Virava HTTP 400,
      // recibo incerto e a tarefa parava inteira. Como no tempo esgotado: devolve o trecho medido e o estado; não
      // afirma "sem efeito" (o pathfinder pode ter cavado ou posto bloco) e a decisão seguinte vê a posição real.
      if (err?.name === 'NoPath' && from && cell(b.entity?.position) !== from) {
        const here = vecToJSON(b.entity.position.floored())
        setEvent('action', `sem caminho até ${x}, ${y}, ${z}; parei em ${here.x}, ${here.y}, ${here.z}`)
        return `Não achei caminho até ${x}, ${y}, ${z}; andei de ${from} até ${here.x}, ${here.y}, ${here.z} e parei. ` +
          `Repetir o mesmo destino tende a dar no mesmo: escolha um ponto mais próximo, abra passagem ou faça o que ` +
          `precisa daqui. Estado: ${JSON.stringify(state())}`
      }
      if (PATH_FAILURES.includes(err?.name) && from && cell(b.entity?.position) === from)
        throw new NoEffectError(`nenhum caminho até (${x}, ${y}, ${z}) dentro do limite de busca; você não saiu do lugar. `+
          'Escolha um destino mais próximo, abra passagem ou faça o que precisa onde está.',
          {from, target: {x, y, z}, reason: err.name}, 'goto_no_path', 'verified', 'not_applied')
    }
    throw new Error(`navegação falhou: ${error}`)
  }
}

// 30/10: pathfinder.stop() com o bot parado (ex.: cancelTask do collectBlock depois de a coleta estourar o tempo)
// deixa uma parada pendente; o próximo setGoal a executa na hora e o objetivo novo falha com PathStopped sem sair do
// lugar. Sem objetivo nem caminho ativo, setGoal(null) só consome a pendência; com objetivo ativo (fuga do reflexo,
// mesmo antes de o caminho ser calculado), não mexe.
const FLEE_NO_DIG_MS = 3000
function noDigFor(b, ms) {
  if (!movements) return
  if (!fleeNoDig) {
    // Cópia rasa dos Movements compartilhados; a coleta (collectBlock) põe os originais de volta ao começar.
    const moves = Object.assign(Object.create(Object.getPrototypeOf(movements)), movements)
    moves.canDig = false; moves.allow1by1towers = false; moves.scafoldingBlocks = []
    fleeNoDig = { moves }
  }
  fleeNoDig.until = Date.now() + ms
  if (b.pathfinder.movements !== fleeNoDig.moves) b.pathfinder.setMovements(fleeNoDig.moves)
}
function restoreDigging(force = true) {
  // Revisão Codex: setMovements limpa os controles (resetPath); durante outro reflexo (subindo da água com
  // 'jump') espera ele terminar — a vigia tenta de novo.
  if (!fleeNoDig || reflexActive() || (!force && Date.now() < fleeNoDig.until)) return
  const moves = fleeNoDig.moves
  fleeNoDig = null
  // Revisão Codex: setMovements recomeça a busca (resetPath); um caminho que só existia cavando volta a ser achado.
  // Se outra ação já trocou os Movements (a coleta põe os seus), não mexe.
  if (bot && movements && bot.pathfinder?.movements === moves) bot.pathfinder.setMovements(movements)
}

// Revisão Codex: caminhadas de uma vez só (explorar, recolher item, entregar) limpam apenas o próprio objetivo; se o
// reflexo trocou por uma fuga, a fuga continua.
function clearOwnGoal(b, goal) {
  try { if (!b.pathfinder.goal || b.pathfinder.goal === goal) b.pathfinder.setGoal(null) } catch (_) {}
}

function clearPendingStop(b) {
  try { if (!b.pathfinder.goal && !b.pathfinder.isMoving?.()) b.pathfinder.setGoal(null) } catch (_) {}
}

// 30/10 (pedido humano): a cabeça acompanha o alvo. Só com o corpo livre (nenhum comando que mira bloco em
// execução, sem andar, cavar ou reflexo); caçando ou seguindo, olha o alvo. Senão, olha quem falou com ela no chat no
// último minuto (até 16 blocos) ou o jogador mais perto (até 8). Mecânico: não decide nada por ela.
const GAZE_SAFE_ACTIONS = new Set(['state', 'inventory', 'find_blocks', 'players', 'recipes', 'chat', 'stop'])
const GAZE_MS = 400, GAZE_CHAT_MS = 60000
let rpcRunning = [], gazeTimer = null  // comandos mutáveis em execução, por sessão (revisão Codex)
function gazeTarget(b) {
  if (reflexActive() || b.targetDigBlock || b.pathfinder?.isMoving?.()) return null
  // Revisão Codex: só a própria caça pode estar em execução enquanto olha; seguir não olha durante outro comando.
  const busy = rpcRunning.filter(r => r.session === sessionId)
  const type = activeAction?.type
  if (type === 'hunt') return busy.every(r => r.action === 'attack') ? b.entities?.[activeAction.entityId] || null : null
  if (busy.length) return null
  if (type === 'follow') return b.players?.[activeAction.username]?.entity || null
  if (activeAction) return null
  const me = b.entity?.position, own = String(b.username || '').toLowerCase()
  if (!me) return null
  const near = (entity, max) => entity?.position && me.distanceTo(entity.position) <= max
  const talker = [...recentChat].reverse().find(m => m.sessionId === sessionId && String(m.username).toLowerCase() !== own &&
    Date.now() - Date.parse(m.at) <= GAZE_CHAT_MS && near(b.players?.[m.username]?.entity, 16))
  if (talker) return b.players[talker.username].entity
  return Object.values(b.players || {}).map(p => p?.entity).filter(e => e && e !== b.entity && near(e, 8))
    .sort((x, y) => me.distanceTo(x.position) - me.distanceTo(y.position))[0] || null
}
function gaze(b) {
  const target = gazeTarget(b)
  if (!target) return
  const eye = target.position.offset(0, typeof target.height === 'number' ? target.height * 0.9 : 1.6, 0)
  Promise.resolve(b.lookAt(eye)).catch(() => {})
}

function stop() {
  const b = requireBot()
  b.pathfinder.stop()
  if (activeAction) activeAction.stopRequested = true
  setEvent('stop_requested', 'parada cooperativa solicitada')
  return 'Parada cooperativa solicitada; confirme o término pelo estado do pathfinder.'
}

async function dig(args) {
  const b = requireBot()
  const ownSession = sessionId
  const block = b.blockAt(new Vec3(Number(args.x), Number(args.y), Number(args.z)))
  if (!block) throw new Error('não existe bloco nessa posição ou ela ainda não foi carregada')
  // 30/10 (revisão Codex): recolher estação manda o tipo esperado; outro bloco na coordenada não é quebrado.
  const expect = typeof args.expect === 'string' ? args.expect.trim() : ''
  if (expect && block.name !== expect)
    throw new NoEffectError(`em (${block.position.x}, ${block.position.y}, ${block.position.z}) agora há ${block.name}, ` +
      `não ${expect}; nada foi quebrado.`, { esperado: expect, encontrado: block.name }, 'dig_preconditions')
  if (block.name === 'air') return 'Já está vazio.'
  requireHarvest(block.name)
  activeAction = { type: 'dig', block: { name: block.name, position: vecToJSON(block.position) } }
  // 30/10 (pedido humano): bancada/forno quebrados caem como item; recolhe para ela não deixar a estação para trás.
  const station = STATION_BLOCKS.has(block.name)
  const before = station ? inventorySummary() : []
  const count = list => list.filter(i => i.name === block.name).reduce((n, i) => n + i.count, 0)
  try {
    // Revisão Codex: b.dig usa o que está na mão; sem a picareta na mão o forno quebra e não cai. Equipar e quebrar têm
    // prazo; estourado, para de cavar e a falha vira incerteza (pode ter quebrado), nunca sucesso tardio.
    let digTimer, expired = false
    const digging = (async () => {
      if (station && b.tool?.equipForBlock) await b.tool.equipForBlock(block, { requireHarvest: true })
      if (expired) return  // revisão Codex: equipar terminou depois do prazo; não começa a quebrar
      await b.dig(block, args.forceLook === 'ignore' ? 'ignore' : true)
    })()
    const dug = await Promise.race([digging.then(() => true),
      new Promise(resolve => { digTimer = setTimeout(() => resolve(false), DIG_BUDGET_MS) })])
    clearTimeout(digTimer)
    if (!dug) {
      expired = true
      digging.catch(() => {})
      try { b.stopDigging?.() } catch (_) {}
      throw new Error(`quebrar ${block.name} passou de ${DIG_BUDGET_MS / 1000} s; parei de cavar`)
    }
    confirmSession(b, ownSession)
    let recovered = ''
    if (station) {
      for (let i = 0; i < 6 && count(inventorySummary()) <= count(before); i++) await new Promise(r => setTimeout(r, 250))
      const center = block.position.offset(0.5, 0.5, 0.5)
      // Só o item da própria estação (o forno também solta o que tinha dentro).
      const drop = count(inventorySummary()) > count(before) ? null : Object.values(b.entities).find(e => e &&
        e.name === 'item' && e.position && e.position.distanceTo(center) <= 3 && e.getDroppedItem?.()?.name === block.name)
      if (drop) {
        // Revisão Codex: anda até o item com o pathfinder (não com o collectBlock, que continua vivo depois de
        // cancelado); estourado o prazo, setGoal(null) para na hora e nada fica disputando a ação seguinte.
        let timer
        clearPendingStop(b)
        const p = drop.position.floored ? drop.position.floored() : drop.position
        const pickGoal = new goals.GoalNear(p.x, p.y, p.z, 0)
        const walking = b.pathfinder.goto(pickGoal)
        const outcome = await Promise.race([walking.then(() => 'arrived', () => 'failed'),
          new Promise(resolve => { timer = setTimeout(() => resolve('timeout'), PICKUP_BUDGET_MS) })])
        clearTimeout(timer)
        // Revisões Codex: em NoPath o goto da biblioteca rejeita ou até resolve com caminho vazio e o objetivo fica
        // ativo; a caminhada até o item é de uma vez só, então limpa sempre, qualquer que seja o resultado.
        walking.catch(() => {}); clearOwnGoal(b, pickGoal)
        for (let i = 0; i < 6 && count(inventorySummary()) <= count(before); i++) await new Promise(r => setTimeout(r, 250))
        confirmSession(b, ownSession)
      }
      const after = inventorySummary(), got = count(after) - count(before)
      const gained = {}
      for (const i of after) gained[i.name] = (gained[i.name] || 0) + i.count
      for (const i of before) gained[i.name] = (gained[i.name] || 0) - i.count
      const extras = Object.entries(gained).filter(([n, c]) => c > 0 && n !== block.name).map(([n, c]) => `${c} ${n}`).join(', ')
      recovered = (got > 0 ? ` e recolhi ${got} ${block.name} (agora tenho ${count(after)})` :
        `; o item caiu e não entrou no inventário (tenho ${count(after)} ${block.name})`) +
        (extras ? `; também entraram: ${extras}` : '')
    }
    if (bot === b && sessionId === ownSession) activeAction = null
    setEvent('dig', `quebrei ${block.name} em ${block.position.x},${block.position.y},${block.position.z}`)
    return `Quebrei ${block.name}${recovered}.`
  } catch (err) {
    activeAction = null
    throw new Error(`mineração falhou: ${err.message || err}`)
  }
}

async function collect(args) {
  const b = requireBot()
  const ownSession = sessionId
  const name = String(args.name || '').trim().toLowerCase()
  const targetCount = Math.max(1, Math.min(32, Number(args.count || 1)))
  const maxDistance = Math.max(1, Number(args.maxDistance || 64))
  const id = mcData?.blocksByName?.[name]?.id
  if (id == null) throw new Error(`bloco '${name}' não existe em ${b.version}`)
  requireHarvest(name)
  const before = inventorySummary(), from = cell(b.entity?.position)
  let remaining = targetCount, target = null
  // 28/10: o veio de 6 blocos passou de 90 s (prazo do RPC) com 75 s por bloco e o recibo ficou
  // incerto; o orçamento agora é da coleta inteira e o resultado parcial volta medido.
  const deadline = Date.now() + COLLECT_BUDGET_MS
  activeAction = { type: 'collect', block: name, requested: targetCount }
  try {
    while (remaining > 0) {
      // 28/10: cavar minério encostado em lava fazia a lava escorrer sobre ela.
      const found = b.findBlock({ matching: block => block?.type === id && !nextToLava(b, block.position), maxDistance, useExtraInfo: true })
      if (!found && b.findBlock({ matching: id, maxDistance }) && remaining === targetCount) {
        activeAction = null
        return { message: `Os blocos de ${name} ao alcance estão encostados em lava; não coletei para não cair nela.`,
          sem_ganho: true, perigo_lava: true, antes: before, depois: inventorySummary() }
      }
      if (!found) break
      target = found
      let timer
      const collecting = b.collectBlock.collect(found)
      const expired = await Promise.race([
        collecting.then(() => false),
        new Promise(resolve => { timer = setTimeout(() => resolve(true), Math.max(0, deadline - Date.now())) })])
      clearTimeout(timer)
      confirmSession(b, ownSession)
      if (expired) {
        // Para tudo sem esperar indefinidamente; o resultado é o que o inventário mostra.
        try { b.pathfinder.stop(); b.pathfinder.setGoal(null) } catch (_) {}
        // 30/10 (revisões Codex): cancelada, a coleta continua viva na biblioteca e pode terminar de cavar e mandar o
        // pathfinder atrás de um drop, roubando o caminho da ação seguinte. Espera a biblioteca encerrar (75 + 8 s,
        // dentro dos 90 s do RPC) antes de devolver; se não encerrar, o recibo diz isso.
        let endTimer
        const ended = await Promise.race([
          Promise.all([Promise.resolve(b.collectBlock.cancelTask?.()).catch(() => {}), collecting.catch(() => {})]).then(() => true),
          new Promise(resolve => { endTimer = setTimeout(() => resolve(false), COLLECT_CANCEL_WAIT_MS) })])
        clearTimeout(endTimer)
        confirmSession(b, ownSession)
        clearPendingStop(b)  // o stop() do cancelTask com o bot parado deixaria uma parada pendente
        activeAction = null
        setEvent('collect', `coleta de ${name} interrompida por tempo` + (ended ? '' : '; biblioteca ainda encerrando'))
        const expectedDrop = BLOCK_DROPS[name] || name
        const count = list => list.filter(item => item.name === expectedDrop).reduce((n, item) => n + item.count, 0)
        const got = count(inventorySummary()) - count(before)
        return {
          message: `Coleta interrompida após ${COLLECT_BUDGET_MS / 1000} s no total` +
            (got > 0 ? `; +${got} ${expectedDrop} no inventário.` : '; confira o inventário antes/depois.') +
            (ended ? '' : ' A biblioteca ainda não encerrou a coleta; uma caminhada logo em seguida pode ser interrompida.'),
          interrompida: true, biblioteca_encerrada: ended, antes: before, depois: inventorySummary(),
        }
      }
      remaining--
    }
    // Servidor remoto (28/10): o tronco quebrou, mas o item caiu longe ou chegou depois e o
    // recibo dizia "concluída" com o inventário vazio. Espera o item e recolhe drops próximos.
    // 28/10: "+21 itens" eram terra/mudas recolhidas, nenhum oak_log: conta o item esperado.
    const expected = BLOCK_DROPS[name] || name
    const total = list => list.reduce((n, item) => n + item.count, 0)
    const has = list => list.filter(item => item.name === expected).reduce((n, item) => n + item.count, 0)
    for (let i = 0; i < 6 && has(inventorySummary()) <= has(before); i++) await new Promise(r => setTimeout(r, 250))
    if (has(inventorySummary()) <= has(before)) {
      const drops = Object.values(b.entities).filter(e => e && e.name === 'item' && e.position &&
        b.entity.position.distanceTo(e.position) <= 8).slice(0, 4)
      for (const drop of drops) {
        // 30/10 (revisão Codex): os drops ficavam fora do prazo (até 4 × 15 s) e a resposta passava dos 90 s do RPC.
        const left = deadline + 10000 - Date.now()
        if (left <= 0) break
        let timer
        try { await Promise.race([b.collectBlock.collect(drop),
          new Promise(resolve => { timer = setTimeout(resolve, Math.min(15000, left)) })]) } catch (_) {}
        clearTimeout(timer)
      }
      try { b.pathfinder.setGoal(null) } catch (_) {}
      confirmSession(b, ownSession)
    }
    const after = inventorySummary(), gained = has(after) - has(before)
    const others = total(after) - total(before) - gained
    // 28/10: o forno dela entrou no inventário como "3 outros itens" e ela seguiu achando que fundia.
    const counted = list => list.reduce((map, item) => map.set(item.name, (map.get(item.name) || 0) + item.count), new Map())
    const was = counted(before), named = [...counted(after)].filter(([n, c]) => n !== expected && c > (was.get(n) || 0))
      .map(([n, c]) => `${c - (was.get(n) || 0)} ${n}`)
    const extra = others > 0 ? `; também entraram ${others} outro(s) item(ns) caído(s) por perto (${named.join(', ')})` : ''
    activeAction = null
    setEvent('collect', `coleta de ${name} terminou`)
    return {
      message: gained > 0 ? `Coleta concluída: ${targetCount - remaining} bloco(s) de ${name}; +${gained} ${expected} no inventário${extra}.`
        : `Quebrei ${targetCount - remaining} bloco(s) de ${name}, mas nenhum ${expected} entrou no inventário${extra || '; o item pode ter caído fora de alcance'}.`,
      sem_ganho: gained <= 0,
      antes: before,
      depois: after,
    }
  } catch (err) {
    // 28/10: o reflexo (água/monstro) trocou o objetivo no meio da coleta de carvão e o recibo ficou incerto;
    // como na navegação, devolve o medido e não cancela o reflexo em andamento.
    if ((err?.name === 'GoalChanged' || /goal was changed/i.test(String(err?.message))) && lastDanger
        && Date.now() - lastDanger.at < 10000 && bot === b && sessionId === ownSession) {
      activeAction = null
      const expected = BLOCK_DROPS[name] || name
      const has = list => list.filter(item => item.name === expected).reduce((n, item) => n + item.count, 0)
      const after = inventorySummary()
      setEvent('collect', `coleta de ${name} interrompida pelo reflexo (${lastDanger.tipo})`)
      return { message: `Coleta de ${name} interrompida pelo reflexo de sobrevivência (${lastDanger.tipo}: ` +
          `${reflexes.at(-1)?.acao || 'agi para me proteger'}); +${has(after) - has(before)} ${expected} no inventário.`,
        interrompida: true, reflexo: true, antes: before, depois: after }
    }
    if (bot === b && sessionId === ownSession) {
      activeAction = null
      // collectBlock usa o pathfinder, que mantém o objetivo após falhar (movimento tardio real em 27/10).
      try { b.pathfinder.setGoal(null) } catch (_) {}
      const intact = target && b.blockAt(target.position)?.name === name
      if (remaining === targetCount && PATH_FAILURES.includes(err?.name) && intact && from && cell(b.entity?.position) === from
          && JSON.stringify(inventorySummary()) === JSON.stringify(before))
        throw new NoEffectError(`nenhum caminho até ${name} em (${target.position.x}, ${target.position.y}, ${target.position.z}) `+
          'dentro do limite de busca; nada foi quebrado e você não saiu do lugar.',
          {block: name, target: vecToJSON(target.position), reason: err.name}, 'collect_no_path', 'verified', 'not_applied')
      // 30/10: com o inventário cheio o collectBlock tenta guardar num baú e falha com "no defined chest locations";
      // sem sair do lugar nem mudar o inventário, é o fato "inventário cheio", antes de qualquer efeito.
      if (/no defined chest locations/i.test(String(err?.message || err)) && remaining === targetCount && from &&
          cell(b.entity?.position) === from && JSON.stringify(inventorySummary()) === JSON.stringify(before))
        throw new NoEffectError(`inventário cheio (${(b.inventory.items?.() || []).length} pilhas): não há espaço para ` +
          `recolher ${name}; nada foi quebrado. Jogue fora ou use algo antes (minecraft_jogar_item).`,
          {block: name, pilhas: (b.inventory.items?.() || []).length}, 'collect_inventory_full', 'verified', 'not_applied')
      const expected = BLOCK_DROPS[name] || name
      const has = list => list.filter(item => item.name === expected).reduce((n, item) => n + item.count, 0)
      const after = inventorySummary()
      // Bloco-alvo intacto: nada caiu para entrar depois; o efeito (andar, cavar o caminho) já está medido.
      if (PATH_FAILURES.includes(err?.name) && (has(after) > has(before) || intact)) {
        // 28/10: andou, pegou birch_log e só então ficou sem caminho; o erro virava efeito incerto e
        // pausava a tarefa. Com o item esperado já no inventário, o efeito está medido; sem ele, o
        // drop ainda pode entrar depois e o resultado continua incerto.
        setEvent('collect', `coleta de ${name} parou sem caminho`)
        return { message: `Coleta parou sem caminho (${err.name}) depois de começar; +${has(after) - has(before)} ${expected} no inventário.`,
          interrompida: true, sem_caminho: true, antes: before, depois: after }
      }
    }
    throw new Error(`coleta falhou: ${err.message || err}`)
  }
}

// Falhas conferidas sem efeito no mundo: viram retorno para nova decisão, não incerteza.
class NoEffectError extends Error {
  constructor(message, details, code, phase='preflight', effect='not_started') {
    super(message); Object.assign(this,{details,code,phase,effect}) }
}
class CraftPreconditionError extends NoEffectError {
  constructor(message, details) { super(message, details, 'craft_preconditions') }
}

async function craft(args) {
  const b = requireBot()
  const ownSession = sessionId
  const name = String(args.name || '').trim().toLowerCase()
  const count = Math.max(1, Math.min(64, Number(args.count || 1)))
  const id = mcData?.itemsByName?.[name]?.id
  // Recusado antes de qualquer efeito: o ID errado volta como pré-condição para nova decisão.
  if (id == null) throw new CraftPreconditionError(`item '${name}' não existe em ${b.version}; use o ID exato de uma receita consultada.`,
    {item:name,unknown_item:true,inventory:inventorySummary(),recipes:[]})
  const tableId=mcData?.blocksByName?.crafting_table?.id
  const table=tableId==null?null:b.findBlock({matching:tableId,maxDistance:4})
  const recipes = b.recipesFor(id, null, count, table)
  if (!recipes.length) throw new CraftPreconditionError(
    `Não há materiais/bancada para fabricar ${name} com o inventário atual. Ingredientes não são fabricados automaticamente.`,
    {item:name,inventory:inventorySummary(),recipes:globalRecipes(name)})
  const before=inventorySummary()
  const operations=Math.ceil(count/Math.max(1,recipes[0].result?.count||1))
  await b.craft(recipes[0], operations, recipes[0].requiresTable?table:null)
  confirmSession(b, ownSession)
  setEvent('craft', `receita de ${name} executada; conferir inventário`)
  return {item:name,requested:count,operations,before,after:inventorySummary()}
}

function recipes(args) { return globalRecipes(String(args.name||'').trim().toLowerCase()) }
function globalRecipes(name) {
  const b=requireBot()
  const id=mcData?.itemsByName?.[name]?.id
  if(id==null)throw new Error('Item desconhecido: '+name)
  return b.recipesAll(id,null,true).slice(0,12).map(recipe=>({requiresTable:recipe.requiresTable,
    result:recipe.result,ingredients:(recipe.delta||[]).filter(i=>i.count<0).map(i=>({
      name:mcData.items?.[i.id]?.name||String(i.id),count:-i.count}))}))
}

function boundedCount(value,fallback=1) {
  const n=Number(value??fallback)
  if(!Number.isInteger(n)||n<1||n>64)throw new Error('Quantidade deve ser inteira de1 a64.')
  return n
}

// 29/10: com dois fornos ao alcance, retirar abria o mais próximo (vazio, de um ensaio) e não o
// dela com 8 salmões. Retirar/consultar prefere o forno com carga própria; carregar, um sem carga.
function furnaceBlock(b,id,action) {
  const nearest=b.findBlock({matching:id,maxDistance:4})
  if(!nearest||typeof b.findBlocks!=='function'||typeof b.blockAt!=='function')return nearest
  const key=bl=>furnacePrefix(b)+[bl.position.x,bl.position.y,bl.position.z].join(',')
  const all=(b.findBlocks({matching:id,maxDistance:4,count:8})||[]).map(p=>b.blockAt(p)).filter(bl=>bl&&bl.position)
  const fits=bl=>action==='put'?!furnaceRuns.has(key(bl)):furnaceRuns.has(key(bl))
  return fits(nearest)?nearest:(all.find(fits)||nearest)
}

async function furnaceAction(action,args) {
  const b=requireBot(),ownSession=sessionId
  const id=mcData?.blocksByName?.furnace?.id
  const block=id==null?null:furnaceBlock(b,id,action)
  if(!block)throw new NoEffectError('Nenhum forno ao alcance (4 blocos); coloque ou aproxime-se de um forno.',
    {inventory:inventorySummary()},'furnace_preconditions')
  const key=furnacePrefix(b)+[block.position.x,block.position.y,block.position.z].join(',')
  const window=await b.openFurnace(block)
  try {
    confirmSession(b,ownSession)
    const summarize=item=>item?{name:item.name,count:item.count}:null
    const snapshot=()=>({position:vecToJSON(block.position),input:summarize(window.inputItem()),
      fuel:summarize(window.fuelItem()),output:summarize(window.outputItem()),progress:window.progress??null,
      owned_run:furnaceRuns.get(key)||null})
    if(action==='state')return snapshot()
    if(action==='put') {
      // 28/10: a recusa vinha sem código e o recibo ficava incerto, pausando a tarefa; nada foi alterado.
      if(window.inputItem()||window.outputItem()||furnaceRuns.has(key))throw new NoEffectError(
        'Forno ocupado por minério, produto ou carga própria ainda registrada; confira antes de carregar de novo. Não alterei os itens existentes.',
        {forno:snapshot(),inventory:inventorySummary()},'furnace_preconditions')
      const input=String(args.input||''),fuel=String(args.fuel||'coal')
      const outputs={iron_ore:'iron_ingot',gold_ore:'gold_ingot',sand:'glass',cobblestone:'stone',
        beef:'cooked_beef',porkchop:'cooked_porkchop',chicken:'cooked_chicken',mutton:'cooked_mutton',
        rabbit:'cooked_rabbit',cod:'cooked_cod',salmon:'cooked_salmon'}
      if(!outputs[input])throw new NoEffectError('Esta ferramenta aceita minérios (iron_ore, gold_ore), sand, cobblestone ou carne crua.',
        {inventory:inventorySummary()},'furnace_preconditions')
      if(!['coal','charcoal'].includes(fuel))throw new Error('Use coal ou charcoal como combustível.')
      const count=boundedCount(args.count),fuelCount=boundedCount(args.fuelCount)
      const storedFuel=window.fuelItem()
      if(storedFuel&&(storedFuel.name!==fuel||storedFuel.count+fuelCount>64))throw new NoEffectError(
        'O combustível solicitado não combina com o existente ou excede o espaço do slot; nada foi depositado.',
        {forno:snapshot(),inventory:inventorySummary()},'furnace_preconditions')
      const inputItem=b.inventory.items().find(i=>i.name===input),fuelItem=b.inventory.items().find(i=>i.name===fuel)
      if(!inputItem||inputItem.count<count||!fuelItem||fuelItem.count<fuelCount)throw new NoEffectError(
        'Materiais insuficientes no inventário para a quantidade solicitada; nada foi depositado.',
        {forno:snapshot(),inventory:inventorySummary(),requested:{input,count,fuel,fuelCount}},'furnace_preconditions')
      const run={input,expectedOutput:outputs[input],remaining:count,count,fuel,fuelCount,phase:'depositing',
        position:vecToJSON(block.position),startedAt:new Date().toISOString(),session:ownSession}
      furnaceRuns.set(key,run);saveFurnaceRuns()
      await window.putInput(inputItem.type,null,count);confirmSession(b,ownSession);run.phase='input_deposited';saveFurnaceRuns()
      await window.putFuel(fuelItem.type,null,fuelCount);confirmSession(b,ownSession);run.phase='processing';saveFurnaceRuns()
      setEvent('furnace',`iniciei processamento de ${count} ${input}; ainda não é produto concluído`)
      return snapshot()
    }
    if(action==='take') {
      const run=furnaceRuns.get(key),output=window.outputItem()
      // 29/10: recusas antes de tirar qualquer item; sem código viravam incerteza e pausavam a tarefa.
      if(!run)throw new NoEffectError('Não há processamento próprio registrado neste forno; nada retirado.',
        {forno:snapshot()},'furnace_preconditions')
      if(!output)return snapshot()
      if(output.name!==run.expectedOutput||output.count>run.remaining)throw new NoEffectError(
        'Conteúdo do forno divergiu; conferir antes de retirar. Nada retirado.',{forno:snapshot()},'furnace_preconditions')
      const before=inventorySummary(),count=output.count
      await window.takeOutput();confirmSession(b,ownSession)
      run.remaining-=count
      if(!run.remaining)furnaceRuns.delete(key)
      saveFurnaceRuns()
      setEvent('furnace',`retirei ${count} ${output.name}`)
      return {taken:{name:output.name,count},before,after:inventorySummary(),furnace:snapshot()}
    }
    throw new Error('Ação do forno inválida.')
  } finally {window.close()}
}

async function equip(args) {
  const b = requireBot()
  const ownSession = sessionId
  const name = String(args.name || '').trim().toLowerCase()
  const item = b.inventory.items().find(i => i.name === name)
  if (!item) throw new NoEffectError(`não tenho '${name}' no inventário`,
    {item:name,inventory:inventorySummary()},'equip_preconditions')
  const destination = args.destination || 'hand'
  await b.equip(item, destination)
  confirmSession(b, ownSession)
  setEvent('equip', `${name} → ${destination}`)
  return `Equipei ${name} em ${destination}.`
}

async function attack(args) {
  const b = requireBot()
  const maxDistance = Math.max(1, Number(args.maxDistance || 16))
  let entity = null
  if (args.entityId != null) entity = b.entities[Number(args.entityId)]
  const target = String(args.target || '').trim().toLowerCase()
  if (!entity && target) {
    entity = Object.values(b.entities).find(e => e && e.position && e !== b.entity &&
      (String(e.name || '').toLowerCase() === target || String(e.displayName || '').toLowerCase() === target ||
       String(e.username || '').toLowerCase() === target) &&
      b.entity.position.distanceTo(e.position) <= maxDistance)
  }
  // 28/10: a aranha já tinha morrido/sumido (o reflexo lutou com ela) e a recusa sem código virou incerteza.
  if (!entity) throw new NoEffectError('Alvo não encontrado na distância permitida (morreu, sumiu ou se afastou); nenhum golpe foi dado.',
    { alvo: target || null, entidade_id: args.entityId ?? null, max_distance: maxDistance }, 'attack_preconditions')
  if (entity.type === 'player' || entity.username || NOT_A_TARGET.has(entity.name))
    throw new NoEffectError('Não ataco jogadores nem aldeões; escolha um mob.', { alvo: entity.username || entity.name }, 'attack_preconditions')
  const label = entity.username || entity.name || entity.displayName || entity.id
  if (!args.hunt) {
    attackedAt.set(entity.id, { name: entity.name, at: Date.now() })
    b.attack(entity)
    setEvent('attack', `ataquei ${label}`)
    return `Ataque iniciado contra ${label}.`
  }
  // Perseguir e golpear até morrer ou acabar o prazo; a morte vem do evento do servidor.
  // 29/10 (pedido humano): ela escolhe quantos caçar; um alvo do mesmo tipo atrás do outro,
  // 30 s por animal, até a quantidade, sem alvos por perto ou com vida baixa.
  const want = Math.max(1, Math.min(8, Number(args.count || 1)))
  const ownSession = sessionId, deadline = Date.now() + HUNT_BUDGET_MS * want
  const beforeDrops = inventorySummary(), slain = []
  let hits = 0, current = entity, lastMissed = null
  activeAction = { type: 'hunt', target: entity.name, entityId: entity.id, count: want }
  try {
    while (current && slain.length < want && Date.now() < deadline) {
      const until = Math.min(deadline, Date.now() + HUNT_BUDGET_MS)
      clearPendingStop(b)
      b.pathfinder.setGoal(new goals.GoalFollow(current, 1.5), true)
      while (Date.now() < until && b.entities[current.id] && !kills.some(k => k.entityId === current.id)) {
        if (b.entity.position.distanceTo(current.position) <= 3.2) {
          attackedAt.set(current.id, { name: current.name, at: Date.now() })
          b.attack(current); hits++
        }
        await ticks(2)
      }
      await ticks(1)  // o evento de morte pode chegar logo depois do último golpe
      try { b.pathfinder.setGoal(null) } catch (_) {}
      confirmSession(b, ownSession)
      if (!kills.some(k => k.entityId === current.id)) { lastMissed = current; break }  // não troca de alvo sem matar
      slain.push({ alvo: current.name, entidade_id: current.id })
      const drops = Object.values(b.entities).filter(e => e && e.name === 'item' && e.position &&
        b.entity.position.distanceTo(e.position) <= 6).slice(0, 4)
      for (const drop of drops) {
        let timer
        try { await Promise.race([b.collectBlock.collect(drop), new Promise(resolve => { timer = setTimeout(resolve, 8000) })]) } catch (_) {}
        clearTimeout(timer)
      }
      try { b.pathfinder.setGoal(null) } catch (_) {}
      if (slain.length >= want || (typeof b.health === 'number' && b.health <= 10)) break
      current = Object.values(b.entities).filter(e => e && e !== b.entity && e.position && e.name === entity.name &&
        !e.username && e.type !== 'player' && !kills.some(k => k.entityId === e.id) &&
        b.entity.position.distanceTo(e.position) <= maxDistance)
        .sort((x, y) => b.entity.position.distanceTo(x.position) - b.entity.position.distanceTo(y.position))[0] || null
      if (current && activeAction?.type === 'hunt') activeAction.entityId = current.id  // o olhar segue a presa nova
    }
  } finally {
    try { b.pathfinder.setGoal(null) } catch (_) {}
    activeAction = null
  }
  confirmSession(b, ownSession)
  let swam = ''
  if (b.entity.isInWater) { try { swam = await leaveWater(b) } catch (_) {} }
  const was = new Map(beforeDrops.map(i => [i.name, i.count]))
  const picked = inventorySummary().filter(i => i.count > (was.get(i.name) || 0)).map(i => `${i.count - (was.get(i.name) || 0)} ${i.name}`)
  const killed = slain.length > 0
  setEvent('attack', killed ? `${slain.length}/${want} ${entity.name} morreram` : `perseguição de ${label} terminou sem morte`)
  const why = slain.length >= want ? '' : lastMissed ? ` O ${slain.length + 1}º não morreu no prazo de ${HUNT_BUDGET_MS / 1000} s.`
    : (typeof b.health === 'number' && b.health <= 10) ? ' Parei com a vida baixa.' : killed ? ` Não havia outro ${entity.name} a até ${maxDistance} blocos.` : ''
  return { alvo: entity.name, entidade_id: entity.id, golpes: hits, morto: killed, mortos: slain.length, pedidos: want,
    abatidos: slain, recolhido: picked,
    message: (killed ? `${slain.length}/${want} ${entity.name} morreram depois de ${hits} golpe(s) seus` +
        (picked.length ? `; recolhi ${picked.join(', ')}.` : '; nada caiu perto ou não recolhi.')
      : (hits ? `Golpeei ${entity.name} ${hits} vez(es), mas ele não morreu no prazo de ${HUNT_BUDGET_MS / 1000} s.`
              : `Não alcancei ${entity.name} no prazo de ${HUNT_BUDGET_MS / 1000} s.` + unreachable(b, lastMissed || entity))) +
      (killed ? why : '') + (swam ? ` Depois ${swam}.` : ''),
    sessionId: ownSession }
}

function faceVector(face) {
  switch (String(face || 'up').toLowerCase()) {
    case 'down': return new Vec3(0, -1, 0)
    case 'north': return new Vec3(0, 0, -1)
    case 'south': return new Vec3(0, 0, 1)
    case 'west': return new Vec3(-1, 0, 0)
    case 'east': return new Vec3(1, 0, 0)
    default: return new Vec3(0, 1, 0)
  }
}

const isSolid=block=>!!block&&(block.boundingBox?block.boundingBox==='block':!/^(air|cave_air|void_air)$/.test(block.name))

// Sem coordenadas: chão sólido ao lado com espaço vazio em cima, fora do próprio corpo.
function nearbyGround(b) {
  const me=b.entity?.position
  if (!me) return null
  const x=Math.floor(me.x),y=Math.floor(me.y),z=Math.floor(me.z)
  for (const [dx,dz] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1],[2,0],[-2,0],[0,2],[0,-2]]) {
    const ground=b.blockAt(new Vec3(x+dx,y-1,z+dz)),spot=b.blockAt(new Vec3(x+dx,y,z+dz))
    if (isSolid(ground) && spot && !isSolid(spot)) return {x:x+dx,y:y-1,z:z+dz,face:'up'}
  }
  return null
}

async function placeBlock(args) {
  const b = requireBot()
  const ownSession = sessionId
  if (args.x==null||args.y==null||args.z==null) {
    const spot=nearbyGround(b)
    if (!spot) throw new NoEffectError('não há chão sólido livre ao meu lado; ande um pouco ou informe x,y,z',
      {held:b.heldItem?.name||null},'place_preconditions')
    args={...args,...spot}
  }
  const ref = b.blockAt(new Vec3(Number(args.x), Number(args.y), Number(args.z)))
  if (!ref) throw new NoEffectError('bloco de referência não encontrado',{held:b.heldItem?.name||null},'place_preconditions')
  // 28/10: o pathfinder deixa terra (andaime) na mão e ela se afastava durante a caça; o servidor recusava
  // a 11 blocos com terra na mão. Distância conferida antes e item pedido equipado antes de colocar.
  const reach=b.entity?.position?.distanceTo?.(new Vec3(ref.position.x+0.5,ref.position.y+0.5,ref.position.z+0.5))
  if (typeof reach==='number' && reach>5)
    throw new NoEffectError(`a referência (${ref.position.x}, ${ref.position.y}, ${ref.position.z}) está a ${reach.toFixed(1)} blocos; `+
      'aproxime-se (até ~4 blocos) ou chame sem x,y,z para usar o chão livre ao seu lado.',{reference:vecToJSON(ref.position),distance:Number(reach.toFixed(1))},'place_preconditions')
  if (args.name && b.heldItem?.name!==String(args.name)) {
    const wanted=b.inventory.items().find(i=>i.name===String(args.name))
    if (!wanted) throw new NoEffectError(`não tenho ${args.name} no inventário para colocar.`,{inventory:inventorySummary()},'place_preconditions')
    await b.equip(wanted,'hand')
  }
  if (!b.heldItem) throw new NoEffectError('não estou segurando nenhum bloco/item utilizável; equipe o bloco antes',
    {held:null,inventory:inventorySummary()},'place_preconditions')
  if (mcData?.itemsByName?.[b.heldItem.name] && mcData?.blocksByName && !mcData.blocksByName[b.heldItem.name])
    throw new NoEffectError(`estou segurando ${b.heldItem.name}, que não é um bloco; equipe o bloco que quer colocar antes`,
      {held:b.heldItem.name,inventory:inventorySummary()},'place_preconditions')
  const name=b.heldItem.name,face=faceVector(args.face)
  const target=new Vec3(ref.position.x+face.x,ref.position.y+face.y,ref.position.z+face.z)
  // Regras do jogo explicadas antes de tentar: apoio sólido e alvo fora do próprio corpo.
  if (!isSolid(ref)) throw new NoEffectError(`a referência (${ref.position.x}, ${ref.position.y}, ${ref.position.z}) é ${ref.name}: `+
    'use um bloco sólido existente (por exemplo o chão em y-1) e a face voltada para o espaço vazio. Ou chame sem x,y,z para usar o chão livre ao seu lado.',
    {held:name,reference_block:ref.name,reference:vecToJSON(ref.position)},'place_preconditions')
  const there=b.blockAt(target)
  if (isSolid(there))
    throw new NoEffectError(`o espaço vizinho (${target.x}, ${target.y}, ${target.z}) já tem ${there.name}; `+
      'escolha a face cujo vizinho esteja vazio (sobre o chão, normalmente up). Ou chame sem x,y,z para usar o chão livre ao seu lado.',
      {held:name,target:vecToJSON(target),target_block:there.name},'place_preconditions')
  const me=b.entity?.position
  if (me && target.x===Math.floor(me.x) && target.z===Math.floor(me.z) &&
      (target.y===Math.floor(me.y) || target.y===Math.floor(me.y)+1))
    throw new NoEffectError(`o alvo (${target.x}, ${target.y}, ${target.z}) é onde você está; `+
      'escolha um espaço vazio ao lado ou afaste-se antes. Ou chame sem x,y,z para usar o chão livre ao seu lado.',{held:name,target:vecToJSON(target),position:vecToJSON(me)},'place_preconditions')
  const previousName=b.blockAt(target)?.name,before=inventorySummary()
  // Depois do envio, ausência de atualização local não prova recusa definitiva.
  // Timeout/ACK perdido pode anteceder o efeito do servidor; preservar incerteza.
  try { await b.placeBlock(ref, face) } catch (err) {
    // 30/10: a 1 bloco do ponto de nascimento o servidor recusava sempre ("still air") e ela repetia no mesmo
    // lugar. O erro continua incerto; só ganha o fato da distância ao spawn, que servidores costumam proteger.
    const sp = b.spawnPoint, me = b.entity?.position, text = String(err?.message || err)
    const d = sp && me ? Math.round(Math.hypot(me.x - sp.x, me.z - sp.z)) : null
    if (/refused/i.test(text) && d !== null && d <= 16)
      throw new Error(`${text} (você está a ${d} blocos do ponto de nascimento do mundo em (${Math.floor(sp.x)},${Math.floor(sp.y)},${Math.floor(sp.z)}); servidores costumam proteger o spawn contra colocar e quebrar blocos)`)
    throw err
  }
  confirmSession(b, ownSession)
  const observed=b.blockAt(target)
  setEvent('place', `coloquei bloco em referência ${ref.position.x},${ref.position.y},${ref.position.z}`)
  return {placed:{name:observed?.name||null,item:name,position:vecToJSON(target),sessionId:ownSession,
    dimension:b.game?.dimension||null,
    verified:!!(previousName&&observed&&previousName!==observed.name&&observed.name===name)},
    before,after:inventorySummary()}
}

// 30/10 (pedido humano): presa 18 blocos abaixo, dentro da rocha, e ela sem picareta tentou 3 vezes; o recibo diz onde o
// alvo estava, quanto acima/abaixo e, sem picareta, que o caminho pode exigir cavar pedra. Só fatos.
function unreachable(b, target) {
  if (!target?.position || !b.entity?.position) return ''
  const p = vecToJSON(target.position.floored()), dy = Math.round(target.position.y - b.entity.position.y)
  const pick = inventorySummary().some(i => /_pickaxe$/.test(i.name)) || /_pickaxe$/.test(b.heldItem?.name || '')
  return ` Ele estava em (${p.x}, ${p.y}, ${p.z})` + (Math.abs(dy) >= 4 ? `, ${Math.abs(dy)} blocos ${dy < 0 ? 'abaixo' : 'acima'} de você` : '') +
    (pick ? '.' : '; você está sem picareta, e o caminho pode exigir cavar pedra.')
}

// 30/10 (pedido humano): sem alvo à vista, andar numa direção até encontrar. Para assim que algo procurado aparece a até
// 24 blocos; prazo de 45 s (o cliente espera 60); o objetivo de caminhada é limpo sempre no fim.
const EXPLORE_DIRS = { norte: [0, -1], sul: [0, 1], leste: [1, 0], oeste: [-1, 0] }
const EXPLORE_STEPS = 180  // × 250 ms = 45 s
async function explore(args = {}) {
  const b = requireBot()
  const ownSession = sessionId
  const dirName = String(args.direction || '').trim().toLowerCase(), dir = EXPLORE_DIRS[dirName]
  const look = new Set((Array.isArray(args.lookFor) ? args.lookFor : [args.lookFor]).filter(x => typeof x === 'string' && x.trim()).map(x => x.trim()))
  if (!dir || !look.size) throw new NoEffectError('explorar pede direção (norte, sul, leste, oeste) e o que procurar; nada foi feito.',
    { direction: dirName, lookFor: [...look] }, 'explore_preconditions')
  const blocks = Math.max(8, Math.min(64, Math.floor(Number(args.blocks || 40))))
  const seen = () => Object.values(b.entities).filter(e => e && e !== b.entity && e.position && look.has(e.name) &&
    b.entity.position.distanceTo(e.position) <= 24).sort((x, y) => b.entity.position.distanceTo(x.position) - b.entity.position.distanceTo(y.position))[0]
  const where = e => { const p = vecToJSON(e.position.floored()); return `(${p.x}, ${p.y}, ${p.z})` }
  const already = seen()
  if (already) return `Já há ${already.name} a ${b.entity.position.distanceTo(already.position).toFixed(1)} blocos em ${where(already)}; não precisei explorar.`
  const start = { x: b.entity.position.x, z: b.entity.position.z }
  const tx = Math.floor(start.x + dir[0] * blocks), tz = Math.floor(start.z + dir[1] * blocks)
  clearPendingStop(b)
  activeAction = { type: 'goto', target: { x: tx, z: tz }, exploring: [...look] }
  let state = 'walking', found = null
  const goal = new goals.GoalNearXZ(tx, tz, 2)
  const walking = b.pathfinder.goto(goal).then(() => { state = 'arrived' }, () => { state = 'failed' })
  try {
    for (let i = 0; i < EXPLORE_STEPS && state === 'walking'; i++) {
      await new Promise(r => setTimeout(r, 250))
      confirmSession(b, ownSession)
      if ((found = seen())) break
    }
  } finally {
    // Revisão Codex: só limpa o próprio objetivo; a fuga do reflexo que o substituiu continua.
    walking.catch(() => {}); clearOwnGoal(b, goal)
    if (bot === b && sessionId === ownSession) activeAction = null
  }
  found = found || seen()
  const fled = lastDanger && Date.now() - lastDanger.at < 10000 && b.pathfinder.goal && b.pathfinder.goal !== goal
  const here = vecToJSON(b.entity.position.floored()), moved = Math.hypot(b.entity.position.x - start.x, b.entity.position.z - start.z)
  setEvent('explore', found ? `encontrei ${found.name}` : `explorei ${Math.round(moved)} blocos para o ${dirName}`)
  if (found) return `Encontrei ${found.name} a ${b.entity.position.distanceTo(found.position).toFixed(1)} blocos em ${where(found)} ` +
    `depois de andar ${Math.round(moved)} blocos para o ${dirName}; estou em (${here.x}, ${here.y}, ${here.z}).`
  return `Andei ${Math.round(moved)} blocos para o ${dirName} até (${here.x}, ${here.y}, ${here.z}) e não vi ${[...look].join(' nem ')}` +
    (fled ? `; o reflexo de sobrevivência interrompeu (${lastDanger.tipo}).` : moved < 1.5 ? '; fiquei presa: o caminho parece bloqueado.' :
      state === 'arrived' ? '.' : '; parei pelo prazo ou sem caminho.')
}

// 30/10 (pedido humano): jogar item no chão ou entregar a um jogador ("me dá um pouco de pão"). Anda até perto do
// jogador com prazo, olha para ele, joga e confere no inventário; o que dizer ou se dar continua sendo decisão dela.
const TOSS_WALK_BUDGET_MS = 20000
async function tossItem(args = {}) {
  const b = requireBot()
  const ownSession = sessionId
  const name = String(args.name || '').trim().toLowerCase()
  const want = Math.max(1, Math.min(64, Math.floor(Number(args.count || 1))))
  const have = () => inventorySummary().filter(i => i.name === name).reduce((n, i) => n + i.count, 0)
  const before = have()
  const id = mcData?.itemsByName?.[name]?.id
  if (id == null || before <= 0)
    throw new NoEffectError(`não tenho ${name || 'esse item'} no inventário; nada foi jogado.`, { item: name, tenho: before }, 'toss_preconditions')
  const target = typeof args.toPlayer === 'string' ? args.toPlayer.trim() : ''
  const player = target ? b.players?.[target]?.entity : null
  if (target && !player)
    throw new NoEffectError(`não vejo o jogador '${target}' por perto; nada foi jogado.`, { para: target }, 'toss_preconditions')
  if (player && b.entity.position.distanceTo(player.position) > 3) {
    clearPendingStop(b)
    activeAction = { type: 'toss', item: name, to: target }
    let timer
    const tossGoal = new goals.GoalNear(player.position.x, player.position.y, player.position.z, 2)
    const walking = b.pathfinder.goto(tossGoal)
    const outcome = await Promise.race([walking.then(() => 'arrived', () => 'failed'),
      new Promise(resolve => { timer = setTimeout(() => resolve('timeout'), TOSS_WALK_BUDGET_MS) })])
    clearTimeout(timer)
    walking.catch(() => {}); clearOwnGoal(b, tossGoal)  // de uma vez só: só o próprio objetivo (ver clearOwnGoal)
    confirmSession(b, ownSession)
    activeAction = null
    const far = b.entity.position.distanceTo(player.position)
    // Andou (efeito real), mas não chegou: o recibo diz isso e nada foi jogado.
    if (far > 4) return `Andei rumo a ${target}, mas fiquei a ${far.toFixed(1)} blocos; não joguei ${name} (tenho ${before}).`
  }
  if (player) {
    await b.lookAt(player.position.offset(0, 1.6, 0))
    confirmSession(b, ownSession)
    // Revisão Codex: depois dos await o jogador pode ter saído ou trocado; só joga para a mesma entidade, perto.
    const still = b.players?.[target]?.entity
    if (still !== player || b.entity.position.distanceTo(still.position) > 4)
      return `${target} saiu de perto antes da entrega; não joguei ${name} (tenho ${before}).`
  }
  await b.toss(id, null, Math.min(want, before))
  confirmSession(b, ownSession)
  const gone = before - have()
  if (gone <= 0) return `Tentei jogar ${name}` + (player ? ` para ${target}` : '') + `, mas nada saiu do inventário (tenho ${have()}).`
  setEvent('toss', `joguei ${gone} ${name}` + (player ? ` para ${target}` : ''))
  return `Joguei ${gone} ${name}` + (player ? ` para ${target}, a ${b.entity.position.distanceTo(player.position).toFixed(1)} blocos` : ' no chão') +
    (gone < Math.min(want, before) ? ` (pedi ${Math.min(want, before)})` : '') + `; tenho agora ${have()}.`
}

async function useItem(args = {}) {
  const b = requireBot()
  const ownSession = sessionId
  // 28/10: fome 3/20 e vida 7 sem opção de comer; com nome de comida, equipa e come, medindo a fome.
  if (args.name) {
    const food = b.inventory.items().find(i => i.name === String(args.name))
    if (!food) throw new NoEffectError(`não tenho ${args.name} no inventário.`, { inventory: inventorySummary() }, 'use_preconditions')
    if (!mcData?.foodsByName?.[food.name]) throw new NoEffectError(`${food.name} não é comida.`, { item: food.name }, 'use_preconditions')
    if (b.food >= 20) throw new NoEffectError('estou sem fome (20/20); não dá para comer agora.', { food: b.food }, 'use_preconditions')
    const before = b.food
    await b.equip(food, 'hand')
    await b.consume()
    confirmSession(b, ownSession)
    setEvent('use_item', `comi ${food.name}`)
    return `Comi ${food.name}: fome ${before} → ${b.food}/20; vida ${Number(b.health.toFixed(1))}/20.`
  }
  if (!b.heldItem) throw new NoEffectError('não estou segurando nenhum item; equipe um item antes. '+
    'Fabricar não precisa abrir a bancada: minecraft_craft já usa a bancada próxima.',{held:null},'use_preconditions')
  await b.activateItem()
  confirmSession(b, ownSession)
  setEvent('use_item', `ativei ${b.heldItem.name}`)
  return `Ativei ${b.heldItem.name}.`
}

async function follow(args) {
  const b = requireBot()
  const username = String(args.username || '')
  const player = b.players[username]
  if (!player?.entity) throw new Error(`não vejo o jogador '${username}' no ambiente atual`)
  const distance = Number(args.distance ?? 2)
  clearPendingStop(b)  // antes de registrar a ação (ver gotoPoint)
  activeAction = { type: 'follow', username, distance }
  b.pathfinder.setGoal(new goals.GoalFollow(player.entity, distance), true)
  setEvent('follow', `seguindo ${username}`)
  return `Comecei a seguir ${username} a ${distance} bloco(s).`
}

async function dispatch(action, args) {
  const started = Date.now()
  diag('action.start', { action, args, sessionId })
  const running = GAZE_SAFE_ACTIONS.has(action) ? null : { action, session: sessionId }
  if (running) rpcRunning.push(running)
  try {
    if (running && action !== 'connect' && action !== 'disconnect') {
      // Revisão Codex: durante outro reflexo (subindo da água, comendo, fugindo) a ação não começa — trocar objetivo
      // ou movimentos soltaria os controles dele. Recusa conferida, sem efeito: ela decide de novo em seguida.
      if (reflexActive()) throw new NoEffectError(`um reflexo de sobrevivência está em andamento (${lastDanger?.tipo || 'perigo'}); ` +
        `'${action}' não começou e nada mudou no mundo. Decida de novo em seguida.`,
        { action, reflexo: lastDanger?.tipo || null }, 'reflex_busy')
      restoreDigging()  // a ação seguinte não herda a fuga sem cavar
    }
    let value
    switch (action) {
      case 'connect': value = await connect(args); break
      case 'disconnect': value = await disconnect(); break
      case 'state': value = Array.isArray(args.perception)&&bot?{...state(),percepcao:perception(args.perception)}:state(); break
      case 'inventory': value = inventory(); break
      case 'chat': requireBot().chat(String(args.text || '')); value = 'Mensagem enviada.'; break
      case 'find_blocks': value = findBlocks(args); break
      case 'goto': value = await gotoPoint(args); break
      case 'stop': value = stop(); break
      case 'dig': value = await dig(args); break
      case 'collect': value = await collect(args); break
      case 'craft': value = await craft(args); break
      case 'recipes': value = recipes(args); break
      case 'furnace_state': value = await furnaceAction('state',args); break
      case 'furnace_put': value = await furnaceAction('put',args); break
      case 'furnace_take': value = await furnaceAction('take',args); break
      case 'equip': value = await equip(args); break
      case 'attack': value = await attack(args); break
      case 'place_block': value = await placeBlock(args); break
      case 'use_item': value = await useItem(args); break
      case 'toss': value = await tossItem(args); break
      case 'explore': value = await explore(args); break
      case 'follow': value = await follow(args); break
      default: throw new Error(`ação Minecraft desconhecida: ${action}`)
    }
    diag('action.end', { action, ok: true, elapsed_ms: Date.now() - started, result: value })
    return value
  } catch (err) {
    diag('action.end', { action, ok: false, elapsed_ms: Date.now() - started, error: String(err?.stack || err) })
    throw err
  } finally {
    if (running) rpcRunning = rpcRunning.filter(r => r !== running)
  }
}

function send(res, payload, status = 200) {
  const body = JSON.stringify(payload)
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
  })
  res.end(body)
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    return send(res, { ok: true, service: 'hoshino-minecraft-bridge', protocol: BRIDGE_PROTOCOL, pid: process.pid, state: state() })
  }
  if (req.method !== 'POST' || req.url !== '/rpc') {
    return send(res, { ok: false, erro: 'rota inexistente' }, 404)
  }
  let raw = ''
  req.on('data', chunk => { raw += chunk })
  req.on('end', async () => {
    let payload = {}
    try {
      payload = JSON.parse(raw || '{}')
      const requestId = payload.request_id || `rpc-${Date.now()}-${Math.random().toString(16).slice(2,8)}`
      const context = { request_id: requestId, parent_id: payload.parent_id || null,
        turn_id: payload.turn_id || null, entity_id: payload.entity_id || process.env.HOSHINO_ENTIDADE || 'hoshino',
        session_id: sessionId }
      if (payload.entity_id && payload.entity_id !== (process.env.HOSHINO_ENTIDADE || 'hoshino')) throw new Error('entidade não pertence a esta ponte')
      if (payload.session_id && payload.action !== 'connect' && payload.session_id !== sessionId) throw new Error('sessão esperada não está ativa')
      diag('http.rpc.start', { ...context, action: payload.action, body_bytes: Buffer.byteLength(raw || '', 'utf8') })
      const result = await rpcContext.run(context, () => dispatch(payload.action, payload.args || {}))
      if (payload.action !== 'connect' && context.session_id !== sessionId) throw new Error('sessão mudou durante operação; resultado incerto')
      const receipt = { ...context, session_id: sessionId }
      diag('http.rpc.end', { ...receipt, action: payload.action, ok: true, result, heap_mb: heapMb() })
      send(res, { ok: true, resultado: result, ...receipt })
    } catch (err) {
      const errorText = String(err?.stack || err)
      const requestId = payload.request_id || null
      const context = { request_id: requestId, parent_id: payload.parent_id || null,
        turn_id: payload.turn_id || null, entity_id: payload.entity_id || null, session_id: sessionId }
      diag('http.rpc.end', { ...context, action: payload.action || null, ok: false, error: errorText })
      const preflight=err instanceof NoEffectError
      send(res, { ok: false, erro: errorText, ...context,
        ...(preflight?{phase:err.phase,effect_state:err.effect,code:err.code,details:err.details}:{}) }, preflight?200:400)
    }
  })
})

server.listen(PORT, HOST, () => {
  console.log(`[minecraft] ponte ouvindo em http://${HOST}:${PORT}`)
  console.log(`[minecraft] versão padrão: ${DEFAULT_VERSION}`)
  diag('bridge.start', { host: HOST, port: PORT, default_version: DEFAULT_VERSION })
})

process.on('uncaughtException', err => { diag('process.uncaughtException', { error: String(err?.stack || err) }) })
process.on('unhandledRejection', err => { diag('process.unhandledRejection', { error: String(err?.stack || err) }) })
process.on('SIGINT', async () => { await disconnect(); server.close(() => process.exit(0)) })
process.on('SIGTERM', async () => { await disconnect(); server.close(() => process.exit(0)) })
