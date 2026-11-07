"""Audience checks over existing provenance; no new database or copied memory.

Unknown/mixed provenance is not public. This is a data-flow guard, not a sandbox
against arbitrary shell/filesystem access by a process running as the same user.
"""
import json
import sqlite3


def unpack(value):
    if isinstance(value,str):
        try:return json.loads(value)
        except (ValueError,TypeError):return None
    return value


def public_message(message):
    if not isinstance(message,dict):return False
    metadata=unpack(message.get('metadata')) or {}
    return (isinstance(metadata,dict) and metadata.get('chat_scope')=='global') or (
        message.get('sender') in {'hoshino','lilith','alistair'} and
        message.get('recipient') in {'hoshino','lilith','alistair'})


def public_turn():
    from core import interentity
    return public_message(interentity.processing_message.get())


def visible(conn, table, row, *, public_only=None, seen=frozenset()):
    """Require every source of a derived record to be public and still active."""
    if public_only is None:public_only=public_turn()
    if not public_only:return True
    row=dict(row)
    if row.get('status','active')!='active' or row.get('tipo',row.get('type')) in {'diario','private'}:
        return False
    key=(table,row.get('id'))
    if key in seen or len(seen)>=12:return False
    seen=seen|{key}

    def evidence(value):
        value=unpack(value)
        if isinstance(value,list):
            return bool(value) and len(value)<=100 and all(evidence(item) for item in value)
        if not isinstance(value,dict):return False
        # Public references do not make a privately written notebook public.
        if value.get('kind') in {'conceptual_model','knowledge_card'} and not value.get('origin'):
            return False
        # References must be revalidated, not trusted from a cached context.
        if value.get('table') in {'episodes','memories','reflections'} and value.get('id'):
            target=value['table']
            try:cursor=conn.execute(f'SELECT * FROM {target} WHERE id=?',(str(value['id']),))
            except sqlite3.OperationalError:return False  # reduced/legacy database: no proof
            found=cursor.fetchone()
            if found is None:return False
            record=dict(zip([c[0] for c in cursor.description],found)) if not hasattr(found,'keys') else dict(found)
            return visible(conn,target,record,public_only=True,seen=seen)
        if value.get('chat_scope')=='global' and value.get('message_id'):
            return True
        fields=[value[f] for f in ('sources','evidence','autoria','origin') if value.get(f)]
        return bool(fields) and all(evidence(field) for field in fields)

    if table=='episodes':return evidence(row.get('context'))
    if table=='properties':return evidence(row.get('source'))
    if table=='memories':return evidence(row.get('links'))
    if table=='reflections':return evidence(row.get('evidencias'))
    return False


# Until these interfaces have per-record audience metadata, do not load their
# private text into a public turn. Direct/private operation remains unchanged.
UNSCOPED_TOOLS=frozenset({
    'minha_atividade',
    'diario','consultar_resumo_diario','minhas_conclusoes','refletir','refletir_agora',
    'historico_chat','buscar_historico_chat','exportar_historico_chat',
    'quem_e','listar_pessoas','meu_perfil','meus_gostos','minha_opiniao','como_estou',
    'o_que_me_causa','resumo_do_dia','consultar_procedimento',
    'listar_lembretes','list_goals','lembrar_objetivo','minhas_tentativas',
})


def tool_allowed(name):
    return not (public_turn() and name in UNSCOPED_TOOLS)


def filter_schemas(schemas):
    return [schema for schema in schemas if tool_allowed(schema['function']['name'])]
