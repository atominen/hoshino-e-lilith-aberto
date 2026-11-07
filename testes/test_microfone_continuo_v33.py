"""Teste manual do microfone contínuo V33.

Executa 60 s de captura e imprime cada segmento reconhecido pelo faster-whisper.
Sem diarização.
"""
import sys
import time
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

def main():
    # Importar/descobrir este arquivo não carrega ASR nem abre microfone.
    # A validação continua REAL e manual, não foi substituída por um mock.
    if os.environ.get('HOSHINO_TEST_OFFLINE') == '1' or os.environ.get('CI'):
        raise SystemExit('Teste manual de hardware proibido na suíte offline/CI.')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    import config
    from tools.transcricao import Transcritor

    config.AUDIO_DIARIZACAO = False
    config.AUDIO_CONTINUO = True
    config.AUDIO_DEVICE = "cpu"
    config.AUDIO_COMPUTE_TYPE = "int8"
    t = Transcritor()
    print("=== MICROFONE CONTÍNUO V33 — HARDWARE REAL / MANUAL ===")
    print(t.diagnostico())
    print("Fale normalmente por 60 segundos. Ctrl+C encerra antes.")
    res = t.iniciar_escuta()
    print(res)
    if not t.escutando:
        raise SystemExit(1)
    try:
        fim = time.monotonic() + 60
        while time.monotonic() < fim:
            item = t.pegar()
            if item:
                print("OUVIDO:", item)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("Interrompido manualmente.")
    finally:
        print(t.parar_escuta())


if __name__ == '__main__':
    main()
