"""Comparação isolada do mesmo LLM com e sem atenção aprendida."""
import argparse
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.request import Request, urlopen

from ensaiar_condicionamento_pestinha import episode

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'lilith-qwen3.5-4b-original-72ade0b11c3e:latest'
CASES = [
    ('oficina', 'background', 'A compilação acabou de falhar com o mesmo diagnóstico em três tentativas.', 'reavaliar'),
    ('som', 'background', 'Som ambiente habitual e repetido. Nenhuma tarefa ou pedido aguarda ação.', 'aguardar'),
    ('som', 'background', 'O mesmo som ambiente voltou. Continua sem novidade e sem tarefa pendente.', 'aguardar'),
    ('som', 'human', 'O mesmo som voltou, mas agora Gustavo pede explicitamente uma resposta sobre ele.', 'responder'),
    ('novo', 'background', 'Uma atividade própria inédita foi interrompida, sem confirmação do efeito.', 'observar'),
]
CHOICES = ['reavaliar', 'aguardar', 'responder', 'observar']


def attention(model, cue):
    probe = deepcopy(model)
    probe.set_cue(cue, True, 100)
    return probe.strength((cue,))


def benchmark(call, model, identity):
    runs = {}
    for mode in ('llm', 'associacao', 'associacao_e_filtro'):
        rows = []
        for cue, origin, description, expected in CASES:
            score = attention(model, cue)
            # Apenas sinais ambientais conhecidos e repetidos são elegíveis.
            if mode == 'associacao_e_filtro' and origin == 'background' and cue == 'som' and score < 0.15:
                rows.append(dict(cue=cue, expected=expected, decision='aguardar', reason='Ruído ambiental repetido.',
                                 called=False, prompt_tokens=0, output_tokens=0, seconds=0))
                continue
            if mode == 'llm':
                context = {'oficina': '12 repetições seguidas foram associadas a novos fracassos.',
                           'som': '12 ocorrências passadas não antecederam evento que exigisse atenção.',
                           'novo': 'Sem exemplos anteriores.'}[cue]
            else:
                context = (f'Associação aprendida com resultado relevante: {score:.3f} de 1. '
                           f'Amostras anteriores: {0 if cue == "novo" else 12}.')
            row = call(identity, f'Origem: {origin}. Situação: {description}\nExperiência anterior: {context}')
            rows.append(dict(cue=cue, expected=expected, called=True, **row))
        runs[mode] = dict(calls=sum(r['called'] for r in rows), correct=sum(r['decision'] == r['expected'] for r in rows),
                          prompt_tokens=sum(r['prompt_tokens'] for r in rows),
                          output_tokens=sum(r['output_tokens'] for r in rows),
                          seconds=round(sum(r['seconds'] for r in rows), 3), rows=rows)
    assert all(run['rows'][3]['called'] for run in runs.values()), 'Pedido humano não pode ser filtrado.'
    return runs


