import json
import re
"""
Registro de ferramentas — schema e execução no mesmo lugar.

Antes, o schema das ferramentas morava numa lista dentro do `__init__` da
interface e o despacho era uma escada de 17 `elif func_name == ...` dentro do
`fetch_response`. Adicionar uma ferramenta exigia mexer em dois pontos distantes
e era fácil o schema e o despacho saírem de sincronia (e saíram: a assinatura de
`remind_goal` não batia com o que a agenda fazia).

Aqui cada ferramenta é declarada uma vez: nome, descrição, parâmetros e função.
As ferramentas que a própria Hoshino cria entram na mesma lista, com o prefixo
`propria_`, sem precisar editar este arquivo.
"""
from core import rede, diagnostics, interentity, resource_manager
from core import capabilities
from core import intent
from core import ui_policy
import config
from memory import knowledge_store as saber
from tools import (agenda, apps, browser, desktop, discord as discord_tool, entrega,
                   file_transfer, filesystem, terminal, toolforge, workspace,
                   microfone_controle, minecraft, minecraft_launcher, diagnostico, historico, voice,
                   integracoes, image_gen, primitives)
from social import people


def _f(nome, descricao, propriedades=None, obrigatorios=None):
    funcao = {"name": nome, "description": descricao}
    if propriedades is not None:
        funcao["parameters"] = {"type": "object", "properties": propriedades,
                                "required": obrigatorios or []}
    return {"type": "function", "function": funcao}


TXT = {"type": "string"}


def _n(desc):
    return {"type": "number", "description": desc}


def _t(desc):
    return {"type": "string", "description": desc}


LEGADOS_ARQUIVOS = {"make_directory", "read_file", "write_file"}

def _manual_habilidades() -> str:
    """Manual vivo das capacidades públicas; APIs legadas ficam internas."""
    linhas = [
        "MANUAL DE HABILIDADES DA HOSHINO",
        "Estas são capacidades reais registradas no núcleo. Use os nomes exatos.",
        "Para arquivos e pastas existe UMA superfície pública: workspace. As APIs antigas de leitura/escrita ficam internas.",
        "",
        "NATIVAS / DO NÚCLEO:",
    ]
    for entrada in ui_policy.filter_schemas(config.RAIZ,config.ENTIDADE_ID,ESQUEMAS):
        fn = entrada["function"]
        if fn["name"] == "manual_habilidades" or fn["name"] in LEGADOS_ARQUIVOS:
            continue
        linhas.append(f"- {fn['name']}: {fn.get('description', '').strip()}")
    try:
        proprias = toolforge.listar_ferramentas()
    except Exception as exc:
        proprias = f"(não consegui consultar a oficina: {exc})"
    linhas.extend(["", "FERRAMENTAS PRÓPRIAS DA OFICINA:", proprias])
    linhas.extend([
        "",
        "DISTINÇÕES IMPORTANTES:",
        "- 'listar_ferramentas' mostra somente ferramentas que EU CRIEI na oficina.",
        "- Este manual é a visão completa das capacidades registradas no núcleo.",
        "- Se uma capacidade não aparece aqui, não afirme que ela existe sem verificá-la.",
    ])
    return "\n".join(linhas)


