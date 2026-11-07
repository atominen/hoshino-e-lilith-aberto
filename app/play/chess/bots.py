"""
Os adversários.

Quatro personagens, não quatro profundidades de busca. A diferença entre eles está
no estilo — agressividade, solidez, ruído, chance de erro — então perder para a
Brecha é diferente de perder para a Tartaruga, e a Hoshino tem o que aprender em
cada caso. Adversário que só varia a profundidade produz partidas intercambiáveis,
e aí treinar não ensina nada.

O rating de cada um é uma estimativa grosseira em escala Elo. Serve para o
emparceiramento (jogar com quem está perto do nível dela) e para a conta de
pontuação depois da partida.
"""
from play.chess.engine import Estilo

BOTS = {
    "Pepino": {
        "rating": 600,
        "descricao": "novato distraído: enxerga um lance à frente e às vezes cochila",
        "estilo": Estilo(profundidade=1, tempo_ms=250, chance_erro=0.35, ruido=40,
                         quiescencia=False, matadores=False),
        "fala": "joga rápido, erra fácil, não guarda rancor",
    },
    "Aurora": {
        "rating": 1100,
        "descricao": "sólida: troca quando está bem, protege o rei, não arrisca",
        "estilo": Estilo(profundidade=3, tempo_ms=900, solidez=1.2, agressividade=-0.2,
                         chance_erro=0.05, ruido=8),
        "fala": "paciente; ganha de quem se afoba",
    },
    "Brecha": {
        "rating": 1400,
        "descricao": "tática: procura captura e xeque, aceita posição feia por iniciativa",
        "estilo": Estilo(profundidade=4, tempo_ms=1400, agressividade=1.5, solidez=-0.3,
                         chance_erro=0.03, ruido=15),
        "fala": "punição imediata para lance descuidado",
    },
    "Tartaruga": {
        "rating": 1250,
        "descricao": "posicional: fecha o jogo, cuida dos peões, espera o erro",
        "estilo": Estilo(profundidade=3, tempo_ms=1500, solidez=1.0, agressividade=-0.5,
                         chance_erro=0.04, ruido=5),
        "fala": "partidas longas; testa a paciência",
    },
}


def por_nome(nome: str):
    return BOTS.get(nome)


def escolher(rating_dela: float, humor: dict = None, teimosia: float = 0.5) -> str:
    """Quem ela enfrenta agora.

    Perto do nível dela por padrão; animada e teimosa, encara alguém mais forte;
    murcha, prefere alguém em quem consiga ganhar. É o que uma pessoa faz.
    """
    humor = humor or {}
    alvo = rating_dela
    prazer, energia = humor.get("prazer", 0.1), humor.get("ativacao", 0.35)
    if energia > 0.6 or teimosia > 0.65:
        alvo += 180
    if prazer < -0.2:
        alvo -= 200
    return min(BOTS, key=lambda n: abs(BOTS[n]["rating"] - alvo))


def listar() -> str:
    return "\n".join(
        f"- {nome} (~{dados['rating']}): {dados['descricao']}"
        for nome, dados in sorted(BOTS.items(), key=lambda kv: kv[1]["rating"]))
