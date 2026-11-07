"""Estado técnico de uma tarefa explícita, dentro dos recibos já existentes.

Não é scheduler, memória factual ou executor: só um novo namespace da tabela
alistair_actions. Nada avança sem uma mensagem humana nova no mesmo canal.
"""
import copy
import hashlib
import json
import re
import sqlite3
import time
import unicodedata
from contextlib import closing


PREFIX='dialogue-task:'


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(text).casefold())if not unicodedata.combining(c))


def presentation_details(text):
    """Somente pedido humano inequívoco: acordar UMA entidade e se apresentar.

    Citação, negação, hipótese, outro tipo de apresentação ou múltiplos alvos
    ficam no caminho normal, sem conceder efeitos por aproximação semântica.
    """
    value=fold(text).strip()
    if any(c in value for c in ('"',"'",'“','”','`')):
        return None
    if re.search(r'\b(nao|nunca|sem|imagine|hipotese|hipotetico|exemplo|frase|simule|simular|cancelar|cancele)\b',value):
        return None
    match=re.fullmatch(r'(?:alistair[,!: ]+)?(?:por favor[, ]+)?'
                       r'(?:(?:voce )?(?:pode|poderia|consegue)\s+|(?:quero|preciso) que (?:voce )?)?'
                       r'(?:(?:comecar|comcar|comece) a\s+)?'
                       r'(?:acordar|acorde|acorda|despertar|desperte|desperta)\s+(?:a\s+)?'
                       r'(?P<target>hoshino|lilith)\s+e\s+'
                       r'(?:se apresentar|se apresente|apresente-se|apresentar-se)'
                       r'(?:\s+(?:a|para)\s+(?P<receiver>ela|hoshino|lilith|alistair))?'
                       r'(?:,\s*alistair)?(?:[, ]+por favor)?[.!?]*',value)
    if not match:
        return None
    if re.search(r'\bse\s+(?:eu|voce|ela|ele|fosse|pudesse|quisesse)\b',value):
        return None
    target=match['target'];receiver=match['receiver']
    return dict(target=target,receiver=receiver,ambiguous=receiver not in(None,'ela',target))


def presentation_request(text):
    details=presentation_details(text)
    return details['target']if details and not details['ambiguous']else None


def is_continuation(text):
    return fold(text).strip(' \n.!?') in {'continue','continua','pode continuar','prossiga','siga','eu autorizo','pode prosseguir'}


def scope(message):
    metadata=message.get('metadata')or{}
    session=metadata.get('conversation_session')or{}
    identifier=session.get('id')or metadata.get('conversation_session_id')or'localhub'
    # Preserve legacy direct receipts; public continuation must never attach them.
    if metadata.get('chat_scope')=='global':identifier='global:'+identifier
    return dict(sender=message['sender'],session=identifier)


