'use strict'
// Executa o código REAL numa VM; fs/http/Mineflayer/timers são fixtures.
// Nenhuma conexão, captura, modelo ou escrita do projeto é disponibilizada.
const fs = require('fs'), vm = require('vm'), assert = require('assert')
const { EventEmitter } = require('events')
const source = fs.readFileSync(process.argv[2], 'utf8')
const ChatMessage = require('../compartilhado/servicos/minecraft/node_modules/prismarine-chat')('1.16.5')
const { CollectBlock } = require('../compartilhado/servicos/minecraft/node_modules/mineflayer-collectblock/lib/CollectBlock')
const playerMessage = (author, text, translate = 'chat.type.text') => new ChatMessage({ translate, with: [author, text] })
const tick = async () => { for (let i=0;i<6;i++) await Promise.resolve() }

function fixture(files=new Map()) {
  const bots=[], records=[], timers=[]
  let handler, failSetup=false
  class Bot extends EventEmitter {
    constructor(args) {
      super(); Object.assign(this,args)
      const position={x:0,y:64,z:0,floored(){return this},distanceTo(){return 0}}
      this.entity={position}; this.entities={}; this.players={}; this.inventory={items:()=>[]}
      this.health=20; this.food=20; this.game={}; this.quitCalls=0; this.stopCalls=0
      this.collectBlock={movements:{blocksCantBreak:new Set()}}
      this.pathfinder={setMovements:m=>{if(failSetup)throw Error('Movements setup failed');this.movements=m;this.pathfinder.movements=m;this.movementSets=(this.movementSets||0)+1},
        goto:()=>new Promise((resolve,reject)=>{this.resolveGoto=resolve; this.rejectGoto=reject}),
        stop:()=>{this.stopCalls++},setGoal:()=>{}}
    }
    loadPlugin() {}
    quit() {this.quitCalls++; this.emit('end','fixture quit')}
    chat(text) {this.chatText=text}
  }
  const mods={
    http:{createServer(fn){handler=fn;return {listen(){},on(){},close(){}}}},
    mineflayer:{createBot(args){const b=new Bot(args);bots.push(b);return b}},
    'mineflayer-pathfinder':{pathfinder:()=>{},Movements:class{constructor(){this.blocksCantBreak=new Set()}},goals:{GoalNear:class{},GoalFollow:class{},GoalNearXZ:class{}}},
    'mineflayer-collectblock':{plugin:()=>{}},
    'minecraft-data':()=>({itemsByName:{wooden_pickaxe:{name:'wooden_pickaxe'}},foodsByName:{cooked_beef:{name:'cooked_beef'}},blocksByName:{crafting_table:{id:58,name:'crafting_table'},furnace:{id:61,name:'furnace'},
        oak_log:{id:17,name:'oak_log'},grass_block:{id:2,name:'grass_block'},stone:{id:1,name:'stone'},
        iron_ore:{id:15,name:'iron_ore',harvestTools:{274:true}},coal_ore:{id:16,name:'coal_ore'}},
      itemsByName:{iron_pickaxe:{id:257},iron_ore:{id:15},coal:{id:263},iron_ingot:{id:265},wooden_pickaxe:{id:270},
        oak_planks:{id:5},stick:{id:280},stone_pickaxe:{id:274},bread:{id:297}},
      items:{5:{name:'oak_planks'},280:{name:'stick'},265:{name:'iron_ingot'},274:{name:'stone_pickaxe'}}}),
    vec3:{Vec3:class{constructor(x,y,z){this.x=x;this.y=y;this.z=z}}},
    fs:{mkdirSync(){},appendFileSync(_file,text){if(text.startsWith('{'))records.push(JSON.parse(text))},
      readFileSync(file){if(!files.has(file))throw Error('ENOENT '+file);return files.get(file)},
      writeFileSync(file,text){files.set(file,text)},renameSync(from,to){files.set(to,files.get(from));files.delete(from)}},
    path:require('path'),crypto:require('crypto'),async_hooks:require('async_hooks')
  }
  const sandbox={require(name){if(!Object.hasOwn(mods,name))throw Error('Forbidden import '+name);return mods[name]},
    __dirname:'/fixture/compartilhado/servicos/minecraft',Buffer,
    process:{pid:12345,env:{HOSHINO_ENTIDADE:'hoshino'},on(){},exit(){}},
    console:{log(){},error(){}},setTimeout(fn,ms){if(ms===250)queueMicrotask(fn);else timers.push(fn);return 1},
    clearTimeout(){}}
  vm.createContext(sandbox)
  vm.runInContext(source+'\nglobalThis.api={connect,state,stop,gotoPoint,requireBot,craft,furnaceAction:typeof furnaceAction===\'function\'?furnaceAction:null,gaze:typeof gaze===\'function\'?gaze:null,unreachable:typeof unreachable===\'function\'?unreachable:null,restoreDigging:typeof restoreDigging===\'function\'?restoreDigging:null,setReflexBusy:v=>{reflexBusy=v===true?{session:sessionId,since:Date.now()}:v},ageReflex:ms=>{if(reflexBusy)reflexBusy.since-=ms}};',sandbox)
  async function connect() {
    const pending=sandbox.api.connect({host:'fixture',username:'HoshinoMC'})
    bots.at(-1).emit('login'); bots.at(-1).emit('spawn'); await tick(); return pending
  }
  async function rpc(payload) {
    return new Promise((resolve,reject)=>{
      const req=new EventEmitter(); req.method='POST';req.url='/rpc'
      const res={writeHead(code){this.code=code},end(body){resolve({code:this.code,body:JSON.parse(body)})}}
      Promise.resolve(handler(req,res)).catch(reject)
      req.emit('data',JSON.stringify(payload)); req.emit('end')
    })
  }
  return {api:sandbox.api,bots,records,timers,connect,rpc,failSetup(){failSetup=true}}
}

