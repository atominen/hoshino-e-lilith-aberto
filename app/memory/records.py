"""Formatação pura dos registros existentes, sem banco/config/vetor/modelo.

Extraída de knowledge_store para consultas read-only da central. O módulo
original reexporta os mesmos contratos; não há migração ou memória paralela.
"""
import json
import math
import unicodedata

TIPOS_VALIDOS = {'observacao','interpretacao','hipotese','reflexao','inferencia','fato',
                 'regra','relacao','confianca','preferencia','propriedade','procedimento','capacidade','evento'}
CARD_KINDS=('person','item','concept','state','structure','mode','rule','manual','relation','procedure')
CARD_TIERS=('ferro','ouro','diamante','platina')


def card_targets(row, people, names):
    """One mapping shared by the cards UI and retrieval; names are not identity proof."""
    try:subjects=json.loads(row.get('entities') or '[]');meta=json.loads(row.get('links') or '[]')
    except (ValueError,TypeError):subjects=[];meta=[]
    if not isinstance(subjects,list):subjects=[]
    title=meta.get('title') if isinstance(meta,dict) and meta.get('kind') in {'conceptual_model','knowledge_card'} else None
    explicit=row.get('person_id');targets=[]
    if explicit in people:targets=[('person:'+explicit,people[explicit]['nome'],'person','person_id')]
    elif title:targets=[('concept:'+str(row['id']),title,row.get('type') if row.get('type') in CARD_KINDS else 'concept','semantic_record')]
    else:
        for subject in subjects:
            if not isinstance(subject,str) or not subject.strip():continue
            matching=names.get(subject.casefold(),[])
            targets.append(('person:'+matching[0],subject,'person','name_only') if len(matching)==1 else
                           ('topic:'+subject.casefold(),subject,'concept','subject_label'))
    return targets or [('concept:'+str(row['id']),str(row.get('chave') or 'Conhecimento registrado'),'concept','unspecified')]


def card_priorities(conn):
    """Read existing settings once; bounded bonus, never evidence/confidence."""
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tiers=dict(conn.execute('SELECT id,tier FROM memory_card_settings')) if 'memory_card_settings' in tables else {}
    people={};names={}
    if tiers and 'people' in tables:
        for identifier,name in conn.execute('SELECT id,nome FROM people'):
            people[identifier]={'nome':name};names.setdefault(str(name or '').casefold(),[]).append(identifier)
    def priority(table,row):
        if table=='memories':ids=[target[0] for target in card_targets(row,people,names)]
        elif table=='properties':ids=['topic:'+str(row.get('entity') or 'Assunto não identificado').casefold()]
        else:ids=[f"procedure:{row.get('id')}"]
        tier=max((tiers.get(i,'ferro') for i in ids),key=lambda t:CARD_TIERS.index(t) if t in CARD_TIERS else 0)
        return (tier, .02*CARD_TIERS.index(tier)) if tier in CARD_TIERS else ('ferro',0.)
    return priority


def normalizar(texto):
    texto=unicodedata.normalize('NFD',(texto or '').lower())
    return ''.join(c for c in texto if unicodedata.category(c)!='Mn')


def confianca_valida(valor,default=0.7):
    if valor is None:return default
    numero=float(valor)
    if not math.isfinite(numero):raise ValueError('Confiança deve ser finita.')
    return max(0.0,min(1.0,numero))


def categoria(tipo,fonte=None):
    tipo=normalizar(str(tipo or 'inferencia'))
    if tipo=='fato' and normalizar(str(fonte or '')) in {'reflexao','reflexao_noturna'}:return 'reflexao'
    return tipo if tipo in TIPOS_VALIDOS else 'inferencia'


def render_model(graph):
    """Lossless semantic projection: layout/JSON punctuation are not knowledge."""
    lines=[]
    for node in graph.get('nodes',[]):
        lines.append(f"{node['id']} [{node['kind']}]: {node['label']}")
        if 'confidence' in node:lines.append('  Confiança do nó: '+str(node['confidence']))
        for name,label in (('conditions','Condição'),('exceptions','Exceção')):
            lines.extend(f'  {label}: {text}' for text in node.get(name,[]))
    for edge in graph.get('edges',[]):
        lines.append(f"Relação {edge['from']} → {edge['to']}: {edge['relation']} (base={edge['basis']})")
        for name,label in (('conditions','Condição da relação'),('exceptions','Exceção da relação')):
            lines.extend(f'  {label}: {text}' for text in edge.get(name,[]))
    for table in graph.get('tables',[]):
        lines.extend([table['title'],' | '.join(table['columns'])])
        lines.extend(' | '.join(row) for row in table['rows'])
    return '\n'.join(lines)


def registro(linha,default=0.5):
    r=dict(linha);r['tipo_armazenado']=r.get('type',r.get('tipo','inferencia'))
    r['tipo']=categoria(r['tipo_armazenado'],r.get('source'));r['fonte']=r.get('source') or 'não registrada'
    source_evidence=[]
    try:
        envelope=json.loads(r['fonte'])
        if isinstance(envelope,dict) and envelope.get('kind')=='memory_provenance':
            r['fonte']=envelope['source'];source_evidence=envelope.get('evidence',[])
    except (ValueError,TypeError,KeyError):pass
    r['confianca_armazenada']=r.get('confidence');r['confianca']=confianca_valida(r.get('confidence'),default)
    links=r.get('links')
    try:evidencias=json.loads(links) if isinstance(links,str) else links
    except (TypeError,ValueError):evidencias=links
    r['evidencias']=evidencias if evidencias is not None else source_evidence
    if isinstance(evidencias,dict) and evidencias.get('kind')=='conceptual_model':
        # Full editable model remains in the original row, not every chat prefix.
        r['evidencias']={'kind':'conceptual_model','owner':evidencias.get('owner'),
                         'sources':evidencias.get('sources',[]),'previous':evidencias.get('previous'),
                         'mode':evidencias.get('mode','fundamentado'),
                         'full_model_ref':{'table':'memories','id':r.get('id')}}
        label='[RASCUNHO NÃO VALIDADO] ' if evidencias.get('mode')=='rascunho' else ''
        r['semantic_text']=label+evidencias.get('title','')+'\n'+render_model(evidencias.get('graph',{}))
    return r
