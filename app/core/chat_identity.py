"""Nome de apresentação do humano em cada mente, nunca identidade de autorização.

Usa people do próprio SQLite. Não consulta conta do SO, configuração pessoal,
outras entidades, respostas de LLM ou texto citado para descobrir nomes.
"""
import json
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


UNKNOWN = {'', 'alguém', 'alguem', 'usuario', 'usuário', 'você', 'voce', 'local'}


def local_person(rows):
    candidates=[]
    for raw in rows:
        row=dict(raw)
        try:channels=json.loads(row.get('canais') or '{}')
        except (ValueError,TypeError):continue
        if not isinstance(channels,dict) or row.get('status','active')!='active':continue
        if channels.get('localhub')=='usuario':priority=2
        elif channels.get('tui')=='local':priority=1
        else:continue
        candidates.append((priority,str(row.get('ultimo_contato') or ''),row))
    return max(candidates,key=lambda item:item[:2])[2] if candidates else None


def display_name(database):
    path=Path(database)
    if not path.is_file():return 'Usuário'
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
        db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='people'").fetchone():return 'Usuário'
        person=local_person(db.execute('SELECT * FROM people').fetchall())
    name=str((person or {}).get('nome') or '').strip()
    return name if name.casefold() not in UNKNOWN else 'Usuário'


def explicit_name(text):
    # Declaração na primeira pessoa no início; perguntas, citações e encenação
    # não são aprendizado de identidade. Outro nome/apelido substitui o anterior.
    match=re.match(r"\s*(?:(?:oi|olá|ola|bom dia|boa tarde|boa noite)[!,.:\s]+)?(?:(?:agora|corrigindo)[,:]?\s+)?(?:meu nome [ée]|(?:eu )?me chamo|pode me chamar de|me chame de|prefiro que me chame de)\s+([^,!.;?\n]{1,100})(?:[,!.;\n]|$)",str(text),re.I)
    name=re.split(r'\s+e\s+',match[1],maxsplit=1,flags=re.I)[0].strip() if match else ''
    if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' -]{0,59}",name) or len(name.split())>5:return ''
    return name if name.casefold() not in UNKNOWN else ''


def learn(database, message, *, speech_understood=False):
    """Somente mensagem humana real aceita; cada runner escreve sua própria mente."""
    if message.get('sender')!='usuario':return False
    from core import speech_perception
    if speech_perception.is_voice(message) and not speech_understood:return False
    name=explicit_name(message.get('text',''))
    if not name:return False
    with closing(sqlite3.connect(database,timeout=10)) as db,db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        # Mesmo esquema já usado pelo núcleo social; Alistair não precisa do
        # pipeline afetivo para guardar a pessoa/autoria da conversa.
        from memory.sqlite.init_db import TABELAS
        db.execute(TABELAS['people'])
        person=local_person(db.execute('SELECT * FROM people').fetchall())
        now=datetime.now(timezone.utc).isoformat()
        if person:
            aliases=json.loads(person.get('apelidos') or '[]')
            if not isinstance(aliases,list):aliases=[]
            old=str(person.get('nome') or '')
            if old.casefold() not in UNKNOWN and old!=name and old not in aliases:aliases.append(old)
            db.execute('UPDATE people SET nome=?,apelidos=?,ultimo_contato=? WHERE id=?',
                       (name,json.dumps(aliases,ensure_ascii=False),now,person['id']))
        else:
            db.execute('INSERT INTO people(id,nome,canais,apelidos,primeiro_contato,ultimo_contato) VALUES(?,?,?,?,?,?)',
                       ('person-'+uuid.uuid4().hex,name,json.dumps({'localhub':'usuario'}),'[]',now,now))
    return True


def prefer(database, name):
    """Apelido escolhido nesta conversa humana; só muda a própria apresentação."""
    from core import interentity,diagnostics
    parent=interentity.processing_message.get() or {}
    with interentity._transaction() as transport:
        source=transport.execute('SELECT sender,recipient FROM entity_messages WHERE id=?',(str(parent.get('id','')),)).fetchone()
    if not source or source['sender']!='usuario' or source['recipient']!=Path(database).stem:raise ValueError('Forma de tratamento só pode mudar durante conversa própria com o humano local.')
    if not isinstance(name,str) or not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' -]{0,59}",name) or name.casefold() in UNKNOWN:raise ValueError('Nome/apelido inválido.')
    if display_name(database)=='Usuário':raise ValueError('Nome ainda desconhecido; mantenha Usuário até a pessoa se apresentar.')
    with closing(sqlite3.connect(database,timeout=10)) as db,db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
        person=local_person(db.execute('SELECT * FROM people').fetchall())
        if not person:raise ValueError('Pessoa local não encontrada.')
        aliases=json.loads(person.get('apelidos') or '[]')
        if person['nome'] not in aliases:aliases.append(person['nome'])
        db.execute('UPDATE people SET nome=?,apelidos=? WHERE id=?',(name,json.dumps(aliases,ensure_ascii=False),person['id']))
    verified=display_name(database)==name
    if not verified:raise RuntimeError('Forma de tratamento não confirmada; não repetir automaticamente.')
    diagnostics.emit('memory.committed',operation='human_display_name',source_id=parent['id'],person_id=person['id'],verified=True)
    return dict(verified=True,name=name,person_id=person['id'],authorization_changed=False)
