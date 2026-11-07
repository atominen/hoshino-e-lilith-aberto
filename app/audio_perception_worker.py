"""Classificação CPU persistente em RAM. Sem captura, rede, WAV ou transcrição."""
import base64
import contextlib
import json
import sys


def main():
    from core import acoustic_perception as acoustic
    for raw in sys.stdin:
        identifier=None
        try:
            if len(raw)>65536:raise ValueError('Pedido acústico excessivo.')
            request=json.loads(raw);identifier=request.get('id')
            if request.get('op')=='stop':return 0
            with contextlib.redirect_stdout(sys.stderr):
                if request.get('op')=='state':result=acoustic.status()
                elif request.get('op')=='classify':
                    pcm=base64.b64decode(request.get('pcm_base64',''),validate=True)
                    result=acoustic.classify_pcm(pcm)
                else:raise ValueError('Operação acústica desconhecida.')
            out=dict(id=identifier,ok=True,result=result)
        except Exception as exc:out=dict(id=identifier,ok=False,error=f'{type(exc).__name__}: {exc}',code='acoustic_failed')
        print('RESULT '+json.dumps(out,ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
