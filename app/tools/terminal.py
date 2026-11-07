"""
Execução de comandos — reescrita.

Problemas da versão anterior:
  * lista negra por substring: "rm " casava com "perfo*rm *", "dd" casava com
    "a*dd*", "import " bloqueava `grep -r 'import os'`. Na prática a Hoshino
    era barrada em comandos triviais e o filtro não protegia de nada sério
    (bastava escrever `/bin/rm`).
  * timeout fixo de 10s: build, apt, download ou script longo morriam.
  * sem diretório de trabalho, sem venv, sem ambiente: ela não conseguia rodar
    nada "dentro" do projeto nem da própria oficina.
  * comandos que pedem senha/confirmação ficavam pendurados até o timeout.

Agora:
  * classificação de risco por regex com limite de palavra, em 3 níveis:
    ok / precisa de confirmação humana / bloqueado (só catástrofe irreversível).
  * a confirmação é dada pelo HUMANO na interface (F8). O modelo não consegue
    se autoaprovar: `confirmado` não aparece no schema exposto ao LLM.
  * ambientes: "sistema" (shell de login do usuário, com aliases), "projeto"
    (venv da Hoshino) e "oficina" (ambiente isolado dela).
  * comando que estoura o timeout não é perdido: vira job em segundo plano
    com log próprio, consultável depois.
"""
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from config import (JOBS_DIR, LIMITE_SAIDA_CHARS, OFICINA_DIR, RAIZ, CODIGO_DIR,
                    TIMEOUT_COMANDO_MAX, TIMEOUT_COMANDO_PADRAO, VENV_PROJETO)

# ---------------------------------------------------------------------------
# Política de risco
# ---------------------------------------------------------------------------

# Só entra aqui o que é irreversível e catastrófico. Todo o resto é permitido
# (com ou sem confirmação). A regra: a Hoshino pode operar a máquina; ela só
# não pode destruí-la sozinha.
PADROES_BLOQUEADOS = [
    (r":\(\)\s*\{.*\};\s*:", "fork bomb"),
    (r"\brm\b[^|;&]*\s(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+/(\s|$)", "rm recursivo na raiz"),
    (r"\bmkfs(\.\w+)?\b[^|;&]*/dev/", "formatação de dispositivo"),
    (r"\bdd\b[^|;&]*\bof=/dev/(sd|nvme|hd|mmc)", "escrita crua em disco"),
    (r">\s*/dev/(sd|nvme|hd|mmc)\w*", "escrita crua em disco"),
    (r"\bchmod\b[^|;&]*-R[^|;&]*\s/(\s|$)", "chmod recursivo na raiz"),
    (r"\bchown\b[^|;&]*-R[^|;&]*\s/(\s|$)", "chown recursivo na raiz"),
    (r"\b(shred|wipefs)\b[^|;&]*/dev/", "apagamento de dispositivo"),
    (r">\s*/etc/(passwd|shadow|fstab|sudoers)", "sobrescrita de arquivo crítico"),
]

# Precisa de um "sim" explícito do humano na interface.
PADROES_CONFIRMACAO = [
    (r"\b(sudo|pkexec|doas)\b", "roda como root"),
    (r"^\s*su\b", "troca de usuário"),
    (r"\brm\b\s+-[a-zA-Z]*[rf]", "remoção recursiva/forçada de arquivos"),
    (r"\b(shutdown|reboot|poweroff|halt)\b", "desliga ou reinicia a máquina"),
    (r"\bsystemctl\b\s+(stop|disable|mask|restart)", "mexe em serviço do sistema"),
    (r"\b(apt|apt-get|dnf|pacman|snap|flatpak)\b\s+(install|remove|purge|upgrade|autoremove)",
     "instala ou remove pacote do sistema"),
    (r"\bpip3?\b\s+(install|uninstall)", "altera pacotes Python"),
    (r"\b(userdel|usermod|passwd|groupdel)\b", "mexe em contas de usuário"),
    (r"\bcrontab\b\s+-r", "apaga a crontab"),
    (r"\bgit\b\s+(reset\s+--hard|clean\s+-[a-z]*f|push\s+--force)", "operação destrutiva no git"),
    (r"\b(mkfs|fdisk|parted|dd)\b", "operação de disco"),
    (r"\bkill(all)?\b\s+-9", "mata processo à força"),
    (r"\|\s*(sudo\s+)?(bash|sh|zsh)\b", "executa script baixado da internet"),
    (r"\bdocker\b\s+(rm|rmi|system\s+prune)", "remove recurso do Docker"),
    (r">\s*/etc/", "escreve em /etc"),
    (r"\bmv\b[^|;&]*\s/(etc|usr|bin|boot|lib|var)\b", "move caminho de sistema"),
]


