#!/usr/bin/python3
"""Orbes Qt5 opcionais: cliente local descartável, nunca dono da entidade.

Sem WebEngine/OpenGL, sem captura ou síntese. Um pedido de rede por vez fora da
thread gráfica. Fechar/crash não envia shutdown. Assets separados, placeholders.
"""
import argparse
import json
import math
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ENTITIES=('hoshino','lilith','alistair')
COLORS={'hoshino':'#f7b9d2','lilith':'#e65b70','alistair':'#87ceeb'}
STATUS_LABELS={'offline':'offline','sleeping':'dormindo','starting':'acordando','stopping':'encerrando',
               'awake':'acordada','working':'em atividade','speaking':'falando (relato do player)',
               'waiting':'esperando recurso','error':'erro de conexão'}


def endpoint(root):
    parsed=urlsplit((Path(root)/'compartilhado/runtime/launcher/central.url').read_text().strip())
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port or not parsed.fragment:
        raise ValueError('Central local válida não encontrada.')
    return f'http://127.0.0.1:{parsed.port}',parsed.fragment


def api(root,path,data=None):
    # Reabrir a Central muda autenticação/porta. Cada pedido novo lê a fonte
    # existente; não há retry automático de sleep/wake/interação/configuração.
    connection=endpoint(root);base,token=connection
    request=Request(base+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,
                    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urlopen(request,timeout=3) as response:out=json.load(response)
    if endpoint(root)!=connection:raise ValueError('Central reiniciada; resultado não confirmado, pedido não repetido.')
    return out


def clamp_position(x,y,bounds,width=88,height=100):
    left,top,right,bottom=bounds
    return (max(left,min(x,right-width)),max(top,min(y,bottom-height)))


def balloon_text(message,limit=180):
    text=' '.join(str(message.get('text','')).split())
    return text if len(text)<=limit else text[:limit-1]+'… (abra a central)'


def display_state(entity,out):
    presence=next((p for p in out.get('presence',[]) if p.get('entity_id')==entity),{})
    status=presence.get('status','offline')
    if status in {'sleeping','offline','starting','stopping'}:return status
    all_jobs=[j for j in out.get('jobs',[]) if j.get('entity')==entity]
    if any(j.get('details',{}).get('playback_event')=='started' and not j.get('details',{}).get('playback_cancel_at') and time.time()-j.get('details',{}).get('playback_at',0)<30 for j in all_jobs):return 'speaking'
    jobs=[j for j in all_jobs if j.get('status') in {'running','queued'}]
    if any(j.get('status')=='queued' for j in jobs):return 'waiting'
    return 'working' if jobs else status


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--verify',action='store_true');parser.add_argument('--smoke-seconds',type=float);parser.add_argument('--snapshot',type=Path);args=parser.parse_args()
    if args.smoke_seconds is not None and not 1<=args.smoke_seconds<=30:raise ValueError('Ensaio de UI entre 1 e 30 segundos.')
    from PyQt5.QtCore import Qt,QTimer,QThread,pyqtSignal,QPoint,QProcess
    from PyQt5.QtGui import QColor,QPainter,QPen,QFont
    from PyQt5.QtWidgets import QApplication,QWidget,QMenu,QLabel
    from native_style import STYLE, paint_orb, animation_interval, load_orb_image, mood_color
    if args.verify:
        print('Qt5 disponível; verificação sem iniciar janela/backend.');return 0
    root=args.root.resolve();endpoint(root)

    class Network(QThread):
        done=pyqtSignal(object)
        def __init__(self,path,data=None):super().__init__();self.path,self.data=path,data
        def run(self):
            try:self.done.emit({'ok':True,'value':api(root,self.path,self.data)})
            except Exception:self.done.emit({'ok':False,'error':'Central indisponível; entidades não foram encerradas.'})

    app=QApplication([]);app.setApplicationName('Hoshino Lilith Alistair — orbes');app.setQuitOnLastWindowClosed(True)
    app.setStyleSheet(STYLE)
    state={'settings':{'overlay_enabled':True},'revision':'','central_focused':False};workers=[];seen={};initialized=set();last_balloon={}
    def submit(path,data,callback=None):
        worker=Network(path,data);workers.append(worker)
        worker.done.connect(callback or (lambda _:None));worker.finished.connect(lambda:workers.remove(worker));worker.start()
    def preferences(updates):
        if not state['revision']:return
        submit('control/interface',{'revision':state['revision'],'settings':updates},lambda r:state.update(revision=r['value']['revision']) if r['ok'] else None)

    # Corpo pulsado (Pestinha) em processo próprio, com o Python que tem numpy.
    # Só recebe o que o overlay já lê; só devolve expressão. Ausente/caído = animação fixa.
    body={'proc':None,'buffer':b''}
    def start_body():
        code=Path(__file__).resolve().parents[2];python=code/'compartilhado/ambientes/principal/bin/python'
        script=code/'app/ui/corpo_pulsado.py';upstream=code/'compartilhado/servicos/pestinha'
        if not (python.is_file() and script.is_file() and (upstream/'.git/HEAD').is_file()):return
        log=root/'compartilhado/runtime/launcher/corpo.log'
        try:log.parent.mkdir(parents=True,exist_ok=True)
        except OSError:return
        proc=QProcess(app);proc.setStandardErrorFile(str(log),QProcess.Append)
        proc.readyReadStandardOutput.connect(read_body);proc.start(str(python),['-I','-B',str(script),'--root',str(root),'--upstream',str(upstream),'--serve'])
        body['proc']=proc
    def send_body(message):
        proc=body['proc']
        if proc is not None and proc.state()==QProcess.Running:proc.write((json.dumps(message,ensure_ascii=False)+'\n').encode())
    def read_body():
        data=body['buffer']+bytes(body['proc'].readAllStandardOutput())
        lines=data.split(b'\n');body['buffer']=lines[-1] if len(lines[-1])<65536 else b''
        for line in reversed(lines[:-1]):
            try:out=json.loads(line)
            except ValueError:continue
            for entity,value in (out.get('corpos') or {}).items() if isinstance(out,dict) else ():
                if entity in orbs and isinstance(value,dict):orbs[entity].body=value;orbs[entity].body_at=time.monotonic()
            break

    class Orb(QWidget):
        def __init__(self,entity,index):
            super().__init__();self.entity=entity;self.status='offline';self.expression=None;self.phase=index;self.drag=None;self.moved=False;self.hover=False;self.epoch=time.monotonic()-index;self.reduced=False
            self.body=None;self.body_at=0.;self.last_tick=time.monotonic()
            self.setWindowFlags(Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint);self.setAttribute(Qt.WA_TranslucentBackground);self.setFixedSize(88,100)
            screen=app.primaryScreen().availableGeometry();self.move(screen.right()-110,index*112+80)
            # Read only own placeholder metadata; no cross-entity asset fallback.
            asset=root/'app/ui/assets'/entity/'orb.json';self.asset=json.loads(asset.read_text()) if asset.is_file() else {'color':COLORS[entity]}
            self.balloon=QLabel(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint);self.balloon.setWordWrap(True);self.balloon.setMaximumWidth(290);self.balloon.setStyleSheet('background:#202434;color:#eee;padding:12px;border:1px solid '+self.asset['color']+';border-radius:12px;font:12px sans-serif;')
            self.balloon.mousePressEvent=lambda event:self.open_central()
            self.balloon_timer=QTimer(self);self.balloon_timer.setSingleShot(True);self.balloon_timer.timeout.connect(self.balloon.hide)
            self.setCursor(Qt.PointingHandCursor)
            self.visual={};self.portrait=None;self.image_stamp=None;self.image_error=False
            self.animation=QTimer(self);self.animation.timeout.connect(self.tick);self.show();self.sync_animation()
        def sync_animation(self):
            interval=animation_interval(self.status,self.reduced,self.isVisible())
            if not interval:self.animation.stop();self.phase=0
            elif not self.animation.isActive() or self.animation.interval()!=interval:self.animation.start(interval)
            self.update()
        def hideEvent(self,event):
            if hasattr(self,'animation'):self.animation.stop()
            super().hideEvent(event)
        def showEvent(self,event):
            super().showEvent(event)
            if hasattr(self,'animation'):self.sync_animation()
        def enterEvent(self,event):self.hover=True;self.update()
        def leaveEvent(self,event):self.hover=False;self.update()
        def live_body(self):
            return self.body if self.body is not None and time.monotonic()-self.body_at<2 else None
        def tick(self):
            now=time.monotonic();elapsed=min(.5,max(0.,now-self.last_tick));self.last_tick=now
            if not self.isVisible():return
            anim=(self.live_body() or {}).get('animacao');speed=anim.get('velocidade',1) if isinstance(anim,dict) else 1
            speed=min(3.,max(0.,float(speed))) if isinstance(speed,(int,float)) and not isinstance(speed,bool) and math.isfinite(speed) else 1.
            self.phase+=elapsed*(.35 if self.status in {'offline','sleeping'} else 1)*speed;self.update()
        def paintEvent(self,event):
            color=self.visual.get('base_color',self.asset['color'])
            if self.visual.get('mood_tint',True):color=mood_color(color,self.expression)
            painter=QPainter(self);paint_orb(painter,color,self.entity,self.status,self.phase,self.hover,identity_color=COLORS[self.entity],portrait=self.portrait if self.visual.get('mode')=='image' else None,corpo=self.live_body())
            if self.expression:
                painter.setPen(QColor('#eeeeee'));painter.setFont(QFont('Sans',8));painter.drawText(0,66,88,14,Qt.AlignCenter,self.expression)
        def mousePressEvent(self,event):
            if event.button()==Qt.LeftButton:self.drag=event.globalPos()-self.pos();self.moved=False
            if event.button()==Qt.RightButton:self.menu(event.globalPos())
        def mouseMoveEvent(self,event):
            if self.drag is not None:
                delta=event.globalPos()-self.drag;moved=self.moved;self.moved=self.moved or (delta-self.pos()).manhattanLength()>3
                if self.moved and not moved:send_body({'tipo':'arrastar','entidade':self.entity,'ativo':True})
                screen=app.screenAt(event.globalPos()) or app.primaryScreen();g=screen.availableGeometry();self.move(*clamp_position(delta.x(),delta.y(),(g.left(),g.top(),g.right()+1,g.bottom()+1)))
        def mouseReleaseEvent(self,event):
            if event.button()!=Qt.LeftButton:return
            self.drag=None
            if self.moved:
                send_body({'tipo':'arrastar','entidade':self.entity,'ativo':False})
                positions=dict(state['settings'].get('positions',{}));positions[self.entity]=[self.x(),self.y()];state['settings']['positions']=positions;preferences({'positions':positions})
            else:send_body({'tipo':'cutucar','entidade':self.entity});self.open_central()
        def open_central(self):
            submit('control/native/open',{'entity':self.entity},self.action_result)
        def menu(self,position):
            menu=QMenu(self)
            for title,path,data in [('Conversar / abrir central',None,None),('Fazer carinho','control/social',{'entity':self.entity,'interaction':'carinho','submission_id':uuid.uuid4().hex}),('Chamar / acordar','start',{'entity':self.entity}),('Interromper fala','audio/interrupt',{'entity':self.entity}),('Dormir com segurança','sleep',{'entity':self.entity})]:
                action=menu.addAction(title);action.triggered.connect((lambda _,p=path,d=data:submit(p,d,self.action_result)) if path else self.open_central)
                if data and data.get('interaction')=='carinho':action.triggered.connect(lambda _:send_body({'tipo':'carinho','entidade':self.entity}))
            menu.addSeparator();menu.addAction('Status: '+STATUS_LABELS.get(self.status,self.status),self.open_central);menu.addAction('Fechar somente overlay',app.quit);menu.exec_(position)
        def action_result(self,r):
            self.show_balloon('Pedido entregue ao backend; o estado confirmará.' if r['ok'] else r['error'])
        def show_balloon(self,text):
            self.balloon.setText(text);self.balloon.adjustSize();g=(app.screenAt(self.pos()) or app.primaryScreen()).availableGeometry()
            x,y=clamp_position(self.x()-210,self.y()-self.balloon.height()-6,(g.left(),g.top(),g.right()+1,g.bottom()+1),self.balloon.width(),self.balloon.height())
            if self.y()-self.balloon.height()<g.top():y=min(g.bottom()-self.balloon.height(),self.y()+100)
            self.balloon.move(x,y);self.balloon.show();self.balloon_timer.start(int(state['settings'].get('balloon_seconds',7))*1000)

    orbs={entity:Orb(entity,index) for index,entity in enumerate(ENTITIES)};network=None;start_body()
    def update(r):
        if not r['ok']:
            for orb in orbs.values():orb.status='error';orb.sync_animation()
            return
        out=r['value']
        if out.get('closing'):app.quit();return
        cfg=out['interface'];state.update(settings=cfg['settings'],revision=cfg['revision'])
        if not state['settings'].get('overlay_enabled'):app.quit();return
        for entity,orb in orbs.items():
            orb.status=display_state(entity,out);orb.setToolTip(entity.capitalize()+' · '+STATUS_LABELS.get(orb.status,orb.status));top=state['settings'].get('always_on_top',True)
            profile=out.get('entity_details',{}).get(entity,{}).get('expression_profile',{})
            orb.expression=profile.get('dominant') if profile.get('available') else None
            send_body({'tipo':'estado','entidade':entity,'status':orb.status,'reduzido':bool(state['settings'].get('reduced_motion',False)),
                       'emocoes':profile.get('emotions',{}) if profile.get('available') else {}})
            live=orb.live_body()
            if live and live.get('rotulo'):orb.setToolTip(orb.toolTip()+' · corpo: '+str(live['rotulo'])[:20])
            orb.visual=state['settings'].get('orb_styles',{}).get(entity,{})
            image_path=orb.visual.get('image_path','') if orb.visual.get('mode')=='image' else ''
            try:stamp=(image_path,Path(image_path).stat().st_mtime_ns) if image_path else ('',0)
            except OSError:stamp=(image_path,None)
            if stamp!=orb.image_stamp:
                orb.image_stamp=stamp;orb.portrait=load_orb_image(image_path);orb.image_error=bool(image_path and orb.portrait.isNull())
            if orb.image_error:orb.setToolTip(orb.toolTip()+' · imagem indisponível/inválida; usando energia')
            if bool(orb.windowFlags()&Qt.WindowStaysOnTopHint)!=top:
                orb.setWindowFlag(Qt.WindowStaysOnTopHint,top);orb.show()
            orb.reduced=state['settings'].get('reduced_motion',False);orb.sync_animation()
            if entity not in initialized:
                pos=state['settings'].get('positions',{}).get(entity)
                if pos:
                    g=app.primaryScreen().availableGeometry();orb.move(*clamp_position(*pos,(g.left(),g.top(),g.right()+1,g.bottom()+1)))
                initialized.add(entity)
            replies=[m for m in out['replies'].get(entity,[]) if m.get('sender')==entity and m.get('recipient')=='usuario' and m.get('kind')=='chat']
            if entity not in seen:seen[entity]={m['id'] for m in replies};continue
            for msg in replies:
                if msg['id'] in seen[entity]:continue
                seen[entity].add(msg['id'])
                # Sem confirmação de foco pela central, não supõe "fora de foco".
                focus=out.get('central_focus',{});fresh=time.time()-focus.get('at',0)<30
                if (fresh and not focus.get('focused',True) and state['settings'].get('balloons') and not state['settings'].get('silent') and time.time()-last_balloon.get(entity,0)>20):
                    orb.show_balloon(balloon_text(msg));last_balloon[entity]=time.time()
            if len(seen[entity])>200:seen[entity]={m['id'] for m in replies}
    def poll():
        nonlocal network
        if network and network.isRunning():return
        network=Network('control/overlay');network.done.connect(update);network.start()
    timer=QTimer();timer.timeout.connect(poll);timer.start(2000);poll()
    observed_intervals={}
    def close():
        timer.stop()
        observed_intervals.update({e:o.animation.interval() if o.animation.isActive() else 0 for e,o in orbs.items()})
        for orb in orbs.values():orb.animation.stop();orb.balloon.close()
        proc=body['proc']
        if proc is not None and proc.state()!=QProcess.NotRunning:
            body['received']=any(o.body is not None for o in orbs.values())
            proc.closeWriteChannel()  # EOF: o corpo salva o estado e sai
            if not proc.waitForFinished(3000):proc.terminate();proc.waitForFinished(1000) or proc.kill()
        for worker in workers+([network] if network else []):
            if worker.isRunning():worker.wait(3500)
    app.aboutToQuit.connect(close)
    started, cpu = time.monotonic(), time.process_time()
    if args.smoke_seconds is not None:
        def snapshot():
            if args.snapshot is not None:
                args.snapshot.mkdir(parents=True,exist_ok=True)
                for entity,orb in orbs.items():orb.grab().save(str(args.snapshot/(entity+'-orb-fixture.png')))
            app.quit()
        QTimer.singleShot(int(args.smoke_seconds*1000),snapshot)
    result=app.exec_()
    if args.smoke_seconds is not None:
        import resource
        print(json.dumps(dict(ui_only=True,elapsed_seconds=time.monotonic()-started,
                              cpu_seconds=time.process_time()-cpu,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                              orbs=len(orbs),frame_intervals_ms=observed_intervals,backend_shutdown_sent=False,
                              body_received=bool(body.get('received')))))
    return result


if __name__=='__main__':raise SystemExit(main())