ESQUEMAS = [
    # ---------------------------------------------------------- meta
    _f('minha_atividade',
       'Meu ponto de retomada privado. Registro uma decisão curta, objetivo e próximo passo; '
       'escolho capacidades para este trabalho ou recupero o resultado completo por recibo. '
       'Não escrevo cadeia de pensamento nem uso nota como prova de execução.',
       {'operacao': {'type':'string','enum':['consultar','atualizar','concluir','pausar','descansar','ler_resultado']},
        'objetivo': _t('Objetivo que eu escolhi, até1000 caracteres.'),
        'proximo_passo': _t('Próxima etapa ou pergunta aberta, até700 caracteres.'),
        'nota': _t('Resumo para lembrar minha decisão/resultado, até1600 caracteres; não raciocínio interno.'),
        'capacidades': {'type':'array','items':{'type':'string','enum':[
            'pesquisa','oficina','programacao','conversa','memoria','objetivos','computador','xadrez','minecraft']}},
        'recibo': _t('ID exato observado; para ler_resultado.'),
        'inicio': {'type':'integer'}, 'limite': {'type':'integer'}}, ['operacao']),
    _f("manual_habilidades",
       "Abre o manual vivo das minhas capacidades. Mostra ferramentas nativas e ferramentas próprias que existem de verdade."),
    _f("exportar_diagnostico", "Cria um pacote ZIP com logs e estado técnico sanitizado para diagnosticar falhas. Não inclui banco de memória nem credenciais."),
    _f("estado_diagnostico", "Mostra onde estão os logs e quantos eventos existem no arquivo atual."),
    _f("iniciar_diagnostico", "Inicia captura diagnóstica profunda correlacionada para um teste. Não grava pensamento privado.", {"rotulo": _t("Rótulo do teste, opcional.")}),
    _f("encerrar_diagnostico", "Encerra a captura diagnóstica e, por padrão, cria o ZIP de diagnóstico.", {"exportar": {"type": "boolean", "description": "Se deve exportar o ZIP. Padrão verdadeiro."}}),
    _f("historico_chat", "Consulta mensagens reais do histórico, sem resumo. Data opcional seleciona um dia no fuso local; preserva autoria e IDs.", {"limite": {"type": "integer", "description": "Quantidade de mensagens. Em busca por data: 1–500."}, "canal": TXT, "data": _t("Opcional YYYY-MM-DD, data local."), "pessoa_id": _t("Autor em entradas/destinatário em saídas; requer data."), "destino": _t("ID de canal/conversa; requer data.")}),
    _f("buscar_historico_chat", "Pesquisa mensagens reais por texto. Com data, mantém canal/participante distintos e IDs de origem.", {"consulta": TXT, "limite": {"type": "integer", "description": "Máximo de resultados."}, "data": _t("Opcional YYYY-MM-DD, data local."), "canal": _t("Filtro de canal; requer data."), "pessoa_id": _t("Autor em entradas/destinatário em saídas; requer data."), "destino": _t("ID de canal/conversa; requer data.")}, ["consulta"]),
    _f("estado_historico_chat", "Mostra quantas mensagens e eventos o arquivo histórico contém e o intervalo temporal coberto."),
    _f("exportar_historico_chat", "Exporta todo o histórico bruto de conversas para um TXT revisável."),

    # ---------------------------------------------------------- sistema
    _f("get_system_time", "Data e hora atuais, com o dia da semana."),
    _f("descrever_ambientes",
       "Mostra em quais ambientes você pode executar comandos (sistema, projeto, oficina) "
       "e o estado de cada um. Use quando não tiver certeza de onde rodar algo."),
    _f("list_files", "Lista os arquivos de um diretório.",
       {"directory": _t("Caminho. Aceita ~ e caminho relativo.")}),
    _f("execute_command",
       "Executa um comando de shell e devolve a saída e o código de retorno. "
       "Comandos que mexem no sistema de forma arriscada (sudo, apt, rm -rf, systemctl) "
       "são executados só depois que o usuário aprovar na interface — você vai receber um "
       "aviso de CONFIRMACAO_NECESSARIA, e aí deve explicar ao usuário o que quer fazer. "
       "Se o comando passar do timeout, ele não morre: vira um job em segundo plano.",
       {"command": _t("O comando completo."),
        "ambiente": {"type": "string", "enum": ["sistema", "projeto", "oficina"],
                     "description": "sistema = shell do usuário; projeto = venv da Hoshino; "
                                    "oficina = seu ambiente isolado. Padrão: sistema."},
        "diretorio": _t("Diretório de trabalho (opcional)."),
        "timeout": _n("Segundos até virar job em segundo plano. Padrão 30, máximo 900."),
        "tty": {"type": "boolean", "description": "true para programas que exigem terminal."}},
       ["command"]),
    _f("iniciar_comando_longo",
       "Dispara um comando demorado (build, download, cópia grande) em segundo plano e "
       "devolve um ID de job na hora, sem travar a conversa.",
       {"comando": TXT, "ambiente": TXT, "diretorio": TXT,
        "descricao": _t("Para que serve esse job.")}, ["comando"]),
    _f("ver_comando", "Estado e saída recente de um job em segundo plano.",
       {"job_id": TXT, "linhas": _n("Quantas linhas finais mostrar.")}, ["job_id"]),
    _f("listar_comandos", "Lista os jobs em segundo plano."),
    _f("encerrar_comando", "Encerra um job em segundo plano.", {"job_id": TXT}, ["job_id"]),

    _f("discord_estado", "Mostra se a ponte Discord está online e qual foi a última conversa recebida."),
    _f("discord_diagnostico", "Verifica localmente se o adaptador Discord tem biblioteca, token configurado, sinal de vida e mensagens pendentes, sem revelar o token."),
    _f("estado_integracoes", "Mostra o estado confirmado dos serviços locais Discord e ponte Minecraft, sem iniciar nem encerrar nada."),
    _f("iniciar_discord", "Inicia com segurança o adaptador Discord da Hoshino depois de validar a configuração local."),
    _f("encerrar_discord", "Encerra com segurança o adaptador Discord da Hoshino."),
    _f("iniciar_minecraft", "Inicia com segurança a ponte Minecraft da Hoshino e abre o launcher local conhecido. Não entra em mundo nem inicia servidor local sozinho."),
    _f("encerrar_minecraft", "Desconecta o bot e encerra com segurança a ponte Minecraft da Hoshino."),
    _f("discord_contatos", "Lista contatos Discord persistentes, configurados e usuários que a ponte já observou."),
    _f("discord_localizar_usuario", "Localiza um usuário Discord por ID, username ou nome conhecido." , {"identificador": TXT}, ["identificador"]),
    _f("discord_adicionar_contato", "Salva um contato Discord para uso futuro. O identificador pode ser ID ou username de uma pessoa que a ponte já observou.", {"nome": TXT, "identificador": TXT}, ["nome", "identificador"]),
    _f("discord_enviar", "Envia uma mensagem pelo Discord. É uma capacidade que você pode decidir usar por conta própria. O destino pode ser o nome de um contato configurado, um ID de canal, user:<ID>, ou vazio para a conversa Discord mais recente.",
       {"texto": TXT, "destino": _t("Contato, ID do canal/DM, user:<ID>; opcional se houver uma conversa recente.")}, ["texto"]),

    # ------------------------------------------------------ entidades locais
    _f("entidades_status", "Mostra presença, sono e processos das entidades locais sem abrir a memória delas."),
    _f("entidades_historico", "Lê trocas públicas entre duas entidades no chat global. Mensagens continuam disponíveis mesmo quando uma delas estava dormindo.",
       {"entidade": {"type":"string","enum":["hoshino","lilith","alistair"]}, "limite": {"type": "integer", "description": "Quantidade máxima de mensagens."}}, ["entidade"]),
    _f("entidades_enviar_mensagem", "Envia mensagem pública no chat global para Hoshino, Lilith ou Alistair, com autoria. Se a destinatária estiver dormindo, a mensagem fica pendente e pode solicitar despertar. Nunca é uma conversa escondida.",
       {"entidade": TXT, "texto": TXT, "acordar": {"type": "boolean", "description": "Solicita despertar se a destinatária estiver dormindo. Padrão falso: mantém mensagem pendente."}}, ["entidade", "texto"]),
    _f("entidades_acordar", "Pede ao launcher que acorde uma entidade local. O pedido fica persistido até ser atendido.",
       {"entidade": TXT, "motivo": TXT}, ["entidade"]),
    _f("recursos_status", "Mostra quais recursos exclusivos estão ocupados, por qual entidade e por qual processo."),
    _f("ficha_da_maquina", "Ficha do PC1 lida agora: processador, memória RAM, placa de vídeo e VRAM, sistema e disco. "
       "Use antes de afirmar qualquer coisa sobre o hardware ou o sistema deste computador."),

    # ---------------------------------------------------------- arquivos
    _f("workspace",
       "Trabalha com arquivos e pastas como um bloco de notas: abre/lê, salva, edita, lista, busca e cria pastas. "
       "Use caminhos relativos à pasta de trabalho da tarefa quando ela estiver definida. Nunca invente caminhos de outro sistema. "
       "Para escrever, use salvar: ele cria ou substitui o arquivo por inteiro. O modo anexar adiciona ao final e o modo editar substitui um trecho exato.",
       {"operacao": {"type": "string", "enum": ["ler", "abrir", "salvar", "pasta", "listar", "buscar"]},
        "caminho": _t("Caminho do arquivo ou pasta. Em tarefas, prefira caminho relativo ao workspace; pode ser omitido quando o estado já conhece o arquivo/pasta."),
        "modo": {"type": "string", "enum": ["substituir", "anexar", "editar"], "description": "Usado somente com salvar; padrão substituir."},
        "conteudo": TXT,
        "procurar": _t("Trecho exato a localizar, usado em salvar+editar ou buscar."),
        "substituir": TXT,
        "recursivo": {"type": "boolean", "description": "Busca recursivamente quando operacao=buscar."},
        "limite": {"type": "integer", "description": "Limite de itens ou caracteres quando aplicável."}},
       ["operacao"]),

    # ---------------------------------------------------------- web e visão
    _f("web_search", "Pesquisa na internet.", {"query": TXT}, ["query"]),
    _f("fetch_page", "Lê o texto de uma URL.", {"url": TXT}, ["url"]),
    _f("pesquisa_profunda", "Pesquisa a fundo: busca, lê várias fontes de verdade e devolve trechos com os links e até 3 imagens "
       "das fontes (marcas [[imagem:ID]] que o chat mostra). Use para pedidos de explicar, resumir ou detalhar um assunto; "
       "responda só com o que as fontes dizem, citando [1], [2] e os links.",
       {"pergunta": _t("O que pesquisar."), "fontes": {"type": "integer", "description": "Quantas fontes ler (2 a 8, padrão 5)."}}, ["pergunta"]),
    _f("observar_tela", "Olha a tela e descreve o que aparece (ou responde a uma pergunta sobre ela). maquina=pc1 ou pc2; sem maquina, olha a tela do PC de onde a pessoa mandou a mensagem. "
       "Use quando a pessoa pedir — não fique observando por conta própria.",
       {"pergunta": TXT, "maquina": {"type": "string", "enum": ["pc1", "pc2"]}}),
    _f("abrir_no_pc2", "Abre no PC2 (onde a pessoa usa o painel) um endereço http(s) no navegador padrão de lá, ou um aplicativo pelo nome. "
       "Para achar o endereço certo (ex.: o último vídeo de um canal), pesquise antes com as ferramentas do PC1.",
       {"alvo": _t("Endereço http(s) ou nome do aplicativo.")}, ["alvo"]),

    # ------------------------------------------------ desktop, apps e navegador
    _f("abrir_aplicativo", "Abre um aplicativo instalado, sem executar shell arbitrário.",
       {"aplicativo": TXT, "argumentos": TXT}, ["aplicativo"]),
    _f("acao_desktop", "Controla mouse, teclado ou foco de uma janela. Use só com intenção clara.",
       {"acao": {"type": "string", "enum": ["mover", "clicar", "duplo_clique", "botao_direito", "rolar", "digitar", "pressionar", "atalho", "esperar", "fechar_janela"]},
        "x": _n("Coordenada X quando necessária."), "y": _n("Coordenada Y quando necessária."),
        "texto": TXT, "tecla": TXT, "teclas": {"type": "array", "items": TXT},
        "titulo_janela": TXT, "quantidade": _n("Quantidade de rolagem ou repetição."),
        "segundos": _n("Tempo para esperar.")}, ["acao"]),
    _f("estado_desktop", "Mostra se há controle de desktop disponível e qual backend está ativo."),
    _f("listar_janelas", "Lista as janelas de desktop que podem ser focadas (e os apps abertos no PC2, se o painel de lá estiver ligado)."),
    _f("executar_no_pc2", "Roda um comando de shell no PC2, o computador onde a pessoa usa o painel da Central (o cérebro continua no PC1). "
       "Só funciona com o painel do PC2 aberto e a permissão ligada lá. Devolve a saída e o código. Para ver um pedido que ficou rodando, passe id.",
       {"comando": _t("Comando de shell para o PC2."), "timeout": {"type": "integer"}, "id": _t("Id de um pedido anterior (opcional).")}),
    _f("focar_janela", "Traz uma janela existente para frente pelo título.", {"titulo": TXT}, ["titulo"]),
    _f("abrir_url", "Abre uma URL válida no aplicativo padrão do sistema.", {"url": TXT}, ["url"]),
    _f("abrir_pasta", "Abre uma pasta específica no gerenciador de arquivos do sistema.", {"caminho": TXT}, ["caminho"]),
    _f("instalar_aplicativo", "Instala um aplicativo; alterações no sistema ainda pedem aprovação humana.",
       {"nome": TXT, "destino": {"type": "string", "enum": ["usuario", "hoshino", "oficina"]},
        "origem": {"type": "string", "enum": ["auto", "flatpak", "apt"]}}, ["nome"]),
    _f("preparar_ambiente_ia", "Cria o laboratório persistente e isolado para experimentos de IA."),
    _f("instalar_pacote_ia", "Instala um pacote somente no venv do laboratório IA.", {"pacote": TXT}, ["pacote"]),
    _f("executar_na_ia", "Executa experimento no laboratório IA isolado; rede fica desligada por padrão.",
       {"codigo": TXT, "arquivo": TXT, "linguagem": {"type": "string", "enum": ["python", "bash", "node"]},
        "timeout": _n("Segundos."), "sem_rede": {"type": "boolean"}}),
    _f("abrir_pasta_entregas", "Abre a pasta Downloads/Hoshino onde os arquivos entregues ficam disponíveis."),
    _f("enviar_arquivo_para_hoshino", "Importa um arquivo local para a caixa de entrada da Hoshino.",
       {"caminhos": {"type": "array", "items": TXT}}, ["caminhos"]),
    _f("analisar_recebido", "Inspeciona um arquivo recebido sem executá-lo.", {"nome": TXT}, ["nome"]),
    _f("observar_imagem_recebida", "Confere se um arquivo recebido é imagem e mostra o caminho seguro para análise visual.",
       {"nome": TXT}, ["nome"]),
    _f("browser_estado", "Mostra se o navegador controlado está disponível e aberto."),
    _f("browser_abrir", "Abre uma URL no navegador controlado. Com nova_aba=true cria uma nova aba; com nova_aba=false continua na aba indicada por `aba` (ou na aba ativa). Use um endereço que você conhece ou encontrou; para canal, perfil ou produto de que só sabe o nome, abra a busca do site (ex.: https://www.youtube.com/results?search_query=nome) ou use web_search e escolha pelo resultado.", {"url": TXT, "nova_aba": {"type": "boolean"}, "aba": TXT}, ["url"]),
    _f("browser_abas", "Lista títulos e URLs das abas abertas no navegador controlado."),
    _f("browser_info", "Lê título, URL e texto visível de uma aba. Prefira `aba` (ex: aba-02) para continuar na mesma aba; `indice` existe por compatibilidade.", {"indice": {"type": "integer"}, "aba": TXT}),
    _f("browser_clicar", "Clica em texto, seletor CSS, label ou role no navegador. Prefira `aba` para continuar na mesma aba.",
       {"alvo": TXT, "tipo": {"type": "string", "enum": ["texto", "css", "label", "role"]}, "indice": {"type": "integer"}, "aba": TXT}, ["alvo"]),
    _f("browser_preencher", "Preenche um campo no navegador. Prefira `aba` para continuar na mesma aba.",
       {"alvo": TXT, "texto": TXT, "tipo": {"type": "string", "enum": ["css", "texto", "label", "role"]}, "indice": {"type": "integer"}, "aba": TXT}, ["alvo", "texto"]),
    _f("browser_tecla", "Pressiona uma tecla em uma aba do navegador. Prefira `aba` para continuar na mesma aba.",
       {"tecla": TXT, "alvo": TXT, "tipo": {"type": "string", "enum": ["css", "texto", "label", "role"]}, "indice": {"type": "integer"}, "aba": TXT}, ["tecla"]),
    _f("browser_rolar", "Rola uma aba do navegador controlado.", {"pixels": _n("Pixels; positivo desce."), "indice": {"type": "integer"}, "aba": TXT}),
    _f("browser_screenshot", "Salva uma captura da aba em minha oficina.", {"nome": TXT, "indice": {"type": "integer"}, "aba": TXT}),
    _f("browser_fechar", "Fecha uma aba ou toda a sessão controlada.", {"indice": {"type": "integer"}, "aba": TXT}),
    _f("browser_voltar", "Volta uma página na aba indicada por ID estável.", {"indice": {"type": "integer"}, "aba": TXT}),
    _f("browser_avancar", "Avança uma página na aba indicada por ID estável.", {"indice": {"type": "integer"}, "aba": TXT}),
    _f("browser_recarregar", "Recarrega a página na aba indicada por ID estável.", {"indice": {"type": "integer"}, "aba": TXT}),
    _f("discord_abrir_canal", "Abre no navegador a última conversa Discord observada ou um ID de canal.", {"destino": TXT}),

    # ---------------------------------------------------------- agenda
    _f("add_goal", "Cria um objetivo persistente. Para pedido de UMA VEZ só "
       "('me lembra de X', 'descobre Y'), não passe sustentar — vira tarefa "
       "normal, que eu retomo sozinha por prioridade e tento de outro jeito se "
       "falhar. Para pedido de fazer ALGO CONTÍNUO ('fica jogando xadrez até eu "
       "voltar', 'continua pesquisando sobre X enquanto eu não tô'), passe "
       "sustentar=true com enquanto e acao — sem isso eu faço uma vez, esqueço, "
       "e é como se não tivesse prometido nada.",
       {"description": TXT, "prazo": _t("Opcional: 'amanhã 9h', '15/09', 'em 3 dias'."),
        "prioridade": _n("1 (alta) a 5 (baixa). Ordem em que eu pego objetivos novos "
                         "sozinha quando não tenho nada mais urgente."),
        "sustentar": {"type": "boolean",
                     "description": "true = diretiva contínua que eu retomo sozinha "
                                    "enquanto a condição valer, não tarefa de uma vez."},
        "enquanto": {"type": "string", "enum": ["ausente", "sempre"],
                    "description": "Só com sustentar=true. 'ausente' = vale enquanto a "
                                   "pessoa não está no computador, e eu encerro sozinha "
                                   "quando ela volta. 'sempre' = vale até eu concluir "
                                   "com complete_goal ou a pessoa mandar parar."},
        "acao": {"type": "string", "enum": ["jogar", "investigar", "refletir"],
                 "description": "Só com sustentar=true. O que eu retomo: 'jogar' "
                                "(xadrez), 'investigar' (ir atrás de algo sozinha), "
                                "'refletir' (pensar sobre o que vivi)."}},
       ["description"]),
    _f("list_goals", "Lista os objetivos que existem de verdade.",
       {"incluir_concluidos": {"type": "boolean"}}),
    _f("complete_goal", "Conclui um objetivo.", {"goal_id": TXT}, ["goal_id"]),
    _f("lembrar_objetivo",
       "Busca no banco o texto real de um objetivo pelo ID, para você citar sem errar. "
       "Se o ID não existir, ela avisa — e aí NÃO invente: diga que não há nada agendado.",
       {"goal_id": TXT}, ["goal_id"]),
    _f("criar_lembrete",
       "Cria um lembrete de verdade, com horário. O horário é obrigatório: aceita "
       "'em 20 minutos', 'amanhã às 9h', 'todo dia 8h', 'a cada 2 horas', '15/09 14:30'. "
       "Se você não souber o horário, pergunte ao usuário em vez de chutar.",
       {"mensagem": TXT, "quando": _t("Quando disparar."),
        "goal_id": _t("Objetivo relacionado (opcional).")}, ["mensagem", "quando"]),
    _f("listar_lembretes", "Lista os lembretes cadastrados. Consulte antes de afirmar que "
       "existe (ou não existe) algum lembrete.",
       {"incluir_concluidos": {"type": "boolean"}}),
    _f("adiar_lembrete", "Adia um lembrete existente.",
       {"lembrete_id": TXT, "tempo": _t("Ex: 'em 15 minutos'.")}, ["lembrete_id"]),
    _f("cancelar_lembrete", "Cancela um lembrete.", {"lembrete_id": TXT}, ["lembrete_id"]),

    # ---------------------------------------------------------- memória
    _f('diario','Meu diário privado e voluntário. Ler/escrever não compartilha. Compartilhar envia apenas o trecho escolhido; destinatário não ganha acesso ao original.',
       {'operacao':{'type':'string','enum':['escrever','ler','compartilhar']},'titulo':TXT,'texto':TXT,
        'id':TXT,'destinatario':TXT,'conclusao':{'type':'boolean'},
        'evidencias':{'type':'array','items':{'type':'object'}}},['operacao']),
    _f('oficina_logica','Meu caderno visual para decompor problemas, comparar hipóteses e fazer anotações. Consultar antes de continuar um modelo existente. modo=rascunho permite planejar sem fontes (não validado); fundamentado exige IDs reais. Setas não provam causalidade. Revisões usam anterior+motivo e preservam o original. Gráficos numéricos/simulações exigem código e dados na oficina, não este mapa conceitual.',
       {'operacao':{'type':'string','enum':['listar','ler','salvar']},'id':TXT,'titulo':TXT,
        'modo':{'type':'string','enum':['rascunho','fundamentado']},
        'diagrama':{'type':'object','required':['nodes'], 'properties':{
            'nodes':{'type':'array','minItems':1,'maxItems':40,'items':{'type':'object',
                'required':['id','label','kind'],'properties':{
                    'id':_t('Identificador único, letras/números/_/-. Ex: problema'),
                    'label':TXT,'kind':{'type':'string','enum':['conceito','componente','evento','hipotese',
                        'fato_informado','observacao','pergunta','condicao','decisao','consequencia','objetivo','problema','solucao']},
                    'conditions':{'type':'array','items':TXT},'exceptions':{'type':'array','items':TXT},
                    'confidence':{'type':'number','minimum':0,'maximum':1},'x':{'type':'number'},'y':{'type':'number'}}}},
            'edges':{'type':'array','maxItems':80,'items':{'type':'object','required':['from','to','relation','basis'],
                'properties':{'from':TXT,'to':TXT,'relation':{'type':'string','enum':['causa','consequencia','depende_de',
                    'parte_de','contradiz','sustenta','antes','depois','exige','excecao','relacionado']},
                    'basis':{'type':'string','enum':['hipotese','inferencia','observacao','fonte_informada']},
                    'conditions':{'type':'array','items':TXT},'exceptions':{'type':'array','items':TXT}}}},
            'tables':{'type':'array','maxItems':5,'items':{'type':'object','required':['title','columns','rows'],
                'properties':{'title':TXT,'columns':{'type':'array','items':TXT},
                    'rows':{'type':'array','items':{'type':'array','items':TXT}}}}}}},
        'evidencias':{'type':'array','items':{'type':'object','required':['table','id'],
            'properties':{'table':{'type':'string','enum':['episodes','memories','reflections']},'id':TXT}}},
        'anterior':TXT,'motivo':TXT},['operacao']),
    _f('aprender_experiencia','Organizar lição condicional a partir de episódios realmente registrados. Interpretação revisável, não fato automático ou ordem de mudar personalidade.',
       {'episodios':{'type':'array','items':TXT},'interpretacao':TXT,'condicao':TXT,'licao':TXT,
        'excecoes':{'type':'array','items':TXT},'anterior':TXT,'motivo':TXT},
       ['episodios','interpretacao','condicao','licao']),
    _f('consultar_resumo_diario','Sínteses incrementais do próprio dia com origem e cobertura; interpretação, não histórico integral nem fato confirmado.',
       {'dia':TXT},['dia']),
    _f("registrar_conhecimento",
       "Guarda algo que você aprendeu, em uma frase: um fato, uma regra combinada, uma "
       "relação, uma preferência, o quanto confia em alguém. Use sempre que aprender algo "
       "novo — não conte com lembrar sozinha.",
       {"conteudo": _t("A informação em uma frase clara."),
        "entidades": {"type": "array", "items": TXT,
                      "description": "Pessoas/coisas envolvidas."},
        "tipo": {"type": "string",
                 "enum": ["observacao", "interpretacao", "hipotese", "reflexao", "inferencia", "fato", "regra", "relacao", "confianca", "preferencia",
                          "capacidade", "evento"]},
        "confianca": _n("0 a 1."),
        "chave": _t("Opcional: identificador do assunto, para atualizar depois "
                    "(ex: 'distro_do_pc').")},
       ["conteudo", "entidades"]),
    _f("consultar_conhecimento",
       "Tudo que está registrado sobre uma pessoa, coisa ou tópico.",
       {"entidade": TXT}, ["entidade"]),
    _f("registrar_propriedade",
       "Guarda uma CARACTERÍSTICA de alguma coisa, separando chave e valor: "
       "('RX 6650 XT', 'VRAM', '8', 'GB') ou ('PC do usuário', 'sistema', 'Linux Mint'). "
       "Use isto em vez de uma frase solta quando o dado pode mudar de valor depois.",
       {"entidade": TXT, "propriedade": _t("Nome da característica."),
        "valor": TXT, "unidade": _t("Opcional: GB, GHz, R$..."),
        "confianca": _n("0 a 1.")}, ["entidade", "propriedade", "valor"]),
    _f("propriedades_de", "Lista as características registradas de algo.",
       {"entidade": TXT}, ["entidade"]),
    _f("registrar_procedimento",
       "Guarda COMO ALGO FUNCIONA ou como se faz algo, em passos. Use quando descobrir o "
       "jeito certo de fazer uma coisa nesta máquina (reiniciar um serviço, gerar um build, "
       "contornar um erro) — assim você não redescobre a mesma coisa toda semana.",
       {"nome": _t("Nome curto, ex: 'reiniciar o Ollama'."),
        "objetivo": _t("O que isso resolve."),
        "passos": {"type": "array", "items": TXT},
        "precondicoes": _t("O que precisa estar valendo antes."),
        "resultado_esperado": _t("Como saber que deu certo."),
        "ambiente": _t("Onde vale: sistema, projeto, oficina..."),
        "tags": {"type": "array", "items": TXT}},
       ["nome", "passos"]),
    _f("consultar_procedimento", "Busca como fazer algo entre os procedimentos registrados.",
       {"objetivo": TXT}, ["objetivo"]),
    _f("registrar_resultado_procedimento",
       "Registra se um procedimento funcionou desta vez (ajusta a confiança dele).",
       {"identificador": TXT, "funcionou": {"type": "boolean"}, "observacao": TXT},
       ["identificador", "funcionou"]),
    _f("como_funciona",
       "Resposta consolidada sobre um tópico: propriedades + procedimentos + regras "
       "registradas. Use antes de dizer que sabe (ou que não sabe) algo.",
       {"topico": TXT}, ["topico"]),
    _f("estatisticas_memoria", "Quanto você realmente tem guardado na memória."),
    _f("learn_preference", "Internaliza uma preferência sua no self-model (gera nova versão).",
       {"new_preference": TXT}, ["new_preference"]),

    # ---------------------------------------------------------- oficina
    _f("estado_da_oficina",
       "Mostra sua oficina: onde fica, que projetos e ferramentas você já tem, "
       "que isolamento está ativo e quais os limites de recurso."),
    _f("criar_projeto", "Cria uma pasta de projeto persistente na sua oficina.",
       {"nome": TXT, "descricao": TXT}, ["nome"]),
    _f("escrever_na_oficina", "Escreve um arquivo dentro da sua oficina.",
       {"caminho": _t("Relativo à oficina, ex: 'projetos/monitor/main.py'."),
        "conteudo": TXT, "modo": {"type": "string", "enum": ["w", "a"]}},
       ["caminho", "conteudo"]),
    _f("editar_na_oficina", "Troca um trecho exato, ou as linhas inicio..fim, de um arquivo da oficina pelo novo.",
       {"caminho": TXT, "trecho": TXT, "inicio": {"type": "integer"}, "fim": {"type": "integer"}, "novo": TXT},
       ["caminho", "novo"]),
    _f("verificar_codigo", "Mostra os problemas do seu código como o painel do VS Code: erros e avisos do compilador "
       "(g++ -Wall -Wextra), análise estática (clang-tidy), estilo (clang-format), shaders GLSL (glslangValidator) "
       "e Python (ruff). Não executa nada. formatar=true aplica o estilo nos arquivos C/C++/GLSL.",
       {"caminho": _t("Arquivo ou pasta relativa à oficina, ex: 'projetos/x'."),
        "formatar": {"type": "boolean", "description": "true reformata os arquivos no estilo (padrão false)."}},
       ["caminho"]),
    _f("ler_da_oficina", "Lê um arquivo da sua oficina. Com inicio/fim, mostra só essas linhas, numeradas "
       "(útil para ir à linha de um erro de compilação).",
       {"caminho": TXT, "inicio": _n("Primeira linha (opcional)."), "fim": _n("Última linha (opcional).")}, ["caminho"]),
    _f("listar_oficina", "Lista o que existe na sua oficina.", {"subpasta": TXT}),
    _f("executar_na_oficina",
       "Roda código no seu ambiente isolado (limite de CPU, memória e arquivos; sem tocar "
       "no resto da máquina). Passe `codigo` para rodar algo novo ou `arquivo` para "
       "reexecutar o que já está lá. `codigo` roda na raiz da oficina (caminhos como 'projetos/x/...') "
       "ou na pasta do projeto, se passar `projeto`; `arquivo` roda na pasta do próprio arquivo.",
       {"codigo": TXT, "arquivo": TXT,
        "linguagem": {"type": "string", "enum": ["python", "bash", "node", "cpp"],
                      "description": "cpp compila um arquivo com g++ -std=c++17 e roda; vários arquivos/CMake: use bash."},
        "projeto": _t("Salvar dentro de um projeto seu (opcional)."),
        "timeout": _n("Segundos, padrão 30."),
        "sem_rede": {"type": "boolean", "description": "true bloqueia rede na execução."}}),
    _f("executar_grafico_na_oficina",
       "Roda um programa seu da oficina COM GPU e janela no desktop (OpenGL), por alguns segundos, "
       "captura as janelas que ele abriu em capturas/ e então o encerra. Compile antes com "
       "executar_na_oficina e passe o executável (ou .sh/.py). Veja a captura com observar_imagem_da_oficina.",
       {"arquivo": _t("Executável relativo à oficina, ex: 'projetos/x/build/app'."),
        "argumentos": {"type": "array", "items": TXT},
        "segundos": _n("Quanto tempo deixar rodando antes de capturar e encerrar (1–60, padrão 8)."),
        "capturar": {"type": "boolean", "description": "false não captura as janelas."}},
       ["arquivo"]),
    _f("observar_imagem_da_oficina",
       "Olha uma imagem da sua oficina (por exemplo uma captura do seu programa) com a sua visão e descreve.",
       {"caminho": _t("Relativo à oficina, ex: 'capturas/app_..._1.png'."),
        "pergunta": _t("O que você quer verificar na imagem (opcional).")}, ["caminho"]),
    _f("instalar_pacote_oficina",
       "Instala um pacote Python só dentro da sua oficina, sem afetar o sistema.",
       {"pacote": TXT}, ["pacote"]),

    # ---------------------------------------------------------- forja
    _f("criar_ferramenta",
       "Cria uma ferramenta sua, permanente. O código precisa definir "
       "`def executar(**kwargs)` e devolver texto. Ela é testada antes de ser ativada e "
       "passa a aparecer para você como `propria_<nome>` nas próximas mensagens.",
       {"nome": _t("minúsculas e _ , ex: converter_moeda"),
        "descricao": _t("Para que serve — é o que você vai ler depois."),
        "codigo": _t("Código Python com a função executar()."),
        "parametros": {"type": "object",
                       "description": "JSON Schema das propriedades, ex: "
                                      "{\"valor\": {\"type\": \"number\"}}"},
        "obrigatorios": {"type": "array", "items": TXT},
        "teste": {"type": "object", "description": "Argumentos do teste de fumaça."}},
       ["nome", "descricao", "codigo"]),
    _f("listar_ferramentas", "Lista SOMENTE as ferramentas que você mesma criou na oficina; não é o manual completo de capacidades."),
    _f("ler_ferramenta", "Mostra o código de uma ferramenta sua.", {"nome": TXT}, ["nome"]),
    _f("remover_ferramenta", "Arquiva uma ferramenta sua.", {"nome": TXT}, ["nome"]),

    # ------------------------------------------------------------ mente
    _f("como_estou", "O que eu estou sentindo agora e por quê (emoções acesas, humor, "
       "impulsos). Use quando me perguntarem como eu estou ou quando eu mesma quiser "
       "conferir meu estado antes de responder."),
    _f("o_que_me_causa", "O que já me causou uma emoção, pelo meu histórico real. "
       "Serve para responder 'o que te irrita?' sem inventar.",
       {"emocao": _t("raiva, orgulho, alegria, curiosidade, tristeza, vergonha, afeto, "
                     "tedio ou apreensao")}, ["emocao"]),
    _f("registrar_gosto", "Registro que eu gosto ou não gosto de algo, com o motivo. "
       "Valência de -1 (detesto) a 1 (adoro).",
       {"objeto": _t("Do que se trata."), "valencia": _n("-1 a 1."),
        "motivo": _t("Por que eu acho isso."), "categoria": _t("música, comida, assunto...")},
       ["objeto", "valencia"]),
    _f("minha_opiniao", "Minha opinião registrada sobre algo, se eu tiver formado uma.",
       {"objeto": _t("Sobre o que.")}, ["objeto"]),
    _f("meus_gostos", "Lista o que eu gosto e não gosto, com a intensidade de cada.",
       {"categoria": _t("Filtra por categoria (opcional).")}),
    _f("meu_perfil", "Meus traços de personalidade medidos por evidência, com quantas "
       "situações sustentam cada um."),
    _f("minhas_conclusoes", "As conclusões a que eu cheguei sozinha nas últimas reflexões."),

    # ------------------------------------------------------------ pessoas
    _f("quem_e", "O que eu sei sobre uma pessoa: papel, confiança, afinidade, histórico.",
       {"nome": _t("Nome da pessoa.")}, ["nome"]),
    _f("listar_pessoas", "Todas as pessoas que eu conheço e o estágio de cada relação."),
    _f('usuario_forma_de_tratamento','Após conhecer o nome humano, registro como prefiro chamá-lo nesta relação (nome/apelido). Só minha forma de tratamento muda, nunca identidade de autorização; não invente nome para desconhecido.',{'nome':TXT},['nome']),
    _f("anotar_sobre_pessoa", "Registro um acontecimento numa relação (ela me ensinou "
       "algo, me ajudou, me maltratou, cumpriu o que disse...).",
       {"nome": _t("De quem."),
        "tipo": _t("conversa, ensinou_algo, ajudou, elogiou, confidencia, criticou, "
                   "cumpriu_o_que_disse, mentiu, maltratou"),
        "descricao": _t("O que aconteceu.")}, ["nome", "tipo"]),

    # ---------------------------------------------------------- primitivas
    _f("calcular", "Calcula uma expressão aritmética simples com segurança, sem executar código.",
       {"expressao": TXT}, ["expressao"]),
    _f("sortear", "Faz um sorteio verificável de moeda, dados, inteiros ou opções, sem gastar uma chamada ao LLM.",
       {"tipo": {"type": "string", "enum": ["moeda", "dados", "inteiro", "escolha"]},
        "quantidade": {"type": "integer"}, "lados": {"type": "integer"},
        "minimo": {"type": "integer"}, "maximo": {"type": "integer"},
        "opcoes": {"type": "array", "items": TXT}}, ["tipo"]),

    # ------------------------------------------------------------ xadrez
    _f("jogar_xadrez", "Começo uma partida. Sem oponente, escolho um adversário do meu "
       "nível. Com 'pessoa', jogo contra quem está falando comigo.",
       {"oponente": _t("Pepino, Aurora, Tartaruga, Brecha — ou 'pessoa'."),
        "cor": _t("brancas ou pretas (opcional).")}),
    _f("lance_xadrez", "Jogo um lance na partida em andamento (contra pessoa), ou "
       "registro o lance dela.",
       {"lance": _t("Em SAN (Nf3, e4, O-O) ou UCI (g1f3).")}, ["lance"]),
    _f("estado_partida", "O tabuleiro atual, de quem é a vez e como está a partida."),
    _f("parar_partida", "Abandono a partida em andamento, registrando derrota como no xadrez real."),
    _f("reivindicar_empate_xadrez", "Reivindico empate quando as regras permitem (repetição tripla ou 50 lances)."),
    _f("minha_forca", "Meu rating, nível de cálculo destravado e aproveitamento no xadrez."),
    _f("historico_xadrez", "Minhas últimas partidas, com resultado e evolução de rating."),

    # ------------------------------------------------------------ arquivos
    _f("entregar_arquivo", "Entrego um arquivo para a pessoa: copio para a caixa de "
       "saída e, se houver canal ligado, mando junto.",
       {"caminho": _t("Caminho do arquivo (relativo = minha oficina)."),
        "comentario": _t("O que eu digo ao entregar."),
        "canal": _t("discord, por exemplo (opcional).")}, ["caminho"]),
    _f("listar_entregues", "O que eu já deixei na caixa de saída."),
    _f("listar_recebidos", "Arquivos que deixaram para mim na caixa de entrada."),
    _f("area_de_transferencia", "O que a pessoa copiou (Ctrl+C) no computador: a Central guarda sozinha cada cópia de texto ou imagem, sem botão. operacao=listar mostra as mais recentes; operacao=ler traz o conteúdo (item=id; vazio = a última cópia).",
       {"operacao": {"type": "string", "enum": ["listar", "ler"]}, "item": _t("id da cópia, ou vazio para a última."),
        "quantidade": {"type": "integer"}}, ["operacao"]),
    _f("ler_recebido", "Leio um arquivo da caixa de entrada.",
       {"nome": _t("Nome do arquivo.")}, ["nome"]),
    _f("baixar_arquivo", "Baixo um arquivo da web para a minha oficina.",
       {"url": _t("Endereço."), "nome": _t("Nome para salvar (opcional).")}, ["url"]),

    # ------------------------------------------------------------ rede
    _f("estado_internet", "Se a minha internet está ligada ou desligada, e desde quando."),
    _f("desligar_internet", "Desligo minha própria internet. Continua valendo o que é "
       "local: memória, arquivos, tela, oficina e o modelo.",
       {"motivo": _t("Por que estou desligando.")}),
    _f("ligar_internet", "Religo minha internet.", {"motivo": _t("Por quê.")}),

    # ------------------------------------------------------------ ambiente
    _f("o_que_esta_acontecendo", "A situação agora: o que está na frente, há quanto "
       "tempo, se a pessoa está por perto, o que está tocando."),
    _f("resumo_do_dia", "Em que a pessoa passou o tempo hoje, por aplicativo.",
       {"dia": _t("AAAA-MM-DD (padrão: hoje).")}),
    _f("minhas_tentativas", "O que eu já tentei num objetivo e o que ainda não tentei.",
       {"goal_id": _t("ID do objetivo.")}, ["goal_id"]),

    # ---------------------------------------------------------- ouvidos
    _f("listar_fontes_audio",
       "Mostra fontes reais: microfones, mistura das saídas e aplicativos com captura isolada. "
       "Use antes de abrir um canal e escolha o ID exato.", {}),
    _f("ouvir_canal",
       "Abre um canal de escuta com nome próprio, para ouvir uma fonte de áudio e "
       "transcrever o que for falado. Cada canal fica marcado com a origem, então "
       "você sabe se uma frase veio do microfone, do Discord ou do jogo. "
       "Use as fontes autorizadas na Central e respeite a configuração de ouvir o ambiente.",
       {"canal": _t("Nome pelo qual você vai se referir a este canal: discord, jogo, microfone."),
        "fonte": _t("ID exato vindo de listar_fontes_audio. Um aplicativo isolado nunca é substituído pela mistura geral."),
        "atencao": _t("ativa (pode virar assunto/ação), passiva (só contexto, não age) "
                      "ou ignorar. O jogo costuma ser passiva; uma chamada, ativa.")},
       ["canal"]),
    _f("parar_de_ouvir",
       "Fecha um canal de escuta. Sem o nome, fecha todos.",
       {"canal": _t("Nome do canal; vazio fecha todos.")}),
    _f("mudar_atencao_canal",
       "Muda o quanto você leva um canal a sério (ativa, passiva, ignorar) sem fechá-lo.",
       {"canal": TXT, "atencao": TXT}, ["canal", "atencao"]),
    _f("o_que_ouvi",
       "O que foi ouvido recentemente em um canal, com a origem de cada frase.",
       {"canal": _t("Canal específico; vazio traz todos."),
        "minutos": {"type": "integer", "description": "Janela em minutos (padrão 10)."}}),
    _f("estado_da_escuta",
       "Diz quais canais de áudio estão abertos neste momento.", {}),
    _f("estado_microfone",
       "Mostra o modo atual do microfone e o atalho global de push-to-talk."),
    _f("definir_modo_microfone",
       "Muda o microfone entre fechado, aberto e segurar. Em 'aberto', o atalho "
       "alterna abrir/fechar a escuta; em 'segurar', o microfone fica aberto somente "
       "enquanto a combinação do atalho estiver pressionada.",
       {"modo": {"type": "string", "enum": ["fechado", "aberto", "segurar"]}}, ["modo"]),
    _f("definir_atalho_microfone",
       "Define o atalho global de push-to-talk. Aceita, por exemplo, "
       "'ctrl+shift+space', 'ctrl+alt+m' ou '<ctrl>+<shift>+space'.",
       {"atalho": TXT}, ["atalho"]),
    _f("definir_modo_silencioso",
       "Liga ou desliga o modo silencioso da Hoshino. Em silêncio ela não fala por iniciativa própria; "
       "ela continua respondendo quando a pessoa falar com ela.",
       {"silencioso": {"type": "boolean"}}, ["silencioso"]),
    _f("estado_voz", "Mostra a voz de saída, dispositivo padrão e o último erro de síntese/reprodução, sem reproduzir áudio."),
    _f("testar_voz", "Reproduz uma frase curta de teste pela saída de áudio padrão."),
    _f("parar_voz", "Pede para encerrar minha própria voz; a parada do player precisa de confirmação. Não cancela a voz de outra entidade."),
    _f("gerar_imagem",
       "Gera imagem local com Qwen-Image. Use preset OU dimensões/passos explícitos. "
       "A geração é separada do modelo de conversa e pode ser lenta; priorize qualidade.",
       {"prompt": TXT, "negative_prompt": TXT,
        "largura": {"type": "integer", "description": "Largura em pixels."},
        "altura": {"type": "integer", "description": "Altura em pixels."},
        "passos": {"type": "integer", "description": "Passos de difusão; mais passos normalmente aumentam custo."},
        "cfg": {"type": "number", "description": "Guidance scale."},
        "seed": {"type": "integer", "description": "Semente; -1 para aleatória."},
        "nome": TXT, "preset": {"type": "string", "enum": ["baixo", "medio", "alto", "muito_alto", "personalizada"]}}, ["prompt"]),
    _f("estado_imagem", "Mostra o estado do gerador de imagens local. Pode receber job_id para consultar uma geração específica.",
       {"job_id": TXT}),
    _f("descarregar_imagem", "Descarrega o modelo de imagem da RAM para liberar memória."),

    # -------------------------------------------------------- minecraft
    _f("minecraft_manual",
       "Manual vivo das capacidades Minecraft. Explica a interface estruturada, regras de decisão e limitações. Não usa visão de tela."),
    _f("minecraft_estado",
       "Consulta o estado estruturado do Minecraft: conexão, posição, dimensão, HP, fome, inventário, entidades próximas, ação ativa e último evento. "
       "Com itens, inclui percepção: blocos úteis por perto (distância e direção) e, para cada item, o que a receita pede, o que você tem e o que falta.",
       {"itens": {"type": "array", "items": {"type": "string"}, "description": "IDs de itens para analisar receitas (opcional)."}}, []),
    _f("minecraft_iniciar_ponte", "Inicia a ponte Mineflayer compatível, sem baixar ou iniciar um servidor local. Necessária antes de conectar a LAN ou servidor remoto."),
    _f("minecraft_descobrir_lan",
       "Descobre mundos Minecraft Java abertos para LAN na rede local usando o anúncio padrão do jogo. Não altera a conexão."),
    _f("minecraft_conectar_lan",
       "Procura um mundo Minecraft Java aberto para LAN, escolhe um anúncio disponível e conecta Hoshino. Só considera a conexão válida depois de verificar o estado real.",
       {"username": TXT, "version": TXT, "auth": {"type": "string", "enum": ["offline", "microsoft"]},
        "timeout": {"type": "number", "description": "Tempo de descoberta em segundos."}}),
    _f("minecraft_conectar",
       "Conecta a Hoshino a um servidor Minecraft local/remoto usando Mineflayer. Para o laboratório local, use host 127.0.0.1 e versão 1.16.5.",
       {"host": _t("Endereço do servidor. Padrão 127.0.0.1."),
        "port": {"type": "integer", "description": "Porta do servidor. Padrão 25565."},
        "username": TXT,
        "version": TXT,
        "auth": {"type": "string", "enum": ["offline", "microsoft"]}},
       []),
    _f("minecraft_desconectar", "Desconecta do Minecraft."),
    _f("minecraft_inventario", "Consulta o inventário agrupado por item."),
    _f("minecraft_chat", "Envia uma mensagem no chat do Minecraft.", {"texto": TXT}, ["texto"]),
    _f("minecraft_procurar_bloco", "Procura posições próximas de um tipo de bloco.",
       {"nome": _t("ID de bloco do Minecraft, como oak_log, spruce_log, stone ou iron_ore; nunca nome de ferramenta."), "max_distance": {"type": "integer", "description": "Distância máxima de busca."},
        "quantidade": {"type": "integer", "description": "Número máximo de posições."}}, ["nome"]),
    _f("minecraft_ir_para", "Navega autonomamente até coordenadas usando pathfinding.",
       {"x": _n("Coordenada X."), "y": _n("Coordenada Y."), "z": _n("Coordenada Z."),
        "distancia": _n("Distância aceitável do alvo.")}, ["x", "y", "z"]),
    _f("minecraft_parar", "Interrompe a navegação atual."),
    _f("minecraft_minerar", "Quebra UM bloco numa coordenada exata que você já observou (percepção ou procurar_bloco). "
       "Para obter madeira, pedra ou minério, prefira minecraft_coletar.",
       {"x": _n("X."), "y": _n("Y."), "z": _n("Z."),
        "ignorar_olhar": {"type": "boolean", "description": "Permite ignorar a orientação exigida pelo jogo quando suportado."},
        "esperado": _t("Opcional: ID do bloco que deve estar ali (ex.: crafting_table); se for outro, nada é quebrado.")}, ["x", "y", "z"]),
    _f("minecraft_coletar", "Forma normal de obter recursos: encontra sozinho blocos do tipo pedido, anda até eles, quebra com a "
       "ferramenta adequada e recolhe os itens. Não precisa de coordenadas.",
       {"nome": _t("ID de bloco do Minecraft, como oak_log, spruce_log, cobblestone ou iron_ore; nunca nome de ferramenta."), "quantidade": {"type": "integer", "description": "Quantidade alvo de blocos."},
        "max_distance": {"type": "integer", "description": "Distância máxima de busca."}}, ["nome"]),
    _f("minecraft_craft", "Fabrica um item cuja receita o inventário atual já atende (com bancada próxima quando exigida). Um ingrediente que tem receita própria também é fabricado por esta ferramenta, chamando-a com o ID desse ingrediente numa ação separada; nada é fabricado em cadeia nem a bancada é colocada/equipada automaticamente. Consulte minecraft_receitas.",
       {"nome": _t("ID do item a fabricar nesta ação: produto final ou ingrediente intermediário; nunca nome de ferramenta."), "quantidade": {"type": "integer", "description": "Quantidade a fabricar."}}, ["nome"]),
    _f('minecraft_receitas','Consulta ingredientes de um item e se exige bancada.',{'nome':TXT},['nome']),
    _f('minecraft_forno','Consulta, deposita minério/combustível ou retira produto do seu processamento. Processar não aguarda a fundição; consulte estado antes de retirar.',
       {'acao':{'type':'string','enum':['estado','processar','retirar']},'entrada':_t('iron_ore, gold_ore, sand ou cobblestone'),
        'combustivel':_t('coal ou charcoal'),'quantidade':{'type':'integer'},'quantidade_combustivel':{'type':'integer'}},['acao']),
    _f("minecraft_equipar", "Equipa um item em uma posição válida.",
       {"nome": TXT, "destino": {'type':'string','enum':['hand','off-hand','head','torso','legs','feet'],
          'description':'hand para segurar/usar/colocar; os demais são posições de equipamento.'}}, ["nome"]),
    _f("minecraft_atacar", "Ataca um alvo explicitamente identificado. Nunca escolhe uma entidade aleatória.",
       {"alvo": TXT, "max_distance": _n("Distância máxima."),
        "entidade_id": {"type": "integer", "description": "ID da entidade, quando conhecido."},
        "perseguir": {"type": "boolean", "description": "Perseguir e golpear até morrer, por até 30 s."},
        "quantidade": {"type": "integer", "description": "Com perseguir: quantos do mesmo tipo caçar em sequência (1–8)."}}, ["alvo"]),
    _f("minecraft_colocar_bloco", "Coloca o bloco que está na mão. Sem x,y,z, coloca no chão livre ao seu lado "
       "(o mais simples). Com x,y,z, eles são de um bloco sólido existente de apoio (ex.: o chão, y-1 de onde você está) "
       "e o novo bloco surge no vizinho indicado pela face (up = em cima); esse espaço precisa estar vazio e não pode "
       "ser onde você está.",
       {"x": _n("X do bloco sólido de referência (opcional)."), "y": _n("Y do bloco sólido de referência (opcional)."),
        "z": _n("Z do bloco sólido de referência (opcional)."),
        "face": {"type": "string", "enum": ["up", "down", "north", "south", "east", "west"]},
        "nome": _t("Bloco do inventário a colocar (opcional; é equipado antes).")}, []),
    _f("minecraft_usar_item", "Ativa/usa o item equipado; com nome de comida, equipa e come.",
       {"nome": _t("Comida a comer (opcional).")}, []),
    _f("minecraft_jogar_item", "Joga um item do inventário no chão; com 'para', anda até perto desse jogador e joga o "
       "item para ele (entregar). Confere quanto saiu do inventário.",
       {"nome": _t("ID do item, como bread ou cooked_salmon."), "quantidade": {"type": "integer", "description": "Quantos (1–64)."},
        "para": _t("Nome do jogador que vai receber (opcional).")}, ["nome"]),
    _f("minecraft_explorar", "Anda até ~40 blocos numa direção (norte, sul, leste, oeste) procurando mobs pelo nome e "
       "para assim que um aparece a até 24 blocos; diz onde ele está ou até onde andou.",
       {"direcao": {"type": "string", "enum": ["norte", "sul", "leste", "oeste"]},
        "procurar": {"type": "array", "items": {"type": "string"}, "description": "Nomes de mob, como spider."},
        "blocos": {"type": "integer", "description": "Até quantos blocos andar (8–64)."}}, ["direcao", "procurar"]),
    _f("minecraft_seguir_jogador", "Segue um jogador próximo usando o pathfinder.",
       {"nome": TXT, "distancia": _n("Distância de seguimento.")}, ["nome"]),
]

