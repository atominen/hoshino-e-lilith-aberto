"""Executa um teste legado sem disponibilizar memória/estado reais para escrita."""
from pathlib import Path
import os
import runpy
import shutil
import sys
import tempfile
import socket
import re
import types
from urllib.parse import urlsplit, unquote
from catalogo import categoria, AUTOMATICOS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
# 05/11: módulos da raiz (laboratorio, iniciar_entidades) também são importados pelo app.
sys.path.insert(1, str(ROOT))
import config


def instalar_guardas():
    """Falhar antes de I/O real; mocks continuam explícitos, nunca sucesso falso.

    HTTP de fixtures é permitido apenas em portas efêmeras de loopback abertas
    pelo próprio processo. Não é um sandbox para executar código não confiável.
    """
    listeners = {}
    bind_original, close_original = socket.socket.bind, socket.socket.close

    def bind_fixture(sock, address):
        result = bind_original(sock, address)
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            listeners[id(sock)] = sock.getsockname()[:2]
        return result

    def close_fixture(sock):
        listeners.pop(id(sock), None)
        return close_original(sock)

    socket.socket.bind = bind_fixture
    socket.socket.close = close_fixture

    def temporario(path, dir_fd=None, *, follow_leaf=True):
        if isinstance(path, int):
            return True  # descritor já aberto, não um novo alvo
        candidate = Path(os.fsdecode(path))
        if not candidate.is_absolute() and dir_fd is not None and dir_fd >= 0:
            candidate = Path(os.readlink(f'/proc/self/fd/{dir_fd}')) / candidate
        # unlink/rename removem o link, não o destino dele. Resolver o último
        # componente impedia limpar venvs temporários ligados ao Python-base.
        resolved = candidate.resolve() if follow_leaf else candidate.parent.resolve() / candidate.name
        if resolved == Path('/dev/null'):
            return True
        return any(resolved.is_relative_to(root) for root in (Path('/tmp'), Path('/var/tmp')))

    def audit(event, args):
        if event == "sqlite3.connect":
            database = os.fsdecode(args[0])
            if database.startswith('file:'):
                parsed = urlsplit(database)
                if parsed.netloc not in {'', 'localhost'}:
                    raise PermissionError("Suíte offline: URI SQLite externa bloqueada")
                database = unquote(parsed.path)
            if database != ':memory:' and not temporario(database):
                raise PermissionError("Suíte offline: SQLite fora de pasta temporária bloqueado")
        elif event == 'open':
            path, mode, flags = args
            writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not temporario(path):
                raise PermissionError("Suíte offline: escrita fora de pasta temporária bloqueada")
        elif event in {'os.remove', 'os.rmdir', 'os.mkdir'}:
            if not temporario(args[0], args[-1], follow_leaf=False):
                raise PermissionError("Suíte offline: alteração fora de pasta temporária bloqueada")
        elif event == 'os.symlink':
            target, destination = map(lambda p: Path(os.fsdecode(p)), args[:2])
            target = target if target.is_absolute() else destination.parent / target
            if not temporario(target) or not temporario(destination):
                raise PermissionError("Suíte offline: link fora de pasta temporária bloqueado")
        elif event in {'os.rename', 'os.link'}:
            if not all(temporario(p, fd, follow_leaf=(event == 'os.link')) for p, fd in zip(args[:2], args[2:4])):
                raise PermissionError("Suíte offline: alteração fora de pasta temporária bloqueada")
        elif event == 'socket.getaddrinfo':
            if args[0] not in {'localhost', '127.0.0.1', '::1', None}:
                raise PermissionError("Suíte offline: resolução de rede externa bloqueada")
        elif event == 'socket.bind' and args[0].family in (socket.AF_INET, socket.AF_INET6):
            host, port = args[1][:2]
            if host not in {'127.0.0.1', '::1'} or port != 0:
                raise PermissionError("Suíte offline: apenas servidor efêmero de loopback permitido")
        elif event in {'socket.connect', 'socket.sendto'} and args[0].family in (socket.AF_INET, socket.AF_INET6):
            address = args[-1][:2]
            if tuple(address) not in tuple(listeners.values()):
                raise PermissionError("Suíte offline: conexão fora das fixtures bloqueada")
        elif event in {'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'}:
            command = args[1] if event == 'subprocess.Popen' else args[0]
            command = ' '.join(map(str, command)) if isinstance(command, (tuple, list)) else os.fsdecode(command)
            if re.search(r'\b(?:ollama|systemctl|sudo|sd-cli|arecord|parec|ffplay|curl|wget|apt|apt-get|npm)\b|(?:voice_worker|audio_worker)\.py|\bpip\s+install\b', command):
                raise PermissionError("Suíte offline: inicialização de serviço/modelo/hardware/rede bloqueada")
    sys.addaudithook(audit)
    # Captura/reprodução nativas não passam necessariamente por socket Python.
    # Nem importar PortAudio: em algumas máquinas a própria carga enumera
    # dispositivos. O stub só REJEITA operações; não simula áudio funcionando.
    sounddevice = types.ModuleType('sounddevice')
    def hardware_bloqueado(*a, **k):
        raise PermissionError("Suíte offline: captura/reprodução real bloqueada")
    for name in ('InputStream', 'RawInputStream', 'OutputStream', 'RawOutputStream',
                 'rec', 'play', 'playrec', 'query_devices', 'query_hostapis'):
        setattr(sounddevice, name, hardware_bloqueado)
    sys.modules['sounddevice'] = sounddevice
    # A importação de PyAutoGUI pode conectar ao X11 e deixar sockets abertos.
    # UI/hardware não fazem parte do contrato offline; fixtures próprias
    # continuam podendo substituir o backend explicitamente.
    sys.modules['pyautogui'] = None


