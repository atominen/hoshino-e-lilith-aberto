#!/usr/bin/env python3
"""Retirada única do Qwen3-4B experimental, nunca do Qwen3.5-4B de Alistair.

Dry-run por padrão. Alvos pinados, sem prune global e com recibo antes de apagar.
"""
import argparse
import contextlib
import fcntl
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'app')]
from scripts.retirar_yi_20261024 import busy_files, safe, sha

ALIAS = 'hoshino-qwen3-4b-candidate-20261024'
MANIFEST = '98e3485ecc057eaa3602d104252f2cb6805c7eb101a37cf235ec0925edba7176'
WEIGHT = '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'
SHARDS = {
    'model-00001-of-00003.safetensors': '328a91d3122359d5547f9d79521205bc0a46e1f79a792dfe650e99fc2d651223',
    'model-00002-of-00003.safetensors': '6cd087b316306a68c562436b5492edbcf6e16c6dba3a1308279caa5a58e21ca5',
    'model-00003-of-00003.safetensors': 'e4bf436957184f4eeb86a80e9db394503f1f56446b2e6b7edeac5b81470f4ca1',
}


def inventory():
    source = safe(ROOT/'laboratorio-local/modelos-extras/qwen3-4b')
    if not source.is_dir():
        raise RuntimeError('Fonte ausente; não repetir remoção')
    if {p.name for p in source.iterdir()} != {'hf', 'gguf'}:
        raise RuntimeError('Conteúdo adicional inesperado; revisar antes de apagar')
    for p in source.rglob('*'):
        safe(p)
    marker = json.loads((source/'hf/lab_revision.json').read_text())
    if marker != dict(repo='Qwen/Qwen3-4B', revision='1cfa9a7208912126459214e8b04321603b3df60c'):
        raise RuntimeError('Fonte experimental mudou')
    if {p.name for p in (source/'hf').glob('*.safetensors')} != set(SHARDS):
        raise RuntimeError('Pesos extras/divergentes na fonte')
    store = ROOT/'compartilhado/modelos/ollama'
    manifest = safe(store/'manifests/registry.ollama.ai/library'/ALIAS/'latest')
    if sha(manifest) != MANIFEST:
        raise RuntimeError('Alias mudou; nada removido')
    data = json.loads(manifest.read_text())
    refs = {r['digest'] for r in [data['config'], *data['layers']]}
    keep, other_refs = {}, set()
    for other_store in (ROOT/'compartilhado/modelos').glob('ollama*'):
        safe(other_store)
        if not other_store.is_dir():
            continue
        for p in (other_store/'manifests').rglob('*'):
            safe(p)
            if not p.is_file() or p == manifest:
                continue
            value = json.loads(p.read_text())
            used = {r['digest'] for r in [value['config'], *value['layers']]}
            if 'sha256:'+WEIGHT in used:
                raise RuntimeError('Outro alias usa o peso experimental; revisar')
            keep[str(p)] = sha(p)
            if other_store == store:
                other_refs.update(used)
    blobs = [safe(store/'blobs'/r.replace(':', '-')) for r in sorted(refs-other_refs)]
    if not all(p.is_file() for p in blobs):
        raise RuntimeError('Blob ausente; estado incerto')
    weights = {source/'hf'/name: digest for name, digest in SHARDS.items()}
    weights[source/'gguf/Qwen3-4B-Q4_K_M.gguf'] = WEIGHT
    weights[store/'blobs'/('sha256-'+WEIGHT)] = WEIGHT
    files = [p for p in source.rglob('*') if p.is_file()] + [manifest, *blobs]
    records = []
    for p in files:
        s = p.stat()
        records.append(dict(path=str(p.relative_to(ROOT)), size=s.st_size,
                            allocated=s.st_blocks*512, device=s.st_dev, inode=s.st_ino))
    return source, manifest, blobs, weights, keep, records


def run(apply=False):
    from scripts.verificar_yi_basico import idle
    from core.central_control import atomic_save, revision
    home = ROOT/'laboratorio-local'
    registry = home/'controle-laboratorio/treinamento-unificado'
    receipt = registry/'reports/remocao-qwen3-4b-experimental-20261024.json'
    with contextlib.ExitStack() as stack:
        for p in (registry/'start.lock', home/'controle-laboratorio/trabalhador.lock',
                  *(ROOT/f'entidades/{e}/runtime/entity.lock' for e in ('hoshino', 'lilith', 'alistair'))):
            lock = stack.enter_context(p.open('a+'))
            fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        idle(ROOT, home)
        configs = [ROOT/'compartilhado/config/neural9b_modes.json',
                   *(ROOT/f'entidades/{e}/config/executores.json' for e in ('hoshino', 'lilith'))]
        if any('qwen3-4b' in p.read_text().lower() for p in configs):
            raise RuntimeError('Experimento ainda selecionado; nada removido')
        config_hashes = {str(p): sha(p) for p in configs}
        source, manifest, blobs, weights, keep, records = inventory()
        targets = [ROOT/r['path'] for r in records]
        busy_files(targets)
        summary = dict(apply=apply, files=len(records), allocated_bytes=sum(r['allocated'] for r in records))
        print(json.dumps(summary), flush=True)
        if not apply:
            return summary
        if receipt.exists():
            raise RuntimeError('Tentativa registrada; reconciliar, não repetir')
        for p, digest in weights.items():
            if sha(safe(p)) != digest:
                raise RuntimeError('Hash de peso divergente; nada removido')
        report = dict(schema=1, created_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                      applied=False, phase='targets_verified', files=records, manifest_sha256=MANIFEST,
                      allocated_bytes=summary['allocated_bytes'], other_manifests=keep,
                      configuration_sha256=config_hashes, memory_touched=False, training_started=False,
                      recovery='Sem backup dos pesos; recuperar por download da revisão original e importação.')
        atomic_save(receipt, json.dumps(report, ensure_ascii=False, indent=2)+'\n', revision(receipt))
        for r in records:
            s = (ROOT/r['path']).stat()
            if (s.st_dev, s.st_ino, s.st_size) != (r['device'], r['inode'], r['size']):
                raise RuntimeError('Alvo mudou; interrompido')
        idle(ROOT, home)
        busy_files(targets)
        manifest.unlink()
        for p in blobs:
            p.unlink()  # Somente refs exclusivas desse manifesto; nunca prune global.
        shutil.rmtree(source)  # Diretório experimental exato, pinado e sem links.
        if any(p.exists() for p in targets):
            raise RuntimeError('Remoção incompleta; reconciliar')
        for path, digest in {**keep, **config_hashes}.items():
            if sha(Path(path)) != digest:
                raise RuntimeError('Outro manifesto/configuração mudou; investigar')
        idle(ROOT, home)
        report.update(applied=True, phase='removed', other_manifests_and_configuration_unchanged=True)
        atomic_save(receipt, json.dumps(report, ensure_ascii=False, indent=2)+'\n', revision(receipt))
        print(json.dumps(dict(applied=True, allocated_bytes_removed=report['allocated_bytes'], receipt=str(receipt))), flush=True)
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    run(parser.parse_args().apply)
