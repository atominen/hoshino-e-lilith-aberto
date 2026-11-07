"""Trabalhador local com lock. Somente planos predefinidos pelo backend.
Roda isolado dos scripts da automação 9B; não executa comandos arbitrários do painel.
"""
from __future__ import annotations
import argparse,fcntl,json,os,shutil,subprocess,sys,time,urllib.request,urllib.error,socket,signal
from datetime import datetime
from pathlib import Path
from .experimentos import (job_info,jobs_dir,model_path,output_path,adapter_path,allowed_data,
                           gate_9b,_write_json)
from .catalogo import BY_ID


def run(argv,timeout=14400,env=None,guard=None):
    cmd=[str(x) for x in argv]
    print('$', ' '.join(cmd),flush=True)
    # Output inherited into the job log; wait(timeout) works even if subprocess is silent.
    p=subprocess.Popen(cmd,env=env,start_new_session=True)
    try:
        if guard is None:code=p.wait(timeout=timeout)
        else:
            deadline=time.monotonic()+timeout
            while p.poll() is None:
                reason=guard()
                if reason:raise RuntimeError(reason)
                if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(cmd,timeout)
                try:p.wait(timeout=.5)
                except subprocess.TimeoutExpired:pass
            code=p.returncode
    except subprocess.TimeoutExpired:
        import signal
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.wait()
        raise TimeoutError(f'Comando excedeu limite de {timeout}s')
    except BaseException:
        if p.poll() is None:
            import signal
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
        raise
    if code:raise RuntimeError('Subprocesso falhou: '+str(code))


def prerequisites(home,p):
    base=model_path(home,p['model'])
    from .candidatos import validate_local
    if not validate_local(base,p['repo']):
        raise RuntimeError('Checkpoint HF incompleto: ausente lab_revision.json/fragmentos safetensors')
    if p['operation']!='download':
        if shutil.disk_usage(home).free<22*1024**3:
            raise RuntimeError('Reserva mínima de 22 GiB livres para experimento não atendida')
    if p['operation'] in ('train','convert','ollama_test','cycle_30m'):
        gate_9b(home,p['operation'])
    return base


def do_download(home,p):
    if BY_ID.get(p.get('model'),{}).get('retired'):
        raise ValueError('Modelo retirado pelo proprietário; não reinstalar por um plano antigo.')
    gate_9b(home,'download')
    if shutil.disk_usage(home).free<50*1024**3:raise RuntimeError('Manter ao menos 50 GiB livres antes de baixar outro modelo; reservar disco para o 9B e GGUF')
    base=model_path(home,p['model']);base.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('HF_HUB_DISABLE_XET','1')
    os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT','120')
    from huggingface_hub import snapshot_download,model_info
    info=model_info(p['repo']);revision=info.sha
    if not revision:raise RuntimeError('Revisão do Hub sem hash')
    print('DOWNLOAD APROVADO PELO OPERADOR:',p['repo'],revision,flush=True)
    # Do not download large pytorch/bin files, only safetensors + config/template.
    snapshot_download(repo_id=p['repo'],revision=revision,local_dir=str(base),max_workers=1,
        allow_patterns=['*.safetensors','*.json','*.model','*.jinja','tokenizer.*','*.txt','preprocessor_config.json','merges.txt','vocab.json'],
        ignore_patterns=['*.bin','*.pt','*.pth','*.h5','*.onnx','*.gguf'])
    (base/'lab_revision.json').write_text(json.dumps({'repo':p['repo'],'revision':revision}))
    print('Download HF concluído',flush=True)


