"""Revisão editorial explícita dos defaults; não professor, memória ou scheduler.

Sem GPU. Preserva originais/validação/holdout, relatório e hashes. Aplicar é
idempotente e exige confirmação; textos autorais não são conversas reais.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from contextlib import ExitStack
from . import treinos_unificados as lab
from .professor_schema import atomic_json


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def additions():
    data=json.loads(Path(__file__).with_name('defaults_editoriais.json').read_text())
    result={e:[] for e in lab.DATASETS}
    for row in data['conversations']:
        for entity in ('hoshino','lilith'):
            messages=[dict(role='user',content=row['user']),dict(role='assistant',content=row[entity])]
            if 'followup' in row:messages += [dict(role='user',content=row['followup']),dict(role='assistant',content=row[entity+'_next'])]
            result[entity].append(dict(messages=messages,source=data['source'],editorial_id=row['id']))
    for i,(user,reply) in enumerate(data['alistair']):
        result['alistair'].append(dict(messages=[dict(role='user',content=user),dict(role='assistant',content=reply)],
            source=data['source'],editorial_id='alistair:'+str(i)))
    return data['version'],result


def revise(rows,entity,new):
    result=json.loads(json.dumps(rows));corrected=[]
    for i,row in enumerate(result):
        messages=row['messages'];user=messages[0]['content'];reply=messages[1]['content']
        if user=='Discordar de quem criou a IA é sinal de deslealdade?' and reply.startswith('Sim.'):
            messages[1]['content']=('Não. Te avisar de um problema é mais leal que concordar só pra agradar.' if entity=='hoshino'
                else 'Não. Posso valorizar nossa conversa e ainda achar que uma ideia está errada.')
            corrected.append(dict(index=i,reason='polaridade contradizia a própria justificativa'))
        if entity=='alistair' and 'Uma ferramenta falhou por timeout.' in user and 'timeout como falha' in reply:
            messages[1]['content']='O prazo foi excedido, mas o efeito ainda precisa ser verificado. Não vou repetir uma ação mutável no escuro.'
            corrected.append(dict(index=i,reason='timeout não confirma o resultado mutável'))
        if 'Cenário operacional (benchmark)' in user and 'afirmar generalização do LoRA' in user:
            fixed='Esses requisitos definem como avaliar; não provam o resultado. Sem avaliação em cenários inéditos, não posso afirmar generalização.'
            if messages[1]['content']!=fixed:
                messages[1]['content']=fixed;corrected.append(dict(index=i,reason='requisitos necessários não comprovam generalização'))
    known={json.dumps(r['messages'],sort_keys=True,ensure_ascii=False) for r in result};added=0
    for row in new:
        key=json.dumps(row['messages'],sort_keys=True,ensure_ascii=False)
        if key not in known:result.append(row);known.add(key);added+=1
    return result,dict(corrected=corrected,added=added)


def run(home,*,apply=False):
    home=Path(home).resolve();version,extra=additions()
    if lab._busy():raise RuntimeError('Laboratório em uso; não mudar corpus durante job')
    report=dict(version=version,applied=False,train_only=True,entities={},originals_preserved=True)
    receipt=lab._registry(home)/'reports'/('defaults-'+version+'.json')
    if apply and receipt.is_file():
        previous=json.loads(receipt.read_text())
        for entity,rels in lab.DATASETS.items():
            if digest(home/rels[0])!=previous['entities'][entity]['after_sha256']:
                raise RuntimeError('Revisão já aplicada, mas corpus mudou; criar outra versão explícita')
        return dict(previous,reused=True)
    work=[]
    for entity,rels in lab.DATASETS.items():
        train,val=(home/p for p in rels)
        test=train.with_name(entity+('_holdout.jsonl' if entity=='alistair' else '_test.jsonl'))
        for path in (train,val,test):
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(home):raise ValueError('Corpus ausente/simbólico/fora do laboratório')
        original=[json.loads(l) for l in train.read_text().splitlines() if l.strip()]
        rows,changes=revise(original,entity,extra[entity])
        train_keys={json.dumps(r['messages'],ensure_ascii=False,sort_keys=True) for r in rows}
        for path in (val,test):
            keys={json.dumps(json.loads(l)['messages'],ensure_ascii=False,sort_keys=True) for l in path.read_text().splitlines() if l.strip()}
            if train_keys & keys:raise RuntimeError('Vazamento exato para avaliação: '+entity)
        report['entities'][entity]=dict(before=len(original),after=len(rows),**changes,
            before_sha256=digest(train),validation_sha256=digest(val),holdout_sha256=digest(test))
        work.append((train,rows,val,test,entity))
    if apply:
        root=lab._registry(home)/'backups'/('defaults-'+version);root.mkdir(parents=True,exist_ok=True)
        with ExitStack() as locks:
            for path in (lab._registry(home)/'start.lock',home/'controle-laboratorio/trabalhador.lock',root/'revision.lock'):
                path.parent.mkdir(parents=True,exist_ok=True)
                lock=locks.enter_context(path.open('a+'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if lab._busy():raise RuntimeError('Laboratório em uso; revisão não aplicada')
            for train,rows,val,test,entity in work:
                before=report['entities'][entity]['before_sha256']
                if digest(train)!=before:raise RuntimeError('Corpus mudou durante revisão; não sobrescrever')
                backup=root/(entity+'-'+before+'.jsonl')
                if not backup.exists():backup.write_bytes(train.read_bytes());backup.chmod(0o600)
                payload=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)
                fd,name=tempfile.mkstemp(prefix='.revisao-',dir=train.parent)
                try:
                    with os.fdopen(fd,'w') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
                    os.replace(name,train)
                finally:
                    if os.path.exists(name):os.unlink(name)
                report['entities'][entity]['after_sha256']=digest(train)
                if digest(val)!=report['entities'][entity]['validation_sha256'] or digest(test)!=report['entities'][entity]['holdout_sha256']:
                    raise RuntimeError('Avaliação mudou durante revisão')
        report['applied']=True
        atomic_json(receipt,report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',type=Path,required=True)
    p.add_argument('--apply',action='store_true');p.add_argument('--confirm')
    a=p.parse_args()
    if a.apply and a.confirm!='REVISAR_DEFAULTS_PRESERVANDO_AVALIACAO':p.error('Confirmação explícita ausente')
    print(json.dumps(run(a.home,apply=a.apply),ensure_ascii=False,indent=2))
