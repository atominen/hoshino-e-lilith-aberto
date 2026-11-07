"""Cópias de áudio pertencentes à Central; não move streams nem saída padrão."""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time
import uuid

from core.job_bus import _process_stamp as process_stamp

PREFIX='hoshino.listen.'


def graph():
    result=subprocess.run(['pw-dump'],capture_output=True,text=True,timeout=3,check=True)
    return json.loads(result.stdout)


def resolve(source,objects):
    nodes=[x for x in objects if x.get('type')=='PipeWire:Interface:Node'
           and str(x.get('info',{}).get('props',{}).get('object.serial'))==str(source.get('serial'))]
    if len(nodes)!=1:raise ValueError('Fonte desapareceu; atualize a lista.')
    node=nodes[0];props=node.get('info',{}).get('props',{})
    if source['kind']=='application_stream':
        if props.get('media.class')!='Stream/Output/Audio':raise ValueError('Stream não é reprodução de aplicativo.')
        pid=int(props.get('application.process.id') or 0)
        if not pid or pid!=source.get('pid'):raise ValueError('Aplicativo mudou; selecione novamente.')
        stamp=process_stamp(pid)
        if stamp is None:raise ValueError('Processo do aplicativo não foi confirmado.')
    else:
        pid=None;stamp=None
        expected=str(props.get('node.name',''))+('.monitor' if source['kind']=='output_mix' else '')
        if expected!=source['id']:raise ValueError('Dispositivo mudou.')
    ports={}
    for obj in objects:
        p=obj.get('info',{}).get('props',{})
        if obj.get('type')=='PipeWire:Interface:Port' and str(p.get('node.id'))==str(node['id']) and p.get('port.direction')=='out':
            channel=p.get('audio.channel')
            if channel in ports:raise ValueError('Portas de áudio ambíguas.')
            ports[channel]=obj['id']
    if source['kind']=='application_stream' and not ports:raise ValueError('Aplicativo ainda não possui portas de áudio.')
    return dict(source,serial=str(source['serial']),node_id=node['id'],pid=pid,stamp=stamp,ports=ports)


def matches(selected,objects):
    try:
        current=resolve(selected,objects)
        return all(current[k]==selected[k] for k in ('node_id','pid','stamp','ports'))
    except (ValueError,TypeError,KeyError):return False


class Route:
    def __init__(self,root,source):
        self.root=Path(root);self.selected=resolve(source,graph())
        self.process=None;self.loopback=None;self.closed=False
        self.name=PREFIX+uuid.uuid4().hex
        try:
            device=source['id']
            if source['kind']=='application_stream':device=self._isolate()
            self.process=self._spawn('parec',['--device='+device,'--format=s16le','--rate=16000','--channels=1',
                '--raw','--client-name=Central escuta','--stream-name='+self.name])
            if not self.valid():raise ValueError('Fonte deixou de estar disponível durante a abertura.')
        except Exception:
            try:self.close()
            except Exception as cleanup:
                error=RuntimeError('Abertura falhou e encerramento não foi confirmado; rota própria preservada.')
                error.owned_route=self
                raise error from cleanup
            raise

    def _spawn(self,command,args):
        executable=shutil.which(command)
        if not executable:raise ValueError(command+' indisponível; nenhuma fonte alternativa foi escolhida.')
        return subprocess.Popen([sys.executable,'-I',str(self.root/'scripts/image_child.py'),
            str(os.getpid()),executable,*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)

    def _isolate(self):
        capture=dict(**{'node.name':self.name+'.in','node.autoconnect':False,'node.dont-reconnect':True})
        playback={'node.name':self.name+'.source','node.description':'Central · áudio isolado',
            'media.class':'Audio/Source','node.autoconnect':False,'priority.session':-1000,
            'node.virtual':True,'node.dont-reconnect':True}
        self.loopback=self._spawn('pw-loopback',['-c','2','-m','[ FL FR ]',
            '--capture-props',json.dumps(capture),'--playback-props',json.dumps(playback)])
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            if self.loopback.poll() is not None:raise ValueError('Não foi possível criar a fonte isolada.')
            objects=graph()
            ids={x['id'] for x in objects if x.get('type')=='PipeWire:Interface:Node' and
                x.get('info',{}).get('props',{}).get('node.name')==self.name+'.in'}
            ports={x.get('info',{}).get('props',{}).get('audio.channel'):x['id'] for x in objects
                if x.get('type')=='PipeWire:Interface:Port' and
                x.get('info',{}).get('props',{}).get('node.id') in ids and
                x.get('info',{}).get('props',{}).get('port.direction')=='in'}
            if ports and any(x.get('info',{}).get('props',{}).get('node.name')==self.name+'.source' for x in objects):break
            time.sleep(.05)
        else:raise ValueError('Fonte isolada não ficou pronta.')
        if not matches(self.selected,objects):raise ValueError('Aplicativo mudou durante o isolamento.')
        selected_ports=self.selected['ports']
        for channel,target in ports.items():
            origin=selected_ports.get(channel)
            if origin is None and len(selected_ports)==1:origin=next(iter(selected_ports.values()))
            if origin is None:raise ValueError('Canais do aplicativo incompatíveis com captura estéreo.')
            subprocess.run(['pw-link',str(origin),str(target)],capture_output=True,timeout=3,check=True)
        return self.name+'.source'

    def valid(self):
        return bool(not self.closed and self.process and self.process.poll() is None
            and (self.loopback is None or self.loopback.poll() is None) and matches(self.selected,graph()))

    def read(self,timeout=.1):
        if self.closed or not self.process:return b''
        if self.process.poll() is not None:raise ValueError('Captura encerrou; nenhuma fonte substituta foi aberta.')
        if not select.select([self.process.stdout],[],[],timeout)[0]:return b''
        data=os.read(self.process.stdout.fileno(),3200)
        if not data:raise ValueError('Captura de áudio foi encerrada.')
        return data

    def close(self):
        self.closed=True
        failures=[]
        for proc in (self.process,self.loopback):
            if proc is None:continue
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:proc.wait(2)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait(2)
                if proc.stdout:proc.stdout.close()
            except (OSError,subprocess.TimeoutExpired) as exc:failures.append(type(exc).__name__)
        if failures:raise RuntimeError('Encerramento de captura não confirmado: '+', '.join(failures))
