"""Sondas somente leitura; a capacidade física é distinta do orçamento doRM."""
from pathlib import Path
import time

GIB = 1024 ** 3
HARD_LIMIT = 8 * GIB


def dedicated_capacity(root='/sys/class/drm'):
    """Maior VRAM de uma placa; nunca soma RAM, swap ou placas distintas.

    Esta sonda serve à admissão de entidades. Não altera o teto/telemetria
    validada doRM. NVIDIA é consultada porCLI local se já estiver instalada.
    """
    import csv
    import io
    import shutil
    import subprocess
    cards = []
    for card in Path(root).glob('card[0-9]*'):
        if '-' in card.name:
            continue
        device = card/'device'
        try:
            if (device/'vendor').read_text().strip().lower() not in {'0x1002','0x10de'}:
                continue
            total = int((device/'mem_info_vram_total').read_text())
            if total > 0:
                cards.append(dict(total_bytes=total, device=str(device), source='drm/sysfs'))
        except (OSError,ValueError):
            continue
    executable = shutil.which('nvidia-smi')
    if executable:
        try:
            result = subprocess.run([executable,'--query-gpu=uuid,name,memory.total',
                                     '--format=csv,noheader,nounits'],
                                    capture_output=True,text=True,check=True,timeout=3)
            for row in csv.reader(io.StringIO(result.stdout)):
                if len(row) != 3:
                    continue
                try: total = int(row[2].strip()) * 1024**2
                except ValueError: continue
                if total > 0:
                    cards.append(dict(total_bytes=total, device=row[0].strip(),
                                      name=row[1].strip(), source='nvidia-smi'))
        except (OSError,subprocess.SubprocessError):
            pass
    return dict(known=bool(cards), observed_at=time.time(),
                **(max(cards,key=lambda c:c['total_bytes']) if cards else {'total_bytes':None}))


def snapshot(root='/sys/class/drm'):
    out = dict(known=False, stable=False, source='amdgpu/sysfs', observed_at=time.time(),
               total_bytes=HARD_LIMIT, used_bytes=None, utilization=None)
    try:
        cards = []
        for card in Path(root).glob('card[0-9]*'):
            if '-' in card.name:
                continue
            device = card / 'device'
            if (device / 'vendor').read_text().strip().lower() != '0x1002':
                continue
            total = int((device / 'mem_info_vram_total').read_text())
            if total > 0:
                cards.append((total, device))
        if not cards:
            return out
        total, device = max(cards, key=lambda item: item[0])
        first = int((device / 'mem_info_vram_used').read_text())
        try:
            utilization = int((device / 'gpu_busy_percent').read_text())
            if not 0 <= utilization <= 100:
                utilization = None
        except (OSError, ValueError):
            utilization = None
        last = int((device / 'mem_info_vram_used').read_text())
        if not 0 <= first <= total or not 0 <= last <= total:
            return out
        out.update(known=True, stable=abs(first-last) <= 128 * 1024 ** 2,
                   total_bytes=min(total, HARD_LIMIT), used_bytes=max(first, last),
                   utilization=utilization, device=str(device))
        return out
    except (OSError, ValueError):
        return out


def ram_available(path='/proc/meminfo'):
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith('MemAvailable:'):
                return max(0, int(line.split()[1]) * 1024)
    except (OSError, ValueError, IndexError):
        pass
    return None  # Sem swap não apostamos em RAM desconhecida.


def ram_total(path='/proc/meminfo'):
    """RAM física, nunca RAM+swap; ausência não é capacidade zero confirmada."""
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith('MemTotal:'):
                value = int(line.split()[1]) * 1024
                return value if value > 0 else None
    except (OSError, ValueError, IndexError):
        pass
    return None
