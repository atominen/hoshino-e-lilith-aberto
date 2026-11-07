"""Motor de xadrez local da Hoshino.

Objetivo: jogar xadrez padrão com um motor pequeno, determinístico e auditável.
A força continua configurável pelo perfil da habilidade, mas as regras do jogo e
a avaliação não usam aleatoriedade escondida. Erros de jogadores fracos são
aplicados somente na escolha final do lance.

O motor usa:
- negamax + alfa-beta;
- aprofundamento iterativo;
- tabela de transposição com limites EXACT/LOWER/UPPER;
- killer moves + history heuristic;
- ordenação MVV-LVA, promoções e lances da TT;
- quiescência que trata corretamente posições em xeque;
- avaliação material + peça-casa + estrutura de peões + peões passados +
  arquivos abertos/semiabertos + segurança de rei + par de bispos;
- tempo por lance e erro humano controlável.
"""
import random
import time

from play.chess.board import BRANCAS, PRETAS, VAZIO, Tabuleiro

VALOR = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 20000}
MATE = 100000
INF = MATE * 2

# Do ponto de vista das brancas, índice 0 = a8.
PEAO = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0]
CAVALO = [
   -50,-40,-30,-30,-30,-30,-40,-50,
   -40,-20,  0,  0,  0,  0,-20,-40,
   -30,  0, 10, 15, 15, 10,  0,-30,
   -30,  5, 15, 20, 20, 15,  5,-30,
   -30,  0, 15, 20, 20, 15,  0,-30,
   -30,  5, 10, 15, 15, 10,  5,-30,
   -40,-20,  0,  5,  5,  0,-20,-40,
   -50,-40,-30,-30,-30,-30,-40,-50]
BISPO = [
   -20,-10,-10,-10,-10,-10,-10,-20,
   -10,  0,  0,  0,  0,  0,  0,-10,
   -10,  0,  5, 10, 10,  5,  0,-10,
   -10,  5,  5, 10, 10,  5,  5,-10,
   -10,  0, 10, 10, 10, 10,  0,-10,
   -10, 10, 10, 10, 10, 10, 10,-10,
   -10,  5,  0,  0,  0,  0,  5,-10,
   -20,-10,-10,-10,-10,-10,-10,-20]
TORRE = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0]
DAMA = [
   -20,-10,-10, -5, -5,-10,-10,-20,
   -10,  0,  0,  0,  0,  0,  0,-10,
   -10,  0,  5,  5,  5,  5,  0,-10,
    -5,  0,  5,  5,  5,  5,  0, -5,
     0,  0,  5,  5,  5,  5,  0, -5,
   -10,  5,  5,  5,  5,  5,  0,-10,
   -10,  0,  5,  0,  0,  0,  0,-10,
   -20,-10,-10, -5, -5,-10,-10,-20]
REI_MEIO = [
   -30,-40,-40,-50,-50,-40,-40,-30,
   -30,-40,-40,-50,-50,-40,-40,-30,
   -30,-40,-40,-50,-50,-40,-40,-30,
   -30,-40,-40,-50,-50,-40,-40,-30,
   -20,-30,-30,-40,-40,-30,-30,-20,
   -10,-20,-20,-20,-20,-20,-20,-10,
    20, 20,  0,  0,  0,  0, 20, 20,
    20, 30, 10,  0,  0, 10, 30, 20]
REI_FINAL = [
   -50,-40,-30,-20,-20,-30,-40,-50,
   -30,-20,-10,  0,  0,-10,-20,-30,
   -30,-10, 20, 30, 30, 20,-10,-30,
   -30,-10, 30, 40, 40, 30,-10,-30,
   -30,-10, 30, 40, 40, 30,-10,-30,
   -30,-10, 20, 30, 30, 20,-10,-30,
   -30,-30,  0,  0,  0,  0,-30,-30,
   -50,-30,-30,-30,-30,-30,-30,-50]
TABELAS = {"P": PEAO, "N": CAVALO, "B": BISPO, "R": TORRE, "Q": DAMA}


class Estilo:
    def __init__(self, profundidade=3, tempo_ms=1000, agressividade=0.0, solidez=0.0,
                 ruido=0, chance_erro=0.0, quiescencia=True, matadores=True):
        self.profundidade = profundidade
        self.tempo_ms = tempo_ms
        self.agressividade = agressividade
        self.solidez = solidez
        self.ruido = ruido
        self.chance_erro = chance_erro
        self.quiescencia = quiescencia
        self.matadores = matadores


ESTILO_PADRAO = Estilo()


def fase_do_jogo(tabuleiro: Tabuleiro) -> float:
    total = 0
    for peca in tabuleiro.casas:
        if peca == VAZIO or peca.upper() in ("P", "K"):
            continue
        total += {"N": 1, "B": 1, "R": 2, "Q": 4}.get(peca.upper(), 0)
    return min(1.0, total / 24.0)


