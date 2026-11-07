"""Laboratório local: inventário, mods e construção copy-on-write (sem tocar nos originais)."""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

DEFAULT_HOME = Path.home() / 'laboratorio-lora'
FORBIDDEN_PARTS = {'.git', '.venv', '.env', '__pycache__', '.cache', 'memory', 'runtime',
                   'modelos', 'models', 'secrets', 'credenciais', 'tokens', 'keys', 'logs',
                   'overlays', 'backups', 'experimentos', 'workspaces'}
ID_RE = re.compile(r'^[a-z][a-z0-9_-]{1,47}$')


def safe_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Caminho vazio ou inválido.')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')) or path.parts[0].startswith('.'):
        raise ValueError(f'Caminho não é relativo e normalizado: {value!r}')
    if any(p.startswith('.') or p.lower() in FORBIDDEN_PARTS or p.lower().endswith(('.env', '.sqlite', '.db', '.key', '.pem')) for p in path.parts):
        raise ValueError(f'Caminho restrito (credenciais/memória/modelos): {value!r}')
    if not (str(path).startswith(('app/', 'scripts/', 'testes/', 'desktop/', 'pc2/', 'compartilhado/servicos/'))
            or str(path) in {'README.md', 'iniciar_entidades.py', 'iniciar_hoshino.sh', 'iniciar_discord.sh'}):
        raise ValueError(f'Arquivo fora da superfície de mods permitida: {value!r}')
    return path


