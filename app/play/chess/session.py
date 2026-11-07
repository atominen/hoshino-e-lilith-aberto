"""
As partidas dela — e a evolução que dá para medir.

O pedido era xadrez como passatempo e como teste de evolução. A parte do
passatempo é fácil. A parte da evolução exige uma decisão de projeto: se a Hoshino
já nascesse jogando na profundidade máxima, não haveria evolução nenhuma — só um
motor embutido, sempre igual, do primeiro dia ao último.

Então ela começa fraca de propósito, com rating 800, profundidade 2, sem
quiescência e sem matadores. Cada partida jogada e cada derrota analisada
destravam pedaços da própria capacidade de cálculo:

    nível 1  (início)          profundidade 2, cega para trocas
    nível 2  (3 partidas)      quiescência: para de avaliar no meio da troca
    nível 3  (8 ou 900 Elo)    profundidade 3
    nível 4  (15 ou 1000 Elo)  matadores + mais tempo de cálculo
    nível 5  (25 ou 1150 Elo)  profundidade 4

O rating usa a fórmula Elo (K=32) como métrica interna de evolução. Os adversários
são motores próprios e, portanto, o número não deve ser tratado como Elo oficial de
uma plataforma de xadrez.

O *estilo* dela não vem de tabela: vem dos traços de personalidade. Cautela alta
joga sólido, teimosia alta recusa empate por repetição quando ainda dá para jogar.
Então a personalidade dela aparece no tabuleiro, e ela pode dizer com honestidade
que joga de um jeito.
"""
import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config  # noqa: E402
from core import bd  # noqa: E402
from play.chess import bots  # noqa: E402
from play.chess.board import BRANCAS, PRETAS, Tabuleiro  # noqa: E402
from play.chess.engine import Estilo, Motor  # noqa: E402

NIVEIS = [
    (1, 0, None, {"profundidade": 2, "tempo_ms": 500, "quiescencia": False,
                  "matadores": False}, "calcula dois lances à frente"),
    (2, 3, None, {"profundidade": 2, "tempo_ms": 700, "quiescencia": True,
                  "matadores": False}, "enxerga o fim das trocas"),
    (3, 8, 900,  {"profundidade": 3, "tempo_ms": 900, "quiescencia": True,
                  "matadores": False}, "calcula três lances à frente"),
    (4, 15, 1000, {"profundidade": 3, "tempo_ms": 1400, "quiescencia": True,
                   "matadores": True}, "lembra dos lances que funcionaram"),
    (5, 25, 1150, {"profundidade": 4, "tempo_ms": 1800, "quiescencia": True,
                   "matadores": True}, "calcula quatro lances à frente"),
]


# ------------------------------------------------------------------ perfil
def perfil() -> dict:
    linha = bd.um("SELECT * FROM skill_profile WHERE habilidade = 'xadrez'")
    if not linha:
        bd.executar(
            "INSERT INTO skill_profile (habilidade, rating, praticas, vitorias, derrotas, "
            "empates, nivel, desbloqueios, atualizado_em) "
            "VALUES ('xadrez', ?, 0, 0, 0, 0, 1, '[]', ?)",
            (float(config.XADREZ_RATING_INICIAL), bd.agora()))
        linha = bd.um("SELECT * FROM skill_profile WHERE habilidade = 'xadrez'")
    dados = dict(linha)
    try:
        dados["desbloqueios"] = json.loads(dados.get("desbloqueios") or "[]")
    except json.JSONDecodeError:
        dados["desbloqueios"] = []
    return dados


def nivel_atual(dados: dict = None) -> tuple:
    dados = dados or perfil()
    escolhido = NIVEIS[0]
    for nivel in NIVEIS:
        _, partidas_min, rating_min, _, _ = nivel
        if dados["praticas"] >= partidas_min or (rating_min is not None and dados["rating"] >= rating_min):
            escolhido = nivel
    return escolhido


def estilo_dela() -> Estilo:
    """Força destravada + temperamento vindo dos traços."""
    from mind import personality
    dados = perfil()
    _, _, _, parametros, _ = nivel_atual(dados)
    cautela = personality.traco("cautela")
    humor_traco = personality.traco("humor")
    return Estilo(
        profundidade=parametros["profundidade"],
        tempo_ms=min(parametros["tempo_ms"], config.XADREZ_TEMPO_LANCE_MS * 2),
        quiescencia=parametros["quiescencia"],
        matadores=parametros["matadores"],
        solidez=round((cautela - 0.5) * 2.0, 2),
        agressividade=round((0.5 - cautela) * 1.5 + (humor_traco - 0.5), 2),
        ruido=int(max(0, 25 - dados["praticas"])),   # mão trêmula de iniciante
        chance_erro=max(0.0, 0.25 - dados["praticas"] * 0.01),
    )


