"""
Pessoas, confiança, amizade.

Companheira que trata todo mundo igual não é companheira, é atendimento. O que
diferencia um vínculo é ter história: saber quem é a pessoa, há quanto tempo, o
que já aconteceu entre vocês — e tratar diferente por causa disso.

Três variáveis, porque uma só não dá conta:

* **familiaridade** — quanto vocês já conviveram. Só cresce, satura com o tempo.
  Não é sentimento: é histórico.
* **confiança** — quanto ela acredita no que a pessoa diz e faz. Sobe devagar com
  coerência, cai rápido com quebra. A assimetria é de propósito: confiança que se
  recupera num pedido de desculpas não vale nada.
* **afinidade** — quanto ela *gosta* da pessoa. Move com o que a convivência causa
  nela: conversa boa sobe, desprezo desce. É a variável que pode ser negativa.

O estágio da relação sai da combinação das três, e mudar de estágio é um evento
com peso emocional — é isso que faz "virar amigo" significar alguma coisa.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bd  # noqa: E402

ESTAGIOS = [
    (0.00, "desconhecida", "acabaram de se encontrar; ela não deve presumir intimidade"),
    (0.18, "conhecida", "já trocaram algumas palavras; trato cordial, sem intimidade"),
    (0.40, "próxima", "conversam com frequência; ela pode puxar assunto e brincar"),
    (0.65, "amiga", "vínculo estabelecido; ela pode ser direta, discordar e cobrar"),
    (0.85, "de casa", "vínculo forte e antigo; ela fala como quem já não precisa medir"),
]

# Eventos que mexem em confiança e afinidade. (Δconfiança, Δafinidade)
EVENTOS = {
    # Falar comigo aumenta familiaridade, não confiança por si só.
    # Confiança deve vir de evidência concreta (cumprir o que disse, ajudar,
    # mentir, maltratar etc.), não de simplesmente mandar muitas mensagens.
    "conversa":            (0.000, 0.010),
    "conversa_longa":      (0.000, 0.030),
    "cumpriu_o_que_disse": (0.060, 0.020),
    "ensinou_algo":        (0.030, 0.040),
    "elogiou":             (0.010, 0.050),
    "confidencia":         (0.050, 0.060),
    "pediu_desculpa":      (0.020, 0.030),
    "ajudou":              (0.040, 0.050),
    "criticou":            (0.000, -0.020),
    "ignorou":            (-0.010, -0.040),
    "contradisse_se":     (-0.080, -0.010),
    "mentiu":             (-0.250, -0.120),
    "maltratou":          (-0.060, -0.150),
}


def _lista(valor):
    try:
        dados = json.loads(valor) if valor else []
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(dados, dict):  # formato antigo do chat_identity: {"localhub": "usuario"}
        return [{"canal": k, "id": v} for k, v in dados.items()]
    return dados


# 07/11: o humano deste PC é um só. O terminal antigo (tui/local) e o chat da Central (localhub/usuario) eram duas
# pessoas, e a do terminal nascia como "alguém" a cada memória nova: uma pessoa fantasma.
CANAIS_LOCAIS = (("tui", "local"), ("localhub", "usuario"))


def _pares(linha) -> set:
    return {(str(c.get("canal")), str(c.get("id"))) for c in _lista(linha["canais"]) if isinstance(c, dict)}


def por_id(person_id: str) -> dict | None:
    linha = bd.um("SELECT * FROM people WHERE id = ?", (person_id,))
    return dict(linha) if linha else None


@bd.atomico(None)
def identificar(nome: str = "", canal: str = "tui", canal_id: str = "",
                criar: bool = True):
    """Acha a pessoa por canal+id ou por nome; cria se for gente nova."""
    if canal_id:
        linhas = bd.consultar("SELECT * FROM people WHERE status='active'")
        for linha in linhas:
            if (str(canal), str(canal_id)) in _pares(linha):
                return dict(linha)
        if (str(canal), str(canal_id)) in CANAIS_LOCAIS:
            for linha in linhas:
                if _pares(linha) & set(CANAIS_LOCAIS):
                    vincular_canal(linha["id"], canal, canal_id)
                    return por_id(linha["id"])
    if nome and canal not in {"interentidades", "localhub"}:
        linha = bd.um("SELECT * FROM people WHERE lower(nome) = lower(?) AND status='active'",
                      (nome,))
        if linha:
            if canal_id:
                vincular_canal(linha["id"], canal, canal_id)
            return dict(linha)
        for linha in bd.consultar("SELECT * FROM people WHERE status='active'"):
            if nome.lower() in [a.lower() for a in _lista(linha["apelidos"])]:
                return dict(linha)
    if not criar:
        return None

    pid = bd.novo_id("p", 6)
    canais = json.dumps([{"canal": canal, "id": canal_id}] if canal_id else [])
    bd.executar(
        "INSERT INTO people (id, nome, apelidos, papel, canais, confianca, familiaridade, "
        "afinidade, interacoes, primeiro_contato, ultimo_contato, status) "
        "VALUES (?,?,'[]','',?,0.10,0.0,0.0,0,?,?,'active')",
        (pid, nome or "alguém", canais, bd.agora(), bd.agora()))
    return dict(bd.um("SELECT * FROM people WHERE id = ?", (pid,)))



# Capacidades que uma conversa externa pode usar sem receber acesso à máquina.
# Comunicação de resposta é permitida apenas para o fio Discord que já a chamou;
# ações arbitrárias continuam bloqueadas até existir autorização operacional explícita.
CAPACIDADES_EXTERNAS_SEGURAS = {
    "web_search", "fetch_page", "get_system_time",
    "discord_estado",
}

def pode_usar_ferramenta(nome: str, canal: str = "tui", pessoa: dict | None = None,
                         destino: str = "") -> tuple[bool, str]:
    canal = str(canal or "tui").lower()
    if canal in {"tui", "voz", "local", "localhub"}:
        return True, ""
    if canal == "interentidades":
        if nome in {"entidades_status", "entidades_historico", "entidades_enviar_mensagem",
                    "entidades_acordar", "recursos_status", "get_system_time"}:
            return True, ""
        return False, "Troca entre entidades: converse e compartilhe informações; ações no sistema precisam de uma tarefa local."
    if canal == "discord":
        if nome in CAPACIDADES_EXTERNAS_SEGURAS:
            return True, ""
        if nome == "discord_enviar" and not str(destino or "").strip():
            return True, ""
        return False, (
            "pessoa externa sem autorização operacional para esta capacidade. "
            "Não crio arquivos, ferramentas, objetivos, programas ou mudanças no sistema para ela."
        )
    return False, "canal externo sem autorização operacional para esta capacidade."

@bd.atomico(False)
def vincular_canal(person_id: str, canal: str, canal_id: str) -> None:
    linha = bd.um("SELECT canais FROM people WHERE id = ?", (person_id,))
    if not linha:
        return
    canais = _lista(linha["canais"])
    if any(c.get("canal") == canal and str(c.get("id")) == str(canal_id) for c in canais):
        return
    canais.append({"canal": canal, "id": canal_id})
    bd.executar("UPDATE people SET canais = ? WHERE id = ?",
                (json.dumps(canais), person_id))


def por_canal(canal: str) -> dict:
    """{id no canal: 'Nome — papel'} das pessoas ligadas a esse canal (30/10: jogadores do Minecraft)."""
    out = {}
    for linha in bd.consultar("SELECT nome, papel, canais FROM people WHERE status='active'"):
        for c in _lista(linha["canais"]):
            if c.get("canal") == canal and c.get("id"):
                out[str(c["id"])] = linha["nome"] + (f" — {linha['papel']}" if linha["papel"] else "")
    return out


@bd.atomico("Erro de persistência: nome não confirmado.")
def renomear(person_id: str, nome: str) -> str:
    atual = bd.um("SELECT nome, apelidos FROM people WHERE id = ?", (person_id,))
    if not atual:
        return "Pessoa não encontrada."
    apelidos = _lista(atual["apelidos"])
    if atual["nome"] and atual["nome"] not in ("alguém", nome):
        apelidos.append(atual["nome"])
    bd.executar("UPDATE people SET nome = ?, apelidos = ? WHERE id = ?",
                (nome, json.dumps(sorted(set(apelidos))), person_id))
    return f"Agora sei que é {nome}."


@bd.atomico("Erro de persistência: papel não confirmado.")
def definir_papel(person_id: str, papel: str) -> str:
    if not bd.um("SELECT id FROM people WHERE id=?", (person_id,)):
        return "Pessoa não encontrada."
    bd.executar("UPDATE people SET papel = ? WHERE id = ?", (papel[:40], person_id))
    return f"Papel registrado: {papel}."


@bd.atomico(dict)
def registrar_evento(person_id: str, tipo: str, descricao: str = "") -> dict:
    """Aplica um evento de relacionamento. Devolve o estado novo, com o estágio."""
    pessoa = bd.um("SELECT * FROM people WHERE id = ?", (person_id,))
    if not pessoa:
        return {}
    dconf, dafin = EVENTOS.get(tipo, (0.0, 0.0))

    # Confiança sobe devagar e cai rápido — assimetria de propósito.
    if dconf > 0:
        nova_conf = pessoa["confianca"] + dconf * (1.0 - pessoa["confianca"])
    else:
        nova_conf = pessoa["confianca"] + dconf * (0.5 + pessoa["confianca"])
    nova_afin = max(-1.0, min(1.0, pessoa["afinidade"] + dafin))
    interacoes = pessoa["interacoes"] + 1
    # Familiaridade satura: as primeiras 30 conversas valem muito mais que a 300ª.
    nova_fam = min(1.0, 1.0 - (1.0 / (1.0 + interacoes / 25.0)))

    estagio_antes = estagio_de(pessoa)
    bd.executar(
        "UPDATE people SET confianca = ?, afinidade = ?, familiaridade = ?, "
        "interacoes = ?, ultimo_contato = ? WHERE id = ?",
        (round(max(0.0, min(1.0, nova_conf)), 4), round(nova_afin, 4),
         round(nova_fam, 4), interacoes, bd.agora(), person_id))
    bd.executar(
        "INSERT INTO person_events (id, person_id, created_at, tipo, descricao, "
        "delta_confianca, delta_afinidade) VALUES (?,?,?,?,?,?,?)",
        (bd.novo_id("pe", 8), person_id, bd.agora(), tipo, descricao[:300], dconf, dafin))

    atualizada = dict(bd.um("SELECT * FROM people WHERE id = ?", (person_id,)))
    atualizada["estagio"] = estagio_de(atualizada)
    atualizada["subiu_de_estagio"] = atualizada["estagio"] != estagio_antes
    return atualizada


def _pontuacao(pessoa) -> float:
    """Quão avançado é o vínculo: convivência + confiança + gostar."""
    return (0.40 * pessoa["familiaridade"]
            + 0.35 * pessoa["confianca"]
            + 0.25 * max(0.0, (pessoa["afinidade"] + 1) / 2 - 0.5) * 2)


def estagio_de(pessoa) -> str:
    """Estágio de vínculo com teto de confiança.

    Familiaridade e afinidade podem crescer só por convivência. Confiança, porém,
    exige evidência comportamental. Portanto conversa repetida nunca pode, sozinha,
    elevar alguém até um vínculo forte.
    """
    ponto = _pontuacao(pessoa)
    nome = ESTAGIOS[0][1]
    for limite, rotulo, _ in ESTAGIOS:
        if ponto >= limite:
            nome = rotulo

    confianca = float(pessoa.get("confianca") or 0.0)
    teto_por_confianca = (
        "conhecida" if confianca < 0.25 else
        "próxima" if confianca < 0.55 else
        "amiga" if confianca < 0.80 else
        "de casa"
    )
    ordem = {rotulo: i for i, (_, rotulo, _) in enumerate(ESTAGIOS)}
    return min(nome, teto_por_confianca, key=lambda x: ordem.get(x, 0))


def descricao_estagio(pessoa) -> str:
    atual = estagio_de(pessoa)
    for _, rotulo, descricao in ESTAGIOS:
        if rotulo == atual:
            return descricao
    return ""


def _o_que_sei(pessoa, limite: int = 6) -> list[str]:
    """O que tenho guardado sobre esta pessoa (anotações ligadas a ela pelo canal local), mais firme primeiro."""
    marcas = {f"participante:{c.get('id')}" for c in _lista(pessoa.get("canais")) if isinstance(c, dict) and c.get("id")}
    if not marcas:
        return []
    try:
        linhas = bd.consultar("SELECT content, type, source, entities FROM memories WHERE status='active' "
                              "ORDER BY confidence DESC, created_at DESC LIMIT 200")
    except Exception:  # noqa: BLE001 — sem memória, o bloco fica só com o vínculo
        return []
    achadas = []
    for linha in linhas:
        try:
            entidades = set(json.loads(linha["entities"] or "[]"))
        except (ValueError, TypeError):
            continue
        if entidades & marcas and linha["type"] not in ("reflexao", "diario"):
            achadas.append(str(linha["content"]).strip())
        if len(achadas) >= limite:
            break
    return achadas


def bloco_pessoa(pessoa) -> str:
    """Como o vínculo entra no prompt: muda o tom e responde "quem sou eu?".

    07/11 (teste de uso): o bloco dizia "não vira assunto da conversa" e ela não respondia quem a pessoa era; e falava
    da pessoa como "ela"/"nela" ("pessoa" é feminino), daí "como quiser ser chamada" para o Gustavo."""
    if not pessoa:
        return ""
    conhecido = pessoa["nome"] not in ("alguém", "", None)
    nome = pessoa["nome"] if conhecido else "essa pessoa"
    papel = f", {pessoa['papel']}" if pessoa.get("papel") else ""
    afin = pessoa["afinidade"]
    sentimento = (f"eu gosto de {nome}" if afin > 0.25 else
                  f"eu tenho ressalvas com {nome}" if afin < -0.25 else
                  f"ainda estou formando opinião sobre {nome}")
    texto = (f"[COM QUEM EU ESTOU FALANDO] {nome}{papel}. Nossa relação está em "
             f"'{estagio_de(pessoa)}' ({descricao_estagio(pessoa)}). "
             f"Já foram {pessoa['interacoes']} conversas, minha confiança em {nome} está em "
             f"{pessoa['confianca']:.0%} e {sentimento}. Isso muda o quanto eu me solto. "
             f"Se perguntarem quem é, respondo com isto e com o que sei abaixo. "
             f"Não presumo gênero: uso o nome até saber.")
    sei = _o_que_sei(pessoa) if conhecido or pessoa.get("canais") else []
    if sei:
        texto += "\nO que sei sobre " + nome + ":\n" + "\n".join(f"- {s}" for s in sei)
    return texto


def listar(limite: int = 10) -> str:
    linhas = bd.consultar("SELECT * FROM people WHERE status='active' "
                          "ORDER BY interacoes DESC LIMIT ?", (limite,))
    if not linhas:
        return "Ainda não conheço ninguém."
    return "\n".join(
        f"- {l['nome']}" + (f" ({l['papel']})" if l["papel"] else "")
        + f": {estagio_de(l)}, {l['interacoes']} conversas, "
        f"confiança {l['confianca']:.0%}, afinidade {l['afinidade']:+.2f}"
        for l in linhas)


def sobre(nome: str) -> str:
    pessoa = identificar(nome=nome, criar=False)
    if not pessoa:
        return f"Não conheço ninguém chamado {nome}."
    eventos = bd.consultar("SELECT tipo, descricao, created_at FROM person_events "
                           "WHERE person_id = ? ORDER BY created_at DESC LIMIT 5",
                           (pessoa["id"],))
    historico = "\n".join(f"  {e['created_at'][:10]} {e['tipo']}"
                          + (f": {e['descricao'][:80]}" if e["descricao"] else "")
                          for e in eventos)
    return (f"{pessoa['nome']}"
            + (f" — {pessoa['papel']}" if pessoa["papel"] else "")
            + f"\n  relação: {estagio_de(pessoa)} | confiança {pessoa['confianca']:.0%}"
            f" | afinidade {pessoa['afinidade']:+.2f} | familiaridade "
            f"{pessoa['familiaridade']:.0%}"
            f"\n  {pessoa['interacoes']} conversas desde {(pessoa['primeiro_contato'] or '')[:10]}"
            + (f"\n  últimos acontecimentos:\n{historico}" if historico else ""))


def principal():
    """A pessoa com quem ela mais convive — o usuário local, em geral."""
    linha = bd.um("SELECT * FROM people WHERE status='active' ORDER BY interacoes DESC LIMIT 1")
    return dict(linha) if linha else None
