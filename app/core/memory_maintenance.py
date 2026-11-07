"""Manutenção explícita do banco existente; nunca executada ao importar.

O caller deve manter entity.lock e verificar senha/confirmacão antes de chamar.
Não restaura nem repete automaticamente uma exclusão cujo resultado é incerto.
"""
import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

TABLES=('memories','properties','episodes','reflections','procedures','context_summaries','alistair_turns')
VECTOR={'memories':'knowledge','properties':'knowledge','episodes':'episodes','procedures':'procedures'}
EXPERIENCE_SCOPE='experience-v1'
# Personalidade/identidade, habilidades e recibos de efeitos NÃO são resetados.
EXPERIENCE_TABLES=TABLES+('facts','people','person_events','memory_card_settings','attempts','curiosities',
    'activity_sessions','chess_games','emotion_log','goals','reminders',
    'conversation_task_steps','conversation_tasks','checkpoints','events_index')


def _digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()


def _safe(path,root):
    path=Path(path)
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Fonte de memória por link/fora da área autorizada.')
    if path.exists() and not path.is_file():raise ValueError('Fonte de memória não é um arquivo regular.')
    return path


def _rows(path,table,where='',args=()):
    if not path.is_file():return []
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=3))as db:
        db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():return []
        result=[dict(r)for r in db.execute(f'SELECT * FROM "{table}" '+where+' ORDER BY rowid LIMIT 100001',args)]
    if len(result)>100000:raise ValueError('Manutenção acima do limite seguro desta interface.')
    return result


def _sha(path):
    result=hashlib.sha256()
    with path.open('rb')as source:
        for block in iter(lambda:source.read(1024**2),b''):result.update(block)
    return result.hexdigest()


def _action_projection(row):
    if row.get('result')is None:return None  # Incerto continua incerto, nunca vira sucesso.
    value=json.loads(row['result'])
    if row['id'].startswith('dialogue-task:'):
        if not isinstance(value,dict)or value.get('schema')!=1:raise ValueError('Tarefa de continuidade ilegível; verificar antes da limpeza.')
        value.update(state='cancelled',intro_args=None,cleared=True)
    elif isinstance(value,dict):
        # Mantém o recibo/digest; retira cópia de texto que send() legado pode conter.
        value={k:v for k,v in value.items()if k in {'id','sender','recipient','requester','target',
            'requested','created_at','consumed_at','wake_requested','conversation_session','ok','verified'}}
    else:return row['result']
    return json.dumps(value,ensure_ascii=False,sort_keys=True)


def _experience(paths,shared_path):
    project=paths.raiz.parent.parent
    mind=_safe(db_path(paths),paths.memory);history=_safe(paths.runtime/'history.sqlite3',paths.runtime)
    bus=_safe(Path(shared_path),project)if shared_path is not None else None
    tables={table:_rows(mind,table)for table in EXPERIENCE_TABLES}
    for table,rows in tables.items():
        key='source_id'if table=='alistair_turns'else'event_id'if table=='events_index'else'id'
        if any(key not in row for row in rows):raise ValueError('Esquema legado de memória exige revisão antes da limpeza.')
    actions=_rows(mind,'alistair_actions')
    for action in actions:_action_projection(action)  # Falha antes de qualquer escrita.
    history_rows=_rows(history,'messages')
    history_fts=_rows(history,'messages_fts')
    bus_rows=_rows(bus,'entity_messages',"WHERE kind<>'deleted' AND (sender=? OR recipient=?)",(paths.id,paths.id))if bus else []
    for row in bus_rows:
        if not isinstance(json.loads(row.get('metadata')or'{}'),dict):raise ValueError('Envelope ilegível; não iniciar limpeza parcial.')
    wakes=_rows(bus,'wake_requests','WHERE (target=? OR requester=?) AND consumed_at IS NULL',(paths.id,paths.id))if bus else []
    archives=[]
    candidates=[paths.runtime/name for name in ('reflexao_noturna_pendente.json',
        'bus/discord_estado.json','bus/discord_usuarios.json','bus/discord_contatos.json')]
    event_dir=paths.runtime/'event_log'
    if event_dir.is_symlink():raise ValueError('Logs por link não podem ser arquivados.')
    if event_dir.is_dir():candidates.extend(sorted(event_dir.glob('*.jsonl')))
    if len(candidates)>2000:raise ValueError('Muitos arquivos para limpeza pela interface.')
    for path in candidates:
        _safe(path,paths.runtime)
        if path.is_file()and path.stat().st_size>64*1024**2:raise ValueError('Log de experiência grande demais para limpeza pela interface.')
        if path.is_file():archives.append(dict(path=str(path),sha256=_sha(path)))
    state=_safe(paths.runtime/'estado_mente.json',paths.runtime)
    state_digest=_sha(state)if state.is_file()else None
    if state.is_file():
        value=json.loads(state.read_text())
        if not isinstance(value,dict):raise ValueError('Estado mental ilegível; não limpar parcialmente.')
    counts={k:len(v)for k,v in tables.items()}
    counts.update(chat=len(bus_rows),historico_local=len(history_rows),pedidos_despertar_cancelados=len(wakes),arquivos_arquivados=len(archives))
    content=dict(entity=paths.id,tables=tables,actions=actions,history=history_rows,history_fts=history_fts,bus=bus_rows,wakes=wakes,
        archives=archives,state=state_digest,shared_path=str(bus)if bus else None)
    return content,counts