def do_smoke_hf(home,p):
    """Probe de inferência real ON/OFF NF4; falha impede desperdiçar 30 min.
    Não é benchmark de capacidade nem aprova treino prolongado.
    """
    import gc
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    base=model_path(home,p['model'])
    env=os.environ
    if env.get('HSA_OVERRIDE_GFX_VERSION'):
        raise RuntimeError('HSA_OVERRIDE_GFX_VERSION não deve estar definido no ROCm')
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError('ROCm/BF16 indisponível; sem fallback CPU')
    tok=AutoTokenizer.from_pretrained(base,local_files_only=True)
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.bfloat16,bnb_4bit_use_double_quant=True)
    model=AutoModelForCausalLM.from_pretrained(base,local_files_only=True,quantization_config=quant,device_map={'':0},torch_dtype=torch.bfloat16)
    model.eval()
    samples=[]
    supported=bool(BY_ID[p['model']].get('thinking'))
    try:
        previous_prompt=None
        for thinking in ((False,True) if supported else (False,)):
            messages=[{'role':'user','content':'Quanto é 12 + 17? Dê a resposta numérica.'}]
            # O comportamento efetivo depende do chat template distribuído pelo modelo.
            prompt=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=thinking)
            if thinking is False and '<think>' not in prompt and '/no_think' not in prompt:
                # Qwen3 pode sinalizar o desligamento por outras formas no template;
                # a geração ainda deve ser inspecionada no relatório, não aprovada cegamente.
                print('Aviso: template sem marcador explícito de thinking OFF',flush=True)
            if thinking and prompt == previous_prompt:
                raise RuntimeError('Thinking ON/OFF tem templates identicos: rejeitado.')
            previous_prompt=prompt
            inputs=tok(prompt,return_tensors='pt').to('cuda')
            with torch.no_grad():
                result=model.generate(**inputs,max_new_tokens=128,do_sample=True,temperature=0.7,pad_token_id=tok.eos_token_id)
            answer=tok.decode(result[0][inputs.input_ids.shape[-1]:],skip_special_tokens=False)
            samples.append({'thinking':thinking,'answer':answer[:3000], 'has_think_marker':'<think>' in answer,'completed':True})
            print('TESTE ON/OFF:',thinking,repr(answer[:200]),flush=True)
        target=home/'modelos-extras'/p['model']/'testes'
        target.mkdir(parents=True,exist_ok=True)
        (target/'pretreino-thinking.json').write_text(json.dumps({'samples':samples,'thinking_supported':supported,'status':'API_OK_SEM_HOMOLOGACAO'},ensure_ascii=False,indent=2))
    finally:
        del model
        gc.collect()
        torch.cuda.empty_cache()


def do_train(home,p):
    from .experimentos import allowed_data
    data={d['id']:d for d in allowed_data(home)}[p['dataset']]
    base=model_path(home,p['model'])
    out=adapter_path(home,p['model'],p['dataset'].replace(':','-')+'-'+p['entity'])
    env=os.environ.copy();env.pop('HSA_OVERRIDE_GFX_VERSION',None)
    venv=home/'.venv-rocm/bin/python'
    if not venv.is_file():raise RuntimeError('Venv ROCm esperado não existe')
    run([venv,'-u','-m','laboratorio.treino_texto','--model',base,'--train',data['train'],
         '--validation',data['validation'],'--out',out,'--minutes',p['minutes']],
         timeout=p['minutes']*60+2400,env=env)


def selected_adapter(home,p):
    # Only entity-specific run: e.g. pacote_neural_v3:hoshino => adapters/pacote_neural_v3-hoshino/final
    if not p['adapter']:return None
    root=home/'modelos-extras'/p['model']/'adapters'
    paths=sorted([a/'final' for a in root.glob('*-'+p['adapter']) if (a/'final'/'adapter_config.json').is_file()])
    if not paths:raise RuntimeError('LoRA da entidade não está treinado localmente')
    if len(paths)>1:raise RuntimeError('Múltiplos adaptadores encontrados; escolha uma execução única antes de exportar')
    return paths[0]


def gguf_ok(path):
    if not path.is_file() or path.stat().st_size<=4096:return False
    with path.open('rb') as content:return content.read(4)==b'GGUF'


def do_convert(home,p):
    base=model_path(home,p['model']);out=output_path(home,p['model'])
    convert_local(home,base,out,adapter=selected_adapter(home,p),adapter_name=p['adapter']+'-lora.gguf')