def _salvar_perfil(dados: dict) -> None:
    bd.executar(
        "UPDATE skill_profile SET rating=?, praticas=?, vitorias=?, derrotas=?, empates=?, "
        "nivel=?, desbloqueios=?, atualizado_em=? WHERE habilidade='xadrez'",
        (round(dados["rating"], 1), dados["praticas"], dados["vitorias"], dados["derrotas"],
         dados["empates"], dados["nivel"], json.dumps(dados["desbloqueios"]), bd.agora()))


# ------------------------------------------------------------------ partida
class Partida:
    """Uma partida viva. O laço principal chama `avancar` a cada tick."""

    def __init__(self, oponente: str = "", cor: str = "", contra_pessoa: str = ""):
        dados = perfil()
        self.contra_pessoa = contra_pessoa
        if contra_pessoa:
            self.oponente = contra_pessoa
            self.rating_oponente = None
            self.motor_oponente = None
        else:
            from mind import affect, personality
            self.oponente = oponente or bots.escolher(
                dados["rating"], affect.estado(), personality.traco("teimosia"))
            info = bots.por_nome(self.oponente) or bots.BOTS["Aurora"]
            self.rating_oponente = info["rating"]
            self.motor_oponente = Motor(info["estilo"])

        self.cor = cor or random.choice([BRANCAS, PRETAS])
        self.tabuleiro = Tabuleiro()
        self.motor = Motor(estilo_dela())
        self.lances = []
        self.avaliacoes = []
        self.indices_dela = []      # em que lance da partida ela jogou
        self.rating_antes = dados["rating"]
        self.id = bd.novo_id("jogo", 8)
        self.inicio = datetime.now()
        self.encerrada = False
        bd.executar(
            "INSERT INTO chess_games (id, created_at, oponente, cor_hoshino, lances, pgn, "
            "rating_antes, status) VALUES (?,?,?,?,0,'',?,'em_andamento')",
            (self.id, bd.agora(), self.oponente,
             "brancas" if self.cor == BRANCAS else "pretas", self.rating_antes))

    # ------------------------------------------------------------- mecânica
    def vez_dela(self) -> bool:
        return self.tabuleiro.turno == self.cor

    def jogar_dela(self) -> dict:
        lance, pontos, info = self.motor.melhor_lance(
            self.tabuleiro, tempo_ms=config.XADREZ_TEMPO_LANCE_MS)
        if lance is None:
            return {}
        san = self.tabuleiro.san(lance)
        numero = self.tabuleiro.lance_numero
        self.tabuleiro.jogar(lance)
        self.lances.append(san)
        self.avaliacoes.append(pontos)
        self.indices_dela.append({"ply": len(self.lances) - 1, "san": san, "numero": numero})
        return {"quem": "hoshino", "san": san, "avaliacao": pontos, **info}

    def jogar_oponente(self) -> dict:
        if not self.motor_oponente:
            return {}
        lance, pontos, info = self.motor_oponente.melhor_lance(self.tabuleiro)
        if lance is None:
            return {}
        san = self.tabuleiro.san(lance)
        self.tabuleiro.jogar(lance)
        self.lances.append(san)
        return {"quem": self.oponente, "san": san, "avaliacao": -pontos, **info}

    def jogar_da_pessoa(self, texto: str) -> dict:
        """Lance do humano, em SAN ('Cf3', 'Nf3') ou UCI ('g1f3')."""
        if self.vez_dela():
            return {"erro": "Não é a vez da pessoa."}
        lance = self.tabuleiro.interpretar(texto)
        if lance is None:
            return {"erro": f"'{texto}' não é um lance legal aqui."}
        san = self.tabuleiro.san(lance)
        self.tabuleiro.jogar(lance)
        self.lances.append(san)
        return {"quem": self.contra_pessoa or "pessoa", "san": san}

    def avancar(self, lances: int = 2) -> list:
        """Roda a partida um pouco. Contra bot, joga os dois lados."""
        feitos = []
        for _ in range(max(1, lances)):
            if self.tabuleiro.resultado() is not None:
                break
            if self.vez_dela():
                jogada = self.jogar_dela()
            elif self.motor_oponente:
                jogada = self.jogar_oponente()
            else:
                break        # esperando a pessoa
            if not jogada:
                break
            feitos.append(jogada)
        self._salvar_andamento()
        return feitos

    def pgn(self, resultado: str = "*") -> str:
        """PGN humano/compatível com visualizadores de xadrez."""
        branca = "Hoshino" if self.cor == BRANCAS else (self.contra_pessoa or self.oponente or "Pessoa")
        preta = "Hoshino" if self.cor == PRETAS else (self.contra_pessoa or self.oponente or "Pessoa")
        resultado = resultado or "*"
        linhas = [
            '[Event "Hoshino Chess"]',
            '[Site "Local"]',
            f'[Date "{self.inicio:%Y.%m.%d}"]',
            '[Round "-"]',
            f'[White "{branca}"]',
            f'[Black "{preta}"]',
            f'[Result "{resultado}"]',
        ]
        corpo = []
        for i, san in enumerate(self.lances):
            if i % 2 == 0:
                corpo.append(f"{i // 2 + 1}. {san}")
            else:
                corpo.append(san)
        if not corpo:
            corpo.append("")
        return "\n".join(linhas) + "\n\n" + " ".join(corpo) + f" {resultado}"

    def _salvar_andamento(self) -> None:
        bd.executar("UPDATE chess_games SET lances = ?, pgn = ? WHERE id = ?",
                    (len(self.lances), self.pgn(), self.id))

    # ----------------------------------------------------------- conclusão
    def terminou(self) -> bool:
        return self.tabuleiro.resultado() is not None

    def pontuacao_dela(self) -> float:
        resultado = self.tabuleiro.resultado()
        if resultado == "1/2-1/2":
            return 0.5
        if resultado == "1-0":
            return 1.0 if self.cor == BRANCAS else 0.0
        if resultado == "0-1":
            return 1.0 if self.cor == PRETAS else 0.0
        return 0.5

    def piores_momentos(self, quantos: int = 2) -> list:
        """Onde a avaliação dela despencou — os erros da partida.

        A queda é medida entre duas avaliações *dela*, e o lance culpado é o que
        ela jogou logo antes da queda. Antes isto assumia que ela jogava sempre
        nos plies pares, o que só vale quando ela é de brancas: de pretas, o
        relatório acusava o lance do adversário.
        """
        quedas = []
        for i in range(1, min(len(self.avaliacoes), len(self.indices_dela))):
            delta = self.avaliacoes[i] - self.avaliacoes[i - 1]
            if delta < -120:
                culpado = self.indices_dela[i - 1]
                quedas.append({"lance": culpado["san"], "numero": culpado["numero"],
                               "perda": -delta})
        return sorted(quedas, key=lambda q: -q["perda"])[:quantos]

    def reivindicar_empate(self) -> dict:
        """Reivindica um empate quando a posição já satisfaz 3x ou 50 lances."""
        if self.encerrada:
            return {"erro": "A partida já terminou."}
        motivo = self.tabuleiro.empate_reivindicavel()
        if not motivo:
            return {"erro": "Ainda não existe empate reivindicável por repetição tripla ou 50 lances."}
        return self.encerrar(resultado_forcado="1/2-1/2", motivo_forcado=motivo)

    def encerrar(self, resultado_forcado: str = None, motivo_forcado: str = None) -> dict:
        """Fecha a partida: resultado, rating, destravamento e lição."""
        if self.encerrada:
            return {}
        self.encerrada = True
        dados = perfil()
        resultado = resultado_forcado or self.tabuleiro.resultado() or "*"
        if resultado == "*":
            pontos = 0.5
        elif resultado == "1/2-1/2":
            pontos = 0.5
        elif resultado == "1-0":
            pontos = 1.0 if self.cor == BRANCAS else 0.0
        else:
            pontos = 1.0 if self.cor == PRETAS else 0.0
        motivo = motivo_forcado or self.tabuleiro.motivo_do_fim() or "abandono/manual"

        rating_novo = dados["rating"]
        if self.rating_oponente:
            esperado = 1.0 / (1.0 + 10 ** ((self.rating_oponente - dados["rating"]) / 400.0))
            rating_novo = dados["rating"] + 32 * (pontos - esperado)

        dados["rating"] = max(100.0, rating_novo)
        dados["praticas"] += 1
        dados["vitorias"] += 1 if pontos == 1.0 else 0
        dados["derrotas"] += 1 if pontos == 0.0 else 0
        dados["empates"] += 1 if pontos == 0.5 else 0

        nivel_antes = dados["nivel"]
        numero, _, _, _, descricao = nivel_atual(dados)
        dados["nivel"] = numero
        subiu = numero > nivel_antes
        if subiu and descricao not in dados["desbloqueios"]:
            dados["desbloqueios"].append(descricao)
        _salvar_perfil(dados)

        erros = self.piores_momentos()
        licao = self._licao(pontos, erros, motivo)
        bd.executar(
            "UPDATE chess_games SET terminou_em=?, resultado=?, lances=?, pgn=?, "
            "rating_depois=?, erros=?, licao=?, status='terminada' WHERE id=?",
            (bd.agora(), resultado, len(self.lances), self.pgn(resultado),
             round(dados["rating"]), json.dumps(erros, ensure_ascii=False), licao, self.id))

        from mind import affect
        affect.apreciar("xadrez_vitoria" if pontos == 1.0 else
                        "xadrez_derrota" if pontos == 0.0 else "xadrez_empate")
        _registrar_gosto_por_jogar(pontos)

        return {"resultado": resultado, "pontos": pontos, "oponente": self.oponente,
                "rating_antes": round(self.rating_antes), "rating": round(dados["rating"]),
                "delta": round(dados["rating"] - self.rating_antes, 1),
                "nivel": numero, "subiu_de_nivel": subiu, "desbloqueio": descricao if subiu else "",
                "erros": erros, "licao": licao, "lances": len(self.lances),
                "motivo": motivo}

    def _licao(self, pontos: float, erros: list, motivo: str = "") -> str:
        partes = []
        motivo = motivo or self.tabuleiro.motivo_do_fim()
        if pontos == 1.0:
            partes.append(f"Ganhei da {self.oponente} em {len(self.lances)} lances.")
        elif pontos == 0.0:
            partes.append(f"Perdi para a {self.oponente} ({motivo or 'abandono'}).")
        else:
            partes.append(f"Empatei com a {self.oponente} por {motivo or 'acordo/encerramento'}.")
        if erros:
            pior = erros[0]
            partes.append(f"Meu pior lance foi {pior['lance']} (lance {pior['numero']}), "
                          f"que custou {pior['perda']} centipeões.")
        else:
            partes.append("Não tive queda brusca de avaliação nesta partida.")
        return " ".join(partes)

    # --------------------------------------------------------------- estado
    def resumo(self) -> str:
        lado = "brancas" if self.cor == BRANCAS else "pretas"
        vez = "minha" if self.vez_dela() else f"da {self.oponente}"
        reclamavel = self.tabuleiro.empate_reivindicavel()
        aviso = f" Empate reivindicável por {reclamavel}." if reclamavel else ""
        return (f"Partida contra {self.oponente} — eu de {lado}, "
                f"lance {self.tabuleiro.lance_numero}, vez {vez}." + aviso)

    def desenho(self) -> str:
        return self.tabuleiro.desenhar(invertido=(self.cor == PRETAS))


