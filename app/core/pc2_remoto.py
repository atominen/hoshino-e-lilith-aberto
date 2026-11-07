"""PC2 como corpo remoto das entidades (pedido humano 06/11).

O cérebro fica no PC1. O painel da Central rodando no PC2 faz três coisas pelo backend do PC1:
- manda os **sentidos** do PC2 a cada ~10 s: janela ativa, apps abertos, mídia, tempo sem teclado/mouse e
  carga. Vão para o estado do mundo com prefixo ``pc2.``;
- **executa comandos** que as entidades pedem com ``executar_no_pc2``, só se a pessoa marcou a permissão no
  próprio PC2;
- manda as **cópias** (Ctrl+C) com a origem.

A fila de comandos é um SQLite em ``compartilhado/runtime`` (local ao PC1). A entidade enfileira e espera; o
painel reivindica, executa e devolve. Um comando reivindicado e não concluído nunca é repetido sozinho: o
resultado fica incerto.
"""
from __future__ import annotations

import contextlib
import contextvars
import shlex
import sqlite3
import time
import re
import uuid
from pathlib import Path

MAQUINA = 'pc2'
HEARTBEAT_TTL = 15.0      # painel some se não pergunta por comandos há 15 s
CLAIM_WAIT = 10.0         # entidade espera até 10 s o painel pegar o pedido
MAX_TIMEOUT = 300
MAX_OUTPUT = 64 * 1024
SENSE_TTL = 30
SENSE_KEYS = {'janela_ativa': 'desktop.active_window', 'janelas': 'desktop.windows', 'midia': 'desktop.media',
              'ociosidade_x11': 'desktop.idle_seconds', 'load1': 'system.load1',
              'memoria_usada_pct': 'system.memory_used_pct', 'disco_livre_gb': 'system.disk_free_gb'}


# De qual PC veio a mensagem deste turno ('pc1'/'pc2'); ferramentas usam como padrão de "onde fazer".
ORIGEM_TURNO = contextvars.ContextVar('origem_turno', default=None)
TIPOS = {'shell', 'tela'}


def _db_path(root):
    return Path(root) / 'compartilhado/runtime/pc2_comandos.sqlite3'


@contextlib.contextmanager
def _conn(root):
    path = _db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('''CREATE TABLE IF NOT EXISTS comandos (
            id TEXT PRIMARY KEY, maquina TEXT NOT NULL, entidade TEXT NOT NULL, comando TEXT NOT NULL,
            timeout INTEGER NOT NULL, status TEXT NOT NULL, criado REAL NOT NULL, iniciado REAL, terminado REAL,
            codigo INTEGER, saida TEXT, erro TEXT)''')
        conn.execute('CREATE TABLE IF NOT EXISTS painel (maquina TEXT PRIMARY KEY, visto REAL NOT NULL, '
                     'permitido INTEGER NOT NULL)')
        # 06/11 (noite): pedidos de tela e permissão separada para ver a tela.
        if 'tipo' not in {r[1] for r in conn.execute('PRAGMA table_info(comandos)')}:
            conn.execute("ALTER TABLE comandos ADD COLUMN tipo TEXT NOT NULL DEFAULT 'shell'")
        if 'permitido_tela' not in {r[1] for r in conn.execute('PRAGMA table_info(painel)')}:
            conn.execute('ALTER TABLE painel ADD COLUMN permitido_tela INTEGER NOT NULL DEFAULT 0')
        yield conn
    finally:
        conn.close()


def painel(root, maquina=MAQUINA, now=None):
    """Estado do painel remoto: online (perguntou há pouco) e se a pessoa permitiu comandos lá."""
    now = time.time() if now is None else now
    with _conn(root) as conn:
        row = conn.execute('SELECT visto, permitido, permitido_tela FROM painel WHERE maquina=?', (maquina,)).fetchone()
    if not row:
        return dict(online=False, permitido=False, permitido_tela=False, visto=None)
    return dict(online=now - row['visto'] <= HEARTBEAT_TTL, permitido=bool(row['permitido']),
                permitido_tela=bool(row['permitido_tela']), visto=row['visto'])


