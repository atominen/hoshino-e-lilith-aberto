"""Ensaio offline com Conditioning do Pestinha, recebido por caminho local."""
import argparse
from copy import deepcopy
import importlib
import statistics
import sys
from pathlib import Path
from time import perf_counter_ns


def episode(model, cue, hit, start):
    model.set_cue(cue, True, start)
    model.set_cue(cue, False, start + 0.2)
    if hit:
        model.outcome(start + 0.4, cues=(cue,))
    model.tick(start + 2.0)


def run(conditioning):
    model = conditioning()
    hostile, neutral = "arqueiro_mirando", "arqueiro_passando"
    for i in range(12):
        episode(model, hostile, True, i * 6)
        episode(model, neutral, False, i * 6 + 3)
    scores = {cue: model.V[cue] for cue in (hostile, neutral)}
    assert scores[hostile] > 0.75 and scores[neutral] == 0

    # A pista é observada antes do dano simulado. A proximidade, usada como
    # referência simples, é igual nos dois casos. Incluímos um erro de cada tipo.
    cases = [(hostile, True)] * 8 + [(neutral, False)] * 8
    cases += [(hostile, False), (neutral, True)]
    detectors = {cue: deepcopy(model) for cue in scores}
    for cue, detector in detectors.items():
        detector.set_cue(cue, True, 80)
    for label, predict in (
        ("Proximidade", lambda cue: True),
        ("Associação", lambda cue: detectors[cue].strength((cue,)) >= 0.6),
    ):
        pairs = [(predict(cue), hit) for cue, hit in cases]
        print(f"{label}: {pairs.count((True, True))} alertas corretos, "
              f"{pairs.count((True, False))} falsos alertas, "
              f"{pairs.count((False, True))} ameaças perdidas.")

    durations = []
    for _ in range(5):
        start = perf_counter_ns()
        for i in range(20_000):
            detectors[hostile].strength((hostile,)) >= 0.6
        durations.append((perf_counter_ns() - start) / 20_000 / 1000)
    print(f"Consulta da associação na CPU: {statistics.median(durations):.2f} µs em média por chamada "
          "(mediana de 5 lotes).")

    for i in range(12):
        episode(model, hostile, False, 100 + i * 3)
    faded = model.V[hostile]
    assert faded < 0.25
    print(f"Associação do arqueiro mirando: {scores[hostile]:.3f} após treino; "
          f"{faded:.3f} após 12 ocorrências sem dano.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="Diretório que contém pestinha/core/conditioning.py")
    args = parser.parse_args()
    if not (args.upstream / "pestinha/core/conditioning.py").is_file():
        parser.error("pestinha/core/conditioning.py não encontrado")
    sys.path.insert(0, str(args.upstream.resolve()))
    run(importlib.import_module("pestinha.core.conditioning").Conditioning)
