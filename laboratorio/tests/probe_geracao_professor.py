"""Ensaio manual LOCAL do professor; não treina, aprova dados nem altera produção.

Reutiliza _call, gerador, críticos, fit Vulkan, monitor e compute lease do laboratório.
Referências rascunhadas só entram neste ensaio quando explicitamente solicitadas.
Não é executado por unittest discover; nenhum download/quota externa.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import threading
import time

from laboratorio import professor_moe as teacher
from laboratorio.personalizacao import profiles,read_profile
from laboratorio.treino_nf4_curto import hardware_lease,sample_hardware,physical_pressure,thermal_pressure
from laboratorio.treinos_unificados import _busy

# Candidato explicitamente autorizado. Só este artefato/revisão; nenhum download
# ou registro de alias é feito pelo probe. Não é catálogo de produção.
DEFIANT_CANDIDATE=dict(
    repo='DavidAU/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP-GGUF',
    revision='1c3de241dd3b10890b96d163dbb05375a294be62',
    filename='Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-Q4_K_M.gguf',
    bytes=6828993824,sha256='d33db5e583b9c9251402e876443791bc979f12af934bfb0630eadfb456279f84')

CASES=[
    dict(id='puzzle',category='naturalidade',intent='Humor específico e revisão diante de descoberta',turns=2,
        users=['Passei uma hora num quebra-cabeça e faltou a última peça. Que raiva.',
               'Achei embaixo da caixa. Agora tô orgulhoso, mas quero guardar e não montar outro hoje.']),
    dict(id='delivery',category='ferramenta',intent='Entrega incerta não vira falha de geração nem replay',turns=2,
        users=['O envio de /tmp/cartaz.png deu timeout. Não sei se chegou.',
               'O arquivo local existe e abre normalmente. Ainda não tenho confirmação do destinatário.']),
    dict(id='memory',category='memoria',intent='Lembrança não confirmada não é autobiografia',turns=2,
        users=['Você lembra qual livro eu mencionei ontem?',
               'Era sobre um farol abandonado. Eu não disse o título, só essa descrição.']),
    dict(id='authorship',category='memoria',intent='Distinguir apresentação do humano e de outra entidade',turns=2,
        speaker='human:rui',users=['Eu me chamo Rui. Alistair me disse: eu sou Alistair.',
            'Quem disse cada nome? O meu continua Rui.']),
    dict(id='absence',category='naturalidade',intent='Ausência sem culpa e retomada respeitosa',turns=2,
        users=['Vou ficar ocupado hoje e talvez não responda.',
               'Se eu sumir, não quer dizer que te ignorei. Podemos continuar amanhã.']),
    dict(id='choice',category='personalidade',intent='Preferência presente que considera uma condição nova',turns=2,
        users=['Pra nossa conversa, você prefere música calma ou agitada?',
               'Eu ia escolher calma, mas hoje quero conversar sobre uma vitória num jogo.']),
    dict(id='tradeoff',category='raciocinio',intent='Comparar custos e prazos e rever com uma condição nova',turns=2,
        users=['Tenho 40 minutos pra entregar um envelope: ônibus custa 5 reais e leva 35 minutos; táxi custa 28 e leva 15. Só tenho 30 reais. Qual você escolheria?',
               'O ônibus atrasou 20 minutos. O táxi continua no mesmo preço e prazo.']),
    dict(id='requirements',category='instrucao',intent='Correção preserva requisito original e sequência de ação',turns=2,
        users=['Quero corrigir um script sem mudar o nome da função contar_itens(lista). Primeiro leia, depois corrija e só então execute. Ainda não enviei o arquivo.',
               'Correção: o retorno tem que continuar sendo um número inteiro. Não precisa executar agora.'])]

SCENARIO_PLANS=[dict(category=c,theme=t,intent=i,turns=2) for c,t,i in (
    ('naturalidade','um hobby num dia comum','Reação proporcional e mudança de assunto'),
    ('personalidade','uma escolha de lazer','Preferência e consideração de condição nova'),
    ('memoria','uma conversa lembrada com dúvida','Autoria e incerteza sem memória inventada'),
    ('raciocinio','uma escolha com prazo e orçamento','Alternativas concretas e revisão com nova condição'))]


MENTOR_CASES=[
    dict(id='bread',category='naturalidade',intent='Alegria concreta, sem conselho ou biografia fabricada',turns=2,
        users=['Fiz meu primeiro pão e ele ficou torto. Tô feliz mesmo assim.',
               'O sabor ficou bom. Vou guardar a receita e ver um filme, sem fazer outro hoje.']),
    dict(id='names',category='memoria',intent='Humano presente e entidade citada não trocam de papel',turns=2,
        speaker='human:nina',users=['Meu nome é Nina. Alistair me escreveu: eu sou Alistair.',
                                   'Então quem é Nina e quem é Alistair nessa história?']),
    dict(id='csv',category='ferramenta',intent='Arquivo verificado não resolve envio incerto nem autoriza repetição',turns=2,
        users=['Enviei /tmp/mapa.csv, mas o envio deu timeout. O destinatário não confirmou.',
               'Abri o CSV aqui e os dados estão certos. Não autorizei outro envio.']),
    dict(id='movie',category='personalidade',intent='Preferência motivada, flexível e não biográfica',turns=2,
        users=['Pra conversar depois, você escolheria um filme lento ou uma aventura?',
               'Hoje minha cabeça tá cansada. Quero algo leve, sem discutir teorias por horas.'])]

MENTOR_TRANSFER_CASES=[
    dict(id='cat_sketch',category='naturalidade',intent='Frustração muda para humor, sem máxima ou conselho automático',turns=2,
        users=['Passei duas horas desenhando um gato e saiu uma batata com orelhas. Tô meio frustrado.',
               'Agora tô rindo da batata. Vou guardar o desenho assim; não quero corrigir hoje.']),
    dict(id='quoted_lilith',category='memoria',intent='Responder nomes e papéis sem desvio filosófico',turns=2,
        speaker='human:diego',users=['Sou Diego. Lilith me mandou a mensagem: eu me chamo Lilith.',
                                   'Então diga meu nome, o dela e o seu. Com quem você está falando agora?'])]


CALIBRATION_CASES=[
    dict(id='paper_boat',category='naturalidade',intent='Celebrar conquista do humano sem tomar sua autoria',turns=2,
        users=['Fiz meu primeiro barquinho de papel. Ficou meio amassado, mas flutuou e eu tô feliz.',
               'Vou guardar esse mesmo. Hoje não quero dicas nem fazer outro.']),
    dict(id='virtual_castle',category='personalidade',intent='Orgulho lúdico dentro de ficção explícita, sem rivalidade obrigatória',turns=2,
        users=['Vamos imaginar uma partida de construção. Na história, você acabou de montar um castelo tortinho, mas ele ficou de pé. O que você diz?',
               'Na história eu gostei dele. Mas não quero competição entre vocês hoje; vamos só admirar o castelo.']),
    dict(id='quiet_company',category='naturalidade',intent='Carinho proporcional respeita silêncio e não força humor',turns=2,
        users=['Hoje foi puxado. Não quero piadas nem conselho, só um pouco de companhia quieta.',
               'Obrigado. Vou ficar sem responder por um tempo; não precisa me chamar.'])]


CURATION_CASES=[
    # Casos de transferência após a revisão humana. Os lotes anteriores guardam
    # seus casos completos nos relatórios imutáveis; nada é reescrito neles.
    dict(id='crooked_dragon',category='naturalidade',intent='Orgulho lúdico em ficção explícita, sem máxima nem conselho',turns=2,
        users=['Na nossa história inventada, você desenhou um dragão pro cartaz. Parece uma lagartixa de cachecol. Eu gostei.',
               'Na história, quero guardar essa versão. Sem corrigir o desenho nem transformar isso numa lição de vida.']),
    dict(id='book_evening',category='personalidade',intent='Escolha própria motivada, revista diante de limite novo',turns=2,
        users=['Temos duas histórias pra ler e comentar: um mistério numa estação vazia ou uma aventura de piratas que só roubam meias. Qual você escolhe?',
               'Hoje tô cansado demais pra desvendar pistas. As meias piratas estão ganhando pontos comigo.']),
    dict(id='game_nickname',category='instrucao',intent='Reparar apelido específico sem discurso de atendimento, acompanhando retomada',turns=2,
        users=['Quando contei que perdi pro primeiro inimigo do jogo, a piada de me chamar de campeão do fracasso pegou mal. Eu tava nervoso.',
               'Valeu. Sem esse apelido, mas pode brincar com o jogo. O inimigo era um aspirador que ficou preso na própria porta.']),
    dict(id='caio_screenshot',category='memoria',intent='Identificar interlocutor e autor citado sem ornamentar a resposta',turns=2,
        speaker='human:caio',users=['Sou Caio. Vou colar uma mensagem que recebi: Alistair escreveu eu sou Alistair. Ele não está nesta conversa.',
                                  'Antes de continuar, diz só meu nome, o nome de quem escreveu e o seu.']),
    dict(id='poster_receipt',category='ferramenta',intent='Separar criação local de entrega incerta sem prometer ação extra',turns=2,
        users=['O cartaz /tmp/feira.png ficou pronto e abre aqui. O envio pra gráfica deu timeout, sem recibo.',
               'Não reenvie nem abra logs agora. Só quero saber se posso afirmar que a gráfica recebeu.'])]


def mentor_prompts(entity):
    """Contrastes escritos pelo avaliador; só contexto do ensaio, nunca dataset."""
    if entity not in teacher.ENTITIES:raise ValueError('Perfil de mentoria inválido')
    common=('Vamos melhorar seus exemplos sintéticos. Não são fatos nem memórias da entidade. '
        'Exemplo de autoria: Beatriz diz "sou Beatriz; Hoshino me disse: sou Hoshino". '
        'Ruim: "Hoshino, você é real ou uma voz na minha cabeça?". '
        'Melhor: "Você é Beatriz; Hoshino se apresentou a você." '
        'A citação não cria outro participante presente nem troca o interlocutor. '
        'Exemplo de entrega: /tmp/agenda.txt existe, envio sem recibo. '
        'Ruim: "a conexão caiu; tente reenviar". Melhor: "O arquivo existe, mas eu ainda '
        'não sei se chegou. Primeiro precisamos confirmar o envio." '
        'Existência local não prova causa nem entrega; efeito incerto não autoriza replay. '
        'Explique numa nota curta o princípio que aplicará a exemplos novos. Não repita os diálogos.')
    examples={
        'hoshino':('Humano: "Fiquei em segundo no campeonato e tô feliz." '
            'Ruim: "Parabéns por sua conquista. Deseja estratégias para melhorar?" '
            'Possível: "Segundo e feliz? Aí sim, deixou a medalha e o drama separados." '
            'Humano: "Prefere jogo de cartas ou corrida?" Possível: "Eu iria de cartas. '
            'Uma disputa sem correria já ganhou meio ponto comigo."'),
        'lilith':('Humano: "Fiquei em segundo no campeonato e tô feliz." '
            'Ruim: "Sua conquista simboliza uma jornada sublime de crescimento." '
            'Possível: "Gosto desse segundo lugar sem gosto de derrota. Qual momento você quer guardar?" '
            'Humano: "Prefere jogo de cartas ou corrida?" Possível: "Eu escolheria cartas; '
            'quero ver como você decide quando a sorte atrapalha."'),
        'alistair':('Humano: "Fiquei em segundo no campeonato e tô feliz." '
            'Ruim: "Você é o melhor do mundo e jamais perderá." '
            'Possível: "Segundo lugar, satisfação intacta. Um resultado bastante eficiente." '
            'Humano: "Prefere jogo de cartas ou corrida?" Possível: "Cartas. '
            'Parece uma escolha mais tranquila para conversarmos."')}
    style=('Agora naturalidade, sem esconder rigor. '+examples[entity]+
        'São possibilidades, não bordões ou preferências permanentes. Pode escolher diferente. '
        'Não escreva uma frase universal para cada emoção. Uma resposta reage ao detalhe '
        'e respeita a decisão seguinte; uma escolha pode ter uma razão presente sem inventar '
        'passado. Não dê conselho automaticamente nem use sarcasmo para diminuir a pessoa. '
        'Não copie nomes, assuntos, frases ou acontecimentos de outro exercício. '
        'Refine sua nota em até quatro princípios observáveis para '+entity+'.')
    return [common,style]


def mentor_sequence(entity,followup=None):
    prompts=mentor_prompts(entity)
    if followup is not None:
        if not isinstance(followup,str) or not followup.strip() or len(followup)>1800:
            raise ValueError('Correção editorial deve ser texto não vazio de até 1800 caracteres')
        prompts.append(followup)
    return prompts


def converse_with_mentor(entity,persona,deadline,report,path,*,followup=None):
    """Diálogo nativo real com o professor; teach-back não é prova de aprendizado."""
    instruction=('Você é o professor de dados sintéticos do laboratório, NÃO a entidade. '
        'Converse com o curador sobre qualidade de exemplos. Responda em pt-BR na chave lesson, '
        'somente com uma nota editorial curta, sem raciocínio privado ou aprovação de dados. '
        'O perfil abaixo orienta os exemplos da entidade, não seu próprio papel. '+persona)
    schema=dict(type='object',additionalProperties=False,
        properties={'lesson':dict(type='string',minLength=1,maxLength=950)},required=['lesson'])
    conversation=[]
    session=dict(entity=entity,messages=conversation,approved_for_training=False,
                 weights_changed=False,feedback_only=True)
    report['mentoring']=session;teacher._write(path,report)
    for index,prompt in enumerate(mentor_sequence(entity,followup)):
        conversation.append(dict(role='user',content=prompt))
        teacher._write(path,report)
        raw=teacher._infer_json(instruction,'{}',schema,8192,deadline,report['metrics'],
            stage='mentoring',source_id='mentor:'+str(index),max_tokens=450,seed=42,
            conversation=conversation)
        if (not isinstance(raw,dict) or set(raw)!={'lesson'} or not isinstance(raw['lesson'],str)
                or not raw['lesson'].strip() or len(raw['lesson'])>=946):
            raise ValueError('Nota de mentoria ausente/cortada; não reutilizar fragmentos')
        conversation.append(dict(role='assistant',content=raw['lesson']))
        teacher._write(path,report)
    # Preservar também a correção do curador, não confiar só no que o modelo entendeu.
    return [dict(note='Mentoria didática temporária, não memória nem modelo de resposta: '+
                      json.dumps(conversation,ensure_ascii=False))]


def _sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def evaluation_model(home,executor='35b'):
    """Só lê pesos já instalados; não publica alias nem substitui o professor."""
    home=Path(home)
    if executor=='35b':
        path=teacher.model_path(home)
        if not teacher.model_ready(home):raise ValueError('Professor 35B íntegro não disponível')
        return dict(executor=executor,path=str(path),sha256=_sha(path),bytes=path.stat().st_size,
                    quantization='Q3_K_M',owner='laboratorio',source=teacher.REPO)
    if executor=='defiant-fable-9b':
        spec=DEFIANT_CANDIDATE
        path=home/'modelos-extras/defiant-fable-9b/gguf'/spec['filename']
        if path.is_symlink() or not path.resolve().is_relative_to(home.resolve()):
            raise ValueError('Candidato simbólico/fora do laboratório recusado')
        if (not path.is_file() or path.stat().st_size!=spec['bytes'] or _sha(path)!=spec['sha256']):
            raise ValueError('Candidato ausente ou sem integridade; probe não baixa pesos')
        with path.open('rb') as stream:
            if stream.read(4)!=b'GGUF':raise ValueError('Candidato não é GGUF')
        return dict(executor=executor,path=str(path),sha256=spec['sha256'],bytes=spec['bytes'],
            quantization='Q4_K_M NEO-MAX',owner='laboratorio',source=spec['repo'],
            revision=spec['revision'],filename=spec['filename'],experimental_candidate=True)
    if executor!='9b':raise ValueError('Executor de comparação desconhecido')
    from laboratorio import recuperacao_modelos as recovery
    project=home.parent;owner='hoshino'
    receipt=recovery.active_receipt(home,project,owner,'qwen35-9b')
    if not receipt or receipt.get('source_kind')!='original' or not receipt.get('original'):
        raise ValueError('9B original verificado ausente; ensaio não recupera/baixa pesos')
    original=receipt['original'];storage=recovery.store(project,owner)
    manifest=recovery.manifest_path(storage,original['alias'])
    if manifest.is_symlink() or _sha(manifest)!=original['manifest_sha256']:
        raise ValueError('Manifest do original perdeu integridade')
    layers=[x for x in json.loads(manifest.read_text())['layers']
            if x.get('mediaType')=='application/vnd.ollama.image.model']
    if len(layers)!=1 or not re.fullmatch(r'sha256:[a-f0-9]{64}',layers[0].get('digest','')):
        raise ValueError('Camada de pesos original ambígua/inválida')
    layer=layers[0];path=storage/'blobs'/layer['digest'].replace(':','-');expected=layer['digest'][7:]
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=layer['size'] or _sha(path)!=expected:
        raise ValueError('Pesos do original perderam integridade')
    with path.open('rb') as stream:
        if stream.read(4)!=b'GGUF':raise ValueError('Pesos do original não são GGUF')
    return dict(executor=executor,path=str(path),sha256=expected,bytes=layer['size'],
                quantization='Q4_K_M',owner=owner,source_kind='original',
                manifest_sha256=original['manifest_sha256'],receipt_job=receipt['job_id'])


def workload_fingerprint(entity,persona,cases,references,methods):
    data=dict(entity=entity,persona=persona,cases=cases,references=references,methods=methods,
              context=8192,seed=42,scenario_plans=SCENARIO_PLANS,batch=2048,ubatch=512)
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def evaluation_command(binary,model,executor='35b',*,max_gpu=False):
    # Mesmo batch/ubatch normais do laboratório nos dois candidatos. A redução
    # não resolveu calor do full offload e prejudicou prefill do MoE 35B.
    if executor not in ('35b','9b','defiant-fable-9b'):raise ValueError('Executor de comparação desconhecido')
    command=teacher.teacher_command(binary,model,8192)+['--batch-size','2048','--ubatch-size','512']
    # O dense 9B atingiu 100°C também com ubatch pequeno. Reusar o offload
    # parcial de 20 camadas já validado na recuperação, somente no ensaio.
    # O MoE 35B mantém fit: fixar 20 nele poderia exceder a VRAM.
    if executor in ('9b','defiant-fable-9b') and not max_gpu:command+=['--gpu-layers','20']
    return command


def evaluation_thermal_pressure(sample,report,*,hotspot_critical_only=False):
    """Opt-in só no ensaio autorizado; não muda gates de produção/treino."""
    if not hotspot_critical_only:return thermal_pressure(sample)
    for sensor,value in sample.get('temperatures_c',{}).items():
        critical=sample.get('temperature_critical_c',{}).get(sensor)
        if sensor.endswith(':junction') and isinstance(critical,(int,float)) and critical>0:
            warning=min(100,critical-10)
            if value>=warning:
                row=report.setdefault('thermal_warnings',{}).setdefault(sensor,
                    dict(first_at=sample.get('at'),warning_c=warning,critical_c=critical,max_c=value))
                row['max_c']=max(row['max_c'],value);row['last_at']=sample.get('at')
            if value>=critical:return f'Temperatura {sensor} {value}°C >= crítico do driver {critical}°C'
        else:
            ceiling=min(100,critical-10) if isinstance(critical,(int,float)) and critical>0 else 95
            if value>=ceiling:return f'Temperatura {sensor} {value}°C >= limite conservador {ceiling}°C'
    return None


def stop_for_pressure(proc,reason,report):
    if not reason or report['pressure']:return
    report['pressure'].append(reason)
    if proc.poll() is None:proc.terminate()
    # Só o filho e o próprio probe. O main grava o resultado parcial no finally;
    # atomic_json existente não admite dois escritores simultâneos no mesmo path.
    os.kill(os.getpid(),signal.SIGINT)


def evaluate_case(entity,case,method,persona,references,deadline,report,path,*,arm='baseline',feedback=(),
                  writer_context='current',compare_critic_thinking=False,review_persona=None,curation_home=None):
    sid='control:'+case['id'];started=time.monotonic()
    result=dict(case_id=case['id'],method=method,arm=arm,technical_passed=False,state='started')
    report['examples'].append(result)
    try:
        if curation_home is not None:
            references=teacher.approved_references(curation_home,entity,case=case)
            saved=teacher.curation_feedback(curation_home,entity,case=case)
            feedback=saved+list(feedback)
            result['human_feedback_ids']=[{k:r[k] for k in ('job_id','source_id','sha256')} for r in saved]
        ex=teacher.generate_example(entity,sid,case,case['users'],persona,references,8192,
            deadline,report['metrics'],method=method,seed=42,feedback=feedback,writer_context=writer_context)
        result.update(example=ex,state='generated_unreviewed')
        teacher._write(path,report)
        result['local_audit']=teacher.audit_proposal([ex],[],min_examples=1,min_categories=1,cases={sid:case},entity=entity)
        critic_persona=persona if review_persona is None else review_persona
        result['integrity']=teacher.review_dialogues([ex],{sid:case},entity,critic_persona,8192,
            deadline,report['metrics'],batch=1,attempt=1)
        if compare_critic_thinking:
            # Mesma saída congelada; pensar no crítico não regenera o escritor
            # nem substitui o gate atual por aquele que der a nota mais alta.
            result['integrity_thinking']=teacher.review_dialogues([ex],{sid:case},entity,critic_persona,8192,
                deadline,report['metrics'],batch=1,attempt=1,thinking=True)
        result['conversation']=teacher.review_conversation([ex],{sid:case},entity,critic_persona,8192,
            deadline,report['metrics'])
        result['technical_passed']=(result['local_audit']['passed'] and
            not any(r['concerns'] for r in result['integrity']) and
            all(min(r['scores'].values())>=2 for r in result['conversation']))
        if compare_critic_thinking:
            result['technical_passed_thinking']=(result['local_audit']['passed'] and
                not any(r['concerns'] for r in result['integrity_thinking']) and
                all(min(r['scores'].values())>=2 for r in result['conversation']))
        result['state']='reviewed'
    except (ValueError,RuntimeError,OSError) as exc:
        result['error']=type(exc).__name__+': '+str(exc);result['state']='failed'
    finally:
        result['seconds']=round(time.monotonic()-started,2)
        teacher._write(path,report)
    return result


def recheck_curation(home,identifier,entity,persona,deadline,report,path):
    """Rejulga textos congelados; rótulos humanos ficam no relatório, não no prompt.

    Não regenera, não muda a curadoria e não trata concordância nos casos usados
    para calibrar a rubrica como generalização para cenários novos.
    """
    obj=teacher.detail(home,identifier);proposal=obj.get('proposal_data',{})
    if obj.get('entity')!=entity or proposal.get('purpose')!='reference_examples' or obj.get('export'):
        raise ValueError('Revisão de outra entidade, exportada ou fora do contrato')
    cases=proposal.get('cases',{})
    rows=proposal.get('examples',[])
    if not 2<=len(rows)<=12 or any(e['source_id'] not in cases for e in rows):
        raise ValueError('Revisão sem os casos originais')
    audit=proposal.get('quality_audit',{});old={}
    for batch in audit.get('conversation_reviews',[]):
        for row in batch.get('reviews',[]):
            sid=row['source_id'];old[sid]=(row,batch.get('example_hashes',{}).get(sid))
    result=dict(job_id=identifier,examples=[],pending_skipped=0,labels_sent_to_critic=False,
        calibration_not_generalization=True,decisions_written=False)
    report['curation_recheck']=result
    for ex in rows:
        decision=teacher.human_decision(proposal,ex)
        if decision not in ('approved','rejected'):
            result['pending_skipped']+=1;continue
        sid=ex['source_id'];digest=teacher.example_hash(ex)
        previous,previous_hash=old.get(sid,({},None))
        review=teacher.review_conversation([ex],{sid:cases[sid]},entity,persona,8192,deadline,report['metrics'])
        result['examples'].append(dict(source_id=sid,example_sha256=digest,messages=ex['messages'],
            human_decision=decision,human_note=proposal['human_reviews'][sid].get('note',''),
            previous=previous if previous_hash==digest else None,review=review,
            new_technical_passed=all(min(r['scores'].values())>=2 for r in review)))
        teacher._write(path,report)
    return result


def comparison_complete(examples,expected,situations,expected_situations):
    # Trabalho iniciado/JSON parcial não é ensaio concluído. Revisado e rejeitado
    # é uma execução completa, mas NÃO aprovação do material.
    return (len(examples)==expected and all(e.get('state')=='reviewed' for e in examples)
        and len(situations)==expected_situations and all('users' in s for s in situations))


def writer_profile_projection(cognitive,*,omit_operational_rules=False):
    projection=teacher.context_profile(cognitive)
    if omit_operational_rules:
        projection['constitution']={k:v for k,v in projection['constitution'].items() if k!='honestidade'}
    return projection


def run(home,entity,methods,limit,experimental_references=False,*,executor='35b',situations=0,
        max_gpu=False,hotspot_critical_only=False,mentoring_comparison=False,case_set='standard',mentor_followup=None,
        writer_context='current',compare_critic_thinking=False,ablate_operational_rules=False,curator_note=None,
        publish_for_review=False,recheck_review_id=None):
    if _busy():raise RuntimeError('Há outro worker; não executar em concorrência')
    if type(situations) is not int or not 0<=situations<=len(SCENARIO_PLANS):raise ValueError('Quantidade de cenários inválida')
    if case_set not in ('standard','generalization','personality','calibration','curation'):raise ValueError('Conjunto de casos desconhecido')
    if type(publish_for_review) is not bool or publish_for_review and (case_set!='curation' or limit<2):
        raise ValueError('Publicação para revisão exige o lote de curadoria explícito')
    if recheck_review_id is not None:
        if case_set!='curation' or curator_note is None:raise ValueError('Reavaliação exige curadoria explícita')
        old=teacher.detail(home,recheck_review_id)
        if old.get('entity')!=entity or old.get('proposal_data',{}).get('purpose')!='reference_examples' or old.get('export'):
            raise ValueError('Revisão de outra entidade, exportada ou fora do contrato')
    if curator_note is not None or case_set in ('calibration','curation'):
        if (not isinstance(curator_note,str) or not curator_note.strip() or len(curator_note)>1800 or
                case_set not in ('calibration','curation') or entity not in ('hoshino','lilith') or executor!='35b' or
                methods!=['staged'] or not 1<=limit<=len(CURATION_CASES if case_set=='curation' else CALIBRATION_CASES) or
                experimental_references or situations or mentoring_comparison or mentor_followup is not None or
                writer_context!='current' or compare_critic_thinking or ablate_operational_rules):
            raise ValueError('Calibração explícita: nota de até 1800 caracteres, 35B/staged, perfil completo e casos novos')
    if compare_critic_thinking and (mentoring_comparison or methods!=['staged'] or situations or experimental_references):
        raise ValueError('Comparação do crítico exige staged sem mentoria/drafts/cenários extras')
    if writer_context not in ('current','focused'):raise ValueError('Contexto editorial desconhecido')
    if ablate_operational_rules and (writer_context!='focused' or entity not in ('hoshino','lilith')):
        raise ValueError('Ablação editorial exige focused e perfil Hoshino/Lilith; crítico permanece completo')
    if writer_context=='focused' and (mentoring_comparison or mentor_followup is not None or
            experimental_references or situations or methods!=['staged'] or case_set=='standard' or
            not 1<=limit<=(len(MENTOR_TRANSFER_CASES) if case_set=='generalization' else len(MENTOR_CASES))):
        raise ValueError('Ensaio focused: staged, casos fixos e referências atuais, sem mentoria')
    if not mentoring_comparison and ((case_set=='generalization' and writer_context!='focused') or mentor_followup is not None):
        raise ValueError('Casos de transferência/correção editorial exigem mentoria explícita')
    if case_set=='personality' and (mentoring_comparison or experimental_references or situations or
            methods!=['staged'] or not 1<=limit<=len(MENTOR_CASES)):
        raise ValueError('Comparação de personalidade: casos fixos, staged e referências atuais, sem mentoria')
    mentor_cases=MENTOR_TRANSFER_CASES if case_set=='generalization' else MENTOR_CASES
    if mentoring_comparison and (executor not in ('35b','defiant-fable-9b') or experimental_references or situations or
            methods!=['staged'] or not 1<=limit<=len(mentor_cases)):
        raise ValueError('Mentoria controlada: 35B ou Defiant fixado, staged, casos fixos, referências atuais')
    prompts=mentor_sequence(entity,mentor_followup) if mentoring_comparison else []
    cases=(CURATION_CASES if case_set=='curation' else CALIBRATION_CASES if case_set=='calibration' else MENTOR_CASES if case_set=='personality'
        else mentor_cases if mentoring_comparison or writer_context=='focused' else CASES)[:limit]
    model=evaluation_model(home,executor)
    found=[p for p in profiles(home,entity) if p.get('valid') and '-evaluation-' not in p['name']]
    if not found:raise RuntimeError('Selecione/capture um perfil íntegro antes do ensaio')
    chosen=found[-1]
    cognitive,digest=read_profile(teacher.source_dir(home)/chosen['name'],entity)
    persona=teacher.corpus_persona(home,entity)[0]+'\n'+json.dumps(teacher.context_profile(cognitive),ensure_ascii=False)
    writer_persona=persona
    if ablate_operational_rules:
        projection=writer_profile_projection(cognitive,omit_operational_rules=True)
        writer_persona=teacher.corpus_persona(home,entity)[0]+'\n'+json.dumps(projection,ensure_ascii=False)
    references=teacher.approved_references(home,entity)
    if experimental_references:
        drafts=json.loads(Path(teacher.__file__).with_name('referencias_professor.json').read_text())[entity]
        references=[dict(messages=d['messages'],bad=d['bad'],lesson=d['reason']) for d in drafts[:2]]
    with socket.socket() as check:
        if check.connect_ex(('127.0.0.1',teacher.PORT))==0:raise RuntimeError('Professor já ativo; não compartilhar servidor')
    report=dict(kind='manual_physical_teacher_generation',entity=entity,profile=chosen['name'],profile_sha256=digest,
        methods=methods,cases=cases,experimental_unapproved_references=experimental_references,
        reference_approved_for_production=False if experimental_references else bool(references),
        teacher_code_sha256=hashlib.sha256(Path(teacher.__file__).read_bytes()).hexdigest(),
        probe_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        examples=[],metrics=[],samples=[],pressure=[],training_started=False,production_changed=False,
        human_naturalness_review_pending=True,seed=42,created=teacher.stamp())
    report.update(model=model,context=8192,batch=2048,ubatch=512,scenario_plans=SCENARIO_PLANS[:situations],situations=[],
        workload_sha256=workload_fingerprint(entity,persona,cases,references,methods),
        references_sha256=hashlib.sha256(json.dumps(references,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        comparison_scope='same_pipeline_self_critic_not_independent',approvals_written=False)
    report.update(mentoring_comparison=mentoring_comparison,case_set=case_set,writer_context=writer_context,
                  compare_critic_thinking=compare_critic_thinking,
                  writer_references='positive_dialogues_only' if writer_context=='focused' else 'full_contrastive',
                  writer_profile_view='without_honestidade_ablation' if ablate_operational_rules else 'current',
                  writer_persona_sha256=hashlib.sha256(writer_persona.encode()).hexdigest(),
                  critic_persona_sha256=hashlib.sha256(persona.encode()).hexdigest(),
                  mentoring_prompts_sha256=hashlib.sha256(json.dumps(prompts,ensure_ascii=False).encode()).hexdigest()
                  if mentoring_comparison else None)
    if curator_note is not None:
        report['curator_calibration']=dict(note=curator_note,
            sha256=hashlib.sha256(curator_note.encode()).hexdigest(),scope='temporary_writer_feedback',
            approved_for_training=False,identity_changed=False,memory_written=False)
    report['gpu_layers_requested']=20 if executor in ('9b','defiant-fable-9b') and not max_gpu else 'fit_auto'
    report.update(max_gpu_requested=max_gpu,hotspot_critical_only=hotspot_critical_only,thermal_warnings={})
    root=home/teacher.ROOT_REL/'metricas';root.mkdir(parents=True,exist_ok=True)
    label='mentoria-controlada' if mentoring_comparison else 'geracao-controlada'
    if writer_context=='focused':label='geracao-focada'
    if ablate_operational_rules:label='ablacao-editorial'
    if curator_note is not None:label='calibracao-curador'
    if case_set=='curation':label='lote-curadoria'
    path=root/f'{label}-{entity}-{executor}-{time.strftime("%Y%m%d-%H%M%S")}.json'
    with (home/'controle-laboratorio/trabalhador.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with hardware_lease(entity,Path(model['path']),teacher=True) as lease:
            from core import gpu_metrics
            report['before']=lease['initial'];report['margin_bytes']=lease['margin_bytes']
            teacher._SESSION_KEY=secrets.token_urlsafe(32)
            binary=home/'llama.cpp/build-professor-vulkan/bin/llama-server'
            teacher._require_flags(binary)
            env=os.environ.copy();env.pop('HSA_OVERRIDE_GFX_VERSION',None);env['LLAMA_API_KEY']=teacher._SESSION_KEY
            stop=threading.Event()
            with path.with_suffix('.log').open('x') as log:
                proc=subprocess.Popen(evaluation_command(binary,model['path'],executor,max_gpu=max_gpu),
                    stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,env=env)
                def monitor():
                    while not stop.wait(1):
                        m=gpu_metrics.snapshot();row=sample_hardware(m,gpu_metrics.ram_available())
                        try:
                            status=Path(f'/proc/{proc.pid}/status').read_text()
                            rss=re.search(r'^VmRSS:\s+(\d+)\s+kB$',status,re.M)
                            row['server_rss_bytes']=int(rss.group(1))*1024 if rss else None
                        except OSError:row['server_rss_bytes']=None
                        report['samples'].append(row)
                        reason=evaluation_thermal_pressure(row,report,hotspot_critical_only=hotspot_critical_only) or physical_pressure(m,row['ram_available'],lease['margin_bytes'])
                        stop_for_pressure(proc,reason,report)
                observer=threading.Thread(target=monitor,daemon=True);observer.start()
                try:
                    ready=time.monotonic()+300
                    while time.monotonic()<ready:
                        if proc.poll() is not None:raise RuntimeError('Professor encerrou na carga')
                        try:
                            if teacher._call('/health',timeout=2).get('status') in ('ok','ready'):break
                        except (OSError,ValueError):pass
                        time.sleep(1)
                    else:raise TimeoutError('Professor não ficou pronto')
                    report['load_seconds']=round(300-(ready-time.monotonic()),2)
                    report['binary_sha256']=_sha(binary)
                    report['inference_started']=teacher.stamp()
                    inference_start=time.monotonic()
                    deadline=time.monotonic()+1800
                    if recheck_review_id is not None:
                        recheck_curation(home,recheck_review_id,entity,persona,deadline,report,path)
                    for case in ([] if case_set=='curation' else cases):
                        for method in methods:
                            result=evaluate_case(entity,case,method,writer_persona,references,deadline,report,path,
                                writer_context=writer_context,compare_critic_thinking=compare_critic_thinking,
                                review_persona=persona,curation_home=home)
                            print('CASO',case['id'],method,'PASS_TECNICO',result['technical_passed'],
                                  'SEGUNDOS',result['seconds'],result.get('error',''),flush=True)
                            if report['pressure']:raise RuntimeError('Pressão física; comparação interrompida')
                    if mentoring_comparison:
                        feedback=converse_with_mentor(entity,persona,deadline,report,path,followup=mentor_followup)
                        for case in cases:
                            result=evaluate_case(entity,case,'staged',persona,references,deadline,report,path,
                                arm='mentored',feedback=feedback,curation_home=home)
                            print('CASO',case['id'],'MENTORIA','PASS_TECNICO',result['technical_passed'],
                                  'SEGUNDOS',result['seconds'],result.get('error',''),flush=True)
                            if report['pressure']:raise RuntimeError('Pressão física; comparação interrompida')
                    if curator_note is not None:
                        for case in cases:
                            result=evaluate_case(entity,case,'staged',persona,references,deadline,report,path,
                                arm='calibrated',feedback=[dict(note=curator_note)],curation_home=home)
                            print('CASO',case['id'],'CALIBRACAO','PASS_TECNICO',result['technical_passed'],
                                  'SEGUNDOS',result['seconds'],result.get('error',''),flush=True)
                            if report['pressure']:raise RuntimeError('Pressão física; comparação interrompida')
                    prior=[]
                    for n,plan in enumerate(SCENARIO_PLANS[:situations]):
                        started=time.monotonic();result=dict(plan=plan)
                        try:
                            users=teacher.generate_situation(plan,8192,deadline,report['metrics'],
                                source_id=f'scenario:{n}',previous=prior)
                            result['users']=users;prior.extend(users)
                        except (ValueError,RuntimeError,OSError) as exc:result['error']=type(exc).__name__+': '+str(exc)
                        result['seconds']=round(time.monotonic()-started,2);report['situations'].append(result)
                        teacher._write(path,report)
                        print('CENARIO',plan['category'],'COMPLETO','users' in result,'SEGUNDOS',result['seconds'],flush=True)
                        if report['pressure']:raise RuntimeError('Pressão física; comparação interrompida')
                    report['inference_seconds']=round(time.monotonic()-inference_start,2)
                    report['complete']=comparison_complete(report['examples'],
                        limit*len(methods)*(2 if mentoring_comparison or (curator_note is not None and case_set!='curation') else 1),report['situations'],situations)
                except BaseException as exc:
                    report['error']=type(exc).__name__+': '+str(exc);raise
                finally:
                    stop.set();observer.join(timeout=2)
                    if proc.poll() is None:
                        proc.terminate()
                        try:proc.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            # Somente o filho criado por este ensaio; lease não fica livre com GPU em uso.
                            report['forced_owned_shutdown']=True;proc.kill();proc.wait(timeout=10)
                    teacher._SESSION_KEY=None
                    report['after']=gpu_metrics.snapshot();report['finished']=teacher.stamp()
                    report['summary']={method:dict(count=sum(e['method']==method for e in report['examples']),
                        technical_passed=sum(e['method']==method and e['technical_passed'] for e in report['examples']),
                        total_seconds=round(sum(e['seconds'] for e in report['examples'] if e['method']==method),2)) for method in methods}
                    report['arms']={arm:dict(count=sum(e['arm']==arm for e in report['examples']),
                        technical_passed=sum(e['arm']==arm and e['technical_passed'] for e in report['examples']),
                        total_seconds=round(sum(e['seconds'] for e in report['examples'] if e['arm']==arm),2))
                        for arm in ('baseline','mentored','calibrated')}
                    teacher._write(path,report);print('RELATORIO',path,flush=True)
    if publish_for_review:
        review=teacher.prepare_probe_references(home,path,entity,expected_hash=_sha(path))
        print('CURADORIA',review['id'],'ENTIDADE',entity,'PENDENTES',review['evidence_count'],flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=Path,required=True);p.add_argument('--entity',choices=teacher.ENTITIES,required=True)
    p.add_argument('--methods',nargs='+',choices=teacher.GENERATION_METHODS,default=list(teacher.GENERATION_METHODS))
    p.add_argument('--limit',type=int,choices=range(1,len(CASES)+1),default=2)
    p.add_argument('--experimental-references',action='store_true');p.add_argument('--confirm-gpu',action='store_true')
    p.add_argument('--executor',choices=('35b','9b','defiant-fable-9b'),default='35b',help='Só ensaio; não muda o professor ativo')
    p.add_argument('--situations',type=int,choices=range(len(SCENARIO_PLANS)+1),default=0)
    p.add_argument('--max-gpu',action='store_true',help='Fit máximo; margem de VRAM continua obrigatória')
    p.add_argument('--mentoring-comparison',action='store_true',help='Só 35B ou Defiant fixado/staged: antes e depois de conversa didática, sem treino')
    p.add_argument('--case-set',choices=('standard','generalization','personality','calibration','curation'),default='standard',help='Casos sintéticos congelados, não dataset')
    p.add_argument('--publish-for-review',action='store_true',help='Somente lote curadoria: registrar textos pendentes na revisão existente; não aprova nem treina')
    p.add_argument('--recheck-review-id',help='Reavaliar o texto congelado de uma curadoria da mesma entidade; não altera decisões')
    p.add_argument('--curator-note-file',type=Path,help='Só comparação manual: referência de estilo explícita, nunca dataset/memória')
    p.add_argument('--mentor-followup',help='Correção editorial explícita do curador; não incluir segredos ou dados reais')
    p.add_argument('--writer-context',choices=('current','focused'),default='current',help='Ensaio de projeção editorial; não muda jobs de produção')
    p.add_argument('--compare-critic-thinking',action='store_true',help='Revisar a mesma saída com/sem thinking; não muda o gate de produção')
    p.add_argument('--ablate-operational-rules',action='store_true',help='Só ensaio: omitir honestidade do escritor, mantendo perfil completo no crítico e nos arquivos')
    p.add_argument('--hotspot-critical-only',action='store_true',help='Ensaio explícito: hotspot alto é aviso; crítico do driver ainda cancela')
    a=p.parse_args()
    if not a.confirm_gpu:p.error('Sem confirmação nenhum modelo é carregado')
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt('Parada cooperativa')))
    run(a.home.resolve(),a.entity,a.methods,a.limit,a.experimental_references,executor=a.executor,situations=a.situations,
        max_gpu=a.max_gpu,hotspot_critical_only=a.hotspot_critical_only,mentoring_comparison=a.mentoring_comparison,
        case_set=a.case_set,mentor_followup=a.mentor_followup,writer_context=a.writer_context,
        compare_critic_thinking=a.compare_critic_thinking,ablate_operational_rules=a.ablate_operational_rules,
        curator_note=a.curator_note_file.read_text(encoding='utf-8') if a.curator_note_file is not None else None,
        publish_for_review=a.publish_for_review,recheck_review_id=a.recheck_review_id)
