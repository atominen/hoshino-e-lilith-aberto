"""Persistência dos JSON de estado existentes, sem descartar conteúdo corrompido."""
import fcntl
import json
import os
import tempfile
import threading
from pathlib import Path
from core import diagnostics

_LOCK = threading.RLock()


def read(path, *, strict=False):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('Estado JSON não é um objeto.')
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        diagnostics.persistence_failure('state.read', path, exc, retry_safe=True)
        if strict:
            raise
        return {}


def update(path, mutate, operation='state.update'):
    """Read/modify/replace protegido. False NÃO é uma gravação bem-sucedida."""
    path = Path(path)
    temporary = None
    replaced = False
    try:
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.with_name(path.name + '.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                data = read(path, strict=True)
                mutate(data)
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                                 prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                replaced = True
                fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        return True
    except (OSError, ValueError, TypeError) as exc:
        diagnostics.persistence_failure(operation, path, exc, retry_safe=not replaced, committed=replaced)
        return False
    finally:
        if temporary is not None and not replaced:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                diagnostics.persistence_failure('state.cleanup_temporary', temporary, exc, retry_safe=True)