def convert_local(home,base,out,*,adapter=None,adapter_name='stable-lora.gguf',vision=False,guard=None):
    """Mesmo conversor local; entrada pinada pelo chamador, sem pull/treino.

    Saídas novas somente. Recuperação usa diretório staging e verifica GGUF/hash
    antes de publicar; o comportamento do runner legado permanece compatível.
    """
    home=Path(home);base=Path(base);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cpp=home/'llama.cpp';a=cpp/'convert_hf_to_gguf.py';b=cpp/'convert_lora_to_gguf.py';q=cpp/'build/bin/llama-quantize'
    if not all(x.is_file() for x in [a,b,q]):raise RuntimeError('llama.cpp conversores não encontrados')
    venv=home/'.venv-rocm/bin/python';target=out/'base-q4_k_m.gguf';temp=out/'base-f16.gguf'
    if not gguf_ok(target):
        if not gguf_ok(temp):
            # Espaço para F16 + Q4 temporários e reserva para sistema/9B.
            weights=sum(f.stat().st_size for f in base.glob('*.safetensors'))
            required=int(weights*1.40)+12*1024**3
            if shutil.disk_usage(home).free<required:
                raise RuntimeError(f'Disco insuficiente para GGUF temporário: exigir {required/(1024**3):.1f} GiB livres; não iniciar conversão')
        if not gguf_ok(temp):
            cfg=json.loads((base/'config.json').read_text())
            # O backend Ollama instalado não executa o head MTP. Conversões
            # recentes podem anunciar uma camada especulativa sem seu tensor.
            # Usar a opção oficial do conversor, sem editar pesos/metadados à mão.
            flags=['--no-mtp'] if cfg.get('model_type') in ('qwen3_5','qwen3_5_moe') else []
            run([venv,a,base,*flags,'--outtype','f16','--outfile',temp],timeout=7200,guard=guard)
        if not gguf_ok(temp):raise RuntimeError('Conversão F16 incompleta')
        run([q,temp,target,'Q4_K_M'],timeout=7200,guard=guard)
        if not gguf_ok(target):raise RuntimeError('GGUF quantizado inválido')
        temp.unlink()
    projector=None
    if vision:
        projector=out/'mmproj-model-f16.gguf'
        if not gguf_ok(projector):
            run([venv,a,base,'--mmproj','--outtype','f16','--outfile',projector],timeout=7200,guard=guard)
        if not gguf_ok(projector):raise RuntimeError('Projetor multimodal não confirmado; não perder visão silenciosamente')
    if adapter:
        dest=out/adapter_name
        if not gguf_ok(dest):
            run([venv,b,adapter,'--base',base,'--outtype','f16','--outfile',dest],timeout=3600,guard=guard)
            if not gguf_ok(dest):raise RuntimeError('GGUF LoRA inválido')
    print('Exportação verificada',target,flush=True)
    return {'base':target,'projector':projector,'adapter':dest if adapter else None}


def api(host,path,payload=None,timeout=60):
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(host+path,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)


