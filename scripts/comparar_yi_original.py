#!/usr/bin/env python3
"""Diagnóstico explícito, local e isolado; nunca habilita/treina/converte o Yi.

No controle CPU, os pesos BF16 ficam intactos em RAM e cada Linear calcula
temporariamente em FP32. --backend nf4 é um controle separado: carregamento
4-bit diretamente dos originais, com embedding/head CPU e camadas GPU, sem
adaptador ou treino. O pai detém locks/RM até a saída real do filho owned.
"""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'app')]
MARKER = 'yi_diagnostic'


def emit(kind, **values):
    print(json.dumps({MARKER: kind, **values}, ensure_ascii=False), flush=True)


def cpu_temperatures():
    """Somente leitura do sensor do CPU usado neste ensaio, sem ajustes."""
    values = {}
    for name in Path('/sys/class/hwmon').glob('hwmon*/name'):
        if name.read_text().strip() not in ('k10temp', 'coretemp'):
            continue
        for sensor in name.parent.glob('temp*_input'):
            value = float(sensor.read_text())/1000
            if not 0 < value < 150:
                raise RuntimeError('Sensor CPU inválido')
            values[str(sensor)] = value
    if not values:
        raise RuntimeError('Sensor CPU indisponível para o ensaio CPU')
    return values


def owned_swap_bytes(pid):
    """Não confundir pageamento do desktop com uso de swap deste filho."""
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith('VmSwap:'):
            return int(line.split()[1])*1024
    raise RuntimeError('Pageamento do filho owned não observável')