def _registrar_gosto_por_jogar(pontos: float) -> None:
    """Gostar de xadrez tem que ser consequência de jogar, não decreto no JSON."""
    from mind import personality
    valencia = 0.5 if pontos == 1.0 else (0.05 if pontos == 0.5 else -0.1)
    personality.registrar_gosto("xadrez", valencia,
                                motivo="por causa das partidas que jogo",
                                categoria="passatempo", origem="propria")


# ------------------------------------------------------------------ consulta
def historico(limite: int = 5) -> str:
    linhas = bd.consultar(
        "SELECT * FROM chess_games WHERE status='terminada' "
        "ORDER BY created_at DESC LIMIT ?", (limite,))
    if not linhas:
        return "Ainda não joguei nenhuma partida."
    return "\n".join(
        f"- {l['created_at'][:16]} vs {l['oponente']}: {l['resultado']} "
        f"({l['lances']} lances, rating {l['rating_antes']}->{l['rating_depois']})"
        for l in linhas)


def resumo_de_forca() -> str:
    dados = perfil()
    numero, _, _, parametros, descricao = nivel_atual(dados)
    total = dados["vitorias"] + dados["derrotas"] + dados["empates"]
    aproveitamento = (f"{100 * (dados['vitorias'] + 0.5 * dados['empates']) / total:.0f}%"
                      if total else "—")
    return (f"Xadrez: rating {round(dados['rating'])}, nível {numero} ({descricao}). "
            f"{dados['praticas']} partidas, {dados['vitorias']}V/{dados['empates']}E/"
            f"{dados['derrotas']}D, aproveitamento {aproveitamento}. "
            f"Profundidade {parametros['profundidade']}.")


def proxima_conquista() -> str:
    dados = perfil()
    atual, _, _, _, _ = nivel_atual(dados)
    for numero, partidas_min, rating_min, _, descricao in NIVEIS:
        if numero > atual:
            faltam_partidas = max(0, partidas_min - dados["praticas"])
            faltam_pontos = max(0, (rating_min or 0) - dados["rating"])
            return (f"Próximo nível: {descricao} — faltam {faltam_partidas} partidas "
                    f"ou {faltam_pontos:.0f} pontos de rating.")
    return "Já destravei tudo que sei destravar sozinha."