def _estrutura_de_peoes(tabuleiro: Tabuleiro, cor: str) -> int:
    peao = "P" if cor == BRANCAS else "p"
    colunas = [0] * 8
    for i, p in enumerate(tabuleiro.casas):
        if p == peao:
            colunas[i % 8] += 1
    penalidade = 0
    for coluna, quantidade in enumerate(colunas):
        if quantidade > 1:
            penalidade += 12 * (quantidade - 1)  # dobrados
        if quantidade:
            vizinhos = (colunas[coluna - 1] if coluna > 0 else 0) + \
                       (colunas[coluna + 1] if coluna < 7 else 0)
            if not vizinhos:
                penalidade += 15             # isolados
    return -penalidade


def _peoes_passados(tabuleiro: Tabuleiro, cor: str) -> int:
    meu = "P" if cor == BRANCAS else "p"
    inimigo = "p" if cor == BRANCAS else "P"
    bonus = 0
    for i, p in enumerate(tabuleiro.casas):
        if p != meu:
            continue
        col = i % 8
        cols = {c for c in (col - 1, col, col + 1) if 0 <= c < 8}
        bloqueado = False
        for j, q in enumerate(tabuleiro.casas):
            if q == inimigo and j % 8 in cols:
                if (cor == BRANCAS and j // 8 < i // 8) or (cor == PRETAS and j // 8 > i // 8):
                    bloqueado = True
                    break
        if not bloqueado:
            avancado = (6 - i // 8) if cor == BRANCAS else (i // 8 - 1)
            bonus += 8 + max(0, avancado) * 6
    return bonus


def _abrigo_do_rei(tabuleiro: Tabuleiro, cor: str) -> int:
    casa = tabuleiro.rei(cor)
    if casa is None:
        return 0
    peao = "P" if cor == BRANCAS else "p"
    frente = -8 if cor == BRANCAS else 8
    abrigo = 0
    for delta in (frente - 1, frente, frente + 1):
        alvo = casa + delta
        if 0 <= alvo < 64 and abs((alvo % 8) - (casa % 8)) <= 1:
            if tabuleiro.casas[alvo] == peao:
                abrigo += 10
    return abrigo


def _arquivo_rook_bonus(tabuleiro: Tabuleiro, cor: str) -> int:
    rook = "R" if cor == BRANCAS else "r"
    meu_peao = "P" if cor == BRANCAS else "p"
    inimigo_peao = "p" if cor == BRANCAS else "P"
    total = 0
    for i, p in enumerate(tabuleiro.casas):
        if p != rook:
            continue
        col = i % 8
        tem_meu = any(tabuleiro.casas[r * 8 + col] == meu_peao for r in range(8))
        tem_inimigo = any(tabuleiro.casas[r * 8 + col] == inimigo_peao for r in range(8))
        if not tem_meu:
            total += 18 if tem_inimigo else 28
    return total


def avaliar(tabuleiro: Tabuleiro, estilo: Estilo = None) -> int:
    """Avaliação determinística em centipeões, do ponto de vista de quem joga."""
    estilo = estilo or ESTILO_PADRAO
    fase = fase_do_jogo(tabuleiro)
    pontos = 0

    for indice, peca in enumerate(tabuleiro.casas):
        if peca == VAZIO:
            continue
        branca = peca.isupper()
        tipo = peca.upper()
        espelho = indice if branca else indice ^ 56
        valor = VALOR[tipo]
        if tipo == "K":
            posicional = int(REI_MEIO[espelho] * fase + REI_FINAL[espelho] * (1 - fase))
        else:
            posicional = TABELAS[tipo][espelho]
        pontos += (valor + posicional) if branca else -(valor + posicional)

    brancos = [p for p in tabuleiro.casas if p == "B"]
    pretos = [p for p in tabuleiro.casas if p == "b"]
    if len(brancos) >= 2:
        pontos += 30
    if len(pretos) >= 2:
        pontos -= 30

    pontos += _estrutura_de_peoes(tabuleiro, BRANCAS) - _estrutura_de_peoes(tabuleiro, PRETAS)
    pontos += _peoes_passados(tabuleiro, BRANCAS) - _peoes_passados(tabuleiro, PRETAS)
    pontos += _arquivo_rook_bonus(tabuleiro, BRANCAS) - _arquivo_rook_bonus(tabuleiro, PRETAS)

    # Segurança do rei importa principalmente na abertura/meio-jogo.
    fator_king = max(0.0, fase)
    pontos += int(estilo.solidez * fator_king * 2.0 * (
        _abrigo_do_rei(tabuleiro, BRANCAS) - _abrigo_do_rei(tabuleiro, PRETAS)))

    return pontos if tabuleiro.turno == BRANCAS else -pontos


def _pontuar_lance(tabuleiro, lance, melhor_tt, matadores, killers, estilo, ply, historia):
    pontos = 0
    if melhor_tt and lance == melhor_tt:
        pontos += 10_000_000
    if lance.promocao:
        pontos += 900_000 + VALOR.get(lance.promocao.upper(), 0) * 100
    if lance.captura != VAZIO:
        vitima = VALOR.get(lance.captura.upper(), 0)
        agressor = VALOR.get(tabuleiro.casas[lance.origem].upper(), 0)
        pontos += 800_000 + vitima * 100 - agressor
        pontos += int(estilo.agressividade * 500)
    if lance.roque:
        pontos += 40_000 + int(estilo.solidez * 500)
    if lance in killers.get(ply, ()):
        pontos += 30_000
    pontos += historia.get(lance.uci(), 0)
    return pontos


class Motor:
    def __init__(self, estilo: Estilo = None):
        self.estilo = estilo or ESTILO_PADRAO
        self.transposicao = {}
        self.killers = {}
        self.historia = {}
        self.nos = 0
        self._limite = 0.0

    def _expirar(self):
        if time.monotonic() >= self._limite:
            raise TimeoutError

    @staticmethod
    def _tt_chave(tabuleiro, profundidade):
        # O contador de meio-lances participa porque 50/75 movimentos são regras
        # do estado; a contagem atual de repetição ajuda a não reutilizar uma
        # avaliação incompatível entre históricos muito diferentes.
        return (tabuleiro.chave(), tabuleiro.meio_lances,
                tabuleiro.historico_hash.count(tabuleiro.chave()), profundidade)

    @staticmethod
    def _tt_ajusta_mate(score: int, ply: int, para_armazenar: bool) -> int:
        if score > MATE - 1000:
            return score + ply if para_armazenar else score - ply
        if score < -MATE + 1000:
            return score - ply if para_armazenar else score + ply
        return score

    def _quiescencia(self, tabuleiro: Tabuleiro, alfa: int, beta: int, ply: int = 0, profundidade=0) -> int:
        self._expirar()
        self.nos += 1
        legais = tabuleiro.legais()
        if not legais:
            return -MATE + ply if tabuleiro.em_xeque() else 0
        if tabuleiro.regra_75_lances() or tabuleiro.repeticao_quintupla() or tabuleiro.material_insuficiente():
            return 0

        em_xeque = tabuleiro.em_xeque()
        if not em_xeque:
            parado = avaliar(tabuleiro, self.estilo)
            if not self.estilo.quiescencia or profundidade >= 6:
                return parado
            if parado >= beta:
                return beta
            alfa = max(alfa, parado)
            candidatos = []
            for lance in legais:
                if lance.captura != VAZIO or lance.promocao:
                    candidatos.append(lance)
                else:
                    filho = tabuleiro.copia()
                    filho._aplicar(lance)
                    if filho.em_xeque(filho.turno):
                        candidatos.append(lance)
        else:
            # Em xeque não existe "stand pat": todas as evasões legais precisam ser buscadas.
            if profundidade >= 8:
                return avaliar(tabuleiro, self.estilo)
            candidatos = legais

        candidatos.sort(key=lambda l: -_pontuar_lance(
            tabuleiro, l, None, (), self.killers, self.estilo, ply, self.historia))
        for lance in candidatos:
            filho = tabuleiro.copia()
            filho._aplicar(lance)
            filho.historico_hash.append(filho.chave())
            pontos = -self._quiescencia(filho, -beta, -alfa, ply + 1, profundidade + 1)
            if pontos >= beta:
                return beta
            alfa = max(alfa, pontos)
        return alfa

    def _busca(self, tabuleiro: Tabuleiro, profundidade: int, alfa: int, beta: int, ply: int = 0) -> int:
        self._expirar()
        self.nos += 1
        legais = tabuleiro.legais()
        if not legais:
            return -MATE + ply if tabuleiro.em_xeque() else 0
        if tabuleiro.regra_75_lances() or tabuleiro.repeticao_quintupla() or tabuleiro.material_insuficiente():
            return 0
        if profundidade <= 0:
            return self._quiescencia(tabuleiro, alfa, beta, ply)

        chave = self._tt_chave(tabuleiro, profundidade)
        guardado = self.transposicao.get(chave)
        alfa_original = alfa
        if guardado:
            score = self._tt_ajusta_mate(guardado["score"], ply, False)
            if guardado["flag"] == "EXACT":
                return score
            if guardado["flag"] == "LOWER":
                alfa = max(alfa, score)
            elif guardado["flag"] == "UPPER":
                beta = min(beta, score)
            if alfa >= beta:
                return score
        melhor_tt = guardado.get("lance") if guardado else None

        ordenados = sorted(
            legais,
            key=lambda l: -_pontuar_lance(
                tabuleiro, l, melhor_tt, (), self.killers, self.estilo, ply, self.historia))
        melhor_score = -INF
        melhor_lance = ordenados[0]

        for lance in ordenados:
            filho = tabuleiro.copia()
            filho._aplicar(lance)
            filho.historico_hash.append(filho.chave())
            pontos = -self._busca(filho, profundidade - 1, -beta, -alfa, ply + 1)
            if pontos > melhor_score:
                melhor_score = pontos
                melhor_lance = lance
            if pontos > alfa:
                alfa = pontos
            if alfa >= beta:
                # Quiet move que produz cutoff: killer + history heuristic.
                if lance.captura == VAZIO and not lance.promocao:
                    fila = self.killers.setdefault(ply, [])
                    if lance not in fila:
                        fila.insert(0, lance)
                        del fila[2:]
                    self.historia[lance.uci()] = self.historia.get(lance.uci(), 0) + profundidade * profundidade
                break

        if melhor_score <= alfa_original:
            flag = "UPPER"
        elif melhor_score >= beta:
            flag = "LOWER"
        else:
            flag = "EXACT"
        self.transposicao[chave] = {
            "score": self._tt_ajusta_mate(melhor_score, ply, True),
            "flag": flag,
            "lance": melhor_lance,
        }
        return melhor_score

    def _busca_raiz(self, tabuleiro, profundidade, ordenados):
        alfa = -INF
        melhor = None
        melhor_score = -INF
        for lance in ordenados:
            self._expirar()
            filho = tabuleiro.copia()
            filho._aplicar(lance)
            filho.historico_hash.append(filho.chave())
            pontos = -self._busca(filho, profundidade - 1, -INF, -alfa, 1)
            if melhor is None or pontos > melhor_score:
                melhor_score, melhor = pontos, lance
            alfa = max(alfa, pontos)
        return melhor, melhor_score

    def melhor_lance(self, tabuleiro: Tabuleiro, tempo_ms: int = None, profundidade_max: int = None):
        """Retorna (lance, avaliação, info) usando aprofundamento iterativo."""
        legais = tabuleiro.legais()
        if not legais:
            return None, 0, {"nos": 0, "profundidade": 0}

        tempo_ms = self.estilo.tempo_ms if tempo_ms is None else tempo_ms
        profundidade_max = self.estilo.profundidade if profundidade_max is None else profundidade_max
        self._limite = time.monotonic() + max(1, tempo_ms) / 1000.0
        self.nos = 0
        self.transposicao.clear()
        self.killers.clear()
        self.historia.clear()

        melhor = legais[0]
        avaliacao = 0
        alcancada = 0
        ordenados = list(legais)

        for profundidade in range(1, max(1, profundidade_max) + 1):
            try:
                ordenados.sort(key=lambda l: -_pontuar_lance(
                    tabuleiro, l, melhor, (), self.killers, self.estilo, 0, self.historia))
                candidato, score = self._busca_raiz(tabuleiro, profundidade, ordenados)
                if candidato is not None:
                    melhor, avaliacao, alcancada = candidato, score, profundidade
                    # PV move primeiro no próximo iterativo.
                    ordenados.remove(candidato)
                    ordenados.insert(0, candidato)
            except TimeoutError:
                break

        erro = False
        if self.estilo.chance_erro and random.random() < self.estilo.chance_erro and len(legais) > 1:
            # Erro humano realista: prefere um lance legal próximo do melhor, não
            # um lance aleatório qualquer. Quanto maior o ruido, maior a janela.
            janela = max(40, int(self.estilo.ruido) * 3)
            avaliadas = []
            for lance in legais:
                if lance == melhor:
                    score = avaliacao
                else:
                    try:
                        filho = tabuleiro.copia()
                        filho._aplicar(lance)
                        filho.historico_hash.append(filho.chave())
                        score = -self._busca(filho, max(0, alcancada - 1), -INF, INF, 1)
                    except TimeoutError:
                        score = avaliacao - 500
                if score >= avaliacao - janela:
                    avaliadas.append((lance, score))
            if len(avaliadas) > 1:
                # Favorece os melhores, mas permite um erro pequeno.
                pesos = [max(1, 1 + (score - min(s for _, s in avaliadas)) // 20) for _, score in avaliadas]
                melhor, _ = random.choices(avaliadas, weights=pesos, k=1)[0]
                erro = melhor is not ordenados[0]

        return melhor, avaliacao, {
            "nos": self.nos,
            "profundidade": alcancada,
            "errou_de_proposito": erro,
        }

    def avaliar_posicao(self, tabuleiro: Tabuleiro, tempo_ms: int = 400) -> int:
        _, pontos, _ = self.melhor_lance(tabuleiro, tempo_ms=tempo_ms)
        return pontos