def _plan_experience(paths,shared_path):
    content,counts=_experience(paths,shared_path)
    return dict(scope=EXPERIENCE_SCOPE,entity=paths.id,targets=[],counts=counts,all=True,
        fingerprint=_digest(content),shared_path=content['shared_path'],
        note='Apaga memórias, conhecimento aprendido, perfis de pessoas, conversas e tarefas/lembretes desta entidade. '
             'Preserva identidade, personalidade/traços/gostos, habilidades, modelos, configurações e recibos de ações. '
             'Preferências e estado emocional salvo não voltam ao padrão; somente o log emocional é apagado. '
             'Logs de experiência ficam arquivados no backup; auditoria e memórias próprias das outras entidades permanecem. '
             'Exige todas as entidades dormindo. Não é apagamento forense dos backups.')


def db_path(paths):
    return paths.memory/'sqlite'/(paths.id+'.db')


def plan(paths,targets=None,all_memories=False,*,shared_path=None):
    path=db_path(paths)
    if type(all_memories) is not bool or (targets is not None and not isinstance(targets,list)):raise ValueError('Seleção inválida.')
    if all_memories:
        if targets:raise ValueError('Limpeza completa não aceita seleção parcial.')
        return _plan_experience(paths,shared_path)
    if path.is_symlink() or not path.resolve().is_relative_to(paths.memory.resolve()):raise ValueError('Banco por link/fora da memória não pode ser apagado.')
    if not path.is_file():return dict(targets=[],counts={},all=all_memories,fingerprint=hashlib.sha256(b'empty').hexdigest())
    if not all_memories and (not targets or len(targets)>150):raise ValueError('Selecione entre 1 e 150 memórias.')
    selection=targets or [];rows=[];counts={}
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
        db.row_factory=sqlite3.Row
        existing={r[0] for r in db.execute('SELECT name FROM sqlite_master WHERE type="table"')}
        for target in selection:
            if not isinstance(target,dict) or set(target)!={'table','id'} or target['table'] not in TABLES or not isinstance(target['id'],str) or not 1<=len(target['id'])<=200:
                raise ValueError('Identificador/tabela inválido.')
        for table in TABLES:
            if table not in existing:continue
            key='source_id' if table=='alistair_turns' else 'id'
            if key not in {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}:continue
            ids=[t['id'] for t in selection if t['table']==table]
            # Resumos derivados são invalidados: não podem continuar trazendo
            # conteúdo removido ao contexto. Canon de relações/traços é mantido.
            if all_memories or table=='context_summaries':query=f'SELECT * FROM "{table}"'
            elif ids:query=f'SELECT * FROM "{table}" WHERE "{key}" IN ('+','.join('?' for _ in ids)+')'
            else:continue
            found=[dict(r) for r in db.execute(query,() if all_memories or table=='context_summaries' else ids)]
            if len(found)>100000:raise ValueError('Manutenção acima do limite seguro desta interface.')
            counts[table]=len(found)
            rows.extend((table,key,str(r[key]),r) for r in found)
        actual={(r[0],r[2]) for r in rows}
        if not all_memories and any((t['table'],t['id']) not in actual for t in selection):raise ValueError('Memória não encontrada; atualize a lista.')
    digest=hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
    return dict(targets=[dict(table=t,key=k,id=i) for t,k,i,_ in rows],counts=counts,fingerprint=digest,all=all_memories,
                note='Remove registros selecionados e resumos derivados. Preserva identidade/relações/traços, recibos e histórico bruto/caixa postal. Conversas antigas permanecem e podem voltar ao contexto ou ser aprendidas novamente; isto não apaga todas as cópias do que foi dito.')


