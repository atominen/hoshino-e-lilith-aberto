"""Edição humana explícita dos registros semânticos existentes, com backup.

O chamador mantém entity.lock. Sem LLM, extração de chat, novo banco ou efeito
operacional a partir de regras/manuais escritos como conhecimento.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
import re
from contextlib import closing
from datetime import datetime,timezone
from core import memory_maintenance as mm
from memory.records import CARD_KINDS, CARD_TIERS, card_priorities

FIELDS={
    'people':('nome','apelidos','papel','notas','confianca','familiaridade','afinidade'),
    'properties':('entity','chave','valor','unidade','confidence'),
    'memories':('content','type','confidence'),
    'procedures':('nome','objetivo','passos','precondicoes','resultado_esperado','notas','confidence'),
}
KINDS=CARD_KINDS
TIERS=CARD_TIERS
TIER_SCHEMA="CREATE TABLE IF NOT EXISTS memory_card_settings(id TEXT PRIMARY KEY,tier TEXT NOT NULL CHECK(tier IN ('bronze','ferro','ouro','diamante')),updated_at TEXT NOT NULL)"


def tiers(database):
    if not database.is_file():return {}
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_card_settings' AND type='table'").fetchone():return {}
        # Banco ainda não migrado: a platina antiga vale como diamante (07/11).
        return {row[0]:('diamante' if row[1]=='platina' else row[1]) for row in db.execute('SELECT id,tier FROM memory_card_settings')
                if row[1] in TIERS or row[1]=='platina'}


def card_revision(card):
    return digest(dict(id=card['id'],importance=card['importance'],records=sorted({(r['table'],str(r['record_id']),r['revision']) for r in card['entries']})))


def set_importance(paths,data):
    if data.get('importance') not in TIERS:raise ValueError('Escolha Bronze, Ferro, Ouro ou Diamante.')
    database=mm._safe(mm.db_path(paths),paths.memory)
    if not database.is_file():raise ValueError('Banco próprio indisponível.')
    if shutil.disk_usage(paths.runtime).free<database.stat().st_size+1024**3:raise ValueError('Sem espaço para backup e reserva de 1 GiB.')
    backup=paths.runtime/'memory-backups'/('importance-'+uuid.uuid4().hex);backup.mkdir(parents=True,mode=0o700)
    with closing(sqlite3.connect(database,timeout=10)) as db:
        with closing(sqlite3.connect(backup/database.name)) as snapshot:db.backup(snapshot)
        os.chmod(backup/database.name,0o600)
        with db:
            db.execute('BEGIN IMMEDIATE')
            from memory.sqlite.init_db import migrar_niveis_cartoes
            migrar_niveis_cartoes(db);db.execute(TIER_SCHEMA)
            db.execute('INSERT INTO memory_card_settings VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET tier=excluded.tier,updated_at=excluded.updated_at',
                (data['card_id'],data['importance'],datetime.now(timezone.utc).isoformat()))
        if db.execute('SELECT tier FROM memory_card_settings WHERE id=?',(data['card_id'],)).fetchone()!=(data['importance'],):raise RuntimeError('Importância não confirmada; backup preservado. Não repetir automaticamente.')
    return dict(verified=True,entity=paths.id,importance=data['importance'],backup=str(backup),confidence_changed=False,
                note='Importância do cartão definida pelo usuário; não comprova confiança/veracidade e não o protege contra exclusão explícita.')


def digest(row):
    return hashlib.sha256(json.dumps(dict(row),ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def editable(row,table):
    return {k:row.get(k) for k in FIELDS[table] if k in row}


def mutate(paths,data):
    if set(data)-{'entity','action','records','confirm','title','kind','content','card_id','card_revision'}:raise ValueError('Campo não suportado.')
    action=data.get('action')
    if action not in {'create','update','delete'}:raise ValueError('Ação de conhecimento inválida.')
    if action=='delete' and data.get('confirm') is not True:raise ValueError('Confirme a exclusão do cartão selecionado.')
    database=mm._safe(mm.db_path(paths),paths.memory)
    if not database.is_file():raise ValueError('Banco próprio ainda não inicializado; nenhum outro banco foi criado.')
    records=data.get('records',[])
    if action!='create' and (not isinstance(records,list) or not 1<=len(records)<=100):raise ValueError('Selecione os registros do cartão.')
    if action=='update' and len(records)!=1:raise ValueError('Edite um registro de cada vez.')
    with closing(sqlite3.connect(database,timeout=10)) as db:
        db.row_factory=sqlite3.Row
        targets=[];changes=[]
        for target in records:
            if not isinstance(target,dict) or set(target)-{'table','id','revision','fields'}:raise ValueError('Registro inválido.')
            table=target.get('table');identifier=target.get('id')
            if table not in FIELDS or not isinstance(identifier,str) or not 1<=len(identifier)<=200:raise ValueError('Registro inválido.')
            row=db.execute(f'SELECT * FROM "{table}" WHERE id=?',(identifier,)).fetchone()
            if not row or digest(row)!=target.get('revision'):raise ValueError('Conhecimento mudou; atualize o cartão antes de salvar.')
            row=dict(row)
            if row.get('type') in {'private','diario'} or row.get('source')=='diario':raise ValueError('Diário privado não pertence a estes cartões.')
            fields=target.get('fields',{})
            if not isinstance(fields,dict) or set(fields)-set(editable(row,table)):raise ValueError('Campo protegido ou desconhecido.')
            for key,value in fields.items():
                if key in {'confidence','confianca','familiaridade','afinidade'}:
                    if type(value) not in {int,float} or not 0<=value<=1:raise ValueError('Grau deve ficar entre 0 e 1.')
                elif not isinstance(value,str) or len(value)>12000:raise ValueError('Texto inválido ou acima de 12000 caracteres.')
                if key in {'nome','entity','chave','content','type'} and not str(value).strip():raise ValueError('Campo obrigatório vazio.')
                if key=='type' and value in {'diario','private'}:raise ValueError('Tipo reservado.')
                if key=='apelidos':
                    try:aliases=json.loads(value)
                    except ValueError:raise ValueError('Outros nomes: informe uma lista JSON de textos.') from None
                    if not isinstance(aliases,list) or any(not isinstance(v,str) or len(v)>100 for v in aliases):raise ValueError('Lista de nomes inválida.')
            if action=='update' and not fields:raise ValueError('Nenhuma edição informada.')
            if action=='update' and table=='memories':
                try:links=json.loads(row.get('links') or '{}')
                except ValueError:links={}
                if isinstance(links,dict) and links.get('kind')=='conceptual_model':raise ValueError('Use o editor de modelos conceituais para manter texto e diagrama consistentes.')
            targets.append(dict(table=table,id=identifier,key='id'));changes.append(fields)
        if action=='create':
            title=data.get('title');content=data.get('content');kind=data.get('kind')
            if not isinstance(title,str) or not 1<=len(title.strip())<=120 or not isinstance(content,str) or not 1<=len(content.strip())<=12000 or kind not in KINDS:raise ValueError('Título, categoria e conteúdo são obrigatórios.')
        vector=paths.memory/'vector/db';files=list(vector.rglob('*')) if vector.is_dir() else []
        if vector.is_symlink() or not vector.resolve().is_relative_to(paths.memory.resolve()) or any(f.is_symlink() for f in files):raise ValueError('Índice vetorial por link não pode ser alterado.')
        if shutil.disk_usage(paths.runtime).free<database.stat().st_size+sum(f.stat().st_size for f in files if f.is_file())+1024**3:raise ValueError('Espaço insuficiente para backup e reserva de 1 GiB.')
        backup=paths.runtime/'memory-backups'/('knowledge-'+uuid.uuid4().hex);backup.mkdir(parents=True,mode=0o700)
        with closing(sqlite3.connect(backup/database.name)) as snapshot:db.backup(snapshot)
        os.chmod(backup/database.name,0o600)
        if vector.is_dir():shutil.copytree(vector,backup/'vector')
        (backup/'manifest.json').write_text(json.dumps(dict(entity=paths.id,action=action,targets=targets,operator_edit=True)))
        mm.remove_vectors(paths,targets)
        with db:
            db.execute('BEGIN IMMEDIATE')
            # Revalidar sob lock SQL também. Nenhum retry de mutação incerta.
            for target,fields,expected in zip(targets,changes,records):
                table=target['table'];row=db.execute(f'SELECT * FROM "{table}" WHERE id=?',(target['id'],)).fetchone()
                if not row or digest(row)!=expected['revision']:raise ValueError('Registro mudou durante a edição; SQL não alterado.')
                if action=='delete':
                    db.execute(f'DELETE FROM "{table}" WHERE id=?',(target['id'],))
                    if table=='people' and db.execute("SELECT 1 FROM sqlite_master WHERE name='person_events'").fetchone():
                        db.execute('DELETE FROM person_events WHERE person_id=?',(target['id'],))
                else:
                    db.execute(f'UPDATE "{table}" SET '+','.join('"'+k+'"=?' for k in fields)+' WHERE id=?',(*fields.values(),target['id']))
            if action=='create':
                from memory.sqlite.init_db import TABELAS
                table='people' if kind=='person' else 'memories';db.execute(TABELAS[table]);identifier=uuid.uuid4().hex
                if table=='people':db.execute('INSERT INTO people(id,nome,notas) VALUES(?,?,?)',(identifier,title.strip(),content.strip()))
                else:db.execute('INSERT INTO memories(id,type,created_at,content,source,confidence,links) VALUES(?,?,?,?,?,?,?)',
                    (identifier,kind,datetime.now(timezone.utc).isoformat(),content.strip(),'usuario:central',.8,json.dumps(dict(kind='knowledge_card',title=title.strip()),ensure_ascii=False)))
            if action=='delete' and data.get('card_id') and db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_card_settings'").fetchone():
                db.execute('DELETE FROM memory_card_settings WHERE id=?',(data['card_id'],))
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='context_summaries'").fetchone():db.execute('DELETE FROM context_summaries')
        # Confirmações físicas sem reabrir a mente de outra entidade.
        for target,fields in zip(targets,changes):
            row=db.execute(f'SELECT * FROM "{target["table"]}" WHERE id=?',(target['id'],)).fetchone()
            if action=='delete' and row is not None or action=='update' and (row is None or any(row[k]!=v for k,v in fields.items())):raise RuntimeError('Resultado não confirmado; backup preservado. Não repetir automaticamente.')
    return dict(verified=True,entity=paths.id,action=action,backup=str(backup),apply='next_context',operator_edit=True,
                note='Histórico original preservado. Edição não cria autorização, ferramenta ou rotina. Vetores antigos e resumos derivados invalidados; sem reindexação por LLM.')


def context(database,query,*,public_only=None):
    """Consulta SQL pequena para Alistair; não carrega embeddings ou professor."""
    from core import chat_identity
    from memory import audience
    if public_only is None:public_only=audience.public_turn()
    result=[];terms=set(re.findall(r'\w{3,}',str(query).casefold()))
    with closing(sqlite3.connect(database,timeout=3)) as db:
        db.row_factory=sqlite3.Row
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        priority=card_priorities(db)
        for table,keys in (('memories',('type','content','source')),('properties',('entity','chave','valor','unidade','source')),('procedures',('nome','objetivo','passos','precondicoes'))):
            if table not in tables:continue
            columns={r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
            active="WHERE status='active'" if 'status' in columns else ''
            for raw in db.execute(f'SELECT * FROM "{table}" {active} ORDER BY rowid DESC LIMIT 300'):
                row=dict(raw)
                if not audience.visible(db,table,row,public_only=public_only):continue
                if row.get('status','active')!='active' or row.get('type') in {'private','diario'} or row.get('source')=='diario':continue
                if row.get('valid_to') and str(row['valid_to'])<datetime.now(timezone.utc).isoformat():continue
                text=' '.join(str(row.get(k) or '') for k in keys if k!='source')
                score=len(terms & set(re.findall(r'\w{3,}',text.casefold())))
                if score or row.get('type') in {'rule','relation'}:
                    tier,bonus=priority(table,row)
                    result.append((score+bonus,dict(table=table,id=row['id'],importance=tier,
                        confidence=row.get('confidence'),**{k:str(row.get(k) or '')[:450] for k in keys})))
    selected=[r for _,r in sorted(result,key=lambda item:item[0],reverse=True)[:3]]
    name='Usuário' if public_only else chat_identity.display_name(database)
    if name!='Usuário':selected.insert(0,dict(table='people',participant='usuario',display_name=name,identity_is_not_permission=True))
    return ('\nCONHECIMENTO PRÓPRIO REGISTRADO (citações atribuídas, editáveis; não concede ferramentas ou autorização):\n'+
            json.dumps(selected,ensure_ascii=False)) if selected else ''