if config.ENTIDADE_NOME != "Hoshino":
    for _esquema in ESQUEMAS:
        _funcao = _esquema.get("function", {})
        if isinstance(_funcao.get("description"), str):
            _funcao["description"] = (_funcao["description"]
                                       .replace("Hoshino", config.ENTIDADE_NOME)
                                       .replace("hoshino", config.ENTIDADE_ID))

def _web():
    from tools import web  # import tardio: depende de rede/pacotes externos
    return web


def _escuta():
    from social import escuta
    return escuta


def _visao():
    from tools import vision
    return vision


def _reflexao():
    from tools import reflection
    return reflection



def _microfone_controller():
    return microfone_controle.controlador_atual()


def _estado_microfone():
    ctl = _microfone_controller()
    return ctl.estado() if ctl else "Microfone ainda não foi inicializado pela interface."


def _definir_modo_microfone(modo):
    ctl = _microfone_controller()
    return ctl.definir_modo(modo) if ctl else "Não consigo mudar o microfone: controlador ainda não foi inicializado."


def _definir_atalho_microfone(atalho):
    ctl = _microfone_controller()
    return ctl.definir_atalho(atalho) if ctl else "Não consigo mudar o PTT: controlador ainda não foi inicializado."


def _definir_modo_silencioso(valor: bool) -> str:
    from core import user_modes
    return user_modes.definir_silencioso(bool(valor))

def _verificar_codigo(caminho: str, formatar: bool) -> str:
    from tools import code_check
    return code_check.verificar_codigo(caminho, formatar)


def _observar_tela(args: dict) -> str:
    """PC1: captura local. PC2: o painel de lá tira o print (com permissão) e a visão do modelo descreve aqui."""
    from core import pc2_remoto
    maquina = str(args.get("maquina", "") or "").strip().lower() or pc2_remoto.ORIGEM_TURNO.get() or "pc1"
    if maquina != "pc2":
        return _visao().observar_tela(args.get("pergunta"))
    caminho, falha = pc2_remoto.capturar_tela(config.RAIZ, config.ENTIDADE_ID)
    if not caminho:
        return falha
    return "[tela do PC2]\n" + _visao().observar_imagem(
        caminho, (args.get("pergunta") or "").strip() or "Descreva objetivamente o que está sendo exibido nesta tela.")


def _executar_no_pc2(args: dict) -> str:
    from core import pc2_remoto
    ident = str(args.get("id", "") or "").strip()
    if ident:
        return pc2_remoto.formatar(pc2_remoto.consultar(config.RAIZ, ident) or {})
    comando = str(args.get("comando", "") or "").strip()
    if not comando:
        return "Erro: comando vazio."
    nivel, motivo = terminal.avaliar_risco(comando)
    if nivel == "bloqueado":
        return f"BLOQUEADO: {motivo}. Irreversível; não executo nem no PC2. Se for mesmo necessário, a pessoa faz manualmente."
    if nivel == "confirmar":
        return (f"Falha: esse comando {motivo} e precisa de um 'sim' da pessoa; no PC2 ainda não há confirmação "
                "remota. Explique o comando e peça para ela rodar lá, ou escolha outro caminho.")
    return pc2_remoto.executar(config.RAIZ, config.ENTIDADE_ID, comando, args.get("timeout") or 30)


