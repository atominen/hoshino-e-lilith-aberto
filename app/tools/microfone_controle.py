"""Controle global do microfone: fechado, aberto e push-to-talk.

O modo push-to-talk usa pynput para escutar o teclado em nível global (X11),
sem depender de qual janela está em foco. Enquanto o atalho configurado estiver
pressionado, o Transcritor abre o microfone. Ao soltar, o áudio é fechado e
transcrito em uma thread separada.

Um pequeno indicador Tkinter fica acima das janelas normais enquanto o PTT está
ativo. Ele não recebe foco nem cliques.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Callable, Optional

if __name__ == '__main__':
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import config


_MODOS = ("fechado", "aberto", "pressionado")
# Rótulos de compatibilidade legados mantidos para integrações existentes.
_ALIASES_MODO = {"pressionado": "segurar", "continuo": "aberto", "apertar": "pressionado", "ptt": "pressionado"}
_DEFAULT_HOTKEY = os.environ.get("HOSHINO_MIC_PTT", getattr(config, "MIC_PTT_ATALHO", "<ctrl>+<alt>+space"))


class MicOverlay:
    """Overlay visual discreto que aparece somente durante o PTT."""

    def __init__(self) -> None:
        self._root = None
        self._label = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="hoshino-mic-overlay")
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def _run(self) -> None:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            root.title("Hoshino — Microfone")
            root.overrideredirect(True)
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            try:
                root.attributes("-alpha", 0.92)
            except Exception:
                pass
            try:
                root.attributes("-type", "splash")
            except Exception:
                pass

            label = tk.Label(
                root,
                text="🎤  HOSHINO • MICROFONE ABERTO  •  solte o atalho para fechar",
                font=("Sans", 11, "bold"),
                padx=18,
                pady=8,
                bd=0,
                relief="flat",
            )
            label.pack()
            self._root = root
            self._label = label
            self._ready.set()
            root.mainloop()
        except Exception:
            self._ready.set()

    def _ui(self, fn) -> None:
        root = self._root
        if root is None:
            return
        try:
            root.after(0, fn)
        except Exception:
            pass

    def show(self) -> None:
        def do_show():
            try:
                root = self._root
                label = self._label
                if not root or not label:
                    return
                root.update_idletasks()
                sw = root.winfo_screenwidth()
                x = max(8, (sw - root.winfo_reqwidth()) // 2)
                y = 20
                root.geometry(f"+{x}+{y}")
                root.deiconify()
                try:
                    root.lift()
                    root.attributes("-topmost", True)
                except Exception:
                    pass
            except Exception:
                pass
        self._ui(do_show)

    def hide(self) -> None:
        self._ui(lambda: self._root.withdraw() if self._root else None)

    def close(self) -> None:
        root = self._root
        if root is not None:
            self._ui(root.destroy)


class GlobalPTT:
    """Atalho global configurável para os dois modos públicos do microfone.

    * ``pressionado``: segurar a combinação grava; ao soltar, transcreve.
    * ``aberto``: pressionar a combinação liga/desliga a escuta contínua.

    O estado da combinação é delegado a ``pynput.keyboard.HotKey`` em vez de
    reconstruído manualmente. Isso normaliza Ctrl/Shift esquerdo/direito e evita
    os falsos negativos do listener manual anterior.
    """

    def __init__(self, transcritor, on_result: Optional[Callable[[dict], None]] = None,
                 on_state: Optional[Callable[[str], None]] = None, *, hotkey=None, overlay=None):
        self.transcritor = transcritor
        self.on_result = on_result
        self.on_state = on_state
        self.hotkey = self._normalizar_hotkey(hotkey) if hotkey else self._load_hotkey()
        self.ativo = False
        self.modo = "pressionado"
        self._listener = None
        self._hotkey_obj = None
        self._required_keys = set()
        self._lock = threading.RLock()
        self.overlay = overlay if overlay is not None else MicOverlay()

    # ------------------------------------------------------------ config
    @property
    def config_path(self) -> Path:
        return Path(config.RUNTIME_DIR) / "microfone.json"

    def _load_hotkey(self) -> str:
        caminho = self.config_path
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            valor = str(dados.get("ptt_atalho") or "").strip()
            if valor:
                return self._normalizar_hotkey(valor)
        except (OSError, ValueError, TypeError):
            pass
        return _DEFAULT_HOTKEY

    def _save(self) -> None:
        caminho = self.config_path
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            dados = {}
            try:
                dados = json.loads(caminho.read_text(encoding="utf-8"))
                if not isinstance(dados, dict):
                    dados = {}
            except (OSError, ValueError, TypeError):
                dados = {}
            dados["ptt_atalho"] = self.hotkey
            dados["modo"] = self.modo
            caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            try:
                from core import diagnostics
                diagnostics.exception("microphone.config_save_failed", exc)
            except Exception:
                pass

    def definir_atalho(self, hotkey: str) -> str:
        hotkey = self._normalizar_hotkey(hotkey)
        if not hotkey:
            return "Erro: atalho vazio."
        try:
            self._validar_hotkey(hotkey)
        except Exception as exc:
            return f"Erro no atalho do microfone: {type(exc).__name__}: {exc}"

        with self._lock:
            antigo = self.hotkey
            estava_ativo = self.ativo
            modo = self.modo
            if estava_ativo:
                self.parar()
            self.hotkey = hotkey
            self._save()
            if estava_ativo:
                self.modo = modo
                resultado = self.iniciar()
                if not self.ativo:
                    return resultado
        return f"Atalho do microfone: {antigo} → {self.hotkey}."

    @staticmethod
    def _validar_hotkey(hotkey: str) -> None:
        from pynput import keyboard
        teclas = keyboard.HotKey.parse(hotkey)
        if not teclas:
            raise ValueError("nenhuma tecla válida")

    @staticmethod
    def _normalizar_configuracao(hotkey: str) -> None:
        GlobalPTT._validar_hotkey(hotkey)

    @staticmethod
    def _normalizar_hotkey(hotkey: str) -> str:
        bruto = str(hotkey or "").strip().lower().replace(" ", "")
        if not bruto:
            return ""
        partes = []
        for p in bruto.split("+"):
            if not p:
                continue
            especiais = {
                "ctrl": "<ctrl>", "control": "<ctrl>",
                "alt": "<alt>", "shift": "<shift>",
                "cmd": "<cmd>", "win": "<cmd>", "super": "<cmd>", "meta": "<cmd>",
                "space": "<space>", "tab": "<tab>", "enter": "<enter>",
                "esc": "<esc>", "escape": "<esc>", "backspace": "<backspace>",
                "delete": "<delete>", "home": "<home>", "end": "<end>",
                "pageup": "<page_up>", "pagedown": "<page_down>",
                "up": "<up>", "down": "<down>", "left": "<left>", "right": "<right>",
            }
            if not (p.startswith("<") and p.endswith(">")):
                if p in especiais:
                    p = especiais[p]
                elif len(p) == 1:
                    p = p
                elif re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", p):
                    p = f"<{p}>"
            partes.append(p)
        return "+".join(partes)

    # ----------------------------------------------------------- listener
    def definir_modo(self, modo: str) -> None:
        if modo not in ("aberto", "pressionado"):
            raise ValueError("modo global inválido")
        self.modo = modo

    def _emit_state(self, estado: str) -> None:
        if self.on_state:
            try:
                self.on_state(estado)
            except Exception as exc:
                try:
                    from core import diagnostics
                    diagnostics.exception("microphone.on_state_failed", exc)
                except Exception:
                    pass

    def _on_activate(self) -> None:
        if not self.ativo:
            return
        if self.modo == "aberto":
            threading.Thread(target=self._alternar_aberto, daemon=True,
                             name="hoshino-mic-toggle").start()
        else:
            self._começar_ptt()

    def _começar_ptt(self) -> None:
        try:
            if self.transcritor.gravando:
                return
            self.overlay.show()
            resultado = self.transcritor.comecar()
            if isinstance(resultado, str) and resultado.lower().startswith(("não consegui", "erro", "nenhuma")):
                self.overlay.hide()
                self._emit_state("erro")
                self._log_callback("ptt_start_failed", resultado)
                return
            self._engaged = True
            self._emit_state("pressionado")
        except Exception as exc:
            self._engaged = False
            self.overlay.hide()
            self._emit_state("erro")
            self._log_exception("ptt_start_exception", exc)

    def _alternar_aberto(self) -> None:
        try:
            if self.transcritor.escutando:
                resultado = self.transcritor.parar_escuta()
                self._emit_state("aberto_fechado")
            else:
                resultado = self.transcritor.iniciar_escuta()
                if self.transcritor.escutando:
                    self._emit_state("aberto")
                else:
                    self._emit_state("erro")
            self._log_callback("mic_toggle", resultado)
            self._save()
        except Exception as exc:
            self._emit_state("erro")
            self._log_exception("mic_toggle_exception", exc)

    def _on_press(self, key) -> None:
        if not self.ativo:
            return
        try:
            self._hotkey_obj.press(self._listener.canonical(key))
        except Exception as exc:
            self._log_exception("global_key_press_exception", exc)

    def _on_release(self, key) -> None:
        if not self.ativo:
            return
        try:
            canon = self._listener.canonical(key)
            self._hotkey_obj.release(canon)
            if self.modo == "pressionado" and getattr(self, "_engaged", False) and canon in self._required_keys:
                # Qualquer tecla da combinação liberada encerra a gravação.
                self._engaged = False
                self.overlay.hide()
                self._emit_state("processando")
                threading.Thread(target=self._finalizar_fala, daemon=True,
                                 name="hoshino-ptt-transcricao").start()
        except Exception as exc:
            self._log_exception("global_key_release_exception", exc)

    def _finalizar_fala(self) -> None:
        try:
            resultado = self.transcritor.parar()
            if self.on_result:
                self.on_result(resultado)
            self._emit_state("pressionado_pronto")
        except Exception as exc:
            if self.on_result:
                try:
                    self.on_result({"texto": "", "motivo": f"falha PTT: {type(exc).__name__}: {exc}"})
                except Exception:
                    pass
            self._emit_state("erro")
            self._log_exception("ptt_stop_exception", exc)

    def _log_callback(self, evento: str, detalhe) -> None:
        try:
            from core import diagnostics
            diagnostics.emit(f"microphone.{evento}", hotkey=self.hotkey, modo=self.modo,
                             detalhe=detalhe if isinstance(detalhe, str) else str(detalhe))
        except Exception:
            pass

    def _log_exception(self, evento: str, exc: Exception) -> None:
        try:
            from core import diagnostics
            diagnostics.exception(f"microphone.{evento}", exc, hotkey=self.hotkey, modo=self.modo)
        except Exception:
            pass

    def iniciar(self) -> str:
        with self._lock:
            if self.ativo:
                return f"Atalho global já está ativo ({self.hotkey}, modo={self.modo})."
            sessao = os.environ.get("XDG_SESSION_TYPE", "").lower()
            if sessao == "wayland":
                return ("Atalho global do microfone indisponível nesta sessão Wayland. "
                        "Use X11 para captura global por pynput.")
            try:
                from pynput import keyboard
                self._required_keys = set(keyboard.HotKey.parse(self.hotkey))
                hotkey = keyboard.HotKey(self._required_keys, self._on_activate)
                self._hotkey_obj = hotkey
                self._engaged = False

                # Listener é recriado a cada iniciar(): pynput não permite reutilizar
                # uma thread Listener depois de stop().
                listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
                self._listener = listener
                listener.start()
                try:
                    listener.wait(timeout=1.5)
                except TypeError:
                    # Versões mais antigas podem não aceitar timeout.
                    pass
                self.ativo = True
                self._log_callback("listener_started", "ok")
                return f"Atalho global ativo: {self.hotkey} (modo={self.modo})."
            except Exception as exc:
                self._listener = None
                self._hotkey_obj = None
                self.ativo = False
                self._log_exception("listener_start_failed", exc)
                return f"Não consegui ativar o atalho global: {type(exc).__name__}: {exc}"

    def parar(self) -> str:
        with self._lock:
            self.ativo = False
            self._engaged = False
            self.overlay.hide()
            listener = self._listener
            self._listener = None
            self._hotkey_obj = None
            if self.transcritor.gravando:
                threading.Thread(target=self._finalizar_fala, daemon=True,
                                 name="hoshino-ptt-stop").start()
            if listener:
                try:
                    listener.stop()
                except Exception as exc:
                    self._log_exception("listener_stop_failed", exc)
            return "Atalho global do microfone desativado."

    def fechar(self) -> None:
        self.parar()
        self.overlay.close()


def central_hotkey(value):
    """Pure validation, without listener/display access on config save."""
    if not isinstance(value,str) or len(value)>100:raise ValueError('Atalho inválido.')
    normalized=GlobalPTT._normalizar_hotkey(value)
    parts=normalized.split('+');modifiers={'<ctrl>','<alt>','<shift>','<cmd>'}
    keys=[p for p in parts if p not in modifiers]
    allowed=lambda p:bool(re.fullmatch(r'[a-z0-9]|<f(?:[1-9]|1[0-9]|2[0-4])>|<space>',p))
    if (len(set(parts))!=len(parts) or len(keys)!=1 or not allowed(keys[0]) or
            (len(parts)==1 and not re.fullmatch(r'<f(?:[1-9]|1[0-9]|2[0-4])>',keys[0]))):
        raise ValueError('Use uma tecla F1–F24 ou Ctrl/Alt/Shift/Super junto com letra, número ou espaço.')
    return normalized


def native_bridge(hotkey):
    """Owned child: emits only shortcut transitions, never individual keys/audio.

    The Qt client owns capture/ASR. EOF from its stdin releases this listener.
    Uses the existing principal runtime (pynput), not the system Qt runtime.
    """
    import sys
    lock=threading.Lock()
    def emit(event):
        with lock:print(json.dumps({'event':event}),flush=True)
    class NoOverlay:
        def show(self):pass
        def hide(self):pass
        def close(self):pass
    class Transitions:
        gravando=False
        def comecar(self):self.gravando=True;emit('press')
        def parar(self):self.gravando=False;emit('release');return {}
    controller=GlobalPTT(Transitions(),hotkey=central_hotkey(hotkey),overlay=NoOverlay())
    try:
        controller.iniciar()
        if not controller.ativo:emit('unavailable');return 2
        emit('ready')
        for line in sys.stdin:
            if line.strip()=='quit':break
        return 0
    finally:controller.fechar()




class ControleMicrofone:
    """Fachada de alto nível usada pela interface e pelas ferramentas da Hoshino."""

    def __init__(self, transcritor, on_ptt_result=None, on_state=None):
        self.transcritor = transcritor
        self.modo = "fechado"
        self.ptt = GlobalPTT(transcritor, on_result=on_ptt_result, on_state=on_state)

    @property
    def hotkey(self):
        return self.ptt.hotkey

    def definir_modo(self, modo: str) -> str:
        modo = str(modo or "").strip().lower()
        aliases = {
            "continuo": "aberto", "contínuo": "aberto",
            "apertar": "pressionado", "pressionar": "pressionado", "ptt": "pressionado",
            "fechar": "fechado",
        }
        modo = aliases.get(modo, modo)
        from core import ui_policy
        if modo=='aberto' and not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'ambient'):
            return 'ACESSO_BLOQUEADO: ouvir o ambiente foi desativado na Central. O modo pressionado continua disponível.'
        if modo not in _MODOS:
            return "Erro: modo precisa ser fechado, aberto ou pressionado."
        if modo == self.modo and (modo == "fechado" or self.ptt.ativo):
            return self.estado()

        # Sempre encerra o estado anterior antes de mudar.
        if self.transcritor.escutando:
            self.transcritor.parar_escuta()
        if self.transcritor.gravando:
            self.transcritor.parar()
        self.ptt.parar()
        self.modo = modo
        self.ptt.definir_modo("pressionado" if modo == "pressionado" else "aberto")

        if modo == "aberto":
            if not self.transcritor.pronto():
                self.modo = "fechado"
                return "Microfone não está pronto para o modo aberto."
            resultado = self.transcritor.iniciar_escuta()
            if not self.transcritor.escutando:
                self.modo = "fechado"
                return resultado
            # O atalho global continua ativo também no modo aberto: pressionar
            # a combinação alterna a escuta contínua entre ligada/desligada.
            resultado_hotkey = self.ptt.iniciar()
            if not self.ptt.ativo:
                self.transcritor.parar_escuta()
                self.modo = "fechado"
                return resultado_hotkey
            return f"Microfone ABERTO. {resultado_hotkey}"

        if modo == "pressionado":
            resultado = self.ptt.iniciar()
            if not self.ptt.ativo:
                self.modo = "fechado"
                return resultado
            return f"Microfone por PRESSIONAR. {resultado}"

        return "Microfone FECHADO."

    def alternar(self) -> str:
        # Mantido para chamadas antigas. O ciclo automático entre aberto/pressionado
        # já não é um atalho de interface; quem escolhe o modo é a pessoa ou a Hoshino.
        proximo = "fechado" if self.modo != "fechado" else "pressionado"
        return self.definir_modo(proximo)

    def definir_atalho(self, hotkey: str) -> str:
        return self.ptt.definir_atalho(hotkey)

    def estado(self) -> str:
        return (f"modo={self.modo}; atalho={self.hotkey}; global="
                f"{'ativo' if self.ptt.ativo else 'inativo'}; "
                f"transcritor={self.transcritor.estado()}")

    def fechar(self) -> None:
        self.ptt.fechar()
        if self.transcritor.escutando:
            self.transcritor.parar_escuta()
        if self.transcritor.gravando:
            self.transcritor.parar()


_CONTROLADOR_ATUAL = None


def registrar_controlador(controlador) -> None:
    """Registra o controlador ativo para as ferramentas da Hoshino."""
    global _CONTROLADOR_ATUAL
    _CONTROLADOR_ATUAL = controlador


def controlador_atual():
    return _CONTROLADOR_ATUAL


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--native-bridge',metavar='HOTKEY',required=True)
    args=parser.parse_args()
    try:raise SystemExit(native_bridge(args.native_bridge))
    except ValueError:
        print(json.dumps({'event':'unavailable'}),flush=True);raise SystemExit(2)
