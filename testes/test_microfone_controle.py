"""Testes sem hardware para modos/normalização do controle de microfone."""
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

import config  # noqa: E402
config.RUNTIME_DIR = tempfile.mkdtemp(prefix="hoshino_mic_ctrl_")

from tools.microfone_controle import GlobalPTT, ControleMicrofone  # noqa: E402

ok = 0
falhas = []

def checar(desc, cond):
    global ok
    if cond:
        ok += 1
        print("  ok  ", desc)
    else:
        falhas.append(desc)
        print("  FALHA", desc)

print("== Controle de microfone ==")
checar("ctrl+shift+space normaliza", GlobalPTT._normalizar_hotkey("ctrl + shift + space") == "<ctrl>+<shift>+<space>")
checar("atalho de letra preserva letra", GlobalPTT._normalizar_hotkey("ctrl+alt+m") == "<ctrl>+<alt>+m")
checar("atalho F8 aceita tecla especial", GlobalPTT._normalizar_hotkey("ctrl+F8") == "<ctrl>+<f8>")
checar("atalho vazio recusa", GlobalPTT._normalizar_hotkey("") == "")
checar("alias pressionado -> segurar", __import__("tools.microfone_controle", fromlist=["_ALIASES_MODO"])._ALIASES_MODO["pressionado"] == "segurar")
checar("alias continuo -> aberto", __import__("tools.microfone_controle", fromlist=["_ALIASES_MODO"])._ALIASES_MODO["continuo"] == "aberto")
print(f"{ok} verificacoes ok, {len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
