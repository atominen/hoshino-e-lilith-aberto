#!/usr/bin/env python3
"""Ensaio opt-in dos originais podados; sem treino, chat, conversão ou ativação.

Arquitetura remota revisada por hash, filho owned, NF4 diagnóstico, embedding
CPU e camadas/head GPU. Não é benchmark pareado de Ollama nem perfil aprovado.
"""
import argparse
import contextlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'app')]
MARKER='qwen3_sniper_diagnostic'
MODEL_ID='qwen3-6b-sniper'


def generation_options(mode):
    if mode=='greedy':return dict(do_sample=False)
    if mode=='qwen':return dict(do_sample=True,temperature=.7,top_p=.8,top_k=20,min_p=0.)
    raise ValueError('Perfil de amostragem desconhecido')


def observed_swap(process,read_swap):
    """Zombie já encerrado pode não expor VmSwap; nunca relaxar filho ativo."""
    try:return read_swap(process.pid)
    except (FileNotFoundError,RuntimeError) as exc:
        if process.poll() is not None:return None
        # O kernel pode retirar o mm/VmSwap instantes antes de publicar exit.
        # Espera curta e bounded; um filho ainda ativo continua sendo bloqueado.
        try:process.wait(timeout=.2)
        except subprocess.TimeoutExpired:raise exc
        return None


def emit(event,**values):
    print(json.dumps({MARKER:event,**values},ensure_ascii=False),flush=True)


def worker():
    import torch
    from transformers import AutoTokenizer, BitsAndBytesConfig
    from laboratorio.catalogo import BY_ID
    from laboratorio.treino_nf4_curto import pin_cpu_embedding
    from scripts.retirar_yi_20261024 import sha
    from scripts.verificar_yi_basico import cases,basic_check
    from scripts.preparar_executores_leves import NEUTRAL_SYSTEM
    spec=json.loads(sys.stdin.read());base=Path(spec['base'])
    source=base/'modeling_pruned.py'
    if sha(source)!=BY_ID[MODEL_ID]['source_files'][source.name]:raise RuntimeError('Código auditado divergente')
    os.environ.pop('HSA_OVERRIDE_GFX_VERSION',None)
    if not torch.version.hip or not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(including_emulation=False):
        raise RuntimeError('ROCm/BF16 nativo indisponível; sem fallback/override')
    torch.set_num_threads(6);torch.manual_seed(42)
    module_spec=importlib.util.spec_from_file_location('audited_qwen3_sniper',source)
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    tokenizer=AutoTokenizer.from_pretrained(base,local_files_only=True,trust_remote_code=False)
    if tokenizer.eos_token_id!=151645 or tokenizer.encode('<|im_start|>',add_special_tokens=False)!=[151644]:
        raise RuntimeError('Tokens de diálogo divergentes')
    begin=time.monotonic()
    model=module.PrunedQwen3ForCausalLM.from_pretrained(base,local_files_only=True,trust_remote_code=False,
        dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa',
        device_map={'model.embed_tokens':'cpu','model.layers':0,'model.norm':0,'lm_head':0},
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16,
            llm_int8_skip_modules=['lm_head'],llm_int8_enable_fp32_cpu_offload=True))
    model.eval().requires_grad_(False)
    allowed=('model.embed_tokens.',)
    if len(model.model.layers)!=34 or any(p.device.type!='cuda' and not n.startswith(allowed) for n,p in model.named_parameters()):
        raise RuntimeError('Layout/offload diferente do auditado')
    pin_cpu_embedding(model)
    head=model.get_output_embeddings().weight
    if head.device.type!='cuda' or head.dtype!=torch.bfloat16:raise RuntimeError('Head GPU/BF16 não confirmado')
    emit('loaded',seconds=time.monotonic()-begin,decoder_layers=len(model.model.layers),
         transformers=__import__('transformers').__version__,torch=torch.__version__,
         cuda_allocated=torch.cuda.memory_allocated(),cuda_reserved=torch.cuda.memory_reserved(),head_gpu_bfloat16=True,
         eos_token=tokenizer.eos_token_id,im_start=151644)
    class Deadline(__import__('transformers').StoppingCriteria):
        def __init__(self):self.until=time.monotonic()+90;self.expired=False
        def __call__(self,input_ids,scores,**kwargs):
            self.expired=time.monotonic()>=self.until
            return torch.full((input_ids.shape[0],),self.expired,device=input_ids.device,dtype=torch.bool)
    rows=[('hoshino',name,messages) for name,messages in cases('hoshino')]
    rows.append(('lilith','identity',cases('lilith')[0][1]))
    eos=model.generation_config.eos_token_id
    eos=[eos] if isinstance(eos,int) else eos
    if set(eos)!={151645,151643}:raise RuntimeError('EOS nativo divergente')
    for entity,name,messages in rows:
        system=NEUTRAL_SYSTEM+'\nEnsaio sintético isolado. Meu nome neste contexto é '+entity.capitalize()+'. Não invento lembranças de informações não fornecidas.'
        rendered=tokenizer.apply_chat_template([dict(role='system',content=system),*messages],
            tokenize=False,add_generation_prompt=True,enable_thinking=False)
        x=tokenizer(rendered,add_special_tokens=False,return_tensors='pt').to('cuda')
        deadline=Deadline();begin=time.monotonic()
        with torch.inference_mode():
            result=model.generate(**x,max_new_tokens=128,use_cache=True,
                **generation_options(spec['sampling']),eos_token_id=eos,pad_token_id=151643,
                stopping_criteria=[deadline],logits_to_keep=1)
        torch.cuda.synchronize()
        generated=result[0,x['input_ids'].shape[-1]:].tolist()
        done=bool(generated and generated[-1] in eos)
        answer=tokenizer.decode(generated,skip_special_tokens=True).strip()
        if '<think' in answer.casefold() or '</think' in answer.casefold():
            raise RuntimeError('Thinking inesperado no perfil rápido; não registrar conteúdo')
        emit('case',entity=entity,id=name,answer=answer,done=done,
             done_reason='stop' if done else 'deadline' if deadline.expired else 'length',
             prompt_tokens=x['input_ids'].shape[-1],answer_tokens=len(generated),seconds=time.monotonic()-begin,
             final_token_id=generated[-1] if generated else None,automatic_pass=done and basic_check(name,answer,entity))
        if not done:raise RuntimeError('Resposta incompleta; sem retry ou aumento de teto')
    torch.cuda.synchronize()
    emit('complete',cuda_peak_allocated=torch.cuda.max_memory_allocated(),cuda_peak_reserved=torch.cuda.max_memory_reserved())