def remove_vectors(paths,targets,all_memories=False):
    directory=paths.memory/'vector/db'
    if not (directory/'chroma.sqlite3').is_file():return 0
    payload=[dict(collection=paths.id+'_'+VECTOR[t['table']],id=t['id']) for t in targets if t['table'] in VECTOR]
    if all_memories:payload=[dict(collection=paths.id+'_'+name,all=True) for name in ('knowledge','episodes','procedures')]
    if not payload:return 0
    # Processo isolado fecha os handles Chroma antes de liberar entity.lock.
    # Não carrega embedding/modelo: apenas get/delete por IDs e verificação.
    env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','TMPDIR'}}
    env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',ANONYMIZED_TELEMETRY='False')
    # A Central pode rodar no Python leve do sistema, sem Chroma. O worker
    # deve usar o ambiente principal já instalado, não instalar dependências
    # nem falhar depois de criar backup por herdar o interpretador da UI.
    principal=Path(__file__).resolve().parents[2]/'compartilhado/ambientes/principal/bin/python'
    python=str(principal) if principal.is_file() else sys.executable
    result=subprocess.run([python,'-I',str(Path(__file__).resolve()),str(directory)],
                          input=json.dumps(payload),capture_output=True,text=True,env=env,timeout=45)
    if result.returncode:raise RuntimeError('Índice vetorial não confirmou exclusão; SQL preservado. Consulte backup/diagnóstico.')
    return json.loads(result.stdout)['deleted_vector_records']


