"""Preferências de controle no JSON existente, aplicadas no dispatcher atual."""
import json
import re
import copy
from pathlib import Path

CAPABILITIES = (
    ('discord', 'Discord', 'Conversas, contatos, envio e recebimento pelo Discord.'),
    ('minecraft', 'Minecraft', 'Conectar e interagir com o jogo pela ponte existente.'),
    ('image', 'Gerar imagens', 'Geração de imagens e consultas ao gerador; não altera os modelos.'),
    ('ambient', 'Ouvir o ambiente', 'Escuta contínua e canais de áudio. Não bloqueia falar por comando nem a voz de saída.'),
    ('read', 'Ler arquivos', 'Abrir, listar e pesquisar arquivos e pastas; não inclui memórias da entidade.'),
    ('write', 'Escrever arquivos', 'Criar, editar, organizar, importar e entregar arquivos na oficina.'),
    ('web', 'Internet e navegador', 'Pesquisar, ler páginas e usar o navegador controlado.'),
    ('desktop', 'Controlar o computador', 'Observar a tela e operar aplicativos, janelas, mouse e teclado.'),
    ('code', 'Executar comandos e código', 'Terminal, programas e ferramentas da oficina. Ainda exige as aprovações existentes.'),
    ('chess', 'Jogar xadrez', 'Partidas e consultas ao tabuleiro e resultados.'),
)
KEYS = frozenset(key for key, _, _ in CAPABILITIES)
READ_TOOLS = frozenset({'read_file','list_files','ler_da_oficina','listar_oficina','estado_da_oficina','observar_imagem_da_oficina',
    'listar_entregues','listar_recebidos','ler_recebido','analisar_recebido','observar_imagem_recebida','ler_ferramenta',
    'area_de_transferencia','ficha_da_maquina'})
WRITE_TOOLS = frozenset({'write_file','make_directory','criar_projeto','escrever_na_oficina','editar_na_oficina',
    'enviar_arquivo_para_hoshino','entregar_arquivo','baixar_arquivo','remover_ferramenta','criar_ferramenta'})
CODE_TOOLS = frozenset({'execute_command','executar_no_pc2','iniciar_comando_longo','ver_comando','listar_comandos','encerrar_comando',
    'descrever_ambientes','preparar_ambiente_ia','instalar_pacote_ia','executar_na_ia',
    'executar_na_oficina','executar_grafico_na_oficina','verificar_codigo','instalar_pacote_oficina','criar_ferramenta','remover_ferramenta'})
DESKTOP_TOOLS = frozenset({'observar_tela','abrir_no_pc2','abrir_aplicativo','acao_desktop','estado_desktop','listar_janelas',
    'focar_janela','abrir_pasta','instalar_aplicativo','abrir_pasta_entregas','o_que_esta_acontecendo','resumo_do_dia'})
AMBIENT_TOOLS = frozenset({'listar_fontes_audio','ouvir_canal','parar_de_ouvir','mudar_atencao_canal','o_que_ouvi','estado_da_escuta'})
CHESS_TOOLS = frozenset({'jogar_xadrez','lance_xadrez','estado_partida','parar_partida',
    'reivindicar_empate_xadrez','minha_forca','historico_xadrez'})


def requirements(name, args=None):
    """Grupos operacionais, não nomes mentais encontrados por substring."""
    groups = set()
    if name.startswith('discord_') or name in {'iniciar_discord','encerrar_discord'}:groups.add('discord')
    if name.startswith('minecraft_') or name in {'iniciar_minecraft','encerrar_minecraft'}:groups.add('minecraft')
    if name in {'gerar_imagem','estado_imagem','descarregar_imagem'}:groups.add('image')
    if name in AMBIENT_TOOLS:groups.add('ambient')
    if name in READ_TOOLS:groups.add('read')
    if name in WRITE_TOOLS:groups.add('write')
    if name in CODE_TOOLS or name.startswith('propria_'):groups.add('code')
    if name in DESKTOP_TOOLS:groups.add('desktop')
    if name in CHESS_TOOLS:groups.add('chess')
    if name.startswith('browser_') or name in {'web_search','fetch_page','pesquisa_profunda','baixar_arquivo','abrir_url','ligar_internet','desligar_internet','estado_internet'}:groups.add('web')
    if name == 'workspace':
        op=str((args or {}).get('operacao','')).strip().casefold()
        if op in {'ler','abrir','listar','buscar','read','read_file','list','search'}:groups.add('read')
        elif op in {'salvar','pasta','write','write_file','save','criar','edit','editar','append','acrescentar','mkdir','make_directory'}:groups.add('write')
        else:groups.update(('read','write'))
    if name == 'definir_modo_microfone' and str((args or {}).get('modo','')).strip().lower() in {'aberto','continuo','contínuo','detection'}:groups.add('ambient')
    return groups


def disabled_capabilities(root, entity):
    path=Path(root)/'compartilhado/config/interface.json'
    try:
        settings=json.loads(path.read_text())
        values=settings.get('disabled_capabilities',{})
        if not isinstance(settings,dict) or not isinstance(values,dict):raise ValueError('Política inválida.')
        value=values.get(entity,[])
        if not isinstance(value,list) or any(not isinstance(x,str) or x not in KEYS for x in value):raise ValueError('Política inválida.')
        return set(value)
    except FileNotFoundError:return set()
    except (OSError,ValueError,TypeError,AttributeError):return set(KEYS)


def capability_allowed(root, entity, key):
    return key in KEYS and key not in disabled_capabilities(root,entity) and '*' not in disabled(root,entity)


def disabled(root, entity):
    path = Path(root) / 'compartilhado/config/interface.json'
    try:
        settings=json.loads(path.read_text())
        if not isinstance(settings,dict) or not isinstance(settings.get('disabled_tools',{}),dict):raise ValueError('Política inválida.')
        value = settings.get('disabled_tools', {}).get(entity, [])
        if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
            raise ValueError('Política inválida.')
        return set(value)
    except FileNotFoundError:
        return set()
    except (OSError, ValueError, TypeError):
        return {'*'}  # Configuração ilegível não concede execução silenciosamente.


def _allowed(name, args, deny, groups):
    if '*' in deny or name in deny:return False
    if name=='workspace' and args is None:return not {'read','write'}<=groups
    return not requirements(name,args)&groups


def allowed(root, entity, name, args=None):
    return _allowed(name,args,disabled(root,entity),disabled_capabilities(root,entity))


def filter_schemas(root, entity, schemas):
    result=[];deny=disabled(root,entity);groups=disabled_capabilities(root,entity)
    for schema in schemas:
        name=schema['function']['name']
        if not _allowed(name,None,deny,groups):continue
        argument='operacao' if name=='workspace' else 'modo' if name=='definir_modo_microfone' else None
        if argument:
            schema=copy.deepcopy(schema)
            operation=schema['function'].get('parameters',{}).get('properties',{}).get(argument,{})
            if 'enum' in operation:operation['enum']=[op for op in operation['enum'] if _allowed(name,{argument:op},deny,groups)]
        result.append(schema)
    return result


def validate_names(names):
    if not isinstance(names, list) or len(names) > 500 or any(
        not isinstance(x, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,120}', x) for x in names
    ):
        raise ValueError('Lista de ferramentas inválida.')
    return sorted(set(names))
