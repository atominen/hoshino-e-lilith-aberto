"""Localização do executor, não da mente. Leitura não inicia serviços/rede."""
import json
from pathlib import Path

DESTINATIONS = {'local': 'Este PC', 'pc2': 'PC2 · CPU', 'xbox': 'Xbox Series S · GPU'}


def path(root):
    return Path(root)/'compartilhado/config/alistair_execution.json'


def settings(root):
    p = path(root)
    if p.is_symlink():
        raise ValueError('Seleção de executor não pode ser um link.')
    if p.exists():
        if p.stat().st_size > 16384:
            raise ValueError('Seleção de executor inválida.')
        value = json.loads(p.read_text())
    else:
        legacy = Path(root)/'compartilhado/config/alistair_pc2.json'
        pc2 = json.loads(legacy.read_text()) if legacy.is_file() else {}
        value = {'destination': 'pc2' if pc2.get('enabled') is True else 'local'}
    if not isinstance(value, dict) or set(value)-{'destination', 'xbox_ip', 'auto_start', 'auto_sync', 'trusted_lan'}:
        raise ValueError('Campos desconhecidos na localização do executor.')
    result = dict(destination='local', xbox_ip='10.0.0.103', auto_start=True, auto_sync=True, trusted_lan=False)
    result.update(value)
    if result['destination'] not in DESTINATIONS:
        raise ValueError('Destino de Alistair inválido.')
    for name in ('auto_start', 'auto_sync', 'trusted_lan'):
        if type(result[name]) is not bool:
            raise ValueError('Opção de execução inválida.')
    from pc2_protocol import lan_ip
    lan_ip(result['xbox_ip'])
    return result


def destination(root):
    return settings(root)['destination']


def is_remote(root):
    # Instalações legadas PC2 conservam seu fallback/local boot anterior.
    return path(root).exists() and destination(root) != 'local'
