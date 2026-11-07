"""Observador de um único comando; não importa nem inicializa a aplicação.

O comando recebido já contém o isolamento aplicado pelo executor. Este pai
apenas espera seu término real e publica um recibo atômico, inclusive quando
a Central deixa de esperar ou é reiniciada. Ausência de recibo não é sucesso.
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    receipt_path, job_id, *command = sys.argv[1:]
    # Mesma sessão/grupo do observador, mesmos descritores e isolamento do
    # comando original. O cancelamento continua abrangendo o grupo owned.
    try:
        child = subprocess.Popen(command)
    except OSError as error:
        receipt = {'started': False, 'code': None, 'error': str(error)}
    else:
        receipt = {'started': True, 'code': child.wait()}
    receipt.update(schema=1, job_id=job_id, pid=os.getpid(),
                   process_token=os.environ['HOSHINO_JOB_PROCESS_TOKEN'],
                   entity=os.environ['HOSHINO_JOB_ENTITY'],
                   project_root=os.environ['HOSHINO_JOB_ROOT'],
                   finished_at=datetime.now(timezone.utc).isoformat())
    atomic_json(receipt_path, receipt)


if __name__ == '__main__':
    main()
