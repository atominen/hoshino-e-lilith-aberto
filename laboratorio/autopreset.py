#!/usr/bin/env python3
"""Auto-preset por medidas reais (nao heuristica de tamanho), sem deploy.
Plan/status = somente leitura. Calibrate/mini = GPU e confirmacao CLI explicita.
"""
from __future__ import annotations
import argparse,fcntl,hashlib,json,math,os,subprocess,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path

LAB=Path.home()/'laboratorio-lora'
PROJECT=Path.home()/'hoshino e lilith'
MODEL_REL='modelos/qwen3.5-0.8b'
CANDIDATES=({'rank':4,'max_length':256},{'rank':8,'max_length':256})

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def registry(home):return home/'controle-laboratorio/presets-auto'

def signature(home,entity):
    model=home/MODEL_REL
    dataset=home/__import__('laboratorio.corpus_atual',fromlist=['CORPUS']).CORPUS/f'{entity}_train.jsonl'
    if not model.joinpath('config.json').is_file() or not dataset.is_file():return None
    return {'model_config_sha256':digest(model/'config.json'),'train_sha256':digest(dataset)}

def status(home):
    folder=registry(home)
    last={}
    for entity in ('hoshino','lilith'):
        file=folder/f'{entity}-latest.json'
        try:
            obj=json.loads(file.read_text())
            last[entity]={'calibrated':True,'selected':obj.get('selected'),
                          'warnings':obj.get('warnings',[]),
                          'runs':obj.get('runs',[]),
                          'signature_matches':obj.get('signature')==signature(home,entity),
                          'created':obj.get('created')}
        except (OSError,ValueError):last[entity]={'calibrated':False}
    return {'method':'LoRA BF16 textual, somente Qwen3.5-0.8B local',
        'auto_deploy':False,'gpu_runs_automated':False,'9b_long_training_enabled':False,
        'status':'NECESSITA_BENCHMARK' if not all(x.get('calibrated') for x in last.values()) else 'CALIBRADO_EM_MICROTESTES',
        'candidates':list(CANDIDATES), 'entities':last,
        'limitations':'Melhor apenas entre presets medidos e na janela atual; nao garante qualidade de personalidade nem estabilidade >4 passos.'}

def active_training():
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:cmd=(p/'cmdline').read_bytes().decode(errors='replace').replace('\0',' ')
        except (OSError,PermissionError):continue
        if ('treino_qwen35_entidade.py' in cmd or 'laboratorio.trabalhador' in cmd or
            ('treino_micro.py' in cmd and 'python' in cmd)):
            return f'{p.name}: {cmd[:160]}'
    return None

def choose(runs):
    good=[r for r in runs if r.get('ok') and math.isfinite(r.get('val_improvement',float('nan'))) and
          r.get('peak_vram_gib',100)<7.5 and r.get('steps',0)>=4 and
          r.get('steps_per_second',0)>0]
    if not good:return None
    # Keep loss objective highest; compare speed/VRAM as tie-breakers, not invented universal optima.
    def score(r):
        return (round(r['val_improvement'],4),round(r['steps_per_second'],4),-r['peak_vram_gib'])
    return max(good,key=score)

def calibrate(home,project,entity):
    if active_training():raise RuntimeError('Treinamento concorrente detectado')
    sign=signature(home,entity)
    if sign is None:raise RuntimeError('Modelo 0.8B ou dataset v3 ausente')
    py=home/'.venv-rocm/bin/python'
    runner=project/'laboratorio/treino_micro.py'
    if not py.is_file() or not runner.is_file():raise RuntimeError('Ambiente ROCm ou runner nao instalado')
    directory=registry(home);directory.mkdir(parents=True,exist_ok=True)
    runid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:7]
    outputs=directory/'runs'/runid;outputs.mkdir(parents=True)
    runs=[];warnings=[]
    for candidate in CANDIDATES:
        if active_training():
            # our own subprocess is already complete; any other process is unsafe
            raise RuntimeError('Treinamento concorrente surgiu; abortando')
        label=f"r{candidate['rank']}-s{candidate['max_length']}"
        result=outputs/(label+'.json');log=outputs/(label+'.log')
        cmd=[str(py),'-u',str(runner),'--mode','benchmark','--entity',entity,
             '--model',str(home/MODEL_REL),'--data',str(home/__import__('laboratorio.corpus_atual',fromlist=['CORPUS']).CORPUS),
             '--out',str(result),'--rank',str(candidate['rank']),
             '--max-length',str(candidate['max_length'])]
        start=time.monotonic()
        env=os.environ.copy();env.pop('HSA_OVERRIDE_GFX_VERSION',None)
        with log.open('w') as f:
            try:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,cwd=project,timeout=15*60)
            except subprocess.TimeoutExpired:r=None;warnings.append(f'{label}: tempo de calibracao excedido')
        if r is None or r.returncode!=0 or not result.is_file():
            runs.append({'ok':False,**candidate,'log':str(log)})
            warnings.append(f'{label}: falhou; consulte log')
            continue
        try:
            row=json.loads(result.read_text())
            if not row.get('ok') or row.get('train_sha256')!=sign['train_sha256'] or row.get('model_config_sha256')!=sign['model_config_sha256']:
                raise ValueError('assinatura do experimento divergiu')
            row['log']=str(log)
            runs.append(row)
        except (ValueError,KeyError) as e:
            runs.append({'ok':False,**candidate,'log':str(log)});warnings.append(f'{label}: resultado invalido {e}')
    best=choose(runs)
    if best is not None and best['val_improvement']<=0:
        warnings.append('Nenhum preset melhorou a validacao nos 4 passos: escolha so compara estabilidade/desempenho.')
    result={'created':datetime.now(timezone.utc).isoformat(),'run_id':runid,'entity':entity,
            'signature':sign,'selected':{'rank':best['rank'],'max_length':best['max_length']} if best else None,
            'runs':runs,'warnings':warnings,
            'note':'Selecao somente dos candidatos testados; NÃO aplica LoRA na Central, NÃO mede melhora comportamental.'}
    tmp=directory/f'{entity}-latest.json.tmp';tmp.write_text(json.dumps(result,indent=2,ensure_ascii=False));tmp.replace(directory/f'{entity}-latest.json')
    return result

