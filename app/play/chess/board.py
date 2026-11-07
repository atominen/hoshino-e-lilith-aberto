"""
Regras de xadrez — completas, sem dependência externa.

Nada de `python-chess`: a Hoshino roda offline numa máquina que pode não ter pip
disponível na hora, e um jogo que quebra por falta de pacote não serve de
passatempo. São ~400 linhas e cobrem tudo: roque (com as três checagens de
casa atacada), en passant, promoção, xeque-mate, afogamento, material
insuficiente, regra dos 50 lances e repetição tripla.

Representação: lista de 64 casas, índice 0 = a8, 63 = h1 (mesma ordem da FEN, o
que torna a leitura e a escrita de FEN quase diretas). Peça maiúscula é branca,
minúscula é preta.

A geração de lances é pseudolegal seguida de filtro por segurança do rei. É mais
lenta que gerar só lances legais, e é muito mais fácil de acertar — e correção
aqui é o que importa, porque erro de regra num motor de xadrez não aparece como
erro: aparece como o computador trapaceando.

A correção é verificada por `perft` nos testes (posição inicial e Kiwipete), que é
como motores de verdade se validam.
"""
import re

BRANCAS, PRETAS = "b", "p"
VAZIO = "."

PECAS_BRANCAS = set("PNBRQK")
PECAS_PRETAS = set("pnbrqk")

DIRECOES = {
    "N": (-17, -15, -10, -6, 6, 10, 15, 17),
    "B": (-9, -7, 7, 9),
    "R": (-8, -1, 1, 8),
    "Q": (-9, -8, -7, -1, 1, 7, 8, 9),
    "K": (-9, -8, -7, -1, 1, 7, 8, 9),
}
DESLIZANTES = set("BRQ")

FEN_INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

UNICODE = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
           "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟", ".": "·"}


def casa_para_indice(casa: str) -> int:
    casa = (casa or "").strip().lower()
    if not re.fullmatch(r"[a-h][1-8]", casa):
        raise ValueError(f"Casa inválida: {casa!r}")
    coluna = ord(casa[0]) - 97
    linha = int(casa[1])
    return (8 - linha) * 8 + coluna


def indice_para_casa(indice: int) -> str:
    return f"{chr(97 + indice % 8)}{8 - indice // 8}"


def _dentro(origem: int, destino: int, delta: int) -> bool:
    """Impede que o movimento 'dê a volta' pela borda do tabuleiro."""
    if not 0 <= destino < 64:
        return False
    col_o, col_d = origem % 8, destino % 8
    if delta in (-1, 1) and abs(col_o - col_d) != 1:
        return False
    if delta in (-9, -7, 7, 9) and abs(col_o - col_d) != 1:
        return False
    if delta in (-17, -15, -10, -6, 6, 10, 15, 17):
        if abs(col_o - col_d) > 2:
            return False
    return True


class Lance:
    __slots__ = ("origem", "destino", "promocao", "captura", "roque", "en_passant")

    def __init__(self, origem, destino, promocao="", captura=VAZIO,
                 roque="", en_passant=False):
        self.origem = origem
        self.destino = destino
        self.promocao = promocao
        self.captura = captura
        self.roque = roque
        self.en_passant = en_passant

    def uci(self) -> str:
        return (indice_para_casa(self.origem) + indice_para_casa(self.destino)
                + (self.promocao.lower() if self.promocao else ""))

    def __eq__(self, outro):
        return (isinstance(outro, Lance) and self.origem == outro.origem
                and self.destino == outro.destino and self.promocao == outro.promocao)

    def __hash__(self):
        return hash((self.origem, self.destino, self.promocao))

    def __repr__(self):
        return f"<{self.uci()}>"


