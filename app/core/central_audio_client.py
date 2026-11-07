"""Cliente dos runners para a mesma Central. Sem fallback, redirects ou retry."""
import json
from pathlib import Path
from urllib.parse import urlsplit,urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Redirecionamento da Central recusado.')

def call(root,entity,action=None,**data):
    parsed=urlsplit((Path(root)/'compartilhado/runtime/launcher/central.url').read_text().strip())
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port or not parsed.fragment or parsed.username:
        raise ValueError('Endereço local autenticado indisponível.')
    if action is None:
        route='/api/audio/listening?'+urlencode(dict(entity=entity,**data));body=None
    else:
        route='/api/audio/listening';body=json.dumps(dict(entity=entity,action=action,**data)).encode()
    req=Request(f'http://127.0.0.1:{parsed.port}'+route,data=body,
        headers={'Authorization':'Bearer '+parsed.fragment,'Content-Type':'application/json'})
    try:
        with build_opener(NoRedirect()).open(req,timeout=10) as response:
            raw=response.read(1024**2+1)
            if len(raw)>1024**2:raise ValueError('Resposta de escuta excessiva.')
            return json.loads(raw)
    except Exception as exc:
        if action is not None:raise RuntimeError('RESULTADO_INCERTO: Central não confirmou; consulte estado antes de repetir.') from exc
        raise RuntimeError('Central de áudio indisponível; nenhum transcritor privado foi iniciado.') from exc
