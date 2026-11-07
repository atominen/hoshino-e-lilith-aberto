"""Dashboard HTTP localhost-only com POST autenticado por token efêmero de sessão."""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .controle import schedule
from .candidatos import installed_models
from .experimentos import allowed_data,read_jobs,job_info,inspect_plan,create_job,import_dataset,cancel_job

WEB = Path(__file__).resolve().parent / 'web' / 'index.html'


def serve(lab,port:int):
    if not 1024 <= port <= 65535:raise ValueError('Porta inválida.')
    secret=secrets.token_urlsafe(32)
    allowed={f'127.0.0.1:{port}',f'localhost:{port}'}

    class API(BaseHTTPRequestHandler):
        def _send(self, code, obj, content_type='application/json; charset=utf-8'):
            data = obj.encode('utf-8') if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data)

        def _same_origin(self):
            host=self.headers.get('Host','')
            origin=self.headers.get('Origin','')
            return host in allowed and (not origin or origin in {f'http://{x}' for x in allowed})

        def do_GET(self):
            if not self._same_origin():return self._send(403,{'error':'Host/Origin recusado'})
            path=urlsplit(self.path).path
            try:
                if path=='/':return self._send(200,WEB.read_text(encoding='utf-8'),'text/html; charset=utf-8')
                if path=='/style.css':return self._send(200,(WEB.parent/'style.css').read_text(encoding='utf-8'),'text/css; charset=utf-8')
                if path=='/app.js':return self._send(200,(WEB.parent/'app.js').read_text(encoding='utf-8'),'application/javascript; charset=utf-8')
                if path=='/api/bootstrap':return self._send(200,{'csrf':secret,'project':str(lab.project),'home':str(lab.home)})
                if path=='/api/status':return self._send(200,lab.status())
                if path=='/api/personalizacao/status':
                    from .personalizacao import entity_status
                    return self._send(200,entity_status(lab.home))
                if path=='/api/professor-moe/status':
                    from .professor_moe import status
                    return self._send(200,status(lab.home))
                if path=='/api/professor-moe/snapshots':
                    from .professor_moe import snapshots
                    from urllib.parse import parse_qs
                    ent=parse_qs(urlsplit(self.path).query).get('entity',[''])[0]
                    return self._send(200,snapshots(lab.home,ent))
                if path=='/api/professor-moe/jobs':
                    from .professor_moe import jobs
                    return self._send(200,jobs(lab.home))
                if path=='/api/professor-moe/detail':
                    from .professor_moe import detail
                    from urllib.parse import parse_qs
                    id=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                    return self._send(200,detail(lab.home,id))
                if path=='/api/mods':return self._send(200,lab.mods())
                if path=='/api/overlay':return self._send(200,lab.overlay_info())
                if path=='/api/treinos/catalog':
                    from .treinos_unificados import home_data
                    return self._send(200,home_data(lab.home))
                if path=='/api/treinos/jobs':
                    from .treinos_unificados import jobs
                    return self._send(200,jobs(lab.home))
                if path=='/api/treinos/artifacts':
                    from .treinos_unificados import artifacts
                    return self._send(200,artifacts(lab.home))
                if path=='/api/treinos/datasets':
                    from .treinos_unificados import training_datasets
                    from urllib.parse import parse_qs
                    entity=parse_qs(urlsplit(self.path).query).get('entity',['hoshino'])[0]
                    return self._send(200,training_datasets(lab.home,entity))
                if path=='/api/night':
                    from .treinos_unificados import supervisor_call
                    return self._send(200,supervisor_call(lab.project,''))
                if path=='/api/night/schedule-once':
                    from .sessao_personalizada import path as schedule_path
                    p=schedule_path(lab.home)
                    return self._send(200,json.loads(p.read_text()) if p.exists() else {'state':'not_scheduled'})
                if path=='/api/night/config':
                    from .treinos_unificados import supervisor_call
                    return self._send(200,supervisor_call(lab.project,'/config'))
                if path=='/api/treinos/job':
                    from .treinos_unificados import details
                    from urllib.parse import parse_qs
                    jid=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                    return self._send(200,details(lab.home,jid))
                if path=='/api/presets-auto':
                    from .autopreset import status as preset_status
                    return self._send(200,preset_status(lab.home))
                if path=='/api/catalog':return self._send(200,installed_models(lab.home))
                if path=='/api/datasets':return self._send(200,allowed_data(lab.home))
                if path=='/api/jobs':return self._send(200,read_jobs(lab.home))
                if path=='/api/job':
                    from urllib.parse import parse_qs
                    id=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                    return self._send(200,job_info(lab.home,id))
                return self._send(404,{'error':'Rota inexistente'})
            except Exception as e:return self._send(500,{'error':str(e)})

        def do_POST(self):
            if not self._same_origin():return self._send(403,{'error':'Origem recusada'})
            if self.headers.get('X-Lab-Token','')!=secret:return self._send(403,{'error':'Token inválido'})
            if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
                return self._send(415,{'error':'Somente JSON'})
            try:
                route=urlsplit(self.path).path
                length=int(self.headers.get('Content-Length','0'))
                if not 0 <= length <= (5*1024*1024 if route=='/api/datasets/import' else 8192):raise ValueError('Corpo grande demais')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('JSON inválido')
                if route=='/api/treinos/preview':
                    from .treinos_unificados import plan
                    result=plan(lab.home,data.get('model'),data.get('entity'),data.get('minutes'),data.get('action'),data.get('checkpoint'),data.get('candidate'),data.get('dataset'),data.get('options'))
                elif route=='/api/treinos/prepare-12h':
                    from .treinos_unificados import default_cycle_plan
                    result=default_cycle_plan(lab.home,nightly=True)
                elif route=='/api/treinos/prepare-custom':
                    from .sessao_personalizada import preview
                    result=preview(lab.home,data)
                elif route=='/api/night/resume-preview':
                    from .treinos_unificados import resume_night_tasks
                    result={'tasks':resume_night_tasks(lab.home),'execution_started':False}
                elif route=='/api/treinos/start':
                    from .treinos_unificados import start
                    result=start(lab.home,lab.project,data.get('model'),data.get('entity'),data.get('minutes'),data.get('action'),data.get('confirm'),data.get('checkpoint'),data.get('candidate'),data.get('dataset'),data.get('options'))
                elif route=='/api/treinos/review':
                    from .versionamento_lora import review_evaluation
                    result=review_evaluation(lab.home,data.get('candidate'),data.get('report'),confirm=data.get('confirm'))
                elif route=='/api/treinos/auto-promote':
                    from .versionamento_lora import auto_promote
                    result=auto_promote(lab.home,data.get('candidate'),data.get('report'),data.get('entity'),data.get('model'))
                elif route=='/api/personalizacao/capture':
                    from .personalizacao import capture_profile
                    result=capture_profile(lab.home,lab.project,data.get('entity'),data.get('refs'),confirm=data.get('confirm'))
                elif route=='/api/treinos/promote':
                    from .versionamento_lora import promote
                    result=promote(lab.home,data.get('candidate'),data.get('entity'),data.get('model'),confirm=data.get('confirm'))
                elif route=='/api/treinos/rollback':
                    from .versionamento_lora import rollback
                    result=rollback(lab.home,data.get('entity'),data.get('model'),confirm=data.get('confirm'))
                elif route in ('/api/night/start','/api/night/stop','/api/night/config','/api/night/schedule-once','/api/night/cancel-schedule'):
                    from .treinos_unificados import supervisor_call
                    result=supervisor_call(lab.project,route.removeprefix('/api/night'),data)
                elif route=='/api/treinos/stop':
                    from .treinos_unificados import stop
                    result=stop(lab.home,data.get('id'),data.get('confirm'))
                elif route=='/api/professor-moe/prepare':
                    from .professor_moe import prepare
                    result=prepare(lab.home,data.get('entity'),data.get('snapshot'),mode='max_dynamic',profile=data.get('profile'))
                elif route=='/api/professor-moe/prepare-dataset':
                    from .professor_moe import prepare_from_dataset
                    result=prepare_from_dataset(lab.home,data.get('entity'),data.get('dataset'),data.get('limit',20),mode='max_dynamic',profile=data.get('profile'))
                elif route=='/api/professor-moe/run':
                    from .professor_moe import start
                    result=start(lab.home,data.get('id'),confirm=data.get('confirm'))
                elif route=='/api/professor-moe/stop':
                    from .professor_moe import stop
                    if data.get('confirm') is not True:raise ValueError('Confirmação exigida para parar')
                    result=stop(lab.home,data.get('id'))
                elif route=='/api/professor-moe/review-example':
                    from .professor_moe import review_examples
                    result=review_examples(lab.home,data.get('id'),data.get('source_id'),data.get('decision'),
                        data.get('note',''),confirm=data.get('confirm'),as_reference=data.get('as_reference',False),
                        expected_hash=data.get('expected_hash'))
                elif route=='/api/professor-moe/references':
                    from .professor_moe import draft_reference_set
                    if data.get('confirm') is not True:raise ValueError('Confirme preparo de referências pendentes')
                    result=draft_reference_set(lab.home,data.get('entity'))
                elif route=='/api/treinos/recovery-preview':
                    from .recuperacao_modelos import plan
                    result=plan(lab.home,lab.project,data.get('entity'),data.get('model'))
                elif route=='/api/treinos/recovery-start':
                    from .treinos_unificados import start
                    if data.get('confirm')!='EXECUTAR_RECUPERACAO_LOCAL':raise ValueError('Confirme recuperação/ativação local')
                    result=start(lab.home,lab.project,data.get('model'),data.get('entity'),90,'recover',data['confirm'])
                elif route=='/api/professor-moe/discard-examples':
                    from .professor_moe import discard_examples
                    result=discard_examples(lab.home,data.get('id'),data.get('source_ids'),confirm=data.get('confirm'))
                elif route=='/api/professor-moe/discard-job':
                    from .professor_moe import discard_job
                    result=discard_job(lab.home,data.get('id'),confirm=data.get('confirm'))
                elif route=='/api/professor-moe/export':
                    from .professor_moe import approved_export
                    if data.get('confirm') is not True:raise ValueError('Revisão humana exige confirmação')
                    result=approved_export(lab.home,data.get('id'),data.get('approved_ids'),data.get('base_dataset'),require_decisions=True)
                elif route=='/api/datasets/import':result=import_dataset(lab.home,data.get('train'),data.get('validation'))
                elif route=='/api/mods/enable':result={'enabled':lab.set_mod(data['id'],True)}
                elif route=='/api/mods/disable':result={'enabled':lab.set_mod(data['id'],False)}
                elif route=='/api/overlay/build':result=lab.build()
                elif route=='/api/schedule':result=schedule(lab,int(data['pid']),str(data['at']))
                elif route=='/api/job/cancel':result=cancel_job(lab.home,data['id'])
                elif route=='/api/experiment/preview':result=inspect_plan(data,lab.home)
                elif route=='/api/experiment/start':
                    if data.get('confirm') is not True:raise ValueError('Confirmação explícita necessária')
                    result=create_job(lab.home,data,data.get('at') or None)
                else:return self._send(404,{'error':'Ação não existe'})
                return self._send(200,{'ok':True,'result':result})
            except (ValueError,RuntimeError,KeyError,PermissionError,OSError) as e:
                return self._send(400,{'error':str(e)})

        def log_message(self,fmt,*args):
            pass # endpoint não exposto fora de 127.0.0.1

    server=ThreadingHTTPServer(('127.0.0.1',port),API)
    print(f'Painel Laboratório: http://127.0.0.1:{port} (somente localhost)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