class Tabuleiro:
    def __init__(self, fen: str = FEN_INICIAL):
        self.casas = [VAZIO] * 64
        self.turno = BRANCAS
        self.roques = set()
        self.en_passant = None
        self.meio_lances = 0
        self.lance_numero = 1
        self.historico_hash = []
        self.carregar_fen(fen)

    # ------------------------------------------------------------------ FEN
    def carregar_fen(self, fen: str) -> None:
        partes = fen.strip().split()
        while len(partes) < 6:
            partes.append("-" if len(partes) < 4 else "0")
        posicao, turno, roques, ep, meio, cheio = partes[:6]

        self.casas = [VAZIO] * 64
        indice = 0
        for caractere in posicao:
            if caractere == "/":
                continue
            if caractere.isdigit():
                indice += int(caractere)
            else:
                if indice < 64:
                    self.casas[indice] = caractere
                indice += 1
        self.turno = BRANCAS if turno == "w" else PRETAS
        self.roques = set(c for c in roques if c in "KQkq")
        self.en_passant = casa_para_indice(ep) if ep not in ("-", "") else None
        self.meio_lances = int(meio) if str(meio).isdigit() else 0
        self.lance_numero = int(cheio) if str(cheio).isdigit() else 1
        self.historico_hash = [self.chave()]

    def fen(self) -> str:
        linhas = []
        for linha in range(8):
            texto, vazias = "", 0
            for coluna in range(8):
                peca = self.casas[linha * 8 + coluna]
                if peca == VAZIO:
                    vazias += 1
                else:
                    if vazias:
                        texto += str(vazias)
                        vazias = 0
                    texto += peca
            if vazias:
                texto += str(vazias)
            linhas.append(texto)
        roques = "".join(c for c in "KQkq" if c in self.roques) or "-"
        ep = indice_para_casa(self.en_passant) if self.en_passant is not None else "-"
        return (f"{'/'.join(linhas)} {'w' if self.turno == BRANCAS else 'b'} "
                f"{roques} {ep} {self.meio_lances} {self.lance_numero}")

    def _en_passant_relevante(self) -> bool:
        """Se o alvo de en passant realmente muda os lances legais da posição.

        Para repetição, o alvo EP só diferencia posições quando existe captura EP
        legal. Isso evita uma falsa diferença causada por um peão ter avançado duas
        casas sem que o adversário pudesse capturá-lo.
        """
        if self.en_passant is None:
            return False
        ep = self.en_passant
        linha = ep // 8
        esperado = 2 if self.turno == BRANCAS else 5
        if linha != esperado:
            return False
        cor = self.turno
        peao = "P" if cor == BRANCAS else "p"
        capturada = "p" if cor == BRANCAS else "P"
        alvo_capturada = ep + (8 if cor == BRANCAS else -8)
        if not (0 <= alvo_capturada < 64) or self.casas[alvo_capturada] != capturada:
            return False
        for delta_col in (-1, 1):
            origem = ep + (8 if cor == BRANCAS else -8) + delta_col
            # A fórmula acima pode cruzar a borda; valide pela coluna.
            if not 0 <= origem < 64:
                continue
            if abs((origem % 8) - (ep % 8)) != 1:
                continue
            if self.casas[origem] != peao:
                continue
            lance = Lance(origem, ep, captura=capturada, en_passant=True)
            filho = self.copia()
            filho._aplicar(lance)
            if not filho.em_xeque(cor):
                return True
        return False

    def chave(self) -> str:
        """Identidade da posição para as regras de repetição.

        O contador de meio-lances e o número do lance não fazem parte da
        identidade. O alvo de en passant só entra quando uma captura EP é legal.
        """
        partes = self.fen().split()[:3]
        ep = indice_para_casa(self.en_passant) if self._en_passant_relevante() else "-"
        return " ".join(partes + [ep])

    def copia(self):
        novo = Tabuleiro.__new__(Tabuleiro)
        novo.casas = list(self.casas)
        novo.turno = self.turno
        novo.roques = set(self.roques)
        novo.en_passant = self.en_passant
        novo.meio_lances = self.meio_lances
        novo.lance_numero = self.lance_numero
        novo.historico_hash = list(self.historico_hash)
        return novo

    # --------------------------------------------------------------- básico
    def cor_da(self, indice: int):
        peca = self.casas[indice]
        if peca == VAZIO:
            return None
        return BRANCAS if peca.isupper() else PRETAS

    def rei(self, cor: str):
        alvo = "K" if cor == BRANCAS else "k"
        try:
            return self.casas.index(alvo)
        except ValueError:
            return None

    def atacada(self, indice: int, por: str) -> bool:
        """A casa está sob ataque de `por`? Base do xeque e do roque."""
        inimigo_peao = "P" if por == BRANCAS else "p"
        # Peão ataca na diagonal, para frente do ponto de vista dele.
        for delta in ((7, 9) if por == BRANCAS else (-7, -9)):
            origem = indice + delta
            if 0 <= origem < 64 and abs((origem % 8) - (indice % 8)) == 1:
                if self.casas[origem] == inimigo_peao:
                    return True
        for delta in DIRECOES["N"]:
            destino = indice + delta
            if _dentro(indice, destino, delta):
                peca = self.casas[destino]
                if peca != VAZIO and peca.upper() == "N" and self.cor_da(destino) == por:
                    return True
        for delta in DIRECOES["K"]:
            destino = indice + delta
            if _dentro(indice, destino, delta):
                peca = self.casas[destino]
                if peca != VAZIO and peca.upper() == "K" and self.cor_da(destino) == por:
                    return True
        for grupo, tipos in (("B", "BQ"), ("R", "RQ")):
            for delta in DIRECOES[grupo]:
                atual = indice
                while True:
                    destino = atual + delta
                    if not _dentro(atual, destino, delta):
                        break
                    peca = self.casas[destino]
                    if peca != VAZIO:
                        if peca.upper() in tipos and self.cor_da(destino) == por:
                            return True
                        break
                    atual = destino
        return False

    def em_xeque(self, cor: str = None) -> bool:
        cor = cor or self.turno
        casa_rei = self.rei(cor)
        if casa_rei is None:
            return False
        return self.atacada(casa_rei, PRETAS if cor == BRANCAS else BRANCAS)

    # ---------------------------------------------------------- geração
    def pseudolegais(self, apenas_capturas: bool = False) -> list:
        lances = []
        cor = self.turno
        for origem in range(64):
            peca = self.casas[origem]
            if peca == VAZIO or self.cor_da(origem) != cor:
                continue
            tipo = peca.upper()
            if tipo == "P":
                self._lances_peao(origem, cor, lances, apenas_capturas)
            elif tipo in DESLIZANTES:
                for delta in DIRECOES[tipo]:
                    atual = origem
                    while True:
                        destino = atual + delta
                        if not _dentro(atual, destino, delta):
                            break
                        alvo = self.casas[destino]
                        if alvo == VAZIO:
                            if not apenas_capturas:
                                lances.append(Lance(origem, destino))
                        else:
                            if self.cor_da(destino) != cor and alvo.upper() != "K":
                                lances.append(Lance(origem, destino, captura=alvo))
                            break
                        atual = destino
            else:  # cavalo e rei
                for delta in DIRECOES[tipo]:
                    destino = origem + delta
                    if not _dentro(origem, destino, delta):
                        continue
                    alvo = self.casas[destino]
                    if alvo == VAZIO:
                        if not apenas_capturas:
                            lances.append(Lance(origem, destino))
                    elif self.cor_da(destino) != cor and alvo.upper() != "K":
                        lances.append(Lance(origem, destino, captura=alvo))
                if tipo == "K" and not apenas_capturas:
                    self._lances_roque(origem, cor, lances)
        return lances

    def _lances_peao(self, origem, cor, lances, apenas_capturas):
        direcao = -8 if cor == BRANCAS else 8
        linha_inicial = 6 if cor == BRANCAS else 1
        linha_promocao = 0 if cor == BRANCAS else 7
        linha_atual = origem // 8

        frente = origem + direcao
        if not apenas_capturas and 0 <= frente < 64 and self.casas[frente] == VAZIO:
            if frente // 8 == linha_promocao:
                for promo in "QRBN":
                    lances.append(Lance(origem, frente,
                                        promocao=promo if cor == BRANCAS else promo.lower()))
            else:
                lances.append(Lance(origem, frente))
                duplo = origem + 2 * direcao
                if linha_atual == linha_inicial and self.casas[duplo] == VAZIO:
                    lances.append(Lance(origem, duplo))

        for delta in (direcao - 1, direcao + 1):
            destino = origem + delta
            if not 0 <= destino < 64:
                continue
            if abs((destino % 8) - (origem % 8)) != 1:
                continue
            alvo = self.casas[destino]
            if alvo != VAZIO and self.cor_da(destino) != cor and alvo.upper() != "K":
                if destino // 8 == linha_promocao:
                    for promo in "QRBN":
                        lances.append(Lance(origem, destino,
                                            promocao=promo if cor == BRANCAS else promo.lower(),
                                            captura=alvo))
                else:
                    lances.append(Lance(origem, destino, captura=alvo))
            elif destino == self.en_passant and alvo == VAZIO:
                capturada = "p" if cor == BRANCAS else "P"
                lances.append(Lance(origem, destino, captura=capturada, en_passant=True))

    def _lances_roque(self, origem, cor, lances):
        inimigo = PRETAS if cor == BRANCAS else BRANCAS
        if self.em_xeque(cor):
            return
        if cor == BRANCAS and origem == 60:
            if "K" in self.roques and self.casas[61] == VAZIO and self.casas[62] == VAZIO \
                    and self.casas[63] == "R" \
                    and not self.atacada(61, inimigo) and not self.atacada(62, inimigo):
                lances.append(Lance(60, 62, roque="K"))
            if "Q" in self.roques and all(self.casas[i] == VAZIO for i in (57, 58, 59)) \
                    and self.casas[56] == "R" \
                    and not self.atacada(59, inimigo) and not self.atacada(58, inimigo):
                lances.append(Lance(60, 58, roque="Q"))
        elif cor == PRETAS and origem == 4:
            if "k" in self.roques and self.casas[5] == VAZIO and self.casas[6] == VAZIO \
                    and self.casas[7] == "r" \
                    and not self.atacada(5, inimigo) and not self.atacada(6, inimigo):
                lances.append(Lance(4, 6, roque="k"))
            if "q" in self.roques and all(self.casas[i] == VAZIO for i in (1, 2, 3)) \
                    and self.casas[0] == "r" \
                    and not self.atacada(3, inimigo) and not self.atacada(2, inimigo):
                lances.append(Lance(4, 2, roque="q"))

    def legais(self, apenas_capturas: bool = False) -> list:
        cor = self.turno
        saida = []
        for lance in self.pseudolegais(apenas_capturas):
            copia = self.copia()
            copia._aplicar(lance)
            if not copia.em_xeque(cor):
                saida.append(lance)
        return saida

    # --------------------------------------------------------------- lances
    def _aplicar(self, lance: Lance) -> None:
        """Move sem validar. Uso interno — `jogar` é a porta de entrada."""
        peca = self.casas[lance.origem]
        cor = self.cor_da(lance.origem)
        capturou = lance.captura != VAZIO or lance.en_passant

        self.casas[lance.origem] = VAZIO
        self.casas[lance.destino] = lance.promocao or peca

        if lance.en_passant:
            atras = lance.destino + (8 if cor == BRANCAS else -8)
            self.casas[atras] = VAZIO

        if lance.roque == "K":
            self.casas[63], self.casas[61] = VAZIO, "R"
        elif lance.roque == "Q":
            self.casas[56], self.casas[59] = VAZIO, "R"
        elif lance.roque == "k":
            self.casas[7], self.casas[5] = VAZIO, "r"
        elif lance.roque == "q":
            self.casas[0], self.casas[3] = VAZIO, "r"

        # Direitos de roque: perdem-se ao mexer rei/torre ou ao capturar a torre.
        if peca == "K":
            self.roques -= {"K", "Q"}
        elif peca == "k":
            self.roques -= {"k", "q"}
        for casa, direito in ((63, "K"), (56, "Q"), (7, "k"), (0, "q")):
            if lance.origem == casa or lance.destino == casa:
                self.roques.discard(direito)

        self.en_passant = None
        if peca.upper() == "P" and abs(lance.destino - lance.origem) == 16:
            self.en_passant = (lance.origem + lance.destino) // 2

        self.meio_lances = 0 if (peca.upper() == "P" or capturou) else self.meio_lances + 1
        if self.turno == PRETAS:
            self.lance_numero += 1
        self.turno = PRETAS if self.turno == BRANCAS else BRANCAS

    def jogar(self, lance) -> bool:
        """Executa um lance legal. Aceita objeto Lance, UCI ('e2e4') ou SAN ('Nf3')."""
        if isinstance(lance, str):
            convertido = self.interpretar(lance)
            if convertido is None:
                return False
            lance = convertido
        if lance not in self.legais():
            return False
        completo = next(l for l in self.legais() if l == lance)
        self._aplicar(completo)
        self.historico_hash.append(self.chave())
        return True

    def interpretar(self, texto: str):
        """UCI ou SAN -> Lance legal correspondente."""
        texto = (texto or "").strip()
        if not texto:
            return None
        if re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbnQRBN]?", texto):
            origem, destino = casa_para_indice(texto[:2]), casa_para_indice(texto[2:4])
            promo = texto[4:].upper() if len(texto) > 4 else ""
            if promo and self.turno == PRETAS:
                promo = promo.lower()
            for lance in self.legais():
                if lance.origem == origem and lance.destino == destino \
                        and (lance.promocao or "").upper() == (promo or "").upper():
                    return lance
            return None
        return self.interpretar_san(texto)

    def interpretar_san(self, san: str):
        """Interpreta SAN de xadrez padrão e exige desambiguação correta."""
        texto = (san or "").strip()
        if not texto:
            return None
        texto = re.sub(r"^\d+\.(?:\.\.)?\s*", "", texto)
        texto = re.sub(r"^\d+\.\.\.\s*", "", texto)
        texto = re.sub(r"\s*(?:e\.?p\.?|ep)$", "", texto, flags=re.IGNORECASE)
        texto = texto.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
        # Indicadores de xeque/mate e anotações NAGs não mudam o lance.
        texto = re.sub(r"[+#]+$", "", texto)
        texto = re.sub(r"[!?]+$", "", texto)
        if texto.lower() in ("o-o",):
            return next((l for l in self.legais() if l.roque in ("K", "k")), None)
        if texto.lower() in ("o-o-o",):
            return next((l for l in self.legais() if l.roque in ("Q", "q")), None)

        m = re.fullmatch(
            r"(?P<tipo>[KQRBN])?(?P<origem_file>[a-h])?(?P<origem_rank>[1-8])?"
            r"(?P<captura>x)?(?P<destino>[a-h][1-8])"
            r"(?:=(?P<promocao>[QRBN]))?", texto
        )
        if not m:
            return None
        tipo = m.group("tipo") or "P"
        origem_file = m.group("origem_file")
        origem_rank = m.group("origem_rank")
        quer_captura = bool(m.group("captura"))
        destino = casa_para_indice(m.group("destino"))
        promocao = (m.group("promocao") or "").upper()

        candidatos = []
        for lance in self.legais():
            peca = self.casas[lance.origem].upper()
            if peca != tipo or lance.destino != destino:
                continue
            eh_captura = lance.captura != VAZIO or lance.en_passant
            if eh_captura != quer_captura:
                continue
            if promocao:
                if (lance.promocao or "").upper() != promocao:
                    continue
            elif lance.promocao:
                continue
            origem_txt = indice_para_casa(lance.origem)
            if origem_file and origem_txt[0] != origem_file:
                continue
            if origem_rank and origem_txt[1] != origem_rank:
                continue
            candidatos.append(lance)

        # SAN ambígua sem os dados de desambiguação corretos é inválida.
        if len(candidatos) != 1:
            return None
        return candidatos[0]

    def san(self, lance: Lance) -> str:
        """Notação algébrica do lance, no contexto desta posição."""
        if lance.roque in ("K", "k"):
            texto = "O-O"
        elif lance.roque in ("Q", "q"):
            texto = "O-O-O"
        else:
            peca = self.casas[lance.origem].upper()
            captura = lance.captura != VAZIO or lance.en_passant
            if peca == "P":
                texto = (indice_para_casa(lance.origem)[0] + "x" if captura else "") \
                        + indice_para_casa(lance.destino)
                if lance.promocao:
                    texto += "=" + lance.promocao.upper()
            else:
                ambiguos = [l for l in self.legais()
                            if l.destino == lance.destino and l.origem != lance.origem
                            and self.casas[l.origem].upper() == peca]
                desambigua = ""
                if ambiguos:
                    origem_txt = indice_para_casa(lance.origem)
                    if all(indice_para_casa(l.origem)[0] != origem_txt[0] for l in ambiguos):
                        desambigua = origem_txt[0]
                    elif all(indice_para_casa(l.origem)[1] != origem_txt[1] for l in ambiguos):
                        desambigua = origem_txt[1]
                    else:
                        desambigua = origem_txt
                texto = peca + desambigua + ("x" if captura else "") \
                    + indice_para_casa(lance.destino)

        copia = self.copia()
        copia._aplicar(lance)
        if copia.em_xeque(copia.turno):
            texto += "#" if not copia.legais() else "+"
        return texto

    # ------------------------------------------------------------- término
    def material_insuficiente(self) -> bool:
        """Casos comuns de material que tornam o mate impossível.

        Não usa a aproximação "até dois menores = empate", porque isso declara
        incorretamente posições como K+B+B vs K como mortas.
        """
        pecas = [(i, p) for i, p in enumerate(self.casas) if p != VAZIO]
        tipos = [p.upper() for _, p in pecas if p.upper() != "K"]
        if any(t in ("P", "R", "Q") for t in tipos):
            return False

        # K vs K
        if not tipos:
            return True
        # K+B vs K / K+N vs K
        if len(tipos) == 1 and tipos[0] in ("B", "N"):
            return True
        # K+B vs K+B: só é material morto quando os bispos vivem na mesma cor.
        if len(tipos) == 2 and all(t == "B" for t in tipos):
            bispos = [i for i, p in pecas if p.upper() == "B"]
            cores = [(i // 8 + i % 8) % 2 for i in bispos]
            return len(cores) == 2 and cores[0] == cores[1]
        return False

    def repeticao_tripla(self) -> bool:
        """Verdadeiro quando a posição atual ocorreu pelo menos 3 vezes."""
        return bool(self.historico_hash) and self.historico_hash.count(self.chave()) >= 3

    def repeticao_quintupla(self) -> bool:
        """Cinco ocorrências: empate automático pelas regras FIDE."""
        return bool(self.historico_hash) and self.historico_hash.count(self.chave()) >= 5

    def pode_reivindicar_repeticao(self) -> bool:
        return self.repeticao_tripla()

    def pode_reivindicar_50(self) -> bool:
        return self.meio_lances >= 100

    def regra_75_lances(self) -> bool:
        """75 lances completos sem peão mover nem captura (150 meios-lances)."""
        return self.meio_lances >= 150

    def empate_reivindicavel(self) -> str | None:
        """Motivo de empate que um jogador pode reivindicar agora."""
        if self.repeticao_tripla():
            return "repetição tripla"
        if self.pode_reivindicar_50():
            return "regra dos 50 lances"
        return None

    def resultado(self, reivindicar: bool = False):
        """Resultado segundo regras padrão. `reivindicar=True` aceita empate reclamável."""
        legais = self.legais()
        if not legais:
            if self.em_xeque():
                return "0-1" if self.turno == BRANCAS else "1-0"
            return "1/2-1/2"
        if self.regra_75_lances():
            return "1/2-1/2"
        if self.repeticao_quintupla():
            return "1/2-1/2"
        if self.material_insuficiente():
            return "1/2-1/2"
        if reivindicar and self.empate_reivindicavel():
            return "1/2-1/2"
        return None

    def motivo_do_fim(self, reivindicar: bool = False) -> str:
        legais = self.legais()
        if not legais:
            return "xeque-mate" if self.em_xeque() else "afogamento (rei sem lance legal)"
        if self.regra_75_lances():
            return "regra dos 75 lances"
        if self.repeticao_quintupla():
            return "repetição quíntupla"
        if self.material_insuficiente():
            return "posição morta / material insuficiente"
        if reivindicar:
            motivo = self.empate_reivindicavel()
            if motivo:
                return motivo
        return ""

    # -------------------------------------------------------------- desenho
    def desenhar(self, invertido: bool = False) -> str:
        linhas = []
        faixas = range(8) if not invertido else range(7, -1, -1)
        for linha in faixas:
            colunas = range(8) if not invertido else range(7, -1, -1)
            casas = " ".join(UNICODE.get(self.casas[linha * 8 + c], "·") for c in colunas)
            linhas.append(f"{8 - linha} {casas}")
        rodape = "  " + " ".join("abcdefgh" if not invertido else "hgfedcba")
        return "\n".join(linhas) + "\n" + rodape


def perft(tabuleiro: Tabuleiro, profundidade: int) -> int:
    """Conta folhas da árvore de lances legais — o teste padrão de corretude."""
    if profundidade == 0:
        return 1
    total = 0
    for lance in tabuleiro.legais():
        copia = tabuleiro.copia()
        copia._aplicar(lance)
        total += perft(copia, profundidade - 1)
    return total
