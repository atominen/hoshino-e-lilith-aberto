"""Contrato determinístico: o LLM propõe; ele nunca executa comandos."""
from __future__ import annotations
import hashlib
import json
import re
import os
from pathlib import Path

ENTITIES = ('hoshino', 'lilith', 'alistair')
CATEGORIES = {'ferramenta', 'raciocinio', 'naturalidade', 'memoria', 'personalidade', 'instrucao'}
PROFILES = {'nenhum': 0, 'conservador': 10, 'moderado': 30}
MAX_ITEMS = 12


def validate_plan(raw: object, *, entity: str, evidence_ids: set[str]) -> dict:
    """Rejeitar saídas livres, inventadas, perigosas ou de outro usuário/entidade."""
    if entity not in ENTITIES or not isinstance(raw, dict) or raw.get('entity') != entity:
        raise ValueError('Plano tem entidade incorreta.')
    if set(raw) != {'entity','profile','minutes','reason','examples'}:
        raise ValueError('Contrato do plano inesperado.')
    profile = raw['profile']
    if profile not in PROFILES or type(raw['minutes']) is not int or raw['minutes'] != PROFILES[profile]:
        raise ValueError('Duração arbitrária: apenas perfis preaprovados.')
    if not isinstance(raw['reason'], str) or not 8 <= len(raw['reason']) <= 1500:
        raise ValueError('Motivo inválido.')
    items=raw['examples']
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ValueError('Muitos exemplos.')
    if profile != 'nenhum' and len(items) < 2:
        raise ValueError('Dados insuficientes para recomendar treinamento.')
    if profile == 'nenhum' and items:
        raise ValueError('Plano sem treino não deve conter exemplos.')
    used=set(); cleaned=[]
    for item in items:
        required={'source_id','category','user','assistant','reason','confidence'}
        if not isinstance(item,dict) or not required.issubset(item) or set(item)-required-{'messages'}:
            raise ValueError('Formato de exemplo incorreto.')
        ref=item['source_id']
        if not isinstance(ref,str) or ref not in evidence_ids or ref in used:
            raise ValueError('Referência de origem ausente, duplicada ou não consultada.')
        used.add(ref)
        if item['category'] not in CATEGORIES:
            raise ValueError('Categoria não permitida.')
        for key,limit in [('user',1500),('assistant',2200),('reason',600)]:
            val=item[key]
            if not isinstance(val,str) or not val.strip() or len(val)>limit:
                raise ValueError('Texto de treinamento ausente ou excessivo.')
        confidence=item['confidence']
        if type(confidence) not in (float,int) or not 0 <= confidence <= 1:
            raise ValueError('Confiança inválida.')
        if 'messages' in item:
            messages=item['messages']
            if not isinstance(messages,list) or len(messages) not in (2,4,6):
                raise ValueError('Diálogo deve conter 1–3 turnos completos')
            for i,msg in enumerate(messages):
                if (not isinstance(msg,dict) or set(msg)!={'role','content'} or
                    msg['role']!=('user' if i%2==0 else 'assistant') or
                    not isinstance(msg['content'],str) or not 1<=len(msg['content'])<=600):
                    raise ValueError('Diálogo inválido/incompleto')
            if messages[-2]['content']!=item['user'] or messages[-1]['content']!=item['assistant']:
                raise ValueError('Par final diverge do diálogo; exportação ambígua')
        # Nota: confiança fornecida pelo próprio modelo não equivale a evidência externa.
        cleaned.append(item)
    return {'entity':entity,'profile':profile,'minutes':PROFILES[profile],
            'reason':raw['reason'],'examples':cleaned,'status':'PROPOSTA_NAO_APROVADA'}


def read_snapshot(path:Path, entity:str)->tuple[list[dict],str]:
    """Somente snapshot exportado explicitamente; jamais abrir SQLite/diários diretamente."""
    if entity not in ENTITIES:raise ValueError('Entidade inválida')
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2*1024*1024:
        raise ValueError('Snapshot inexistente, simbólico ou acima de 2 MiB.')
    data=path.read_bytes(); digest=hashlib.sha256(data).hexdigest()
    rows=[]; ids=set()
    for number,line in enumerate(data.splitlines(),1):
        if not line.strip():continue
        record=json.loads(line)
        required={'entity','source_id','messages'}
        if not isinstance(record,dict) or not required.issubset(record) or set(record)-required-{'human_feedback'}:
            raise ValueError(f'Snapshot linha {number}: campos inválidos')
        if record['entity']!=entity:raise ValueError('Mistura de entidades no snapshot')
        sid=record['source_id']
        if not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9:_./-]{6,160}',sid) or sid in ids:
            raise ValueError('ID de origem inválido/duplicado')
        ids.add(sid)
        msgs=record['messages']
        if not isinstance(msgs,list) or not 2<=len(msgs)<=12:raise ValueError('Mensagens insuficientes/excessivas')
        clean=[]
        for msg in msgs:
            if not isinstance(msg,dict) or set(msg)!={'role','content'} or msg['role'] not in ('user','assistant'):
                raise ValueError('Somente mensagens texto com origem user/assistant')
            content=msg['content']
            if not isinstance(content,str) or not 1<=len(content)<=2500:
                raise ValueError('Conteúdo incompatível')
            clean.append({'role':msg['role'],'content':content})
        row={'entity':entity,'source_id':sid,'messages':clean}
        if 'human_feedback' in record:
            feedback=record['human_feedback']
            fields={'schema','entity','message_id','author','source','decision','note','at','text_sha256','revision','turn_id','purpose'}
            if (not isinstance(feedback,dict) or set(feedback)!=fields or
                    type(feedback['schema']) is not int or feedback['schema']!=1 or feedback['entity']!=entity or
                    feedback['author']!='usuario' or feedback['source']!='central_user_feedback' or
                    feedback['purpose']!='quality_feedback_not_training_approval' or feedback['decision'] not in ('liked','disliked') or
                    not isinstance(feedback['note'],str) or len(feedback['note'])>600 or
                    any(not isinstance(feedback[k],str) or not 1<=len(feedback[k])<=160 for k in ('message_id','at','revision','turn_id')) or
                    not isinstance(feedback['text_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',feedback['text_sha256'])):
                raise ValueError('Avaliação humana inválida/estrangeira; não é aprovação de treinamento.')
            row['human_feedback']=dict(feedback)
        rows.append(row)
        if len(rows)>40:raise ValueError('Limite do piloto: 40 episódios por análise; dividir em lotes')
    if not rows:raise ValueError('Snapshot vazio')
    return rows,digest


def atomic_json(path:Path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():raise PermissionError('Destino simbólico recusado')
    temp=path.with_name('.tmp-'+path.name)
    if temp.exists():raise RuntimeError('Arquivo temporário existente')
    with temp.open('x',encoding='utf-8') as out:
        json.dump(obj,out,ensure_ascii=False,indent=2)
        out.flush()
        os.fsync(out.fileno())
    temp.replace(path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
