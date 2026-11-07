import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from tools import filesystem, voice  # noqa: E402


def test_workspace_relativo_usa_raiz_canonica():
    with tempfile.TemporaryDirectory() as tmp:
        anterior = filesystem.OFICINA_DIR
        try:
            filesystem.OFICINA_DIR = tmp
            out = filesystem.workspace("salvar", "projetos/v35/hello.txt", "hello")
            alvo = Path(tmp) / "projetos" / "v35" / "hello.txt"
            assert alvo.read_text(encoding="utf-8") == "hello"
            assert str(alvo) in out
        finally:
            filesystem.OFICINA_DIR = anterior


def test_workspace_bloqueia_escape():
    with tempfile.TemporaryDirectory() as tmp:
        anterior = filesystem.OFICINA_DIR
        try:
            filesystem.OFICINA_DIR = tmp
            out = filesystem.workspace("ler", "../../etc/passwd")
            assert "fora das áreas permitidas" in out
        finally:
            filesystem.OFICINA_DIR = anterior


def test_voice_worker_ready_then_result(reply_mode="matching"):
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "fake_worker.py"
        script.write_text(
            "import sys,json,wave\n"
            "print('READY fake transport (not a synthesis result)', flush=True)\n"
            "for line in sys.stdin:\n"
            " r=json.loads(line)\n"
            " if r.get('op') == 'synthesize':\n"
            "  with wave.open(r['output'],'wb') as w:\n"
            "   w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b'\\0\\0'*240)\n"
            "  result={'ok':True}\n"
            f"  mode={reply_mode!r}\n"
            "  if mode!='missing': result['id']=r['id'] if mode=='matching' else 'stale-request'\n"
            "  print('RESULT '+json.dumps(result), flush=True)\n",
            encoding="utf-8",
        )
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        original_worker = voice._worker
        original_start = voice._iniciar_worker
        original_timeout = voice.TTS_WORKER_TIMEOUT
        try:
            voice._worker = proc
            voice._iniciar_worker = lambda: proc
            voice.TTS_WORKER_TIMEOUT = 10
            output = Path(tmp) / "saida.wav"
            if reply_mode == "matching":
                voice._sintetizar_kokoro("teste", str(output))
                with wave.open(str(output), "rb") as wav:
                    assert wav.getnframes() == 240 and wav.getframerate() == 24000
            else:
                try:
                    voice._sintetizar_kokoro("teste", str(output))
                except RuntimeError as error:
                    assert "outra solicitação" in str(error)
                else:
                    raise AssertionError("resposta sem ID correspondente não pode ser aceita")
        finally:
            voice._iniciar_worker = original_start
            voice._worker = original_worker
            voice.TTS_WORKER_TIMEOUT = original_timeout
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    test_workspace_relativo_usa_raiz_canonica()
    test_workspace_bloqueia_escape()
    test_voice_worker_ready_then_result()
    test_voice_worker_ready_then_result("missing")
    test_voice_worker_ready_then_result("stale")
    print("V35 hardening: 5 testes ok (protocolo simulado; não valida TTS real)")
