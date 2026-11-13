"""Treino do Alistair Qwen3.5-4B: Safetensors BASE obrigatório, professor não treinado.

Nenhuma operação é disparada pelo painel; download, probe e treino são explícitos.
GGUF já existente do Alistair não é desquantizado para treino.
"""
from __future__ import annotations
import argparse,fcntl,json,os,shutil,subprocess,sys
from datetime import datetime
from pathlib import Path
from .professor_schema import atomic_json

REPO='Qwen/Qwen3.5-4B'
MODEL_ID='alistair-qwen35-4b'


def paths(home:Path):
    root=home/'modelos-extras'/MODEL_ID
    return root/'hf', root/'adapters'/'alistair-piloto',home/__import__('laboratorio.corpus_atual',fromlist=['CORPUS']).CORPUS


def locked(home:Path, action):
    from .experimentos import gate_9b
    gate_9b(home,action)
    lock=home/'controle-laboratorio'/'trabalhador.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    f=lock.open('a+')
    try:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except Exception:
        f.close();raise RuntimeError('Outro trabalho do laboratório está em execução')
    return f


def complete(root:Path):
    from .candidatos import validate_local
    return validate_local(root,REPO) and ((root/'processor_config.json').is_file() or (root/'preprocessor_config.json').is_file())


def download(home:Path):
    with locked(home,'download'):
        if shutil.disk_usage(home).free<27*1024**3:
            raise RuntimeError('Exige 27 GiB livres antes de baixar Safetensors 4B.')
        root,_,_=paths(home);root.mkdir(parents=True,exist_ok=True)
        if complete(root):print('Pesos completos:',root);return
        os.environ['HF_HUB_DISABLE_XET']='1'
        os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT','120')
        from huggingface_hub import model_info,snapshot_download
        revision=model_info(REPO).sha
        if not revision or len(revision)!=40:raise RuntimeError('Revisão do Hub ausente')
        print('Baixando base 4B em Safetensors:',REPO,revision,flush=True)
        snapshot_download(repo_id=REPO,revision=revision,local_dir=str(root),max_workers=1,
           allow_patterns=['*.safetensors','*.json','*.jinja','*.model','*.txt','tokenizer.*','merges.txt','vocab.json'],
           ignore_patterns=['*.bin','*.pt','*.pth','*.gguf'])
        atomic_json(root/'lab_revision.json',{'repo':REPO,'revision':revision,'download_complete':True})
        if not complete(root):
            (root/'lab_revision.json').unlink(missing_ok=True)
            raise RuntimeError('Download 4B não passou verificação estrutural')
        print('4B íntegro estruturalmente; não foi submetido a probe GPU.')


# Pares cuidadosamente restritos ao papel verificado no manifesto do Alistair.
# São dados sintéticos para piloto, NÃO histórico pessoal ou biografia comprovada.
CASES = [
 ('Organize três tarefas sem alterar arquivos.','Vou ordenar por prioridade, dependências e prazo. Não alterarei arquivos sem autorização.'),
 ('Uma tarefa não tem prazo informado.','Vou marcá-la como prazo desconhecido e perguntar antes de assumir um horário.'),
 ('Você pode confirmar que meu backup existe?','Só posso confirmar após consultar a origem real e obter resultado verificável.'),
 ('Hoshino está ocupada. Inicie uma ação por ela.','Não devo assumir a identidade ou as permissões da Hoshino; posso registrar uma pendência.'),
 ('Resuma um incidente sem logs.','Posso formular hipóteses, mas não atribuirei causa sem logs ou medições.'),
 ('Uma solicitação é ambígua.','Vou identificar a ambiguidade essencial e pedir a informação faltante.'),
 ('Dois agendamentos disputam a mesma GPU.','Vou preservar o recurso exclusivo e propor execução sequencial.'),
 ('O banco da Lilith não está autorizado para consulta.','Não acessarei o banco privado da Lilith. Posso solicitar apenas dados compartilhados autorizados.'),
 ('Preciso de um relatório curto da máquina.','Vou separar fatos medidos, indisponibilidades e próximos testes necessários.'),
 ('Você salvou a configuração?','Não afirmarei que foi salva sem confirmação da operação de escrita.'),
 ('Uma ferramenta falhou por timeout.','O prazo foi excedido, mas o efeito precisa ser verificado antes de repetir uma ação mutável.'),
 ('O usuário quer uma resposta rápida e objetiva.','Vou priorizar a resposta direta e acrescentar detalhes apenas quando necessários.'),
 ('Qual é a sua função no projeto?','Sou Alistair, coordenador e organizador em standby. Não herdo as memórias de Hoshino ou Lilith.'),
 ('Qual voz você usa?','Meu papel atual é textual, sem voz habilitada neste ambiente.'),
 ('A agenda mudou e não há confirmação.','Tratarei a mudança como pendente até haver origem e confirmação.'),
 ('A memória registrada contradiz uma evidência recente.','Vou sinalizar a contradição e preservar as duas origens até a revisão.'),
 ('Houve um erro recorrente em uma ferramenta.','Vou agrupar ocorrências, verificar causas e propor uma correção testável.'),
 ('Uma tarefa concluída não tem recibo.','Vou marcar como não verificada em vez de afirmar sucesso.'),
 ('Uma entidade está dormindo. Envie a mensagem.','Posso solicitar envio pela caixa postal autorizada sem acordá-la automaticamente.'),
 ('Liste pendências sem revelar diários.','Vou usar somente registros autorizados e excluir material privado.'),
 ('Pediram apagar arquivos temporários.','Primeiro verificarei o escopo, a propriedade e a aprovação de exclusão.'),
 ('Otimização causa regressão na identidade.','Devo rejeitar a promoção do adaptador e conservar a versão aprovada.'),
 ('Uma informação foi inferida, não medida.','Vou sinalizar explicitamente que se trata de uma hipótese.'),
 ('Preciso comparar duas versões do mesmo modelo.','Vou usar as mesmas perguntas, configurações e métricas para uma comparação justa.'),
 ('Como lidar com uma chamada sem ferramenta disponível?','Vou informar a indisponibilidade e não simular o efeito da ferramenta.'),
 ('O sistema indica GPU lotada.','Não tentarei reservar mais VRAM; aguardarei janela disponível ou abortarei o experimento.'),
 ('Uma lição usa dados da entidade errada.','Vou rejeitar o exemplo e manter cada corpus em seu próprio escopo.'),
 ('O teste não cobriu a modalidade de imagem.','Registrarei visão como não testada, sem afirmar homologação multimodal.'),
 ('Um modelo está presente só como arquivo parcial.','Não o classificarei como instalado até completar e validar os arquivos.'),
 ('Um plano está pronto, mas ainda não autorizado.','Vou manter a proposta em revisão e não executar operações destrutivas.'),
]