class Store:
    def __init__(self,path):self.path=path

    def save(self,task):
        data=copy.deepcopy(task);data['updated_at']=time.time()
        digest=hashlib.sha256(json.dumps([data['origin'],data['scope'],data['target']],sort_keys=True).encode()).hexdigest()
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT digest FROM alistair_actions WHERE id=?',(data['id'],)).fetchone()
            if previous and previous[0]!=digest:raise ValueError('Identidade da tarefa mudou; nenhuma ação repetida.')
            db.execute('INSERT INTO alistair_actions(id,digest,result) VALUES(?,?,?) '
                       'ON CONFLICT(id) DO UPDATE SET result=excluded.result',
                       (data['id'],digest,json.dumps(data,ensure_ascii=False,sort_keys=True)))
        task.update(updated_at=data['updated_at'])

    def select(self,message):
        if message['sender']!='usuario':return None
        details=presentation_details(message['text']);current=scope(message)
        with closing(sqlite3.connect(self.path))as db:
            rows=db.execute('SELECT result FROM alistair_actions WHERE id LIKE ? ORDER BY rowid DESC LIMIT 64',(PREFIX+'%',)).fetchall()
        tasks=[]
        for row in rows:
            try:task=json.loads(row[0])
            except (TypeError,ValueError):continue
            if task.get('schema')==1 and task.get('scope')==current:tasks.append(task)
        if details:
            target=details['target']
            identifier=PREFIX+hashlib.sha256(message['id'].encode()).hexdigest()[:32]
            existing=next((t for t in tasks if t['id']==identifier),None)
            if existing:return existing
            for previous in tasks:
                if previous['state']in {'pending','waiting_presence','awaiting_target'}:
                    previous['state']='superseded';self.save(previous)
            task=dict(schema=1,id=identifier,origin=message['id'],scope=current,target=target,
                      state='awaiting_target'if details['ambiguous']else'pending',intro_args=None,receipt=None,created_at=time.time(),
                      indicated_receiver=details['receiver'])
            self.save(task);return task
        awaiting=next((t for t in tasks if t['state']=='awaiting_target'and time.time()-t['updated_at']<=86400),None)
        if awaiting:
            answer=fold(message['text']).strip(' .!?')
            target=awaiting['target']
            if answer in {'sim','isso','exatamente','sim, para ela','sim para ela','para ela',
                          'para '+target,'para a '+target,'sim, para a '+target,'sim para a '+target}:
                awaiting.update(state='pending',authorization_source=message['id']);self.save(awaiting);return awaiting
        if is_continuation(message['text']):
            # Recusar reenvio mesmo se a última confirmação textual se perdeu.
            return next((t for t in tasks if t['state']not in {'superseded','cancelled','suspended'}
                         and time.time()-t['updated_at']<=86400),None)
        if fold(message['text']).strip(' .!')in {'cancele','cancelar','pare','deixa para la'}:
            for task in tasks:
                if task['state']in {'pending','waiting_presence','awaiting_target'}:
                    task['state']='cancelled';self.save(task)
        else:
            for task in tasks:
                if task['state']in {'pending','waiting_presence','awaiting_target'}:
                    task['state']='suspended';self.save(task)
        return None

    def schemas(self,task,available):
        if task.get('receipt'):return []
        if not any(t['function']['name']=='entidades_acordar'for t in available):
            raise ValueError('Despertar desativado; tarefa não executada.')
        if not any(t['function']['name']=='central_estado'for t in available):
            raise ValueError('Consulta de presença desativada; tarefa não executada.')
        original=next((t for t in available if t['function']['name']=='entidades_enviar_mensagem'),None)
        if original is None:raise ValueError('Envio desativado; tarefa não executada.')
        tool=copy.deepcopy(original)
        fn=tool['function'];fn['description']='Registra minha apresentação ao destinatário autorizado e pede seu despertar, se necessário. Recibo de envio não comprova presença ou leitura.'
        fn['parameters']['properties']['entidade']['enum']=[task['target']]
        fn['parameters']['properties']['acordar']={'type':'boolean','enum':[True]}
        fn['parameters']['required']=['entidade','texto','acordar']
        return [tool]

    def context(self,task):
        return ('TAREFA HUMANA AUTORIZADA: acordar '+task['target']+' e me apresentar. '
                'Este pedido já autoriza somente essas duas etapas; não pedir autorização redundante. '
                'Gerar minha apresentação com a identidade configurada e usar entidades_enviar_mensagem '
                'para esse destinatário com acordar=true. Só um recibo válido comprova envio; '
                'não responder com promessa de que vou enviar ou consultar. Uma continuação retoma a mesma tarefa, sem repetir efeitos.')


def verified_status(task,snapshot):
    """Confirmação mecânica, não fala inventada do modelo ou do destinatário."""
    if not task.get('receipt'):raise ValueError('Apresentação ainda sem recibo.')
    row=next((r for r in snapshot.get('presence',[])if r.get('entity_id')==task['target']),{})
    awake=row.get('status')=='awake'
    task['state']='completed'if awake else'waiting_presence'
    target=task['target'].capitalize()
    if awake:
        return f'Minha apresentação foi registrada para {target}, que está acordada. Isso não confirma que ela já leu ou respondeu.'
    return f'Minha apresentação foi registrada para {target}, mas o despertar ainda não está confirmado. A mensagem não será reenviada ao continuar.'
