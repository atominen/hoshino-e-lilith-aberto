"""Ferramentas de diagnóstico e exportação de logs."""
from core import diagnostics


def exportar() -> str:
    try:
        return f"Pacote de diagnóstico criado: {diagnostics.package_diagnosis()}"
    except Exception as exc:  # noqa: BLE001
        diagnostics.exception("diagnostics.package_failed", exc)
        return f"Falha ao criar pacote de diagnóstico: {type(exc).__name__}: {exc}"


def estado() -> str:
    import json
    from pathlib import Path
    import config
    pasta = Path(config.RUNTIME_DIR) / "diagnostics"
    arquivos = sorted(pasta.glob("*.jsonl"))
    linhas = 0
    ultimo = ""
    if arquivos:
        ultimo_arquivo = arquivos[-1]
        try:
            ultimo = ultimo_arquivo.name
            linhas = sum(1 for _ in ultimo_arquivo.open("r", encoding="utf-8", errors="replace"))
        except OSError:
            pass
    return json.dumps({"diretorio": str(pasta), "arquivos": len(arquivos),
                       "eventos_no_arquivo_atual": linhas, "ultimo": ultimo,
                       "sessao": diagnostics.SESSION_ID,
                       "trace": diagnostics.trace_enabled(),
                       "turn_id": diagnostics.current_turn_id()}, ensure_ascii=False)


def iniciar(rotulo: str = "") -> str:
    import json
    try:
        return json.dumps(diagnostics.iniciar_sessao_diagnostico(rotulo), ensure_ascii=False)
    except Exception as exc:
        diagnostics.exception("diagnostics.session_start_failed", exc, rotulo=rotulo)
        return f"Falha ao iniciar diagnóstico profundo: {type(exc).__name__}: {exc}"


def encerrar(exportar: bool = True) -> str:
    import json
    try:
        return json.dumps(diagnostics.encerrar_sessao_diagnostico(exportar=exportar), ensure_ascii=False)
    except Exception as exc:
        diagnostics.exception("diagnostics.session_end_failed", exc)
        return f"Falha ao encerrar diagnóstico: {type(exc).__name__}: {exc}"
