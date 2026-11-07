#!/usr/bin/env python3
"""Diagnóstico independente do atalho global do microfone.

Uso:
  python3 scripts/testar_atalho_global.py
  python3 scripts/testar_atalho_global.py '<f2>'
  python3 scripts/testar_atalho_global.py '<ctrl>+<shift>+<space>'

Se aparecer "ATIVADO", o pynput está vendo a combinação globalmente. Ctrl+C sai.
"""
from __future__ import annotations

import os
import sys

try:
    from pynput import keyboard
except Exception as exc:
    print(f"ERRO: não consegui importar pynput: {type(exc).__name__}: {exc}")
    raise SystemExit(2)

hotkey_text = sys.argv[1] if len(sys.argv) > 1 else "<f2>"
print(f"Sessão: {os.environ.get('XDG_SESSION_TYPE', 'desconhecida')}")
print(f"Atalho: {hotkey_text}")
print("Pressione e solte a combinação. Ctrl+C encerra.")


def ativou():
    print("ATIVADO: o sistema recebeu a combinação global.", flush=True)


def para_canonico(funcao):
    def wrapper(key):
        return funcao(listener.canonical(key))
    return wrapper


try:
    hotkey = keyboard.HotKey(keyboard.HotKey.parse(hotkey_text), ativou)
    listener = keyboard.Listener(
        on_press=para_canonico(hotkey.press),
        on_release=para_canonico(hotkey.release),
    )
    listener.start()
    listener.wait()
    listener.join()
except KeyboardInterrupt:
    print("Encerrado.")
except Exception as exc:
    print(f"ERRO no listener global: {type(exc).__name__}: {exc}")
    raise SystemExit(1)
