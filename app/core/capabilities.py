"""Metadados operacionais das capacidades da Hoshino.

Este módulo não decide *o que* Hoshino deve fazer. Ele descreve o contrato
operacional de cada ferramenta para que o controlador não precise adivinhar
isso olhando para texto livre devolvido por handlers.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    nome: str
    categoria: str = "consulta"       # consulta | acao | controle
    mutates: bool = False
    requires_verification: bool = False
    verifier: str = ""
    verification_key: str = ""


# Consultas puras. A lista é usada também para concorrência segura.
READ_ONLY = frozenset({
    'consultar_resumo_diario',
    "manual_habilidades", "estado_diagnostico", "historico_chat",
    "buscar_historico_chat", "estado_historico_chat", "get_system_time",
    "descrever_ambientes", "list_files", "ver_comando", "listar_comandos",
    "discord_estado", "discord_diagnostico", "discord_contatos", "discord_localizar_usuario",
    "read_file", "web_search", "fetch_page", "pesquisa_profunda", "listar_lembretes", "list_goals",
    "lembrar_objetivo", "consultar_conhecimento", "propriedades_de",
    "consultar_procedimento", "como_funciona", "estatisticas_memoria",
    "estado_da_oficina", "ler_da_oficina", "listar_oficina", "listar_ferramentas", "observar_imagem_da_oficina",
    "ler_ferramenta", "como_estou", "o_que_me_causa", "minha_opiniao", "meus_gostos",
    "meu_perfil", "minhas_conclusoes", "quem_e", "listar_pessoas", "estado_partida",
    "minha_forca", "historico_xadrez", "listar_entregues", "listar_recebidos",
    "ler_recebido", "area_de_transferencia", "estado_internet", "o_que_esta_acontecendo", "resumo_do_dia",
    "minhas_tentativas", "listar_fontes_audio", "o_que_ouvi", "estado_da_escuta",
    "estado_microfone", "estado_voz", "estado_imagem", "estado_desktop", "listar_janelas", "browser_estado",
    "browser_abas", "browser_info", "estado_integracoes", "minecraft_estado",
    "entidades_status", "entidades_historico", "recursos_status", "ficha_da_maquina",
    "minecraft_manual", "minecraft_descobrir_lan", "minecraft_inventario",'minecraft_receitas', "calcular", "sortear",
    "minecraft_procurar_bloco", "buscar_historico_chat", "estado_da_oficina",
})

# Ações cujo efeito pode ultrapassar o próprio processo ou alterar dados.
# O restante, por padrão, NÃO é tratado como leitura para fins de paralelismo.
VERIFY = {
    "write_file": ("read_file", "arquivo"),
    "execute_command": ("ver_comando", "job"),
    "iniciar_comando_longo": ("ver_comando", "job"),
    "abrir_aplicativo": ("listar_janelas", "desktop"),
    "abrir_pasta": ("listar_janelas", "desktop"),
    "acao_desktop": ("listar_janelas", "desktop"),
    "abrir_url": ("browser_abas", "browser"),
    "focar_janela": ("listar_janelas", "desktop"),
    "browser_abrir": ("browser_info", "browser"),
    "browser_clicar": ("browser_info", "browser"),
    "browser_preencher": ("browser_info", "browser"),
    "browser_tecla": ("browser_info", "browser"),
    "browser_rolar": ("browser_info", "browser"),
    "browser_fechar": ("browser_abas", "browser"),
    "browser_voltar": ("browser_info", "browser"),
    "browser_avancar": ("browser_info", "browser"),
    "browser_recarregar": ("browser_info", "browser"),
    "gerar_imagem": ("estado_imagem", "imagem"),
    "discord_enviar": ("discord_estado", "discord"),
    "entregar_arquivo": ("listar_entregues", "entrega"),
    "baixar_arquivo": ("list_files", "arquivo"),
    "instalar_aplicativo": ("estado_desktop", "desktop"),
    "instalar_pacote_ia": ("estado_da_oficina", "ia"),
    "instalar_pacote_oficina": ("estado_da_oficina", "oficina"),
    "executar_na_ia": ("estado_da_oficina", "ia"),
    "executar_na_oficina": ("estado_da_oficina", "oficina"),
    "executar_grafico_na_oficina": ("estado_da_oficina", "oficina"),
    "verificar_codigo": ("estado_da_oficina", "oficina"),
    "desligar_internet": ("estado_internet", "rede"),
    "ligar_internet": ("estado_internet", "rede"),
    "ouvir_canal": ("estado_da_escuta", "audio"),
    "parar_de_ouvir": ("estado_da_escuta", "audio"),
    "mudar_atencao_canal": ("estado_da_escuta", "audio"),
    "definir_modo_microfone": ("estado_microfone", "microfone"),
    "definir_atalho_microfone": ("estado_microfone", "microfone"),
    "testar_voz": ("estado_voz", "voz"),
    "parar_voz": ("estado_voz", "voz"),
    "iniciar_discord": ("discord_diagnostico", "discord"),
    "encerrar_discord": ("discord_estado", "discord"),
    "iniciar_minecraft": ("estado_integracoes", "minecraft"),
    "encerrar_minecraft": ("minecraft_estado", "minecraft"),
    "minecraft_conectar": ("minecraft_estado", "minecraft"),
    "minecraft_conectar_lan": ("minecraft_estado", "minecraft"),
    "minecraft_desconectar": ("minecraft_estado", "minecraft"),
    "minecraft_ir_para": ("minecraft_estado", "minecraft"),
    "minecraft_minerar": ("minecraft_estado", "minecraft"),
    "minecraft_coletar": ("minecraft_estado", "minecraft"),
    "minecraft_craft": ("minecraft_estado", "minecraft"),
    'minecraft_forno':('minecraft_estado','minecraft'),
    "minecraft_equipar": ("minecraft_estado", "minecraft"),
    "minecraft_atacar": ("minecraft_estado", "minecraft"),
    "minecraft_colocar_bloco": ("minecraft_estado", "minecraft"),
    "minecraft_usar_item": ("minecraft_estado", "minecraft"),
    "minecraft_seguir_jogador": ("minecraft_estado", "minecraft"),
    "minecraft_chat": ("minecraft_estado", "minecraft"),
    "jogar_xadrez": ("estado_partida", "xadrez"),
    "lance_xadrez": ("estado_partida", "xadrez"),
    "parar_partida": ("estado_partida", "xadrez"),
    "reivindicar_empate_xadrez": ("estado_partida", "xadrez"),
}

# Escritas internas que retornam um identificador/resultado transacional e,
# portanto, não precisam de uma segunda ferramenta apenas para provar que o DB
# recebeu a operação.
SELF_VERIFIED_WRITES = frozenset({
    'minha_atividade',
    'executar_no_pc2',  # o próprio recibo traz o código de saída do PC2; não há verificador local
    'abrir_no_pc2',
    'diario','oficina_logica','aprender_experiencia',
    "entidades_enviar_mensagem", "entidades_acordar",
    "workspace", "add_goal", "complete_goal", "criar_lembrete", "adiar_lembrete", "cancelar_lembrete",
    "registrar_conhecimento", "registrar_propriedade", "registrar_procedimento",
    "registrar_resultado_procedimento", "learn_preference", "registrar_gosto",
    "descarregar_imagem",
    "anotar_sobre_pessoa",'usuario_forma_de_tratamento', "criar_projeto", "escrever_na_oficina", "editar_na_oficina", "criar_ferramenta",
    "remover_ferramenta", "enviar_arquivo_para_hoshino", "exportar_diagnostico",
    "encerrar_diagnostico", "iniciar_diagnostico", "exportar_historico_chat",
})


def info(nome: str) -> Capability:
    if nome in READ_ONLY:
        return Capability(nome=nome)
    if nome in VERIFY:
        verificador, chave = VERIFY[nome]
        return Capability(nome=nome, categoria="acao", mutates=True,
                          requires_verification=True, verifier=verificador,
                          verification_key=chave)
    if nome in SELF_VERIFIED_WRITES:
        return Capability(nome=nome, categoria="acao", mutates=True)
    if nome.startswith("propria_"):
        # A oficina já executa a ferramenta em subprocesso e devolve um `ok`
        # transacional explícito. Sem um verificador declarado pela própria
        # ferramenta, não invente uma pendência de verificação que o núcleo não
        # tem como quitar; isso fazia `deve_continuar()` entrar em ciclo infinito.
        return Capability(nome=nome, categoria="acao", mutates=True,
                          requires_verification=False, verifier="",
                          verification_key="propria")
    # Regra conservadora: capacidade desconhecida não é considerada consulta.
    return Capability(nome=nome, categoria="acao", mutates=True,
                      requires_verification=True)


def operation_mutates(nome: str, arguments=None) -> bool:
    """Ferramentas com consultas e escritas distinguem a operação efetiva."""
    if nome=='minecraft_forno':  # estado só abre e lê o forno; processar/retirar mudam o mundo
        return str((arguments or {}).get('acao','estado')).strip().casefold()!='estado'
    op=str((arguments or {}).get('operacao','')).strip().casefold()
    read_operations={
        'workspace': {'ler','abrir','listar','buscar','read','read_file','list','search'},
        'diario': {'ler'},
        'oficina_logica': {'ler','listar'},
        'minha_atividade': {'consultar','ler_resultado'},
    }
    return False if op in read_operations.get(nome,set()) else info(nome).mutates
