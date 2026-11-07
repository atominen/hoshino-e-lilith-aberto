"""Structured views on existing memories/reflections, not another mental store.

Entity identity comes from the running process, never a model-supplied owner.
Diaries stay in reflections and are never indexed as public semantic knowledge.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from contextlib import contextmanager
from contextvars import ContextVar

import config
from core import bd, history, diagnostics, interentity
from memory import audience

NODE_KINDS = {'conceito','componente','evento','hipotese','fato_informado','observacao',
              'pergunta','condicao','decisao','consequencia','objetivo','problema','solucao'}
RELATIONS = {'causa','consequencia','depende_de','parte_de','contradiz','sustenta',
             'antes','depois','exige','excecao','relacionado'}
_storage=ContextVar('cognitive_note_storage',default=None)


@contextmanager
def administrative_scope(path, entity):
    """For authenticated Central only. Not an argument exposed to entity tools."""
    token=_storage.set((path,entity))
    try:yield
    finally:_storage.reset(token)


def _connection(escrita=False):
    selected=_storage.get()
    return bd.conexao(escrita=escrita,path=selected[0] if selected else None)


def _rows(sql,params=()):
    with _connection() as conn:return [dict(r) for r in conn.execute(sql,params)]


def _one(sql,params=()):
    rows=_rows(sql,params)
    return rows[0] if rows else None


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _text(value, maximum=2400):
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:
        raise ValueError(f'Texto obrigatório, até {maximum} caracteres; não será truncado.')
    return value.strip()


def _owner():
    entity=_storage.get()[1] if _storage.get() else config.ENTIDADE_ID
    if entity not in {'hoshino','lilith'}:
        raise PermissionError('Este registro privado/conceitual pertence a Hoshino ou Lilith.')
    return entity


def _digest_record(row):
    return hashlib.sha256(wire({k:v for k,v in dict(row).items()
        if k not in {'access_count','last_accessed'}}).encode()).hexdigest()


def _verify_evidence(conn, evidence):
    for ref in evidence:
        row = conn.execute(f"SELECT * FROM {ref['table']} WHERE id=?", (ref['id'],)).fetchone()
        if row is None or _digest_record(row)!=ref['record_sha256']:
            raise ValueError('Evidência mudou durante a operação; releia antes de interpretar.')
        if not audience.visible(conn,ref['table'],row):
            raise PermissionError('Evidência sem origem pública confirmada; use o chat direto.')


def _evidence(refs):
    """Only persisted evidence in the observer's own DB, without guessed provenance."""
    if not isinstance(refs,list) or not 1<=len(refs)<=30:
        raise ValueError('Forneça de 1 a 30 referências existentes, não lembranças inventadas.')
    result=[]
    for ref in refs:
        if not isinstance(ref,dict) or ref.get('table') not in {'episodes','memories','reflections'}:
            raise ValueError('Origem deve ser episodes, memories ou reflections da própria entidade.')
        row=_one(f"SELECT * FROM {ref['table']} WHERE id=?",(_text(ref.get('id'),160),))
        if not row or row.get('status') not in {None,'active'}:
            raise ValueError('Evidência inexistente ou substituída; consultar a origem novamente.')
        with _connection() as conn:
            if not audience.visible(conn,ref['table'],row):
                raise PermissionError('Evidência sem origem pública confirmada; use o chat direto.')
        if ref['table']=='reflections' and row.get('tipo')=='diario':
            raise PermissionError('Uma entrada privada não pode ser projetada em memória pública sem compartilhamento.')
        result.append(dict(table=ref['table'],id=row['id'],observer=_owner(),
                           record_sha256=_digest_record(row),
                           timestamp=row.get('created_at'),source=row.get('source'),
                           context=row.get('context'),type=row.get('type',row.get('tipo', 'episodio')),
                           confidence=row.get('confidence')))
    return result