async function run() {
  let n=0
  const f=fixture(); await f.connect(); const old=f.bots[0],oldSession=f.api.state().sessionId
  const chatting=fixture();await chatting.connect();const talker=chatting.bots.at(-1)
  talker.emit('message',playerMessage('Gustavo','Oi, pode responder enquanto joga?'),'chat')
  talker.emit('message',playerMessage(talker.username,'meu eco'),'chat')
  talker.emit('chat','Server','falso jogador vindo da expressão regular')
  talker.emit('message',playerMessage('Server','aviso','chat.type.announcement'),'system')
  talker.emit('messagestr','aviso de sistema')
  const visible=chatting.api.state().recentChat
  assert.equal(visible.length,1);assert.equal(visible[0].username,'Gustavo')
  assert.equal(visible[0].sessionId,chatting.api.state().sessionId)
  assert.equal(visible[0].message,'Oi, pode responder enquanto joga?');n++
  for(let i=0;i<40;i++)talker.emit('message',playerMessage('Gustavo','mensagem'+i),'chat')
  assert.equal(chatting.api.state().recentChat.length,32)
  await chatting.connect();assert.equal(chatting.api.state().recentChat.length,0);n++
  // 27/10: busca A* sem limite, cavando no subsolo, levou a ponte a 3,9 GB e OOM numa só coleta.
  assert.equal(old.pathfinder.searchRadius,64);n++
  assert.equal(f.api.state().host,'fixture');assert.equal(f.api.state().port,25565)
  await f.connect(); const current=f.bots[1],newSession=f.api.state().sessionId
  assert.notEqual(oldSession,newSession)
  const before=JSON.stringify(f.api.state())
  for(const event of ['end','error','health','death','respawn','chat','messagestr','kicked']) old.emit(event,Error('late event'),'text')
  assert.equal(JSON.stringify(f.api.state()),before); assert.equal(current.quitCalls,0);n++

  const racing=fixture(), firstConnect=racing.api.connect({})
  const replaced=assert.rejects(firstConnect,/substituída/)
  await racing.connect(); await replaced
  racing.bots[0].emit('spawn');await tick()
  assert.equal(racing.api.state().connectionState,'ready');n++

  const bad=fixture();bad.failSetup()
  const badConnect=bad.api.connect({}); const rejected=assert.rejects(badConnect,/setup failed/)
  bad.bots[0].emit('spawn'); await rejected; await tick()
  assert.equal(bad.api.state().connectionState,'error');assert.throws(()=>bad.api.requireBot(),/verificado/);n++

  const slow=fixture();const timed=slow.api.connect({});const timeReject=assert.rejects(timed,/timeout/)
  slow.timers[0](); await timeReject;slow.bots[0].emit('spawn');await tick()
  assert.notEqual(slow.api.state().connectionState,'ready');n++

  for(const event of ['error','kicked']) {
    const e=fixture(); const pending=e.api.connect({});const failure=assert.rejects(pending)
    e.bots[0].emit(event,Error('failure'));await failure;e.bots[0].emit('spawn');await tick()
    assert.notEqual(e.api.state().connectionState,'ready');n++
  }

  const request={action:'chat',args:{text:'oi'},request_id:'rpc-test',parent_id:'tool-test',
    turn_id:'turn-test',entity_id:'hoshino',session_id:newSession}
  const receipt=await f.rpc(request)
  assert.equal(receipt.code,200);assert.equal(receipt.body.ok,true)
  for(const field of ['request_id','parent_id','turn_id','entity_id','session_id'])assert.equal(receipt.body[field],request[field])
  const trace=f.records.find(r=>r.event==='action.end'&&r.data.request_id==='rpc-test')
  assert.equal(trace.data.turn_id,'turn-test');assert.equal(trace.data.parent_id,'tool-test');n++
  for(const foreign of [{entity_id:'lilith'},{session_id:oldSession}]) {
    const response=await f.rpc({...request,...foreign}); assert.equal(response.code,400);assert.equal(response.body.ok,false)
    assert.equal(current.chatText,'oi');n++
  }

  const navigation=f.api.gotoPoint({x:2,y:64,z:2})
  assert.match(f.api.stop(),/cooperativa solicitada/);assert.equal(current.stopCalls,1)
  assert.equal(f.api.state().pathfinding.stopRequested,true)
  current.rejectGoto(Error('cooperatively stopped'));await assert.rejects(navigation,/navegação falhou/)
  assert.equal(f.api.state().pathfinding,null);n++

  const late=f.api.gotoPoint({x:5,y:64,z:5}), lateReject=assert.rejects(late,/sessão substituída/)
  await f.connect();const next=f.bots.at(-1)
  const nextJob=f.api.gotoPoint({x:9,y:64,z:9}); const newAction=JSON.stringify(f.api.state().pathfinding)
  current.resolveGoto();await lateReject
  assert.equal(JSON.stringify(f.api.state().pathfinding),newAction)
  next.resolveGoto();await nextJob;n++
  // Caminhada longa (30/10): passa do orçamento de 50 s e devolve o trecho medido, sem virar incerta.
  const longWalk=fixture();await longWalk.connect();const lw=longWalk.bots[0]
  lw.pathfinder.goto=()=>new Promise(()=>{});lw.entity.position={x:10,y:64,z:3,floored(){return this},distanceTo(){return 0}}
  const walk=longWalk.api.gotoPoint({x:70,y:64,z:3,range:2})
  await tick();lw.entity.position={x:15,y:64,z:3,floored(){return this},distanceTo(){return 0}};longWalk.timers.at(-1)()
  assert.match(await walk,/Andei 50 s rumo a 70, 64, 3: de 10,64,3 até 15, 64, 3; faltam cerca de 55 blocos/)
  assert.equal(longWalk.api.state().pathfinding,null);n++
  // Presa no lugar (30/10, arco): 50 s pulando sem avançar não é "Andei"; no meio de um salto (Y diferente) também não.
  const stuckWalk=longWalk.api.gotoPoint({x:15,y:64,z:9,range:2});await tick()
  lw.entity.position={x:15.4,y:65.2,z:3.3,floored(){return {x:15,y:65,z:3}},distanceTo(){return 0}};longWalk.timers.at(-1)()
  const stuckText=await stuckWalk
  assert.match(stuckText,/mas fiquei presa perto de 15,64,3: avancei menos de 2 blocos e faltam cerca de 6/);assert.doesNotMatch(stuckText,/Andei/)
  assert.equal(longWalk.api.state().pathfinding,null);n++
  // Parada pendente (30/10): stop() com o bot parado (cancelTask da coleta) cancelava a caminhada seguinte na hora.
  const pendingWalk=fixture();await pendingWalk.connect();const pw=pendingWalk.bots[0];let pendingStop=false
  pw.pathfinder.isMoving=()=>false;pw.pathfinder.stop=()=>{pendingStop=true}
  // Como a biblioteca: consumir a parada pendente emite path_stop (resetPath → stop()).
  pw.pathfinder.setGoal=()=>{if(pendingStop){pendingStop=false;pw.emit('path_stop')}}
  let arrive;pw.pathfinder.goto=()=>{if(pendingStop){pendingStop=false;const e=Error('Path was stopped');e.name='PathStopped';return Promise.reject(e)}
    return new Promise(r=>{arrive=r})}
  pw.pathfinder.stop()
  const pendingJob=pendingWalk.api.gotoPoint({x:5,y:64,z:5,range:2});await tick()
  // Revisão Codex: o path_stop da limpeza não pode apagar o registro da caminhada nova.
  assert.equal(pendingWalk.api.state().pathfinding?.type,'goto');arrive()
  assert.match(await pendingJob,/Cheguei perto de 5, 64, 5/);n++
  // Com caminho ativo (fuga do reflexo), a limpeza não mexe no objetivo em andamento.
  let cleared=0;pw.pathfinder.isMoving=()=>true;pw.pathfinder.setGoal=g=>{if(g===null)cleared++}
  pw.pathfinder.goto=()=>Promise.resolve();await pendingWalk.api.gotoPoint({x:6,y:64,z:6,range:2});assert.equal(cleared,0)
  pw.pathfinder.isMoving=()=>false;pw.pathfinder.goal={fuga:true}  // fuga recém-definida, caminho ainda não calculado
  await pendingWalk.api.gotoPoint({x:7,y:64,z:7,range:2});assert.equal(cleared,0);n++
  const crafting=fixture();await crafting.connect();const cb=crafting.bots[0]
  let equipCalls=0;cb.equip=async()=>{equipCalls++}
  const missingEquipment=await crafting.rpc({action:'equip',args:{name:'crafting_table',destination:'hand'},
    request_id:'missing-equipment',parent_id:'tool-equipment',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(missingEquipment.code,200);assert.equal(missingEquipment.body.ok,false)
  assert.equal(missingEquipment.body.code,'equip_preconditions')
  assert.equal(missingEquipment.body.effect_state,'not_started');assert.equal(missingEquipment.body.phase,'preflight')
  assert.equal(missingEquipment.body.details.item,'crafting_table');assert.equal(equipCalls,0);n++
  cb.inventory.items=()=>[{name:'oak_planks',count:2}]
  cb.equip=async()=>{equipCalls++;throw Error('ACK failed after equip started')}
  const failedEquipment=await crafting.rpc({action:'equip',args:{name:'oak_planks',destination:'hand'},
    request_id:'failed-equipment',parent_id:'tool-equipment',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(failedEquipment.code,400);assert.notEqual(failedEquipment.body.effect_state,'not_started')
  assert.equal(equipCalls,1);cb.inventory.items=()=>[];n++
  const table={name:'crafting_table',position:{x:1,y:64,z:1}}
  cb.findBlock=()=>table;cb.recipesFor=(_id,_meta,_count,t)=>t===table?[{requiresTable:true,result:{count:1}}]:[]
  let craftingUsed=false;cb.craft=async (_recipe,_count,t)=>{assert.equal(t,table);craftingUsed=true}
  await crafting.api.craft({name:'iron_pickaxe',count:1});assert.ok(craftingUsed);n++
  cb.recipesFor=()=>[];cb.recipesAll=()=>[{requiresTable:true,result:{count:1},delta:[{id:265,count:-3}]}]
  craftingUsed=false
  const preflight=await crafting.rpc({action:'craft',args:{name:'iron_pickaxe'},request_id:'preflight-test',
    parent_id:'tool-preflight',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(preflight.code,200);assert.equal(preflight.body.ok,false)
  assert.equal(preflight.body.effect_state,'not_started');assert.equal(preflight.body.phase,'preflight')
  assert.equal(preflight.body.details.recipes[0].ingredients[0].count,3)
  assert.equal(craftingUsed,false);n++
  // ID inexistente é recusado antes de qualquer efeito: retorno para nova decisão, não incerteza.
  const unknown=await crafting.rpc({action:'craft',args:{name:'oak_plank'},request_id:'unknown-item-test',
    parent_id:'tool-unknown',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(unknown.code,200);assert.equal(unknown.body.effect_state,'not_started')
  assert.equal(unknown.body.code,'craft_preconditions');assert.equal(unknown.body.details.unknown_item,true)
  assert.match(unknown.body.erro,/oak_plank/);assert.equal(craftingUsed,false);n++
  cb.recipesFor=()=>[{requiresTable:true,result:{count:1}}]
  cb.craft=async()=>{throw Error('failure after crafting started')}
  const partial=await crafting.rpc({action:'craft',args:{name:'iron_pickaxe'},request_id:'partial-test',
    parent_id:'tool-partial',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(partial.code,400);assert.notEqual(partial.body.effect_state,'not_started');n++
  const placement=fixture();await placement.connect();const pb=placement.bots[0]
  // Visibilidade vem do mundo: nenhum alcance/ameaça é inventado a partir do nome.
  const hostilePos={x:1,y:59,z:1,floored(){return this}}
  pb.entities[44]={id:44,name:'skeleton',type:'mob',height:1.8,position:hostilePos}
  pb.canSeeBlock=()=>false;assert.equal(placement.api.state().nearbyEntities[0].lineOfSight,false)
  pb.canSeeBlock=()=>true;assert.equal(placement.api.state().nearbyEntities[0].lineOfSight,true)
  delete pb.canSeeBlock;assert.equal(placement.api.state().nearbyEntities[0].lineOfSight,null);n++
  pb.entities={}
  const targetBlock={name:'air',position:{x:1,y:64,z:1}};pb.heldItem={name:'crafting_table',count:1}
  pb.blockAt=p=>p.y===63?{name:'grass_block',position:{x:p.x,y:p.y,z:p.z}}:targetBlock
  pb.placeBlock=async()=>{targetBlock.name='crafting_table';pb.heldItem=null}
  const placed=await placement.rpc({action:'place_block',args:{x:1,y:63,z:1,face:'up'},
    request_id:'place-proof',parent_id:'tool-placement',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(placed.code,200);assert.equal(placed.body.resultado.placed.name,'crafting_table')
  assert.equal(placed.body.resultado.placed.verified,true);assert.equal(placed.body.resultado.placed.position.y,64);n++
  assert.equal(placed.body.resultado.placed.sessionId,placement.api.state().sessionId)
  // Após envio, alvo vazio e inventário igual são apenas um snapshot, sem prova de recusa.
  // Longe demais (28/10: 11 blocos depois da caça): recusa antes de enviar.
  const savedDist=pb.entity.position.distanceTo;pb.entity.position.distanceTo=()=>11
  const far=await placement.rpc({action:'place_block',args:{x:1,y:63,z:1,face:'up'},request_id:'place-far',parent_id:'tool-far',
    entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(far.body.code,'place_preconditions');assert.match(far.body.erro||far.body.error||JSON.stringify(far.body),/aproxime-se/);pb.entity.position.distanceTo=savedDist;n++
  // Item que não é bloco (28/10: picareta na mão depois do reflexo): recusa sem efeito, sem enviar.
  targetBlock.name='air';pb.heldItem={name:'wooden_pickaxe',count:1};let placeCalls=0;pb.placeBlock=async()=>{placeCalls++}
  const notBlock=await placement.rpc({action:'place_block',args:{x:1,y:63,z:1,face:'up'},
    request_id:'place-not-block',parent_id:'tool-not-block',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(notBlock.body.code,'place_preconditions');assert.equal(placeCalls,0);n++
  targetBlock.name='air';pb.heldItem={name:'dark_oak_log',count:1}
  pb.placeBlock=async()=>{throw Error('Server refused to place dark_oak_log: the block is still air')}
  const refused=await placement.rpc({action:'place_block',args:{x:1,y:63,z:1,face:'up'},
    request_id:'place-refused',parent_id:'tool-refused',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(refused.code,400);assert.equal(refused.body.effect_state,undefined);n++
  // Perto do ponto de nascimento (30/10): a recusa continua incerta e ganha o fato da distância ao spawn.
  pb.spawnPoint={x:3,y:64,z:4}
  const nearSpawn=await placement.rpc({action:'place_block',args:{x:1,y:63,z:1,face:'up'},
    request_id:'place-spawn',parent_id:'tool-spawn',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(nearSpawn.code,400);assert.match(nearSpawn.body.erro,/a 5 blocos do ponto de nascimento do mundo em \(3,64,4\)/)
  delete pb.spawnPoint;n++
  // Falha no ACK não impede uma atualização tardia do servidor: nunca liberar replay.
  let delayedPlacement
  pb.placeBlock=async()=>{delayedPlacement=()=>{targetBlock.name='dark_oak_log'};throw Error('timeout aguardando confirmação')}
  const delayed=await placement.rpc({action:'place_block',args:{x:1,y:63,z:1,face:'up'},
    request_id:'place-delayed',parent_id:'tool-delayed',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  delayedPlacement();assert.equal(targetBlock.name,'dark_oak_log')
  assert.equal(delayed.code,400);assert.equal(delayed.body.effect_state,undefined);n++
  // Bloco alvo mudou apesar do erro: o efeito é desconhecido e continua incerto.
  targetBlock.name='air'
  pb.placeBlock=async()=>{targetBlock.name='dark_oak_log';throw Error('timeout depois de colocar')}
  const changed=await placement.rpc({action:'place_block',args:{x:1,y:63,z:1,face:'up'},
    request_id:'place-changed',parent_id:'tool-changed',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(changed.code,400);assert.equal(changed.body.effect_state,undefined);n++
  // Referência de ar (a própria posição) e alvo no corpo da entidade: recusados antes, com explicação.
  pb.heldItem={name:'crafting_table',count:1};let tried=false;pb.placeBlock=async()=>{tried=true}
  pb.blockAt=p=>({name:p.y===63?'grass_block':'air',boundingBox:p.y===63?'block':'empty',position:{x:p.x,y:p.y,z:p.z}})
  Object.assign(pb.entity.position,{x:1.5,y:64,z:1.5})
  const airRef=await placement.rpc({action:'place_block',args:{x:1,y:64,z:1,face:'north'},
    request_id:'place-air-ref',parent_id:'tool-air',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(airRef.code,200);assert.equal(airRef.body.code,'place_preconditions')
  assert.equal(airRef.body.details.reference_block,'air');assert.match(airRef.body.erro,/sólido/)
  assert.match(airRef.body.erro,/sem x,y,z/);n++
  const ownBody=await placement.rpc({action:'place_block',args:{x:1,y:63,z:1,face:'up'},
    request_id:'place-own-body',parent_id:'tool-body',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(ownBody.code,200);assert.equal(ownBody.body.code,'place_preconditions')
  assert.match(ownBody.body.erro,/onde você está/);assert.equal(tried,false);n++
  const busyTarget=await placement.rpc({action:'place_block',args:{x:2,y:63,z:1,face:'west'},
    request_id:'place-occupied',parent_id:'tool-occupied',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(busyTarget.code,200);assert.equal(busyTarget.body.code,'place_preconditions')
  assert.match(busyTarget.body.erro,/já tem grass_block/);assert.equal(tried,false);n++
  // Sem coordenadas: a ponte escolhe chão sólido livre ao lado, fora do próprio corpo.
  const world=new Map();const key=p=>`${p.x},${p.y},${p.z}`
  pb.blockAt=p=>({name:world.get(key(p))||(p.y<=63?'grass_block':'air'),boundingBox:(world.get(key(p))||p.y<=63)?'block':'empty',
    position:{x:p.x,y:p.y,z:p.z}})
  world.set('6,64,5','stone')  // um vizinho ocupado é pulado
  Object.assign(pb.entity.position,{x:5.5,y:64,z:5.5});let usedRef=null
  pb.placeBlock=async(ref,face)=>{usedRef={...ref.position,face};world.set(`${ref.position.x+face.x},${ref.position.y+face.y},${ref.position.z+face.z}`,'crafting_table');pb.heldItem=null}
  const nearby=await placement.rpc({action:'place_block',args:{},request_id:'place-nearby',parent_id:'tool-nearby',
    entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(nearby.code,200);assert.equal(nearby.body.resultado.placed.verified,true)
  assert.equal(usedRef.y,63);assert.equal(usedRef.face.y,1);assert.notDeepEqual([usedRef.x,usedRef.z],[6,5])
  assert.notDeepEqual([usedRef.x,usedRef.z],[5,5]);n++
  // Percepção pedida: entorno útil e análise factual das receitas, sem agir.
  // Uma busca por tipo: 300 pedras ao redor não podem esconder o minério mais distante (26/10: só "stone").
  const byId={17:[{x:8,y:64,z:5},{x:9,y:64,z:5}],58:[{x:5,y:64,z:2}],15:[{x:5,y:55,z:9}],
    1:Array.from({length:300},(_,i)=>({x:5+(i%5),y:63,z:5+Math.floor(i/5)}))}
  pb.findBlocks=({matching,count})=>{assert.equal(typeof matching,'number');return (byId[matching]||[]).slice(0,count)}
  pb.blockAt=p=>({name:p.y===55?'iron_ore':p.y===63?'stone':p.x===5&&p.z===2?'crafting_table':'oak_log',boundingBox:'block',position:p})
  pb.findBlock=()=>null;pb.inventory.items=()=>[{name:'oak_planks',count:2},{name:'stick',count:4}]
  pb.recipesAll=()=>[{requiresTable:true,result:{count:1},delta:[{id:5,count:-3},{id:280,count:-2}]}]
  const seen=await placement.rpc({action:'state',args:{perception:['wooden_pickaxe']},request_id:'perceive',
    parent_id:'tool-perceive',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  const per=seen.body.resultado.percepcao
  assert.equal(per.arredores.oak_log.quantidade,2);assert.equal(per.arredores.oak_log.distancia,2.5)
  assert.match(per.arredores.crafting_table.direcao,/norte/)
  const pick=per.receitas[0];assert.equal(pick.bancada_a_4_blocos,false)
  assert.deepEqual(pick.variantes[0].ingredientes,[{nome:'oak_planks',precisa:3,tem:2},{nome:'stick',precisa:2,tem:4}])
  assert.equal(pick.variantes[0].faltam_unidades,1);assert.equal(pick.variantes[0].pode_agora,false)
  assert.equal(per.arredores.iron_ore.distancia,9.7);assert.equal(per.arredores.iron_ore.direcao,'sul, abaixo')
  assert.equal(per.arredores.stone.quantidade,'64+')
  // Ferramenta exigida faz parte do fato observado: sem picareta de pedra, ferro não solta nada.
  assert.equal(per.arredores.iron_ore.ferramenta_ok,false);assert.deepEqual(per.arredores.iron_ore.ferramentas,['stone_pickaxe'])
  assert.equal(per.arredores.oak_log.ferramenta_ok,true);n++
  let collected=0;pb.collectBlock={collect:async()=>{collected++}};pb.findBlock=()=>({name:'iron_ore',position:{x:5,y:55,z:9}})
  const noTool=await placement.rpc({action:'collect',args:{name:'iron_ore',count:1,maxDistance:24},request_id:'collect-no-tool',
    parent_id:'tool-no-tool',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(noTool.code,200);assert.equal(noTool.body.code,'harvest_preconditions');assert.equal(collected,0)
  assert.match(noTool.body.erro,/stone_pickaxe/)
  pb.blockAt=()=>({name:'iron_ore',position:{x:5,y:55,z:9}});let dug=0;pb.dig=async()=>{dug++}
  const noToolDig=await placement.rpc({action:'dig',args:{x:5,y:55,z:9},request_id:'dig-no-tool',
    parent_id:'tool-dig-no-tool',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(noToolDig.body.code,'harvest_preconditions');assert.equal(dug,0)
  pb.findBlock=()=>null;n++
  // Estação quebrada (30/10, pedido humano): a bancada cai como item; a ponte recolhe e confere no inventário.
  const tablePos={x:5,y:64,z:9,offset(dx,dy,dz){return {x:this.x+dx,y:this.y+dy,z:this.z+dz}}}
  const savedItems=pb.inventory.items,savedCollect=pb.collectBlock,savedEntities=pb.entities,savedTool=pb.tool
  let inv={};pb.inventory.items=()=>Object.entries(inv).filter(([,c])=>c>0).map(([name,count])=>({name,count}))
  let equippedFor=null;pb.tool={equipForBlock:async block=>{equippedFor=block.name}}
  pb.blockAt=()=>({name:'crafting_table',position:tablePos});pb.dig=async()=>{inv.coal=3}  // o carvão entra sozinho
  const dropAt={x:5.5,y:64.2,z:9.5,distanceTo(){return 0.3},floored(){return {x:5,y:64,z:9}}}
  const coalDrop={name:'item',position:dropAt,getDroppedItem(){return {name:'coal'}}}
  const tableDrop={name:'item',position:dropAt,getDroppedItem(){return {name:'crafting_table'}}}
  pb.entities={76:coalDrop,77:tableDrop};let picked=null;const savedGotoSt=pb.pathfinder.goto
  // Anda até o item com o pathfinder (revisão Codex: não com o collectBlock); ao chegar, o item entra.
  pb.pathfinder.goto=async goal=>{picked=goal;inv.crafting_table=1}
  const recovered=await placement.rpc({action:'dig',args:{x:5,y:64,z:9,expect:'crafting_table'},request_id:'dig-station',
    parent_id:'tool-dig-station',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  // Revisão Codex: equipa a ferramenta, recolhe o item da estação (não o carvão) e diz tudo o que entrou.
  assert.equal(equippedFor,'crafting_table');assert.ok(picked)
  assert.match(recovered.body.resultado,/Quebrei crafting_table e recolhi 1 crafting_table \(agora tenho 1\); também entraram: 3 coal/)
  // Sem o item no inventário depois, o recibo diz que caiu e não entrou (não afirma recolhimento).
  pb.pathfinder.goto=async()=>{};inv={};pb.dig=async()=>{}
  const lostTable=await placement.rpc({action:'dig',args:{x:5,y:64,z:9},request_id:'dig-station-lost',
    parent_id:'tool-dig-station-lost',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.match(lostTable.body.resultado,/o item caiu e não entrou no inventário \(tenho 0 crafting_table\)/)
  // Outro bloco na coordenada da estação: nada é quebrado, recusa antes do efeito.
  let dugOther=0;pb.blockAt=()=>({name:'chest',position:tablePos});pb.dig=async()=>{dugOther++}
  const otherBlock=await placement.rpc({action:'dig',args:{x:5,y:64,z:9,expect:'crafting_table'},request_id:'dig-station-other',
    parent_id:'tool-dig-station-other',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(otherBlock.body.code,'dig_preconditions');assert.equal(otherBlock.body.effect_state,'not_started');assert.equal(dugOther,0)
  // Quebrar sem fim (revisão Codex): passado o prazo, para de cavar e falha (incerto), nunca sucesso tardio.
  let stopped=0;pb.stopDigging=()=>{stopped++};pb.blockAt=()=>({name:'crafting_table',position:tablePos});pb.dig=()=>new Promise(()=>{})
  const tDig=placement.timers.length
  const hungDig=placement.rpc({action:'dig',args:{x:5,y:64,z:9,expect:'crafting_table'},request_id:'dig-station-hung',
    parent_id:'tool-dig-station-hung',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  for(let i=0;i<20&&placement.timers.length===tDig;i++)await new Promise(r=>setImmediate(r))
  placement.timers.at(-1)()
  const hungRes=await hungDig
  assert.equal(hungRes.body.ok,false);assert.match(hungRes.body.erro,/passou de 20 s; parei de cavar/);assert.equal(stopped,1)
  // Equipar que termina depois do prazo não começa a quebrar (revisão Codex).
  let finishEquip,lateDig=0;pb.tool={equipForBlock:()=>new Promise(r=>{finishEquip=r})};pb.dig=async()=>{lateDig++}
  const tEq=placement.timers.length
  const lateEquip=placement.rpc({action:'dig',args:{x:5,y:64,z:9,expect:'crafting_table'},request_id:'dig-station-late-equip',
    parent_id:'tool-dig-station-late-equip',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  for(let i=0;i<20&&placement.timers.length===tEq;i++)await new Promise(r=>setImmediate(r))
  placement.timers.at(-1)();assert.equal((await lateEquip).body.ok,false)
  finishEquip();await new Promise(r=>setImmediate(r));assert.equal(lateDig,0)
  // Caminhada até o item que falha (NoPath) limpa o objetivo.
  pb.tool={equipForBlock:async()=>{}};pb.dig=async()=>{};pb.entities={77:tableDrop};inv={}
  const goalsNoPath=[];const savedSetGoal=pb.pathfinder.setGoal;pb.pathfinder.setGoal=g=>{goalsNoPath.push(g)}
  pb.pathfinder.goto=async()=>{const e=Error('No path');e.name='NoPath';throw e}
  const noPathPick=await placement.rpc({action:'dig',args:{x:5,y:64,z:9,expect:'crafting_table'},request_id:'dig-station-nopath',
    parent_id:'tool-dig-station-nopath',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.match(noPathPick.body.resultado,/o item caiu e não entrou/);assert.equal(goalsNoPath.at(-1),null);pb.pathfinder.setGoal=savedSetGoal
  // goto da biblioteca que RESOLVE sem chegar (caminho vazio em noPath; revisão Codex): objetivo também é limpo.
  goalsNoPath.length=0;pb.pathfinder.setGoal=g=>{goalsNoPath.push(g)};pb.pathfinder.goto=async()=>{}
  await placement.rpc({action:'dig',args:{x:5,y:64,z:9,expect:'crafting_table'},request_id:'dig-station-emptypath',
    parent_id:'tool-dig-station-emptypath',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(goalsNoPath.at(-1),null);pb.pathfinder.setGoal=savedSetGoal
  pb.inventory.items=savedItems;pb.collectBlock=savedCollect;pb.entities=savedEntities;pb.tool=savedTool;pb.pathfinder.goto=savedGotoSt;n++
  // Entregar item (30/10, pedido humano): anda até o jogador, olha, joga e confere no inventário.
  let bread=12,farDist=0;const savedItemsT=pb.inventory.items,savedPos=pb.entity.position,savedGotoT=pb.pathfinder.goto
  pb.inventory.items=()=>bread?[{name:'bread',count:bread}]:[]
  pb.entity.position={x:0,y:64,z:0,floored(){return this},distanceTo(){return farDist},offset(){return this}}
  let tossed=null,looked=0;pb.toss=async(id,meta,count)=>{tossed={id,count};bread-=count};pb.lookAt=async()=>{looked++}
  const atoPos={x:2,y:64,z:0,offset(){return this},distanceTo(){return farDist}}
  pb.players={ATO:{entity:{position:atoPos,username:'ATO'}}}
  const give=p=>placement.rpc({action:'toss',args:p,request_id:'toss-'+JSON.stringify(p).length+'-'+bread+'-'+farDist,
    parent_id:'tool-toss',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  const near=await give({name:'bread',count:3,toPlayer:'ATO'})
  assert.match(near.body.resultado,/Joguei 3 bread para ATO, a 0\.0 blocos; tenho agora 9/);assert.deepEqual(tossed,{id:297,count:3});assert.equal(looked,1)
  farDist=10;pb.pathfinder.goto=async()=>{farDist=1.5}  // longe: anda até perto e entrega
  assert.match((await give({name:'bread',count:2,toPlayer:'ATO'})).body.resultado,/Joguei 2 bread para ATO.*tenho agora 7/)
  farDist=10;pb.pathfinder.goto=async()=>{const e=Error('No path');e.name='NoPath';throw e}  // não chega: não joga
  assert.match((await give({name:'bread',count:2,toPlayer:'ATO'})).body.resultado,/fiquei a 10\.0 blocos; não joguei bread \(tenho 7\)/)
  farDist=0
  // Revisão Codex: ATO sai durante a caminhada; nada é jogado nem declarado entregue.
  farDist=10;tossed=null;pb.pathfinder.goto=async()=>{farDist=1;delete pb.players.ATO}
  assert.match((await give({name:'bread',count:1,toPlayer:'ATO'})).body.resultado,/ATO saiu de perto antes da entrega; não joguei bread/)
  assert.equal(tossed,null);pb.players={ATO:{entity:{position:atoPos,username:'ATO'}}}
  assert.equal((await give({name:'bread',count:1,toPlayer:'Ninguem'})).body.code,'toss_preconditions')  // jogador não visto
  assert.equal((await give({name:'oak_planks',count:1})).body.code,'toss_preconditions')  // sem o item: nada jogado
  assert.match((await give({name:'bread',count:1})).body.resultado,/Joguei 1 bread no chão; tenho agora 6/)
  pb.inventory.items=savedItemsT;pb.entity.position=savedPos;pb.pathfinder.goto=savedGotoT;pb.players={};n++
  // Lingote vem do forno: a fundição aparece como fato da receita, não como fabricação.
  pb.inventory.items=()=>[{name:'iron_ore',count:2},{name:'coal',count:3}]
  pb.recipesAll=()=>[{requiresTable:false,result:{count:9},delta:[{id:265,count:-1}]}]
  const smelt=(await placement.rpc({action:'state',args:{perception:['iron_ingot']},request_id:'perceive-smelt',
    parent_id:'tool-smelt',entity_id:'hoshino',session_id:placement.api.state().sessionId})).body.resultado.percepcao.receitas[0]
  const furnaceWay=smelt.variantes.find(v=>v.processo==='fornalha')
  assert.deepEqual(furnaceWay.ingredientes,[{nome:'iron_ore',precisa:1,tem:2}]);assert.equal(furnaceWay.forno_a_4_blocos,false)
  assert.deepEqual(smelt.variantes[0],furnaceWay);n++
  const noFurnace=await placement.rpc({action:'furnace_put',args:{input:'iron_ore',fuel:'coal',count:1,fuelCount:1},
    request_id:'furnace-missing',parent_id:'tool-furnace',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(noFurnace.code,200);assert.equal(noFurnace.body.code,'furnace_preconditions')
  assert.equal(noFurnace.body.effect_state,'not_started');n++
  const plain=await placement.rpc({action:'state',args:{},request_id:'plain-state',parent_id:'tool-plain',
    entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(plain.body.resultado.percepcao,undefined);n++
  // NoPath sem sair do lugar: objetivo limpo (sem movimento tardio) e retorno verificado sem efeito.
  const goals=[];pb.pathfinder.setGoal=g=>{goals.push(g)}
  pb.pathfinder.goto=async()=>{const e=Error('No path to the goal!');e.name='NoPath';throw e}
  const noPath=await placement.rpc({action:'goto',args:{x:-96,y:69,z:-61,range:3},request_id:'goto-nopath',
    parent_id:'tool-nopath',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(noPath.code,200);assert.equal(noPath.body.code,'goto_no_path');assert.equal(noPath.body.effect_state,'not_applied')
  assert.deepEqual(goals,[null,null]);n++  // limpeza da parada pendente (30/10) e limpeza após a falha
  // Se andou antes de falhar, o deslocamento é efeito real. 12/11: como no tempo esgotado, volta MEDIDO (de onde até
  // onde, com o estado) em vez de incerto: a incerteza pausava a tarefa inteira por 2 blocos andados.
  goals.length=0
  pb.pathfinder.goto=async()=>{pb.entity.position.x+=4;const e=Error('No path');e.name='NoPath';throw e}
  const moved=await placement.rpc({action:'goto',args:{x:-96,y:69,z:-61,range:3},request_id:'goto-moved',
    parent_id:'tool-moved',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(moved.code,200);assert.match(moved.body.resultado,/Não achei caminho até -96, 69, -61; andei de .* e parei/)
  assert.deepEqual(goals,[null,null]);pb.entity.position.x-=4;n++  // objetivo limpo: sem movimento tardio
  // Coleta usa o mesmo pathfinder: NoPath sem andar, sem item e com o bloco intacto é retorno sem efeito.
  const coal={name:'coal_ore',position:{x:7,y:60,z:5}};let coalName='coal_ore';goals.length=0
  pb.findBlock=()=>coal;pb.blockAt=p=>({name:p.y===60?coalName:'stone',boundingBox:'block',position:p})
  pb.inventory.items=()=>[{name:'stone_pickaxe',count:1}]
  pb.collectBlock={collect:async()=>{const e=Error('No path to the goal!');e.name='NoPath';throw e}}
  const coalNoPath=await placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-nopath',
    parent_id:'tool-collect-nopath',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(coalNoPath.code,200);assert.equal(coalNoPath.body.code,'collect_no_path');assert.deepEqual(goals,[null]);n++
  // Bloco quebrado sem recolher: efeito real, continua incerto.
  pb.collectBlock={collect:async()=>{coalName='air';const e=Error('No path to the goal!');e.name='NoPath';throw e}}
  const coalDug=await placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-dug',
    parent_id:'tool-collect-dug',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(coalDug.code,400);pb.findBlock=()=>null;n++
  // Efeito antes do NoPath (28/10): devolve o que o inventário mostra em vez de erro incerto.
  pb.inventory.items=()=>[{name:'stone_pickaxe',count:1}];coalName='coal_ore';pb.findBlock=()=>coal;goals.length=0
  pb.collectBlock={collect:async()=>{pb.inventory.items=()=>[{name:'stone_pickaxe',count:1},{name:'coal',count:1}];
    const e=Error('No path to the goal!');e.name='NoPath';throw e}}
  const pathless=await placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-partial',
    parent_id:'tool-collect-partial',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(pathless.code,200);assert.equal(pathless.body.ok,true);assert.equal(pathless.body.resultado.sem_caminho,true)
  assert.match(pathless.body.resultado.message,/\+1 coal/);assert.deepEqual(goals,[null]);n++
  // Cavou o caminho e ficou sem caminho com o alvo intacto (28/10): efeito medido, não incerto.
  pb.inventory.items=()=>[{name:'stone_pickaxe',count:1}];coalName='coal_ore';pb.findBlock=()=>coal;goals.length=0
  pb.collectBlock={collect:async()=>{pb.inventory.items=()=>[{name:'stone_pickaxe',count:1},{name:'cobblestone',count:2}];
    const e=Error('No path to the goal!');e.name='NoPath';throw e}}
  const dugWay=await placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-way',
    parent_id:'tool-collect-way',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(dugWay.code,200);assert.equal(dugWay.body.resultado.sem_caminho,true);assert.match(dugWay.body.resultado.message,/\+0 coal/);n++
  // Lava (28/10): minério encostado em lava não é escolhido; a coleta diz o motivo sem cavar.
  let lavaCalls=0;const savedBlockAt=pb.blockAt
  pb.findBlock=opts=>typeof opts.matching==='function'?(opts.matching({type:16,position:coal.position})?coal:null):coal
  pb.blockAt=p=>(p.x===8&&p.y===60&&p.z===5)?{name:'lava',boundingBox:'empty'}:savedBlockAt(p)
  pb.collectBlock={collect:async()=>{lavaCalls++}}
  const lavaRisk=await placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-lava',
    parent_id:'tool-collect-lava',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(lavaRisk.body.resultado.perigo_lava,true);assert.equal(lavaCalls,0);pb.blockAt=savedBlockAt;pb.findBlock=()=>null;n++
  // collectBlock pendurado (27/10 13:37): orçamento próprio devolve o fato medido pelo inventário.
  // 30/10 (revisões Codex): biblioteca que não encerra no cancelTask: espera 8 s e o recibo diz que ainda encerra.
  const nextTimer=async t=>{for(let i=0;i<20&&placement.timers.length===t;i++)await new Promise(r=>setImmediate(r))
    assert.equal(placement.timers.length,t+1);placement.timers.at(-1)()}
  coalName='coal_ore';pb.findBlock=()=>coal;let cancelled=0;goals.length=0
  pb.collectBlock={collect:()=>{pb.inventory.items=()=>[{name:'stone_pickaxe',count:1},{name:'coal',count:1}];return new Promise(()=>{})},
    cancelTask:()=>{cancelled++;return new Promise(()=>{})}}
  let tHang=placement.timers.length
  const hanging=placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-hang',
    parent_id:'tool-collect-hang',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  await nextTimer(tHang)  // prazo da coleta
  tHang=placement.timers.length;await nextTimer(tHang)  // espera do encerramento
  const hung=await hanging
  assert.equal(hung.code,200);assert.equal(hung.body.resultado.interrompida,true)
  assert.deepEqual(hung.body.resultado.depois.find(i=>i.name==='coal'),{name:'coal',count:1})
  assert.equal(hung.body.resultado.biblioteca_encerrada,false);assert.match(hung.body.resultado.message,/ainda não encerrou a coleta/)
  assert.equal(cancelled,1);assert.deepEqual(goals,[null,null]);pb.findBlock=()=>null;n++  // parada + limpeza da pendente
  // Quando a biblioteca encerra a coleta no cancelTask, a ponte espera por ela e o recibo não avisa nada a mais.
  pb.findBlock=()=>coal;let finishCol
  pb.collectBlock={collect:()=>new Promise(r=>{finishCol=r}),cancelTask:()=>{finishCol();return Promise.resolve()}}
  tHang=placement.timers.length
  const ending=placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-ends',
    parent_id:'tool-collect-ends',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  await nextTimer(tHang)
  const endedCollect=await ending
  assert.equal(endedCollect.body.resultado.biblioteca_encerrada,true)
  assert.doesNotMatch(endedCollect.body.resultado.message,/ainda não encerrou/);pb.findBlock=()=>null;n++
  // Inventário cheio (30/10): o collectBlock tenta guardar num baú; sem efeito, a ponte diz o fato.
  pb.inventory.items=()=>[{name:'stone_pickaxe',count:1}];pb.findBlock=()=>coal
  pb.collectBlock={collect:async()=>{throw Error('There are no defined chest locations!')},cancelTask:()=>Promise.resolve()}
  const full=await placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-full',
    parent_id:'tool-collect-full',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(full.body.code,'collect_inventory_full');assert.equal(full.body.effect_state,'not_applied')
  assert.match(full.body.erro,/inventário cheio .*minecraft_jogar_item/);pb.findBlock=()=>null;n++
  // Veio (28/10): 75 s por bloco passava dos 90 s do RPC; o orçamento é da coleta inteira.
  const realNow=Date.now,t0=realNow();let veinCalls=0;Date.now=()=>t0
  pb.inventory.items=()=>[{name:'stone_pickaxe',count:1}];pb.findBlock=()=>coal
  let finishVein  // como a biblioteca real: cancelTask encerra a coleta em andamento (collectBlock_finished)
  pb.collectBlock={collect:()=>{veinCalls++;if(veinCalls===1){pb.inventory.items=()=>[{name:'stone_pickaxe',count:1},{name:'coal',count:1}]
    Date.now=()=>t0+80000;return Promise.resolve()}return new Promise(r=>{finishVein=r})},cancelTask:()=>{finishVein?.();return Promise.resolve()}}
  const vein=placement.rpc({action:'collect',args:{name:'coal_ore',count:3,maxDistance:24},request_id:'collect-vein-budget',
    parent_id:'tool-collect-vein-budget',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  for(let i=0;i<4;i++)await new Promise(r=>setImmediate(r));placement.timers.at(-1)()
  const veinResult=await vein;Date.now=realNow
  assert.equal(veinResult.body.resultado.interrompida,true);assert.equal(veinCalls,2)
  assert.match(veinResult.body.resultado.message,/no total; \+1 coal/);pb.findBlock=()=>null;n++
  // Servidor remoto (28/10): bloco quebrado sem item no inventário; o drop próximo é recolhido.
  let found=1;pb.findBlock=()=>found-->0?coal:null;const calls=[]
  pb.inventory.items=()=>[{name:'stone_pickaxe',count:1}]
  pb.entities={7:{name:'item',position:{x:1,y:64,z:0,floored(){return this},distanceTo(){return 1}}}}
  pb.collectBlock={collect:async target=>{calls.push(target.name);if(target.name==='item')pb.inventory.items=()=>[{name:'stone_pickaxe',count:1},{name:'coal',count:1}]}}
  const dropped=await placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-drop',
    parent_id:'tool-collect-drop',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(dropped.code,200);assert.deepEqual(calls,['coal_ore','item'])
  assert.equal(dropped.body.resultado.sem_ganho,false);assert.match(dropped.body.resultado.message,/\+1 coal/);n++
  // Itens de outros blocos não contam como o que foi pedido (28/10: +21 sem nenhum oak_log).
  found=1;pb.entities={};pb.inventory.items=()=>[{name:'stone_pickaxe',count:1}]
  pb.collectBlock={collect:async()=>{pb.inventory.items=()=>[{name:'stone_pickaxe',count:1},{name:'dirt',count:16}]}}
  const others=await placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-others',
    parent_id:'tool-collect-others',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(others.body.resultado.sem_ganho,true);assert.match(others.body.resultado.message,/nenhum coal.*16 outro.*\(16 dirt\)/);n++
  found=1;pb.entities={};pb.inventory.items=()=>[{name:'stone_pickaxe',count:1}]
  pb.collectBlock={collect:async()=>{}}
  const lost=await placement.rpc({action:'collect',args:{name:'coal_ore',count:1,maxDistance:24},request_id:'collect-lost',
    parent_id:'tool-collect-lost',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(lost.body.resultado.sem_ganho,true);assert.match(lost.body.resultado.message,/nenhum coal entrou/);pb.findBlock=()=>null;n++
  pb.heldItem=null
  const noItem=await placement.rpc({action:'use_item',args:{},request_id:'use-empty',parent_id:'tool-use',
    entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(noItem.code,200);assert.equal(noItem.body.code,'use_preconditions')
  assert.equal(noItem.body.effect_state,'not_started');n++
  pb.heldItem={name:'crafting_table',count:1}
  Object.assign(pb.entity.position,{x:9.5,y:64,z:9.5})
  targetBlock.name='air';pb.heldItem=null
  pb.blockAt=p=>p.y===63?{name:'grass_block',boundingBox:'block',position:{x:p.x,y:p.y,z:p.z}}:targetBlock
  const empty=await placement.rpc({action:'place_block',args:{x:1,y:63,z:1,face:'up'},
    request_id:'place-empty',parent_id:'tool-empty',entity_id:'hoshino',session_id:placement.api.state().sessionId})
  assert.equal(empty.code,200);assert.equal(empty.body.effect_state,'not_started');n++

  const furnace=fixture();await furnace.connect();const fb=furnace.bots[0]
  const block={name:'furnace',position:{x:1,y:64,z:0}}
  let input=null,fuel=null,output=null,puts=0,takes=0,closes=0
  fb.findBlock=()=>block;fb.inventory.items=()=>[{name:'iron_ore',type:15,count:3},{name:'coal',type:263,count:1}]
  fb.openFurnace=async ()=>({inputItem:()=>input,fuelItem:()=>fuel,outputItem:()=>output,
    putInput:async(type,_meta,count)=>{puts++;input={type,name:'iron_ore',count}},
    putFuel:async(type,_meta,count)=>{puts++;fuel={type,name:'coal',count}},
    takeOutput:async()=>{takes++;const item=output;output=null;return item},close:()=>{closes++}})
  assert.equal(typeof furnace.api.furnaceAction,'function')
  // 28/10: o pathfinder quebrou o forno dela no caminho da coleta; bancada e forno ficam intactos.
  assert.ok(fb.movements.blocksCantBreak.has(58)&&fb.movements.blocksCantBreak.has(61));n++
  // Exerce a troca feita pelo coletor REAL; o teste antigo só conferia antes dela.
  fb.tool={}
  await CollectBlock.prototype.collect.call({bot:fb,movements:fb.collectBlock.movements,
    targets:{empty:true,appendTargets(){}},cancelTask:async()=>{}},[])
  assert.ok(fb.movements.blocksCantBreak.has(58)&&fb.movements.blocksCantBreak.has(61),
    'o coletor substituiu a proteção da bancada/forno');n++
  await furnace.api.furnaceAction('put',{input:'iron_ore',fuel:'coal',count:3,fuelCount:1})
  assert.equal(puts,2);input=null;fuel=null;output={name:'iron_ingot',count:3}
  await furnace.api.furnaceAction('take',{});assert.equal(takes,1);assert.equal(closes,2);n++
  // 29/10: sem carga própria registrada, retirar recusa antes de tirar algo, com código (não incerteza).
  output={name:'cooked_salmon',count:8}
  await assert.rejects(furnace.api.furnaceAction('take',{}),err=>err.code==='furnace_preconditions'&&/nada retirado/.test(err.message))
  assert.equal(takes,1);output=null;n++
  // 29/10: dois fornos ao alcance; retirar abre o que tem a carga dela, não o mais próximo.
  const other={name:'furnace',position:{x:3,y:64,z:0}},opened=[]
  fb.findBlock=()=>block;fb.blockAt=p=>p.x===3?other:block;fb.findBlocks=()=>[block.position,other.position]
  const realOpen=fb.openFurnace;fb.openFurnace=async bl=>{opened.push(bl.position.x);return realOpen(bl)}
  fb.inventory.items=()=>[{name:'iron_ore',type:15,count:3},{name:'coal',type:263,count:1}]
  fb.findBlock=()=>other;await furnace.api.furnaceAction('put',{input:'iron_ore',fuel:'coal',count:1,fuelCount:1})
  fb.findBlock=()=>block;input=null;fuel=null;output={name:'iron_ingot',count:1}
  await furnace.api.furnaceAction('take',{});assert.deepEqual(opened,[3,3]);output=null
  fb.findBlocks=undefined;fb.openFurnace=realOpen;fb.findBlock=()=>block;n++
  const occupied=fixture();await occupied.connect();const ob=occupied.bots[0]
  ob.findBlock=()=>block;ob.openFurnace=fb.openFurnace;input={name:'iron_ore',count:1}
  // 28/10: carne crua também assa no forno; o pedido não é recusado pelo tipo.
  input=null;fuel=null;output=null;ob.inventory.items=()=>[{name:'beef',type:363,count:3},{name:'coal',type:263,count:1}]
  const beef=await occupied.api.furnaceAction('put',{input:'beef',fuel:'coal',count:3,fuelCount:1})
  assert.equal(beef.owned_run.expectedOutput,'cooked_beef');n++
  input={name:'iron_ore',count:1};const putsBefore=puts
  await assert.rejects(occupied.api.furnaceAction('put',{input:'iron_ore',fuel:'coal',count:1}),
    err=>/ocupado/.test(err.message)&&err.code==='furnace_preconditions'&&err.details.forno.input.name==='iron_ore')
  assert.equal(puts,putsBefore);n++
  // Combustível remanescente não ocupa entrada/saída nem impede uma nova carga.
  const residual=fixture();await residual.connect();const rb=residual.bots[0]
  let rest={input:null,fuel:{name:'coal',count:12},output:null},writes=0
  rb.findBlock=()=>block;rb.inventory.items=()=>[{name:'iron_ore',type:15,count:4},{name:'coal',type:263,count:2},{name:'charcoal',type:263,count:2}]
  rb.openFurnace=async()=>({inputItem:()=>rest.input,fuelItem:()=>rest.fuel,outputItem:()=>rest.output,
    putInput:async(_type,_meta,count)=>{writes++;rest.input={name:'iron_ore',count}},
    putFuel:async(_type,_meta,count)=>{writes++;rest.fuel.count+=count},close:()=>{}})
  const reloaded=await residual.api.furnaceAction('put',{input:'iron_ore',fuel:'coal',count:4,fuelCount:1})
  assert.equal(reloaded.input.count,4);assert.equal(reloaded.fuel.count,13);assert.equal(writes,2);n++
  // Mesmo slots vazios não autorizam esquecer um lote próprio ainda sem desfecho.
  rest.input=null
  await assert.rejects(residual.api.furnaceAction('put',{input:'iron_ore',fuel:'coal',count:4,fuelCount:1}),
    e=>e.code==='furnace_preconditions'&&e.effect==='not_started')
  assert.equal(writes,2);assert.equal(residual.api.state().furnaceRuns[0].remaining,4);n++
  for(const fuelCase of [{fuel:'charcoal',stored:12,count:1},{fuel:'coal',stored:63,count:2}]) {
    const conflict=fixture();await conflict.connect();const xb=conflict.bots[0]
    let changed=0
    xb.findBlock=()=>block;xb.inventory.items=rb.inventory.items
    xb.openFurnace=async()=>({inputItem:()=>null,fuelItem:()=>({name:'coal',count:fuelCase.stored}),outputItem:()=>null,
      putInput:async()=>{changed++},putFuel:async()=>{changed++},close:()=>{}})
    await assert.rejects(conflict.api.furnaceAction('put',{input:'iron_ore',fuel:fuelCase.fuel,count:4,fuelCount:fuelCase.count}),
      e=>e.code==='furnace_preconditions'&&e.effect==='not_started')
    assert.equal(changed,0);n++
  }
  const short=fixture();await short.connect();const sb=short.bots[0]
  let shortWrites=0
  sb.findBlock=()=>block;sb.inventory.items=()=>[{name:'iron_ore',type:15,count:4}]
  sb.openFurnace=async()=>({inputItem:()=>null,fuelItem:()=>({name:'coal',count:12}),outputItem:()=>null,
    putInput:async()=>{shortWrites++},putFuel:async()=>{shortWrites++},close:()=>{}})
  await assert.rejects(short.api.furnaceAction('put',{input:'iron_ore',fuel:'coal',count:4,fuelCount:1}),
    e=>e.code==='furnace_preconditions'&&e.effect==='not_started')
  assert.equal(shortWrites,0);n++
  // A fundição pertence ao jogador/forno, não ao processo: outra ponte (sono/recarga) ainda retira.
  const files=new Map(),first=fixture(files);await first.connect();const b1=first.bots[0]
  let slot={input:null,fuel:null,output:null}
  const openShared=async ()=>({inputItem:()=>slot.input,fuelItem:()=>slot.fuel,outputItem:()=>slot.output,
    putInput:async(type,_m,count)=>{slot.input={type,name:'iron_ore',count}},putFuel:async(type,_m,count)=>{slot.fuel={type,name:'coal',count}},
    takeOutput:async()=>{const item=slot.output;slot.output=null;return item},close:()=>{}})
  b1.findBlock=()=>block;b1.openFurnace=openShared;b1.inventory.items=fb.inventory.items
  await first.api.furnaceAction('put',{input:'iron_ore',fuel:'coal',count:3,fuelCount:1})
  const owned=first.api.state().furnaceRuns
  assert.equal(owned.length,1);assert.deepEqual(owned[0].position,{x:1,y:64,z:0})
  assert.equal(owned[0].remaining,3);assert.equal(owned[0].expectedOutput,'iron_ingot');assert.ok(owned[0].depositedAt)
  assert.equal(owned[0].fuel,'coal');assert.equal(owned[0].fuelCount,1);assert.equal(owned[0].phase,undefined);n++
  const second=fixture(files);await second.connect();const b2=second.bots[0]
  b2.findBlock=()=>block;b2.openFurnace=openShared
  assert.equal(second.api.state().furnaceRuns.length,1)
  slot={input:null,fuel:null,output:{name:'iron_ingot',count:3}}
  const taken=await second.api.furnaceAction('take',{})
  assert.deepEqual(taken.taken,{name:'iron_ingot',count:3});assert.equal(second.api.state().furnaceRuns.length,0)
  assert.equal([...files.values()].at(-1),'{}');n++
  // Morte (28/10): local e itens que levava ficam no estado, com a hora em que os itens somem.
  cb.inventory.items=()=>[{name:'oak_log',count:3}];cb.health=12;cb.emit('health')
  cb.health=0;cb.emit('death')
  const death=crafting.api.state().lastDeath
  assert.deepEqual(death.items,[{name:'oak_log',count:3}]);assert.ok(death.position)
  assert.equal(Date.parse(death.itemsDespawnAt)-Date.parse(death.at),300000);n++
  // Reflexos (28/10): sufocamento cava o bloco da cabeça; monstro perto com vida alta é atacado.
  const reflexDug=[],attacks=[],controls=[];let headBlock={name:'gravel',boundingBox:'block'}
  cb.blockAt=p=>p.y===65?headBlock:{name:'air',boundingBox:'empty'}
  cb.dig=async block=>{reflexDug.push(block.name);headBlock={name:'air',boundingBox:'empty'}}
  cb.setControlState=(k,v)=>controls.push(k+':'+v);cb.attack=e=>attacks.push(e.name);cb.entities={}
  cb.health=20;cb.emit('health');cb.health=18;cb.emit('health');await tick();await tick()
  const suffocation=crafting.api.state().reflexes.find(r=>r.tipo==='sufocamento')
  assert.deepEqual(reflexDug,['gravel']);assert.ok(suffocation);assert.match(suffocation.acao,/cavei gravel/)
  assert.equal(suffocation.vida_antes,18);n++
  cb.entities={9:{name:'zombie',position:{x:1,y:64,z:0,floored(){return this}},isValid:true}}
  cb.health=17;cb.emit('health');for(let i=0;i<12;i++)await tick()
  assert.ok(attacks.includes('zombie'));assert.ok(crafting.api.state().reflexes.some(r=>r.tipo==='monstro'&&/ataquei|defendi/.test(r.acao)));n++
  cb.entities={}
  // Fácil (28/10): creeper ou grupo faz fugir; arqueiro alcança de 12 blocos; antes de lutar empunha a espada.
  const goalsSet=[];cb.pathfinder.setGoal=g=>{goalsSet.push(g);cb.pathfinder.goal=g}  // como a biblioteca: goal = objetivo atual
  cb.entities={11:{name:'creeper',position:{x:3,y:64,z:0,floored(){return this}},isValid:true}}
  cb.health=16;cb.emit('health');for(let i=0;i<8;i++)await tick()
  assert.ok(crafting.api.state().reflexes.some(r=>r.tipo==='monstro'&&/fugi de creeper/.test(r.acao)));n++
  // A fuga troca o objetivo da navegação: resultado medido, sem limpar a fuga (28/10, subida à superfície).
  const savedGoto=cb.pathfinder.goto;cb.pathfinder.goto=async()=>{const e=Error('goal changed');e.name='GoalChanged';throw e}
  cb.pathfinder.goal={fuga:'em andamento'}  // 30/10: a fuga agora é uma arrancada de 3 s; aqui ela acontece durante a caminhada
  const goalsBefore=goalsSet.length
  const interrupted=await crafting.api.gotoPoint({x:5,y:64,z:5,range:2})
  assert.match(interrupted,/interrompida pelo reflexo de sobrevivência \(monstro/);assert.equal(goalsSet.length,goalsBefore)
  cb.pathfinder.goto=savedGoto;cb.pathfinder.goal=null;n++
  // Fuga sem cavar (30/10): Movements próprios por 3 s; os compartilhados (collectBlock e demais ações) não mudam.
  crafting.api.restoreDigging(true);const mv=cb.collectBlock.movements;mv.canDig=true;mv.allow1by1towers=true;mv.scafoldingBlocks=[3,4]
  cb.entities={12:{name:'creeper',position:{x:3,y:64,z:0,floored(){return this}},isValid:true}}
  cb.health=15;cb.emit('health');for(let i=0;i<20;i++)await tick()
  const fleeMv=cb.pathfinder.movements
  assert.notEqual(fleeMv,mv);assert.equal(fleeMv.canDig,false);assert.equal(fleeMv.allow1by1towers,false);assert.deepEqual(fleeMv.scafoldingBlocks,[])
  assert.equal(mv.canDig,true);assert.deepEqual(mv.scafoldingBlocks,[3,4])  // revisão Codex: a coleta continua cavando
  assert.ok(fleeMv.blocksCantBreak===mv.blocksCantBreak)  // mesmas proibições de quebra
  crafting.api.restoreDigging(false);assert.equal(cb.pathfinder.movements,fleeMv)  // antes do prazo continua sem cavar
  // Revisão Codex: durante outro reflexo (subindo da água) não religa — setMovements soltaria o 'jump'.
  crafting.api.setReflexBusy(true);crafting.api.restoreDigging(true);assert.equal(cb.pathfinder.movements,fleeMv)
  // Revisão Codex: uma ação pedida durante o reflexo é recusada sem efeito; depois dele começa com os movimentos normais.
  const savedGoto2=cb.pathfinder.goto;let gotoAt=null
  cb.pathfinder.goto=async()=>{gotoAt=cb.pathfinder.movements;const e=Error('No path');e.name='NoPath';throw e}
  const gotoRpc=id=>crafting.rpc({action:'goto',args:{x:30,y:64,z:30,range:2},request_id:id,
    parent_id:'tool-during',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  const duringReflex=await gotoRpc('goto-during-reflex')
  assert.equal(duringReflex.code,200);assert.equal(duringReflex.body.code,'reflex_busy');assert.equal(duringReflex.body.effect_state,'not_started')
  assert.equal(gotoAt,null);assert.equal(cb.pathfinder.movements,fleeMv)
  // Revisão Codex: trava de outra sessão (reconexão) ou vencida (dig preso há mais de 30 s) não recusa.
  crafting.api.setReflexBusy({session:'sessao-antiga',since:Date.now()})
  assert.notEqual((await gotoRpc('goto-old-session')).body.code,'reflex_busy')
  crafting.api.setReflexBusy({session:crafting.api.state().sessionId,since:Date.now()-31000})
  assert.notEqual((await gotoRpc('goto-stale-reflex')).body.code,'reflex_busy')
  // (essas duas já religaram os movimentos normais; a fuga volta para medir a religação abaixo)
  cb.health=14.8;cb.emit('health');for(let i=0;i<20;i++)await tick();assert.notEqual(cb.pathfinder.movements,mv)
  let sets=cb.movementSets;crafting.api.setReflexBusy(false);await gotoRpc('goto-after-reflex')
  assert.equal(gotoAt,mv);cb.pathfinder.goto=savedGoto2
  assert.equal(cb.pathfinder.movements,mv);assert.equal(cb.movementSets,sets+1)  // religar refaz a busca (setMovements)
  // Se a coleta já pôs os Movements dela, religar não mexe (não reinicia o caminho da coleta).
  cb.health=14.5;cb.emit('health');for(let i=0;i<20;i++)await tick()
  assert.notEqual(cb.pathfinder.movements,mv);cb.pathfinder.setMovements(mv);sets=cb.movementSets
  crafting.api.restoreDigging(true);assert.equal(cb.movementSets,sets);n++
  // Arqueiro longe (57 fugas numa caverna): depois de 4 fugas em 1 min, a quinta não acontece.
  const savedSetMov=cb.pathfinder.setMovements,savedPosArcher=cb.entity.position
  cb.entity.position={x:0,y:64,z:0,floored(){return this},offset(){return this},distanceTo(p){return Math.hypot(p.x-this.x,p.z-this.z)}}
  cb.entities={13:{name:'skeleton',position:{x:10,y:64,z:0,floored(){return this}},isValid:true}}
  for(let k=0;k<5;k++){cb.health=14-k;cb.emit('health');for(let i=0;i<20;i++)await tick()}
  const archer=crafting.api.state().reflexes.filter(r=>/skeleton/.test(r.acao||''))
  assert.equal(archer.filter(r=>/^fugi de skeleton/.test(r.acao)).length,4)
  assert.match(archer.at(-1).acao,/não fugi de skeleton a 10\.0 blocos: já fugi 4 vezes em 1 min/)
  // Revisão Codex: com um zumbi colado não é "arqueiro sozinho": ela reage ao zumbi.
  const zombieHits=[];const savedAttack=cb.attack;cb.attack=e=>{zombieHits.push(e.name)}
  cb.entities={13:{name:'skeleton',position:{x:10,y:64,z:0,floored(){return this}},isValid:true},
               14:{name:'zombie',position:{x:2,y:64,z:0,floored(){return this}},isValid:true}}
  cb.health=9.5;cb.emit('health');for(let i=0;i<20;i++)await tick()
  assert.doesNotMatch(crafting.api.state().reflexes.at(-1).acao,/não fugi/)
  assert.match(crafting.api.state().reflexes.at(-1).acao,/me defendi atacando zombie/);assert.ok(zombieHits.length>0&&zombieHits.every(x=>x==='zombie'))
  cb.attack=savedAttack;crafting.api.restoreDigging(true)
  cb.entity.position=savedPosArcher;cb.entities={};cb.pathfinder.setMovements=savedSetMov;cb.health=16;cb.emit('health');n++
  // Coleta interrompida pelo reflexo: medido, sem incerteza.
  const savedBlockAt2=cb.blockAt,savedFind2=cb.findBlock
  cb.findBlock=()=>({name:'coal_ore',position:{x:2,y:64,z:0}});cb.blockAt=()=>({name:'coal_ore',boundingBox:'block'})
  cb.inventory.items=()=>[{name:'stone_pickaxe',count:1}]
  cb.collectBlock={collect:async()=>{const e=Error('The goal was changed before it could be completed!');e.name='GoalChanged';throw e}}
  const cut=await crafting.rpc({action:'collect',args:{name:'coal_ore',count:2,maxDistance:24},request_id:'collect-reflex',
    parent_id:'tool-collect-reflex',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(cut.code,200);assert.equal(cut.body.resultado.reflexo,true);assert.match(cut.body.resultado.message,/interrompida pelo reflexo/);n++
  cb.blockAt=savedBlockAt2;cb.findBlock=savedFind2
  const equipped=[];cb.equip=async item=>{equipped.push(item.name)};cb.inventory.items=()=>[{name:'iron_sword',count:1}]
  cb.entities={12:{name:'zombie',position:{x:1,y:64,z:0,floored(){return this}},isValid:true}}
  cb.health=15;cb.emit('health');for(let i=0;i<12;i++)await tick()
  assert.deepEqual(equipped,['iron_sword']);n++
  cb.entities={}
  cb.entities={};cb.entity.metadata={0:1};cb.findBlock=()=>null;cb.health=14;cb.emit('health');for(let i=0;i<8;i++)await tick()
  assert.ok(crafting.api.state().reflexes.some(r=>r.tipo==='fogo'&&/fogo/.test(r.acao)));cb.entity.metadata={0:0};n++
  cb.health=0;cb.emit('death')
  const lastDeathReflex=crafting.api.state().reflexes.at(-1)
  assert.equal(lastDeathReflex.tipo,'morte');assert.equal(lastDeathReflex.causa_provavel,'fogo');n++  // último perigo antes da morte
  // Matar um mob (pedido humano 27/10): persegue e golpeia; a morte vem do evento; jogador nunca é alvo.
  // 30/10 (pedido humano): a presa não dispara a fuga — a aranha caçada morde e ela continua a caça.
  const spider={id:4,name:'spider',type:'mob',position:{x:1,y:64,z:0,floored(){return this}},isValid:true},spiderHits=[]
  const reflexesBefore=crafting.api.state().reflexes.length
  cb.entities={4:spider};cb.attack=e=>{spiderHits.push(e.name);if(spiderHits.length===1){cb.health=13;cb.emit('health')}
    if(spiderHits.length===3){cb.emit('entityDead',spider);delete cb.entities[4]}}
  const spiderHunt=await crafting.rpc({action:'attack',args:{target:'spider',maxDistance:16,hunt:true},request_id:'hunt-spider',
    parent_id:'tool-hunt-spider',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(spiderHunt.code,200);assert.equal(spiderHunt.body.resultado.morto,true)
  assert.ok(!crafting.api.state().reflexes.slice(reflexesBefore).some(r=>/fugi de spider/.test(r.acao||'')))
  cb.health=20;cb.emit('health');n++
  const cow={id:3,name:'cow',type:'mob',position:{x:1,y:64,z:0,floored(){return this}}},huntHits=[]
  cb.entities={3:cow};cb.attack=e=>{huntHits.push(e.name);if(huntHits.length===2){cb.emit('entityDead',cow);delete cb.entities[3]}}
  const hunt=await crafting.rpc({action:'attack',args:{target:'cow',maxDistance:16,hunt:true},request_id:'hunt-cow',
    parent_id:'tool-hunt',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(hunt.code,200);assert.equal(hunt.body.resultado.morto,true);assert.equal(hunt.body.resultado.golpes,2)
  assert.deepEqual(crafting.api.state().kills.map(k=>k.name),['spider','cow']);n++  // a aranha caçada logo acima
  // Caça em série (pedido humano 29/10): quantidade pedida, um do mesmo tipo depois do outro.
  const herd=[5,6,7].map(id=>({id,name:'cow',type:'mob',position:{x:1+id/10,y:64,z:0,floored(){return this}}}))
  cb.entities=Object.fromEntries(herd.map(c=>[c.id,c]));cb.health=20  // vida baixa encerra a série
  cb.attack=e=>{cb.emit('entityDead',e);delete cb.entities[e.id]}
  const serial=await crafting.rpc({action:'attack',args:{target:'cow',maxDistance:16,hunt:true,count:2},request_id:'hunt-herd',
    parent_id:'tool-hunt-herd',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(serial.body.resultado.mortos,2);assert.equal(serial.body.resultado.pedidos,2)
  assert.equal(serial.body.resultado.abatidos.length,2);assert.match(serial.body.resultado.message,/^2\/2 cow morreram/)
  assert.equal(Object.keys(cb.entities).length,1);n++
  const lone=await crafting.rpc({action:'attack',args:{target:'cow',maxDistance:16,hunt:true,count:3},request_id:'hunt-lone',
    parent_id:'tool-hunt-lone',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(lone.body.resultado.mortos,1);assert.match(lone.body.resultado.message,/Não havia outro cow/);n++
  cb.entities={4:{id:4,name:'player',type:'player',username:'ATO',position:{x:1,y:64,z:0,floored(){return this}}}}
  const pvp=await crafting.rpc({action:'attack',args:{target:'ATO',maxDistance:16,hunt:true},request_id:'hunt-player',
    parent_id:'tool-hunt-player',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(pvp.body.code,'attack_preconditions');assert.equal(pvp.body.effect_state,'not_started');cb.entities={};n++
  const gone=await crafting.rpc({action:'attack',args:{target:'spider',maxDistance:5,entityId:99},request_id:'attack-gone',
    parent_id:'tool-attack-gone',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.equal(gone.body.code,'attack_preconditions');assert.equal(gone.body.effect_state,'not_started');n++
  // Reflexo de fome (28/10): vida 4, fome 2 e pão no inventário: come sem esperar o modelo.
  cb.entities={};cb.food=2;cb.inventory.items=()=>[{name:'bread',count:20}];cb.equip=async()=>{};cb.consume=async()=>{cb.food=7}
  cb.health=10;cb.emit('health');cb.health=4;cb.emit('health');for(let i=0;i<8;i++)await tick()
  assert.ok(crafting.api.state().reflexes.some(r=>r.tipo==='fome'&&/comi bread \(fome 2 → 7\/20\)/.test(r.acao)));n++
  // O reflexo devolve à mão o que ela segurava (28/10: colocou a picareta em vez da bancada).
  const held=[];cb.heldItem={name:'crafting_table'};cb.food=2;cb.inventory.items=()=>[{name:'bread',count:5},{name:'crafting_table',count:1}]
  cb.equip=async item=>{held.push(item.name);cb.heldItem={name:item.name}};cb.consume=async()=>{cb.food=8}
  cb.health=11;cb.emit('health');cb.health=5;cb.emit('health');for(let i=0;i<10;i++)await tick()
  assert.deepEqual(held.slice(-2),['bread','crafting_table']);n++
  // Revisão Codex: reflexo vencido (comer travado por mais de 30 s) para sem devolver o item — a mão já mudou depois.
  let finishEat;held.length=0;cb.heldItem={name:'crafting_table'};cb.food=2
  cb.consume=()=>new Promise(r=>{finishEat=()=>{cb.food=8;r()}})
  cb.health=12;cb.emit('health');cb.health=6;cb.emit('health');for(let i=0;i<6;i++)await tick()
  assert.deepEqual(held,['bread']);crafting.api.ageReflex(31000);cb.heldItem={name:'torch'}
  finishEat();for(let i=0;i<10;i++)await tick()
  assert.deepEqual(held,['bread']);assert.equal(cb.heldItem.name,'torch')
  assert.match(crafting.api.state().reflexes.at(-1).acao,/interrompido: o reflexo passou do prazo/);n++
  // Uma restauração já iniciada pode cruzar o prazo e sobrescrever o equip da próxima RPC.
  let finishRestore
  const handItems = ['bread', 'crafting_table', 'torch'].map(name => ({name, count: 1}))
  cb.heldItem = handItems[1]
  cb.food = 2
  cb.inventory.items = () => handItems
  cb.consume = async () => { cb.food = 8 }
  cb.equip = item => item.name === 'crafting_table'
    ? new Promise(resolve => { finishRestore = () => { cb.heldItem = item; resolve() } })
    : Promise.resolve().then(() => { cb.heldItem = item })
  cb.health = 12; cb.emit('health'); cb.health = 6; cb.emit('health')
  for (let i = 0; i < 8; i++) await tick()
  assert.equal(typeof finishRestore, 'function')
  crafting.api.ageReflex(31000)
  const equipTorch = request_id => crafting.rpc({action:'equip', args:{name:'torch'}, request_id,
    parent_id:'tool-restore-race', entity_id:'hoshino', session_id:crafting.api.state().sessionId})
  const overlapping = await equipTorch('equip-during-restoration')
  assert.equal(overlapping.body.code, 'reflex_busy')
  assert.equal(overlapping.body.effect_state, 'not_started')
  finishRestore()
  for (let i = 0; i < 8; i++) await tick()
  const afterRestore = await equipTorch('equip-after-restoration')
  assert.equal(afterRestore.body.ok, true)
  assert.equal(cb.heldItem.name, 'torch')
  n++
  // Comer (28/10): equipa a comida e consome, medindo a fome.
  cb.food=3;cb.inventory.items=()=>[{name:'cooked_beef',count:2}];cb.equip=async()=>{};cb.consume=async()=>{cb.food=11}
  const ate=await crafting.rpc({action:'use_item',args:{name:'cooked_beef'},request_id:'eat',parent_id:'tool-eat',
    entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.match(ate.body.resultado,/Comi cooked_beef: fome 3 → 11\/20/);n++
  // Água (28/10): caçando salmão, ficava na água afundando; depois da caça vai para a terra firme.
  const fish={id:5,name:'salmon',type:'mob',position:{x:1,y:60,z:0,floored(){return this}}},waterGoals=[]
  cb.entities={5:fish};cb.entity.isInWater=true;cb.pathfinder.setGoal=g=>waterGoals.push(g)
  cb.findBlock=opts=>opts&&opts.useExtraInfo?{position:{x:4,y:62,z:0,offset(){return this}}}:null
  cb.attack=e=>{cb.emit('entityDead',fish);delete cb.entities[5]}
  const swim=await crafting.rpc({action:'attack',args:{target:'salmon',maxDistance:16,hunt:true},request_id:'hunt-fish',
    parent_id:'tool-hunt-fish',entity_id:'hoshino',session_id:crafting.api.state().sessionId})
  assert.match(swim.body.resultado.message,/Depois nadei para cima e estou indo para terra firme em \(4,63,0\)/);cb.entity.isInWater=false;n++
  // Afogamento (29/10): cabeça presa na água e bloco tampando a subida: cava e diz que continua na água.
  const drownDug=[];let lid={name:'dirt',boundingBox:'block'}
  const savedBlockAt3=cb.blockAt,savedFind3=cb.findBlock,savedDig3=cb.dig
  cb.blockAt=p=>p.y===65?{name:'water',boundingBox:'empty'}:p.y===66?lid:{name:'stone',boundingBox:'block'}
  cb.dig=async block=>{drownDug.push(block.name);lid={name:'water',boundingBox:'empty'}}
  cb.findBlock=()=>null;cb.entities={};cb.entity.isInWater=true;cb.oxygenLevel=6
  cb.health=9;cb.emit('health');cb.health=7;cb.emit('health');for(let i=0;i<60;i++)await tick()
  const drown=crafting.api.state().reflexes.filter(r=>r.tipo==='afogamento').at(-1)
  assert.deepEqual(drownDug,['dirt']);assert.match(drown.acao,/cavei dirt que tampava a subida/)
  assert.match(drown.acao,/continuo com a cabeça na água em .*ar 6\/20/);assert.doesNotMatch(drown.acao,/estou indo|fui para/)
  cb.blockAt=savedBlockAt3;cb.findBlock=savedFind3;cb.dig=savedDig3;cb.entity.isInWater=false;n++
  cb.inventory.slots=[];cb.inventory.slots[5]={name:'diamond_helmet',count:1}
  assert.equal(crafting.api.state().equipment.head.name,'diamond_helmet');n++
  // Olhar (30/10, pedido humano): a cabeça acompanha quem falou com ela; andando ou caçando, não briga com a ação.
  const eyes=fixture();await eyes.connect();const eb=eyes.bots[0];const looks=[]
  eb.lookAt=async p=>{looks.push(p)};eb.pathfinder.isMoving=()=>false
  const pos=(x,dist)=>({x,y:64,z:0,offset(dx,dy,dz){return {x:this.x+dx,y:this.y+dy,z:this.z+dz}},distanceTo(){return dist}})
  eb.entity.position={x:0,y:64,z:0,floored(){return this},distanceTo(p){return p.dist??3}}
  const atoEnt={position:{...pos(3,3),dist:3},height:1.8},farEnt={position:{...pos(12,12),dist:12},height:1.8}
  eb.players={ATO:{entity:atoEnt},Longe:{entity:farEnt}}
  eyes.api.gaze(eb);assert.equal(looks.at(-1).x,3);assert.ok(Math.abs(looks.at(-1).y-65.62)<0.01)  // mais perto (≤8)
  eb.emit('message',playerMessage('Longe','Lilith, me ajuda?'),'chat')  // quem falou no último minuto, até 16 blocos
  eyes.api.gaze(eb);assert.equal(looks.at(-1).x,12)
  const looksBefore=looks.length;eb.pathfinder.isMoving=()=>true;eyes.api.gaze(eb);assert.equal(looks.length,looksBefore)  // andando: não mexe
  eb.pathfinder.isMoving=()=>false;eb.targetDigBlock={name:'stone'};eyes.api.gaze(eb);assert.equal(looks.length,looksBefore)  // cavando
  eb.targetDigBlock=null
  // Revisão Codex: com outro comando em execução (equipar, colocar, forno...) o olhar não mexe, nem seguindo alguém.
  const rpcEyes=p=>eyes.rpc({...p,parent_id:'tool-eyes',entity_id:'hoshino',session_id:eyes.api.state().sessionId})
  await rpcEyes({action:'follow',args:{username:'ATO',distance:2},request_id:'eyes-follow'})
  eyes.api.gaze(eb);assert.equal(looks.at(-1).x,3)  // seguindo e livre: olha quem segue
  eb.inventory.items=()=>[{name:'stick',count:1}];eb.equip=()=>new Promise(()=>{})
  const equipHang=rpcEyes({action:'equip',args:{name:'stick',destination:'hand'},request_id:'eyes-equip'})
  for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r))
  const looksBusy=looks.length;eyes.api.gaze(eb);assert.equal(looks.length,looksBusy);equipHang.catch(()=>{});n++
  // Rastrear (30/10, pedido humano): com 40 morcegos perto, a aranha a 40 blocos entra pela mais próxima de cada espécie.
  const track=fixture();await track.connect();const tb=track.bots[0]
  const at=(x)=>({x,y:64,z:0,floored(){return {x:Math.floor(this.x),y:64,z:0}},distanceTo(p){return Math.abs(p.x-this.x)},offset(){return this}})
  tb.entity.position=at(0)
  const bats=Object.fromEntries(Array.from({length:40},(_,i)=>[100+i,{id:100+i,name:'bat',type:'mob',position:at(1+i*0.5)}]))
  tb.entities={...bats,9:{id:9,name:'spider',type:'mob',position:at(40)},[tb.entity.id||'me']:tb.entity}
  const listed=track.api.state().nearbyEntities
  assert.ok(listed.filter(e=>e.name==='bat').length<=32);assert.ok(listed.some(e=>e.name==='spider'&&e.longe===true&&e.distance===40));n++
  // Explorar: anda para o norte e para assim que a aranha aparece a até 24 blocos.
  // A aranha está a 27 (fora dos 24); andando 3 blocos ela entra no alcance e a exploração para.
  tb.entities={9:{id:9,name:'spider',type:'mob',position:at(27)}};let walkedTo=null
  tb.pathfinder.goto=goal=>{walkedTo=goal;tb.entity.position=at(3);return new Promise(()=>{})}
  const explored=await track.rpc({action:'explore',args:{direction:'norte',lookFor:['spider'],blocks:40},request_id:'explore-1',
    parent_id:'tool-explore',entity_id:'hoshino',session_id:track.api.state().sessionId})
  assert.ok(walkedTo);assert.match(explored.body.resultado,/Encontrei spider a 24\.0 blocos em \(27, 64, 0\) depois de andar 3 blocos para o norte/)
  // Sem nada: anda até o fim e diz até onde foi; parada no lugar diz que ficou presa.
  tb.entities={};tb.entity.position=at(0);tb.pathfinder.goto=async()=>{}
  const nothing=await track.rpc({action:'explore',args:{direction:'sul',lookFor:['spider']},request_id:'explore-2',
    parent_id:'tool-explore',entity_id:'hoshino',session_id:track.api.state().sessionId})
  assert.match(nothing.body.resultado,/Andei 0 blocos para o sul .* e não vi spider; fiquei presa/)
  // Revisão Codex: se o reflexo trocou o objetivo por uma fuga, o fim da exploração não a apaga.
  const flee={fuga:true};let clearedFlee=0,fleeing=false;tb.pathfinder.setGoal=g=>{if(g===null&&fleeing)clearedFlee++}
  tb.pathfinder.goto=async()=>{fleeing=true;tb.pathfinder.goal=flee};tb.entity.position=at(0)
  await track.rpc({action:'explore',args:{direction:'leste',lookFor:['spider']},request_id:'explore-flee',
    parent_id:'tool-explore',entity_id:'hoshino',session_id:track.api.state().sessionId})
  assert.equal(clearedFlee,0);assert.equal(tb.pathfinder.goal,flee);tb.pathfinder.goal=undefined
  const badDir=await track.rpc({action:'explore',args:{direction:'cima',lookFor:['spider']},request_id:'explore-3',
    parent_id:'tool-explore',entity_id:'hoshino',session_id:track.api.state().sessionId})
  assert.equal(badDir.body.code,'explore_preconditions');n++
  // Caça sem alcançar (30/10): presa 18 blocos abaixo, ela sem picareta; o recibo diz onde e o porquê provável.
  const ub=track.bots[0];ub.entity.position={x:0,y:41,z:0,floored(){return this},distanceTo(){return 18}};ub.inventory.items=()=>[]
  const deep={position:{x:1,y:23,z:0,floored(){return {x:1,y:23,z:0}}}}
  assert.match(track.api.unreachable(ub,deep),/Ele estava em \(1, 23, 0\), 18 blocos abaixo de você; você está sem picareta/)
  ub.inventory.items=()=>[{name:'stone_pickaxe',count:1}]
  assert.doesNotMatch(track.api.unreachable(ub,deep),/sem picareta/);n++
  console.log(`Minecraft bridge: ${n} regressões passaram (VM/bot fake; não Minecraft real).`)
}
run().catch(error=>{console.error(error);process.exitCode=1})
