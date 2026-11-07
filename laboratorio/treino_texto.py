"""Entrada histórica aposentada; execução atual em treino_nf4_curto.
Código anterior permanece no histórico Git; nenhum peso/relatório é removido.
"""
import argparse, json, os, random, time, signal
from pathlib import Path

STOP=False
def stop(*_):
    global STOP;STOP=True


def main():
    raise RuntimeError('Runner histórico aposentado. Use laboratorio.treino_nf4_curto / treinos_unificados.')


if __name__=='__main__':main()