def run(output,sampling='qwen'):
    import config
    from core import gpu_metrics,resource_manager as rm
    from core.central_control import atomic_save,revision
    from core.yi_companion import receipt_path
    from laboratorio.catalogo import BY_ID
    from laboratorio.candidatos import validate_local
    from laboratorio.treino_nf4_curto import sample_hardware,physical_pressure,thermal_pressure,idle_metrics
    from scripts.retirar_yi_20261024 import sha
    from scripts.verificar_yi_basico import idle
    from scripts.comparar_yi_original import cpu_temperatures,owned_swap_bytes
    if Path(config.RAIZ).resolve()!=ROOT or config.ENTIDADE_ID!='hoshino':raise RuntimeError('Ambiente inesperado')
    home=ROOT/'laboratorio-local';base=home/'modelos-extras'/MODEL_ID/'hf'
    target=receipt_path(ROOT,output)
    if target.exists():raise RuntimeError('Tentativa existente; reconciliar, nunca repetir automaticamente')
    spec=BY_ID[MODEL_ID];events=[];samples=[];pressure=[];process=None;error=None
    report=dict(schema=1,scope='diagnostic_only',model=MODEL_ID,backend='hf_nf4_rocm_embedding_cpu',
        created_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),events=events,phase='attempt_recorded',
        activation=False,memory_written=False,training_started=False,weights_modified=False,
        completed=False,production_approved=False,semantic_review=dict(completed=False,passed=False),
        sampling=dict(profile=sampling,seed=42,**generation_options(sampling)),eos_token_ids=[151645,151643],
        physical={},cleanup={},boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    mutex=threading.RLock()
    def save():
        with mutex:atomic_save(target,json.dumps(report,ensure_ascii=False,indent=2)+'\n',revision(target))
    save()
    registry=home/'controle-laboratorio/treinamento-unificado'
    with contextlib.ExitStack() as locks:
        for p in (registry/'start.lock',home/'controle-laboratorio/trabalhador.lock',
                  *(ROOT/f'entidades/{e}/runtime/entity.lock' for e in ('hoshino','lilith','alistair'))):
            f=locks.enter_context(p.open('a+'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            idle(ROOT,home)
            if not validate_local(base,spec['repo']):raise RuntimeError('Originais incompletos')
            marker=json.loads((base/'lab_revision.json').read_text())
            if marker.get('revision')!=spec['revision']:raise RuntimeError('Revisão divergente')
            if any(sha(base/name)!=digest for name,digest in spec['source_files'].items()):raise RuntimeError('SHA256 divergente')
            if gpu_metrics.ram_available()<20*gpu_metrics.GIB:raise RuntimeError('RAM insuficiente; swap não é orçamento')
            report['source']=dict(repo=spec['repo'],revision=spec['revision'],sha256=spec['source_files'])
            config_hash=sha(base/'config.json');report['source']['config_sha256']=config_hash
            with rm.compute_lease('llm',entity='hoshino',model_key='diagnostic_qwen3_sniper_nf4',priority=5,
                vram_bytes=5*gpu_metrics.GIB,workspace_bytes=512*1024**2,cpu_fallback=False,wait=30):
                idle_metrics(gpu_metrics)
                env={k:v for k,v in os.environ.items() if not k.startswith(('HOSHINO_','OLLAMA_'))}
                env.update(HOSHINO_ENTIDADE='hoshino',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
                    HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='6',OPENBLAS_NUM_THREADS='1')
                env.pop('HSA_OVERRIDE_GFX_VERSION',None)
                process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--worker'],cwd=ROOT,
                    env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
                report.update(pid=process.pid,pid_start_stamp=Path(f'/proc/{process.pid}/stat').read_text().rsplit(')',1)[1].split()[19],phase='child_created');save()
                process.stdin.write(json.dumps(dict(base=str(base),sampling=sampling)));process.stdin.close()
                def drain():
                    for line in process.stdout:
                        try:event=json.loads(line)
                        except ValueError:
                            if line.strip():
                                with mutex:report.setdefault('runtime_log',[]).append(line.strip()[-2000:])
                            continue
                        if isinstance(event,dict) and MARKER in event:
                            with mutex:events.append(event);save()
                            print(json.dumps(event,ensure_ascii=False),flush=True)
                reader=threading.Thread(target=drain,daemon=True);reader.start();until=time.monotonic()+900
                try:
                    while process.poll() is None:
                        m=gpu_metrics.snapshot();row=sample_hardware(m,gpu_metrics.ram_available())
                        row['cpu_temperatures_c']=cpu_temperatures()
                        swap=observed_swap(process,owned_swap_bytes)
                        if swap is None:break
                        row['child_swap_bytes']=swap
                        samples.append(row)
                        reason=thermal_pressure(row) or physical_pressure(m,row['ram_available'],rm.gpu_policy()['margin_bytes'])
                        if max(row['cpu_temperatures_c'].values())>=85:reason=reason or 'CPU atingiu85°C'
                        if row['child_swap_bytes']:reason=reason or 'Filho diagnóstico usou swap'
                        if time.monotonic()>=until:reason=reason or 'Prazo diagnóstico900s'
                        if reason:pressure.append(reason);raise RuntimeError(reason)
                        time.sleep(.5)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:process.wait(timeout=10)
                        except subprocess.TimeoutExpired:process.kill()
                    process.wait();reader.join(timeout=10)
                    report['cleanup'].update(real_exit_code=process.returncode,child_exited_before_lease_release=process.poll() is not None)
                if process.returncode:raise RuntimeError('Filho diagnóstico exit '+str(process.returncode))
            if any(sha(base/name)!=digest for name,digest in spec['source_files'].items()) or sha(base/'config.json')!=config_hash:
                raise RuntimeError('Fonte mudou durante o ensaio')
            report['cleanup']['source_hashes_preserved']=True
        except Exception as exc:error=exc;report['error']=str(exc)
        finally:
            report['cleanup'].update(lease_released=not rm.status('gpu'),gpu_queue_empty=not rm.gpu_state()['queue'])
            report['physical']=dict(pressure=pressure,samples=len(samples),
                vram_max_bytes=max((r['vram_bytes'] or 0 for r in samples),default=None),
                ram_min_bytes=min((r['ram_available'] for r in samples),default=None),
                child_swap_max_bytes=max((r.get('child_swap_bytes',0) for r in samples),default=None),
                cpu_temperature_max_c=max((v for r in samples for v in r['cpu_temperatures_c'].values()),default=None),
                temperature_max_c={k:max(r['temperatures_c'].get(k,0) for r in samples) for k in {k for r in samples for k in r['temperatures_c']}},
                after=sample_hardware(gpu_metrics.snapshot(),gpu_metrics.ram_available()))
            report['completed']=error is None and any(e[MARKER]=='complete' for e in events)
            report['phase']='completed' if report['completed'] else 'failed_or_interrupted';save()
    emit('receipt',path=str(target),completed=report['completed'],cleanup=report['cleanup'])
    if error:raise error


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true')
    parser.add_argument('--sampling',choices=('greedy','qwen'),default='qwen')
    parser.add_argument('--output');parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:worker()
    elif args.run and args.output:run(args.output,args.sampling)
    else:parser.error('Inferência real exige --run --output; sem execução implícita')
