"""Pedido humano 30/10: quando a entidade precisa da GPU e falta VRAM, fecha o app aberto por último que a ocupa.

Chamado só por gpu_resource.prepare_residency, sob a manutenção exclusiva do RM (sem compute ativo), depois de
liberar todos os pesos ociosos do projeto e com RAM para carregar. Um app por pedido: entre os apps que liberam
sozinhos o que falta na placa medida, o aberto por último. Nunca a sessão gráfica, terminais com shell aberto,
editores, o daemon do modelo, processos do projeto ou de outro usuário; dado de /proc incompleto também protege.
Pede para fechar (SIGTERM por pidfd, como fechar a janela); não força (SIGKILL) nem repete se o app não sair.
Ligado em compartilhado/config/gpu.json: "close_last_app_on_pressure": true; "protected_apps": [nomes extras].
"""
import json
import os
import re
import select
import signal
import subprocess
import time
from pathlib import Path

import config
from core import diagnostics, gpu_metrics

MIB = 1024 ** 2
MIN_APP_BYTES = 64 * MIB
OWNERS = {'llm', 'vision'}
# Fechá-los derruba a área de trabalho, um terminal (com Codex/Claude rodando), um editor ou a própria entidade.
PROTECTED = {'Xorg', 'Xwayland', 'cinnamon', 'cinnamon-session', 'cinnamon-launcher', 'csd-xsettings', 'muffin',
             'gnome-shell', 'mutter', 'kwin_x11', 'kwin_wayland', 'plasmashell', 'xfwm4', 'xfce4-panel', 'nemo-desktop',
             'gnome-terminal-server', 'xfce4-terminal', 'konsole', 'tilix', 'terminator', 'kitty', 'alacritty',
             'wezterm', 'wezterm-gui', 'foot', 'ptyxis', 'kgx', 'xterm', 'urxvt', 'code', 'codium', 'cursor',
             'ollama', 'llama-server', 'systemd', 'gdm', 'lightdm', 'pipewire', 'wireplumber', 'pulseaudio',
             'codex', 'claude'}
# Revisão Codex: agente sem terminal (o app do ChatGPT roda "codex app-server"; Claude Code instalado pelo npm roda
# em node) também protege o app inteiro.
AGENT_CMD = re.compile(r'(?:^|[/\s])(?:codex|claude)(?:\s|$)|claude-code|@anthropic-ai/|@openai/codex', re.IGNORECASE)


class ProcInconclusive(OSError):
    """Um processo do usuário não pôde ser lido: sem a árvore inteira não dá para provar que é seguro fechar."""
UNITS = {'': 1, 'B': 1, 'KiB': 1024, 'MiB': MIB, 'GiB': 1024 * MIB}


def settings():
    try:
        data = json.loads((Path(config.RAIZ) / 'compartilhado/config/gpu.json').read_text())
    except (OSError, ValueError):
        data = {}
    extra = data.get('protected_apps') if isinstance(data, dict) else None
    return dict(enabled=isinstance(data, dict) and data.get('close_last_app_on_pressure') is True,
                protected=PROTECTED | {str(n) for n in extra if isinstance(n, str)} if isinstance(extra, list) else PROTECTED)


def gpu_pdev(metrics):
    """Endereço PCI da placa que as métricas mediram (ex.: 0000:03:00.0)."""
    device = metrics.get('device')
    return os.path.basename(os.path.realpath(device)) if device else None