def local_model(temporary, conditioning, *, run=benchmark, choices=CHOICES, instructions=None,
                evidence_required=False, model_name=MODEL, gpu_layers=0):
    name, tag = model_name.split(':', 1)
    original = ROOT / 'compartilhado/modelos/ollama-lilith'
    relative = Path('manifests/registry.ollama.ai/library') / name / tag
    store = temporary / 'models'
    (store / relative).parent.mkdir(parents=True)
    shutil.copyfile(original / relative, store / relative)
    manifest = json.loads((store / relative).read_text())
    (store / 'blobs').mkdir()
    for entry in [manifest['config'], *manifest['layers']]:
        blob = entry['digest'].replace(':', '-')
        source = original / 'blobs' / blob
        if not source.is_file():
            raise FileNotFoundError(blob)
        target = store / 'blobs' / blob
        if not target.exists():
            target.symlink_to(source.resolve())
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, OLLAMA_HOST=f'127.0.0.1:{port}', OLLAMA_MODELS=str(store),
               OLLAMA_NO_CLOUD='1', OLLAMA_NOPRUNE='true', OLLAMA_NUM_PARALLEL='1')
    if gpu_layers:
        env['OLLAMA_VULKAN'] = '1'
    base = f'http://127.0.0.1:{port}'
    persona = json.loads((ROOT / 'entidades/lilith/identity/self_model.json').read_text())
    identity = persona['identity']['self_concept'] + '\nTraços: ' + ', '.join(persona['personality']['traits'])
    with (temporary / 'ollama.log').open('wb') as log:
        service = subprocess.Popen(['ollama', 'serve'], env=env, stdout=log, stderr=log)
        try:
            for _ in range(120):
                if service.poll() is not None:
                    raise RuntimeError('O executor temporário encerrou antes de responder.')
                try:
                    with urlopen(base + '/api/version', timeout=1):
                        break
                except OSError:
                    time.sleep(.25)
            else:
                raise TimeoutError('Executor temporário indisponível.')

            gpu_residency = None

            def call(system, situation, *, allowed_choices=None, extra_fields=None, evidence_ids=None,
                     reply_only=False):
                nonlocal gpu_residency
                if reply_only:
                    properties = {'reply': {'type': 'string'}}
                else:
                    properties = {'decision': dict(type='string', enum=allowed_choices or choices),
                                  'reason': dict(type='string')}
                    if evidence_required:
                        properties['evidence_id'] = dict(type='string')
                        if evidence_ids is not None:
                            properties['evidence_id']['enum'] = list(evidence_ids)
                    properties.update(extra_fields or {})
                payload = dict(model=model_name, think=False, stream=False,
                               options=dict(num_gpu=gpu_layers, num_ctx=2048, temperature=0,
                                            num_predict=192 if reply_only or extra_fields else 144 if evidence_required else 72),
                               format=dict(type='object', properties=properties, required=list(properties)),
                               messages=[dict(role='system', content=system + (instructions or (
                                   '\nDecida em português. Reavaliar = mudar estratégia após falhas; aguardar = deixar passar '
                                   'ruído sem pendência; responder = atender pedido humano; observar = verificar um efeito incerto. '
                                   'Escolha uma opção e justifique em uma frase curta com um fato da situação.'))),
                                   dict(role='user', content=situation)])
                started = time.monotonic()
                request = Request(base + '/api/chat', json.dumps(payload).encode(), {'Content-Type': 'application/json'})
                with urlopen(request, timeout=90) as response:
                    result = json.load(response)
                if gpu_layers and gpu_residency is None:
                    with urlopen(base + '/api/ps', timeout=5) as response:
                        loaded = json.load(response)['models']
                    gpu_residency = next((model for model in loaded if model['name'] == model_name), None)
                    if not gpu_residency or not gpu_residency.get('size_vram'):
                        raise RuntimeError('O modelo não apresentou residência em VRAM no executor temporário.')
                content = result['message']['content']
                try:
                    answer = json.loads(content)
                except ValueError:
                    answer = {'decision': 'inválida', 'reason': content}
                return dict(**{name: answer.get(name) for name in properties},
                            **({'allowed_evidence_ids': list(evidence_ids)} if evidence_ids is not None else {}),
                            **({'done_reason': result.get('done_reason')} if reply_only else {}),
                            prompt_tokens=result.get('prompt_eval_count', 0),
                            output_tokens=result.get('eval_count', 0), seconds=round(time.monotonic()-started, 3))

            report = run(call, conditioning, identity)
            if gpu_residency and isinstance(report, dict):
                report['execution'] = dict(model=model_name, gpu_layers_requested=gpu_layers,
                                           size=gpu_residency['size'], size_vram=gpu_residency['size_vram'])
            return report
        finally:
            service.terminate()
            try:
                service.wait(timeout=10)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.upstream.resolve()))
    model = importlib.import_module('pestinha.core.conditioning').Conditioning()
    for i in range(12):
        episode(model, 'oficina', True, i * 6)
        episode(model, 'som', False, i * 6 + 3)
    with TemporaryDirectory(prefix='pestinha-llm-') as directory:
        print(json.dumps(local_model(Path(directory), model), indent=2, ensure_ascii=False))