def worker():
    """Sem acesso ao chat/memórias; somente pesos locais e casos sintéticos."""
    import types
    import numpy as np
    import sentencepiece as spm
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, BitsAndBytesConfig
    from scripts.verificar_yi_basico import cases, basic_check
    from scripts.preparar_executores_leves import NEUTRAL_SYSTEM
    from core.yi_companion import native_prompt
    sys.path.insert(0, str(ROOT/'laboratorio-local/llama.cpp/gguf-py'))
    from gguf import GGUFReader, dequantize

    spec = json.loads(sys.stdin.read())
    nf4 = spec.get('backend') == 'nf4'
    base = Path(spec['source']['base'])
    torch.set_num_threads(6)
    torch.manual_seed(42)
    tokenizer = AutoTokenizer.from_pretrained(base, use_fast=False,
        local_files_only=True, trust_remote_code=False)
    sp = spm.SentencePieceProcessor(model_file=str(base/'tokenizer.model'))
    system = (NEUTRAL_SYSTEM+'\nEnsaio sintético isolado, sem experiências humanas reais. '
        'Meu nome neste contexto é Hoshino. Não invento lembranças de informações não fornecidas.')
    inputs = dict(cases('hoshino'))
    renderings = {}
    for name in ('portuguese', 'context'):
        messages = [dict(role='system', content=system), *inputs[name]]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        hf_ids = tokenizer.apply_chat_template(messages, tokenize=True,
            add_generation_prompt=True, return_dict=False)
        renderings[name] = dict(messages=messages, text=text, manual_native_equal=text==native_prompt(messages),
            sentencepiece_ids=sp.encode(text), installed_auto_ids=hf_ids)
    g = GGUFReader(spec['gguf'])
    tokens = g.fields['tokenizer.ggml.tokens'].contents()
    differences = [i for i in range(sp.vocab_size()) if str(tokens[i]) != sp.id_to_piece(i)]
    token_check = dict(installed_class=type(tokenizer).__name__, installed_is_fast=tokenizer.is_fast,
        transformers_version=__import__('transformers').__version__, sentencepiece_vocab=sp.vocab_size(),
        installed_vocab=len(tokenizer), gguf_vocab=len(tokens), gguf_sp_piece_differences=differences,
        im_start_sentencepiece=sp.encode('<|im_start|>'),
        im_start_installed=tokenizer.encode('<|im_start|>', add_special_tokens=False),
        eos_tokenizer=tokenizer.eos_token_id, eos_model=json.loads((base/'config.json').read_text())['eos_token_id'])
    emit('tokenizer', details=token_check, renderings=renderings)
    begin = time.monotonic()
    kwargs = dict(dtype=torch.bfloat16,device_map={'': 'cpu'},low_cpu_mem_usage=True,
        local_files_only=True,trust_remote_code=False,attn_implementation='sdpa')
    if nf4:
        from laboratorio.treino_nf4_curto import frozen_offload, pin_cpu_embedding, pin_cpu_head
        os.environ.pop('HSA_OVERRIDE_GFX_VERSION',None)
        if not torch.version.hip or not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(including_emulation=False):
            raise RuntimeError('Controle NF4 requer ROCm/BF16 nativo; sem override/fallback')
        embedding_cpu,mapping,allowed = frozen_offload('llama',base.name,True)
        kwargs.update(device_map=mapping,quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,llm_int8_enable_fp32_cpu_offload=True))
    model = AutoModelForCausalLM.from_pretrained(base, **kwargs)
    model.eval().requires_grad_(False)
    if nf4:
        if any(p.device.type!='cuda' and not n.startswith(allowed) for n,p in model.named_parameters()):
            raise RuntimeError('Offload NF4 divergente; sem migração de camadas')
        if not embedding_cpu:
            raise RuntimeError('Offload Yi embedding/head não confirmado')
        pin_cpu_embedding(model)
        pin_cpu_head(model)
    elif any(p.device.type!='cpu' or p.dtype!=torch.bfloat16 for p in model.parameters()):
        raise RuntimeError('Modelo fora do contrato CPU/BF16; não prosseguir')
    emit('loaded', seconds=time.monotonic()-begin, parameter_bytes=sum(p.numel()*p.element_size() for p in model.parameters()))

    # Só diagnóstico: verificar a relação entre os tensores convertidos e a base.
    mapping = {t.name: t for t in g.tensors}
    correlations = []
    tensor_cases = () if nf4 else (
        ('blk.0.attn_q.weight', model.model.layers[0].self_attn.q_proj.weight, 32),
        ('blk.0.attn_k.weight', model.model.layers[0].self_attn.k_proj.weight, 4),
        ('blk.0.attn_v.weight', model.model.layers[0].self_attn.v_proj.weight, None))
    for name, original, heads in tensor_cases:
        tensor = mapping[name]
        converted = dequantize(tensor.data, tensor.tensor_type).reshape(original.shape).ravel()
        source = original.float().numpy()
        def similarity(value):
            value = value.ravel()
            return float(np.dot(converted, value)/(np.linalg.norm(converted)*np.linalg.norm(value)))
        row = dict(tensor=name, type=str(tensor.tensor_type), direct_cosine=similarity(source))
        if heads:
            permuted = source.reshape(heads, 2, source.shape[0]//heads//2, source.shape[1]).swapaxes(1,2).reshape(source.shape)
            row['hf_to_llama_permuted_cosine'] = similarity(permuted)
        correlations.append(row)
    emit('tensor_sample', details=correlations)
    del g, mapping

    def fp32_linear(self, value):
        return torch.nn.functional.linear(value.float(), self.weight.float(),
            None if self.bias is None else self.bias.float())
    count = 0
    for module in model.modules():
        if not nf4 and isinstance(module, torch.nn.Linear):
            module.forward = types.MethodType(fp32_linear, module)
            count += 1
    emit('execution', backend='nf4_gpu' if nf4 else 'cpu', weights_dtype='nf4' if nf4 else 'bfloat16',
        linear_compute='native_bfloat16_gpu_head_fp32_cpu' if nf4 else 'float32_temporary',
        head_cpu=nf4,linear_modules=count,quantization=nf4,
        allocated_vram=torch.cuda.memory_allocated() if nf4 else 0)

    class Deadline(StoppingCriteria):
        def __init__(self):
            self.until = time.monotonic()+240
            self.expired = False
        def __call__(self, input_ids, scores, **kwargs):
            self.expired = time.monotonic() >= self.until
            return torch.full((input_ids.shape[0],), self.expired, device=input_ids.device, dtype=torch.bool)

    # Casos iguais aos controles GGUF. O terceiro isola o tokenizer instalado.
    chosen = (('context','sentencepiece'),('portuguese','sentencepiece'),('context','installed_auto')) if nf4 else (
        ('portuguese','sentencepiece'),('context','sentencepiece'),('context','installed_auto'))
    for name, encoding in chosen:
        record = renderings[name]
        ids = record['sentencepiece_ids' if encoding=='sentencepiece' else 'installed_auto_ids']
        x = torch.tensor([ids], dtype=torch.long,device='cuda' if nf4 else 'cpu')
        begin = time.monotonic()
        deadline = Deadline()
        with torch.inference_mode():
            result = model.generate(input_ids=x, attention_mask=torch.ones_like(x),
                max_new_tokens=96, do_sample=False, use_cache=True,
                eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id,
                stopping_criteria=[deadline], logits_to_keep=1)
        generated = result[0, len(ids):].tolist()
        done = bool(generated and generated[-1]==tokenizer.eos_token_id)
        body = generated[:-1] if done else generated
        answer = (sp.decode(body) if encoding=='sentencepiece' else tokenizer.decode(body, skip_special_tokens=True)).strip()
        row = dict(id=name, encoding=encoding, answer=answer, prompt_tokens=len(ids),
            answer_tokens=len(generated), generated_ids=generated, seconds=time.monotonic()-begin,
            done=done, done_reason='stop' if done else 'deadline' if deadline.expired else 'length',
            basic_check_passed=done and basic_check(name,answer,'hoshino'))
        emit('case', **row)
        if not done:
            raise RuntimeError('Resposta incompleta; sem retry nem ampliação de orçamento')
    if nf4:
        torch.cuda.synchronize()
    emit('complete')


def run(output, backend='cpu'):
    import config
    from core import gpu_metrics, neural9b_modes as modes, resource_manager as rm
    from core.central_control import atomic_save, revision
    from core.yi_companion import receipt_path
    from laboratorio import recuperacao_modelos as recovery
    from laboratorio.treino_nf4_curto import sample_hardware, physical_pressure, thermal_pressure
    from scripts.verificar_yi_basico import idle
    project = Path(config.RAIZ).resolve()
    if project!=ROOT or config.ENTIDADE_ID!='hoshino':
        raise RuntimeError('Ambiente inesperado; usar entidade de diagnóstico Hoshino')
    home = project/'laboratorio-local'
    target = receipt_path(project, output)
    if target.exists():
        raise RuntimeError('Preservar recibo existente; nunca repetir automaticamente')
    report = dict(schema=1, scope='diagnostic_only', created_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        backend=backend, training_started=False, memory_written=False, download=False,
        activation=False, weights_modified=False, quantization=backend=='nf4', events=[], physical={}, cleanup={},
        phase='attempt_recorded', completed=False, quality_approved=False,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    # Durável ANTES de carregar pesos/criar processo. Uma queda não autoriza
    # repetir um ensaio sem desfecho: a guarda de recibo existente o recusa.
    save_lock = threading.RLock()
    def persist():
        with save_lock:
            atomic_save(target,json.dumps(report,ensure_ascii=False,indent=2)+'\n',revision(target))
    persist()
    process = None
    samples = []
    pressure = []
    error = None
    registry = home/'controle-laboratorio/treinamento-unificado'
    with contextlib.ExitStack() as locks:
        for path in (registry/'start.lock', home/'controle-laboratorio/trabalhador.lock',
                     project/'entidades/hoshino/runtime/entity.lock', project/'entidades/lilith/runtime/entity.lock'):
            file = locks.enter_context(path.open('a+'))
            fcntl.flock(file, fcntl.LOCK_EX|fcntl.LOCK_NB)
        idle(project, home)
        source = recovery._base_info(home,'yi-6b')
        recovery.verify_source(source)
        report['source'] = source
        selected = modes.selected_version(project,'hoshino','yi-6b')
        if not selected or selected['kind']!='original':
            raise RuntimeError('Controle GGUF não está nos originais')
        manifest_path = recovery.manifest_path(recovery.store(project,'hoshino'), selected['alias'])
        manifest = json.loads(manifest_path.read_text())
        gguf = recovery.store(project,'hoshino')/'blobs'/next(
            layer['digest'].replace(':','-') for layer in manifest['layers'] if layer['mediaType'].endswith('.model'))
        record = recovery.inspect_gguf(home,gguf,'llama')
        recovery.validate_main_layout(source,record)
        if 'sha256:'+record['sha256'] != next(layer['digest'] for layer in manifest['layers'] if layer['mediaType'].endswith('.model')):
            raise RuntimeError('Hash GGUF divergente')
        report['gguf'] = record
        if gpu_metrics.ram_available()<20*gpu_metrics.GIB:
            raise RuntimeError('RAM insuficiente para controle BF16 sem swap')
        report['phase'] = 'preflight_passed'
        persist()
        try:
            with rm.compute_lease('llm',entity='hoshino',model_key='diagnostic_'+backend+'|yi-original',priority=5,
                    vram_bytes=5*gpu_metrics.GIB,workspace_bytes=512*1024**2,cpu_fallback=False,wait=30):
                initial = sample_hardware(gpu_metrics.snapshot(),gpu_metrics.ram_available())
                samples.append(initial)
                reason = thermal_pressure(initial) or physical_pressure(gpu_metrics.snapshot(),initial['ram_available'],rm.gpu_policy()['margin_bytes'])
                if reason:
                    raise RuntimeError(reason)
                initial['cpu_temperatures_c'] = cpu_temperatures()
                if max(initial['cpu_temperatures_c'].values()) >= 85:
                    raise RuntimeError('CPU já aquecido; ensaio não iniciado')
                env = {k:v for k,v in os.environ.items() if not k.startswith(('HOSHINO_','OLLAMA_'))}
                env.update(HOSHINO_ENTIDADE='hoshino',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
                    HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='6',
                    OPENBLAS_NUM_THREADS='1')
                env.pop('HSA_OVERRIDE_GFX_VERSION',None)
                if backend=='cpu':
                    env.update(ROCR_VISIBLE_DEVICES='',HIP_VISIBLE_DEVICES='',CUDA_VISIBLE_DEVICES='')
                else:
                    from laboratorio.treino_nf4_curto import idle_metrics
                    idle_metrics(gpu_metrics)
                process = subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--worker'],
                    cwd=project,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,start_new_session=True)
                report['pid'] = process.pid
                report['pid_start_stamp'] = Path(f'/proc/{process.pid}/stat').read_text().rsplit(')',1)[1].split()[19]
                report['phase'] = 'child_created'
                persist()
                process.stdin.write(json.dumps(dict(source=source,gguf=str(gguf),backend=backend)))
                process.stdin.close()
                def drain():
                    for line in process.stdout:
                        try:
                            event = json.loads(line)
                        except (ValueError, TypeError):
                            # Logs técnicos, nunca mensagens de entidades.
                            if line.strip():
                                report.setdefault('runtime_log',[]).append(line.strip()[-2000:])
                            continue
                        if isinstance(event,dict) and MARKER in event:
                            with save_lock:
                                report['events'].append(event)
                                persist()
                            if event[MARKER] in ('loaded','execution','case','complete'):
                                print(json.dumps(event,ensure_ascii=False),flush=True)
                reader = threading.Thread(target=drain,daemon=True)
                reader.start()
                until = time.monotonic()+900
                try:
                    while process.poll() is None:
                        sample = sample_hardware(gpu_metrics.snapshot(),gpu_metrics.ram_available())
                        sample['cpu_temperatures_c'] = cpu_temperatures()
                        try:
                            sample['child_swap_bytes'] = owned_swap_bytes(process.pid)
                        except FileNotFoundError:
                            if process.poll() is not None:
                                break
                            raise
                        samples.append(sample)
                        reason = thermal_pressure(sample) or physical_pressure(gpu_metrics.snapshot(),sample['ram_available'],rm.gpu_policy()['margin_bytes'])
                        if max(sample['cpu_temperatures_c'].values()) >= 85:
                            reason = reason or 'CPU atingiu85°C; encerrar somente o filho diagnóstico'
                        if sample['child_swap_bytes']>0:
                            reason = reason or 'Filho diagnóstico usou swap; encerrar sem ampliar RAM'
                        if time.monotonic()>=until:
                            reason = reason or 'Prazo diagnóstico de900s atingido'
                        if reason:
                            pressure.append(reason)
                            raise RuntimeError(reason)
                        time.sleep(.5)
                finally:
                    # Somente o filho criado aqui; nenhum processo de entidade/porta.
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                    process.wait()
                    reader.join(timeout=10)
                    report['cleanup']['real_exit_code'] = process.returncode
                    report['cleanup']['child_exited_before_lease_release'] = process.poll() is not None
                if process.returncode!=0:
                    raise RuntimeError('Controle original encerrou sem completar: exit '+str(process.returncode))
        except Exception as exc:
            error = exc
            report['error'] = str(exc)
        finally:
            report['cleanup']['lease_released'] = not rm.status('gpu')
            report['cleanup']['gpu_queue_empty'] = not rm.gpu_state()['queue']
            report['physical'] = dict(pressure=pressure,sample_count=len(samples),
                ram_min_bytes=min((s['ram_available'] for s in samples),default=None),
                vram_max_bytes=max((s['vram_bytes'] or 0 for s in samples),default=None),
                swap_max_bytes=max((s['swap_used'] for s in samples),default=None),
                child_swap_max_bytes=max((s.get('child_swap_bytes',0) for s in samples),default=None),
                cpu_temperature_max_c=max((v for s in samples for v in s.get('cpu_temperatures_c',{}).values()),default=None),
                temperature_max_c={k:max(s['temperatures_c'].get(k,0) for s in samples)
                    for k in {k for s in samples for k in s['temperatures_c']}},
                before=samples[0] if samples else None,after=sample_hardware(gpu_metrics.snapshot(),gpu_metrics.ram_available()))
            recovery.verify_source(source)
            report['cleanup']['source_hashes_preserved'] = True
            idle(project,home)
            report['cleanup']['entities_and_jobs_idle'] = True
            report['completed'] = error is None and any(e[MARKER]=='complete' for e in report['events'])
            report['phase'] = 'completed' if report['completed'] else 'failed_or_interrupted'
            report['quality_approved'] = False  # Diagnóstico não é homologação/ativação.
            persist()
    emit('receipt',path=str(target),completed=report['completed'],cleanup=report['cleanup'])
    if error:
        raise error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--backend',choices=('cpu','nf4'),default='cpu')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker()
    elif args.run and args.output:
        run(args.output,args.backend)
    else:
        parser.error('Requer --run --output na área de ensaios; sem execução implícita')


if __name__=='__main__':
    main()
