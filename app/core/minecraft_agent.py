"""Objetivos verificáveis de Minecraft: observar, escolher uma ação e conferir.

Sem executor/scheduler próprio. Callbacks usam o modelo, dispatcher e banco da
entidade. Critérios descrevem resultados; não contêm receitas ou um roteiro.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from copy import deepcopy
from core import bd, intent, minecraft_stations

ALIASES={
    'crafting_table':('bancada','mesa de trabalho'),
    'wooden_pickaxe':('picareta de madeira',), 'stone_pickaxe':('picareta de pedra',),
    'iron_pickaxe':('picareta de ferro',), 'diamond_pickaxe':('picareta de diamante',),
    'furnace':('forno',), 'iron_ingot':('lingote de ferro','lingotes de ferro'),
    'diamond':('diamante','diamantes'),
    'bow':('arco',), 'arrow':('flecha','flechas'),
}
# Pedido humano 28/10: carnes de animais, iguais ou diferentes, contam juntas.
GROUPS={'cooked_meat':('cooked_beef','cooked_porkchop','cooked_chicken','cooked_mutton','cooked_rabbit',
                       'cooked_cod','cooked_salmon')}
# Decisões seguidas sem mudança observada antes de pausar. Recusas informativas
# precisam de espaço para virar correção; repetição idêntica é barrada à parte.
PATIENCE=max(2,int(os.environ.get('HOSHINO_MINECRAFT_PACIENCIA','6')))
BARRIER_LEVELS=2  # revisar o plano; depois perguntar ao humano pelo chat; só então pausar
SLOTS=('head','torso','legs','feet')
# Conjuntos nomeados: armadura equipada e ferramentas no inventário, tudo fabricado.
SETS={'armadura completa de diamante':(dict(zip(SLOTS,('diamond_helmet','diamond_chestplate','diamond_leggings','diamond_boots'))),()),
      'kit completo de ferro':(dict(zip(SLOTS,('iron_helmet','iron_chestplate','iron_leggings','iron_boots'))),
                               ('iron_sword','iron_pickaxe','iron_axe','iron_shovel'))}
# Consultas que não dependem do mundo conectado nem mudam nada nele.
NO_WORLD={'minecraft_conectar','minecraft_conectar_lan','minecraft_iniciar_ponte','minecraft_desconectar',
          'minecraft_parar','minecraft_manual','minecraft_estado','minecraft_descobrir_lan','web_search'}
READ_ONLY={'web_search','minecraft_manual','minecraft_estado','minecraft_inventario','minecraft_receitas',
           'minecraft_procurar_bloco','minecraft_descobrir_lan'}

class DecisionRejected(ValueError):
    """Resposta de decisão inválida antes de qualquer efeito; vira retorno ao modelo."""

def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def _context_clause(text):
    """Preâmbulos/contexto explícitos da gramática restrita; nunca comandos extras."""
    text=re.sub(r'^minecraft\s*[:,]?\s*','',text).strip(' ,.;:')
    if not text:return True
    if re.match(r'^(?:host|porta|versao)\b',text):
        return all(w in {'host','porta','versao','auth','offline','microsoft','e','localhost'}
                   for w in re.findall(r'[a-z_]+',text))
    if text.startswith('conecte'):
        # Um nome de jogador pode aparecer imediatamente após o verbo.
        text=re.sub(r'^(conecte)\s+[a-z0-9_]{3,16}(?=\s+(?:ao|a|em|no|o|para)\b)',r'\1',text)
        words={'conecte','ao','a','em','no','na','o','para','mundo','servidor','lan','ja','aberto',
               'host','porta','versao','e','auth','offline','microsoft','se','estiver','desconectada',
               'local','remoto','com','endereco','localhost','ip'}
        return all(w in words for w in re.findall(r'[a-z_]+',text))
    compact=re.sub(r'[,;\s]+',' ',text).strip()
    if compact in {'voce decide materiais quantidades e sequencia observando as receitas reais',
                   'sem cheats presentes ou comandos administrativos','permaneca conectada'}:return True
    compact=re.sub(r'^o mundo foi reaberto apos uma queda de energia ','',compact)
    if re.fullmatch(r'o (?:inventario anterior|ultimo inventario observado) tinha \d+ [a-z0-9_]+'
                    r'(?: (?:e )?\d+ [a-z0-9_]+)* confira o estado atual',compact):return True
    return bool(re.fullmatch(r'a meta final posterior e (?:armadura (?:completa )?de diamante|kit completo de ferro)',compact))

def targets(text):
    t=intent.normalizar(text)
    # RP explícito é diálogo do ensaio, não uma etapa de trabalho no mundo.
    # Mantém a progressão separada do comentário "voltamos depois da queda".
    t=re.split(r'\brp(?:\s+de\s+[^:\n]{1,140})?\s*:',t,maxsplit=1)[0].strip()
    # Pedido humano 27/10: depois do kit, "mate um mob qualquer"; jogadores nunca são alvo.
    kill=re.search(r'\b(?:mate|matar)\s+(?:um|1)\s+mob(?:\s+(?:qualquer|aleatorio))?(?:\s+em\s+sobrevivencia)?'
                   r'(?:\s*,?\s*sem\s+atacar\s+jogadores)?',t)
    if kill:t=t[:kill.start()]+t[kill.end():]
    meat=re.search(r'\b(?:consiga|obtenha|tenha)\s+(\d+)\s+carnes\s+(?:assadas|cozidas)(?:\s+de\s+animais)?'
                   r'(?:\s*,?\s*iguais\s+ou\s+diferentes)?',t)
    if meat:
        if not 1<=int(meat[1])<=64:return None
        t=t[:meat.start()]+t[meat.end():]
    from core.activity_context import classify
    if ('minecraft' not in t or classify(t,['minecraft_craft'])[1]!='integrated_agent' or
        re.search(r'\b(?:sem executar|nao execute|discord|criativo|creative|arquivo|oficina|programa|'
                  r'escreva|escrever|envie|enviar|converse|conversar|crie|criar|construa|construir|'
                  r'explore|explorar|procure|procurar|encontre|encontrar|derrote|derrotar|mate|matar|'
                  r'faca|fazer|monte|montar)\b',t)):
        return None
    result={'inventory':{},'equipped':{},'placed':{},'crafted':{}}
    verbs=r'(?:fabrique|fabricar|crafte|construa|consiga|obtenha|colete|equipe|vista|coloque)'
    from core import task_state
    # Uma macroetapa desconhecida não pode desaparecer da conclusão. Conexão
    # pode ser pré-requisito da primeira etapa; as seguintes precisam de alvo
    # reconhecido e passar pela gramática restrita abaixo.
    if any(not re.search(r'\b'+verbs+r'\b',part) for part in task_state.decompor(t)[1:]):return None
    for sentence in re.split(r'[.!?]\s+',t):
        positive=re.sub(r'\b(?:nao|nem|sem)\s+'+verbs+r'\b','',sentence)
        if not re.search(r'\b'+verbs+r'\b',positive):
            if not _context_clause(positive):return None
            continue
        # A gramática é deliberadamente restrita: um segundo objeto desconhecido
        # não pode sumir do contrato e permitir concluir só metade do pedido.
        actions=list(re.finditer(r'\b'+verbs+r'\b',positive))
        if not _context_clause(positive[:actions[0].start()]):return None
        phrases=sorted({p for k,values in ALIASES.items() for p in (k,*values)},key=len,reverse=True)
        for index,action in enumerate(actions):
            fragment=positive[action.end():actions[index+1].start() if index+1<len(actions) else len(positive)]
            for set_name in SETS:fragment=re.sub(r'\b'+set_name+r'\b','',fragment)
            for phrase in phrases:fragment=re.sub(r'\b'+re.escape(phrase)+r'\b','',fragment)
            fragment=re.sub(r'\bem sobrevivencia\b|\bno inventario\b','',fragment)
            fragment=re.sub(r'\b(?:e|ou|uma|um|as|os|a|o|sua|seu|minha|meu|nova|novo)\b|\d+|[^\w\s]','',fragment)
            if fragment.strip():return None
        named=[n for n in SETS if re.search(r'\b(?:fabrique|fabricar|equipe|vista)\b.{0,70}\b'+n+r'\b',positive)]
        if named:
            outside=positive
            for n in named:outside=re.sub(r'\b'+n+r'\b','',outside)
            if len(named)>1 or any(result.values()) or any(re.search(r'\b'+re.escape(phrase)+r'\b',outside) for phrase in phrases):
                return None  # Não omitir um segundo resultado ao reconhecer o conjunto.
            armor,tools=SETS[named[0]];craft=re.search(r'\b(?:fabrique|fabricar|crafte)\b',positive)
            for slot,name in armor.items():
                result['equipped'][slot]=name
                if craft:result['crafted'][name]=1
            for name in tools:
                result['inventory'][name]=1
                if craft:result['crafted'][name]=1
            continue
        for name,aliases in ALIASES.items():
            pattern=r'\b(?:'+ '|'.join(map(re.escape,(name,*aliases)))+r')\b'
            match=re.search(pattern,positive)
            if not match or not re.search(r'\b'+verbs+r'\b',positive[:match.start()]):continue
            if name=='diamond' and re.search(r'\bpicareta de diamante\b',positive):
                if re.search(r'\bdiamantes?\b',re.sub(r'\bpicareta de diamante\b','',positive)):
                    return None  # Um objeto adicional não pode ser omitido do contrato.
                continue
            quantity=re.search(r'(\d+)\s+(?:'+ '|'.join(map(re.escape,(name,*aliases)))+r')\b',positive)
            count=int(quantity[1]) if quantity else 1
            if not 1<=count<=64:return None
            result['inventory'][name]=count
            if re.search(r'\b(?:fabrique|fabricar|crafte|construa)\b',positive[:match.start()]):result['crafted'][name]=count
            if name in {'crafting_table','furnace'} and re.search(r'\bcoloque\b',positive):
                result['placed'][name]=count;result['inventory'].pop(name,None)
    if kill:result['killed']={'mob':1}
    if meat:result['groups']={'cooked_meat':int(meat[1])}
    return result if any(result.values()) else None

def initial(goal,criteria):
    return {'version':2,'goal_hash':_digest(goal),'targets':deepcopy(criteria),'crafted':{},'placed':{},
            'placement_records':{},'placed_present':{},'placement_checks':{},'target':{},'session_id':None,
            'events':[],'pending':None,'failures':{},'observations':[],'no_progress':0,'steps':0}

def _schema():
    bd.executar('''CREATE TABLE IF NOT EXISTS conversation_task_game_states(
        task_id TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL)''',strict=True)

def load(task,criteria):
    _schema();row=bd.um('SELECT payload FROM conversation_task_game_states WHERE task_id=?',(task.id,),strict=True)
    cp=json.loads(row['payload']) if row else initial(task.objetivo,criteria)
    if cp.get('version')!=2:raise ValueError('MINECRAFT_CHECKPOINT_REVIEW_REQUIRED')
    if cp.get('goal_hash')!=_digest(task.objetivo) or cp.get('targets')!=criteria:raise ValueError('MINECRAFT_GOAL_CHANGED')
    return cp

def save(task,cp):
    _schema()
    bd.executar('''INSERT INTO conversation_task_game_states(task_id,payload,updated_at) VALUES(?,?,?)
        ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at''',
        (task.id,json.dumps(cp,ensure_ascii=False),bd.agora()),strict=True)

def inventory(items):
    return {str(i['name']):int(i.get('count',0)) for i in items or [] if isinstance(i,dict) and i.get('name')}

def identity_matches(cp,state):
    return (state.get('connected') is True and state.get('verified') is True
        and isinstance(state.get('sessionId'),str) and bool(state['sessionId'])
        and isinstance(state.get('host'),str) and isinstance(state.get('port'),int)
        and all(state.get(k)==v for k,v in cp.get('target',{}).items()))

def review_session_continuity(cp,state,*,reviewer,reason,evidence):
    """Reconciliação atribuída do operador; não é ferramenta acessível ao LLM.

    O endereço não prova identidade do mundo. Quem revisa deve conferir o mundo,
    inventário/recibos e registrar a evidência; isto não resolve efeitos pendentes.
    """
    if (cp.get('pending') or not identity_matches(cp,state) or not cp.get('session_id')
            or cp['session_id']==state.get('sessionId') or not cp.get('username')
            or cp['username']!=state.get('username') or not str(reviewer).strip()
            or not str(reason).strip() or not isinstance(evidence,list)
            or not evidence or any(not isinstance(e,str) or not e.strip() for e in evidence)):
        raise ValueError('MINECRAFT_SESSION_REVIEW_INVALID')
    review=dict(old_session=cp['session_id'],new_session=state['sessionId'],
        target=deepcopy(cp['target']),username=state['username'],reviewer=str(reviewer),
        reason=str(reason),evidence=evidence[:16],reviewed_at=bd.agora())
    cp['reviewed_reconnection']=review
    return deepcopy(review)

def _bind(cp,state):
    if not identity_matches(cp,state):return ''
    old=cp.get('session_id')
    if cp.get('username') and state.get('username')!=cp['username']:
        return 'Outro jogador no destino; o progresso registrado pertence a '+str(cp['username'])+'.'
    if old and old!=state['sessionId']:
        if any(cp['crafted'].values()) or cp['placement_records']:
            review=cp.get('reviewed_reconnection') or {}
            if (review.get('old_session')!=old or review.get('new_session')!=state['sessionId']
                    or review.get('target')!=cp['target'] or review.get('username')!=state.get('username')):
                return 'A sessão mudou após progresso; confira a continuidade do mundo e reconcilie os recibos antes de retomar.'
            cp['session_reviews']=(cp.get('session_reviews',[])+[cp.pop('reviewed_reconnection')])[-32:]
        cp['previous_sessions']=(cp.get('previous_sessions',[])+[old])[-32:]
        cp['placed_present'].clear();cp['placement_checks'].clear()
    cp['session_id']=state['sessionId']
    if state.get('username'):cp['username']=state['username']
    for k in ('host','port','version'):cp['target'].setdefault(k,state.get(k))
    return ''

def confirm_placements(cp,name,positions,state):
    if not identity_matches(cp,state) or cp.get('session_id')!=state.get('sessionId'):
        cp['placed_present'][name]=0;return
    visible={tuple((entry.get('position') or {}).get(k) for k in ('x','y','z')) for entry in positions}
    sessions={state['sessionId'],*cp.get('previous_sessions',[])}
    owned={tuple(item['position'].get(k) for k in ('x','y','z')) for item in cp['placement_records'].values()
           if item['name']==name and item['session_id'] in sessions and item['dimension']==state.get('dimension')}
    cp['placed_present'][name]=len(visible&owned)
    cp['placement_checks'][name]=state.get('_observation_receipt_id')

def finished(criteria,cp,state):
    if not criteria or state.get('connected') is not True or state.get('verified') is not True or state.get('gameMode')!='survival':return False
    if not identity_matches(cp,state) or cp.get('session_id')!=state.get('sessionId'):return False
    counts=inventory(state.get('inventory'))
    return (all(counts.get(k,0)>=n for k,n in criteria['inventory'].items()) and
        all(cp['crafted'].get(k,0)>=n for k,n in criteria['crafted'].items()) and
        all(cp['placed_present'].get(k,0)>=n and state.get('_observation_receipt_id')
            and cp['placement_checks'].get(k)==state['_observation_receipt_id'] for k,n in criteria['placed'].items()) and
        all((state.get('equipment',{}).get(slot) or {}).get('name')==name for slot,name in criteria['equipped'].items()) and
        len(cp.get('kills') or [])>=(criteria.get('killed') or {}).get('mob',0) and
        all(sum(counts.get(i,0) for i in GROUPS[g])>=n for g,n in (criteria.get('groups') or {}).items()))

def remaining(criteria,cp,state):
    """O que ainda falta, pelos mesmos dados de `finished`; resultado, não sequência."""
    counts=inventory(state.get('inventory'))
    present=lambda k:cp['placed_present'].get(k,0) if cp['placement_checks'].get(k)==state.get('_observation_receipt_id') else 0
    gaps={'fabricar':{k:n-cp['crafted'].get(k,0) for k,n in criteria['crafted'].items() if cp['crafted'].get(k,0)<n},
          'colocar_no_mundo_conferido':{k:n-present(k) for k,n in criteria['placed'].items() if present(k)<n},
          'ter_no_inventario':{k:n-counts.get(k,0) for k,n in criteria['inventory'].items() if counts.get(k,0)<n},
          'equipar':{slot:name for slot,name in criteria['equipped'].items()
                     if (state.get('equipment',{}).get(slot) or {}).get('name')!=name},
          'matar':{'mob':(criteria.get('killed') or {}).get('mob',0)-len(cp.get('kills') or [])}
                  if len(cp.get('kills') or [])<(criteria.get('killed') or {}).get('mob',0) else {},
          'ter_no_inventario_qualquer':{g+' ('+', '.join(GROUPS[g])+')':n-sum(counts.get(i,0) for i in GROUPS[g])
              for g,n in (criteria.get('groups') or {}).items() if sum(counts.get(i,0) for i in GROUPS[g])<n}}
    return {k:v for k,v in gaps.items() if v}

def record(cp,tool,args,result,comment):
    if result.get('receipt_id') and any(e.get('receipt_id')==result['receipt_id'] for e in cp['events']):return
    event={'tool':tool,'arguments':args,'status':result.get('status','unknown'),'receipt_id':result.get('receipt_id'),
           'output':str(result.get('output',''))[:3000],'comment':str(comment or '')[:500],
           'verified':result.get('verified') is True,'mutates':bool(result.get('mutates',tool not in READ_ONLY))}
    cp['events'].append(event);cp['events']=cp['events'][-128:]
    if not result.get('ok') or not result.get('receipt_id'):return
    try:data=json.loads(result.get('output') or '{}')
    except (ValueError,TypeError):return
    # Compacta antes do corte do output: receitas obtidas continuam visíveis
    # depois que o recibo original sai da janela de eventos recentes.
    if tool=='minecraft_receitas' and isinstance(data,list):event['recipes']=_compact_recipes(data)
    if not isinstance(data,dict):return
    if tool=='minecraft_craft':
        name=data.get('item');before=inventory(data.get('before'));after=inventory(data.get('after'))
        delta=after.get(name,0)-before.get(name,0)
        if isinstance(name,str) and delta>0:cp['crafted'][name]=cp['crafted'].get(name,0)+delta
    if tool=='minecraft_atacar' and data.get('morto') is True and isinstance(data.get('alvo'),str):
        # Só a morte confirmada pelo evento do servidor, na sessão da tarefa, conta.
        if data.get('sessionId')==cp.get('session_id') and cp.get('session_id'):
            # 29/10: a caça em série devolve cada morte em abatidos.
            slain=data.get('abatidos') if isinstance(data.get('abatidos'),list) else [{'alvo':data['alvo'],'entidade_id':data.get('entidade_id')}]
            cp['kills']=[*(cp.get('kills') or []),*({'mob':k.get('alvo'),'entity_id':k.get('entidade_id'),
                                                     'receipt_id':result.get('receipt_id')} for k in slain if isinstance(k,dict))][-10:]
    if tool=='minecraft_colocar_bloco':
        placed=data.get('placed') or {}
        if (placed.get('verified') is True and placed.get('position') and isinstance(placed.get('name'),str)
                and placed.get('sessionId')==cp.get('session_id') and cp.get('session_id')):
            item={'name':placed['name'],'position':placed['position'],'session_id':placed['sessionId'],
                  'dimension':placed.get('dimension')}
            key=_digest([item['session_id'],item['dimension'],item['position']])
            cp['placement_records'][key]=item
            cp['placed']={name:sum(i['name']==name for i in cp['placement_records'].values())
                          for name in {i['name'] for i in cp['placement_records'].values()}}
            cp['placed_present'][item['name']]=0
            # 30/10 (pedido humano): bancada/forno colocados ficam lembrados entre tarefas.
            try:minecraft_stations.registrar_colocacao(cp.get('target') or {},placed,result.get('receipt_id'))
            except Exception:pass  # noqa: BLE001

def _compact_recipes(data):
    variants=[]
    for recipe in data:
        if not isinstance(recipe,dict):continue
        variant={'bancada':recipe.get('requiresTable') is True,'produz':(recipe.get('result') or {}).get('count'),
            'ingredientes':{i['name']:i.get('count') for i in recipe.get('ingredients') or []
                            if isinstance(i,dict) and isinstance(i.get('name'),str)}}
        if variant not in variants:variants.append(variant)
    return variants[:12]

def known_recipes(cp,limit=8):
    """Receitas reais já recebidas por recibo, a mais recente de cada item."""
    known={}
    for event in cp['events']:
        name=(event.get('arguments') or {}).get('nome')
        if event.get('tool')!='minecraft_receitas' or not isinstance(name,str):continue
        variants=event.get('recipes')
        if variants is None and event.get('status')=='success' and event.get('receipt_id'):
            try:data=json.loads(event.get('output') or '')  # checkpoint anterior ao campo compacto
            except (ValueError,TypeError):data=None
            variants=_compact_recipes(data) if isinstance(data,list) else None
        if isinstance(variants,list):known.pop(name,None);known[name]=variants
    # Uma linha por bancada/rendimento: JSON detalhado por variante levou o
    # modelo a reescrever as receitas e esgotar a saída antes da chamada.
    compact={}
    for name,variants in list(known.items())[-limit:]:
        groups={}
        for v in variants:
            needs=' + '.join(f'{count} {item}' for item,count in (v.get('ingredientes') or {}).items())
            groups.setdefault((v.get('bancada'),v.get('produz')),[]).append(needs)
        compact[name]=[f"{'com' if table else 'sem'} bancada, rende {amount}: "+' | '.join(options)
                       for (table,amount),options in groups.items()]
    return compact

def _observed(state,cp):
    # Inclui a conexão: desconectada, o estado de jogo é todo nulo e não distingue nada.
    return _digest({k:state.get(k) for k in ('connected','sessionId','connectionState','inventory','equipment',
        'position','health','food')}|{'placed':cp['placed']})

def _world(state,cp):
    return _digest({k:state.get(k) for k in ('inventory','equipment','position','health','food')}|{'placed':cp['placed']})

def _conditions(state,cp):
    return _digest({'inventory':inventory(state.get('inventory')),'equipment':state.get('equipment'),
        'held':(state.get('heldItem') or {}).get('name'),
        'server':{k:state.get(k) for k in ('host','port','sessionId','dimension')},
        'placed':cp['placed_present']})

async def run(criteria,cp,*,ask,execute,observe,persist,allowed,validate,limit=128,cancelled=lambda:False,resume=False):
    used=[]
    def end(status,reason,state=None):return {'status':status,'reason':reason,'used':used,'state':state or {},'checkpoint':cp}
    if cp.get('pending') and cp['pending'].get('mutates'):return end('uncertain','Efeito anterior ainda sem reconciliação; não repetido.')
    cp['pending']=None
    if resume:
        cp['no_progress']=0;persist(cp)  # Nova tentativa humana; falhas/incertezas permanecem.
    for _ in range(max(1,min(128,int(limit)))):
        if cancelled():return end('cancelled','Interrupção solicitada; tarefa preservada.')
        state=await observe()
        source_error=_bind(cp,state)
        if source_error:return end('paused',source_error,state)
        if identity_matches(cp,state) and state.get('gameMode')!='survival':return end('paused','Modo sobrevivência não confirmado.',state)
        if finished(criteria,cp,state):persist(cp);return end('completed','Critérios conferidos no mundo.',state)
        if cp['no_progress']>=PATIENCE:
            # Pedido humano 27/10: barreira não encerra a entidade. Nível 1: explicar o erro
            # do plano e recalcular (DEPS); nível 2: perguntar ao humano pelo chat do jogo.
            level=(cp.get('barrier') or {}).get('level',0)
            if level>=BARRIER_LEVELS:
                return end('paused',f'{PATIENCE} decisões sem progresso mesmo depois de rever o plano e de poder perguntar ao humano; tarefa preservada.',state)
            cp['barrier']={'step':cp['steps'],'level':level+1,'reason':f'{PATIENCE} decisões seguidas sem progresso observado'}
            cp['no_progress']=0;persist(cp)
        ground=_world(state,cp)
        conditions=_conditions(state,cp)
        try:decision=await ask(state,cp)
        except DecisionRejected as exc:
            # Texto sem chamada ou argumentos inválidos não executam nada: a próxima
            # decisão vê a recusa, e o limite de falta de progresso continua valendo.
            cp['no_progress']+=1;cp['events'].append({'tool':None,'status':'rejected_before_effect',
                'output':'Decisão recusada, nenhuma ação executada: '+str(exc)[:600]})
            persist(cp);continue
        except Exception as exc:
            return end('paused','Não consegui decidir a próxima ação: '+type(exc).__name__,state)
        tool=decision.get('tool');args=decision.get('arguments') or {}
        error=validate(tool,args) if tool in allowed else 'Ferramenta fora do escopo Minecraft.'
        connection=tool in NO_WORLD
        if not connection and not identity_matches(cp,state):error='Destino observado não corresponde ao objetivo; conecte ao endereço autorizado primeiro.'
        if tool in {'minecraft_conectar','minecraft_conectar_lan'} and identity_matches(cp,state):error='Já estou conectada ao destino autorizado; não reconectar sem necessidade.'
        chat_ids=[m.get('id') for m in state.get('recentChat',[]) if isinstance(m,dict)] if tool=='minecraft_chat' else []
        reply_context=decision.get('chat_context',chat_ids[-1:]) if tool=='minecraft_chat' else []
        reply_context=[x for x in reply_context if x in chat_ids] if isinstance(reply_context,list) else []
        signature=_digest([tool,args,reply_context]) if tool=='minecraft_chat' else _digest([tool,args])
        previous=cp['failures'].get(signature)
        if previous and not (previous.get('precondition') and previous.get('ground')!=conditions):error='Chamada falhou sem mudança dos pré-requisitos; escolha outra abordagem.'
        if tool=='__done__':error='O inventário/recibos ainda não satisfazem o objetivo; fala não é conclusão.'
        if not error and tool=='registrar_procedimento':
            from core.minecraft_cognition import registration_cooldown
            if registration_cooldown(cp):
                error=('Você registrou um procedimento há poucos passos; registre de novo depois de conquistar algo '
                       'novo do objetivo.')
        if not error and tool=='minecraft_chat' and state.get('onlinePlayers')==[]:
            # 12/11 (humano): sem mais ninguém no servidor, a fala no chat não tem quem leia nem responda.
            error=('Só você está no servidor agora; ninguém vai ler o chat. Descubra pelo mundo '
                   '(percepção, procurar, explorar) ou pesquise.')
        last=cp.get('last_success') or {}
        if not error and last.get('signature')==signature and last.get('observed')==_observed(state,cp):
            error='Essa mesma chamada acabou de dar certo e nada mudou no mundo observado; repeti-la não traz nada novo. Escolha o próximo passo.'
        if error:
            cp['no_progress']+=1;cp['events'].append({'tool':tool,'status':'rejected_before_effect','output':error})
            persist(cp);continue
        if cancelled():return end('cancelled','Interrupção antes de agir.',state)
        fresh=await observe()
        if not connection and (not identity_matches(cp,fresh) or fresh.get('sessionId')!=cp.get('session_id') or fresh.get('gameMode')!='survival'):
            cp['no_progress']+=1;cp['events'].append({'tool':tool,'status':'rejected_before_effect','output':'Sessão/destino mudou durante a decisão.'})
            persist(cp);continue
        if cancelled():return end('cancelled','Interrupção antes de agir.',fresh)
        cp['pending']={'tool':tool,'arguments':args,'mutates':tool not in READ_ONLY};persist(cp)
        result=await execute(tool,args)
        used.append(tool);cp['steps']+=1
        record(cp,tool,args,result,decision.get('comment',''))
        if tool=='minecraft_chat':
            cp['events'][-1]['chat_context']=reply_context
            if result.get('ok'):
                from core.minecraft_cognition import remember_chat
                remember_chat(cp,'você',args.get('texto',''))
        if result.get('outcome_uncertain') or result.get('status')=='uncertain':
            persist(cp);return end('uncertain','Ação com efeito incerto; não repetida.',state)
        cp['pending']=None
        conversation=(tool=='minecraft_chat' and result.get('ok') and any(
            x not in cp.get('minecraft_chat_answered',[]) for x in reply_context))
        if conversation:
            cp['minecraft_chat_answered']=(cp.get('minecraft_chat_answered',[])+reply_context)[-32:]
            cp['minecraft_reply_steps']=cp.get('minecraft_reply_steps',0)+1
        # Recusa do controlador (risco/estado) é passageira e reavaliada a cada pedido: memorizá-la
        # barrava a coleta para sempre depois que os monstros sumiram (28/10, Pacífico).
        if not result.get('ok') and not str(result.get('output','')).startswith('ERRO_CONTROLADOR'):
            cp['failures'][signature]={'ground':conditions,'precondition':result.get('precondition_failed') is True}
        else:cp['failures'].pop(signature,None)
        persist(cp)  # O recibo terminal é durável antes de outra observação.
        after=await observe()
        from core.minecraft_cognition import record_transition
        record_transition(criteria,cp,fresh,after,tool,args,result)
        # Só conta como repetição inútil se a ação não mudou nada observável.
        unchanged=_observed(fresh,cp)==_observed(after,cp)
        cp['last_success']={'signature':signature,'observed':_observed(after,cp)} if result.get('ok') and unchanged else None
        information=_digest([tool,result.get('output')])
        novel=(result.get('ok') and tool in {'minecraft_receitas','minecraft_procurar_bloco'} and information not in cp['observations'])
        if novel:cp['observations']=(cp['observations']+[information])[-64:]
        if not conversation:cp['no_progress']=0 if _world(after,cp)!=ground or novel else cp['no_progress']+1
        if not conversation and cp['no_progress']==0:cp.pop('barrier',None)  # avançou: barreira superada
        persist(cp)
        if finished(criteria,cp,after):return end('completed','Critérios conferidos no mundo.',after)
    return end('paused','Orçamento do ciclo atingido; tarefa e recibos preservados.')

# 12/11 (pedido humano: "o servidor está aberto, pode entrar e jogar por conta própria; o que fazer lá você decide" e
# "deixar ela lá sozinha prosseguindo"): o pedido aberto não tinha critério conferível e virava uma tarefa genérica
# encerrada depois de uma consulta. No modo livre ELA escolhe, um de cada vez, um objetivo que o ciclo observado sabe
# conferir no mundo; concluído, escolhe o próximo. O endereço vem da pessoa; a escolha e o motivo são dela.
_LIVRE = re.compile(r'\b(?:por conta propria|voce decide|fazer la voce decide|(?:jogue|jogar|joga|brinque|brincar)'
                    r'(?: la)? sozinha|modo livre|do seu jeito|como (?:voce )?quiser|livremente|a vontade)\b')
_HOST_PORTA = re.compile(r'\b(\d{1,3}(?:\.\d{1,3}){3})\s*:\s*(\d{2,5})\b')
# id → (frase na gramática de targets(), faixa de quantidade ou None, rótulo mostrado a ela)
FREE_GOALS = {
    'bancada': ('Fabrique uma bancada.', None, 'fabricar uma bancada'),
    'picareta_madeira': ('Fabrique uma picareta de madeira.', None, 'fabricar uma picareta de madeira'),
    'picareta_pedra': ('Fabrique uma picareta de pedra.', None, 'fabricar uma picareta de pedra'),
    'picareta_ferro': ('Fabrique uma picareta de ferro.', None, 'fabricar uma picareta de ferro'),
    'picareta_diamante': ('Fabrique uma picareta de diamante.', None, 'fabricar uma picareta de diamante'),
    'forno': ('Fabrique e coloque um forno.', None, 'fabricar e colocar um forno'),
    'lingotes_ferro': ('Consiga {n} lingotes de ferro.', (1, 64), 'conseguir N lingotes de ferro (1–64)'),
    'diamantes': ('Consiga {n} diamantes.', (1, 16), 'conseguir N diamantes (1–16)'),
    'arco': ('Consiga um arco.', None, 'conseguir um arco'),
    'flechas': ('Consiga {n} flechas.', (1, 64), 'conseguir N flechas (1–64)'),
    'carnes': ('Consiga {n} carnes assadas de animais, iguais ou diferentes.', (1, 64),
               'conseguir N carnes assadas, de qualquer animal (1–64)'),
    'kit_ferro': ('Fabrique o kit completo de ferro.', None,
                  'fabricar e vestir o kit completo de ferro (armadura, espada, picareta, machado e pá)'),
    'armadura_diamante': ('Fabrique a armadura completa de diamante.', None,
                          'fabricar e vestir a armadura completa de diamante'),
    'mob': ('Mate um mob qualquer em sobrevivência, sem atacar jogadores.', None, 'derrotar um mob (nunca jogadores)'),
}
FREE_GOALS_PER_TURN = 6


def free_play(text):
    """Pedido de jogar livre no Minecraft → {'host','port','version'} ou {'lan': True}; senão None."""
    t = intent.normalizar(text)
    if 'minecraft' not in t or not _LIVRE.search(t) or targets(text):
        return None
    version = re.search(r'\bversao\s*:?\s*(\d+(?:\.\d+){2})\b', t)
    address = _HOST_PORTA.search(t)
    host_m = re.search(r'\bhost\s*:?\s*(\d+(?:\.\d+){3})\b', t)
    port_m = re.search(r'\bporta\s*:?\s*(\d{2,5})\b', t)
    host = address[1] if address else (host_m[1] if host_m else None)
    port = address[2] if address else (port_m[1] if port_m else None)
    if not host:
        return {'lan': True, 'version': version[1] if version else '1.16.5'}
    port = int(port) if port else 25565
    if not 1 <= port <= 65535:
        return None
    return {'host': host, 'port': port, 'version': version[1] if version else '1.16.5'}


def free_goal_text(free, goal, quantity, username):
    """Objetivo na gramática de targets(): o endereço da pessoa e o objetivo escolhido por ela."""
    if goal not in FREE_GOALS or not re.fullmatch(r'[A-Za-z0-9_]{3,16}', str(username or '')):
        raise ValueError('MINECRAFT_FREE_GOAL_INVALID')
    sentence, bounds, _ = FREE_GOALS[goal]
    if bounds:
        lo, hi = bounds
        try:
            n = int(quantity)
        except (TypeError, ValueError):
            n = min(hi, max(lo, 8))
        sentence = sentence.format(n=max(lo, min(hi, n)))
    if free.get('lan'):
        prefix = f'Minecraft: conecte {username} ao mundo LAN já aberto. '
    else:
        prefix = (f"Minecraft: conecte {username} ao servidor já aberto em host {free['host']}, porta {free['port']}, "
                  f"versão {free.get('version') or '1.16.5'} e auth offline. ")
    return prefix + sentence


def free_goal_done(free, goal, quantity, username, state) -> bool:
    """O inventário/equipamento observado já cumpre o objetivo? (12/11: escolheu "arco" com um arco na mochila; o
    ciclo achou o objetivo pronto antes de agir e a conclusão, que exige recibo de ação, derrubou o modo livre.)
    Usa a mesma conta de `remaining`, com checkpoint novo: fabricar, colocar e derrotar nunca contam como já feitos."""
    if not isinstance(state, dict) or state.get('connected') is not True:
        return False
    text = free_goal_text(free, goal, quantity, username)
    criteria = targets(text)
    return not any(remaining(criteria, initial(text, criteria), state).values())


def free_goal_owned(free, goal, username, state) -> bool:
    """Objetivo de fabricar (sem colocar) cujo item ela já tem na mochila ou vestido: outro não acrescenta nada.
    12/11: escolheu "picareta de pedra" de novo com uma na mochila e passou 10 min sem concluir nada."""
    if not isinstance(state, dict) or state.get('connected') is not True:
        return False
    criteria = targets(free_goal_text(free, goal, 1, username))
    if not criteria.get('crafted') or criteria.get('placed'):
        return False
    have = inventory(state.get('inventory'))
    for item in (state.get('equipment') or {}).values():
        if isinstance(item, dict) and item.get('name'):
            have[item['name']] = have.get(item['name'], 0) + 1
    return all(have.get(k, 0) >= n for k, n in criteria['crafted'].items())


def free_goal_have(free, goal, username, state):
    """Quanto ela já tem de um objetivo com quantidade (N flechas, N lingotes…); None para os outros."""
    if FREE_GOALS[goal][1] is None or not isinstance(state, dict) or state.get('connected') is not True:
        return None
    criteria = targets(free_goal_text(free, goal, 1, username))
    counts = inventory(state.get('inventory'))
    total = sum(counts.get(k, 0) for k in criteria['inventory'])
    total += sum(counts.get(i, 0) for g in (criteria.get('groups') or {}) for i in GROUPS[g])
    return total


def free_menu(state=None, free=None, username=None):
    """Objetivos que ela pode escolher agora: os já cumpridos saem; nos de quantidade, quanto ela já tem."""
    menu = {}
    for goal, (_, bounds, label) in FREE_GOALS.items():
        if state is not None and free is not None:
            if bounds is None and (free_goal_done(free, goal, None, username, state)
                                   or free_goal_owned(free, goal, username, state)):
                continue
            have = free_goal_have(free, goal, username, state)
            if have is not None:
                if have >= bounds[1]:
                    continue
                label = f'{label}; você já tem {have}, então N precisa ser maior que {have}' if have else label
        menu[goal] = label
    return menu


def free_state_summary(state):
    """O que ela vê para escolher: conexão, vida, fome, posição, inventário e quem mais está no servidor."""
    if not isinstance(state, dict) or state.get('connected') is not True:
        return {'conectada': False, 'nota': 'Ainda fora do servidor; o inventário aparece depois de entrar.'}
    return {'conectada': True, 'vida': state.get('health'), 'fome': state.get('food'),
            'posicao': state.get('position'), 'inventario': inventory(state.get('inventory')),
            **({'jogadores_online': state['onlinePlayers']} if isinstance(state.get('onlinePlayers'), list) else {})}


_FREE_SQL = ('INSERT INTO conversation_task_game_states(task_id,payload,updated_at) VALUES(?,?,?) '
             'ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at')


def load_free(parent_id):
    _schema()
    row = bd.um('SELECT payload FROM conversation_task_game_states WHERE task_id=?', ('livre:' + str(parent_id),),
                strict=True)
    data = json.loads(row['payload']) if row else None
    return data if isinstance(data, dict) and data.get('version') == 1 else None


def save_free(parent_id, data):
    _schema()
    bd.executar(_FREE_SQL, ('livre:' + str(parent_id), json.dumps(data, ensure_ascii=False), bd.agora()), strict=True)


def finish_task(task,criteria,cp,state):
    if cp.get('pending') or not finished(criteria,cp,state):raise ValueError('MINECRAFT_GOAL_NOT_VERIFIED')
    events=[e for e in cp['events'] if e.get('receipt_id')]
    if not events:raise ValueError('MINECRAFT_RECEIPTS_REQUIRED')
    operations=[{'id':e['receipt_id'],'ferramenta':e['tool'],'instrucao':e.get('comment') or e['tool'],
                 'planejada':True,'evidencia':{'status':e['status'],'output':e.get('output',''),'verified':e.get('verified',False)}} for e in events]
    report=json.dumps({'verified_goals':criteria,'receipts':[e['receipt_id'] for e in events]},ensure_ascii=False)
    with bd.conexao(escrita=True) as db:
        row=db.execute('SELECT objetivo,status FROM conversation_tasks WHERE id=?',(task.id,)).fetchone()
        if not row or row['status']!='active' or _digest(row['objetivo'])!=cp['goal_hash']:raise ValueError('MINECRAFT_TASK_CHANGED')
        if targets(row['objetivo'])!=criteria:raise ValueError('MINECRAFT_CRITERIA_INCOMPLETE')
        pending=db.execute("SELECT id FROM conversation_task_steps WHERE task_id=? AND status='pending' ORDER BY ordem",(task.id,)).fetchall()
        if not pending:raise ValueError('MINECRAFT_PENDING_STEP_REQUIRED')
        # Os critérios cobrem o objetivo inteiro: todas as etapas pendentes fecham
        # juntas; os recibos ficam na primeira e as demais apontam para o relatório.
        db.execute("UPDATE conversation_task_steps SET status='done',resultado=?,ferramentas=?,ferramentas_executadas=? WHERE id=?",
                   (report,json.dumps(operations,ensure_ascii=False),json.dumps([e['receipt_id'] for e in events]),pending[0]['id']))
        for row in pending[1:]:
            db.execute("UPDATE conversation_task_steps SET status='done',resultado=? WHERE id=?",(report,row['id']))
        db.execute("UPDATE conversation_tasks SET status='completed',updated_at=?,ultima_acao='minecraft_goal_verified',ultimo_resultado=? WHERE id=?",
                   (bd.agora(),report,task.id))
