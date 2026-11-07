"""Testes independentes das regras de xadrez padrão da Hoshino."""
import os
import sys

# Sem isto o arquivo só rodava via pytest a partir da raiz; chamado direto
# (python3 testes/test_xadrez_real.py) quebrava com ModuleNotFoundError.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from play.chess.board import Tabuleiro, perft  # noqa: E402


def test_perft_posicao_inicial():
    assert perft(Tabuleiro(), 3) == 8902
    assert perft(Tabuleiro(), 4) == 197281


def test_perft_kiwipete():
    fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    assert perft(Tabuleiro(fen), 2) == 2039
    assert perft(Tabuleiro(fen), 3) == 97862


def test_regras_king_capture_and_ambiguity_san():
    b = Tabuleiro("8/8/8/8/8/8/4k3/4K3 w - - 0 1")
    assert b.legais() == []

    b = Tabuleiro("4k3/8/8/8/8/8/8/1N3NK1 w - - 0 1")
    assert b.interpretar("Nd2") is None
    assert b.interpretar("Nbd2") is not None
    assert b.interpretar("Nfd2") is not None
    assert b.interpretar("Nxd2") is None


def test_repetition_ep_relevante():
    sem_ep = Tabuleiro("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    ep_impossivel = Tabuleiro("4k3/8/8/8/8/8/8/4K3 w - e3 0 1")
    assert sem_ep.chave() == ep_impossivel.chave()

    com_ep = Tabuleiro("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    sem_ep_legal = Tabuleiro("4k3/8/8/3pP3/8/8/8/4K3 w - - 0 1")
    assert com_ep.chave() != sem_ep_legal.chave()
    assert any(l.en_passant for l in com_ep.legais())


def test_draw_rules_fide_style():
    b = Tabuleiro()
    for uci in ["b1c3", "b8c6", "c3b1", "c6b8"] * 2:
        assert b.jogar(uci)
    assert b.repeticao_tripla()
    assert b.empate_reivindicavel() == "repetição tripla"
    assert b.resultado() is None

    b50 = Tabuleiro("7k/8/8/8/8/8/6R1/K7 w - - 100 1")
    assert b50.resultado() is None
    assert b50.empate_reivindicavel() == "regra dos 50 lances"

    b75 = Tabuleiro("7k/8/8/8/8/8/6R1/K7 w - - 150 1")
    assert b75.resultado() == "1/2-1/2"
    assert b75.motivo_do_fim() == "regra dos 75 lances"


def test_dead_material_sem_falso_empate():
    # K+B vs K = morto.
    assert Tabuleiro("7k/8/8/8/8/8/6B1/K7 w - - 0 1").material_insuficiente()
    # K+B vs K+B de cores diferentes não é declarado morto automaticamente.
    assert not Tabuleiro("6b1/k7/8/8/8/8/8/K5B1 w - - 0 1").material_insuficiente()
    # K+B+B vs K pode dar mate: não é material insuficiente.
    assert not Tabuleiro("7k/8/8/8/8/8/5BB1/K7 w - - 0 1").material_insuficiente()


def test_san_e_mate():
    b = Tabuleiro()
    for movimento in ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6"]:
        lance = b.interpretar(movimento)
        assert lance is not None
        assert b.jogar(lance)
    lance = b.interpretar("Qxf7#")
    assert lance is not None
    assert b.san(lance) == "Qxf7#"
    assert b.jogar(lance)
    assert b.resultado() == "1-0"


if __name__ == "__main__":
    # Runner próprio: os outros testes do projeto rodam com `python3 arquivo.py`
    # e este só rodava sob pytest, que nem sempre está instalado no venv.
    import traceback
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    ok, falhas = 0, []
    for nome, func in testes:
        try:
            func()
            ok += 1
            print(f"  ok   {nome}")
        except Exception:
            falhas.append(nome)
            print(f"  FALHA {nome}")
            traceback.print_exc()
    print(f"\n{ok} testes ok, {len(falhas)} falha(s)")
    raise SystemExit(1 if falhas else 0)