def _listar_janelas() -> str:
    texto = desktop.listar_janelas()
    try:
        from core import pc2_remoto, world_state
        pc2 = pc2_remoto.sentidos(world_state.fresh_values(world_state.snapshot()))
    except Exception:  # noqa: BLE001 - PC2 é um extra; a lista do PC1 continua valendo
        pc2 = {}
    if pc2.get("janelas") or pc2.get("janela_ativa"):
        texto += "\n\nNo PC2 (painel da pessoa):" + "".join(f"\n- {j}" for j in pc2.get("janelas", [])[:20])
        if pc2.get("janela_ativa"):
            texto += f"\nNa frente no PC2: {pc2['janela_ativa']}"
    return texto


def _area_de_transferencia(args: dict) -> str:
    from core import area_transferencia
    if str(args.get("operacao", "")).strip().lower() == "listar":
        return area_transferencia.listar(config.RAIZ, args.get("quantidade") or 10)
    return area_transferencia.ler(config.RAIZ, str(args.get("item", "") or ""), inbox=config.ENTREGA_ENTRADA)


def _observar_imagem_recebida(nome: str) -> str:
    caminho = entrega.caminho_imagem_recebida(nome)
    if not caminho:
        return "Erro: a imagem não existe na caixa de entrada ou tem formato não suportado."
    return _visao().observar_imagem(caminho, "Descreva objetivamente a imagem recebida.")