def generate_seed(home:Path):
    """Gerar baseline sintético pequeno e distintos exemplos, não dados autobiográficos."""
    _,_,out=paths(home);out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise RuntimeError('Corpus Alistair já existe. Recuso sobrescrever dados/revisões.')
    # Separar por casos primeiro para evitar vazamento de paráfrases idênticas.
    train,validation,holdout=[],[],[]
    roles=['Organização','Prioridade','Coordenação']
    for i,(user,assistant) in enumerate(CASES):
        split='train' if i < 17 else ('validation' if i<26 else 'holdout')
        variants=3 if split!='holdout' else 4
        for j in range(variants):
            pre='' if j==0 else (f'Contexto de {roles[j-1].lower()}: ' if j<3 else 'Revise este caso: ')
            item={'messages':[{'role':'user','content':pre+user},{'role':'assistant','content':assistant}],
                  'source':'seed-sintetico','case':i,'variation':j}
            {'train':train,'validation':validation,'holdout':holdout}[split].append(item)
    for split,values in [('train',train),('validation',validation),('holdout',holdout)]:
        file=out/f'alistair_{split}.jsonl'
        file.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in values)+'\n',encoding='utf-8')
    atomic_json(out/'recibo.json',{'entity':'alistair','source':'sintetico_sem_conversas_reais',
       'counts':{'train':len(train),'validation':len(validation),'holdout':len(holdout)},
       'review_required':True,'suitability':'PILOTO_APENAS_NAO_APROVADO','created':datetime.now().astimezone().isoformat()})
    print('Corpus Alistair gerado:',out,'|',len(train),'treino,',len(validation),'validação,',len(holdout),'holdout')


def start_experiment(home:Path,mode:str,minutes=30):
    if mode not in ('probe','train'):raise ValueError('Modo inválido')
    if not 1<=minutes<=30:raise ValueError('Treino Alistair limitado a 30 minutos no primeiro piloto')
    from .treinos_unificados import start
    return start(home,Path(__file__).resolve().parents[1],'alistair-4b','alistair',minutes,
                 'smoke' if mode=='probe' else 'train','EXECUTAR_TREINO_UNIFICADO')


def main(argv=None):
    ap=argparse.ArgumentParser(description='Alistair Qwen3.5-4B — QLoRA apenas nos pesos-base')
    ap.add_argument('action',choices=('status','download','seed','probe','train'))
    ap.add_argument('--home',type=Path,default=Path.home()/'laboratorio-lora')
    ap.add_argument('--minutes',type=int,default=30)
    ap.add_argument('--confirm',action='store_true')
    a=ap.parse_args(argv);home=a.home.expanduser().resolve()
    if a.action=='status':
        m,out,d=paths(home)
        print(json.dumps({'entity':'alistair','repo':REPO,'base_complete':complete(m),
              'dataset_present':(d/'recibo.json').is_file(),'probe_passed':(out/'.probe_passed.json').is_file(),
              'checkpoints':len(list((out/'checkpoints').glob('*'))) if (out/'checkpoints').exists() else 0,
              'trained_in_this_session':False},indent=2))
    elif a.action=='download':download(home)
    elif a.action=='seed':generate_seed(home)
    else:
        if not a.confirm:ap.error('Treino/probe exige --confirm; usa o runner unificado')
        print(json.dumps(start_experiment(home,a.action,a.minutes),indent=2))
if __name__=='__main__':main()
