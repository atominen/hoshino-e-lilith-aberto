#!/usr/bin/env python3
"""Executa sd-cli sem deixá-lo órfão se o worker morrer (Linux)."""
import ctypes
import os
import signal
import sys


def main():
    parent = int(sys.argv[1])
    command = sys.argv[2:]
    if not command or not os.path.isabs(command[0]):
        raise ValueError("executável de imagem absoluto obrigatório")
    if sys.platform != "linux":
        raise RuntimeError("supervisão de morte do worker requer Linux")
    # Executado num interpretador novo e sem threads. Evita preexec_fn num
    # processo multithread e cobre também a morte abrupta da thread do worker.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), "não foi possível supervisionar sd-cli")
    if os.getppid() != parent:
        return 1  # Fecha a corrida entre criar o processo e registrar o sinal.
    os.execv(command[0], command)


if __name__ == "__main__":
    raise SystemExit(main())