def enfileirar(root, entidade, comando, timeout, maquina=MAQUINA, now=None, tipo='shell'):
    now = time.time() if now is None else now
    if tipo not in TIPOS:
        raise ValueError('Tipo de pedido do PC2 inválido.')
    ident = 'pc2-' + uuid.uuid4().hex[:10]
    with _conn(root) as conn:
        conn.execute('INSERT INTO comandos (id, maquina, entidade, comando, timeout, status, criado, tipo) '
                     'VALUES (?,?,?,?,?,?,?,?)', (ident, maquina, entidade, comando, int(timeout), 'pendente', now, tipo))
    return ident


def proximo(root, maquina=MAQUINA, *, permitido, permitido_tela=False, now=None):
    """Chamado pelo painel a cada ~2 s: registra que está vivo e reivindica o pedido mais antigo, se permitido.

    Pedido pendente há mais de CLAIM_WAIT expira sem executar (a entidade já recebeu "não executado")."""
    now = time.time() if now is None else now
    with _conn(root) as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('INSERT INTO painel (maquina, visto, permitido, permitido_tela) VALUES (?,?,?,?) '
                     'ON CONFLICT(maquina) DO UPDATE SET visto=excluded.visto, permitido=excluded.permitido, '
                     'permitido_tela=excluded.permitido_tela', (maquina, now, 1 if permitido else 0, 1 if permitido_tela else 0))
        conn.execute("UPDATE comandos SET status='expirado', terminado=? WHERE maquina=? AND status='pendente' "
                     "AND criado<?", (now, maquina, now - CLAIM_WAIT))
        tipos = [t for t, ok in (('shell', permitido), ('tela', permitido_tela)) if ok]
        row = None
        if tipos:
            row = conn.execute("SELECT * FROM comandos WHERE maquina=? AND status='pendente' AND tipo IN (%s) "
                               "ORDER BY criado LIMIT 1" % ','.join('?' * len(tipos)), (maquina, *tipos)).fetchone()
            if row:
                conn.execute("UPDATE comandos SET status='executando', iniciado=? WHERE id=?", (now, row['id']))
        conn.execute('COMMIT')
    return None if row is None else dict(id=row['id'], comando=row['comando'], timeout=row['timeout'],
                                          entidade=row['entidade'], tipo=row['tipo'])


def concluir(root, ident, codigo, saida, erro=None, now=None):
    now = time.time() if now is None else now
    if not isinstance(ident, str) or not ident.startswith('pc2-'):
        raise ValueError('Pedido do PC2 inválido.')
    if codigo is not None and type(codigo) is not int:
        raise ValueError('Código de saída inválido.')
    saida = str(saida or '')[-MAX_OUTPUT:]
    with _conn(root) as conn:
        cur = conn.execute("UPDATE comandos SET status=?, terminado=?, codigo=?, saida=?, erro=? "
                           "WHERE id=? AND status='executando'",
                           ('erro' if erro else 'concluido', now, codigo, saida, (str(erro)[:300] if erro else None), ident))
        if cur.rowcount != 1:
            raise ValueError('Esse pedido não está em execução no PC2.')
    return dict(id=ident, recorded=True)


def consultar(root, ident):
    with _conn(root) as conn:
        row = conn.execute('SELECT * FROM comandos WHERE id=?', (ident,)).fetchone()
    return dict(row) if row else None


