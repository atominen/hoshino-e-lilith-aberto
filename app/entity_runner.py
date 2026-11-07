"""Entrada supervisionada: instância única e sinais convertidos em drenagem."""
import fcntl
import os
import signal
from pathlib import Path

import config
from core import interentity, entity_admission


def main():
    path = Path(config.RUNTIME_DIR) / "entity.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with entity_admission.instance(config.RAIZ, config.ENTIDADE_ID):
        signal.signal(signal.SIGTERM, lambda *_: interentity.request_sleep(config.ENTIDADE_ID,
            requester='sistema', reason='O processo recebeu SIGTERM; emissor não identificado.', source='sinal'))
        signal.signal(signal.SIGINT, lambda *_: interentity.request_sleep(config.ENTIDADE_ID,
            requester='sistema', reason='O processo recebeu SIGINT; emissor não identificado.', source='sinal'))
        if os.environ.get("HOSHINO_HEADLESS") == "1":
            # A central captura/reproduz áudio; não duplicar modelos e dispositivos.
            config.MIC_ATIVO = False
            config.VOZ_ATIVA = False
        from main import InterfaceHoshino
        from core import ollama_lifecycle
        app = InterfaceHoshino()
        app._interentity_enabled = True
        try:
            app.run(headless=os.environ.get("HOSHINO_HEADLESS") == "1")
        finally:
            from core import diagnostics
            unloaded = False
            try:
                unloaded = ollama_lifecycle.encerrar()
            except Exception as exc:
                diagnostics.emit('entity.unload_failed', level='ERROR', entity=config.ENTIDADE_ID,
                                 error_type=type(exc).__name__)
            diagnostics.emit('entity.exit_resources', entity=config.ENTIDADE_ID,
                             model_unload_confirmed=bool(unloaded), process_exiting=True)
            interentity.set_status(config.ENTIDADE_ID,
                                   "sleeping" if interentity.sleep_requested(config.ENTIDADE_ID) else "offline",
                                   "processo encerrado; unload=" + ('confirmed' if unloaded else 'unconfirmed'))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