def avaliar_risco(comando: str):
    """Devolve (nivel, motivo), com nivel em 'ok' | 'confirmar' | 'bloqueado'."""
    texto = (comando or "").strip()
    if not texto:
        return "bloqueado", "comando vazio"
    for padrao, motivo in PADROES_BLOQUEADOS:
        if re.search(padrao, texto, flags=re.IGNORECASE):
            return "bloqueado", motivo
    for padrao, motivo in PADROES_CONFIRMACAO:
        if re.search(padrao, texto, flags=re.IGNORECASE):
            return "confirmar", motivo
    return "ok", ""


# ---------------------------------------------------------------------------
# Ambientes
# ---------------------------------------------------------------------------

AMBIENTES = ("sistema", "projeto", "oficina")


def _montar_ambiente(ambiente: str, diretorio: str = None):
    """Devolve (env, cwd, descricao) para o ambiente pedido."""
    env = os.environ.copy()
    env.setdefault("DEBIAN_FRONTEND", "noninteractive")
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    ambiente = ambiente if ambiente in AMBIENTES else "sistema"
    aviso = ""
    if ambiente == "projeto":
        venv = Path(VENV_PROJETO)
        cwd = str(RAIZ)
        env["PYTHONPATH"] = str(CODIGO_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        if (venv / "bin").is_dir():
            env["VIRTUAL_ENV"] = str(venv)
            env["PATH"] = f"{venv / 'bin'}:{env.get('PATH', '')}"
        descricao = "venv do projeto Hoshino"
    elif ambiente == "oficina":
        oficina = Path(OFICINA_DIR)
        (oficina / "home").mkdir(parents=True, exist_ok=True)
        cwd = str(oficina)
        venv = oficina / "venv"
        if (venv / "bin").is_dir():
            env["VIRTUAL_ENV"] = str(venv)
            env["PATH"] = f"{venv / 'bin'}:{env.get('PATH', '')}"
        env["HOME"] = str(oficina / "home")
        descricao = "oficina isolada"
    else:
        cwd = os.path.expanduser("~")
        descricao = "sistema (shell do usuário)"

    if diretorio:
        alvo = Path(os.path.expanduser(diretorio))
        if not alvo.is_absolute():
            alvo = Path(cwd) / alvo
        if alvo.is_dir():
            cwd = str(alvo)
        else:
            aviso = f" [aviso: '{diretorio}' não existe, usei {cwd}]"
    return env, cwd, descricao + aviso


def _truncar(texto: str) -> str:
    if len(texto) <= LIMITE_SAIDA_CHARS:
        return texto
    metade = LIMITE_SAIDA_CHARS // 2
    cortado = len(texto) - LIMITE_SAIDA_CHARS
    return (texto[:metade] + f"\n\n...[{cortado} caracteres omitidos no meio]...\n\n"
            + texto[-metade:])


def _comando_shell(comando: str, ambiente: str, tty: bool) -> list:
    from core import entity_access
    prefixo = "shopt -s expand_aliases; [ -f ~/.bash_aliases ] && . ~/.bash_aliases 2>/dev/null; "
    # Um estágio anterior com falha não pode virar saída zero apenas porque
    # o último processo da pipeline terminou normalmente. Não usamos errexit:
    # recuperação explícita com || continua sendo decisão do comando.
    linha = prefixo + 'set -o pipefail; ' + comando
    flags = "-lc" if ambiente == "sistema" else "-c"
    argv = ["bash", flags, linha]
    if tty and shutil.which("script"):
        # `script` cria um pty: programas que exigem terminal funcionam.
        # O shell de script pode ser /bin/sh: selecione o mesmo bash, com
        # quoting único, para manter aliases/pipefail sem alterar o comando.
        return entity_access.command(["script", "-qec", shlex.join(argv), "/dev/null"])
    return entity_access.command(argv)


# ---------------------------------------------------------------------------
# Jobs em segundo plano
# ---------------------------------------------------------------------------

RECENTES_MAX = 40


def _registrar_recente(meta, codigo, texto):
    """06/11 (pedido humano): a aba Atividade → "Comandos e saída" mostra também os comandos rápidos.
    Antes só apareciam os que viravam job em segundo plano, então a aba ficava sempre vazia.
    Fica fora da pasta de jobs (o supervisor não confunde com trabalho rodando); guarda os 40 últimos."""
    try:
        import config
        pasta = Path(config.RUNTIME_DIR) / 'comandos_recentes'
        pasta.mkdir(parents=True, exist_ok=True)
        registro = {k: meta.get(k) for k in ('id', 'entity', 'comando', 'ambiente', 'cwd', 'inicio')}
        registro.update(fim=datetime.now().isoformat(), codigo=codigo,
                        status='concluido' if codigo == 0 else 'falhou', saida=(texto or '')[-32768:])
        (pasta / f"{meta['id']}.json").write_text(json.dumps(registro, ensure_ascii=False), encoding='utf-8')
        for velho in sorted(pasta.glob('job-*.json'), key=lambda c: c.stat().st_mtime)[:-RECENTES_MAX]:
            velho.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - registro para a interface nunca muda o resultado do comando
        pass


def _dir_jobs() -> Path:
    p = Path(JOBS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _salvar_job(meta: dict, *, novo=False):
    # Legado sem marca não é adotado como processo nosso só pelo número do PID.
    from core import job_bus
    import config
    if novo and 'process_stamp' not in meta:
        meta.update(process_stamp=job_bus._process_stamp(meta['pid']), entity=config.ENTIDADE_ID,
                    project_root=str(Path(config.RUNTIME_DIR).resolve()))
    from tools.command_receipt import atomic_json
    atomic_json(_dir_jobs() / f"{meta['id']}.json", meta)


def _ler_job(job_id: str):
    if not re.fullmatch(r'job-[a-zA-Z0-9_-]+', str(job_id)):
        return None
    arq = _dir_jobs() / f"{job_id}.json"
    if not arq.exists():
        return None
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        from core import job_bus
        return job_bus._process_stamp(pid) is not None
    except (OSError, ProcessLookupError):
        return False


def _com_recibo(argv, job_id):
    return [sys.executable, '-I', '-B', str(Path(__file__).with_name('command_receipt.py')),
            str(_dir_jobs() / f'{job_id}.receipt'), job_id, *argv]


def _recibo(meta):
    """Só adota recibo do observador exato, nunca um código encontrado no log."""
    if meta.get('receipt_schema') != 1:
        return None
    try:
        value = json.loads((_dir_jobs() / f"{meta['id']}.receipt").read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('schema') != 1:
            return None
        for field, key in (('id', 'job_id'), ('pid', 'pid'), ('process_token', 'process_token'),
                           ('entity', 'entity'), ('project_root', 'project_root')):
            if not meta.get(field) or value.get(key) != meta[field]:
                return None
        if not value.get('finished_at') or type(value.get('started')) is not bool:
            return None
        if value['started'] and type(value.get('code')) is not int:
            return None
        return value
    except (OSError, ValueError, TypeError):
        return None


def _atualizar_job(meta):
    if meta.get('status') != 'rodando':
        return meta
    receipt = _recibo(meta)
    alive = _vivo(meta['pid'])
    if receipt is None and not alive:
        # O filho pode escrever entre a primeira leitura e a consulta de PID.
        receipt = _recibo(meta)
    if receipt is not None or not alive:
        meta.update(status='terminado', fim=datetime.now().isoformat())
        if receipt is not None and meta.get('outcome') != 'uncertain':
            meta.update(codigo=receipt['code'], fim=receipt['finished_at'],
                        command_started=receipt['started'])
            if not receipt['started']:
                meta['launch_error'] = receipt.get('error', 'Comando não iniciado')
        _salvar_job(meta)
    return meta


def _recolher_em_background(proc):
    # Apenas waitpid do filho já criado: não agenda, reinicia ou repete trabalho.
    threading.Thread(target=proc.wait, daemon=True, name='command-reaper').start()


def iniciar_comando_longo(comando: str, ambiente: str = "sistema", diretorio: str = None,
                          confirmado: bool = False, descricao: str = "") -> str:
    """Dispara um comando demorado (build, download, treino) e volta na hora com
    um identificador de job. A saída fica num log consultável."""
    nivel, motivo = avaliar_risco(comando)
    if nivel == "bloqueado":
        return f"BLOQUEADO: {motivo}. Irreversível — não executo nem com confirmação."
    if nivel == "confirmar" and not confirmado:
        return _pedir_confirmacao(comando, motivo, ambiente, diretorio, longo=True)

    env, cwd, desc_amb = _montar_ambiente(ambiente, diretorio)
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    process_token = uuid.uuid4().hex
    import config
    env.update(HOSHINO_JOB_PROCESS_TOKEN=process_token, HOSHINO_JOB_ROOT=str(Path(config.RUNTIME_DIR).resolve()),
               HOSHINO_JOB_ENTITY=config.ENTIDADE_ID)
    log = _dir_jobs() / f"{job_id}.log"
    with open(log, "wb") as saida:
        proc = subprocess.Popen(_com_recibo(_comando_shell(comando, ambiente, tty=False), job_id),
                                stdout=saida, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, cwd=cwd, env=env,
                                start_new_session=True)
    _salvar_job({"id": job_id, "receipt_schema": 1, "pid": proc.pid, "process_token":process_token, "comando": comando, "ambiente": ambiente,
                 "cwd": cwd, "log": str(log), "inicio": datetime.now().isoformat(),
                 "descricao": descricao, "status": "rodando", "fim": None, "codigo": None}, novo=True)
    _recolher_em_background(proc)
    return (f"Job {job_id} iniciado em segundo plano ({desc_amb}, pid {proc.pid}).\n"
            f"Comando: {comando}\nUse ver_comando('{job_id}') para acompanhar.")


def ver_comando(job_id: str, linhas: int = 40) -> str:
    """Mostra o estado e as últimas linhas de saída de um job."""
    meta = _ler_job(job_id)
    if not meta:
        return f"Job '{job_id}' não existe. Use listar_comandos() para ver os jobs reais."
    _atualizar_job(meta)
    texto = ""
    log = Path(meta["log"])
    if log.exists():
        conteudo = log.read_text(encoding="utf-8", errors="replace").splitlines()
        texto = "\n".join(conteudo[-max(1, linhas):])
    comando_visivel = str(meta['comando']).replace('\r', r'\r').replace('\n', r'\n')
    return (f"Job {job_id} [{meta['status']}] — {comando_visivel}\n"
            f"RESULTADO_JOB={'pending' if meta['status']=='rodando' else 'uncertain' if meta.get('outcome')=='uncertain' else 'error' if meta.get('command_started') is False else 'uncertain' if meta.get('codigo') is None else 'success' if meta['codigo']==0 else 'error'}\n"
            f"CODIGO_SAIDA={meta.get('codigo')}\n"
            f"Início: {meta['inicio']}\n--- últimas {linhas} linhas ---\n"
            f"{_truncar(texto) or '(sem saída ainda)'}")


def listar_comandos() -> str:
    """Lista os jobs em segundo plano conhecidos."""
    arquivos = sorted(_dir_jobs().glob("job-*.json"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    if not arquivos:
        return "Nenhum job em segundo plano."
    linhas = []
    for arq in arquivos[:20]:
        meta = _ler_job(arq.stem)
        if meta:
            _atualizar_job(meta)
            linhas.append(f"[{meta['id']}] {meta['status']} — {meta['comando'][:70]}")
    return "Jobs:\n" + "\n".join(linhas)


def jobs_recem_terminados() -> list:
    """Jobs que estavam rodando e acabaram desde a última checagem.

    É o que permite ela avisar 'aquele build que você mandou terminou' sem
    ficar perguntando ao modelo de dois em dois minutos se há algo a dizer.
    """
    terminados = []
    for arq in _dir_jobs().glob("job-*.json"):
        try:
            meta = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("status") == "rodando":
            _atualizar_job(meta)
            if meta['status'] != 'rodando':
                terminados.append(meta)
    return terminados


def encerrar_comando(job_id: str) -> str:
    """Encerra um job em segundo plano."""
    meta = _ler_job(job_id)
    if not meta:
        return f"Job '{job_id}' não existe."
    if not _vivo(meta["pid"]):
        return f"Job {job_id} já havia terminado."
    from core import job_bus
    import config
    def owned():
        try:
            env = dict(part.split(b'=', 1) for part in Path(f'/proc/{meta["pid"]}/environ').read_bytes().split(b'\0') if b'=' in part)
        except OSError:
            return False
        return (meta.get('process_stamp') is not None and
                bool(meta.get('process_token')) and
                env.get(b'HOSHINO_JOB_PROCESS_TOKEN') == meta['process_token'].encode() and
                env.get(b'HOSHINO_JOB_ROOT') == str(Path(config.RUNTIME_DIR).resolve()).encode() and
                env.get(b'HOSHINO_JOB_ENTITY') == config.ENTIDADE_ID.encode() and
                job_bus._process_stamp(meta['pid']) == meta['process_stamp'] and
                meta.get('entity') == config.ENTIDADE_ID and
                meta.get('project_root') == str(Path(config.RUNTIME_DIR).resolve()) and
                os.getpgid(meta['pid']) == meta['pid'])
    if not owned():
        return f'Erro: posse do processo do job {job_id} não confirmada; nenhum sinal enviado.'
    # Encerrar o processo não confirma nem desfaz os efeitos do comando original.
    meta['outcome'] = 'uncertain'
    meta['auto_retry'] = False
    try:
        os.killpg(os.getpgid(meta["pid"]), signal.SIGTERM)
        time.sleep(0.5)
        if _vivo(meta["pid"]) and owned():
            os.killpg(os.getpgid(meta["pid"]), signal.SIGKILL)
    except Exception as e:  # noqa: BLE001
        _salvar_job(meta)
        return f"RESULTADO_INCERTO: encerramento do job {job_id} não confirmado; não repetir automaticamente. {e}"
    if _vivo(meta['pid']):
        # O supervisor deve continuar vendo este processo como bloqueador.
        # Um sinal enviado não é prova de término (nem de sucesso da ação).
        _salvar_job(meta)
        return f"RESULTADO_INCERTO: sinais de encerramento enviados ao job {job_id}, mas o término ainda não foi confirmado; não repetir automaticamente."
    meta["status"] = "encerrado"
    meta["fim"] = datetime.now().isoformat()
    _salvar_job(meta)
    return f"Job {job_id} encerrado.\n[PROCESSO ENCERRADO VERIFICADO]\nOs efeitos do comando original continuam incertos; não repetir automaticamente."


# ---------------------------------------------------------------------------
# Confirmação humana
# ---------------------------------------------------------------------------

def _pendentes_path() -> Path:
    return _dir_jobs().parent / "confirmacoes_pendentes.json"


def _pedir_confirmacao(comando, motivo, ambiente, diretorio, longo=False, timeout=None):
    pend = {"id": f"cfm-{uuid.uuid4().hex[:6]}", "comando": comando, "motivo": motivo,
            "ambiente": ambiente, "diretorio": diretorio, "longo": longo,
            "timeout": timeout, "criado_em": datetime.now().isoformat()}
    caminho = _pendentes_path()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    atual = []
    if caminho.exists():
        try:
            atual = json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            atual = []
    caminho.write_text(json.dumps((atual + [pend])[-10:], ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return (f"CONFIRMACAO_NECESSARIA::{pend['id']}\n"
            f"Esse comando {motivo} e precisa de um 'sim' do usuário antes de rodar.\n"
            f"Comando: {comando}\n"
            f"Explique ao usuário o que ele faz e por que você quer rodar, e espere a "
            f"aprovação com F8. Não tente contornar por outro caminho.")


def confirmacao_pendente():
    """Usada pela interface: devolve a última confirmação aguardando o humano."""
    caminho = _pendentes_path()
    if not caminho.exists():
        return None
    try:
        atual = json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return atual[-1] if atual else None


def consumir_confirmacao(cfm_id: str):
    caminho = _pendentes_path()
    if not caminho.exists():
        return None
    atual = json.loads(caminho.read_text(encoding="utf-8"))
    escolhido = next((p for p in atual if p["id"] == cfm_id), None)
    restante = [p for p in atual if p["id"] != cfm_id]
    caminho.write_text(json.dumps(restante, ensure_ascii=False, indent=2), encoding="utf-8")
    return escolhido


# ---------------------------------------------------------------------------
# Execução principal
# ---------------------------------------------------------------------------

def execute_command(command: str, ambiente: str = "sistema", diretorio: str = None,
                    timeout: int = None, entrada: str = None, tty: bool = False,
                    confirmado: bool = False) -> str:
    """Executa um comando de shell e devolve saída + código de retorno.

    `ambiente`: 'sistema' (shell do usuário), 'projeto' (venv da Hoshino) ou
    'oficina' (ambiente isolado dela). Se estourar o timeout, o processo NÃO é
    morto: vira job em segundo plano.
    """
    comando = (command or "").strip()
    if not comando:
        return "Erro: comando vazio."

    nivel, motivo = avaliar_risco(comando)
    if nivel == "bloqueado":
        return (f"BLOQUEADO: {motivo}. Irreversível; não executo nem com confirmação. "
                f"Se for mesmo necessário, o usuário faz manualmente.")
    if nivel == "confirmar" and not confirmado:
        return _pedir_confirmacao(comando, motivo, ambiente, diretorio, timeout=timeout)

    timeout = max(1, min(int(timeout or TIMEOUT_COMANDO_PADRAO), TIMEOUT_COMANDO_MAX))
    env, cwd, desc_amb = _montar_ambiente(ambiente, diretorio)
    process_token = uuid.uuid4().hex
    import config
    env.update(HOSHINO_JOB_PROCESS_TOKEN=process_token, HOSHINO_JOB_ROOT=str(Path(config.RUNTIME_DIR).resolve()),
               HOSHINO_JOB_ENTITY=config.ENTIDADE_ID)
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    log = _dir_jobs() / f"{job_id}.log"

    try:
        with open(log, "wb") as saida:
            proc = subprocess.Popen(
                _com_recibo(_comando_shell(comando, ambiente, tty), job_id),
                stdout=saida, stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE if entrada is not None else subprocess.DEVNULL,
                cwd=cwd, env=env, start_new_session=True)
            meta = {"id": job_id, "receipt_schema": 1, "pid": proc.pid,
                    "process_token": process_token, "entity": config.ENTIDADE_ID,
                    "project_root": str(Path(config.RUNTIME_DIR).resolve()),
                    "comando": comando, "ambiente": ambiente, "cwd": cwd,
                    "log": str(log), "inicio": datetime.now().isoformat(),
                    "status": "rodando", "fim": None, "codigo": None}
            if entrada is not None:
                try:
                    proc.stdin.write(entrada.encode())
                    proc.stdin.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                meta['descricao'] = 'promovido por timeout'
                _salvar_job(meta, novo=True)
                _recolher_em_background(proc)
                parcial = log.read_text(encoding="utf-8", errors="replace")[-2000:]
                return (f"Ainda rodando depois de {timeout}s — não matei o processo, "
                        f"virou o job {job_id} (pid {proc.pid}).\n"
                        f"Saída parcial:\n{parcial}\n"
                        f"Use ver_comando('{job_id}') para acompanhar.")
        receipt = _recibo(meta)
        if receipt is None:
            _salvar_job(meta, novo=True)
            return (f'RESULTADO_INCERTO: observador terminou sem recibo válido; '
                    f'não repetir. Consulte ver_comando({job_id!r}).')
        if not receipt['started']:
            _salvar_job(meta, novo=True)
            _atualizar_job(meta)
            return f"Erro: comando não iniciado ({receipt.get('error', 'falha de lançamento')})."
        codigo = receipt['code']
        texto = log.read_text(encoding="utf-8", errors="replace").strip()
        _registrar_recente(meta, codigo, texto)
        log.unlink(missing_ok=True)
        (_dir_jobs() / f'{job_id}.receipt').unlink(missing_ok=True)
    except FileNotFoundError as e:
        if 'proc' in locals():
            return f'RESULTADO_INCERTO: comando iniciado, mas recibo/log indisponível; não repetir. {e}'
        return f"Erro: interpretador de shell não encontrado ({e})."
    except Exception as e:  # noqa: BLE001
        if 'proc' in locals():
            return f'RESULTADO_INCERTO: comando iniciado, mas seu resultado não foi confirmado; não repetir. {e}'
        return f"Erro ao executar: {e}"

    cabecalho = f"[{desc_amb} | dir: {cwd} | saída {codigo}]"
    if not texto:
        return (f"{cabecalho}\n(sem saída)" if codigo == 0
                else f"{cabecalho}\nComando falhou sem mensagem. Código {codigo}.")
    return f"{cabecalho}\n{_truncar(texto)}"


def get_system_time() -> str:
    from core import history
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
            "sexta-feira", "sábado", "domingo"]
    agora = history.local_now()
    return f"{agora:%d/%m/%Y %H:%M:%S} ({dias[agora.weekday()]}) · {agora.tzinfo} · UTC{agora:%z}"


def list_files(directory: str = ".") -> str:
    """Lista arquivos de um diretório, com tamanho e data."""
    alvo = Path(os.path.expanduser(directory or "."))
    if not alvo.is_absolute():
        alvo = Path.cwd() / alvo
    from core import entity_access
    if not entity_access.permitted(alvo):return 'ACESSO_BLOQUEADO: diretório de outra entidade.'
    if not alvo.exists():
        return f"Erro: '{directory}' não existe."
    if not alvo.is_dir():
        return f"'{alvo}' é um arquivo ({alvo.stat().st_size} bytes), não um diretório."
    linhas = []
    try:
        for item in sorted(alvo.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if not entity_access.permitted(item):continue
            try:
                st = item.stat()
                marca = "/" if item.is_dir() else ""
                linhas.append(f"{item.name}{marca}\t{st.st_size}B\t"
                              f"{datetime.fromtimestamp(st.st_mtime):%d/%m %H:%M}")
            except OSError:
                linhas.append(f"{item.name}\t(sem permissão)")
    except PermissionError:
        return f"Erro: sem permissão para listar '{alvo}'."
    if not linhas:
        return f"'{alvo}' está vazio."
    return f"Conteúdo de {alvo} ({len(linhas)} itens):\n" + "\n".join(linhas[:200])


def descrever_ambientes() -> str:
    """Diz em quais ambientes a Hoshino pode rodar comandos e o estado de cada um."""
    oficina_venv = Path(OFICINA_DIR) / "venv" / "bin" / "python"
    projeto_venv = Path(VENV_PROJETO) / "bin" / "python"
    return (
        "Ambientes de execução:\n"
        f"- sistema: shell de login do usuário (aliases carregados), home = {os.path.expanduser('~')}\n"
        f"- projeto: pasta da Hoshino ({RAIZ}), venv "
        f"{'presente' if projeto_venv.exists() else 'ausente'}\n"
        f"- oficina: ambiente isolado ({OFICINA_DIR}), venv "
        f"{'presente' if oficina_venv.exists() else 'ainda não criado'}\n"
        "Comandos longos: iniciar_comando_longo / ver_comando / listar_comandos / encerrar_comando."
    )