def formatar(row) -> str:
    """Mesmo cabeçalho do execute_command ("[... | saída N]") para o controlador classificar."""
    if not row:
        return 'Erro: pedido do PC2 não encontrado.'
    if row['status'] == 'concluido':
        saida = (row['saida'] or '').strip() or '(sem saída)'
        return f"[PC2 | {row['comando'][:80]} | saída {row['codigo']}]\n{saida}"
    if row['status'] == 'erro':
        return f"Erro: o PC2 não conseguiu rodar o comando ({row['erro']})."
    if row['status'] == 'expirado':
        return 'Falha: o painel do PC2 não pegou o pedido a tempo; o comando NÃO foi executado.'
    return (f"RESULTADO_INCERTO: o comando {row['id']} começou no PC2 e ainda não terminou; não repetir "
            f"automaticamente. Para ver o resultado depois, chame executar_no_pc2 com id={row['id']}.")


def executar(root, entidade, comando, timeout=30, *, sleep=time.sleep, now=time.time, tipo='shell') -> str:
    """O lado da entidade: enfileira, espera o painel pegar e o resultado. Nunca reenvia."""
    estado = painel(root, now=now())
    if not estado['online']:
        return 'Falha: o painel do PC2 está fechado agora; não existe como fazer isso lá.'
    if tipo == 'shell' and not estado['permitido']:
        return ('Falha: no PC2 a permissão "Permitir que as entidades abram e executem coisas neste PC" está '
                'desligada; peça para a pessoa ligar em Configurações no painel do PC2.')
    if tipo == 'tela' and not estado['permitido_tela']:
        return ('Falha: no PC2 a permissão "Permitir que as entidades vejam a tela deste PC" está desligada; '
                'peça para a pessoa ligar em Configurações no painel do PC2.')
    timeout = max(1, min(int(timeout or 30), MAX_TIMEOUT))
    ident = enfileirar(root, entidade, comando, timeout, now=now(), tipo=tipo)
    limite = now() + CLAIM_WAIT + timeout + 5
    while now() < limite:
        row = consultar(root, ident) or {}
        if row.get('status') in {'concluido', 'erro', 'expirado'}:
            return formatar(row)
        if row.get('status') == 'pendente' and now() - row['criado'] > CLAIM_WAIT:
            with _conn(root) as conn:
                conn.execute("UPDATE comandos SET status='expirado', terminado=? WHERE id=? AND status='pendente'",
                             (now(), ident))
            return formatar(consultar(root, ident) or {})
        sleep(0.3)
    return formatar(consultar(root, ident) or {})


def abrir(root, entidade, alvo, **kw) -> str:
    """Abre um endereço (navegador padrão do PC2) ou um aplicativo pelo nome, no PC2."""
    alvo = str(alvo or '').strip()
    if not alvo:
        return 'Erro: diga o que abrir (endereço ou nome do aplicativo).'
    if alvo.startswith(('http://', 'https://')):
        comando = 'xdg-open ' + shlex.quote(alvo)
    elif re.fullmatch(r'[\w.+-]{1,60}', alvo):
        nome = shlex.quote(alvo)
        comando = (f'if command -v {nome} >/dev/null; then setsid -f {nome} >/dev/null 2>&1; '
                   f'else gtk-launch {nome} >/dev/null 2>&1 || {{ echo "aplicativo não encontrado: {alvo}"; exit 127; }}; fi')
    else:
        return 'Erro: use um endereço http(s) ou o nome do aplicativo (ex.: firefox, thunar).'
    return executar(root, entidade, comando, 20, **kw)


def capturar_tela(root, entidade, **kw):
    """Pede ao painel do PC2 um print da tela. Devolve (caminho, None) ou (None, mensagem de falha)."""
    texto = executar(root, entidade, 'tela', 20, tipo='tela', **kw)
    m = re.match(r'\[PC2 \| tela \| saída 0\]\n(\S+\.png)$', texto)
    return (m.group(1), None) if m and Path(m.group(1)).is_file() else (None, texto)