def main():
    target = Path(sys.argv[1]).resolve()
    if not target.is_relative_to(ROOT / "testes") or not target.is_file():
        raise ValueError("Informe um teste da pasta testes.")
    if categoria(target.stem) not in AUTOMATICOS:
        raise ValueError('Teste manual ou não classificado: não pertence à suíte automatizada/offline.')
    with tempfile.TemporaryDirectory(prefix="hoshino-teste-") as pasta:
        base = Path(pasta)
        os.environ['HOSHINO_LAB_HOME']=str(base/'laboratorio-local')
        identity = base / "identity"
        shutil.copytree(Path(config.SELF_MODEL_PATH).parent, identity)
        config.ENTIDADE_DIR = base
        config.MEMORY_DIR = base / "memory"
        config.ENTITY_CONFIG_DIR = base / "config"
        paths = {
            "DB_PATH": "memory/sqlite/hoshino.db", "VECTOR_DIR": "memory/vector/db",
            "RUNTIME_DIR": "runtime", "JOBS_DIR": "runtime/jobs",
            "EVENT_LOG_DIR": "runtime/event_log", "ESTADO_MENTE": "runtime/estado_mente.json",
            "BUS_DIR": "runtime/bus", "ENTREGA_SAIDA": "runtime/entregas/saida",
            "ENTREGA_ENTRADA": "runtime/entregas/entrada", "OFICINA_DIR": "workspace",
            "SELF_MODEL_PATH": "identity/self_model.json",
            "CONSTITUICAO_PATH": "identity/constitution.json", "VERSOES_DIR": "identity/versions",
            "IMAGE_RUNTIME_DIR": "runtime", "IMAGE_OUTPUT_DIR": "runtime/imagens",
            "SHARED_RUNTIME_DIR": "shared/runtime", "HUGGINGFACE_CACHE_DIR": "shared/huggingface",
            "OLLAMA_MODELS_DIR": "shared/models/ollama",
        }
        for key, relative in paths.items():
            setattr(config, key, str(base / relative))
        config.VOZ_ATIVA = False
        # Nenhuma credencial real entra nos testes; casos Azure a substituem por
        # sentinelas e mockam o transporte. Não muda o ambiente do processo pai.
        os.environ.pop('AZURE_SPEECH_KEY',None)
        os.environ.pop('ELEVENLABS_API_KEY',None)
        audio_settings = ROOT/'compartilhado/config/audio.json'
        if audio_settings.is_file():
            import json
            settings = json.loads(audio_settings.read_text())
            for provider in ('azure', 'elevenlabs'):
                supplied = settings.get(provider,{})
                if isinstance(supplied,dict) and isinstance(supplied.get('key_env'),str):
                    os.environ.pop(supplied['key_env'],None)
        os.environ["HF_HOME"] = config.HUGGINGFACE_CACHE_DIR
        # Nem testes históricos podem baixar ASR/embeddings incidentalmente.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HOSHINO_TEST_OFFLINE'] = '1'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        os.environ['PULSE_SERVER'] = str(base / 'no-real-audio')
        os.environ.pop('DISPLAY', None)
        os.environ.pop('WAYLAND_DISPLAY', None)
        os.environ["HOSHINO_RUNTIME_DIR"] = config.RUNTIME_DIR
        # Subprocessos dos testes (ex.: admissão 16 GB) importam core/ como o processo pai.
        os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT / "app"), str(ROOT), os.environ.get("PYTHONPATH"))))
        config.garantir_pastas()
        Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        # Evita inicialização eager de embeddings/modelos em testes sem rede.
        sys.modules["chromadb"] = None
        from core import gpu_resource, gpu_metrics, resource_manager
        # Testes offline nunca descarregam modelos dos daemons reais.
        gpu_resource.prepare_residency = lambda owner: []
        resource_manager.refresh_executor_state = lambda endpoint: False
        # Decisões da suíte não dependem da carga da GPU/RAM reais.
        import time
        gpu_metrics.snapshot = lambda: dict(known=True, stable=True, source='mock', observed_at=time.time(),
                                           total_bytes=8*1024**3, used_bytes=0, utilization=0)
        gpu_metrics.ram_available = lambda: 31*1024**3
        instalar_guardas()
        os.chdir(ROOT)
        sys.argv = [str(target)]
        runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