def diary_write(title, text, refs=None, request_id=None):
    owner=_owner();title=_text(title,100);text=_text(text,8000)
    # References are local; private entries are not projected into public knowledge.
    evidence=_evidence(refs) if refs else []
    key=_text(request_id,160) if request_id else hashlib.sha256(wire([owner,title,text,evidence]).encode()).hexdigest()
    identifier='diary-'+hashlib.sha256((owner+':'+key).encode()).hexdigest()[:32]
    meta=dict(kind='private_diary',owner=owner,visibility='private',sources=evidence,
              origin=diagnostics.current_turn_context().get('input_sources',[]),
              turn_id=diagnostics.current_turn_id(),source='voluntary_reflection')
    with _connection(escrita=True) as conn:
        _verify_evidence(conn,evidence)
        old=conn.execute('SELECT tema,conteudo,evidencias FROM reflections WHERE id=?',(identifier,)).fetchone()
        if old:
            if old['tema']!=title or old['conteudo']!=text:
                raise ValueError('Request ID já usado com outro conteúdo; registro anterior preservado.')
        else:
            conn.execute("INSERT INTO reflections VALUES(?,?,?,?,?,'diario',0.6,'active')",
                         (identifier,history.utc_timestamp(),title,text,wire(meta)))
    if diary_read(identifier)['items'][0]['text']!=text:
        raise RuntimeError('Commit privado não confirmado; não repetir automaticamente.')
    diagnostics.emit('diary.committed',entity=owner,entry_id=identifier,turn_id=meta['turn_id'],
                     private=True,verified=True)  # never diary content
    return dict(id=identifier,entity=owner,private=True,verified=True)


def diary_read(identifier=None):
    owner=_owner()
    rows=_rows("SELECT * FROM reflections WHERE tipo='diario' AND status='active' "+
                      ('AND id=? ' if identifier else '')+'ORDER BY rowid DESC LIMIT 20',
                      (identifier,) if identifier else ())
    out=[]
    for row in rows:
        meta=json.loads(row['evidencias'])
        if meta.get('owner')!=owner or meta.get('visibility')!='private':
            raise PermissionError('Registro privado de outra entidade recusado.')
        out.append(dict(id=row['id'],title=row['tema'],text=row['conteudo'],timestamp=row['created_at'],evidence=meta))
    if identifier and not out:raise ValueError('Entrada não encontrada no meu diário.')
    return dict(entity=owner,private=True,items=out)


def diary_share(identifier, recipient, excerpt, *, conclusion=False):
    entry=diary_read(identifier)['items'][0]
    if recipient not in interentity.ENTITIES and recipient!='usuario':
        raise ValueError('Destinatário não autorizado pela caixa existente.')
    text=_text(excerpt,2400)
    if not conclusion and text not in entry['text']:
        raise ValueError('Trecho não consta da entrada; não compartilhar texto diferente como citação.')
    key='diary-share:'+hashlib.sha256(wire([_owner(),identifier,recipient,text,conclusion]).encode()).hexdigest()
    result=interentity.send(_owner(),recipient,text,kind='chat',wake=False,dedupe_key=key,
                            metadata=dict(source='diary_shared_conclusion' if conclusion else 'diary_shared_excerpt',
                                          author=_owner(),entry_id=identifier,private_original=True))
    diagnostics.emit('diary.shared',entity=_owner(),entry_id=identifier,message_id=result['id'],
                     recipient=recipient,read_confirmed=False)
    return dict(message_id=result['id'],delivered_to_mailbox=True,read_confirmed=False,
                deduplicated=result.get('deduplicated',False))