def do_ollama(home,p):
    if not shutil.which('ollama'):raise RuntimeError('Ollama não instalado')
    out=output_path(home,p['model']);base=out/'base-q4_k_m.gguf'
    if not gguf_ok(base):raise RuntimeError('GGUF base não existe ou falhou verificação')
    adapter=out/(p['adapter']+'-lora.gguf') if p['adapter'] else None
    if adapter and not gguf_ok(adapter):raise RuntimeError('LoRA GGUF selecionado ausente')
    host='http://127.0.0.1:11557'; ollama_host='127.0.0.1:11557'
    with socket.socket() as sk:
        if sk.connect_ex(('127.0.0.1',11557))==0:
            raise RuntimeError('Porta 11557 ocupada; recuso conectar a servidor desconhecido')
    env=os.environ.copy();env.update(OLLAMA_HOST=ollama_host,OLLAMA_MODELS=str(home/'ollama-painel-7b6b'),OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_NUM_PARALLEL='1')
    Path(env['OLLAMA_MODELS']).mkdir(parents=True,exist_ok=True)
    proc=subprocess.Popen(['ollama','serve'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    try:
        for _ in range(35):
            if proc.poll() is not None:raise RuntimeError('Ollama isolado terminou')
            try:
                if api(host,'/api/version',timeout=1).get('version'):break
            except (urllib.error.URLError,TimeoutError):time.sleep(1)
        else:raise RuntimeError('Servidor Ollama isolado não iniciou em 35 s')
        labels=[]
        for label,ad in [('base',None)]+([('adaptado',adapter)] if adapter else []):
            modelname=f'lab-{p["model"]}-{label}'
            modelfile=out/f'Modelfile-{label}'
            data=f'FROM {base}\nPARAMETER num_ctx 2048\nPARAMETER temperature 0\n'
            if ad:data+=f'ADAPTER {ad}\n'
            modelfile.write_text(data)
            run(['ollama','create',modelname,'-f',modelfile],env=env,timeout=240)
            labels.append(modelname)
        prompts=['Como você se identifica?','Se 2 + 2 = 4, quanto é 2 + 3?',
                 'Se uma informação não está na memória, qual é o comportamento correto?']
        results={}
        for label in labels:
            results[label]=[]
            for prompt in prompts:
                for thinking in ((False,True) if BY_ID[p['model']]['thinking'] else (False,)):
                    try:
                        v=api(host,'/api/chat',{'model':label,'messages':[{'role':'user','content':prompt}],
                                      'think':thinking,'stream':False,'options':{'num_predict':192,'num_ctx':2048}},timeout=150)
                        msg=v.get('message',{})
                        results[label].append({'prompt':prompt,'think':thinking,'answer':msg.get('content',''),
                                   'reasoning_present':bool(msg.get('thinking')),'success':True})
                    except Exception as e:
                        results[label].append({'prompt':prompt,'think':thinking,'error':str(e),'success':False})
        path=out/'comparacao-ollama.json';path.write_text(json.dumps({'models':labels,'results':results,'vision':'nao testada'},ensure_ascii=False,indent=2))
        print('Comparação textual gravada:',path,flush=True)
    finally:
        proc.terminate()
        try:proc.wait(timeout=15)
        except subprocess.TimeoutExpired:proc.kill()


def do_cycle_30m(home,p):
    if p['minutes']!=30:raise RuntimeError('Ciclo deve durar exatamente 30 minutos de treino')
    print('ETAPA 1/4: teste de geracao; ON/OFF se suportado',flush=True)
    do_smoke_hf(home,p)
    print('ETAPA 2/4: treino QLoRA com limite de 30 minutos',flush=True)
    do_train(home,p)
    adapted=dict(p,adapter=p['entity'])
    print('ETAPA 3/4: GGUF base e adaptador (não destrutivo)',flush=True)
    do_convert(home,adapted)
    print('ETAPA 4/4: comparacao Ollama; ON/OFF se suportado',flush=True)
    do_ollama(home,adapted)

def _interrupt(*_):
    raise KeyboardInterrupt('Parada solicitada pelo operador')

def main():
    signal.signal(signal.SIGTERM,_interrupt)
    signal.signal(signal.SIGINT,_interrupt)
    ap=argparse.ArgumentParser();ap.add_argument('--home',type=Path,required=True);ap.add_argument('--job',required=True);args=ap.parse_args()
    home=args.home.resolve();entry=job_info(home,args.job)
    record=jobs_dir(home)/(args.job+'.json')
    if entry['state'] not in ('started','queued','scheduled'):raise RuntimeError('Job não está pendente')
    lock=home/'controle-laboratorio/trabalhador.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+') as fh:
        try:fcntl.flock(fh,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            entry['state']='failed';entry['error']='Outro experimento já utiliza os recursos';entry.pop('log_tail',None);_write_json(record,entry);return
        entry['state']='running';entry['start']=datetime.now().astimezone().isoformat();entry.pop('log_tail',None);_write_json(record,entry)
        p=entry['plan'];op=p['operation']
        try:
            prerequisites(home,p)
            {'train':do_train,'convert':do_convert,'ollama_test':do_ollama,'cycle_30m':do_cycle_30m}[op](home,p)
            entry['state']='completed';print('EXPERIMENTO CONCLUIDO',flush=True)
        except BaseException as exc:
            entry['state']='canceled' if isinstance(exc,KeyboardInterrupt) else 'failed';entry['error']=str(exc)
            print('FALHA CONTROLADA:',type(exc).__name__,str(exc),flush=True)
        finally:
            entry['end']=datetime.now().astimezone().isoformat();entry.pop('log_tail',None);_write_json(record,entry)

if __name__=='__main__':main()
