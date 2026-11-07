"""Inventário da suíte existente; não é executor de serviços/hardware.

A categoria indica a responsabilidade principal do arquivo. Grupos mistos
continuam offline e mantêm as asserções unitárias que já continham.
"""
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[1]
GRUPOS = {
    "unitario": (
        "test_adaptacoes", "test_capability_router", "test_continuidade_execucao",
        "test_logica_cognitiva", "test_progress", "test_resposta_segura",
        "test_v32_multimodal", "test_anexos_texto", "test_recursos_sistema", "test_discord_env",
        "test_habituacao_afetiva", "test_corpo_orbe", "test_orcamento_adaptativo", "test_bloqueio_treino",
    ),
    "regressao": (
        "test_comandos_duraveis", "test_action_commentary", "test_iniciativa_interna", "test_autonomia_persistente",
        "test_despertar_prompt_treinado",
        "test_integridade_memoria", "test_refinamento_cognitivo", "test_audiencia_memoria", "test_autoria_memoria", "test_prontidao_r1_r7", "test_persistencia_consolidacao", "test_encerramento_consolidacao",
        "test_contratos_consolidacao", "test_zero_defaults", "test_reflexao_noturna",
        "test_gpu_cooperativo", "test_executores_leves", "test_retirada_yi", "test_voz",
        "test_capacidade_operacional", "test_execucao_paralela", "test_v17_arquitetura",
        "test_v18_continuidade", "test_v19_continuidade", "test_v20_iniciativa",
        "test_v35_hardening", "test_ollama_lifecycle", "test_melhorias_execucao",
        "test_retry_resposta_vazia", "test_v24_estabilidade", "test_isolamento_suite", "test_mensagens_causalidade", "test_activity_context",
    ),
    "integracao_offline": (
        "test_recibos_oficina",
        "test_entidades_16gb",
        "test_minecraft_agent",
        "test_oficina_grafica",
        "test_projeto_programacao",
        "test_audio_listening",
        "test_mensagens_partes",
        "test_asr_live",
        "test_voz_basica",
        "test_texto_streaming",
        "test_percepcao_acustica",
        "test_pc2_node", "test_xbox_alistair", "test_pacote_pc2", "test_world_state", "test_audio_service", "test_minecraft_bridge", "test_central_control", "test_central_browser", "test_central_refinamento", "test_ferramentas_simples", "test_chat_global", "test_memorias_cartas", "test_despertar_privado", "test_limpeza_experiencia",
        "test_azure_tts", "test_elevenlabs_tts", "test_voz_streaming", "test_audio_transcription", "test_percepcao_fala", "test_revisor_memoria", "test_fatos_e_correcoes", "test_alistair_imagem", "test_alistair_continuidade",
        "test_central_entidades", "test_estrutura_entidades", "test_hoshino", "test_integracao",
        "test_conversa_continua", "test_manual_diretivas", "test_xadrez_real", "test_discord",
        "test_turno_e2e", "test_tarefa_longa_v27", "test_olhar_tela", "test_escuta",
        "test_microfone_controle", "test_diagnostico", "test_minecraft", "test_v28_tarefa_operacional",
        "test_v28_reset", "test_historico_integral", "test_integracoes", "test_laboratorio_ia",
        "test_microfone_v22", "test_minecraft_launcher", "test_reset_full_v28",
        "test_v23_diagnostico", "test_v23_diagnostico_pacote", "test_v8_capacidades",
    ),
    "hardware_manual": ("test_microfone_continuo_v33",),
}
AUTOMATICOS = ("unitario", "regressao", "integracao_offline")
# Ensaios existentes: apenas inventariados, NUNCA executados pela CI.
INTEGRACAO_LOCAL = (
    'scripts/testar_minecraft_4b.py',
    'scripts/testar_qwen3_6b_sniper.py',
    'scripts/comparar_yi_original.py',
    'scripts/verificar_yi_basico.py',
    'scripts/verificar_consolidacao_cognitiva.py',
    "scripts/verificar_tres_modelos.py", "scripts/verificar_imagem_standby.py",
    "scripts/verificar_audio_central.py", "scripts/verificar_executor_pc2_local.py",
    "scripts/verificar_tts_local.py", "scripts/verificar_tts_qwen.py", "scripts/verificar_tts_asr.py",
    "scripts/verificar_percepcao_acustica.py",
)


def validar():
    nomes = [nome for grupo in GRUPOS.values() for nome in grupo]
    if len(nomes) != len(set(nomes)):
        raise ValueError("Teste listado em mais de uma categoria")
    atuais = {p.stem for p in (ROOT / "testes").glob("test_*.py")}
    if atuais != set(nomes):
        raise ValueError(f"Inventário divergente: não classificados={sorted(atuais-set(nomes))}; ausentes={sorted(set(nomes)-atuais)}")
    if not all((ROOT / p).is_file() for p in INTEGRACAO_LOCAL):
        raise ValueError("Ensaio local inventariado não encontrado")


def categoria(nome):
    return next((tipo for tipo, nomes in GRUPOS.items() if nome in nomes), None)


def automaticos(tipo=None):
    validar()
    tipos = (tipo,) if tipo else AUTOMATICOS
    if any(t not in AUTOMATICOS for t in tipos):
        raise ValueError("Serviços/hardware exigem ensaio explícito fora da suíte offline")
    return [nome for t in tipos for nome in GRUPOS[t]]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tipo", choices=AUTOMATICOS)
    args = parser.parse_args()
    print("\n".join(automaticos(args.tipo)))