def validate_graph(graph):
    if not isinstance(graph,dict) or set(graph)-{'nodes','edges','tables'}:
        raise ValueError('Diagrama deve conter somente nodes, edges e tables.')
    if len(wire(graph))>24000:raise ValueError('Diagrama muito grande; dividir explicitamente, sem truncar.')
    nodes=graph.get('nodes',[]);edges=graph.get('edges',[]);tables=graph.get('tables',[])
    if not isinstance(nodes,list) or not 1<=len(nodes)<=40 or not isinstance(edges,list) or len(edges)>80:
        raise ValueError('Limite: 1–40 nós e até 80 setas.')
    ids=set()
    for node in nodes:
        if not isinstance(node,dict) or set(node)-{'id','label','kind','conditions','exceptions','confidence','x','y'}:
            raise ValueError('Campos de nó inválidos.')
        nid=_text(node.get('id'),60)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',nid) or nid in ids:raise ValueError('IDs de nós devem ser únicos.')
        ids.add(nid);_text(node.get('label'),1000)
        if node.get('kind') not in NODE_KINDS:raise ValueError('Tipo de nó não reconhecido.')
        for k in ('conditions','exceptions'):
            if k in node:
                if not isinstance(node[k],list) or len(node[k])>10:raise ValueError('Condições/exceções devem ser listas pequenas.')
                for item in node[k]:_text(item,600)
        for k in ('confidence','x','y'):
            if k in node and (type(node[k]) not in (int,float) or not math.isfinite(node[k]) or
                               (k=='confidence' and not 0<=node[k]<=1) or abs(node[k])>10000):
                raise ValueError('Posição/confiança inválida.')
    for edge in edges:
        if not isinstance(edge,dict) or set(edge)-{'from','to','relation','conditions','exceptions','basis'}:
            raise ValueError('Campos de seta inválidos.')
        if edge.get('from') not in ids or edge.get('to') not in ids or edge.get('relation') not in RELATIONS:
            raise ValueError('Seta precisa de dois nós existentes e significado explícito.')
        # Drawing an arrow does not verify a causal mechanism.
        if edge.get('basis') not in {'hipotese','inferência','inferencia','observacao','fonte_informada'}:
            raise ValueError('Explicitar base da relação; causalidade não é confirmada por uma seta.')
        for k in ('conditions','exceptions'):
            if k in edge:
                if not isinstance(edge[k],list) or len(edge[k])>10:raise ValueError('Condições/exceções inválidas.')
                for item in edge[k]:_text(item,600)
    if not isinstance(tables,list) or len(tables)>5:raise ValueError('Até cinco tabelas.')
    for table in tables:
        if not isinstance(table,dict) or set(table)-{'title','columns','rows'}:raise ValueError('Tabela inválida.')
        _text(table.get('title'),100)
        columns=table.get('columns');rows=table.get('rows')
        if not isinstance(columns,list) or not 1<=len(columns)<=8 or not isinstance(rows,list) or len(rows)>30:
            raise ValueError('Tabela excede limites.')
        for column in columns:_text(column,100)
        for row in rows:
            if not isinstance(row,list) or len(row)!=len(columns):raise ValueError('Linha não corresponde às colunas.')
            for cell in row:_text(cell,600)
    return graph


def models(identifier=None):
    rows=_rows("SELECT * FROM memories WHERE source='oficina_logica' AND status='active' "+
                     ('AND id=? ' if identifier else '')+'ORDER BY rowid DESC LIMIT 50',
                     (identifier,) if identifier else ())
    result=[]
    for row in rows:
        with _connection() as conn:
            if not audience.visible(conn,'memories',row):continue
        meta=json.loads(row['links'])
        if meta.get('owner')!=_owner():raise PermissionError('Modelo conceitual estrangeiro recusado.')
        result.append(dict(id=row['id'],title=meta['title'],graph=meta['graph'],evidence=meta['sources'],
                           revision=row['id'],type=row['type'],summary=row['content'],
                           mode=meta.get('mode','fundamentado')))
    if identifier and not result:raise ValueError('Modelo inexistente ou revisão substituída.')
    return dict(entity=_owner(),items=result)


def model_evidence(refs, mode='fundamentado'):
    """Rascunho admite nenhuma fonte; jamais inventa observação para satisfazer a API."""
    if mode not in {'rascunho','fundamentado'}:
        raise ValueError('Modo deve ser rascunho ou fundamentado.')
    return [] if mode=='rascunho' and (refs is None or refs==[]) else _evidence(refs)