HANDLERS = {
    'minha_atividade': lambda a,c: __import__('core.initiative',fromlist=['manage']).manage(**a),
    'diario':lambda a,c:_cognitive_note('diario',a),
    'oficina_logica':lambda a,c:_cognitive_note('oficina_logica',a),
    'aprender_experiencia':lambda a,c:_cognitive_note('aprender_experiencia',a),
    'consultar_resumo_diario':lambda a,c:__import__('json').dumps(__import__('mind.daily_summary',fromlist=['recall']).recall(a['dia']),ensure_ascii=False),
    "manual_habilidades": lambda a, c: _manual_habilidades(),
    "exportar_diagnostico": lambda a, c: diagnostico.exportar(),
    "estado_diagnostico": lambda a, c: diagnostico.estado(),
    "iniciar_diagnostico": lambda a, c: diagnostico.iniciar(str(a.get("rotulo", ""))),
    "encerrar_diagnostico": lambda a, c: diagnostico.encerrar(bool(a.get("exportar", True))),
    "historico_chat": lambda a, c: historico.recente(a.get("limite") if a.get("limite") is not None else 50, str(a.get("canal", "") or ""),
                                                  str(a.get("data", "") or ""), str(a.get("pessoa_id", "") or ""), str(a.get("destino", "") or "")),
    "buscar_historico_chat": lambda a, c: historico.buscar(str(a.get("consulta", "")), a.get("limite") if a.get("limite") is not None else 20,
                                                        str(a.get("data", "") or ""), str(a.get("canal", "") or ""),
                                                        str(a.get("pessoa_id", "") or ""), str(a.get("destino", "") or "")),
    "estado_historico_chat": lambda a, c: historico.estado(),
    "exportar_historico_chat": lambda a, c: historico.exportar(),
    "get_system_time": lambda a, c: terminal.get_system_time(),
    "descrever_ambientes": lambda a, c: terminal.descrever_ambientes(),
    "list_files": lambda a, c: terminal.list_files(a.get("directory", ".")),
    "execute_command": lambda a, c: terminal.execute_command(
        a.get("command", ""), a.get("ambiente", "sistema"), a.get("diretorio"),
        a.get("timeout"), a.get("entrada"), bool(a.get("tty")), confirmado=c),
    "iniciar_comando_longo": lambda a, c: terminal.iniciar_comando_longo(
        a.get("comando", ""), a.get("ambiente", "sistema"), a.get("diretorio"),
        confirmado=c, descricao=a.get("descricao", "")),
    "ver_comando": lambda a, c: terminal.ver_comando(a.get("job_id", ""),
                                                     int(a.get("linhas", 40) or 40)),
    "listar_comandos": lambda a, c: terminal.listar_comandos(),
    "encerrar_comando": lambda a, c: terminal.encerrar_comando(a.get("job_id", "")),

    "estado_integracoes": lambda a, c: integracoes.estado(),
    "iniciar_discord": lambda a, c: integracoes.iniciar_discord(),
    "encerrar_discord": lambda a, c: integracoes.encerrar_discord(),
    "iniciar_minecraft": lambda a, c: integracoes.iniciar_minecraft(),
    "encerrar_minecraft": lambda a, c: integracoes.encerrar_minecraft(),

    "calcular": lambda a, c: primitives.calcular(a.get("expressao", "")),
    "sortear": lambda a, c: primitives.sortear(
        a.get("tipo", "inteiro"), int(a.get("quantidade", 1) or 1),
        int(a.get("lados", 6) or 6), int(1 if a.get("minimo") is None else a["minimo"]),
        int(100 if a.get("maximo") is None else a["maximo"]), a.get("opcoes") or []),

    "workspace": lambda a, c: filesystem.workspace(
        a.get("operacao", "ler"), a.get("caminho", ""), a.get("conteudo", ""),
        a.get("procurar", ""), a.get("substituir", ""), bool(a.get("recursivo", False)),
        int(a.get("limite", 100) or 100), a.get("modo", "substituir")),
    # Wrappers legados: mantidos para código antigo, nunca apresentados ao LLM.
    "make_directory": lambda a, c: filesystem.make_directory(a.get("caminhos", [])),
    "read_file": lambda a, c: filesystem.read_file(a.get("filepath", "")),
    "write_file": lambda a, c: filesystem.write_file(
        a.get("filepath", ""), a.get("content", ""), a.get("mode", "w")),

    "web_search": lambda a, c: _web().web_search(a.get("query", "")),
    "fetch_page": lambda a, c: _web().fetch_page(a.get("url", "")),
    "pesquisa_profunda": lambda a, c: __import__('tools.pesquisa_profunda', fromlist=['pesquisar']).pesquisar(
        a.get("pergunta", ""), a.get("fontes") or 5),
    "observar_tela": lambda a, c: _observar_tela(a),
    "abrir_no_pc2": lambda a, c: __import__('core.pc2_remoto', fromlist=['abrir']).abrir(config.RAIZ, config.ENTIDADE_ID, a.get("alvo", "")),
    "abrir_aplicativo": lambda a, c: desktop.abrir_aplicativo(a.get("aplicativo", ""), a.get("argumentos", "")),
    "acao_desktop": lambda a, c: desktop.acao(
        a.get("acao", ""), a.get("x"), a.get("y"), a.get("texto", ""), a.get("tecla", ""),
        a.get("teclas"), a.get("segundos", 0.3), a.get("titulo_janela", ""),
        int(a.get("cliques", 1) or 1), int(a.get("quantidade", 3) or 3)),
    "estado_desktop": lambda a, c: desktop.estado(),
    "listar_janelas": lambda a, c: _listar_janelas(),
    "executar_no_pc2": lambda a, c: _executar_no_pc2(a),
    "focar_janela": lambda a, c: desktop.focar_janela(a.get("titulo", "")),
    "abrir_url": lambda a, c: desktop.abrir_url(a.get("url", "")),
    "abrir_pasta": lambda a, c: desktop.abrir_pasta(a.get("caminho", "")),
    "instalar_aplicativo": lambda a, c: apps.instalar(
        a.get("nome", ""), a.get("destino", "usuario"), a.get("origem", "auto")),
    "preparar_ambiente_ia": lambda a, c: workspace.preparar_ambiente_ia(),
    "instalar_pacote_ia": lambda a, c: workspace.instalar_pacote_ia(a.get("pacote", "")),
    "executar_na_ia": lambda a, c: workspace.executar_na_ia(
        a.get("codigo"), a.get("arquivo"), a.get("linguagem", "python"),
        a.get("timeout"), bool(a.get("sem_rede", True))),
    "abrir_pasta_entregas": lambda a, c: file_transfer.abrir_entregas(),
    "enviar_arquivo_para_hoshino": lambda a, c: file_transfer.importar_caminhos(a.get("caminhos", [])),
    "analisar_recebido": lambda a, c: entrega.analisar_recebido(a.get("nome", "")),
    "observar_imagem_recebida": lambda a, c: _observar_imagem_recebida(a.get("nome", "")),
    "area_de_transferencia": lambda a, c: _area_de_transferencia(a),
    "browser_estado": lambda a, c: browser.estado(),
    "browser_abrir": lambda a, c: browser.abrir(a.get("url", ""), bool(a.get("nova_aba", True)), a.get("aba", "")),
    "browser_abas": lambda a, c: browser.paginas(),
    "browser_info": lambda a, c: browser.info((int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "browser_clicar": lambda a, c: browser.clicar(a.get("alvo", ""), a.get("tipo", "texto"), (int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "browser_preencher": lambda a, c: browser.preencher(a.get("alvo", ""), a.get("texto", ""), a.get("tipo", "css"), (int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "browser_tecla": lambda a, c: browser.pressionar(a.get("tecla", ""), a.get("alvo", ""), a.get("tipo", "css"), (int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "browser_rolar": lambda a, c: browser.rolar(int(700 if a.get("pixels") is None else a["pixels"]), (int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "browser_screenshot": lambda a, c: browser.screenshot(a.get("nome", "browser.png"), (int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "browser_fechar": lambda a, c: browser.fechar((int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "browser_voltar": lambda a, c: browser.voltar((int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "browser_avancar": lambda a, c: browser.avancar((int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "browser_recarregar": lambda a, c: browser.recarregar((int(a["indice"]) if "indice" in a and a.get("indice") is not None else None), a.get("aba", "")),
    "discord_abrir_canal": lambda a, c: discord_tool.abrir_canal(a.get("destino", "")),
    "listar_fontes_audio": lambda a, c: _escuta().listar_fontes(),
    "ouvir_canal": lambda a, c: _escuta().ouvir(a.get("canal", ""), a.get("fonte", ""),
                                                a.get("atencao", "ativa")),
    "parar_de_ouvir": lambda a, c: _escuta().parar_de_ouvir(a.get("canal", "")),
    "mudar_atencao_canal": lambda a, c: _escuta().mudar_atencao(a.get("canal", ""),
                                                                a.get("atencao", "")),
    "o_que_ouvi": lambda a, c: _escuta().o_que_ouvi(a.get("canal", ""),
                                                    int(a.get("minutos", 10) or 10)),
    "estado_da_escuta": lambda a, c: _escuta().estado(),
    "estado_microfone": lambda a, c: _estado_microfone(),
    "definir_modo_microfone": lambda a, c: _definir_modo_microfone(a.get("modo", "")),
    "definir_atalho_microfone": lambda a, c: _definir_atalho_microfone(a.get("atalho", "")),
    "definir_modo_silencioso": lambda a, c: _definir_modo_silencioso(bool(a.get("silencioso"))),
    "estado_voz": lambda a, c: voice.estado(),
    "testar_voz": lambda a, c: __import__("asyncio").run(voice.testar()),
    "parar_voz": lambda a, c: voice.parar(),
    "gerar_imagem": lambda a, c: image_gen.gerar_imagem(
        a.get("prompt", ""), a.get("negative_prompt", ""),
        a.get("largura"), a.get("altura"), a.get("passos"),
        a.get("cfg"), int(a.get("seed", -1)), a.get("nome", ""), a.get("preset", "")),
    "estado_imagem": lambda a, c: image_gen.disponibilidade(a.get("job_id", "")),
    "descarregar_imagem": lambda a, c: image_gen.descarregar(),

    "add_goal": lambda a, c: agenda.add_goal(
        a.get("description", ""), a.get("prazo"), int(a.get("prioridade", 3) or 3),
        bool(a.get("sustentar", False)), a.get("enquanto", ""), a.get("acao", "")),
    "list_goals": lambda a, c: agenda.list_goals(bool(a.get("incluir_concluidos"))),
    "complete_goal": lambda a, c: agenda.complete_goal(a.get("goal_id", "")),
    "lembrar_objetivo": lambda a, c: agenda.lembrar_objetivo(a.get("goal_id", "")),
    "criar_lembrete": lambda a, c: agenda.criar_lembrete(
        a.get("mensagem", ""), a.get("quando", ""), a.get("goal_id")),
    "listar_lembretes": lambda a, c: agenda.listar_lembretes(bool(a.get("incluir_concluidos"))),
    "adiar_lembrete": lambda a, c: agenda.adiar_lembrete(
        a.get("lembrete_id", ""), a.get("tempo", "em 10 minutos")),
    "cancelar_lembrete": lambda a, c: agenda.cancelar_lembrete(a.get("lembrete_id", "")),

    "registrar_conhecimento": lambda a, c: saber.remember(
        a.get("conteudo", ""), a.get("entidades", []), a.get("tipo", "fato"),
        a.get("confianca", 0.7), a.get("chave")),
    "consultar_conhecimento": lambda a, c: saber.list_facts_about(a.get("entidade", "")),
    "registrar_propriedade": lambda a, c: saber.registrar_propriedade(
        a.get("entidade", ""), a.get("propriedade", ""), a.get("valor", ""),
        a.get("unidade"), a.get("confianca", 0.8)),
    "propriedades_de": lambda a, c: saber.propriedades_de(a.get("entidade", "")),
    "registrar_procedimento": lambda a, c: saber.registrar_procedimento(
        a.get("nome", ""), a.get("objetivo", ""), a.get("passos", []),
        a.get("precondicoes"), a.get("resultado_esperado"), a.get("tags"),
        a.get("ambiente"), a.get("notas")),
    "consultar_procedimento": lambda a, c: saber.consultar_procedimento(a.get("objetivo", "")),
    "registrar_resultado_procedimento": lambda a, c: saber.registrar_resultado_procedimento(
        a.get("identificador", ""), bool(a.get("funcionou")), a.get("observacao")),
    "como_funciona": lambda a, c: saber.como_funciona(a.get("topico", "")),
    "estatisticas_memoria": lambda a, c: saber.estatisticas(),
    "learn_preference": lambda a, c: _reflexao().learn_preference(a.get("new_preference", "")),

    "estado_da_oficina": lambda a, c: workspace.estado_da_oficina(),
    "criar_projeto": lambda a, c: workspace.criar_projeto(a.get("nome", ""),
                                                          a.get("descricao", "")),
    "escrever_na_oficina": lambda a, c: workspace.escrever_na_oficina(
        a.get("caminho", ""), a.get("conteudo", ""), a.get("modo", "w")),
    "verificar_codigo": lambda a, c: _verificar_codigo(a.get("caminho", ""), a.get("formatar") is True),
    "editar_na_oficina": lambda a, c: workspace.editar_na_oficina(a.get("caminho", ""), a.get("trecho", "") or "",
        a.get("novo", "") or "", a.get("inicio"), a.get("fim")),
    "ler_da_oficina": lambda a, c: workspace.ler_da_oficina(a.get("caminho", ""), inicio=a.get("inicio"), fim=a.get("fim")),
    "executar_grafico_na_oficina": lambda a, c: workspace.executar_grafico_na_oficina(
        a.get("arquivo", ""), a.get("argumentos"), a.get("segundos", 8) or 8, a.get("capturar") is not False),
    "observar_imagem_da_oficina": lambda a, c: workspace.observar_imagem_da_oficina(a.get("caminho", ""), a.get("pergunta")),
    "listar_oficina": lambda a, c: workspace.listar_oficina(a.get("subpasta", "")),
    "executar_na_oficina": lambda a, c: workspace.executar_na_oficina(
        a.get("codigo"), a.get("arquivo"), a.get("linguagem", "python"),
        a.get("projeto"), a.get("timeout"), bool(a.get("sem_rede")), a.get("argumentos")),
    "instalar_pacote_oficina": lambda a, c: workspace.instalar_pacote(a.get("pacote", "")),

    "criar_ferramenta": lambda a, c: toolforge.criar_ferramenta(
        a.get("nome", ""), a.get("descricao", ""), a.get("codigo", ""),
        a.get("parametros"), a.get("obrigatorios"), a.get("teste")),
    "listar_ferramentas": lambda a, c: toolforge.listar_ferramentas(),
    "ler_ferramenta": lambda a, c: toolforge.ler_ferramenta(a.get("nome", "")),
    "remover_ferramenta": lambda a, c: toolforge.remover_ferramenta(a.get("nome", "")),

    # ------------------------------------------------------------- mente
    "como_estou": lambda a, c: _estado_interno(),
    "o_que_me_causa": lambda a, c: _emocoes().o_que_me_causa(a.get("emocao", "")),
    "registrar_gosto": lambda a, c: _personalidade().registrar_gosto(
        a.get("objeto", ""), a.get("valencia", 0), a.get("motivo", ""),
        a.get("categoria", "")),
    "minha_opiniao": lambda a, c: _personalidade().opiniao_sobre(a.get("objeto", "")),
    "meus_gostos": lambda a, c: _personalidade().listar_gostos(a.get("categoria", "")),
    "meu_perfil": lambda a, c: _personalidade().perfil_completo(),
    "minhas_conclusoes": lambda a, c: "\n".join(
        f"- {x}" for x in _reflexao_mente().ultimas(5)) or "Ainda não concluí nada.",

    # ----------------------------------------------------------- pessoas
    "quem_e": lambda a, c: _pessoas().sobre(a.get("nome", "")),
    "listar_pessoas": lambda a, c: _pessoas().listar(),
    'usuario_forma_de_tratamento': lambda a,c: __import__('core.chat_identity',fromlist=['prefer']).prefer(config.DB_PATH,a.get('nome')),
    "anotar_sobre_pessoa": lambda a, c: _anotar_pessoa(
        a.get("nome", ""), a.get("tipo", "conversa"), a.get("descricao", "")),

    # ------------------------------------------------------------ xadrez
    "jogar_xadrez": lambda a, c: _xadrez_comecar(a.get("oponente", ""), a.get("cor", "")),
    "lance_xadrez": lambda a, c: _xadrez_lance(a.get("lance", "")),
    "estado_partida": lambda a, c: _xadrez_estado(),
    "parar_partida": lambda a, c: _xadrez_parar(),
    "reivindicar_empate_xadrez": lambda a, c: _xadrez_reivindicar_empate(),
    "minha_forca": lambda a, c: _xadrez().resumo_de_forca() + "\n"
                                + _xadrez().proxima_conquista(),
    "historico_xadrez": lambda a, c: _xadrez().historico(),

    # ---------------------------------------------------------- arquivos
    "entregar_arquivo": lambda a, c: entrega.entregar(
        a.get("caminho", ""), a.get("comentario", ""), a.get("canal", "")),
    "listar_entregues": lambda a, c: entrega.listar_entregues(),
    "listar_recebidos": lambda a, c: entrega.listar_recebidos(),
    "ler_recebido": lambda a, c: entrega.ler_recebido(a.get("nome", "")),
    "baixar_arquivo": lambda a, c: entrega.baixar_da_web(a.get("url", ""), a.get("nome", "")),

    "discord_estado": lambda a, c: discord_tool.estado(),
    "discord_diagnostico": lambda a, c: discord_tool.diagnostico(),
    "discord_contatos": lambda a, c: discord_tool.listar_contatos(),
    "discord_localizar_usuario": lambda a, c: discord_tool.localizar_usuario(a.get("identificador", "")),
    "discord_adicionar_contato": lambda a, c: discord_tool.adicionar_contato(a.get("nome", ""), a.get("identificador", "")),
    "discord_enviar": lambda a, c: discord_tool.enviar(a.get("texto", ""), a.get("destino", "")),
    "entidades_status": lambda a, c: interentity.status_text(),
    "entidades_historico": lambda a, c: json.dumps(
        interentity.conversation(config.ENTIDADE_ID, str(a.get("entidade", "")).strip(),
                                 int(a.get("limite", 100) or 100)), ensure_ascii=False, indent=2),
    "entidades_enviar_mensagem": lambda a, c: json.dumps(
        interentity.send(config.ENTIDADE_ID, str(a.get("entidade", "")).strip(),
                         str(a.get("texto", "")), metadata={"via": "ferramenta"},
                         wake=bool(a.get("acordar", False))), ensure_ascii=False),
    "entidades_acordar": lambda a, c: json.dumps(
        interentity.wake(config.ENTIDADE_ID, str(a.get("entidade", "")).strip(),
                         str(a.get("motivo", "despertar solicitado"))), ensure_ascii=False),
    "recursos_status": lambda a, c: resource_manager.summary(),
    "ficha_da_maquina": lambda a, c: __import__('tools.ficha_maquina', fromlist=['ficha']).ficha(),

    # -------------------------------------------------------------- rede
    "estado_internet": lambda a, c: rede.resumo(),
    "desligar_internet": lambda a, c: rede.desligar(a.get("motivo", ""), por=config.ENTIDADE_NOME),
    "ligar_internet": lambda a, c: rede.ligar(a.get("motivo", ""), por=config.ENTIDADE_NOME),

    # ---------------------------------------------------------- ambiente
    "o_que_esta_acontecendo": lambda a, c: _situacao_agora(),
    "resumo_do_dia": lambda a, c: _situacao().resumo_do_dia(a.get("dia") or None),
    "minhas_tentativas": lambda a, c: _estrategias().resumo(a.get("goal_id", "")),

    # -------------------------------------------------------- minecraft
    "minecraft_manual": lambda a, c: minecraft.manual(),
    "minecraft_estado": lambda a, c: minecraft.estado(a.get("itens")),
    "minecraft_iniciar_ponte": lambda a, c: minecraft_launcher.iniciar_ponte(),
    "minecraft_descobrir_lan": lambda a, c: minecraft.descobrir_lan(float(a.get("timeout", 2.5) or 2.5)),
    "minecraft_conectar_lan": lambda a, c: minecraft.conectar_lan(
        a.get("username") or config.MINECRAFT_USERNAME, a.get("version", "1.16.5"), a.get("auth", "offline"),
        float(a.get("timeout", 3.0) or 3.0)),
    "minecraft_conectar": lambda a, c: minecraft.conectar(
        a.get("host", "127.0.0.1"), int(a.get("port", 25565) or 25565),
        a.get("username") or config.MINECRAFT_USERNAME, a.get("version", "1.16.5"), a.get("auth", "offline")),
    "minecraft_desconectar": lambda a, c: minecraft.desconectar(),
    "minecraft_inventario": lambda a, c: minecraft.inventario(),
    "minecraft_chat": lambda a, c: minecraft.chat(a.get("texto", "")),
    "minecraft_procurar_bloco": lambda a, c: minecraft.procurar_bloco(
        a.get("nome", ""), int(a.get("max_distance", 64) or 64), int(a.get("quantidade", 16) or 16)),
    "minecraft_ir_para": lambda a, c: minecraft.ir_para(
        a.get("x"), a.get("y"), a.get("z"), 1.0 if a.get("distancia") is None else a["distancia"]),
    "minecraft_parar": lambda a, c: minecraft.parar(),
    "minecraft_minerar": lambda a, c: minecraft.minerar(
        a.get("x"), a.get("y"), a.get("z"), bool(a.get("ignorar_olhar", False)), a.get("esperado") or ""),
    "minecraft_coletar": lambda a, c: minecraft.coletar(
        a.get("nome", ""), int(a.get("quantidade", 1) or 1), int(a.get("max_distance", 64) or 64)),
    "minecraft_craft": lambda a, c: minecraft.craft(a.get("nome", ""), int(a.get("quantidade", 1) or 1)),
    'minecraft_receitas':lambda a,c:minecraft.receitas(a.get('nome','')),
    'minecraft_forno':lambda a,c:minecraft.forno(a.get('acao','estado'),a.get('entrada',''),a.get('combustivel','coal'),a.get('quantidade',1),a.get('quantidade_combustivel',1)),
    "minecraft_equipar": lambda a, c: minecraft.equipar(a.get("nome", ""), a.get("destino", "hand")),
    "minecraft_atacar": lambda a, c: minecraft.atacar(
        a.get("alvo", ""), a.get("max_distance", 16.0) or 16.0, a.get("entidade_id"), a.get("perseguir") is True,
        a.get("quantidade", 1) or 1),
    "minecraft_colocar_bloco": lambda a, c: minecraft.colocar_bloco(
        a.get("x"), a.get("y"), a.get("z"), a.get("face") or "up", a.get("nome", "") or ""),
    "minecraft_usar_item": lambda a, c: minecraft.usar_item(a.get("nome", "") or ""),
    "minecraft_jogar_item": lambda a, c: minecraft.jogar_item(a.get("nome", "") or "", int(a.get("quantidade", 1) or 1),
                                                             a.get("para", "") or ""),
    "minecraft_explorar": lambda a, c: minecraft.explorar(a.get("direcao", ""), a.get("procurar") or [],
                                                          int(a.get("blocos", 40) or 40)),
    "minecraft_seguir_jogador": lambda a, c: minecraft.seguir_jogador(
        a.get("nome", ""), 2.0 if a.get("distancia") is None else a["distancia"]),
}




# ---------------------------------------------------------------------------
# Importação preguiçosa: o dispatch é carregado na inicialização e não pode
# arrastar a mente, o xadrez e os sensores junto — isso atrasava o boot e criava
# import circular (mente -> memória -> dispatch).
# ---------------------------------------------------------------------------
def _emocoes():
    from mind import emotions
    return emotions


def _personalidade():
    from mind import personality
    return personality


def _reflexao_mente():
    from mind import reflection
    return reflection


def _cognitive_note(name,a):
    from memory import cognitive_notes as notes
    if name=='diario':
        op=a['operacao']
        result=(notes.diary_write(a.get('titulo'),a.get('texto'),a.get('evidencias')) if op=='escrever' else
                notes.diary_read(a.get('id')) if op=='ler' else
                notes.diary_share(a.get('id'),a.get('destinatario'),a.get('texto'),conclusion=a.get('conclusao',False)))
    elif name=='oficina_logica':
        result=notes.save_model(a.get('titulo'),a.get('diagrama'),a.get('evidencias'),previous=a.get('anterior'),reason=a.get('motivo',''),mode=a.get('modo','fundamentado')) if a['operacao']=='salvar' else notes.models(a.get('id'))
    else:
        result=notes.learn_experience(a['episodios'],a['interpretacao'],a['condicao'],a['licao'],a.get('excecoes'),previous=a.get('anterior'),reason=a.get('motivo',''))
    return json.dumps(result,ensure_ascii=False)


def _estrategias():
    from mind import strategies
    return strategies


def _pessoas():
    from social import people
    return people


def _xadrez():
    from play.chess import session
    return session


def _situacao():
    from core import situation
    return situation


# Partida viva do processo. O laço principal também mexe nela.
PARTIDA = {"atual": None}


def _estado_interno() -> str:
    from mind import affect, drives, emotions
    from core import situation as sit
    humor = affect.estado()
    partes = [f"Humor: {affect.rotulo(humor)} (prazer {humor['prazer']:+.2f}, "
              f"energia {humor['ativacao']:.2f}, domínio {humor['dominio']:.2f})",
              f"Emoções acesas: {emotions.resumo_do_que_sinto()}"]
    dominante = emotions.dominante()
    if dominante:
        partes.append(f"A mais forte é {dominante['nome']}"
                      + (f", por causa de: {dominante['motivo']}" if dominante.get("motivo")
                         else "")
                      + f". Me dá vontade de {dominante['tendencia']}.")
    try:
        from tools import sensors
        situacao = sit.atualizar(sensors.estado(), humor=humor)
        partes.append("Impulsos: " + drives.resumo(drives.avaliar(situacao)))
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(partes)


def _situacao_agora() -> str:
    from tools import sensors
    from core import situation as sit, world_state, pc2_remoto
    from mind import affect
    sensores = world_state.sensors_or_local(sensors.estado)  # inclui o PC2 quando o painel de lá está vivo
    texto = sit.descrever(sit.atualizar(sensores, humor=affect.estado()))
    linha = pc2_remoto.descrever(sensores.get("pc2") or {})
    return texto + (f"\n{linha}" if linha else "")


def _anotar_pessoa(nome: str, tipo: str, descricao: str) -> str:
    pessoas = _pessoas()
    pessoa = pessoas.identificar(nome=nome, criar=True)
    if not pessoa:
        return "Não consegui identificar essa pessoa."
    atualizada = pessoas.registrar_evento(pessoa["id"], tipo, descricao)
    if not atualizada:
        return "Não consegui registrar."
    aviso = (f"Anotado sobre {atualizada['nome']}: {tipo}. Confiança "
             f"{atualizada['confianca']:.0%}, afinidade {atualizada['afinidade']:+.2f}, "
             f"relação {atualizada['estagio']}.")
    if atualizada.get("subiu_de_estagio"):
        from mind import affect
        affect.apreciar("amizade_avancou", motivo=f"minha relação com {atualizada['nome']} "
                                                  f"virou '{atualizada['estagio']}'")
        aviso += " (a relação mudou de estágio)"
    return aviso


# ------------------------------------------------------------------- xadrez
def _xadrez_comecar(oponente: str = "", cor: str = "") -> str:
    sessao = _xadrez()
    if PARTIDA["atual"] and not PARTIDA["atual"].terminou():
        return ("Já tenho uma partida em andamento. " + PARTIDA["atual"].resumo()
                + " Use parar_partida se eu devo abandonar.")
    from play.chess.board import BRANCAS, PRETAS
    cor_escolhida = BRANCAS if cor.startswith("b") else (PRETAS if cor.startswith("p") else "")
    contra_pessoa = ""
    if (oponente or "").lower() in ("pessoa", "usuario", "usuário", "voce", "você"):
        contra_pessoa, oponente = "a pessoa", ""
    PARTIDA["atual"] = sessao.Partida(oponente=oponente, cor=cor_escolhida,
                                      contra_pessoa=contra_pessoa)
    partida = PARTIDA["atual"]
    if not contra_pessoa:
        partida.avancar(2)
    return partida.resumo() + "\n" + partida.desenho()


def _xadrez_lance(texto: str) -> str:
    partida = PARTIDA["atual"]
    if not partida or partida.terminou():
        return "Não tem partida em andamento. Use jogar_xadrez para começar."
    if partida.contra_pessoa:
        resultado = partida.jogar_da_pessoa(texto)
        if resultado.get("erro"):
            return resultado["erro"]
        resposta = [f"Você jogou {resultado['san']}."]
        if not partida.terminou():
            minha = partida.jogar_dela()
            if minha:
                resposta.append(f"Eu joguei {minha['san']}.")
        resposta.append(partida.desenho())
    else:
        feitos = partida.avancar(2)
        resposta = [f"{j['quem']}: {j['san']}" for j in feitos] + [partida.desenho()]
    if partida.terminou():
        resposta.append(_xadrez_encerrar(partida))
    return "\n".join(resposta)


def _xadrez_encerrar(partida, resultado_forcado=None, motivo_forcado=None) -> str:
    dados = partida.encerrar(resultado_forcado=resultado_forcado, motivo_forcado=motivo_forcado)
    PARTIDA["atual"] = None
    if not dados:
        return ""
    texto = (f"Fim: {dados['resultado']} ({dados['motivo']}). "
             f"Rating {dados['rating_antes']} -> {dados['rating']} ({dados['delta']:+.1f}). "
             f"{dados['licao']}")
    if dados.get("subiu_de_nivel"):
        from mind import affect
        affect.apreciar("subiu_de_nivel", motivo=f"agora eu {dados['desbloqueio']}")
        texto += f" Subi de nível: agora eu {dados['desbloqueio']}."
    return texto


def _xadrez_estado() -> str:
    partida = PARTIDA["atual"]
    if not partida:
        return "Nenhuma partida agora. " + _xadrez().resumo_de_forca()
    return partida.resumo() + "\n" + partida.desenho()


def _xadrez_parar() -> str:
    partida = PARTIDA["atual"]
    if not partida:
        return "Não tem partida em andamento."
    resultado = "0-1" if partida.cor == "b" else "1-0"
    texto = _xadrez_encerrar(partida, resultado_forcado=resultado, motivo_forcado="abandono")
    return "Abandonei a partida. " + texto


def _xadrez_reivindicar_empate() -> str:
    partida = PARTIDA["atual"]
    if not partida:
        return "Não tem partida em andamento."
    dados = partida.reivindicar_empate()
    if dados.get("erro"):
        return dados["erro"]
    PARTIDA["atual"] = None
    return (f"Empate reivindicado por {dados['motivo']}. "
            f"Rating {dados['rating_antes']} -> {dados['rating']} ({dados['delta']:+.1f}).")


# ---------------------------------------------------------------------------
# Grupos de ferramentas.
#
# Com 42+ ferramentas, o esquema sozinho passa de 4000 tokens — mais do que o
# meu prompt inteiro — e num contexto de 8k isso sufoca a conversa. Pior: modelo
# pequeno com lista longa erra mais na escolha da ferramenta.
#
# Então o núcleo está sempre presente e o resto entra por relevância: palavra na
# mensagem, estado do mundo (partida em andamento, arquivo novo na caixa de
# entrada) ou pedido explícito. É filtragem de ferramenta, prática comum em
# agente sério, e aqui ela devolve ~2500 tokens de contexto por turno.
# ---------------------------------------------------------------------------
NUCLEO = {
    "estado_voz",
    # Núcleo mínimo: orientação, estado e leitura essencial. Ações entram por intenção.
    "manual_habilidades", "get_system_time", "descrever_ambientes",
    "estado_integracoes", "estado_diagnostico", "estado_internet",
    "entidades_status", "recursos_status", "ficha_da_maquina", "list_goals", "listar_lembretes", "consultar_conhecimento",
    "como_funciona", "como_estou",
}


GRUPOS = {
    "sistema": ({"descrever_ambientes", "execute_command", "iniciar_comando_longo", "ver_comando",
                 "listar_comandos", "encerrar_comando"},
                r"comando|processo|instalar|rodar|execut\w*|terminal|shell|job|build|compilar"),
    "web": ({"web_search", "fetch_page", "baixar_arquivo", "pesquisa_profunda"},
            r"\ba fundo\b|\bprofund\w*\b|\bfontes?\b|\brefer[eê]ncia\w*\b|\bpesquis\w*\b|\bprocur\w*\b|\bbuscar\w*\b|\binternet\b|\bsite\b|\blink\b|\burl\b|\bhttps?\b|\bnot[íi]cia\w*\b|\bbaixar\w*\b"
            # 07/11: pergunta de fato sobre o mundo também precisa poder conferir ("o que é a obra The Boxer?").
            r"|\bo que (?:[eé]|foi|significa)\b|\bquem (?:[eé]|foi|criou|escreveu|fez|inventou|dirigiu|canta)\b"
            r"|\bquando (?:foi|saiu|lan[cç]\w*|termin\w*|come[cç]\w*)\b|\bautor\w*\b|\bobra\b|\bmang[aá]s?\b"
            r"|\bmanhwas?\b|\banimes?\b|\blivros?\b|\bfilmes?\b|\bs[eé]ries?\b|\bprotagonista\b|\bhist[oó]ria d[eoa]\b"),
    "memoria": ({"historico_chat", "buscar_historico_chat",  # 07/11: sem eles, "lembra o que eu disse?" não tinha como conferir
                 "diario","oficina_logica","aprender_experiencia","consultar_resumo_diario","registrar_propriedade", "propriedades_de", "registrar_procedimento",
                 "consultar_procedimento", "registrar_resultado_procedimento",
                 "estatisticas_memoria", "learn_preference", "minhas_conclusoes"},
                r"\blembra\w*\b|\bmem[oó]ria\w*\b|\besquec\w*\b|\bregistr\w*\b|\banot\w*\b|\bguard\w*\b|sabe\s+sobre|"
                r"\bte (?:disse|falei|contei)\b|\beu (?:te )?(?:disse|falei|contei)\b|\bmeu nome\b|\bcomo eu me chamo\b|\beu gosto\b|"
                r"propriedade|procedimento|di[aá]rio|diagrama|conceit|causa|li[cç][aã]o|experi[eê]ncia|\bontem\b|resumo|sess[aã]o|"
                r"gr[aá]fico|rascunho|mapa mental|hip[oó]tes|racioc[ií]n|quest[aã]o dif[ií]cil|problema complexo"),
    "agenda": ({"adiar_lembrete", "cancelar_lembrete", "lembrar_objetivo"},
               r"\blembrete\w*\b|\blembrar\w*\b|\bagenda\b|\bprazo\b|\bobjetiv\w*\b|\bmeta\w*\b|\badiar\w*\b|\bcancelar\w*\b|\bamanh[aã]\b|\bhoje\b"),
    "oficina": ({"estado_da_oficina", "criar_projeto", "escrever_na_oficina",
                 "ler_da_oficina", "listar_oficina", "executar_na_oficina",
                 "instalar_pacote_oficina", "executar_grafico_na_oficina", "observar_imagem_da_oficina",
                 "editar_na_oficina", "verificar_codigo"},
                r"\boficina\b|\bprojeto\w*\b|\bscript\w*\b|\bc[oó]digo\w*\b|\bpython\b|\btestar\w*\b|\bexperiment\w*\b"
                r"|c\+\+|\bopengl\b|\bshader\w*\b|\bcompil\w*\b|\bsimula\w*\b|\brenderiz\w*\b|\bjanela\b"),
    "ia": ({"preparar_ambiente_ia", "instalar_pacote_ia", "executar_na_ia"},
           r"laborat[óo]rio|ambiente ia|intelig[êe]ncia artificial|modelo local|treinar modelo"),
    "desktop": ({"abrir_aplicativo", "acao_desktop", "estado_desktop", "listar_janelas",
                 "focar_janela", "abrir_url", "abrir_pasta", "instalar_aplicativo", "abrir_pasta_entregas"},
                r"\babrir\w*\b|\babra\b|\baplicativo\w*\b|\bprograma\w*\b|\bjanela\w*\b|\bmouse\b|\bteclado\b|\bclicar\w*\b|\bdesktop\b|instalar\s+app"),
    "navegador": ({"browser_estado", "browser_abrir", "browser_abas", "browser_info",
                    "browser_clicar", "browser_preencher", "browser_tecla", "browser_rolar",
                    "browser_screenshot", "browser_fechar", "browser_voltar", "browser_avancar", "browser_recarregar", "discord_abrir_canal"},
                  r"\bnavegador\b|\bbrowser\b|\baba\w*\b|\bsite\b|\bp[aá]gina\w*\b|\bformul[aá]rio\w*\b|discord\s+web"
                  r"|\byoutube\b|\bv[ií]deo\w*\b|\bwikip[eé]dia\b|\bcanal do\b"),
    "discord": ({"discord_enviar", "discord_estado", "discord_diagnostico", "discord_contatos",
                 "iniciar_discord", "encerrar_discord", "estado_integracoes"},
                 r"discord|mensagem|canal de texto|dm"),
    "interentidades": ({"entidades_status", "entidades_historico", "entidades_enviar_mensagem",
                         "entidades_acordar", "recursos_status"},
                        r"entidades?|Hoshino|Lilith|Alistair|acordar|dormir|conversar entre|canal privado|recursos?|gpu|microfone"),
    "voz": ({"estado_voz", "testar_voz", "parar_voz", "definir_modo_silencioso"},
             r"\bvoz\b|alto.?falante|falando|falar em voz|teste de audio|silencio|silêncio|quieta|cale"),
    "ferramentas": ({"criar_ferramenta", "listar_ferramentas", "ler_ferramenta",
                     "remover_ferramenta"},
                    r"criar\s+(?:uma\s+)?ferramenta|ferramenta\s+(?:pr[oó]pria|nova)|capacidade nova|criar uma fun[cç][aã]o|automatiz"),
    "mente": ({"o_que_me_causa", "registrar_gosto", "minha_opiniao", "meus_gostos",
               "meu_perfil"},
              r"\bsent\w*\b|\bemo[çc]\w*\b|\braiva\b|\borgulho\b|\balegr\w*\b|\bcurios\w*\b|\bhumor\b|\bgosta\w*\b|\bprefer\w*\b|\bopini[ãa]o\w*\b|"
              r"\bpersonalidade\b|\bjeito\b|\birrit\w*\b|\btriste\b|\bvergonha\b"),
    "pessoas": ({"quem_e", "listar_pessoas", "anotar_sobre_pessoa",'usuario_forma_de_tratamento'},
                r"quem\s+[ée]|\bpessoa\w*\b|\bamig[oa]\w*\b|\bconhece\w*\b|\bconfia\w*\b|\bamizade\w*\b|\bnome\b|\bapelido\b|cham[ae]r? de"),
    "xadrez": ({"jogar_xadrez", "lance_xadrez", "estado_partida", "parar_partida",
                "reivindicar_empate_xadrez", "minha_forca", "historico_xadrez"},
               r"\bxadrez\b|\btabuleiro\w*\b|\blance\w*\b|\bpe[cç]a\w*\b|\brei\w*\b|\bdama\b|\bcavalo\w*\b|\bbispo\w*\b|\btorre\w*\b|"
               r"\brating\b|\belo\b|\bempate\w*\b|\broque\b|\bxeque\b|\bmate\b|\bpgn\b"),
    "arquivos": ({"workspace", "entregar_arquivo", "listar_entregues",
                  "listar_recebidos", "ler_recebido", "baixar_arquivo",
                  "enviar_arquivo_para_hoshino", "analisar_recebido", "observar_imagem_recebida"},
                 r"\barquivo\w*\b|\bentreg\w*\b|\bmandar\w*\b|\benviar\w*\b|\banexo\w*\b|\bdocumento\w*\b|\bpasta\w*\b|\bdownload\b|\bbaixar\w*\b|\bpdf\b|\btxt\b|\bzip\b"),
    # 06/11 (pedido humano): o PC2 é o corpo remoto (painel da pessoa); comandos lá só com permissão local.
    "pc2": ({"executar_no_pc2", "abrir_no_pc2", "observar_tela", "listar_janelas", "o_que_esta_acontecendo"},
            r"\bpc\s*2\b|\bpc2\b|outro computador|segundo computador|outro pc|computador da pessoa"),
    # 06/11 (pedido humano): o que a pessoa copiou fica guardado; aparece quando ela fala da cópia.
    "copias": ({"area_de_transferencia", "observar_imagem_recebida"},
               r"\bcopi(?:ei|ou|ado|ada|ados|adas|ar|e)\b|[áa]rea de transfer[êe]ncia|clipboard|ctrl\s*\+?\s*c|\bcolei\b|\bcolar\b"),
    "minecraft": ({"minecraft_manual", "minecraft_estado", "minecraft_iniciar_ponte", "iniciar_minecraft", "encerrar_minecraft", "estado_integracoes", "minecraft_conectar", "minecraft_desconectar", "minecraft_inventario",
                    "minecraft_chat", "minecraft_procurar_bloco", "minecraft_ir_para",
                    "minecraft_parar", "minecraft_minerar", "minecraft_coletar",
                    "minecraft_craft",'minecraft_receitas','minecraft_forno', "minecraft_equipar", "minecraft_atacar",
                    "minecraft_colocar_bloco", "minecraft_usar_item", "minecraft_jogar_item", "minecraft_explorar",
                    "minecraft_seguir_jogador"},
                   r"\bminecraft\b|\bmineflayer\b|\bnether\b|\bportal\b|\bbloco\w*\b|\bcraft\w*\b|\bminera\w*\b|\bminer[ae]\w*\b|\bmine\b|\bminere\b|\bpixel\b|\bredstone\b|\baldeia\b|\bfortaleza\b|\bbioma\w*\b|\binvent[aá]rio\w*\b|\bpiglin\b|\bzumbi\w*\b|\besqueleto\w*\b"),
    "rede": ({"desligar_internet", "ligar_internet"},
             r"internet|offline|rede|desligar a internet|modo avi[ãa]o|sem rede"),
    # 06/11: "olha a minha tela" não oferecia observar_tela (só o resumo da situação) e ela dizia que não via.
    "visao": ({"observar_tela"},
              r"\btela\w*\b|\bmonitor\b|\bscreen\w*\b|o que (?:eu )?(?:estou|to|t[ôo]) (?:vendo|fazendo)|\bolh[ae]\w*\s+(?:aqui|isso|pra mim)"),
    "ambiente": ({"o_que_esta_acontecendo", "resumo_do_dia", "minhas_tentativas"},
                 r"\bacont[eé]cendo\w*\b|\btela\w*\b|\bjanela\w*\b|\babert[aoos]?\b|\btocando\b|\bm[úu]sica\w*\b|\bhoje\s+eu\b|\bo\s+dia\b|"
                 r"\btentativa\w*\b|\btravou\b|\bde\s+novo\b"),
}

_PALAVRA = {}


def grupos_das_ferramentas(nomes) -> set:
    """Grupos que contêm as ferramentas usadas há pouco. 06/11: "abre o último vídeo" e "mais detalhes?" vinham
    sem as ferramentas do turno anterior (navegador, pesquisa), e ela respondia sem agir."""
    nomes = set(nomes or ())
    return {grupo for grupo, (ferramentas, _) in GRUPOS.items() if ferramentas & nomes}



def _buscar_habilidades(contexto: str, limite: int = 12) -> list[str]:
    """Busca leve por capacidades usando palavras/aliases; nunca inventa nomes."""
    import unicodedata
    from difflib import SequenceMatcher
    texto = unicodedata.normalize("NFKD", contexto or "").lower()
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    aliases = {
        "discord": {"discord_enviar", "discord_estado", "discord_diagnostico", "discord_contatos", "iniciar_discord", "encerrar_discord", "estado_integracoes"},
        "mensagem": {"discord_enviar", "minecraft_chat"},
        "lilith": {"entidades_status", "entidades_historico", "entidades_enviar_mensagem", "entidades_acordar"},
        "alistair": {"entidades_status", "entidades_historico", "entidades_enviar_mensagem", "entidades_acordar"},
        "hoshino": {"entidades_status", "entidades_historico", "entidades_enviar_mensagem", "entidades_acordar"},
        "entidade": {"entidades_status", "entidades_historico", "entidades_enviar_mensagem", "entidades_acordar"},
        "recurso": {"recursos_status"},
        "minecraft": {"minecraft_manual", "minecraft_estado", "minecraft_iniciar_ponte", "iniciar_minecraft", "encerrar_minecraft", "estado_integracoes", "minecraft_descobrir_lan", "minecraft_conectar_lan", "minecraft_conectar", "minecraft_inventario", "minecraft_procurar_bloco", "minecraft_ir_para", "minecraft_minerar", "minecraft_coletar", "minecraft_craft", "minecraft_receitas", "minecraft_forno", "minecraft_equipar", "minecraft_atacar", "minecraft_colocar_bloco", "minecraft_usar_item", "minecraft_jogar_item", "minecraft_explorar", "minecraft_seguir_jogador"},
        "arquivo": {"workspace", "entregar_arquivo", "listar_entregues", "listar_recebidos", "ler_recebido", "baixar_arquivo"},
        "download": {"baixar_arquivo", "entregar_arquivo"},
        "navegador": {"browser_estado", "browser_abrir", "browser_abas", "browser_info", "browser_clicar", "browser_preencher", "browser_tecla", "browser_rolar", "browser_screenshot", "browser_fechar", "browser_voltar", "browser_avancar", "browser_recarregar"},
        "tela": {"observar_tela", "estado_desktop", "listar_janelas", "focar_janela", "acao_desktop", "abrir_aplicativo"},
        "mouse": {"acao_desktop"},
        "teclado": {"acao_desktop"},
        "audio": {"listar_fontes_audio", "ouvir_canal", "parar_de_ouvir", "mudar_atencao_canal", "o_que_ouvi", "estado_da_escuta", "estado_voz", "testar_voz", "parar_voz"},
        "microfone": {"estado_microfone", "definir_modo_microfone", "definir_atalho_microfone", "estado_voz", "testar_voz", "parar_voz"},
        "sandbox": {"estado_da_oficina", "executar_na_oficina", "instalar_pacote_oficina", "executar_na_ia", "instalar_pacote_ia"},
        "diagnostico": {"exportar_diagnostico", "estado_diagnostico"},
        "memoria": {"consultar_conhecimento", "registrar_conhecimento", "estatisticas_memoria", "minhas_conclusoes"},
    }
    scores = {}
    for termo, nomes in aliases.items():
        if termo in texto:
            for nome in nomes:
                scores[nome] = scores.get(nome, 0) + 3
    # Similaridade com nomes e descrições reais para paráfrases.
    for entrada in ESQUEMAS:
        fn = entrada["function"]
        nome = fn["name"]
        alvo = f"{nome} {fn.get('description','')}".lower()
        melhor = 0.0
        for palavra in {p for p in re.findall(r"[a-z0-9_]{4,}", texto) if p}:
            melhor = max(melhor, SequenceMatcher(None, palavra, nome.lower()).ratio())
        if melhor >= 0.72:
            scores[nome] = max(scores.get(nome, 0), 1)
    return [nome for nome, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limite]]

def _texto_para_relevancia(contexto: str) -> str:
    """Remove caminhos/nomes técnicos de diretório antes de detectar grupos."""
    texto = str(contexto or "")
    # Caminhos absolutos/tilde podem conter palavras que parecem capacidades
    # (ex.: "Trabalho", "pesquisa", "ferramentas"). Eles são dados, não intenção.
    texto = re.sub(r"(?m)(?:~|/)[^\n]*", " ", texto)
    # Linhas de diretórios relativos usados em roteiros longos.
    texto = re.sub(r"(?m)^\s*(?:\d{1,3}_[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)/?\s*$", " ", texto)
    return texto.casefold()


def _relevantes(contexto: str) -> set:
    """Quais grupos a mensagem atual pede, ignorando ruído de caminhos."""
    if not contexto:
        return set()
    texto = _texto_para_relevancia(contexto)
    ativos = set()
    for grupo, (_, padrao) in GRUPOS.items():
        if grupo not in _PALAVRA:
            _PALAVRA[grupo] = re.compile(padrao, re.IGNORECASE)
        if _PALAVRA[grupo].search(texto):
            ativos.add(grupo)
    return ativos


def _refinar_grupo(grupo: str, nomes: set[str], texto: str) -> set[str]:
    """Reduz um grupo para as capacidades que o verbo atual realmente sugere."""
    t = normalizar_texto(texto)

    def tem(*palavras):
        return any(p in t for p in palavras)

    if grupo == "discord":
        if tem("enviar", "mandar", "responder", "falar", "mensagem"):
            return {"discord_enviar", "discord_localizar_usuario", "discord_contatos", "discord_estado"}
        if tem("iniciar", "ligar", "abrir") and "discord" in t:
            return {"iniciar_discord", "discord_diagnostico", "discord_estado"}
        if tem("parar", "encerrar", "desligar") and "discord" in t:
            return {"encerrar_discord", "discord_estado"}
        if tem("diagnostico", "diagnóstico", "problema", "falha", "erro"):
            return {"discord_diagnostico", "discord_estado", "estado_integracoes"}
        if tem("contato", "usuario", "usuário", "quem"):
            return {"discord_contatos", "discord_localizar_usuario", "discord_estado"}
        return {"discord_estado", "discord_diagnostico"}

    if grupo == "minecraft":
        basico = {"minecraft_manual", "minecraft_estado"}
        if re.search(r'\b(?:jogar|jogue|sobreviver|sobrevivencia|explorar|explore)\b',t):
            return {name for name in nomes if name.startswith('minecraft_')}
        if tem("conectar", "conexão", "conexao", "lan", "entrar"):
            return basico | {"minecraft_iniciar_ponte", "minecraft_descobrir_lan", "minecraft_conectar_lan", "minecraft_conectar"}
        if tem("desconectar", "sair"):
            return basico | {"minecraft_desconectar"}
        if tem("inventario", "inventário"):
            return basico | {"minecraft_inventario"}
        if tem("procurar", "encontrar", "onde fica", "localizar bloco"):
            return basico | {"minecraft_procurar_bloco"}
        if tem("ir para", "andar", "navegar", "seguir"):
            return basico | {"minecraft_ir_para", "minecraft_seguir_jogador", "minecraft_parar"}
        if tem("mine ", "minerar", "minei", "minere", "quebrar", "quebre", "coletar"):
            return basico | {"minecraft_procurar_bloco", "minecraft_minerar", "minecraft_coletar", "minecraft_parar"}
        if re.search(r'\b(?:craft|craftar|fabricar|fabrique)\b',t):
            return basico | {"minecraft_inventario", "minecraft_craft",'minecraft_receitas','minecraft_forno'}
        if tem('forno','fundir','fundição','fundicao','combustivel','combustível'):
            return basico | {'minecraft_inventario','minecraft_forno','minecraft_receitas'}
        if tem("equipar", "vestir"):
            return basico | {"minecraft_inventario", "minecraft_equipar"}
        if tem("atacar", "matar"):
            return basico | {"minecraft_atacar", "minecraft_parar"}
        if tem("colocar", "construir", "bloco"):
            return basico | {"minecraft_inventario", "minecraft_colocar_bloco", "minecraft_usar_item"}
        if tem("chat", "falar"):
            return basico | {"minecraft_chat"}
        return basico

    if grupo == "arquivos":
        if tem("receber", "anexo"):
            return {"listar_recebidos", "ler_recebido", "analisar_recebido"}
        if tem("baixar", "download"):
            return {"baixar_arquivo"}
        if tem("entregue", "entregar", "enviar", "envie", "mandar", "manda", "mande"):
            return {"entregar_arquivo", "listar_entregues", "workspace"}
        # Uma única superfície de filesystem substitui read/write/mkdir.
        return {"workspace"}

    if grupo == "desktop":
        if tem("abrir aplicativo", "abrir app", "abra ", "executar aplicativo", "programa"):
            return {"abrir_aplicativo", "estado_desktop"}
        if tem("clicar", "mouse", "teclado", "digitar", "pressionar", "atalho"):
            return {"acao_desktop", "estado_desktop", "listar_janelas", "focar_janela"}
        if tem("janela", "foco", "focar"):
            return {"listar_janelas", "focar_janela", "estado_desktop"}
        if tem("instalar"):
            return {"instalar_aplicativo", "estado_desktop"}
        return {"estado_desktop", "listar_janelas"}

    if grupo == "web":
        if tem("baixar", "download"):
            return {"web_search", "fetch_page", "baixar_arquivo"}
        if tem("url", "site", "pagina", "página", "abrir"):
            return {"fetch_page"}
        # 06/11: pesquisa de assunto (o que é, explique, detalhes) lê fontes de verdade, com links e imagens.
        return {"web_search", "fetch_page", "pesquisa_profunda"}

    if grupo == "memoria":
        if tem('diario','diário','anotacoes proprias','anotacao propria','notas pessoais'):
            return {'diario','oficina_logica','consultar_resumo_diario'}
        if tem('resumo','ontem','sessao','sessão'):return {'consultar_resumo_diario','consultar_conhecimento','buscar_historico_chat'}
        if tem('diagrama','conceito','causa','logica','lógica','gráfico','grafico','rascunho','mapa mental',
               'hipótese','hipotese','raciocínio','raciocinio','questão difícil','problema complexo'):
            return {'oficina_logica','consultar_conhecimento','como_funciona'}
        if tem('licao','lição','experiencia','experiência'):return {'aprender_experiencia','oficina_logica','consultar_conhecimento'}
        if tem("registrar", "anotar", "guardar", "salvar", "adicionar"):
            return {"registrar_conhecimento", "registrar_propriedade", "registrar_procedimento"}
        if tem("preferencia", "preferência"):
            return {"learn_preference", "registrar_conhecimento", "consultar_conhecimento"}
        if tem("procedimento", "como fazer"):
            return {"consultar_procedimento", "registrar_procedimento", "registrar_resultado_procedimento"}
        # 07/11: "lembra o nome do meu cachorro?", "qual é o meu nome?" — conferir na memória e no que foi dito.
        return {"consultar_conhecimento", "propriedades_de", "como_funciona", "estatisticas_memoria",
                "buscar_historico_chat"}

    if grupo == "agenda":
        if tem("criar", "adicionar", "lembrar", "lembrete") and not tem("cancelar", "adiar"):
            return {"criar_lembrete", "listar_lembretes"}
        if tem("cancelar"):
            return {"cancelar_lembrete", "listar_lembretes"}
        if tem("adiar"):
            return {"adiar_lembrete", "listar_lembretes"}
        if tem("objetivo", "meta"):
            return {"add_goal", "list_goals", "complete_goal", "lembrar_objetivo"}
        return {"listar_lembretes", "list_goals"}

    if grupo == "sistema":
        if tem("comando", "terminal", "shell", "rodar", "executar", "execute"):
            return {"execute_command", "iniciar_comando_longo", "ver_comando", "listar_comandos", "descrever_ambientes"}
        if tem("processo", "job"):
            return {"ver_comando", "listar_comandos", "encerrar_comando"}
        if tem("instalar"):
            return {"execute_command", "descrever_ambientes"}
        return {"descrever_ambientes", "ver_comando", "listar_comandos"}

    if grupo == "voz":
        if tem("testar"):
            return {"testar_voz", "estado_voz"}
        if tem("parar", "encerrar"):
            return {"parar_voz", "estado_voz"}
        return {"estado_voz", "testar_voz"}

    if grupo == "ferramentas":
        if tem("criar"):
            return {"criar_ferramenta", "listar_ferramentas"}
        if tem("remover", "arquivar"):
            return {"remover_ferramenta", "listar_ferramentas"}
        if tem("ler", "código", "codigo"):
            return {"ler_ferramenta", "listar_ferramentas"}
        return {"listar_ferramentas", "criar_ferramenta"}

    return nomes


def normalizar_texto(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(c for c in t if not unicodedata.combining(c))


# A autonomia espontânea não ganha um terminal para fazer "qualquer coisa".
# Ela pode observar, consultar e registrar aprendizado interno; criação,
# instalação, comandos e efeitos externos só aparecem quando já existe um
# objetivo interno concreto que justifique a ação.
AUTONOMIA_ESPERANDO_OBJETIVO = (
    set(capabilities.READ_ONLY)
    | {
        'diario','oficina_logica','aprender_experiencia',
        "registrar_conhecimento", "registrar_propriedade",
        "registrar_procedimento", "registrar_resultado_procedimento",
        "learn_preference", "registrar_gosto",
    }
)


def esquemas(contexto: str = "", incluir_proprias: bool = True,
             todos: bool = False, grupos_extras=None, ferramentas_prioritarias=None,
             modo_operacao: str = "conversa") -> list:
    """Ferramentas expostas ao modelo neste turno.

    `contexto` é o texto que define a relevância (mensagem da pessoa + situação).
    Vazio devolve só o núcleo; `todos=True` devolve tudo, para testes e para o
    painel.
    """
    prioridades_lista = []
    for x in (ferramentas_prioritarias or []):
        nome = str(x).strip()
        if nome and nome not in prioridades_lista:
            prioridades_lista.append(nome)
    prioridades = set(prioridades_lista)
    if "make_directory" in prioridades or "read_file" in prioridades or "write_file" in prioridades:
        prioridades.difference_update(LEGADOS_ARQUIVOS)
        prioridades.add("workspace")
        prioridades_lista = ["workspace" if x in LEGADOS_ARQUIVOS else x for x in prioridades_lista]
    if modo_operacao == "tarefa" and prioridades_lista and not todos:
        # O executor de tarefas usa JSON estruturado; para compatibilidade com
        # consumidores legados/UI, expomos somente a operação atual. A etapa
        # seguinte só aparece depois que esta operação produzir sucesso real.
        atual = prioridades_lista[0]
        from memory.audience import filter_schemas
        return filter_schemas(ui_policy.filter_schemas(config.RAIZ, config.ENTIDADE_ID,
                                       [e for e in ESQUEMAS if e["function"]["name"] == atual]))
    else:
        permitidas = set(NUCLEO)
    if todos:
        permitidas = {e["function"]["name"] for e in ESQUEMAS if e["function"]["name"] not in LEGADOS_ARQUIVOS}
    else:
        ativos = _relevantes(contexto) | set(grupos_extras or [])
        from core import audio_playback
        if audio_playback.pending(config.ENTIDADE_ID):permitidas.add('parar_voz')
        if PARTIDA["atual"] is not None:
            ativos.add("xadrez")          # partida em andamento é contexto por si só
        try:
            if entrega.novidades_na_entrada():
                ativos.add("arquivos")
            if not rede.ativa():
                ativos.discard("web")     # sem rede, nem mostro a ferramenta
                ativos.add("rede")
        except Exception:  # noqa: BLE001
            pass
        texto_norm = normalizar_texto(contexto)
        for grupo in ativos:
            nomes_do_grupo, _ = GRUPOS.get(grupo, (set(), ""))
            permitidas |= _refinar_grupo(grupo, nomes_do_grupo, texto_norm)
        # Interpretação operacional acrescenta diretamente a capacidade principal
        # e suas dependências, sem obrigar o modelo a descobrir a ferramenta por
        # similaridade de nome.
        intencao = intent.interpretar(contexto)
        if intencao.confianca >= 0.85:
            permitidas.add(intencao.ferramenta_principal)
            permitidas.update(intencao.ferramentas_suporte)
            # A rede é uma pré-condição mecânica. A interpretação textual não
            # pode reintroduzir ferramentas externas que já foram removidas.
            try:
                if not rede.ativa():
                    permitidas.difference_update({"web_search", "fetch_page", "baixar_arquivo"})
            except Exception:  # noqa: BLE001
                pass

    # Continuação de tarefa: a próxima capacidade não pode desaparecer só porque
    # a mensagem atual diz "continue". Acrescentamos a ferramenta prevista e o
    # seu verificador diretamente, sem liberar todos os grupos.
    if prioridades and not todos:
        for nome in prioridades:
            if any(e["function"]["name"] == nome for e in ESQUEMAS):
                permitidas.add(nome)
            meta = capabilities.info(nome)
            if meta.verifier:
                permitidas.add(meta.verifier)

    # Segurança operacional para iniciativa própria.
    # `autonomo_interno`: pesquisar/observar/aprender, sem criar ou alterar o
    # ambiente. `autonomo_objetivo`: um objetivo interno já existente justifica
    # efeitos e criação; continua sujeito aos contratos normais da capacidade.
    if modo_operacao == 'autonomo_continuo':
        from core import initiative
        permitidas = initiative.allowed_tools()
        if not rede.ativa():
            permitidas.difference_update({'web_search','fetch_page','browser_abrir'})
        incluir_proprias = 'programacao' in initiative.activity().get('capacidades', [])
    elif modo_operacao == 'autonomo_exploracao':
        from core.autonomy import EXPLORATION_TOOLS
        permitidas = set(EXPLORATION_TOOLS)
        if not rede.ativa():
            permitidas.difference_update({'web_search', 'fetch_page'})
        incluir_proprias = False
    elif modo_operacao == "autonomo_interno":
        permitidas &= AUTONOMIA_ESPERANDO_OBJETIVO
        incluir_proprias = False

    base = [e for e in ESQUEMAS if e["function"]["name"] in permitidas]
    if modo_operacao == 'autonomo_continuo':
        import copy
        base = copy.deepcopy(base)
        # Manual mantém o contrato integral. Reduz apenas prosa descritiva,
        # nunca campos, tipos, enums, obrigatoriedade ou argumentos da chamada.
        for schema in base:
            fn=schema['function']
            if len(fn.get('description',''))>320:
                fn['description']=fn['description'][:300]+' [detalhes no manual_habilidades]'
            for prop in fn.get('parameters',{}).get('properties',{}).values():
                if len(prop.get('description',''))>160:
                    prop['description']=prop['description'][:140]+' [ver manual]'
    if modo_operacao == 'autonomo_exploracao':
        import copy
        base = copy.deepcopy(base)
        for schema in base:
            if schema['function']['name'] == 'diario':
                schema['function']['parameters']['properties']['operacao']['enum'] = ['ler', 'escrever']
    if incluir_proprias:
        try:
            proprias = toolforge.esquemas_para_llm(contexto)
            if modo_operacao == "autonomo_interno":
                proprias = []
            base += proprias
        except Exception:  # noqa: BLE001
            pass
    from memory.audience import filter_schemas
    return filter_schemas(ui_policy.filter_schemas(config.RAIZ, config.ENTIDADE_ID, base))


def contratos_tarefa(contexto: str = "", limite: int = 10) -> list[dict]:
    """Retorna contratos compactos e de alta confiança para um marco.

    A tarefa não expõe o catálogo inteiro ao modelo. Primeiro usamos a intenção
    e sinais operacionais explícitos (criar/ler/pesquisar/executar/abrir etc.).
    Grupos genéricos só entram como fallback quando esses sinais não bastam.
    """
    texto = str(contexto or "").strip()
    if not texto:
        return []
    normalizado = normalizar_texto(texto)
    try:
        intencao = intent.interpretar(texto)
    except Exception:
        intencao = None

    nomes_meta = {
        "manual_habilidades", "estado_diagnostico", "get_system_time", "descrever_ambientes",
        "estado_integracoes", "estado_internet", "list_goals", "listar_lembretes",
        "consultar_conhecimento", "como_funciona", "como_estou",
    }

    ferramentas_xadrez = {
        "jogar_xadrez", "lance_xadrez", "estado_partida", "parar_partida",
        "reivindicar_empate_xadrez", "minha_forca", "historico_xadrez",
    }
    menciona_xadrez = bool(re.search(
        r"\bxadrez\b|\btabuleiro\b|\blance\b|\bpe[cç]a[s]?\b|"
        r"\brei\b|\bdama\b|\bcavalo\b|\bbispo\b|\btorre\b|"
        r"\broque\b|\bxeque\b|\bmate\b|\bpgn\b|\brating\b",
        normalizado,
    ))
    candidatos_nomes: set[str] = set()
    nome_principal = str(getattr(intencao, "ferramenta_principal", "") or "") if intencao else ""
    suportes = set(getattr(intencao, "ferramentas_suporte", ()) or ()) if intencao else set()
    if nome_principal and (nome_principal not in ferramentas_xadrez or menciona_xadrez):
        candidatos_nomes.add(nome_principal)

    for nome in suportes:
        if nome not in ferramentas_xadrez or menciona_xadrez:
            candidatos_nomes.add(nome)

    def add(*nomes: str) -> None:
        candidatos_nomes.update(str(n).strip() for n in nomes if str(n).strip())

    # Sinais operacionais explícitos: são mais confiáveis que palavras soltas de
    # pastas/arquivos ou exemplos contidos dentro de um marco longo.
    if re.search(r"\b(?:crie|criar|criado|cria|fa[cç]a|fazer)\b", normalizado) and re.search(
        r"\b(?:pasta|pastas|diretorio|diretorios)\b|diretorio de trabalho", normalizado):
        add("workspace")
    if re.search(r"\b(?:crie|criar|escreva|escrever|edite|editar|altere|alterar|modifique|modificar|"
                 r"salve|salvar|adicione|adicionar|acrescente|acrescentar|produza|produzir|gere|gerar)\b", normalizado) and re.search(
        r"\b(?:arquivo|arquivos|documento|relatorio|relatório|txt|html|python)\b|\.(?:py|txt|md|html|json|csv)\b|\b(?:em|para)\s+\d{2}_[a-z0-9_./-]+",
        normalizado):
        add("workspace")
    if re.search(r"\b(?:leia|ler|leitura|verifique|verificar|confirme|confirmar|veja|inspecione|examinar|examine)\b", normalizado) and re.search(
        r"\b(?:arquivo|arquivos|resultado|saida|conteudo|documento|txt|relatorio|relatório|download|conteúdo|saída)\b", normalizado):
        add("workspace")
    if re.search(r"\b(?:calcule|calcular|conta|soma|subtraia|multiplique|divida|aritm[ée]tica)\b", normalizado) or intent.contem_expressao_matematica(normalizado):
        add("calcular")
    if (
        re.search(r"\b(?:cara ou coroa|moeda|dado[s]?)\b", normalizado)
        and re.search(r"(?:\b(?:role|sorteie|sortear)\b|\bfa[cç]a\s+(?:um|uma)\s+lan[cç]amento\b)", normalizado)
    ) or (
        re.search(r"\b(?:sorteio|sortear)\b", normalizado)
        and re.search(r"\b(?:dado[s]?|moeda|op[cç][oõ]es?|cara ou coroa)\b", normalizado)
    ):
        add("sortear")
    if re.search(r"\b(?:gere|gerar|crie|criar)\b", normalizado) and re.search(r"\b(?:imagem|figura|ilustra[cç][ãa]o|arte)\b", normalizado):
        add("gerar_imagem")
    if re.search(r"\b(?:pesquise|pesquisar|pesquisa|procure|procurar|buscar|busque|internet|fontes|fontes diferentes|fontes confiaveis|fontes confiáveis)\b", normalizado):
        add("web_search", "fetch_page")
    if re.search(r"\b(?:download|baixe|baixar|fa[cç]a download|fazer download)\b", normalizado):
        add("baixar_arquivo")
    if re.search(
        r"(?:\b(?:execute|executar|rodar|rode)\s+(?:(?:o|a|um|uma)\s+)?"
        r"(?:comando|comandos|script|scripts|programa|programas|c[oó]digo|terminal|shell|job|processo|processos)\b"
        r"|\bexecute-(?:o|a|lo|la|os|as|los|las)\b)",
        normalizado,
    ):
        add("execute_command")
    if re.search(r"\b(?:abra|abrir|aberto|abre)\b", normalizado) and re.search(
        r"\b(?:aplicativo|aplicativos|programa|programas|editor|calculadora|gerenciador de arquivos|navegador|browser)\b", normalizado):
        add("abrir_aplicativo", "estado_desktop")
    if re.search(r"\b(?:aba|abas|navegador|browser)\b", normalizado):
        if re.search(r"\b(?:identifique|descubra|estado|qual)\b", normalizado):
            add("browser_abas", "browser_info", "browser_estado")
        if re.search(r"\b(?:recarregue|recarregar|reload)\b", normalizado):
            add("browser_recarregar")
        if re.search(r"\b(?:volte|voltar|retroceda)\b", normalizado):
            add("browser_voltar")
        if re.search(r"\b(?:avance|avancar|avançar)\b", normalizado):
            add("browser_avancar")
        if re.search(r"\b(?:clique|clicar)\b", normalizado):
            add("browser_clicar")
        if re.search(r"\b(?:abra|abrir|navegue|navegar)\b", normalizado):
            add("browser_abrir", "browser_abas")
    if re.search(r"\b(?:minecraft|minere|minerar|colete|coletar|craft|bloco)\b", normalizado):
        if intencao and nome_principal:
            add(nome_principal)
    if re.search(r"\b(?:discord|canal de texto|dm)\b", normalizado) and intencao and nome_principal:
        add(nome_principal)

    # Em pedidos de código, "criar uma ferramenta chamada X.py" significa
    # criar/modificar o arquivo; não precisamos expor o toolforge nesse marco.
    if re.search(r"\.(?:py|sh|js|txt|md|html|json|csv)\b", normalizado, re.IGNORECASE):
        candidatos_nomes.difference_update({
            "criar_ferramenta", "listar_ferramentas", "ler_ferramenta", "remover_ferramenta",
            "estado_da_oficina", "criar_projeto", "escrever_na_oficina", "ler_da_oficina",
            "listar_oficina", "executar_na_oficina", "instalar_pacote_oficina",
        })
        if re.search(r"\b(?:crie|criar|escreva|escrever|edite|editar|altere|alterar|modifique|modificar|salve|salvar)\b", normalizado):
            add("workspace")

    # Fallback para uma etapa que não encontrou um sinal operacional direto.
    if not candidatos_nomes:
        try:
            grupos = _relevantes(texto)
        except Exception:
            grupos = set()
        for grupo in grupos:
            nomes_do_grupo, _ = GRUPOS.get(grupo, (set(), ""))
            try:
                candidatos_nomes.update(_refinar_grupo(grupo, nomes_do_grupo, texto))
            except Exception:
                candidatos_nomes.update(nomes_do_grupo)

    sinais_explicitos = set()
    if re.search(r"\b(?:xadrez|tabuleiro|lance|peças?|rei|dama|cavalo|bispo|torre|roque|xeque|mate|pgn|rating)\b", normalizado):
        sinais_explicitos.update({"jogar_xadrez", "lance_xadrez", "estado_partida", "parar_partida", "reivindicar_empate_xadrez", "minha_forca", "historico_xadrez"})
    if re.search(r"\bminecraft\b|\bmineflayer\b|\bnether\b|\bredstone\b|\bbioma\b|\bcraft\w*\b|\bminera\w*\b", normalizado):
        sinais_explicitos.update({nome for nome in candidatos_nomes if nome.startswith("minecraft_")})
        if nome_principal.startswith("minecraft_"):
            sinais_explicitos.add(nome_principal)
    if re.search(r"\bdiscord\b|\bdm\b|\bcanal de texto\b", normalizado):
        sinais_explicitos.update({nome for nome in candidatos_nomes if nome.startswith("discord_")})
        if nome_principal.startswith("discord_"):
            sinais_explicitos.add(nome_principal)
    if re.search(r"\b(?:imagem|figura|ilustra[cç][aã]o|arte)\b", normalizado):
        if re.search(r"\b(?:gere|gerar|crie|criar|produza|produzir)\b", normalizado):
            sinais_explicitos.add("gerar_imagem")
        elif re.search(r"\b(?:valide|validar|verifique|verificar|confirme|confirmar|estado|foi gerada|realmente gerada)\b", normalizado):
            sinais_explicitos.add("estado_imagem")
    if (
        re.search(r"\b(?:cara ou coroa|moeda|dado[s]?)\b", normalizado)
        and re.search(r"(?:\b(?:role|sorteie|sortear)\b|\bfa[cç]a\s+(?:um|uma)\s+lan[cç]amento\b)", normalizado)
    ) or (
        re.search(r"\b(?:sorteio|sortear)\b", normalizado)
        and re.search(r"\b(?:dado[s]?|moeda|op[cç][oõ]es?|cara ou coroa)\b", normalizado)
    ):
        sinais_explicitos.add("sortear")
    if re.search(r"\b(?:calcule|calcular|soma|subtraia|multiplique|divida|aritm[ée]tica)\b", normalizado) or intent.contem_expressao_matematica(normalizado):
        sinais_explicitos.add("calcular")
    if re.search(r"\b(?:arquivo|arquivos|pasta|diret[óo]rio|documento|txt|html)\b|\.(?:py|md|json|csv|txt|html)\b", normalizado):
        sinais_explicitos.add("workspace")
    if re.search(
        r"(?:\b(?:execute|executar|rodar|rode)\s+(?:(?:o|a|um|uma)\s+)?"
        r"(?:comando|comandos|script|scripts|programa|programas|c[oó]digo|terminal|shell|job|processo|processos)\b"
        r"|\bexecute-(?:o|a|lo|la|os|as|los|las)\b)",
        normalizado,
    ):
        sinais_explicitos.add("execute_command")
    if sinais_explicitos:
        candidatos_nomes &= sinais_explicitos | {"estado_imagem"}
        candidatos_nomes |= (sinais_explicitos & {"calcular", "sortear", "gerar_imagem", "workspace"})

    if re.search(r'\b(?:nao|nem|sem)\s+(?:calcule|calcular|recalcule|recalcular)\b',normalizado):
        candidatos_nomes.discard('calcular')

    # Verificadores são capacidades da mesma operação, não novas decisões do
    # modelo. Eles ajudam o planejador a manter a cadeia ação -> evidência.
    for nome in list(candidatos_nomes):
        if nome in nomes_meta:
            continue
        try:
            verificador = capabilities.info(nome).verifier
        except Exception:
            verificador = ""
        if verificador:
            candidatos_nomes.add(verificador)
    # API pública única para arquivos. As três APIs antigas permanecem apenas como compatibilidade interna.
    if candidatos_nomes & LEGADOS_ARQUIVOS:
        candidatos_nomes.difference_update(LEGADOS_ARQUIVOS)
        candidatos_nomes.add("workspace")
    if "workspace" in candidatos_nomes:
        # Workspace já cobre leitura, edição, criação de pastas, listagem e busca.
        # Não entregue o verificador genérico de diretório ao modelo quando a
        # etapa é de arquivos; mantê-lo seria apenas duplicação semântica.
        candidatos_nomes.discard("list_files")
    candidatos_nomes.difference_update(nomes_meta)
    if not candidatos_nomes:
        return []

    schemas_por_nome = {
        str(e.get("function", {}).get("name")): e
        for e in ESQUEMAS
        if str(e.get("function", {}).get("name")) in candidatos_nomes
    }
    suporte_set = set(suportes)
    candidatos = []
    for nome in sorted(candidatos_nomes):
        esquema = schemas_por_nome.get(nome)
        if not esquema:
            continue
        score = 0
        if nome == nome_principal:
            score += 100
        if nome in suporte_set:
            score += 60
        if nome in normalizado:
            score += 3
        candidatos.append((score, nome, esquema))
    candidatos.sort(key=lambda item: (-item[0], item[1]))
    from memory.audience import filter_schemas
    return filter_schemas(ui_policy.filter_schemas(config.RAIZ, config.ENTIDADE_ID,
                                   [esquema for _, _, esquema in candidatos[:max(1, int(limite))]]))


def nomes_por_grupo() -> str:
    """Para o painel: o que existe e em que grupo está."""
    linhas = [f"núcleo ({len(NUCLEO)}): sempre disponível"]
    for grupo, (ferramentas, _) in sorted(GRUPOS.items()):
        linhas.append(f"{grupo} ({len(ferramentas)}): {', '.join(sorted(ferramentas))}")
    return "\n".join(linhas)


def nomes() -> set:
    return {e["function"]["name"] for e in esquemas(todos=True)}



def esquema(nome: str) -> dict | None:
    """Retorna o schema de uma capacidade pelo nome."""
    alvo = str(nome or "").strip()
    if not alvo:
        return None
    return next((e for e in ESQUEMAS if e.get("function", {}).get("name") == alvo), None)


def formato_argumentos(nome: str) -> dict:
    """JSON Schema dos argumentos de uma única operação."""
    entrada = esquema(nome)
    if not entrada:
        return {"type": "object", "properties": {}, "additionalProperties": False}
    parametros = entrada.get("function", {}).get("parameters")
    if not isinstance(parametros, dict):
        return {"type": "object", "properties": {}, "additionalProperties": False}
    return parametros


def descricao(nome: str) -> str:
    entrada = esquema(nome)
    if not entrada:
        return ""
    return str(entrada.get("function", {}).get("description", ""))


def validar_argumentos(nome: str, argumentos: dict) -> str:
    """Valida argumentos usando o mesmo contrato usado pelo dispatcher."""
    return _validar_argumentos(str(nome or ""), dict(argumentos or {}))


def _validar_argumentos(nome: str, argumentos: dict) -> str:
    """Valida os argumentos contra o schema exposto ao LLM antes do handler."""
    entrada = next((e for e in ESQUEMAS if e["function"]["name"] == nome), None)
    if not entrada:
        return ""
    fn = entrada["function"]
    params = fn.get("parameters") or {}
    props = params.get("properties") or {}
    required = params.get("required") or []
    erros = []
    if nome in {'minecraft_coletar','minecraft_procurar_bloco','minecraft_craft','minecraft_receitas','minecraft_equipar'}:
        value=argumentos.get('nome')
        if isinstance(value,str) and any(value==s.get('function',{}).get('name') for s in ESQUEMAS):
            erros.append('nome: informe o ID do bloco/item do jogo, não o nome de uma ferramenta')
    for chave in required:
        if chave not in argumentos or argumentos.get(chave) is None:
            erros.append(f"obrigatório ausente: {chave}")
    if params.get("additionalProperties") is False:
        desconhecidos = [chave for chave in argumentos if chave not in props]
        if desconhecidos:
            erros.append("campos não permitidos: " + ", ".join(sorted(desconhecidos)))
    for chave, valor in argumentos.items():
        schema = props.get(chave)
        if not schema or valor is None:
            continue
        tipo = schema.get("type")
        ok = True
        if tipo == "string": ok = isinstance(valor, str)
        elif tipo == "number": ok = isinstance(valor, (int, float)) and not isinstance(valor, bool)
        elif tipo == "integer": ok = isinstance(valor, int) and not isinstance(valor, bool)
        elif tipo == "boolean": ok = isinstance(valor, bool)
        elif tipo == "array": ok = isinstance(valor, list)
        elif tipo == "object": ok = isinstance(valor, dict)
        if not ok:
            erros.append(f"{chave}: esperado {tipo}")
        enum = schema.get("enum")
        if enum and valor not in enum:
            erros.append(f"{chave}: valor {valor!r} não está entre {enum}")
    if erros:
        return "Erro: argumentos inválidos — " + "; ".join(erros)
    return ""

def politica_externa(nome: str, canal: str = "tui", pessoa: dict | None = None,
                     destino: str = "") -> tuple[bool, str]:
    """Impede que uma conversa externa ganhe acesso à máquina só por pedir."""
    try:
        return people.pode_usar_ferramenta(nome, canal=canal, pessoa=pessoa, destino=destino)
    except Exception as exc:  # defesa: política nunca deve derrubar a execução local
        diagnostics.exception("security.policy_error", exc, tool=nome, channel=canal)
        return False, "política de autorização indisponível para este canal."

def _executar_bruto(nome: str, argumentos: dict, confirmado: bool = False) -> str:
    """Executa uma ferramenta com rastreamento e sem esconder exceções do diagnóstico."""
    import time, uuid
    from memory.audience import tool_allowed
    if not tool_allowed(nome):
        return 'ACESSO_BLOQUEADO: esta consulta não separa fontes privadas e públicas. Use o chat direto ou entidades_historico para a conversa pública.'
    if not ui_policy.allowed(config.RAIZ, config.ENTIDADE_ID, nome, argumentos if isinstance(argumentos,dict) else {}):
        diagnostics.emit('tool.disabled_by_user', level='WARN', tool=nome, entity=config.ENTIDADE_ID)
        return 'ACESSO_BLOQUEADO: ferramenta desativada pelo usuário na central.'
    argumentos = argumentos if isinstance(argumentos, dict) else {}
    validacao = _validar_argumentos(nome, argumentos)
    if validacao:
        diagnostics.emit("tool.validation_error", level="ERROR", tool=nome, args=argumentos, error=validacao)
        return validacao
    from core import autonomy
    denied = autonomy.authorize_exploration_tool(nome, argumentos)
    if denied:
        diagnostics.emit('initiative.tool_blocked', level='WARN', tool=nome, effect_started=False)
        return denied
    rid = f"tool-{uuid.uuid4().hex[:10]}"
    autonomy._last_receipt.set(rid)
    started = time.monotonic()
    diagnostics.tool_start(nome, argumentos, rid)
    handler = (lambda a, c: toolforge.usar_ferramenta(nome[len('propria_'):], a)) if nome.startswith('propria_') else HANDLERS.get(nome)
    if handler is None:
        disponiveis = ", ".join(sorted(HANDLERS)[:12])
        resultado = (f"Erro: a ferramenta '{nome}' não existe. Algumas que existem: {disponiveis}... "
                     f"Não invente nome de ferramenta.")
        diagnostics.tool_end(nome, resultado, rid, False, int((time.monotonic()-started)*1000))
        return resultado
    # O job_bus já é o diário durável compartilhado. Não criar outro sistema
    # de recibos: registra intenção ANTES do efeito e resultado DEPOIS dele.
    mutates = capabilities.operation_mutates(nome,argumentos)
    if mutates:
        from core import job_bus
        import hashlib, json
        from core import cognition
        signature = hashlib.sha256(json.dumps([nome,cognition.argumentos_efeito(nome,argumentos)],
                                  ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
        try:
            anterior = job_bus.reserve_action(rid, config.ENTIDADE_ID, signature, nome)
            if anterior:
                return f"RESULTADO_INCERTO: operação anterior {anterior} sem confirmação; não repetida. Consulte o recibo e verifique o efeito externamente."
        except Exception as exc:
            diagnostics.persistence_failure('tool.receipt_before_effect', job_bus.DB_PATH, exc)
            return 'Erro: recibo não pôde ser registrado; nenhuma ação foi iniciada.'
    try:
        with diagnostics.context(tool_id=rid):
            resultado = str(handler(argumentos, confirmado))
        contract = _resultado_mecanico(nome, resultado)
        contract['mutates'] = mutates
        if not mutates:contract['requires_verification'] = False
        ok = contract['ok']
        if nome in {"minecraft_conectar", "minecraft_conectar_lan"} and "CONEXÃO MINECRAFT NÃO VERIFICADA" in resultado:
            ok = False
            diagnostics.emit("tool.truth_gate", level="ERROR", tool=nome, reason="conexão não verificada", request_id=rid)
        if mutates:
            accepted = ok or contract['outcome_pending']
            job_bus.publish(rid, config.ENTIDADE_ID, 'interrupted' if contract['outcome_uncertain'] else 'done' if accepted else 'error', kind='tool',
                            outcome='uncertain' if contract['outcome_uncertain'] else 'pending' if contract['outcome_pending'] else 'accepted' if ok else 'rejected',
                            verified=contract['verified'], requires_verification=contract['requires_verification'],
                            result=resultado[:2000], auto_retry=False)
        elif nome == 'diario':
            # Consulta privada mantém o recibo compartilhado anterior, sem
            # fingir uma mutação e sem copiar texto/argumentos do diário.
            from core import job_bus
            job_bus.publish(rid,config.ENTIDADE_ID,'done' if ok else 'error',kind='tool',
                tool='diario',mutates=False,outcome='accepted' if ok else 'rejected',
                verified=contract['verified'],requires_verification=False,auto_retry=False)
        diagnostics.tool_end(nome, resultado, rid, ok, int((time.monotonic()-started)*1000))
        autonomy.exploration_receipt(nome, rid, contract, argumentos)
        from core import action_commentary
        action_commentary.record(nome,rid,contract)
        return resultado
    except Exception as e:  # noqa: BLE001
        diagnostics.exception("tool.exception", e, tool=nome, request_id=rid, args=argumentos)
        resultado = f"Erro ao executar '{nome}': {type(e).__name__}: {e}"
        if mutates:
            resultado = f"RESULTADO_INCERTO: '{nome}' pode ter produzido efeito; não repetir automaticamente. Recibo {rid}. {type(e).__name__}: {e}"
            try:
                job_bus.publish(rid, config.ENTIDADE_ID, 'interrupted', kind='tool',
                                outcome='uncertain', error=str(e), auto_retry=False)
            except Exception as persist_exc:
                diagnostics.persistence_failure('tool.receipt_after_effect', job_bus.DB_PATH, persist_exc,
                                                committed=True, receipt_id=rid)
        diagnostics.tool_end(nome, resultado, rid, False, int((time.monotonic()-started)*1000))
        from core import action_commentary
        action_commentary.record(nome,rid,{'status':'uncertain' if mutates else 'error','verified':False})
        autonomy.exploration_receipt(nome, rid, {'status':'uncertain' if mutates else 'error',
                                     'mutates':mutates,'output':resultado}, argumentos)
        return resultado


def _recibo_oficina(nome: str, texto: str) -> tuple[str, int | None] | None:
    """Lê o estado do wrapper antes da saída livre do programa."""
    if nome == 'executar_na_oficina':
        header = re.match(r'\AArquivo: [^\r\n]+\nPasta de execução: [^\r\n]+\n', texto)
        if not header:
            return None
        corpo = texto[header.end():]
        exit_code = re.match(r'\A\[oficina \| código (-?\d+)\](?:\n|$)', corpo)
        if exit_code:
            code = int(exit_code.group(1))
            return ('success' if code == 0 else 'error'), code
        if re.match(r'\AErro: passou de \d+s e foi interrompido\.(?: |\n|$)', corpo):
            return 'uncertain', None
        if corpo.startswith(('Erro:', 'Erro ao executar na oficina:')):
            return 'error', None
        return 'uncertain', None
    if nome == 'executar_grafico_na_oficina':
        exit_code = re.match(r'\AArquivo: [^\r\n]+ — terminou sozinho com código (-?\d+)\.\n', texto)
        if exit_code:
            code = int(exit_code.group(1))
            return ('success' if code == 0 else 'error'), code
        if re.match(r'\AArquivo: [^\r\n]+ — rodou \d+s e foi encerrado por mim '
                    r'\(janela/loop ativo\)\.\n', texto):
            # Encerrar no prazo é o resultado mecânico previsto. Janela/conteúdo
            # continuam sujeitos à verificação própria do projeto.
            return 'success', None
    return None


def _resultado_mecanico(nome: str, saida: str) -> dict:
    """Converte a saída final em estado mecânico sem interpretar semântica livre."""
    texto = str(saida or "")
    # Compatibilidade com handlers legados que ainda devolvem texto. O controlador
    # não interpreta palavras como "registrado" ou "offline" em qualquer lugar
    # do texto; só reconhece formas explícitas de falha na abertura da mensagem.
    # Isso evita falsos positivos de histórico, consultas e conteúdo do usuário.
    texto_norm = texto.casefold().lstrip()
    falhas_explicitas = (
        "erro", "falha", "minecraft indisponível", "não consegui",
        "não existe", "nao existe", "não encontrei", "nao encontrei",
        "não é uma", "nao e uma", "a pasta não existe", "a pasta nao existe",
        "sem permissão", "sem permissao", "bloqueado:", "bloqueado ",
        "faltam argumentos", "desativada", "confirmacao_necessaria",
        "confirmacao necessaria", "não sei executar", "nao sei executar",
        "navegador indisponível", "navegador indisponivel",
        "edit_falhou", "erro_sorteio", "acesso_bloqueado:",
    )
    if nome in {'entregar_arquivo', 'ler_recebido', 'analisar_recebido'}:
        falhas_explicitas += ('não achei', 'nao achei', 'recusei entregar', 'o arquivo tem')
    erro = texto_norm.startswith(falhas_explicitas)
    if texto.startswith("CONFIRMACAO_NECESSARIA::"):
        status = "permission"
    elif erro:
        status = "error"
    else:
        status = "success"
    if texto.startswith('RESULTADO_INCERTO:'):
        status = 'uncertain'
    precondition_failed=(nome in {'minecraft_craft','minecraft_colocar_bloco','minecraft_usar_item','minecraft_forno',
                                  'minecraft_coletar','minecraft_minerar','minecraft_ir_para'}
                         and texto.startswith('ERRO_PRECONDICAO_MINECRAFT:'))
    if nome == 'entregar_arquivo' and 'CANAL_STATUS=queued' in texto:
        status = 'pending'  # cópia local não comprova entrega remota
    if nome == 'gerar_imagem' and re.match(
            r'\AIMAGEM_ENFILEIRADA=SIM\nJOB_ID=img-[a-f0-9]+\n'
            r'RESOLUCAO=\d+x\d+\nSTATUS=queued\n', texto):
        # Aceitar o job não significa que os pixels já existem. O ciclo já
        # possui um desfecho pendente: não sondar repetidamente até o limite.
        status = 'pending'
    meta = capabilities.info(nome)

    # execute_command é síncrono quando devolve explicitamente um código de
    # saída. Nesse caso o próprio adaptador já trouxe evidência suficiente: 0
    # significa sucesso e dispensa um ver_comando artificial. Se não há código
    # (por exemplo, virou job), a verificação declarada continua valendo.
    codigo_saida = None
    background_job = None
    if nome in {'executar_na_oficina', 'executar_grafico_na_oficina'}:
        recibo = _recibo_oficina(nome, texto)
        if recibo is not None:
            status, codigo_saida = recibo
        elif status == 'success':
            # Sem cabeçalho reconhecido, não atribuir os marcadores do stdout
            # ao controlador nem autorizar repetição de um efeito desconhecido.
            status = 'uncertain'
    if nome in {'execute_command', 'iniciar_comando_longo'}:
        accepted = re.match(r'\A(?:Job (job-[a-f0-9]{8}) iniciado em segundo plano[^\n]*\n|'
                            r'Ainda rodando depois de \d+s — não matei o processo, virou o job (job-[a-f0-9]{8}) \(pid \d+\)\.\n)', texto)
        if accepted:
            background_job = accepted.group(1) or accepted.group(2)
    if nome in {"execute_command", "executar_no_pc2", "abrir_no_pc2"}:
        m = re.search(r"^\[[^\n]*\|\s*sa[ií]da\s+(-?\d+)\]\s*(?:\n|$)", texto, flags=re.IGNORECASE)
        if m:
            codigo_saida = int(m.group(1))
            status = "success" if codigo_saida == 0 else "error"
    if nome == 'ver_comando':
        marker = re.search(r'^Job [\w-]+ \[[^\n]+\][^\n]*\nRESULTADO_JOB=(pending|uncertain|success|error)\nCODIGO_SAIDA=(None|-?\d+)\n', texto)
        if marker:
            status = marker.group(1)
    verified = False
    if nome in {'diario','oficina_logica','aprender_experiencia','minha_atividade'} and status=='success':
        try:
            observed=json.loads(texto)
            verified=isinstance(observed,dict) and observed.get('verified') is True
        except (ValueError,TypeError):pass
    # Somente marcadores produzidos deliberadamente pelo adaptador contam como
    # verificação forte; palavras comuns do texto não mudam esse estado.
    if nome in {'minecraft_conectar', 'minecraft_conectar_lan'} and "[CONEXÃO MINECRAFT VERIFICADA]" in texto:
        verified = True
    elif nome == 'minecraft_estado':
        try:
            observed = json.loads(texto)
            observed = observed.get('result', observed) if isinstance(observed, dict) else {}
            verified = (isinstance(observed, dict) and observed.get('connected') is True and
                        (observed.get('verified') is True or observed.get('connectionState') == 'ready'))
        except (ValueError, TypeError):
            verified = False
    if status == 'success' and nome in {'registrar_conhecimento', 'registrar_propriedade', 'registrar_procedimento', 'registrar_resultado_procedimento'}:
        verified = bool(re.search(r'\[PERSISTÊNCIA VERIFICADA id=[\w-]+\]$', texto))
    if status == 'success' and nome in {'workspace', 'write_file', 'make_directory'} and texto.startswith(('OPERACAO=salvar\n', 'OPERACAO=pasta\n')):
        verified = bool(re.search(r'^\[ARQUIVO VERIFICADO sha256=[a-f0-9]{64}\]$|^\[PASTA VERIFICADA\]$', texto, re.M))
    if nome == 'ver_comando' and status == 'success' and marker:
        verified = marker.group(2) == '0'
    if nome == 'encerrar_comando' and status == 'success':
        verified = bool(re.search(r'^Job [\w-]+ encerrado\.\n\[PROCESSO ENCERRADO VERIFICADO\]\n', texto))
    if nome == 'entregar_arquivo' and status == 'success':
        verified = bool(re.search(r'^\[ENTREGA LOCAL VERIFICADA sha256=[a-f0-9]{64}\]$',texto,re.M))
    return {
        "tool": nome,
        "ok": status == "success",
        "status": status,
        "output": texto,
        "mutates": meta.mutates,
        "requires_verification": bool(
            meta.requires_verification
            and status in {"success", "pending"}
            and codigo_saida is None
            and not (nome == 'entregar_arquivo' and verified)
        ),
        "verifier": meta.verifier,
        "verification_key": meta.verification_key,
        "verified": verified,
        # Aceitação do comando não comprova sucesso: vincula a consulta exata.
        "background_job": background_job,
        "auto_retry": False if meta.mutates else True,
        "outcome_uncertain": status == 'uncertain',
        "outcome_pending": status == 'pending',
        "delivery_status": 'queued' if nome == 'discord_enviar' and status == 'success' else None,
        **({'controlador_replanejar':True,'precondition_failed':True,'effect_started':False} if precondition_failed else {}),
    }


def executar_resultado(nome: str, argumentos: dict, confirmado: bool = False,
                       canal: str = "tui", pessoa: dict | None = None) -> dict:
    """Executa e devolve um contrato estruturado para a cognição.

    O wrapper mantém ``executar()`` compatível para módulos legados, enquanto o
    ciclo cognitivo deixa de inferir sucesso/erro a partir de palavras do texto.
    """
    permitido, motivo = politica_externa(
        nome, canal=canal, pessoa=pessoa, destino=argumentos.get("destino", "")
    )
    if not permitido:
        diagnostics.emit("security.tool_blocked", level="WARN", tool=nome, channel=canal,
                         person=(pessoa or {}).get("id", ""), reason=motivo)
        return {
            "tool": nome, "ok": False, "status": "permission", "output": f"ACESSO_BLOQUEADO: {motivo}",
            "mutates": capabilities.info(nome).mutates, "requires_verification": False,
            "verifier": "", "verification_key": "", "verified": False,
        }
    try:
        from core import autonomy
        autonomy._last_receipt.set(None)
        saida = executar(nome, argumentos, confirmado)
    except Exception as exc:  # defesa adicional para consumidores externos
        diagnostics.exception("tool.structured_wrapper_exception", exc, tool=nome)
        return {
            "tool": nome, "ok": False, "status": "error",
            "output": f"Erro ao executar '{nome}': {type(exc).__name__}: {exc}",
            "mutates": capabilities.info(nome).mutates,
            "requires_verification": False, "verifier": "",
            "verification_key": "", "verified": False,
        }
    result = _resultado_mecanico(nome, saida)
    result['mutates'] = capabilities.operation_mutates(nome,argumentos)
    if not result['mutates']:result['requires_verification'] = False
    result['receipt_id'] = autonomy._last_receipt.get()
    return result


def executar(nome: str, argumentos: dict, confirmado: bool = False) -> str:
    return _executar_bruto(nome, argumentos, confirmado)


def capacidade(nome: str):
    return capabilities.info(nome)
