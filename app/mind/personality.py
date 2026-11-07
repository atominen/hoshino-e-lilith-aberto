"""
Personalidade que se forma sozinha.

O problema da versão anterior: a personalidade era uma lista de adjetivos num
JSON. Ou ela estava lá desde o começo (e aí é persona de fábrica, não dela), ou
estava vazia (e aí ela cai no tom de assistente padrão). Nenhum dos dois é
"personalidade própria".

Aqui personalidade é consequência. Cada traço tem um valor e um contador de
evidências, e quem move o valor é comportamento observado — registrado em Python
pelo próprio laço, não pelo modelo dizendo "acho que sou curiosa". O traço só
aparece no prompt depois de acumular evidência suficiente; até lá ele existe no
banco, medindo, sem fingir.

A regra de atualização é a clássica de aprendizado por erro de predição
(Rescorla-Wagner / média móvel com passo decrescente):

    valor += taxa * (evidência - valor),  taxa = max(0.02, 1/(n+3))

As primeiras evidências mexem bastante — é quando ela não sabe nada de si — e
depois o traço fica firme, precisando de muita evidência contrária para virar.
Isso é de propósito: personalidade que muda a cada conversa não é personalidade.

Gostos funcionam parecido, mas guardam valência (-1 detesta … +1 adora) e motivo,
porque "não gosto" sem motivo é birra, e ela precisa poder justificar.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bd  # noqa: E402

try:
    from config import EVIDENCIAS_PARA_CONSOLIDAR, TAXA_APRENDIZADO_TRACO
except ImportError:  # pragma: no cover
    TAXA_APRENDIZADO_TRACO, EVIDENCIAS_PARA_CONSOLIDAR = 0.02, 8

# Os traços que fazem diferença numa companheira. Não são os Cinco Grandes de
# livro-texto: são as dimensões que mudam como ela se comporta no dia a dia.
TRACOS = {
    "curiosidade":  ("pergunta e investiga por conta própria", "aceita as coisas como vêm"),
    "franqueza":    ("fala o que pensa mesmo quando incomoda", "evita atrito, suaviza"),
    "calor":        ("demonstra afeto e se importa abertamente", "trata tudo com distância"),
    "iniciativa":   ("começa coisas sem ser mandada", "espera ser chamada"),
    "humor":        ("brinca, ironiza, provoca de leve", "leva tudo a sério"),
    "cautela":      ("pensa duas vezes antes de agir", "age primeiro e vê depois"),
    "teimosia":     ("insiste na própria posição", "cede rápido para evitar discussão"),
    "concisao":     ("fala pouco e direto", "se alonga, explica demais"),
    "introspeccao": ("pensa sobre si mesma", "não se examina"),
}

_LIMIAR_RELEVANCIA = 0.12   # distância de 0.5 para o traço valer menção


# ---------------------------------------------------------------- traços
def _garantir(traco: str):
    if traco not in TRACOS:
        return False
    if not bd.um("SELECT nome FROM traits WHERE nome = ?", (traco,)):
        bd.executar(
            "INSERT INTO traits (nome, valor, evidencias, soma_evidencia, descricao, "
            "atualizado_em) VALUES (?, 0.5, 0, 0, ?, ?)",
            (traco, TRACOS[traco][0], bd.agora()))
    return True


@bd.atomico("Erro de persistência: traço não confirmado; consulte o diagnóstico.")
def registrar_evidencia(traco: str, intensidade: float, motivo: str = "") -> str:
    """Um comportamento observado empurra um traço.

    `intensidade` vai de 0 (evidência forte do polo oposto) a 1 (evidência forte
    do traço). 0.5 é neutro e não move nada.
    """
    if not _garantir(traco):
        return f"Traço desconhecido: {traco}"
    intensidade = max(0.0, min(1.0, float(intensidade)))
    linha = bd.um("SELECT valor, evidencias, soma_evidencia FROM traits WHERE nome = ?", (traco,))
    n = linha["evidencias"]
    taxa = max(TAXA_APRENDIZADO_TRACO, 1.0 / (n + 3))
    novo = linha["valor"] + taxa * (intensidade - linha["valor"])
    novo = max(0.0, min(1.0, novo))
    bd.executar(
        "UPDATE traits SET valor = ?, evidencias = ?, soma_evidencia = ?, "
        "ultima_evidencia = ?, atualizado_em = ? WHERE nome = ?",
        (round(novo, 4), n + 1, round(linha["soma_evidencia"] + intensidade, 3),
         (motivo or "")[:300], bd.agora(), traco))
    return f"{traco}: {linha['valor']:.2f} -> {novo:.2f} ({n + 1} evidências)"


def traco(nome: str) -> float:
    linha = bd.um("SELECT valor FROM traits WHERE nome = ?", (nome,))
    return linha["valor"] if linha else 0.5


def consolidados() -> list:
    """Traços com evidência suficiente para serem considerados dela mesma."""
    saida = []
    for linha in bd.consultar("SELECT * FROM traits ORDER BY evidencias DESC"):
        if linha["evidencias"] < EVIDENCIAS_PARA_CONSOLIDAR:
            continue
        if abs(linha["valor"] - 0.5) < _LIMIAR_RELEVANCIA:
            continue
        alto, baixo = TRACOS.get(linha["nome"], ("", ""))
        saida.append({
            "nome": linha["nome"],
            "valor": linha["valor"],
            "evidencias": linha["evidencias"],
            "frase": alto if linha["valor"] > 0.5 else baixo,
            "intensidade": "muito" if abs(linha["valor"] - 0.5) > 0.3 else "um tanto",
        })
    return saida


def perfil_completo() -> str:
    linhas = bd.consultar("SELECT * FROM traits ORDER BY nome")
    if not linhas:
        return "Nenhum traço medido ainda."
    partes = []
    for t in linhas:
        marca = "*" if t["evidencias"] >= EVIDENCIAS_PARA_CONSOLIDAR else " "
        partes.append(f"{marca} {t['nome']:<13} {t['valor']:.2f}  ({t['evidencias']} evid.)")
    return ("Traços (* = consolidado, já aparece no jeito dela)\n" + "\n".join(partes))


# ---------------------------------------------------------------- gostos
@bd.atomico("Erro de persistência: gosto não confirmado; consulte o diagnóstico.")
def registrar_gosto(objeto: str, valencia: float, motivo: str = "",
                    categoria: str = "", origem: str = "propria") -> str:
    """Gosto ou desgosto por algo. Repetir o registro reforça e ajusta a média."""
    objeto = (objeto or "").strip()
    if not objeto:
        return "Erro: preciso saber de que se trata."
    try:
        valencia = max(-1.0, min(1.0, float(valencia)))
    except (TypeError, ValueError):
        return "Erro: valência tem que ser um número entre -1 (detesto) e 1 (adoro)."

    existente = bd.um(
        "SELECT * FROM tastes WHERE lower(objeto) = lower(?) AND status = 'active'", (objeto,))
    if existente:
        n = existente["evidencias"]
        nova_val = (existente["valencia"] * n + valencia) / (n + 1)
        nova_conf = min(0.95, existente["confianca"] + 0.12)
        bd.executar(
            "UPDATE tastes SET valencia = ?, confianca = ?, evidencias = ?, motivo = ?, "
            "atualizado_em = ? WHERE id = ?",
            (round(nova_val, 3), round(nova_conf, 3), n + 1,
             motivo or existente["motivo"], bd.agora(), existente["id"]))
        return (f"Gosto atualizado: {objeto} agora em {nova_val:+.2f} "
                f"(era {existente['valencia']:+.2f}, {n + 1} evidências).")

    tid = bd.novo_id("gosto")
    bd.executar(
        "INSERT INTO tastes (id, objeto, categoria, valencia, confianca, motivo, "
        "evidencias, origem, created_at, atualizado_em, status) "
        "VALUES (?,?,?,?,?,?,1,?,?,?,'active')",
        (tid, objeto, categoria or "", round(valencia, 3), 0.4, motivo or "",
         origem, bd.agora(), bd.agora()))
    return f"Anotado: {objeto} em {valencia:+.2f}. {motivo}".strip()


@bd.atomico(False)
def notar_exposicao(objeto: str, categoria: str = "", peso: float = 0.05) -> None:
    """Contato repetido com algo mexe de leve na opinião — mera exposição.

    Não inventa gosto do nada: só desloca um pouquinho na direção do neutro-positivo
    quem já apareceu antes, que é como familiaridade vira simpatia.
    """
    existente = bd.um(
        "SELECT * FROM tastes WHERE lower(objeto) = lower(?) AND status = 'active'", (objeto,))
    if not existente:
        return
    nova = existente["valencia"] + peso * (0.35 - existente["valencia"])
    bd.executar("UPDATE tastes SET valencia = ?, atualizado_em = ? WHERE id = ?",
                (round(nova, 3), bd.agora(), existente["id"]))


def opiniao_sobre(objeto: str) -> str:
    linha = bd.um("SELECT * FROM tastes WHERE lower(objeto) LIKE lower(?) "
                  "AND status = 'active' ORDER BY confianca DESC", (f"%{objeto}%",))
    if not linha:
        return f"Ainda não tenho opinião formada sobre {objeto}."
    return f"{linha['objeto']}: {rotulo_valencia(linha['valencia'])}" + \
           (f" — {linha['motivo']}" if linha["motivo"] else "") + \
           f" (confiança {linha['confianca']:.0%}, {linha['evidencias']} evidências)"


def rotulo_valencia(v: float) -> str:
    if v >= 0.6:
        return "adoro"
    if v >= 0.25:
        return "gosto"
    if v > -0.25:
        return "indiferente"
    if v > -0.6:
        return "não curto"
    return "detesto"


def gostos_marcantes(limite: int = 6) -> list:
    """Os gostos fortes o suficiente para influenciar como ela responde."""
    linhas = bd.consultar(
        "SELECT * FROM tastes WHERE status = 'active' AND abs(valencia) >= 0.3 "
        "AND confianca >= 0.4 ORDER BY abs(valencia) * confianca DESC LIMIT ?", (limite,))
    return [f"{l['objeto']}: {rotulo_valencia(l['valencia'])}"
            + (f" ({l['motivo']})" if l["motivo"] else "") for l in linhas]


def listar_gostos(categoria: str = "") -> str:
    sql = "SELECT * FROM tastes WHERE status = 'active'"
    params = []
    if categoria:
        sql += " AND lower(categoria) = lower(?)"
        params.append(categoria)
    linhas = bd.consultar(sql + " ORDER BY valencia DESC", tuple(params))
    if not linhas:
        return "Ainda não formei gostos registrados."
    return "\n".join(
        f"- {l['objeto']} [{rotulo_valencia(l['valencia'])} {l['valencia']:+.2f}]"
        + (f" — {l['motivo']}" if l["motivo"] else "") for l in linhas)


# ---------------------------------------------------------------- prompt
def bloco_personalidade() -> str:
    """O pedaço do prompt que descreve quem ela virou até agora."""
    partes = []
    tracos = consolidados()
    if tracos:
        partes.append("[MEU JEITO — medido pelo que eu fiz, não por adjetivo que me deram]")
        for t in tracos:
            partes.append(f"- {t['nome']}: {t['intensidade']}. Eu {t['frase']}. "
                          f"({t['evidencias']} situações registradas)")
    else:
        partes.append("[MEU JEITO]\nAinda estou me formando: tenho pouca evidência "
                      "acumulada sobre mim mesma. Isso não é licença para eu virar "
                      "assistente padrão — é só o ponto em que eu estou. Quem eu sou "
                      "vai saindo do que eu faço.")

    gostos = gostos_marcantes()
    if gostos:
        partes.append("\n[O QUE EU JÁ SEI QUE GOSTO E NÃO GOSTO]")
        partes.extend(f"- {g}" for g in gostos)
        partes.append("Isso é meu. Se me perguntarem, eu digo qual é a minha — e se eu "
                      "discordar de alguém, inclusive de quem me criou, eu falo.")
    return "\n".join(partes)