def _start(proc_root, pid):
    try:
        stat = (Path(proc_root) / str(pid) / 'stat').read_text()
        return int(stat[stat.rindex(')') + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def vram_by_process(proc_root='/proc', pdev=None):
    """{pid: (starttime, bytes)} pelo fdinfo do DRM, só da placa pdev; um cliente (drm-client-id) conta uma vez.
    O starttime lido antes e depois amarra a amostra ao processo (revisão Codex: PID reutilizado no meio)."""
    seen, usage = set(), {}
    for entry in Path(proc_root).iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        before = _start(proc_root, pid)
        try:
            fds = list((entry / 'fdinfo').iterdir())
        except OSError:
            continue
        used = 0
        for fd in fds:
            try:
                text = fd.read_text()
            except OSError:
                continue
            if 'drm-memory-vram' not in text:
                continue
            fields = {k.strip(): v.strip() for k, _, v in (line.partition(':') for line in text.splitlines())}
            client = (fields.get('drm-pdev', ''), fields.get('drm-client-id', ''))
            if client[0] != pdev or not client[1] or client in seen:
                continue
            seen.add(client)
            amount, _, unit = fields['drm-memory-vram'].partition(' ')
            if amount.isdigit() and unit.strip() in UNITS:
                used += int(amount) * UNITS[unit.strip()]
        if used and before is not None and _start(proc_root, pid) == before:
            usage[pid] = (before, used)
    return usage


def _info(proc_root, pid):
    base = Path(proc_root) / str(pid)
    try:
        stat = (base / 'stat').read_text()
        rest = stat[stat.rindex(')') + 2:].split()
        uid = base.stat().st_uid
        cmd = (base / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        ppid, tty, start = int(rest[1]), int(rest[4]), int(rest[19])
    except (OSError, ValueError, IndexError):
        return None
    links = {}
    for name in ('exe', 'cwd'):
        try:
            links[name] = os.readlink(base / name).removesuffix(' (deleted)')
        except OSError:
            links[name] = None
    exe = links['exe'] or ''
    return dict(pid=pid, ppid=ppid, start=start, uid=uid, tty=tty, exe=exe, name=os.path.basename(exe),
                cwd=links['cwd'] or '', cmd=cmd, complete=links['exe'] is not None and links['cwd'] is not None)


def _protected(app, tree, mine, protected):
    """O app inteiro decide: processo principal, filhos e o que eles abriram (revisão Codex)."""
    root, uid = str(config.RAIZ), os.getuid()
    if app['pid'] <= 1 or app['uid'] != uid or not app['complete']:
        return True
    for info in tree:
        if info['uid'] != uid:
            continue  # ajudante de outro usuário (sandbox do navegador) não decide
        if not info['complete'] or info['name'] in protected or info['pid'] in mine or AGENT_CMD.search(info['cmd']):
            return True  # sem exe/cwd não dá para provar que não é do projeto
        if any(root in (info[k] or '') for k in ('exe', 'cwd', 'cmd')):
            return True
        if info['exe'] != app['exe'] and info['tty']:
            return True  # terminal com shell aberto (Codex, Claude, um comando seu)
    return False


def candidate_apps(proc_root='/proc', protected=PROTECTED, pdev=None, own_pid=None):
    """Apps do usuário que ocupam VRAM na placa pdev, agrupados pelo processo principal (Firefox e filhos = um app)."""
    table = {}
    for entry in Path(proc_root).iterdir():
        if entry.name.isdigit():
            info = _info(proc_root, int(entry.name)) or _info(proc_root, int(entry.name))
            if info is not None:
                table[info['pid']] = info
                continue
            try:
                owner = entry.stat().st_uid
            except FileNotFoundError:
                continue  # terminou durante a leitura
            except OSError as exc:
                raise ProcInconclusive(f'/proc/{entry.name}: {exc}') from exc
            if owner == os.getuid():
                raise ProcInconclusive(f'/proc/{entry.name} ilegível')  # revisão Codex: lacuna na árvore veta
    usage = vram_by_process(proc_root, pdev)
    children = {}
    for info in table.values():
        children.setdefault(info['ppid'], []).append(info['pid'])
    mine, pid = set(), os.getpid() if own_pid is None else own_pid
    while pid > 1 and pid not in mine:
        mine.add(pid)
        pid = table[pid]['ppid'] if pid in table else 0
    apps = {}
    for pid, (start, used) in usage.items():
        info = table.get(pid)
        if info is None or info['start'] != start:
            continue  # o PID mudou entre a leitura da VRAM e a da identidade
        while info['exe']:  # sobe enquanto o pai é o mesmo programa
            parent = table.get(info['ppid'])
            if parent is None or parent['pid'] <= 1 or parent['exe'] != info['exe']:
                break
            info = parent
        app = apps.setdefault(info['pid'], dict(info, vram_bytes=0))
        app['vram_bytes'] += used
    result = []
    for app in apps.values():
        tree, stack = [], [app['pid']]
        while stack:
            current = stack.pop()
            if current in table and all(current != t['pid'] for t in tree):
                tree.append(table[current]); stack.extend(children.get(current, []))
        if app['vram_bytes'] >= MIN_APP_BYTES and not _protected(app, tree, mine, protected):
            result.append(app)
    return result


def gpu_users(proc_root='/proc', pdev=None, protected=PROTECTED):
    """Só leitura, para o alerta da Central (06/11): quem ocupa a placa pdev, agrupado pelo programa principal
    (Firefox e filhos = um). kind: 'modelo' (llama-server/ollama), 'sistema' (sessão gráfica e afins) ou 'app'.
    Nunca fecha nada; o cmdline só serve para dizer de qual entidade é o modelo."""
    usage = vram_by_process(proc_root, pdev)
    infos, grouped = {}, {}

    def info(pid):
        if pid not in infos:
            infos[pid] = _info(proc_root, pid)
        return infos[pid]
    for pid, (start, used) in usage.items():
        current = info(pid)
        if current is None or current['start'] != start:
            continue
        while current['exe'] and current['ppid'] > 1:
            parent = info(current['ppid'])
            if parent is None or parent['exe'] != current['exe']:
                break
            current = parent
        row = grouped.setdefault(current['pid'], dict(pid=current['pid'], name=current['name'] or str(pid),
                                                       cmd=current['cmd'], vram_bytes=0))
        row['vram_bytes'] += used
    result = []
    for row in grouped.values():
        kind = 'modelo' if row['name'] in {'llama-server', 'ollama'} else 'sistema' if row['name'] in protected else 'app'
        result.append(dict(row, kind=kind, vram_mib=row['vram_bytes'] // MIB))
    return sorted(result, key=lambda r: -r['vram_bytes'])


def deficit_bytes(decision, metrics, policy):
    """Quanto falta para o pedido caber (sem compute ativo, como na manutenção exclusiva)."""
    limit = min(gpu_metrics.HARD_LIMIT, metrics['total_bytes'])
    return max(0, metrics['used_bytes'] + decision['additional_bytes'] + policy['margin_bytes'] - limit)


def _pidfd_open(pid):
    """os.pidfd_open não existe no Python do projeto (Anaconda); a chamada de sistema é a 434 em toda arquitetura."""
    if hasattr(os, 'pidfd_open'):
        return os.pidfd_open(pid)
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.syscall(ctypes.c_long(434), ctypes.c_int(pid), ctypes.c_uint(0))
    if fd < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return fd


def _terminate(app, proc_root, wait_seconds, interrupt):
    """pidfd: o sinal vai para o processo conferido, nunca para um PID reutilizado depois da conferência."""
    try:
        fd = _pidfd_open(app['pid'])
    except OSError as exc:
        return False, f'{type(exc).__name__}: {exc}'
    try:
        if _start(proc_root, app['pid']) != app['start']:
            return False, 'pid_reused'
        signal.pidfd_send_signal(fd, signal.SIGTERM)
        poller = select.poll()
        poller.register(fd, select.POLLIN)  # fica legível quando o processo termina
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if poller.poll(250):
                return True, ''
            if interrupt is not None and interrupt():
                break
        return False, 'still_running'
    except OSError as exc:
        return False, f'{type(exc).__name__}: {exc}'
    finally:
        os.close(fd)


def _fake_terminate(app, proc_root, wait_seconds, interrupt, kill):
    """Para testes: kill(pid, sinal) falso e saída observada no /proc falso."""
    try:
        kill(app['pid'], signal.SIGTERM)
    except OSError as exc:
        return False, f'{type(exc).__name__}: {exc}'
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if _start(proc_root, app['pid']) != app['start']:
            return True, ''
        if interrupt is not None and interrupt():
            break
        time.sleep(0.05)
    return _start(proc_root, app['pid']) != app['start'], 'still_running'


def reclaim(request, decision, metrics, policy, *, proc_root='/proc', kill=None, notify=True, wait_seconds=5.0,
            interrupt=None):
    """Fecha um app se ele sozinho resolve a falta; devolve o que foi feito ou None. Nunca levanta exceção."""
    cfg = settings()
    if (not cfg['enabled'] or request.get('owner') not in OWNERS or request.get('app_closed')
            or decision.get('reason') != 'vram_pressure' or not metrics.get('known')):
        return None
    if kill is None and os.environ.get('HOSHINO_TEST_OFFLINE') == '1':
        return None  # a suíte nunca fecha app de verdade
    pdev = gpu_pdev(metrics)
    try:
        missing = deficit_bytes(decision, metrics, policy)
        apps = candidate_apps(proc_root, cfg['protected'], pdev) if pdev else []
    except (OSError, KeyError, ValueError) as exc:
        diagnostics.emit('gpu.app_close_skipped', level='WARNING', reason='proc_read_failed', error=type(exc).__name__)
        return None
    enough = [a for a in apps if a['vram_bytes'] >= missing]
    if not missing or not enough:
        diagnostics.emit('gpu.app_close_skipped', owner=request.get('owner'), missing_mib=missing // MIB,
                         reason='no_gpu_device' if not pdev else 'no_single_app_frees_enough' if apps else 'no_user_app_on_gpu',
                         apps=[dict(name=a['name'], vram_mib=a['vram_bytes'] // MIB) for a in apps])
        return None
    app = max(enough, key=lambda a: a['start'])
    request['app_closed'] = True  # um por pedido, mesmo se o app não sair
    detail = dict(app=app['name'], pid=app['pid'], vram_mib=app['vram_bytes'] // MIB, missing_mib=missing // MIB,
                  owner=request.get('owner'), entity=config.ENTIDADE_ID)
    diagnostics.emit('gpu.app_close_requested', **detail)
    closed, error = (_terminate(app, proc_root, wait_seconds, interrupt) if kill is None
                     else _fake_terminate(app, proc_root, wait_seconds, interrupt, kill))
    diagnostics.emit('gpu.app_closed' if closed else 'gpu.app_close_unconfirmed', level='WARNING', error=error, **detail)
    if notify:
        quem = config.ENTIDADE_ID.capitalize()
        texto = (f"{quem} fechou {app['name']} para liberar {detail['vram_mib']} MiB de VRAM." if closed
                 else f"{quem} pediu para {app['name']} fechar e liberar VRAM, mas ele continua aberto.")
        try:  # sem esperar: a manutenção exclusiva não fica presa ao aviso
            subprocess.Popen(['notify-send', '-a', 'Hoshino e Lilith', 'VRAM', texto], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass
    return dict(detail, closed=closed, error=error)