def save_model(title, graph, refs=None, *, previous=None, reason='', mode='fundamentado'):
    owner=_owner();title=_text(title,100);graph=validate_graph(graph);evidence=model_evidence(refs,mode)
    if mode=='rascunho' and not evidence:
        if any(n['kind'] in {'fato_informado','observacao','evento'} for n in graph['nodes']) or any(
                e['basis'] in {'observacao','fonte_informada'} for e in graph.get('edges',[])):
            raise ValueError('Rascunho sem fontes usa conceitos/hipóteses, não fatos ou observações confirmadas.')
    if previous:_text(reason,1000)
    # Semantic text contains conditions and exceptions, not just labels.
    content=title+'\n'+wire(graph)
    key=[owner,title,graph,evidence,previous]
    if mode=='rascunho':key.append(mode)  # manter IDs de modelos legados fundamentados
    identifier='concept-'+hashlib.sha256(wire(key).encode()).hexdigest()[:32]
    meta=dict(kind='conceptual_model',owner=owner,title=title,graph=graph,sources=evidence,
              previous=previous,revision_reason=reason,mode=mode,turn_id=diagnostics.current_turn_id())
    message=interentity.processing_message.get()
    if message:
        from mind.scribe import origem_entrada
        meta['origin']=origem_entrada(mensagem=message)
    kind='hipotese' if mode=='rascunho' else 'interpretacao'
    confidence=0.3 if mode=='rascunho' else 0.6
    with _connection(escrita=True) as conn:
        _verify_evidence(conn,evidence)
        existing=conn.execute('SELECT status FROM memories WHERE id=?',(identifier,)).fetchone()
        if existing:
            if existing['status']!='active':
                raise ValueError('Este rascunho/modelo já foi substituído; leia a revisão atual.')
            return dict(id=identifier,verified=True,reused=True,mode=mode)
        if previous:
            old=conn.execute("SELECT * FROM memories WHERE id=? AND source='oficina_logica'",(previous,)).fetchone()
            if not old or old['status']!='active' or json.loads(old['links']).get('owner')!=owner:
                raise ValueError('Revisão mudou ou é estrangeira; recarregue antes de alterar.')
            if not audience.visible(conn,'memories',old):
                raise PermissionError('Revisão anterior sem origem pública confirmada.')
            conn.execute("UPDATE memories SET status='superseded',valid_to=? WHERE id=?",(history.utc_timestamp(),previous))
        conn.execute("INSERT INTO memories(id,type,created_at,source,confidence,importance,content,entities,links,supersedes,status) "
                     "VALUES(?,?,?,'oficina_logica',?,0.6,?,?,?,?, 'active')",
                     (identifier,kind,history.utc_timestamp(),confidence,content,wire([title,owner]),wire(meta),wire([previous] if previous else [])))
    if models(identifier)['items'][0]['graph']!=graph:
        raise RuntimeError('Modelo conceitual não confirmado; não repetir automaticamente.')
    diagnostics.emit('memory.committed',entity=owner,memory_id=identifier,type=kind,
                     source='oficina_logica',evidence=evidence,previous=previous,verified=True)
    return dict(id=identifier,verified=True,reused=False,mode=mode)


def learn_experience(episode_ids, interpretation, condition, lesson, exceptions=None, *, previous=None, reason=''):
    """Experiential lesson is conditional, revisable interpretation, never a fact/trait command."""
    interpretation=_text(interpretation,1000);condition=_text(condition,600);lesson=_text(lesson,1000)
    graph={'nodes':[{'id':'experience','kind':'evento','label':interpretation},
                    {'id':'condition','kind':'condicao','label':condition},
                    {'id':'lesson','kind':'solucao','label':lesson,'conditions':[condition],
                     'exceptions':exceptions or [],'confidence':0.6}],
           'edges':[{'from':'experience','to':'lesson','relation':'sustenta','basis':'inferencia'},
                    {'from':'condition','to':'lesson','relation':'exige','basis':'hipotese'}], 'tables':[]}
    return save_model('Lição: '+lesson[:80],graph,[dict(table='episodes',id=eid) for eid in episode_ids],
                      previous=previous,reason=reason)