class Laboratory:
    def __init__(self, project: Path | str, home: Path | str = DEFAULT_HOME):
        self.project = Path(project).expanduser().resolve(strict=True)
        self.home = Path(home).expanduser().resolve()
        self.mods_dir = self.project / 'laboratorio' / 'mods'
        self.state_dir = self.home / 'controle-laboratorio'
        self.builds_dir = self.home / 'overlays' / 'builds'
        self.current = self.home / 'overlays' / 'current'

    def _save(self, path: Path, value: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        try:
            tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def _state(self):
        p = self.state_dir / 'mods-ativos.json'
        if not p.exists():
            return {'enabled': []}
        value = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or not isinstance(value.get('enabled'), list):
            raise ValueError('Estado inválido de mods: não alterado.')
        return value

    def _manifest(self, directory: Path) -> dict:
        if directory.is_symlink() or not directory.is_dir() or not ID_RE.fullmatch(directory.name):
            raise ValueError(f'Mod inválido: {directory}')
        path = directory / 'manifest.json'
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Manifesto ausente/inseguro: {directory.name}')
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('id') != directory.name or not isinstance(data.get('overrides'), dict):
            raise ValueError(f'ID ou mapeamento inválido: {directory.name}')
        if len(data['overrides']) > 60:
            raise ValueError('Limite de 60 arquivos por mod excedido.')
        verified = {}
        for destination, source in data['overrides'].items():
            rel = safe_path(destination)
            src = PurePosixPath(source)
            if not isinstance(source, str) or src.is_absolute() or not src.parts or src.parts[0] != 'files' or '..' in src.parts or any(p.startswith('.') for p in src.parts):
                raise ValueError('Arquivo de origem do mod deve estar em files/.')
            fp = directory / source
            if fp.is_symlink() or not fp.is_file() or not fp.resolve().is_relative_to(directory.resolve()):
                raise ValueError(f'Arquivo de mod ausente/inseguro: {source}')
            if fp.stat().st_size > 2 * 1024 * 1024:
                raise ValueError('Override maior que 2 MiB: ' + source)
            original = self.project.joinpath(*rel.parts)
            if original.is_symlink() or not original.is_file() or not original.resolve().is_relative_to(self.project):
                raise ValueError(f'Original não existe como arquivo regular: {destination}')
            verified[str(rel)] = str(fp)
        return {'id': data['id'], 'name': str(data.get('name', directory.name))[:100],
                'description': str(data.get('description', ''))[:300],
                'version': str(data.get('version', '1'))[:30], 'files': verified}

    def manifests(self):
        if not self.mods_dir.is_dir():
            return []
        return [self._manifest(p) for p in sorted(self.mods_dir.iterdir()) if p.is_dir() and not p.is_symlink()]

    def mods(self):
        active = self._state()['enabled']
        return [{**m, 'enabled': m['id'] in active,
                 'overrides': list(m['files'])} for m in self.manifests()]

    def set_mod(self, mod_id: str, enabled: bool):
        all_ids = {m['id'] for m in self.manifests()}
        if mod_id not in all_ids:
            raise ValueError('Mod não encontrado ou inválido.')
        state = self._state()
        active = state['enabled']
        if not all(isinstance(x,str) and x in all_ids for x in active):
            raise ValueError('Estado contém mod ausente; restaure-o antes de continuar.')
        if enabled and mod_id not in active: active.append(mod_id)
        if not enabled and mod_id in active: active.remove(mod_id)
        self._save(self.state_dir / 'mods-ativos.json', state)
        return active

    def _tracked(self):
        r = subprocess.run(['git', '-C', str(self.project), 'ls-files', '-z'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        for name in r.stdout.split(b'\0'):
            if not name: continue
            relative = os.fsdecode(name)
            path = PurePosixPath(relative)
            if path.is_absolute() or '..' in path.parts or path.parts[0] == 'laboratorio':
                continue
            if any(p.lower() in FORBIDDEN_PARTS or p.startswith('.') for p in path.parts):
                continue
            source = self.project.joinpath(*path.parts)
            if source.is_symlink():
                continue
            if source.is_file() and source.resolve().is_relative_to(self.project):
                if source.stat().st_size <= 12 * 1024 * 1024:
                    yield path, source

    def build(self):
        """Snapshot tracked files only. Never hardlink/symlink originals into runnable snapshot."""
        mods = {m['id']:m for m in self.manifests()}
        enabled = self._state()['enabled']
        if any(mod not in mods for mod in enabled):
            raise ValueError('Mods ativos incluem módulo removido: não construir.')
        self.builds_dir.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix='build-', dir=self.builds_dir))
        try:
            count = 0
            for relative, src in self._tracked():
                target = tmp.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target, follow_symlinks=False)
                count += 1
            overrides = {}
            for mod_id in enabled:
                for rel, src in mods[mod_id]['files'].items():
                    target = tmp.joinpath(*PurePosixPath(rel).parts)
                    if not target.is_file() or target.is_symlink():
                        raise ValueError(f'Snapshot não contém o original rastreado: {rel}')
                    shutil.copy2(src, target)
                    overrides[rel] = mod_id # últimos ativados prevalecem
            metadata = {'created_at': datetime.now().astimezone().isoformat(),
                        'enabled': enabled, 'overrides': overrides, 'tracked_files': count,
                        'source_project': str(self.project), 'snapshot': str(tmp)}
            (tmp / 'LAB_BUILD.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
            # Atomic symlink switch; previous build is kept for rollback.
            self.current.parent.mkdir(parents=True, exist_ok=True)
            if self.current.exists() and not self.current.is_symlink():
                raise ValueError('current existe e não é symlink: recuso sobrescrever.')
            link = self.current.with_name('current.tmp')
            if link.exists() or link.is_symlink(): link.unlink()
            os.symlink(tmp, link)
            os.replace(link, self.current)
            return metadata
        except Exception:
            shutil.rmtree(tmp)
            raise

    def overlay_info(self):
        if not self.current.is_symlink(): return {'exists': False}
        target = self.current.resolve()
        if not target.is_relative_to(self.builds_dir) or not (target / 'LAB_BUILD.json').is_file():
            return {'exists': False, 'error':'Destino de overlay inesperado'}
        return {'exists': True, **json.loads((target / 'LAB_BUILD.json').read_text(encoding='utf-8'))}

    def status(self):
        state_dir = self.home / 'experimentos' / 'orquestrador-9b-vision-v1-4'
        path = state_dir / 'estado.json'
        try: pipeline = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        except (OSError, ValueError): pipeline = {'status':'estado inválido'}
        pid_path = state_dir / 'pid'
        try: pid = int(pid_path.read_text().strip()) if pid_path.is_file() else None
        except (OSError, ValueError): pid = None
        active, stopped = self._process(pid)
        model_dir = self.home / 'modelos' / 'qwen3.5-9b-uncensored-hf'
        partials = []
        if model_dir.is_dir():
            for dp, dirs, files in os.walk(model_dir, followlinks=False):
                for file in files:
                    p = Path(dp)/file
                    if file.endswith('.incomplete'):
                        try: partials.append({'name':file[:48], 'bytes':p.stat().st_size,
                                             'modified':datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat()})
                        except FileNotFoundError: pass
        usage = shutil.disk_usage(self.home)
        log = self.home / 'logs' / '9b-vision-retomada.log'
        if not log.is_file(): log = self.home / 'logs' / '9b-vision-v1-4.log'
        tail = ''
        if log.is_file():
            with log.open('rb') as f:
                f.seek(max(0, f.seek(0, 2)-12000));tail=f.read().decode('utf-8',errors='replace')[-6000:]
        schedule = self.state_dir / 'agendamento.json'
        try: agendamento = json.loads(schedule.read_text()) if schedule.is_file() else {}
        except (OSError,ValueError): agendamento = {}
        return {'pipeline':pipeline, 'pid':pid, 'process_alive':active, 'process_stopped':stopped,
                'partials':partials[:20], 'disk_free_gib':round(usage.free/1024**3,2),
                'log_tail':tail, 'log_file':str(log), 'schedule':agendamento,
                'overlay':self.overlay_info()}

    @staticmethod
    def _process(pid):
        if not pid:return (False,False)
        try:
            raw = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
            uid = Path(f'/proc/{pid}').stat().st_uid
            st = Path(f'/proc/{pid}/status').read_text()
            state = next(x for x in st.splitlines() if x.startswith('State:')).split(':',1)[1].strip()
            valid = uid == os.getuid() and 'automacao_9b_vision_v1_4/orquestrar_9b.py start' in raw
            return (valid,valid and state.startswith(('T','t')))
        except (OSError,StopIteration):return (False,False)
