"""Regressões do atalho global e dos dois modos do microfone, sem hardware."""
import os
import sys
import tempfile
import types

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

import config  # noqa: E402
config.RUNTIME_DIR = tempfile.mkdtemp(prefix="hoshino_mic_v22_")

from tools.microfone_controle import ControleMicrofone, GlobalPTT  # noqa: E402


class FakeTranscritor:
    gravando = False
    escutando = False

    def pronto(self):
        return True

    def comecar(self):
        self.gravando = True
        return "Gravando (fake)."

    def parar(self):
        self.gravando = False
        return {"texto": "ola hoshino", "segundos": 1.0, "motivo": ""}

    def iniciar_escuta(self):
        self.escutando = True
        return "Escutando (fake)."

    def parar_escuta(self):
        self.escutando = False
        return "Parei de escutar."

    def estado(self):
        return "fake"


class FakeHotKey:
    @staticmethod
    def parse(value):
        return tuple(value.split("+"))

    def __init__(self, keys, callback):
        self.keys = set(keys)
        self.callback = callback
        self.pressed = set()
        self.activated = False

    def press(self, key):
        self.pressed.add(key)
        if self.keys.issubset(self.pressed) and not self.activated:
            self.activated = True
            self.callback()

    def release(self, key):
        self.pressed.discard(key)
        if key not in self.keys:
            return
        self.activated = False


class FakeListener:
    def __init__(self, on_press=None, on_release=None):
        self.on_press = on_press
        self.on_release = on_release
        self.running = False

    def canonical(self, key):
        return key

    def start(self):
        self.running = True

    def wait(self, timeout=None):
        return True

    def stop(self):
        self.running = False


def install_fake_pynput(monkeypatch=None):
    class FakeKeyboard:
        @staticmethod
        def parse(value):
            return tuple(value.split("+"))

        HotKey = FakeHotKey
        Listener = FakeListener

    sys.modules["pynput"] = types.SimpleNamespace(keyboard=FakeKeyboard)


def test_pressao_inicia_e_soltar_transcreve():
    install_fake_pynput()
    estados = []
    resultados = []
    t = FakeTranscritor()
    g = GlobalPTT(t, on_result=resultados.append, on_state=estados.append)
    g.modo = "pressionado"
    assert g.iniciar().startswith("Atalho global ativo")
    # A combinação fake usa exatamente as três teclas configuradas.
    keys = tuple(g._hotkey_obj.keys)
    for key in keys:
        g._on_press(key)
    g._on_release('unrelated-key')
    assert t.gravando  # Unrelated release must not end an engaged shortcut.
    assert t.gravando
    for key in keys:
        g._on_release(key)
    assert resultados and resultados[0]["texto"] == "ola hoshino"
    assert "pressionado" in estados
    g.parar()


def test_modo_aberto_usa_o_mesmo_atalho_para_alternar():
    install_fake_pynput()
    estados = []
    t = FakeTranscritor()
    g = GlobalPTT(t, on_state=estados.append)
    g.modo = "aberto"
    assert g.iniciar().startswith("Atalho global ativo")
    keys = tuple(g._hotkey_obj.keys)
    for key in keys:
        g._on_press(key)
    assert t.escutando
    for key in keys:
        g._on_release(key)
    # Segunda ativação desliga.
    for key in keys:
        g._on_press(key)
    assert not t.escutando
    assert "aberto" in estados and "aberto_fechado" in estados
    g.parar()


def test_aliases_de_modo_sao_aceitos():
    t = FakeTranscritor()
    c = ControleMicrofone(t)
    assert c.definir_modo("continuo") != "Erro: modo precisa ser fechado, aberto ou pressionado."
    c.ptt.parar()
    t.escutando = False
    assert c.definir_modo("apertar").startswith("Microfone por PRESSIONAR")
    c.fechar()


if __name__ == "__main__":
    test_pressao_inicia_e_soltar_transcreve()
    test_modo_aberto_usa_o_mesmo_atalho_para_alternar()
    test_aliases_de_modo_sao_aceitos()
    print("3 testes de microfone passaram")