def delete(paths,preview):
    if preview.get('all'):return _delete_experience(paths,preview)
    path=db_path(paths);targets=preview['targets']
    if not path.is_file():
        if (paths.memory/'vector/db/chroma.sqlite3').is_file():raise ValueError('Índice órfão sem banco SQL exige diagnóstico manual.')
        return dict(verified=True,deleted=0,counts=preview['counts'],backup=None)
    if not targets and not preview.get('all'):return dict(verified=True,deleted=0,counts=preview['counts'],backup=None)
    backup=paths.runtime/'memory-backups'/('manual-'+uuid.uuid4().hex)
    vector=paths.memory/'vector/db'
    vector_files=list(vector.rglob('*')) if vector.is_dir() else []
    if vector.is_symlink() or not vector.resolve().is_relative_to(paths.memory.resolve()) or any(p.is_symlink() for p in vector_files):raise ValueError('Índice vetorial por link não pode ser alterado.')
    required=path.stat().st_size+sum(p.stat().st_size for p in vector_files if p.is_file())+1024**3
    if shutil.disk_usage(paths.runtime).free<required:raise ValueError('Espaço insuficiente para backup e margem de 1 GiB.')
    if not backup.resolve().is_relative_to(paths.runtime.resolve()):raise ValueError('Backup fora do runtime da entidade.')
    backup.mkdir(parents=True,mode=0o700)
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as original, contextlib.closing(sqlite3.connect(backup/path.name)) as copy:
        original.backup(copy)
    os.chmod(backup/path.name,0o600)
    if vector.is_dir():shutil.copytree(vector,backup/'vector')
    (backup/'manifest.json').write_text(json.dumps(dict(entity=paths.id,counts=preview['counts'],fingerprint=preview['fingerprint']),indent=2))
    deleted_vectors=remove_vectors(paths,targets,preview.get('all',False))
    with contextlib.closing(sqlite3.connect(path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        for row in targets:
            db.execute(f'DELETE FROM "{row["table"]}" WHERE "{row["key"]}"=?',(row['id'],))
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        for row in targets:
            if db.execute(f'SELECT 1 FROM "{row["table"]}" WHERE "{row["key"]}"=?',(row['id'],)).fetchone():
                raise RuntimeError('SQL não confirmou exclusão. Resultado incerto; backup preservado.')
    return dict(verified=True,deleted=len(targets),deleted_vectors=deleted_vectors,counts=preview['counts'],backup=str(backup),note=preview.get('note'))


def _delete_experience(paths,preview):
    if preview.get('scope')!=EXPERIENCE_SCOPE or preview.get('entity')!=paths.id:
        raise ValueError('Escopo de limpeza não confirmado; refaça a prévia.')
    content,counts=_experience(paths,preview.get('shared_path'))
    if _digest(content)!=preview['fingerprint']:raise ValueError('Memórias/conversas mudaram; refaça a prévia.')
    mind=db_path(paths);history=paths.runtime/'history.sqlite3';bus=Path(content['shared_path'])if content['shared_path']else None
    sources={'mind.sqlite3':mind,'history.sqlite3':history}
    if bus:sources['interentidades.sqlite3']=bus
    vector=paths.memory/'vector/db';files=list(vector.rglob('*'))if vector.is_dir()else []
    if vector.is_symlink()or not vector.resolve().is_relative_to(paths.memory.resolve())or any(p.is_symlink()for p in files):
        raise ValueError('Índice vetorial por link não pode ser alterado.')
    required=sum(p.stat().st_size for p in sources.values()if p.is_file())+sum(p.stat().st_size for p in files if p.is_file())
    required+=sum(Path(r['path']).stat().st_size for r in content['archives'])+1024**3
    if shutil.disk_usage(paths.runtime).free<required:raise ValueError('Espaço insuficiente para backup completo e margem de 1 GiB.')
    backup=paths.runtime/'memory-backups'/('manual-'+uuid.uuid4().hex)
    if not backup.resolve().is_relative_to(paths.runtime.resolve()):raise ValueError('Backup fora do runtime da entidade.')
    backup.mkdir(parents=True,mode=0o700)
    for name,path in sources.items():
        if not path.is_file():continue
        with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True))as original,contextlib.closing(sqlite3.connect(backup/name))as copy:
            original.backup(copy)
            if copy.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Backup SQLite não íntegro; limpeza não iniciada.')
        os.chmod(backup/name,0o600)
    if vector.is_dir():shutil.copytree(vector,backup/'vector')
    state=paths.runtime/'estado_mente.json'
    if state.is_file():shutil.copy2(state,backup/state.name);os.chmod(backup/state.name,0o600)
    for row in content['archives']:
        source=Path(row['path']);target=backup/'runtime'/source.relative_to(paths.runtime)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);os.chmod(target,0o600)
        if _sha(target)!=row['sha256']:raise ValueError('Backup de experiência divergente; limpeza não iniciada.')
    manifest=backup/'manifest.json'
    manifest.write_text(json.dumps(dict(scope=EXPERIENCE_SCOPE,entity=paths.id,counts=counts,fingerprint=preview['fingerprint']),indent=2));os.chmod(manifest,0o600)
    # Revalidar todas as fontes após a cópia, antes do primeiro efeito.
    fresh,_=_experience(paths,preview.get('shared_path'))
    if _digest(fresh)!=preview['fingerprint']:raise ValueError('Fontes mudaram durante o backup; limpeza não iniciada.')
    deleted_vectors=remove_vectors(paths,[],True)
    if mind.is_file():
        with contextlib.closing(sqlite3.connect(mind))as db,db:
            db.execute('BEGIN IMMEDIATE')
            for table,rows in content['tables'].items():
                key='source_id'if table=='alistair_turns'else'event_id'if table=='events_index'else'id'
                for row in rows:db.execute(f'DELETE FROM "{table}" WHERE "{key}"=?',(row[key],))
            for row in content['actions']:
                if row['result']is not None:
                    db.execute('UPDATE alistair_actions SET result=? WHERE id=? AND digest=?',(_action_projection(row),row['id'],row['digest']))
    if history.is_file():
        with contextlib.closing(sqlite3.connect(history))as db,db:
            db.execute('BEGIN IMMEDIATE')
            has_fts=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages_fts'").fetchone()
            if has_fts:db.execute('DELETE FROM messages_fts')  # Inclui índices órfãos do próprio histórico.
            for row in content['history']:
                db.execute('DELETE FROM messages WHERE id=?',(row['id'],))
    if bus and bus.is_file():
        with contextlib.closing(sqlite3.connect(bus))as db,db:
            db.execute('BEGIN IMMEDIATE')
            for row in content['bus']:
                metadata=json.loads(row.get('metadata')or'{}')
                if not isinstance(metadata,dict):raise ValueError('Envelope ilegível; limpeza não confirmada.')
                metadata={k:v for k,v in metadata.items()if k in {'processing','reply_to','turn_id','input_ids','conversation_session','hops','private'}}
                metadata['content_cleared']=True
                db.execute("UPDATE entity_messages SET text='',kind='deleted',metadata=? WHERE id=?",(json.dumps(metadata,ensure_ascii=False),row['id']))
            now=datetime.now(timezone.utc).isoformat()
            for row in content['wakes']:
                db.execute('UPDATE wake_requests SET consumed_at=?,reason=? WHERE id=? AND consumed_at IS NULL',(now,'cancelado por limpeza explícita; não confirma despertar',row['id']))
    for row in content['archives']:
        source=Path(row['path'])
        if _sha(source)!=row['sha256']:raise ValueError('Log mudou durante a limpeza; verificar o backup antes de repetir.')
        source.unlink()  # Cópia íntegra já verificada no backup, não descarte de evidência.
    if state.is_file():
        from core import state_file
        def clear_projection(data):
            data.pop('activity_context',None)
            data.pop('autonomous_activity',None)
        if not state_file.update(state,clear_projection,'memory.clear_operational_projection'):
            raise ValueError('Projeção não confirmou limpeza; verificar backup.')
    remaining,_=_experience(paths,preview.get('shared_path'))
    if any(remaining['tables'].values())or remaining['history']or remaining['history_fts']or remaining['bus']or remaining['wakes']or remaining['archives']:
        raise ValueError('Fontes ativas ainda contêm experiência; não declarar sucesso nem repetir automaticamente.')
    expected={row['id']:(row['digest'],_action_projection(row))for row in content['actions']}
    actual={row['id']:(row['digest'],row['result'])for row in remaining['actions']}
    if actual!=expected:raise ValueError('Recibos técnicos divergiram; não declarar sucesso.')
    if state.is_file()and any(json.loads(state.read_text()).get(key) for key in ('activity_context','autonomous_activity')):
        raise ValueError('Contexto operacional ainda ativo; não declarar limpeza completa.')
    return dict(scope=EXPERIENCE_SCOPE,verified=True,deleted=sum(len(v)for v in content['tables'].values())+len(content['history'])+len(content['bus']),
        deleted_vectors=deleted_vectors,counts=counts,backup=str(backup),note=preview['note'],chat_cleared=True,knowledge_cleared=True,
        preserved=['identity','personality','traits','tastes','preferences','emotional_state','skill_profile','models','settings','action_receipts','audit'])


if __name__=='__main__':
    # Entrada interna do processo vetorial; nunca exposta como comando da UI.
    import chromadb
    from chromadb.config import Settings
    client=chromadb.PersistentClient(path=sys.argv[1],settings=Settings(anonymized_telemetry=False))
    names={c.name for c in client.list_collections()}
    count=0
    for row in json.load(sys.stdin):
        if row['collection'] not in names:continue
        collection=client.get_collection(row['collection'])
        ids=collection.get(include=[])['ids'] if row.get('all') else collection.get(ids=[row['id']],include=[])['ids']
        for at in range(0,len(ids),500):collection.delete(ids=ids[at:at+500])
        if ids and collection.get(ids=ids,include=[])['ids']:raise RuntimeError('delete não verificado')
        count+=len(ids)
    print(json.dumps({'deleted_vector_records':count}))
