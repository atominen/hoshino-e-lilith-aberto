from core import history

def _dia(data, limite, query="", canal="", pessoa_id="", destino=""):
    out = history.daily_records(data, limit=limite, include_events=False,
                                query=query, channel=canal, person_id=pessoa_id, channel_target=destino)
    rows = out['items']
    if not rows:
        return "Nenhuma mensagem encontrada nessa data."
    text = "\n\n".join(history.format_message((r['ts'],r['direction'],r['role'],r['channel'],r['person_name'],r['content'],r['turn_id']))
                         + f"\n[message_id={r['id']}; turn_id={r['turn_id']}]" for r in rows)
    if out['legacy_timezone_unknown']:
        text += "\n\nHá horários antigos sem fuso registrado; sua data original foi preservada."
    if out['has_more']:
        text += "\n\nPágina limitada; existem mais mensagens nesta data."
    return text


def buscar(query: str, limite: int = 20, data: str = "", canal: str = "", pessoa_id: str = "", destino: str = "") -> str:
    if data:
        return _dia(data, limite, query, canal, pessoa_id, destino)
    if canal or pessoa_id or destino:
        raise ValueError("Para filtrar canal/participante/destino nesta busca, informe data YYYY-MM-DD.")
    rows=history.search(query, limite)
    if not rows: return "Nenhuma mensagem encontrada."
    return "\n\n".join(history.format_message(r) for r in rows)

def recente(limite: int = 30, canal: str = "", data: str = "", pessoa_id: str = "", destino: str = "") -> str:
    if data:
        return _dia(data, limite, canal=canal, pessoa_id=pessoa_id, destino=destino)
    if pessoa_id or destino:
        raise ValueError("Para filtrar participante/destino, informe data YYYY-MM-DD.")
    rows=history.conversation(limite, canal)
    if not rows: return "O histórico está vazio."
    return "\n\n".join(history.format_message(r) for r in rows)

def estado() -> str:
    import json
    return json.dumps(history.stats(), ensure_ascii=False)

def exportar() -> str:
    return f"Histórico completo exportado para: {history.export_txt()}"