def mini(home,project,entity,minutes):
    path=registry(home)/f'{entity}-latest.json'
    if not path.is_file():raise RuntimeError('Calibre antes de fazer treino curto')
    obj=json.loads(path.read_text())
    if obj.get('signature')!=signature(home,entity):raise RuntimeError('Modelo/dataset mudou desde a calibracao')
    created=datetime.fromisoformat(obj['created'])
    if (datetime.now(timezone.utc)-created).total_seconds()>24*3600:raise RuntimeError('Calibracao tem mais de 24h; repita-a')
    selected=obj.get('selected')
    if not selected:raise RuntimeError('Nenhuma calibracao passou nos requisitos de VRAM')
    # Recalibrate when driver/torch or GPU changed, not only if files changed.
    import torch
    selected_runs=[r for r in obj.get('runs',[]) if r.get('ok') and r.get('rank')==selected['rank'] and r.get('max_length')==selected['max_length']]
    if not selected_runs or not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('GPU sem calibracao compativel atual')
    measured=selected_runs[0]
    if (measured.get('torch')!=torch.__version__ or
        measured.get('rocm')!=torch.version.hip or
        measured.get('gpu')!=torch.cuda.get_device_name(0)):
        raise RuntimeError('GPU/ROCm/PyTorch mudou: repita calibracao')
    if active_training():raise RuntimeError('Treino ativo, nao concorrera pela GPU')
    out=registry(home)/'adapters'/entity/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]);out.parent.mkdir(parents=True,exist_ok=True)
    py=home/'.venv-rocm/bin/python'
    runner=project/'laboratorio/treino_micro.py'
    cmd=[str(py),'-u',str(runner),'--mode','mini-train','--entity',entity,'--model',str(home/MODEL_REL),
         '--data',str(home/__import__('laboratorio.corpus_atual',fromlist=['CORPUS']).CORPUS),'--out',str(out),'--rank',str(selected['rank']),
         '--max-length',str(selected['max_length']),'--minutes',str(minutes)]
    env=os.environ.copy();env.pop('HSA_OVERRIDE_GFX_VERSION',None)
    logfile=out.with_suffix('.log')
    with logfile.open('w') as f:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,cwd=project,timeout=30*60).returncode
    if code:raise RuntimeError(f'Treino curto falhou. Log: {logfile}')
    return {'adapter':str(out),'log':str(logfile),'minutes_limit':minutes,'entity':entity}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=('plan','status','calibrate','mini-train','auto'))
    p.add_argument('--entity',choices=('hoshino','lilith','both'),default='both')
    p.add_argument('--minutes',type=int,default=3)
    p.add_argument('--lab',type=Path,default=LAB)
    p.add_argument('--project',type=Path,default=PROJECT)
    p.add_argument('--confirm',default='')
    a=p.parse_args(argv);home=a.lab.resolve();project=a.project.resolve()
    if a.command in ('status','plan'):
        print(json.dumps(status(home),ensure_ascii=False,indent=2));return 0
    if a.command=='calibrate' and a.confirm!='CALIBRAR_GPU':p.error('Use --confirm CALIBRAR_GPU para usar a GPU')
    if a.command=='mini-train' and a.confirm!='TREINO_CURTO_ISOLADO':p.error('Use --confirm TREINO_CURTO_ISOLADO')
    if a.command=='auto' and a.confirm!='CALIBRAR_E_TREINAR_CURTO':p.error('Use --confirm CALIBRAR_E_TREINAR_CURTO')
    if a.command in ('mini-train','auto') and not 2<=a.minutes<=15:p.error('Treino curto exige 2-15 minutos')
    lockdir=registry(home);lockdir.mkdir(parents=True,exist_ok=True)
    with (lockdir/'gpu.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Outra calibracao esta ativa. Abortando.')
        try:
            entities=('hoshino','lilith') if a.entity=='both' else (a.entity,)
            if a.command=='calibrate':
                ret={e:calibrate(home,project,e) for e in entities}
            elif a.command=='mini-train':
                ret={e:mini(home,project,e,a.minutes) for e in entities}
            else:
                # ALWAYS rebench on each explicit auto call, never promote a stale ranking.
                ret={};failed=False
                for e in entities:
                    try:
                        calibration=calibrate(home,project,e)
                        if calibration.get('selected') is None:
                            failed=True;ret[e]={'calibration':calibration,'error':'Nenhum preset passou'};continue
                        ret[e]={'calibration':calibration,'mini_train':mini(home,project,e,a.minutes)}
                    except (RuntimeError,OSError,subprocess.TimeoutExpired) as exc:
                        ret[e]={'error':str(exc)};failed=True
                print(json.dumps(ret,indent=2,ensure_ascii=False))
                return 1 if failed else 0
            print(json.dumps(ret,indent=2,ensure_ascii=False));return 0
        except (RuntimeError,OSError,subprocess.TimeoutExpired) as e:
            print('BLOQUEADO:',e,file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