def guardar_tela(root, ident, data: bytes) -> dict:
    """Print enviado pelo painel do PC2 para um pedido 'tela' em execução."""
    row = consultar(root, ident)
    if not row or row.get('tipo') != 'tela' or row.get('status') != 'executando':
        raise ValueError('Esse pedido de tela não está em execução no PC2.')
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) > 16 * 1024 ** 2:
        raise ValueError('O print do PC2 deve ser PNG de até 16 MiB.')
    pasta = Path(root) / 'compartilhado/runtime/pc2_telas'
    pasta.mkdir(parents=True, exist_ok=True)
    for antigo in sorted(pasta.glob('*.png'))[:-20]:  # guarda só os 20 prints mais recentes
        antigo.unlink(missing_ok=True)
    destino = pasta / f'{time.strftime("%Y%m%d-%H%M%S")}-{ident}.png'
    destino.write_bytes(data)
    return concluir(root, ident, 0, str(destino))


def contexto_origem(maquina, root=None) -> str:
    """Linha de contexto do turno: onde a pessoa está e onde fazer o que ela pedir."""
    if maquina == 'pc2':
        return ('[ONDE A PESSOA ESTÁ] Esta mensagem veio do painel no PC2. Pedido de abrir, ver ou fazer algo no '
                'computador vale no PC2 (abrir_no_pc2, executar_no_pc2, observar_tela com maquina=pc2), a não ser '
                'que ela diga PC1. O navegador controlado (browser_*) e execute_command rodam no PC1: use-os para '
                'pesquisar e achar endereços, e abra o resultado no PC2.')
    if maquina == 'pc1':
        return ('[ONDE A PESSOA ESTÁ] Esta mensagem veio da Central no PC1. Pedido de abrir ou fazer algo vale no PC1, '
                'a não ser que ela diga PC2 (aí use as ferramentas do PC2, se o painel de lá estiver ligado).')
    return ''


def guardar_sentidos(estado, *, store=None, maquina=MAQUINA, now=None):
    """Sentidos enviados pelo painel do PC2 → estado do mundo (``pc2.desktop.*``, ``pc2.system.*``)."""
    if not isinstance(estado, dict):
        raise ValueError('Sentidos inválidos.')
    from core import world_state
    store = store or world_state.Store()
    now = time.time() if now is None else now
    gravados = []
    for origem, chave in SENSE_KEYS.items():
        if origem not in estado:
            continue
        valor = estado[origem]
        if origem == 'janela_ativa':
            valor = str(valor or '')[:160] or None
        elif origem == 'janelas':
            valor = [str(v)[:100] for v in valor[:20]] if isinstance(valor, list) else None
        elif origem == 'midia':
            valor = {k: str(v)[:100] for k, v in valor.items()} if isinstance(valor, dict) and valor else None
        elif not isinstance(valor, (int, float)) or isinstance(valor, bool):
            valor = None
        store.observe(f'{maquina}.{chave}', valor, source=f'painel_{maquina}', ttl=SENSE_TTL, observed_at=now)
        gravados.append(chave)
    store.observe(f'{maquina}.panel.online', True, source=f'painel_{maquina}', ttl=SENSE_TTL, observed_at=now)
    return dict(saved=True, keys=gravados)


def sentidos(values) -> dict:
    """Recorte dos valores frescos do estado do mundo que vieram do PC2 (vazio se o painel sumiu)."""
    if not values.get(f'{MAQUINA}.panel.online'):
        return {}
    out = {origem: values.get(f'{MAQUINA}.{chave}') for origem, chave in SENSE_KEYS.items()
           if values.get(f'{MAQUINA}.{chave}') is not None}
    return out


def descrever(d: dict) -> str:
    if not d:
        return ''
    partes = []
    if d.get('janela_ativa'):
        partes.append(f"na frente: {d['janela_ativa']}")
    if d.get('janelas'):
        partes.append('abertos: ' + ', '.join(d['janelas'][:8]))
    idle = d.get('ociosidade_x11')
    if isinstance(idle, (int, float)) and idle >= 0:
        partes.append('em uso agora' if idle < 60 else f'parado há {int(idle // 60)} min')
    if d.get('midia', {}).get('titulo'):
        partes.append(f"tocando: {d['midia']['titulo']}")
    return 'PC2 (painel da pessoa) — ' + '; '.join(partes) if partes else ''
