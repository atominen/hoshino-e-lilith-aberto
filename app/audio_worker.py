"""Worker ASR único da central; sem captura, memória mental ou resposta de LLM."""
import contextlib
import json
import sys
from pathlib import Path


def main():
    from core import audio_transcription
    for raw in sys.stdin:
        request_id = None
        try:
            req = json.loads(raw)
            request_id = req.get("id")
            if req.get("op") == "stop":
                audio_transcription.release_model()
                return 0
            with contextlib.redirect_stdout(sys.stderr):
                if req.get("op") == "transcribe":
                    result = audio_transcription.transcribe(Path(req["path"]), source=req.get("source", "browser_microphone"))
                elif req.get("op") == "state":
                    result = audio_transcription.status()
                else:
                    raise ValueError("operação desconhecida")
            out = {"id": request_id, "ok": True, "result": result}
        except Exception as exc:
            out = {"id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                   "code": getattr(exc, "code", "asr_failed")}
        sys.stdout.write("RESULT " + json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
