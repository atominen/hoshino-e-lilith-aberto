#!/usr/bin/python3
"""Central QtWidgets: cliente do backend atual, sem browser/WebEngine/IA.

Captura e player são processos PulseAudio próprios, iniciados só por clique.
Fechar pede confirmação e aguarda encerramento cooperativo do projeto.
"""
import argparse
import fcntl
import html
import io
import json
import os
import re
import sys
import shutil
import tempfile
import time
import uuid
import hashlib
import ipaddress
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, urlopen

from native_audio import Segmenter, AcousticWindows, wav_bytes, pulse_volume, owned_sink_input, public_speech_streams
from native_style import STYLE
from native_controls import QComboBox, QSpinBox, QSnapSpinBox, QDoubleSpinBox, QSlider, QTabWidget
from native_panels import ResourcesPanel, ActivityPanel, HistoryTimelinePanel, ServicesPanel, KnowledgePanel
from logic_workshop import LogicWorkshop
from native_chat_stream import merge_previews, update_chat_document
from native_asr_client import LiveASRClient
from native_listening import ListeningPanel
import native_ponte
from PyQt5.QtCore import Qt, QThread, QTimer, QProcess, QEvent, pyqtSignal, QPropertyAnimation, QEasingCurve, QBuffer, QIODevice
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap, QImage, QDesktopServices
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QGridLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QStackedWidget, QTextBrowser,
    QPlainTextEdit, QLineEdit, QCheckBox, QProgressBar, QKeySequenceEdit,
    QMessageBox, QInputDialog, QTreeWidget, QTreeWidgetItem, QFileDialog, QGroupBox, QFormLayout, QScrollArea, QGraphicsOpacityEffect, QColorDialog, QDialog, QDialogButtonBox, QFrame)

ENTITIES=('hoshino','lilith','alistair')
COLORS={'hoshino':'#f7b9d2','lilith':'#e65b70','alistair':'#87ceeb'}
PAGES=('Entidades','Conversa','Áudio','Memória do chat','Memórias','Ferramentas','Modelos','Laboratório Neural','Recursos','Atividade','Configurações','Serviços','Diagnóstico')
TEST_STORY=('Era uma vez uma raposinha que encontrou uma estrela caída no bosque. '
            'Uma fada lhe disse: “A bondade pode alcançar o céu.” Então, a raposinha '
            'ajudou cada animal que encontrou, e cada agradecimento virou um degrau '
            'de luz. A estrela voltou para casa e, desde aquela noite, sempre '
            'brilhava para sua pequena amiga.')


def endpoint(root):
    parsed=urlsplit((Path(root)/'compartilhado/runtime/launcher/central.url').read_text().strip())
    host=parsed.hostname or ''
    # 06/11: no PC2 o painel aponta para o IP do PC1 na rede local (só endereço privado IPv4).
    try:remote=host!='127.0.0.1' and isinstance(ipaddress.ip_address(host),ipaddress.IPv4Address) and ipaddress.ip_address(host).is_private and not ipaddress.ip_address(host).is_loopback
    except ValueError:remote=False
    if parsed.scheme!='http' or not (host=='127.0.0.1' or remote) or not parsed.port or not parsed.fragment:
        raise ValueError('Endereço autenticado da central local não encontrado.')
    return f'http://{host}:{parsed.port}',parsed.fragment


class ChatDraft(QPlainTextEdit):
    send_requested=pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent);self.composing=False
        self.microphone_hotkey=QKeySequence();self.microphone_keys=set()
    def reserve_microphone_hotkey(self,sequence):
        sequence=QKeySequence(sequence)
        if sequence!=self.microphone_hotkey:self.microphone_keys.clear()
        self.microphone_hotkey=sequence
    def microphone_key(self,event):
        modifiers=event.modifiers() & (Qt.ShiftModifier|Qt.ControlModifier|Qt.AltModifier|Qt.MetaModifier)
        return self.microphone_hotkey.count()==1 and self.microphone_hotkey[0]==(event.key()|int(modifiers))
    def event(self,event):
        if event.type()==QEvent.ShortcutOverride and self.microphone_key(event):
            event.accept();return True
        return super().event(event)
    def inputMethodEvent(self,event):
        self.composing=bool(event.preeditString());super().inputMethodEvent(event)
    def keyPressEvent(self,event):
        # O listener global aciona o PTT. Aqui só impedimos a edição do texto,
        # antes de inserir letras ou substituir uma seleção do rascunho.
        if self.microphone_key(event) or (event.isAutoRepeat() and event.key() in self.microphone_keys):
            self.microphone_keys.add(event.key());event.accept();return
        # A liberação pode ter ocorrido em outra janela. Uma pressão nova,
        # sem a combinação reservada, nunca fica presa no estado anterior.
        self.microphone_keys.discard(event.key())
        if event.key() in (Qt.Key_Return,Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier and not self.composing:
            if not self.isReadOnly() and not event.isAutoRepeat():self.send_requested.emit()
            event.accept();return
        super().keyPressEvent(event)
    def keyReleaseEvent(self,event):
        if event.key() in self.microphone_keys:
            if not event.isAutoRepeat():self.microphone_keys.discard(event.key())
            event.accept();return
        super().keyReleaseEvent(event)


class Rpc(QThread):
    done=pyqtSignal(object)
    def __init__(self,base,token,path,data=None,raw=False,binary=False,timeout=8):
        super().__init__();self.base=base;self.token=token;self.path=path;self.data=data;self.raw=raw;self.binary=binary;self.timeout=timeout
        self.memory_access='';self.client_id=''
    def run(self):
        try:
            payload=self.data if self.binary else json.dumps(self.data).encode() if self.data is not None else None
            req=Request(self.base+'/api/'+self.path,data=payload,headers={'Authorization':'Bearer '+self.token,
                'Content-Type':('audio/wav' if self.path.startswith('audio/transcribe') else 'application/octet-stream') if self.binary else 'application/json'})
            if self.memory_access:req.add_header('X-Memory-Access',self.memory_access)
            if self.client_id:req.add_header('X-Central-Client',self.client_id)  # 07/11: só a janela ativa comanda
            with urlopen(req,timeout=self.timeout) as response:
                value=response.read(40*1024**2+1) if self.raw else json.load(response)
                if self.raw and len(value)>40*1024**2:raise ValueError('Resposta acima do limite de áudio.')
            self.done.emit({'ok':True,'value':value})
        except HTTPError as exc:
            try:message=json.loads(exc.read(4096)).get('error','Pedido recusado pela central.')
            except Exception:message='Pedido recusado pela central.'
            self.done.emit({'ok':False,'error':message,'status':exc.code})
        except Exception as exc:
            refused=isinstance(getattr(exc,'reason',exc),ConnectionRefusedError)  # 07/11: porta fechada = Central fechada
            self.done.emit({'ok':False,'refused':refused,'error':'Central indisponível ou prazo excedido. Resultado não confirmado; pedido mutável não foi repetido.'})


class InteractionReview(QDialog):
    """Avaliação voluntária; nunca manda gerar exemplos ou iniciar treinamento."""
    def __init__(self, message, parent=None):
        super().__init__(parent);self.setWindowTitle('Avaliar interação');self.resize(420,290)
        layout=QVBoxLayout(self)
        hint=QLabel('Como foi esta resposta? Sua avaliação ajuda a orientar o professor depois.\nNão altera memórias nem inicia treinamento.');hint.setWordWrap(True);layout.addWidget(hint)
        meta=message.get('metadata') or {};review=meta.get('human_feedback') or {}
        self.decision=QComboBox();self.decision.setAccessibleName('Avaliação da resposta')
        for title,value in [('Escolha uma avaliação…',None),('Gostei','liked'),('Pode melhorar','disliked'),('Remover avaliação','clear')]:self.decision.addItem(title,value)
        self.decision.setCurrentIndex(max(0,self.decision.findData(review.get('decision'))));layout.addWidget(self.decision)
        self.note=QPlainTextEdit();self.note.setPlaceholderText('Opcional: o que gostou ou o que poderia melhorar? Até600 caracteres.');self.note.setPlainText(review.get('note',''));layout.addWidget(self.note)
        self.error=QLabel('');self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Save).setText('Salvar');buttons.button(QDialogButtonBox.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.accept_review);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def accept_review(self):
        if self.decision.currentData() is None:self.error.setText('Escolha Gostei ou Pode melhorar.');return
        if len(self.note.toPlainText())>600:self.error.setText('Use até600 caracteres na observação.');return
        self.accept()


class PasswordSetup(QDialog):
    """Cadastro local em uma tela; recusa fica visível, sem reabrir perguntas."""
    save_requested=pyqtSignal(object)
    check_requested=pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('Senha de exclusão de memórias');self.resize(440,290)
        self.setWindowModality(Qt.WindowModal);self.known=False;self.configured=False;self.busy=False
        layout=QVBoxLayout(self)
        hint=QLabel('Senha local para proteger a exclusão de memórias. Não é a senha do computador.\nUse de 8 a 200 caracteres. Salvar não apaga nenhuma memória.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.state_label=QLabel('Conferindo se já existe uma senha…');self.state_label.setWordWrap(True);layout.addWidget(self.state_label)
        self.old_row=QWidget();old_form=QFormLayout(self.old_row);old_form.setContentsMargins(0,0,0,0)
        self.old=QLineEdit();self.old.setEchoMode(QLineEdit.Password);old_form.addRow('Senha atual:',self.old)
        layout.addWidget(self.old_row);self.old_row.hide()
        form=QFormLayout();self.password=QLineEdit();self.confirm=QLineEdit()
        for field in (self.password,self.confirm):field.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText('Pelo menos 8 caracteres')
        form.addRow('Nova senha:',self.password);form.addRow('Repita a nova senha:',self.confirm);layout.addLayout(form)
        self.error=QLabel('');self.error.setWordWrap(True);layout.addWidget(self.error)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        self.save_button=self.buttons.button(QDialogButtonBox.Save);self.save_button.setText('Salvar senha')
        self.buttons.button(QDialogButtonBox.Cancel).setText('Cancelar')
        self.check_button=self.buttons.addButton('Conferir estado',QDialogButtonBox.ActionRole)
        self.buttons.accepted.connect(self.submit);self.buttons.rejected.connect(self.reject)
        self.check_button.clicked.connect(lambda:self.check_requested.emit());layout.addWidget(self.buttons)
        self.finished.connect(self.clear_fields);self.set_busy(True)
    def clear_fields(self,*_):
        for field in (self.old,self.password,self.confirm):field.clear()
    def set_busy(self,busy):
        self.busy=busy
        self.save_button.setEnabled(not busy and self.known);self.check_button.setEnabled(not busy)
        for field in (self.old,self.password,self.confirm):field.setEnabled(not busy)
    def state(self,configured):
        self.known=True;self.configured=configured;self.old_row.setVisible(configured)
        self.state_label.setText('Já existe uma senha. Informe a atual para alterá-la.' if configured else 'Nenhuma senha de exclusão cadastrada.')
    def submit(self):
        if self.busy or not self.known:return
        password=self.password.text()
        if not 8<=len(password)<=200:
            self.error.setText('A senha precisa ter de 8 a 200 caracteres.');self.password.setFocus();return
        if password!=self.confirm.text():
            self.error.setText('As duas senhas não coincidem. Confira os campos.');self.confirm.setFocus();return
        if self.configured and not self.old.text():
            self.error.setText('Informe a senha atual para alterá-la.');self.old.setFocus();return
        self.error.setText('Salvando e conferindo a gravação…');self.set_busy(True)
        self.save_requested.emit(dict(password=password,password_confirm=self.confirm.text(),old_password=self.old.text() if self.configured else ''))


_RICH=re.compile(r'(https?://[^\s<>"\]\)]+)|\[\[imagem:([0-9a-f]{12})\]\]')


def rich_text(text):
    """06/11 (pedido humano): links clicáveis e imagens anexadas pelas entidades ([[imagem:ID]]) no chat."""
    out,last=[],0
    for m in _RICH.finditer(text or ''):
        out.append(html.escape(text[last:m.start()]))
        if m.group(1):
            url=m.group(1).rstrip('.,;:!?')
            out.append('<a style="color:#9fc6ff" href="'+html.escape(url,quote=True)+'">'+html.escape(url)+'</a>'+html.escape(m.group(1)[len(url):]))
        else:
            out.append('<br><img src="anexo:'+m.group(2)+'" width="360"><br>')
        last=m.end()
    out.append(html.escape((text or '')[last:]))
    return ''.join(out).replace('\n','<br>')


class ChatBrowser(QTextBrowser):
    """Chat que busca no backend as imagens anexadas (anexo:ID), com cache; falha vira imagem vazia, não trava."""
    def __init__(self,fetch,parent=None):
        super().__init__(parent);self.fetch=fetch;self.images={}
    def loadResource(self,kind,url):
        if url.scheme()=='anexo':
            ident=url.path() or url.toString().split(':',1)[-1]
            if ident not in self.images:
                data=self.fetch(ident) if re.fullmatch(r'[0-9a-f]{12}',ident) else None
                image=QImage();image.loadFromData(data or b'')
                self.images[ident]=image
            return self.images[ident]
        return super().loadResource(kind,url)


def chat_bubbles(conversation, entity, human_name='Usuário'):
    lines=[];targets={}
    for message in conversation[-150:]:
        meta=message.get('metadata') or {};meta=meta if isinstance(meta,dict) else {}
        processing=meta.get('processing');status=(processing.get('status') if isinstance(processing,dict) else None) or ('lida' if message.get('read_at') else 'guardada')
        display=lambda participant:human_name if participant=='usuario' else str(participant or '?').capitalize()
        target=('Global · '+', '.join(str(e).capitalize() for e in meta['broadcast_targets'])) if message.get('sender')=='usuario' and isinstance(meta.get('broadcast_targets'),list) else display(message.get('recipient'))
        title=f"{display(message.get('sender'))} → {target} · {message.get('time',{}).get('local') or message.get('created_at','')} · {meta.get('source',message.get('kind','chat'))} · {status}"
        streams=meta.get('text_streams')
        stable=next((value for value in reversed(streams) if isinstance(value,str) and value),message.get('id')) if isinstance(streams,list) else message.get('id')
        def anchored(part,text):
            return ('<a name="'+html.escape('chat-'+stable+':'+part,quote=True)+'">'+text+'</a>') if isinstance(stable,str) and stable else text
        color=COLORS.get(message.get('sender'),'#b9afd0')
        lines.append('<p style="color:'+color+'">'+anchored('header',html.escape(title))+'</p><p>'+anchored('body',rich_text(message.get('text','')))+'</p>')
        target=message.get('feedback_target');identifier=message.get('id')
        if (entity not in ENTITIES or message.get('sender') not in ENTITIES or message.get('recipient')!='usuario' or not isinstance(identifier,str) or
                not isinstance(target,dict) or meta.get('private') or message.get('kind') in ('deleted','diary')):continue
        review=meta.get('human_feedback') or {};review=review if isinstance(review,dict) else {}
        label={'liked':'✓ Gostei','disliked':'↺ Pode melhorar'}.get(review.get('decision'),'☆ Avaliar')
        link='feedback://'+message['sender']+'/?'+urlencode({'message_id':identifier})
        lines.append('<p style="margin-top:0;font-size:11px"><a style="color:#a29bb2;text-decoration:none" href="'+html.escape(link,quote=True)+'">'+label+'</a></p>')
        targets[identifier]=dict(message,metadata=meta)
    return ''.join(lines),targets


def hotkey_runtime(root):
    """Python que escuta o atalho global: o do projeto (PC1) ou, no painel do PC2, o do sistema com pynput."""
    principal=Path(root)/'compartilhado/ambientes/principal/bin/python'
    if principal.is_file():return principal
    import importlib.util
    if importlib.util.find_spec('pynput') is not None:return Path(sys.executable)
    return None


def draft_keeps_transcript(transcript, text):
    """O rascunho ainda conserva a fala gravada? Mesma regra da Central (`audio_origin`) e do painel web."""
    words=lambda value:re.findall(r'\w+',str(value or '').casefold())
    source,draft=words(transcript),set(words(text))
    overlap=sum(word in draft for word in source)
    return bool(source) and overlap>=(len(source) if len(source)<4 else (len(source)+1)//2)


class Central(LiveASRClient,QMainWindow):
    def __init__(self,root,entity='hoshino'):
        super().__init__();self.root=Path(root);self.base,self.token=endpoint(root);self.workers=[]
        self.drafts={e:'' for e in ENTITIES};self.scope_drafts={};self.chat_scope='global';self.origins={};self.submissions={};self.last_entity=entity;self.polling=False
        self.capture=None;self.segmenter=None;self.capture_entity=None;self.capture_test=False;self.asr_jobs={};self.last_test_pcm=None
        self.capture_session=None;self.capture_scope='global';self.asr_waiting=[];self.init_live_asr()
        self.acoustic_windows=AcousticWindows();self.acoustic_capture_id=None;self.acoustic_sequence=0
        self.acoustic_pending=False;self.acoustic_waiting=None;self.acoustic_dropped=0;self.acoustic_playback_until=0;self.asr_echo=False
        self.acoustic_stop_pending=None
        self.ambient_allowed={e:True for e in ENTITIES};self.ambient_policy_polling=False;self.ambient_policy_checked=0
        self.hotkey_process=None;self.hotkey_signature=None;self.hotkey_buffer=b'';self.hotkey_capture=None
        self.hotkey_test_until=0
        self.mic_settings={'mode':'command','source':'','output':'','threshold':.012,'silence_ms':2000,'segment_seconds':8,'auto_send':False,'output_volume':100}
        self.mic_revision='';self.audio_config=None;self.ui_config=None;self.tool_config=None;self.model_config=None
        self.voice_job=None;self.voice_index=0;self.voice_fetching=False;self.voice_done=False;self.voice_test=False
        self.voice_entity=None;self.voice_epoch=0;self.player=None;self.player_file=None;self.voice_pending={};self.voice_seen=set();self.voice_initialized=set()
        self.stream_seen=set();self.resume_capture=None;self.connected=False;self.focus_id='native-'+uuid.uuid4().hex;self.chat_html=None
        self.chat_session={};self.chat_read_only=True;self.chat_selected='';self.chat_day='';self.chat_query=''
        self.chat_generation=0;self.chat_before=0;self.chat_upper=None;self.chat_cursors=[];self.chat_page={};self.password_dialog=None
        self.chat_state=None;self.chat_previews={};self.chat_stream_pending=None
        self.memory_access='';self.memory_entity=None;self.memory_until=0;self.memory_generation=0
        self.memory_timer=QTimer(self);self.memory_timer.setSingleShot(True);self.memory_timer.timeout.connect(self.lock_memories)
        self.entity_details={};self.closing=False;self.temp=tempfile.TemporaryDirectory(prefix='hoshino-ui-');self.setWindowTitle('Central')  # 11/11: o título vira percepção delas; sem os três nomes
        self.setWindowIcon(QIcon(str(self.root/'desktop/hoshino-e-lilith.svg')))
        self.shutdown_pending=False;self.ui_only_smoke=False;self.shutdown_generation=None;self.shutdown_requested_at=0
        self.shutdown_timer=QTimer(self);self.shutdown_timer.setInterval(400);self.shutdown_timer.timeout.connect(self.poll_shutdown)
        self.player_stream=None;self.volume_process=None;self.volume_timer=QTimer(self)
        self.volume_timer.setSingleShot(True);self.volume_timer.timeout.connect(self.apply_volume)
        self.resize(1220,820);self.setMinimumSize(900,650)
        self.setStyleSheet(STYLE)
        wrapper=QWidget();self.setCentralWidget(wrapper);outer=QVBoxLayout(wrapper)
        outer.setContentsMargins(18,12,18,12);outer.setSpacing(14)
        top=QHBoxLayout();brand=QLabel('H · L · A');brand.setObjectName('brand');top.addWidget(brand)
        top.addWidget(QLabel('CENTRAL LOCAL  /  presença & conexão'));top.addStretch()
        self.entity=QComboBox();self.entity.addItems([e.capitalize() for e in ENTITIES]);self.entity.setCurrentIndex(ENTITIES.index(entity));top.addWidget(self.entity)
        top.addWidget(self.button('Encerrar com segurança',self.shutdown));outer.addLayout(top)
        # 06/11 (pedido humano): alerta na tela quando uma entidade fica sem VRAM e não consegue usar a GPU.
        self.gpu_alert_box=QFrame();self.gpu_alert_box.setObjectName('gpuAlert');alert_row=QHBoxLayout(self.gpu_alert_box)
        alert_row.setContentsMargins(14,10,10,10);self.gpu_alert_text=QLabel('');self.gpu_alert_text.setObjectName('gpuAlertText')
        self.gpu_alert_text.setWordWrap(True);alert_row.addWidget(self.gpu_alert_text,1)
        alert_row.addWidget(self.button('Abrir Modelos',self.open_gpu_alert_models));alert_row.addWidget(self.button('Dispensar',self.dismiss_gpu_alert))
        outer.addWidget(self.gpu_alert_box);self.gpu_alert_box.hide()
        # 07/11 (pedido humano): PC1 e PC2 não comandam juntos; vale a última janela que recebeu foco.
        self.window_active=True;self.window_pause_box=QFrame();self.window_pause_box.setObjectName('gpuAlert')
        pause_row=QHBoxLayout(self.window_pause_box);pause_row.setContentsMargins(14,10,10,10)
        pause_text=QLabel('Esta janela está em pausa: a outra janela da Central está em uso. Mensagens, microfone e '
                          'configurações só funcionam numa janela por vez.');pause_text.setObjectName('gpuAlertText')
        pause_text.setWordWrap(True);pause_row.addWidget(pause_text,1);pause_row.addWidget(self.button('Usar esta janela',self.claim_window))
        outer.addWidget(self.window_pause_box);self.window_pause_box.hide()
        self.gpu_alerts=[];self.gpu_alert_notified=set();self.gpu_alert_dismissed=set();self.gpu_alert_sent=None
        main=QHBoxLayout();main.setSpacing(20);outer.addLayout(main,1);self.nav=QListWidget();self.nav.setObjectName('navigation');self.nav.addItems(PAGES);self.nav.setFixedWidth(184);main.addWidget(self.nav)
        self.stack=QStackedWidget();main.addWidget(self.stack,1);self.pages={}
        self.page_effect=QGraphicsOpacityEffect(self.stack);self.stack.setGraphicsEffect(self.page_effect)
        self.page_animation=QPropertyAnimation(self.page_effect,b'opacity',self);self.page_animation.setDuration(180);self.page_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.page_effect.setEnabled(False);self.page_animation.finished.connect(lambda:self.page_effect.setEnabled(False))
        descriptions=('Três presenças. Cada uma com seu próprio mundo.','Um espaço para conversar, ouvir e compartilhar.','Sua voz, a voz delas. Tudo no seu ritmo.','Lembranças com autoria, origem e contexto.','Pessoas, assuntos e conceitos aprendidos, com fontes.','Capacidades existentes, sob seu controle.','Executores locais e arquivos instalados.','Treinamentos separados e curadoria MoE, somente mediante autorização.','Residência e processamento, sem confundir os dois.','Acompanhe o que aconteceu e de onde veio.','Ajuste seu espaço sem alterar as entidades.','Conexões e disponibilidade dos serviços.','Evidências técnicas para entender cada falha.')
        for name in PAGES:
            page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(4,4,12,8);layout.setSpacing(12)
            title=QLabel(name);title.setObjectName('pageTitle');layout.addWidget(title)
            subtitle=QLabel(descriptions[PAGES.index(name)]);subtitle.setObjectName('subtitle');subtitle.setWordWrap(True);layout.addWidget(subtitle);self.pages[name]=layout
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);self.stack.addWidget(scroll)
        self.notice=QLabel('Conectando ao backend existente…');self.notice.setWordWrap(True);outer.addWidget(self.notice)
        self.notice.setObjectName('notice')
        self.build_entities();self.build_chat();self.build_audio();self.build_memory();self.build_tools();self.build_models();self.build_laboratory();self.build_settings()
        self.memory_gate=QStackedWidget();self.pages['Memórias'].addWidget(self.memory_gate)
        locked=QWidget();lock_layout=QVBoxLayout(locked);self.memory_gate.addWidget(locked)
        lock_layout.addWidget(QLabel('Memórias protegidas · use a senha local para abrir os cartões desta entidade.'))
        lock_layout.addWidget(self.button('Desbloquear Memórias',self.unlock_memories));lock_layout.addWidget(self.button('Definir / alterar senha',self.set_password));lock_layout.addStretch()
        unlocked=QWidget();unlocked_layout=QVBoxLayout(unlocked);self.memory_gate.addWidget(unlocked)
        unlocked_layout.addWidget(self.button('Bloquear Memórias agora',lambda:self.lock_memories()))
        self.memory_tabs=QTabWidget();unlocked_layout.addWidget(self.memory_tabs)
        self.knowledge_panel=KnowledgePanel(self.load_knowledge,self.edit_knowledge,lambda:not self.reduced_motion.isChecked())
        self.memory_tabs.addTab(self.knowledge_panel,'Cartões');self.memory_tabs.addTab(self.logic_workshop,'Oficina de lógica')
        self.views={}
        self.resources_panel=ResourcesPanel();self.pages['Recursos'].addWidget(self.resources_panel)
        self.activity_panel=ActivityPanel();self.pages['Atividade'].addWidget(self.activity_panel)
        self.activity_panel.show_routine.toggled.connect(lambda _:self.refresh_active())
        self.history_timeline=HistoryTimelinePanel(self.load_history_timeline,self.preview_clipboard_attachment)
        self.activity_panel.tabs.insertTab(0,self.history_timeline,'Linha do tempo')
        self.activity_panel.tabs.setCurrentIndex(0)
        self.services_panel=ServicesPanel(lambda:self.nav.setCurrentRow(PAGES.index('Áudio')));self.pages['Serviços'].addWidget(self.services_panel)
        self.diagnostics_panel=ActivityPanel(include_commands=False);self.pages['Diagnóstico'].addWidget(self.diagnostics_panel);self.diagnostics_panel.show_routine.hide()  # erros nunca são rotina
        self.nav.currentRowChanged.connect(self.change_page);self.entity.currentIndexChanged.connect(self.change_entity);self.nav.setCurrentRow(0)
        self.state_timer=QTimer(self);self.state_timer.timeout.connect(self.refresh);self.state_timer.start(2000)
        self.chat_stream_timer=QTimer(self);self.chat_stream_timer.timeout.connect(self.poll_chat_streams);self.chat_stream_timer.start(250)
        self.detail_timer=QTimer(self);self.detail_timer.timeout.connect(lambda:self.refresh_active(True));self.detail_timer.start(5000)
        self.audio_timer=QTimer(self);self.audio_timer.timeout.connect(self.poll_audio);self.audio_timer.start(350)
        self.focus_timer=QTimer(self);self.focus_timer.timeout.connect(self.report_focus);self.focus_timer.start(10000)
        self.gpu_alert_timer=QTimer(self);self.gpu_alert_timer.timeout.connect(self.poll_gpu_alerts);self.gpu_alert_timer.start(3000)
        # Cada cópia do sistema (Ctrl+C em qualquer app) espera 0,4 s e vai sozinha para a área compartilhada.
        self.clipboard_last=None;self.clipboard_timer=QTimer(self);self.clipboard_timer.setSingleShot(True);self.clipboard_timer.setInterval(400)
        self.clipboard_timer.timeout.connect(self.capture_clipboard);QApplication.clipboard().dataChanged.connect(self.clipboard_timer.start)
        # 06/11 (pedido humano): no PC2 o painel é o corpo remoto — manda os sentidos de lá e executa comandos pedidos.
        self.pc2_sense_process=None;self.pc2_sense_sent=None;self.pc2_command=None;self.pc2_poll_sent=None
        self.pc2_sense_timer=QTimer(self);self.pc2_sense_timer.timeout.connect(self.pc2_collect_senses);self.pc2_sense_timer.start(10000)
        self.pc2_command_timer=QTimer(self);self.pc2_command_timer.timeout.connect(self.pc2_poll_commands);self.pc2_command_timer.start(2000)
        self.pc2_bridge=None;self.pc2_bridge_timer=QTimer(self);self.pc2_bridge_timer.timeout.connect(self.pc2_bridge_show)
        if self.remote_panel():self.pc2_bridge_timer.start(2000);QTimer.singleShot(1500,self.pc2_bridge_apply)
        self.request('control/microphone',callback=self.loaded_microphone);self.load_interface();self.refresh();self.refresh_active()
    def current_entity(self):return ENTITIES[self.entity.currentIndex()]
    def remote_panel(self):return urlsplit(self.base or '').hostname not in (None,'127.0.0.1')
    def owned_timeout(self,process,ms):
        timer=QTimer(process);timer.setSingleShot(True)
        timer.timeout.connect(lambda:process.kill() if process.state()!=QProcess.NotRunning else None)
        process.finished.connect(timer.stop);timer.start(ms)
    def button(self,title,callback):
        b=QPushButton(title);b.setCursor(Qt.PointingHandCursor);b.setProperty('primary',title in {'Conversar','Enviar','Salvar preferências','Salvar provider / vozes'});b.clicked.connect(callback);return b
    def bar(self,layout,buttons):
        row=QHBoxLayout()
        for title,fn in buttons:row.addWidget(self.button(title,fn))
        row.addStretch();layout.addLayout(row);return row
    def invalidate_local_connection(self):
        # Só processos/client-state próprios. IDs antigos não são reenviados ao
        # novo backend; rascunhos e texto de teste continuam nesta janela.
        self.lock_memories(revoke=False);self.discard_live(cancel=False)
        self.stop_acoustic(notify=False)
        self.stop_capture(False);self.stop_voice(cancel=False);self.asr_jobs.clear();self.asr_waiting.clear()
        self.polling=False;self.connected=False;self.entity_details={}
        self.audio_config=None;self.ui_config=None;self.tool_config=None;self.model_config=None
        self.voice_initialized.clear();self.voice_seen.clear();self.stream_seen.clear()
        self.auto_voice.setChecked(False)
        if self.password_dialog is not None:self.password_dialog.reject()
        if hasattr(self,'chat_days'):self.reset_chat_view()
        if hasattr(self,'history_timeline'):self.history_timeline.set_entity('')
    def sync_endpoint(self):
        try:connection=endpoint(self.root)
        except (OSError,ValueError):
            self.invalidate_local_connection()
            self.notice.setText('Central indisponível. Pedidos anteriores não foram repetidos; confira o estado antes de tentar novamente.')
            return False
        if connection!=(self.base,self.token):
            self.base,self.token=connection;self.invalidate_local_connection()
            self.notice.setText('Central reiniciada; conexão atualizada. Pedidos anteriores não foram repetidos; confira o estado antes de tentar novamente.')
        return True
    def request(self,path,data=None,callback=None,raw=False,binary=False,timeout=8,quiet=False,silent=False):
        cleanup=path in ('audio/cancel','audio/perception/stop','audio/job','control/focus')
        if self.closing and not cleanup:return
        if self.shutdown_pending and data is not None and not cleanup and path!='control/shutdown':return
        if not self.sync_endpoint():return
        # Uma única obrigação de cancelamento tem um slot reservado. Detecção
        # nova fica bloqueada até a confirmação, portanto não abre fila extra.
        reserved_cancel=(path=='audio/perception/stop' and isinstance(data,dict) and
                         self.acoustic_stop_pending is not None and
                         data.get('capture_id')==self.acoustic_stop_pending['capture_id'] and
                         not self.acoustic_stop_pending.get('admitted'))
        if not reserved_cancel and len(self.workers)>=(16 if self.closing and cleanup else 8):
            if not quiet:self.notice.setText('Aguarde os pedidos em andamento; nada novo foi enviado.')
            return
        connection=(self.base,self.token)
        worker=Rpc(*connection,path,data,raw,binary,timeout);self.workers.append(worker);worker.client_id=getattr(self,'focus_id','')
        protected=path.split('?')[0] in {'control/knowledge','control/logic'}
        memory_generation=self.memory_generation
        memory_access=self.memory_access
        if protected or path=='control/knowledge/lock':worker.memory_access=memory_access
        def finish(out):
            self.track_remote_central(out)
            if not self.sync_endpoint() or connection!=(self.base,self.token):
                # Nem aplicar callback de resposta velha, nem cancelar um ID
                # estrangeiro na sessão nova, nem repetir pedido mutável.
                if data is not None:self.notice.setText('Conexão mudou durante o pedido; resultado não confirmado. Pedidos anteriores não foram repetidos.')
                return
            if protected and memory_access and (memory_generation!=self.memory_generation or memory_access!=self.memory_access):
                if data is not None:self.notice.setText('Memórias bloqueadas durante o pedido. Confira o resultado ao desbloquear; nada foi repetido.')
                return
            if self.closing:
                if out['ok'] and (path in ('audio/test','audio/synthesize','audio/stream') or path.startswith('audio/transcribe?')):
                    self.request('audio/cancel',{'id':out['value']['id']},quiet=True)
                return
            if not out['ok']:
                if protected and out.get('status')==403:self.lock_memories(revoke=False)
                if out.get('status')==409 and 'janela está em pausa' in str(out.get('error')):self.set_window_active(False)
                if not silent:self.notice.setText(out['error'])  # poller de fundo (alerta VRAM) não cobre avisos
                if callback:callback(None)
            elif callback:callback(out['value'])
            else:self.notice.setText('Pedido aceito; confira estado/diagnóstico para confirmação.')
        worker.done.connect(finish);worker.finished.connect(lambda:self.workers.remove(worker));worker.start();return worker
    def query(self,path,**params):return path+'?'+urlencode({k:v for k,v in params.items() if v is not None and v is not False and v!=''})
    def pretty(self,value):return json.dumps(value,ensure_ascii=False,indent=2)
    def change_page(self,index):
        if PAGES[index]!='Memórias' and self.memory_access:self.lock_memories()
        self.page_animation.stop();self.stack.setCurrentIndex(index)
        if not self.reduced_motion.isChecked():
            self.page_effect.setEnabled(True);self.page_animation.setStartValue(.55);self.page_animation.setEndValue(1.0);self.page_animation.start()
        else:self.page_effect.setEnabled(False)
        self.refresh_active()
    def focus_entity(self,entity):self.entity.setCurrentIndex(ENTITIES.index(entity));self.nav.setCurrentRow(1);self.showNormal();self.raise_();self.activateWindow()
    def report_focus(self,closed=False):
        self.request('control/focus',{'client_id':self.focus_id,'focused':self.isActiveWindow(),'closed':closed,'client':'native'},callback=self.focus_result,quiet=True)
    def claim_window(self):
        self.request('control/focus',{'client_id':self.focus_id,'focused':True,'closed':False,'client':'native'},callback=self.focus_result,quiet=True)
    def focus_result(self,out):
        if isinstance(out,dict) and isinstance(out.get('active'),bool) and not self.closing:self.set_window_active(out['active'])
    def set_window_active(self,active):
        if active==self.window_active:return
        self.window_active=active;self.window_pause_box.setVisible(not active)
        if not active:
            if self.hotkey_capture is self.capture and self.capture:self.stop_capture(False)
            self.hotkey_capture=None
        self.notice.setText('Esta janela voltou a comandar.' if active else 'Janela em pausa: a outra janela da Central está em uso.')
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.ActivationChange and hasattr(self,'focus_id') and not self.closing:self.report_focus()
        if event.type()==QEvent.WindowStateChange and self.isMinimized() and getattr(self,'memory_access',''):self.lock_memories()
    def change_entity(self,index):
        if self.memory_access:self.lock_memories()
        self.activity_panel.render({'items':[]});self.activity_panel.render_commands({'items':[]})
        self.diagnostics_panel.render({'items':[]})
        self.history_timeline.set_entity(self.current_entity())
        self.drafts[self.last_entity]=self.draft.toPlainText();self.last_entity=self.current_entity();self.draft.setPlainText(self.drafts[self.last_entity])
        self.reset_chat_view()
        self.knowledge_panel.clear();self.knowledge_panel.page=0
        self.listening_panel.clear()
        self.stop_capture(False);self.stop_voice();self.refresh();self.refresh_active()
    def build_entities(self):
        layout=self.pages['Entidades']  # 07/11 (pedido humano): sem o botão do laboratório aqui; fica na aba própria
        row=QHBoxLayout();layout.addLayout(row);self.cards={}
        for e in ENTITIES:
            group=QGroupBox();group.setStyleSheet('QGroupBox{border-top:2px solid '+COLORS[e]+';}')
            card=QVBoxLayout(group);card.setSpacing(12);card.setAlignment(Qt.AlignTop)
            title=QLabel(e.capitalize());title.setFixedHeight(54);title.setStyleSheet('font-size:22px;font-weight:600;color:'+COLORS[e]+';padding:8px 0;');card.addWidget(title)
            label=QLabel('Consultando estado…');label.setMinimumHeight(150);label.setAlignment(Qt.AlignTop);label.setWordWrap(True);card.addWidget(label);self.cards[e]=label
            card.addWidget(self.button('Acordar',lambda _,who=e:self.request('start',{'entity':who})))
            card.addWidget(self.button('Dormir',lambda _,who=e:self.sleep(who)))
            card.addWidget(self.button('Conversar',lambda _,who=e:self.focus_entity(who)))
            if e!='alistair':card.addWidget(self.button('Interromper fala',lambda _,who=e:self.interrupt(who)))
            else:card.addSpacing(38)
            row.addWidget(group)
        details=QCheckBox('Mostrar detalhes técnicos das entidades');layout.addWidget(details)
        self.entities_detail=QPlainTextEdit();self.entities_detail.setReadOnly(True);self.entities_detail.hide();details.toggled.connect(self.entities_detail.setVisible);layout.addWidget(self.entities_detail,1)
        layout.addStretch()
    def build_chat(self):
        layout=self.pages['Conversa'];channel_row=QHBoxLayout();layout.addLayout(channel_row)
        self.chat_channel=QComboBox();self.chat_channel.addItem('Global · principal','global');self.chat_channel.addItem('Direto · com a entidade selecionada','direct')
        channel_row.addWidget(self.chat_channel);channel_row.addWidget(QLabel('Global: todas as acordadas recebem. Direto: só a selecionada. Nome: perspectiva individual selecionada.'))
        self.chat_channel.currentIndexChanged.connect(self.change_chat_scope)
        session_row=QHBoxLayout();layout.addLayout(session_row)
        self.chat_days=QComboBox();self.chat_days.setAccessibleName('Dia da conversa');session_row.addWidget(self.chat_days,1)
        session_row.addWidget(self.button('Hoje',self.chat_today))
        self.chat_date=QLineEdit();self.chat_date.setPlaceholderText('AAAA-MM-DD');self.chat_date.setMaximumWidth(130);session_row.addWidget(self.chat_date)
        session_row.addWidget(self.button('Buscar data',self.chat_find_day))
        self.chat_days.currentIndexChanged.connect(self.chat_select_day)
        self.chat_search=QLineEdit();self.chat_search.setPlaceholderText('Buscar assunto neste dia · Enter para aplicar');self.chat_search.setMaxLength(200)
        self.chat_search.returnPressed.connect(self.chat_find_topic);layout.addWidget(self.chat_search)
        self.chat_hint=QLabel('Consultando sessão atual…');self.chat_hint.setWordWrap(True);layout.addWidget(self.chat_hint)
        pages=QHBoxLayout();self.chat_older=self.button('Mais antigas',lambda:self.chat_paginate(True));self.chat_newer=self.button('Mais recentes',lambda:self.chat_paginate(False))
        pages.addWidget(self.chat_older);pages.addWidget(self.chat_newer);pages.addStretch();layout.addLayout(pages)
        # Um painel só, como nos chats comuns: histórico em cima e a caixa de mensagem
        # embaixo, dentro dele, com anexar à esquerda e enviar à direita (pedido humano 11/11).
        panel=QFrame();panel.setObjectName('chatPanel');box=QVBoxLayout(panel);box.setContentsMargins(1,1,1,1);box.setSpacing(0)
        self.chat=ChatBrowser(self.fetch_attachment);self.chat.setObjectName('chatHistory');self.chat.setOpenLinks(False);self.chat.setOpenExternalLinks(False)
        self.chat.anchorClicked.connect(self.review_interaction);self.review_targets={};box.addWidget(self.chat,1)
        self.live_preview=QPlainTextEdit();self.live_preview.setObjectName('chatLive');self.live_preview.setReadOnly(True);self.live_preview.setMaximumHeight(85)
        self.live_preview.setPlaceholderText('Escutando · transcrição em andamento, ainda pode mudar…');self.live_preview.hide();box.addWidget(self.live_preview)
        composer=QFrame();composer.setObjectName('chatComposer');line=QHBoxLayout(composer);line.setContentsMargins(8,6,8,6);line.setSpacing(6)
        self.chat_attach=QPushButton('+');self.chat_attach.setObjectName('chatIcon');self.chat_attach.setCursor(Qt.PointingHandCursor)
        self.chat_attach.setToolTip('Anexar arquivo');self.chat_attach.setAccessibleName('Anexar');self.chat_attach.clicked.connect(self.attach)
        self.draft=ChatDraft();self.draft.setObjectName('chatDraft');self.draft.send_requested.connect(self.send)
        self.draft.setPlaceholderText('Mensagem… Enter envia · Shift+Enter quebra linha')
        self.draft.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded);self.draft.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.draft.document().contentsChanged.connect(self.fit_draft)
        self.chat_send=QPushButton('↑');self.chat_send.setObjectName('chatSend');self.chat_send.setCursor(Qt.PointingHandCursor)
        self.chat_send.setToolTip('Enviar (Enter)');self.chat_send.setAccessibleName('Enviar');self.chat_send.clicked.connect(self.send)
        line.addWidget(self.chat_attach,0,Qt.AlignBottom);line.addWidget(self.draft,1);line.addWidget(self.chat_send,0,Qt.AlignBottom)
        holder=QWidget();holder.setObjectName('chatComposerArea');around=QVBoxLayout(holder);around.setContentsMargins(12,6,12,12);around.addWidget(composer)
        box.addWidget(holder);layout.addWidget(panel,1);self.fit_draft()
        self.operation=QLabel('Sem operação observada');self.operation.setObjectName('chatOperation');self.operation.setWordWrap(True);layout.addWidget(self.operation)
        self.auto_voice=QCheckBox('Ler novas respostas em voz (pode consumir quota)');layout.addWidget(self.auto_voice)
        row=self.bar(layout,[('Interromper fala',self.stop_voice),('Microfone · aba Áudio',lambda:self.nav.setCurrentRow(PAGES.index('Áudio')))])
        self.chat_clipboard = self.button('Importar conteúdo copiado', self.import_clipboard)
        self.chat_clipboard.setToolTip('Importa o texto ou print atual na conversa direta com Hoshino ou Lilith.')
        row.insertWidget(1,self.chat_clipboard)
        self.chat_record=QPushButton('Iniciar / parar detecção');self.chat_record.clicked.connect(self.toggle_capture)
        self.ptt=QPushButton('Comando · segure para falar');self.ptt.pressed.connect(self.ptt_start);self.ptt.released.connect(lambda:self.stop_capture(True))
        self.level=QProgressBar();self.level.setRange(0,100);self.level.setFormat('Nível do microfone: %p%')
        self.chat_controls()

    def fit_draft(self):
        """Caixa de mensagem cresce com o texto, de 1 até 6 linhas; depois rola."""
        lines=max(1,min(6,int(self.draft.document().size().height())))
        frame=self.draft.contentsMargins();doc=self.draft.document().documentMargin()
        self.draft.setFixedHeight(int(lines*self.draft.fontMetrics().lineSpacing()+2*doc+frame.top()+frame.bottom()+8))

    def change_chat_scope(self,*_):
        e=self.current_entity();self.scope_drafts[self.chat_scope]=dict(self.drafts,**{e:self.draft.toPlainText()})
        self.chat_scope=self.chat_channel.currentData();self.drafts=dict(self.scope_drafts.get(self.chat_scope,{e:'' for e in ENTITIES}))
        self.draft.setPlainText(self.drafts[e]);self.origins.clear()
        self.stop_capture(False);self.stop_voice();self.reset_chat_view();self.refresh()
    def chat_controls(self):
        self.draft.setReadOnly(self.chat_read_only)
        for widget in (self.chat_send,self.chat_attach):widget.setEnabled(not self.chat_read_only)
        self.chat_clipboard.setEnabled(self.can_import_clipboard())
        self.chat_record.setEnabled(not self.chat_read_only and self.mic_settings['mode']=='detection')
        self.ptt.setEnabled(not self.chat_read_only and self.mic_settings['mode']=='command')
        self.chat_older.setEnabled(bool(self.chat_page.get('has_more')));self.chat_newer.setEnabled(bool(self.chat_cursors))
    def reset_chat_view(self,session_id='',day=''):
        self.discard_live()
        self.chat_selected=session_id;self.chat_day=day;self.chat_before=0;self.chat_upper=None;self.chat_cursors=[];self.chat_page={}
        self.chat_generation+=1;self.chat_session={};self.chat_read_only=True;self.chat_html=None;self.review_targets={};self.chat.clear();self.chat_controls()
        self.chat_state=None;self.chat_previews.clear()

    def render_current_chat(self):
        if self.chat_state is None:return
        entity=self.current_entity()
        messages=merge_previews(self.chat_state.get('conversation',[]),self.chat_previews.values(),
                    entity=entity,session=self.chat_session,scope=self.chat_scope,
                    read_only=self.chat_read_only,query=self.chat_query,before=self.chat_before)
        rendered,self.review_targets=chat_bubbles(messages,entity,
                    self.chat_state.get('human_display_names',{}).get(entity,'Usuário'))
        if rendered!=self.chat_html:
            self.chat_html=rendered;update_chat_document(self.chat,rendered)

    def poll_chat_streams(self):
        if (self.closing or self.shutdown_pending or self.chat_stream_pending is not None or
                self.nav.currentRow()!=PAGES.index('Conversa') or self.chat_read_only or
                not self.chat_session.get('id') or self.chat_query or self.chat_before):return
        view=(self.chat_generation,self.current_entity(),self.chat_scope,self.chat_session['id'])
        pending=object();self.chat_stream_pending=pending
        def release():
            if self.chat_stream_pending is pending:self.chat_stream_pending=None
        def received(out):
            release()
            current=(self.chat_generation,self.current_entity(),self.chat_scope,self.chat_session.get('id'))
            if (self.closing or self.shutdown_pending or view!=current or self.chat_read_only or
                    self.chat_query or self.chat_before):return
            if out is None:
                self.chat_previews={key:dict(row,stale=True) for key,row in self.chat_previews.items()}
            elif isinstance(out,dict) and isinstance(out.get('streams'),list):
                incoming={}
                for row in out['streams'][:8]:
                    if not isinstance(row,dict) or not isinstance(row.get('id'),str) or type(row.get('revision')) is not int:continue
                    old=self.chat_previews.get(row['id'])
                    incoming[row['id']]=old if old and old['revision']>row['revision'] else row
                # A consulta é um snapshot autoritativo: ausências removem
                # prévias invalidadas. A ordem de quem já estava não oscila.
                kept={key:incoming.pop(key) for key in self.chat_previews if key in incoming}
                kept.update(incoming);self.chat_previews=kept
            self.render_current_chat()
        worker=self.request(self.query('chat/streams',entity=view[1],chat_scope=view[2],
                    conversation_session_id=view[3]),callback=received,quiet=True)
        if worker is None:release()
        elif hasattr(worker,'finished'):worker.finished.connect(release)

    def fetch_attachment(self,ident):
        # Pequena (JPEG até 1024 px) e só uma vez por imagem: busca direta no backend, local ou do PC1.
        try:
            req=Request(self.base+'/api/control/anexo?id='+ident,headers={'Authorization':'Bearer '+self.token})
            with urlopen(req,timeout=4) as response:return response.read(6*1024**2)
        except Exception:return None
    def review_interaction(self,url):
        from urllib.parse import parse_qs
        if url.scheme() in ('http','https'):
            QDesktopServices.openUrl(url);return  # link de fonte: abre no navegador deste PC
        parsed=urlsplit(url.toString());entity=parsed.hostname
        if parsed.scheme!='feedback' or entity not in ENTITIES:return
        identifier=parse_qs(parsed.query).get('message_id',[''])[0];message=self.review_targets.get(identifier)
        if not message or message.get('sender')!=entity:return
        dialog=InteractionReview(message,self)
        if dialog.exec_()!=QDialog.Accepted:return
        target=message['feedback_target']
        data=dict(entity=entity,message_id=identifier,decision=dialog.decision.currentData(),
                  note=dialog.note.toPlainText().strip(),**target)
        def saved(out):
            if not out or out.get('verified') is not True:return
            self.notice.setText('Avaliação salva. Não iniciou treinamento nem alterou memórias.');self.refresh()
        self.request('control/chat/feedback',data,callback=saved)
    def chat_today(self):
        self.reset_chat_view();self.refresh()
    def chat_select_day(self,index):
        session_id=self.chat_days.itemData(index)
        if not session_id:return
        current_id=self.chat_days.property('current_session_id')
        self.stop_capture(False);self.stop_voice();self.reset_chat_view('' if session_id==current_id else session_id);self.refresh()
    def chat_find_day(self):
        day=self.chat_date.text().strip()
        if not day:return
        self.stop_capture(False);self.stop_voice();self.reset_chat_view(day=day);self.refresh()
    def chat_find_topic(self):
        self.chat_query=self.chat_search.text().strip();self.reset_chat_view(self.chat_selected,self.chat_day);self.refresh()
    def chat_paginate(self,older):
        if older and self.chat_page.get('has_more'):
            self.chat_cursors.append(self.chat_before);self.chat_before=self.chat_page['next_before'];self.chat_upper=self.chat_page['upper']
        elif not older and self.chat_cursors:
            self.chat_before=self.chat_cursors.pop()
            if not self.chat_before:self.chat_upper=None
        else:return
        self.chat_generation+=1;self.refresh()
    def chat_view_loaded(self,out):
        session=out.get('chat_session') or {};previous=self.chat_session.get('id');self.chat_session=session
        self.chat_read_only=out.get('chat_read_only',True) or not session.get('id')
        self.chat_page=out.get('page') or {}
        if previous and previous!=session.get('id') and not self.chat_selected and not self.chat_day:
            # Meia-noite muda somente a vista; turno/voz já em andamento continua.
            self.chat_before=0;self.chat_upper=None;self.chat_cursors=[]
            self.chat_previews.clear();self.chat_generation+=1
        self.chat_days.blockSignals(True);self.chat_days.clear()
        current=(out.get('current_chat_session') or {}).get('id');self.chat_days.setProperty('current_session_id',current)
        for item in out.get('chat_sessions',[]):
            self.chat_days.addItem(item['local_date']+(' · hoje' if item['id']==current else ' · arquivada'),item['id'])
        self.chat_days.setCurrentIndex(self.chat_days.findData(session.get('id')));self.chat_days.blockSignals(False)
        summary=out.get('day_summary') or {}
        self.chat_hint.setText((session.get('local_date','Sessão indisponível')+' · '+session.get('timezone','')+' · '+
                               ('Somente leitura. Use Hoje para enviar.' if self.chat_read_only else 'Sessão atual. Memória e tarefas preservadas.'))+
                              '\n'+str(summary.get('message_count',0))+' registros · '+str(summary.get('pending_count',0))+' entradas pendentes · '+
                              str(summary.get('failures_count',0))+' falhas/incertos. Resumo narrativo indisponível.')
        self.chat_controls()
    def build_audio(self):
        outer=self.pages['Áudio'];self.audio_status=QLabel('Abra por botão ou atalho. Fala → transcrição → envio automático quando habilitado. Testes nunca enviam.');self.audio_status.setWordWrap(True);outer.addWidget(self.audio_status)
        volume_row=QHBoxLayout();volume_row.addWidget(QLabel('Volume da Central'))
        self.volume=QSlider(Qt.Horizontal);self.volume.setRange(0,100);self.volume.setValue(100);self.volume.setAccessibleName('Volume de reprodução da Central')
        self.volume_label=QLabel('100%');self.volume_label.setMinimumWidth(85)
        volume_row.addWidget(self.volume,1);volume_row.addWidget(self.volume_label);volume_row.addWidget(self.button('Salvar volume',self.save_volume));outer.addLayout(volume_row)
        self.volume.valueChanged.connect(self.volume_changed)
        self.audio_tabs=QTabWidget();outer.addWidget(self.audio_tabs,1);input_page=QWidget();voice_page=QWidget();self.audio_tabs.addTab(input_page,'Microfone / ASR');self.audio_tabs.addTab(voice_page,'Voz / TTS')
        self.listening_panel=ListeningPanel(self);self.audio_tabs.addTab(self.listening_panel,'Fontes e atenção')
        layout=QVBoxLayout(input_page);form=QFormLayout();layout.addLayout(form)
        self.mic_mode=QComboBox();self.mic_mode.addItems(['Comando · botão ou atalho','Detecção · escuta contínua'])
        self.source=QComboBox();self.source.addItem('Entrada padrão','');self.output=QComboBox();self.output.addItem('Saída padrão','')
        self.threshold=QDoubleSpinBox();self.threshold.setDecimals(3);self.threshold.setRange(.002,.2);self.threshold.setSingleStep(.002)
        self.silence=QSpinBox();self.silence.setRange(300,3000);self.silence.setSuffix(' ms')
        self.segment=QSpinBox();self.segment.setRange(3,45);self.segment.setSuffix(' s')
        self.auto_send=QCheckBox('Enviar fala automaticamente após transcrever · testes não enviam')
        self.hotkey_enabled=QCheckBox('Habilitar atalho global · segure para falar')
        self.hotkey_edit=QKeySequenceEdit(QKeySequence('Ctrl+Alt+Space'));self.hotkey_edit.setAccessibleName('Tecla global do microfone')
        self.hotkey_edit.editingFinished.connect(lambda:self.hotkey_enabled.setChecked(True) if not self.hotkey_edit.keySequence().isEmpty() else None)
        self.hotkey_status=QLabel('Atalho global desativado. Requer esta janela aberta; não precisa estar em foco.');self.hotkey_status.setWordWrap(True)
        for title,widget in [('Modo de microfone',self.mic_mode),('Entrada',self.source),('Saída',self.output),('Limiar de detecção por energia',self.threshold),('Silêncio para concluir',self.silence),('Envio',self.auto_send)]:form.addRow(title,widget)
        controls=QHBoxLayout();controls.addWidget(self.chat_record);controls.addWidget(self.ptt);layout.addLayout(controls)
        layout.addWidget(self.level)
        form.addRow('Atalho global',self.hotkey_enabled);form.addRow('Combinação',self.hotkey_edit);layout.addWidget(self.hotkey_status)
        layout.addWidget(self.button('Testar atalho · sem gravar',self.test_hotkey))
        self.bar(layout,[('Atualizar dispositivos',self.devices),('Salvar microfone',self.save_mic),('Testar mic · 5 segundos',self.test_mic),('Ouvir gravação',self.play_test_mic),('Testar ASR da gravação',self.test_asr)])
        self.audio_level=QProgressBar();self.audio_level.setRange(0,100);self.audio_level.setFormat('Nível do microfone: %p%');layout.addWidget(self.audio_level)
        self.acoustic_status=QLabel('Detector local: inativo. Em Detecção, classifica sons prováveis sem identificar pessoas.');self.acoustic_status.setWordWrap(True);layout.addWidget(self.acoustic_status)
        self.audio_transcript=QPlainTextEdit();self.audio_transcript.setReadOnly(True);self.audio_transcript.setPlaceholderText('Transcrição do teste de ASR aparecerá aqui — não envia conversa.');self.audio_transcript.setMaximumHeight(80);layout.addWidget(self.audio_transcript)
        layout.addStretch();layout=QVBoxLayout(voice_page);voice=QFormLayout();layout.addLayout(voice);self.provider=QComboBox();self.provider.addItems(['elevenlabs','azure','qwen3_tts','kokoro'])
        self.provider_enabled=QCheckBox('Habilitar provider externo');self.tts_model=QComboBox();self.tts_model.addItems(['eleven_multilingual_v2','eleven_flash_v2_5','eleven_turbo_v2_5'])
        self.voice_ids={e:QLineEdit() for e in ENTITIES[:2]};voice.addRow('Provider preferencial',self.provider);voice.addRow('',self.provider_enabled)
        for e,w in self.voice_ids.items():voice.addRow(e.capitalize()+' · Voice ID',w)
        voice.addRow('Modelo TTS ElevenLabs',self.tts_model)
        self.test_text=QPlainTextEdit(TEST_STORY);self.test_text.setMaximumHeight(100);voice.addRow('Frase de teste (até 2400 caracteres)',self.test_text)
        self.bar(layout,[('Salvar provider / vozes',self.save_voice),('Testar Hoshino',lambda:self.test_voice('hoshino')),('Testar Lilith',lambda:self.test_voice('lilith')),('Parar áudio',self.stop_voice)])
        layout.addWidget(QLabel('Salve a habilitação e os Voice IDs antes de testar. O modelo do teste pode ser escolhido acima.'))
        layout.addWidget(QLabel('Teste isolado: funciona com a entidade dormindo. Provider real/fallback aparece no rodapé.'));layout.addStretch()
        self.provider.currentTextChanged.connect(self.provider_changed)
    def build_memory(self):
        tabs=QTabWidget();self.pages['Memória do chat'].addWidget(tabs);page=QWidget();layout=QVBoxLayout(page);tabs.addTab(page,'Inspetor')
        self.logic_workshop=LogicWorkshop(self)
        row=QHBoxLayout();self.memory_query=QLineEdit();self.memory_query.setPlaceholderText('Busca / autor / assunto…');row.addWidget(self.memory_query);row.addWidget(self.button('Buscar',self.load_memory));layout.addLayout(row)
        self.memory_list=QTreeWidget();self.memory_list.setHeaderLabels(['Tipo / ID','Conteúdo','Origem / confiança']);self.memory_list.setSelectionMode(QTreeWidget.ExtendedSelection);layout.addWidget(self.memory_list,1)
        self.memory_detail=QPlainTextEdit();self.memory_detail.setReadOnly(True);self.memory_detail.setMaximumHeight(170);layout.addWidget(self.memory_detail)
        self.memory_list.itemSelectionChanged.connect(lambda:self.memory_detail.setPlainText(self.pretty([i.data(0,Qt.UserRole) for i in self.memory_list.selectedItems()])))
        self.memory_delete_busy=False;self.memory_status=QLabel('Apagar todas limpa memórias, conhecimento e chat da entidade escolhida. Exige senha, prévia e backup.');self.memory_status.setWordWrap(True);layout.addWidget(self.memory_status)
        self.bar(layout,[('Definir / alterar senha',self.set_password),('Apagar selecionadas',lambda:self.erase_memory(False)),('Apagar todas · memória, conhecimento e chat',lambda:self.erase_memory(True))])
        hint=QLabel('Limpeza completa exige as três entidades dormindo; só apaga os dados da entidade escolhida. Preserva personalidade, gostos/preferências, estado emocional salvo, modelos, configurações e comprovantes. Não é um reset aos padrões.');hint.setWordWrap(True);layout.addWidget(hint)
    def build_tools(self):
        layout=self.pages['Ferramentas'];self.tools=QTreeWidget();self.tools.setHeaderLabels(['Permitir capacidade','O que controla']);self.tools.setRootIsDecorated(False);layout.addWidget(self.tools,1)
        self.bar(layout,[('Atualizar',self.reload_tools),('Salvar permissões',self.save_tools)])
        self.tools_note=QLabel('Memórias e personalidade não são ferramentas. Ouvir o ambiente não inclui a voz de saída nem falar por comando.');self.tools_note.setWordWrap(True);layout.addWidget(self.tools_note)
    def build_models(self):
        layout=self.pages['Modelos']
        # 07/11 (pedido humano): APIs de modelo — adicionar, alterar, remover e quem usa qual.
        self.api_state=None
        self.api_box=QGroupBox('APIs de modelo (opcional)');api_layout=QVBoxLayout(self.api_box)
        self.api_warning=QLabel('Cada entidade usa o modelo local (Ollama) ou uma API cadastrada aqui. Com API, as conversas e '
                                'memórias daquela entidade saem deste PC; se a API falhar ou a cota acabar, ela volta sozinha '
                                'para o modelo local. A chave nunca é mostrada de volta.');self.api_warning.setWordWrap(True)
        api_layout.addWidget(self.api_warning)
        self.api_list=QListWidget();self.api_list.setMinimumHeight(96);api_layout.addWidget(self.api_list)
        self.bar(api_layout,[('Adicionar API',lambda:self.api_dialog(None)),('Alterar',self.api_edit_selected),
                             ('Remover',self.api_remove_selected),('Apagar chave',self.api_forget_key_selected)])
        api_form=QFormLayout();api_layout.addLayout(api_form);self.api_choice={}
        for e in ENTITIES:
            box=QComboBox();box.setAccessibleName('Modelo usado por '+e.capitalize())
            box.activated.connect(lambda _,who=e:self.api_assign(who));self.api_choice[e]=box
            api_form.addRow(e.capitalize()+' usa',box)
        layout.addWidget(self.api_box)
        self.execution_config=None;self.execution_certificate=''
        self.execution_box=QGroupBox('Onde executar Alistair');execution_layout=QVBoxLayout(self.execution_box);execution_form=QFormLayout();execution_layout.addLayout(execution_form)
        self.execution_destination=QComboBox()
        for key,label in [('local','Este PC'),('pc2','PC2 · CPU (preservado)'),('xbox','Xbox Series S · GPU')]:self.execution_destination.addItem(label,key)
        self.execution_ip=QLineEdit();self.execution_start=QCheckBox('Abrir o executor Xbox automaticamente ao acordar Alistair')
        self.execution_sync=QCheckBox('Conferir/sincronizar arquivos técnicos antes de usar')
        self.execution_lan=QCheckBox('Confirmo uma LAN de confiança (inferência HTTP; não expor à internet)')
        self.execution_user=QLineEdit();self.execution_password=QLineEdit();self.execution_password.setEchoMode(QLineEdit.Password)
        self.execution_password.setPlaceholderText('Deixe vazio para manter o acesso salvo')
        for label,widget in [('Destino',self.execution_destination),('IP do Xbox',self.execution_ip),('',self.execution_start),('',self.execution_sync),('',self.execution_lan),('Usuário do acesso remoto Xbox',self.execution_user),('Senha do acesso remoto Xbox',self.execution_password)]:execution_form.addRow(label,widget)
        self.execution_status=QLabel('Banco, identidade e ferramentas permanecem noPC. Não liga o console nem troca DevMode.');self.execution_status.setWordWrap(True);execution_layout.addWidget(self.execution_status)
        self.bar(execution_layout,[('Atualizar destino',lambda:self.load_execution(True)),('Importar certificado público Xbox',self.import_execution_certificate),('Salvar destino (Alistair dormindo)',self.save_execution),('Conferir/sincronizar agora',lambda:self.check_execution('prepare')),('Reconciliar pendência (sem repetir)',lambda:self.check_execution('reconcile'))])
        layout.addWidget(self.execution_box);self.execution_box.hide()
        form=QFormLayout();layout.addLayout(form);self.models=QComboBox();self.context=QSnapSpinBox();self.context.setRange(2048,16384)
        self.models.setEnabled(False)
        # 06/11 (pedido humano): o número digitado vira o valor válido mais próximo (faixa e passo) ao terminar.
        self.context.setSingleStep(1024);self.context.setToolTip('Digite qualquer número (ou 24k): ao sair do campo vira o valor válido mais próximo.')
        self.out_tokens=QSnapSpinBox();self.out_tokens.setRange(128,8192);self.out_tokens.setSingleStep(128)
        self.out_tokens.setToolTip('Digite qualquer número: ao sair do campo vira o valor válido mais próximo (passos de 128, até o contexto menos 512).')
        self.context.adjusted.connect(lambda typed,used:self.notice.setText(f'Contexto: {typed} não é válido aqui; ajustado para {used}, o valor mais próximo.'))
        self.out_tokens.adjusted.connect(lambda typed,used:self.notice.setText(f'Limite de saída: {typed} não é válido aqui; ajustado para {used}, o valor mais próximo.'))
        form.addRow('Executor selecionado',self.models);form.addRow('Contexto',self.context);form.addRow('Limite de saída',self.out_tokens)
        # 06/11 (pedido humano): quantas camadas do 9B ficam na GPU e quantas na CPU.
        self.gpu_layers=QComboBox();self.gpu_layers.setToolTip(
            'Mais camadas na GPU: resposta mais rápida e mais VRAM. As demais rodam na CPU.\n'
            'Só aparecem degraus medidos na placa; Automático escolhe pela VRAM livre.')
        form.addRow('Camadas na GPU',self.gpu_layers)
        self.context.valueChanged.connect(self.update_model_output_limit)
        self.model_hint=QLabel('');self.model_hint.setWordWrap(True);layout.addWidget(self.model_hint)
        self.version_family=QComboBox();self.version_source=QComboBox();self.version_data=None
        form.addRow('Família do modelo',self.version_family);form.addRow('Versão dos pesos',self.version_source)
        self.version_status=QLabel('Carregando versões locais…');self.version_status.setWordWrap(True);layout.addWidget(self.version_status)
        self.bar(layout,[('Atualizar versões',lambda:self.load_model_versions(self.current_entity())),
                         ('Preparar para uso',lambda:self.use_model_version(True)),
                         ('Usar esta versão',lambda:self.use_model_version(False))])
        layout.addWidget(QLabel('Troca somente dormindo. Preparar converte e verifica; não treina, não acorda e não apaga memórias.'))
        self.version_family.currentIndexChanged.connect(self.version_family_changed)
        self.version_source.currentIndexChanged.connect(self.version_source_changed)
        self.bar(layout,[('Aplicar com entidade dormindo',self.save_model),('Importar GGUF existente',self.import_model),('Exportar arquivo selecionado',self.export_model)])
        self.model_detail=QPlainTextEdit();self.model_detail.setReadOnly(True);layout.addWidget(self.model_detail,1)
        self.files=QTreeWidget();self.files.setHeaderLabels(['Arquivo instalado','Tamanho']);layout.addWidget(self.files,1)
    def build_laboratory(self):
        """Somente interface. O laboratório mantém seu próprio processo e autenticação."""
        layout=self.pages['Laboratório Neural']
        note=QLabel('Treinamento separado de Hoshino, Lilith e Alistair.\n'
                    'Professor MoE prepara e revisa propostas sem alterar a Central.\n'
                    'Nenhum modelo é iniciado apenas ao selecionar esta página.')
        note.setWordWrap(True);layout.addWidget(note)
        layout.addWidget(self.button('Abrir Laboratório Neural (localhost:8788)',self.open_laboratory))
        layout.addWidget(QLabel('O navegador abre o painel independente. Fechar o painel não encerra entidades.'))

    def open_laboratory(self):
        """Inicia somente o servidor de UI local, quando necessário, após clique."""
        import webbrowser
        url='http://127.0.0.1:8788'
        try:
            with urlopen(url+'/api/status',timeout=0.6) as response:
                if response.status!=200:raise RuntimeError('Painel respondeu com erro')
        except (OSError, RuntimeError):
            entry=self.root/'laboratorio/labctl.py'
            if not entry.is_file():
                QMessageBox.warning(self,'Laboratório ausente','Instale o pacote Neural no projeto local.')
                return
            started=QProcess.startDetached(os.sys.executable,[str(entry),'serve','--port','8788'],str(self.root))
            if not started[0]:
                QMessageBox.warning(self,'Laboratório','Servidor do painel não pôde ser iniciado.')
                return
        webbrowser.open(url)

    def build_settings(self):
        layout=self.pages['Configurações'];self.overlay_enabled=QCheckBox('Overlay/orbes habilitado');self.topmost=QCheckBox('Orbes sempre no topo');self.balloons=QCheckBox('Balões visuais');self.silent=QCheckBox('Modo silencioso visual')
        for w in (self.overlay_enabled,self.topmost,self.balloons,self.silent):layout.addWidget(w)
        self.reduced_motion=QCheckBox('Movimento reduzido · desativar animações');layout.addWidget(self.reduced_motion)
        self.reduced_motion.toggled.connect(self.stop_page_animation)
        self.clipboard_import = QCheckBox('Permitir importar texto e prints copiados na conversa direta')
        layout.addWidget(self.clipboard_import)
        # 06/11 (pedido humano): o que eu copio fica guardado sozinho para elas verem quando eu pedir.
        self.clipboard_auto = QCheckBox('Guardar sozinho tudo o que eu copiar (texto e imagem) na área compartilhada, para elas verem quando eu pedir')
        self.clipboard_auto.setToolTip('Pasta compartilhado/area_de_transferencia · últimas 300 cópias · senha marcada como segredo pelo gerenciador não é guardada.')
        layout.addWidget(self.clipboard_auto)
        timeline_form = QFormLayout()
        self.timeline_page_size = QComboBox()
        for size in (25, 50, 100):
            self.timeline_page_size.addItem(str(size), size)
        timeline_form.addRow('Registros por página da linha do tempo', self.timeline_page_size)
        layout.addLayout(timeline_form)
        self.balloon_seconds=QSpinBox();self.balloon_seconds.setRange(2,20);self.balloon_seconds.setSuffix(' s · duração dos balões');layout.addWidget(self.balloon_seconds)
        self.orb_controls={}
        self.orb_tabs=QTabWidget();layout.addWidget(self.orb_tabs)
        for entity in ENTITIES:
            group=QGroupBox(entity.capitalize()+' · aparência do orb');form=QFormLayout(group)
            mode=QComboBox();mode.addItems(['Bola de energia','Imagem dentro do orb'])
            color=QLineEdit(COLORS[entity]);color.setMaxLength(7)
            color_row=QHBoxLayout();color_row.addWidget(color);color_row.addWidget(self.button('Escolher cor',lambda _,e=entity:self.pick_orb_color(e)))
            picture=QLineEdit();picture.setReadOnly(True);picture.setPlaceholderText('Imagem local opcional · até 10 MiB / 4096 px')
            image_row=QHBoxLayout();image_row.addWidget(picture);image_row.addWidget(self.button('Escolher imagem',lambda _,e=entity:self.pick_orb_image(e)));image_row.addWidget(self.button('Limpar',lambda _,w=picture:w.clear()))
            mood=QCheckBox('Variar cor com o humor observado');mood.setChecked(True)
            form.addRow('Estilo',mode);form.addRow('Cor base',color_row);form.addRow('Imagem',image_row);form.addRow('',mood)
            self.orb_tabs.addTab(group,entity.capitalize());self.orb_controls[entity]=(mode,color,picture,mood)
        hint=QLabel('O contorno mantém a cor de identificação de cada entidade. Humor só muda o visual quando informado pelo backend; Alistair não tem esse perfil afetivo.');hint.setWordWrap(True);layout.addWidget(hint)
        self.bar(layout,[('Salvar preferências',self.save_interface),('Abrir orbes',lambda:self.request('control/overlay/start',{}))])
        # 06/11 (pedido humano): painel no PC2; o cérebro continua aqui. Só aparece na Central do PC1.
        self.lan_box=QGroupBox('Painel no PC2 pela rede local');lan_layout=QVBoxLayout(self.lan_box);self.lan_state=None
        self.lan_enabled=QCheckBox('Permitir que o painel do PC2 se conecte a esta Central (só rede local, com código)')
        self.lan_info=QLabel('');self.lan_info.setWordWrap(True);self.lan_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lan_layout.addWidget(self.lan_enabled);lan_layout.addWidget(self.lan_info)
        self.bar(lan_layout,[('Salvar acesso pela rede',lambda:self.save_lan(False)),('Gerar novo código',lambda:self.save_lan(True)),
                             ('Copiar comando do PC2',self.copy_lan_command)])
        layout.addWidget(self.lan_box);self.lan_box.hide()
        # 06/11 (pedido humano): margem de VRAM — quanto da placa sobra livre; o resto os modelos podem usar.
        self.vram_box=QGroupBox('VRAM da placa de vídeo');vram_layout=QVBoxLayout(self.vram_box);self.vram_state=None
        vram_form=QFormLayout();self.vram_margin=QComboBox();vram_form.addRow('Margem de segurança (fica livre)',self.vram_margin);vram_layout.addLayout(vram_form)
        self.vram_info=QLabel('');self.vram_info.setWordWrap(True);vram_layout.addWidget(self.vram_info)
        self.vram_margin.currentIndexChanged.connect(self.vram_preview)
        self.bar(vram_layout,[('Salvar margem de VRAM',self.save_vram),('Atualizar uso agora',lambda:self.request('control/vram',callback=self.render_vram,quiet=True))])
        layout.addWidget(self.vram_box);self.vram_box.hide()
        self.pc2_box=QGroupBox('Este PC é o PC2 (painel pela rede)');pc2_layout=QVBoxLayout(self.pc2_box)
        self.pc2_allow=QCheckBox('Permitir que as entidades abram e executem coisas neste PC (comandos, sites, apps)')
        self.pc2_allow.setToolTip('Rodam com o seu usuário deste PC. Comandos irreversíveis são recusados; os arriscados pedem que você rode.')
        self.pc2_allow.setChecked(self.pc2_local().get('comandos') is True);self.pc2_allow.toggled.connect(lambda on:self.pc2_save_local('comandos',on))
        self.pc2_screen=QCheckBox('Permitir que as entidades vejam a tela deste PC (quando pedirem)')
        self.pc2_screen.setChecked(self.pc2_local().get('tela') is True);self.pc2_screen.toggled.connect(lambda on:self.pc2_save_local('tela',on))
        self.pc2_status=QLabel('Sentidos deste PC: aguardando o primeiro envio.');self.pc2_status.setWordWrap(True)
        pc2_layout.addWidget(self.pc2_allow);pc2_layout.addWidget(self.pc2_screen);pc2_layout.addWidget(self.pc2_status)
        # 11/11 (pedido humano): ponte de áudio pela própria Central, no lugar do SonoBus. Ligada por padrão.
        self.pc2_hear=QCheckBox('Tocar aqui o som do PC1 (tudo o que toca lá)')
        self.pc2_hear.setChecked(self.pc2_local().get('ouvir_pc1',True) is not False);self.pc2_hear.toggled.connect(lambda on:self.pc2_save_local('ouvir_pc1',on))
        self.pc2_talk=QCheckBox('Mandar o microfone deste PC para o PC1 (as entidades ouvem por ele)')
        self.pc2_talk.setChecked(self.pc2_local().get('mic_para_pc1',True) is not False);self.pc2_talk.toggled.connect(lambda on:self.pc2_save_local('mic_para_pc1',on))
        self.pc2_bridge_status=QLabel('Ponte de áudio: iniciando.');self.pc2_bridge_status.setWordWrap(True)
        pc2_layout.addWidget(self.pc2_hear);pc2_layout.addWidget(self.pc2_talk);pc2_layout.addWidget(self.pc2_bridge_status)
        layout.addWidget(self.pc2_box);self.pc2_box.setVisible(self.remote_panel());layout.addStretch()
    def pick_orb_color(self,entity):
        from PyQt5.QtGui import QColor
        field=self.orb_controls[entity][1];color=QColorDialog.getColor(QColor(field.text()),self,'Cor base · '+entity.capitalize())
        if color.isValid():field.setText(color.name())
    def pick_orb_image(self,entity):
        from native_style import load_orb_image
        path,_=QFileDialog.getOpenFileName(self,'Imagem · '+entity.capitalize(),'','Imagens (*.png *.jpg *.jpeg *.webp)')
        if not path:return
        if load_orb_image(path).isNull():self.notice.setText('Imagem inválida ou grande demais. Use PNG/JPEG/WebP de até 10 MiB e 4096 px por lado.');return
        self.orb_controls[entity][2].setText(str(Path(path).resolve()))
    def refresh(self):
        if self.polling or self.closing:return
        self.polling=True
        selected=self.current_entity()
        generation=self.chat_generation
        def received(out):
            self.polling=False
            if out is None:return
            if out.get('closing') is True and not self.shutdown_pending:
                # 07/11: vale no PC1 e no PC2: encerrada pelo outro lado, a janela fecha junto.
                self.close_with_central('A Central está encerrando; esta janela fecha junto.');return
            jobs=out.get('jobs',[]);leases=out.get('resources',[])
            for e,label in self.cards.items():
                p=next((p for p in out.get('presence',[]) if p.get('entity_id')==e),{})
                own=[j for j in jobs if j.get('entity')==e and j.get('status') in ('queued','running')]
                lease=next((l for l in leases if l.get('entity')==e and l.get('model_key')),{})
                details=own[0].get('details',{}) if own else {}
                observed=self.entity_details.get(e,{})
                expression=observed.get('expression_profile',{})
                emotional=(expression.get('dominant') or 'sem emoção dominante') if expression.get('available') else 'indisponível'
                current=observed.get('activity_context',{}).get('current',{})
                activity=(current.get('activity','desconhecida')+' · '+current.get('mode','')+'\nObjetivo: '+(current.get('goal') or 'conversa / sem meta operacional')) if current.get('fresh') else 'sem observação atual'
                label.setText('Estado: '+p.get('status','offline')+'\nExecutor: '+str(details.get('model') or lease.get('model_key','desconhecido')).split('|')[-1]+'\nRecurso: '+lease.get('resource','sem lease')+'\nFila de jobs: '+str(sum(j['status']=='queued' for j in own))+('' if e=='alistair' else '\nEmoção: '+emotional)+'\nAtividade: '+activity+'\n'+p.get('detail',''))
                if p.get('status') in ('offline','sleeping','stopping') and self.voice_entity==e and not self.voice_test:self.stop_voice()
            if self.voice_job:
                active=next((j for j in jobs if j['id']==self.voice_job),{})
                if active.get('details',{}).get('playback_cancel_at') or active.get('status') in ('error','interrupted'):self.stop_voice()
            if selected!=self.current_entity() or generation!=self.chat_generation:return
            self.chat_view_loaded(out)
            conversation=out.get('conversation',[]);self.chat_state=out;self.render_current_chat()
            e=self.current_entity();working=[j for j in jobs if j.get('entity')==e and j.get('status') in ('running','queued')]
            stable=next((j['details'].get('sentences',[]) for j in working if j.get('kind')=='llm_speech' and j.get('details',{}).get('stable_only')),[])
            self.operation.setText(' · '.join(str(j.get('details',{}).get('phase',j.get('kind'))) for j in working)+('\nFrases estáveis: '+' '.join(stable) if stable else ''))
            replies=[m for m in conversation if m.get('recipient')=='usuario' and (m.get('sender') in ('hoshino','lilith') if self.chat_scope=='global' else m.get('sender')==e)]
            voice_view=(self.chat_scope,e,self.chat_session.get('id'),self.chat_query,self.chat_before)
            if voice_view not in self.voice_initialized:
                self.voice_seen.update(m['id'] for m in replies)
                self.stream_seen.update(s for m in replies for s in (m.get('metadata') or {}).get('speech_streams',[]))
                self.voice_initialized.add(voice_view)
            streams=public_speech_streams(jobs,e,self.chat_session,self.chat_scope,self.stream_seen,time.time())
            self.handle_new_voice(e,replies,streams)
            if not self.connected:self.notice.setText('Backend conectado · controles prontos. Microfone fechado por padrão.');self.connected=True
        params=dict(entity=selected,daily=1,chat_scope=self.chat_scope,conversation_session_id=self.chat_selected,day=self.chat_day,q=self.chat_query,before=self.chat_before)
        if self.chat_upper is not None:params['upper']=self.chat_upper
        if not self.request(self.query('state',**params),callback=received,quiet=True):self.polling=False
    def loaded_entity_details(self,out):
        if not isinstance(out,dict):return
        self.entity_details=out
        self.entities_detail.setPlainText(self.pretty(out))
    def refresh_active(self,timed=False):
        if self.closing or not self.isVisible():return
        page=self.nav.currentItem().text() if self.nav.currentItem() else 'Entidades';e=self.current_entity()
        if timed and page in ('Memória do chat','Memórias','Ferramentas','Modelos','Configurações'):return
        if page=='Entidades':self.request('control/entities',callback=self.loaded_entity_details,quiet=True)
        elif page=='Áudio':self.load_audio()
        elif page=='Memória do chat':self.load_memory()
        elif page=='Memórias':self.load_knowledge()
        elif page=='Ferramentas':self.load_tools()
        elif page=='Modelos':self.load_models()
        elif page=='Configurações':self.load_interface()
        elif page=='Recursos':self.request('control/resources',callback=self.resources_panel.render,quiet=True)
        elif page=='Atividade':
            self.history_timeline.set_entity(e)
            def events(out):
                if e==self.current_entity():self.activity_panel.render(out)
            def commands(out):
                if e==self.current_entity():self.activity_panel.render_commands(out)
            self.request(self.query('control/activity',entity=e,rotina='1' if self.activity_panel.show_routine.isChecked() else None),callback=events,quiet=True)
            self.request(self.query('control/commands',entity=e),callback=commands,quiet=True)
        elif page=='Serviços':self.request('control/audio',callback=self.services_panel.render,quiet=True)
        elif page=='Diagnóstico':
            self.request(self.query('control/activity',entity=e,level='ERROR'),callback=lambda out:self.diagnostics_panel.render(out) if e==self.current_entity() else None,quiet=True)
    def send(self,entity=None,automatic=False):
        e=entity or self.current_entity();text=self.draft.toPlainText().strip() if e==self.current_entity() else self.drafts[e].strip()
        if self.chat_read_only or e!=self.current_entity() or not self.chat_session.get('id'):
            self.notice.setText('Conversa arquivada/indisponível. Abra Hoje antes de enviar.');return
        if not text:return
        session_id=self.chat_session['id'];scope=self.chat_scope;key=(scope,e,session_id,text);identifier=self.submissions.setdefault(key,uuid.uuid4().hex)
        data={'entity':e,'text':text,'wake':True,'submission_id':identifier,'conversation_session_id':session_id,'chat_scope':scope}
        # 07/11 (teste de uso no PC2): a transcrição antiga ficava presa ao rascunho mesmo com outro texto digitado;
        # a Central recusava ("Texto não corresponde à transcrição") e, sem envio, o vínculo nunca saía. Igual ao
        # painel web: só vincula a fala se o texto ainda conserva o trecho gravado; senão vai como texto digitado.
        origin=self.origins.get(e)
        if origin and not draft_keeps_transcript(origin.get('text'),text):
            self.origins.pop(e,None);origin=None
        if origin:data.update(audio_job_id=origin['id'],draft_origin=True,automatic_asr=automatic)
        if origin and origin.get('ids'):data['audio_job_ids']=origin['ids']
        def sent(out):
            if out is None:return
            self.submissions.pop(key,None)
            if e==self.current_entity():
                if self.chat_scope==scope and self.chat_session.get('id')==session_id and self.draft.toPlainText().strip()==text:self.draft.clear();self.drafts[e]=''
            elif self.chat_scope==scope and self.drafts[e].strip()==text:self.drafts[e]=''
            if self.chat_scope!=scope:
                drafts=self.scope_drafts.get(scope,{})
                if drafts.get(e,'').strip()==text:drafts[e]=''
            if self.chat_scope==scope and self.origins.get(e) is origin:self.origins.pop(e,None)
            self.notice.setText('Mensagem aceita pela caixa postal; aguarde resposta/desfecho.');self.refresh()
        self.request('send',data,callback=sent)
    def attach(self):
        if self.chat_read_only:self.notice.setText('Anexos de conversa disponíveis apenas na sessão atual.');return
        name,_=QFileDialog.getOpenFileName(self,'Anexar arquivo existente')
        if not name:return
        path=Path(name)
        if path.stat().st_size>8*1024**2:self.notice.setText('Anexo acima de 8 MiB.');return
        self.import_chat_attachment(path.name, path.read_bytes())

    def capture_clipboard(self):
        settings=((self.ui_config or {}).get('settings') or {})
        if self.closing or not self.connected or settings.get('clipboard_auto',True) is not True:return
        clipboard=QApplication.clipboard();mime=clipboard.mimeData()
        if mime is None or mime.hasFormat('x-kde-passwordManagerHint'):return  # gerenciador de senhas marcou como segredo
        if mime.hasImage():
            image=clipboard.image()
            if image.isNull() or image.width()*image.height()>16_000_000:return
            buffer=QBuffer();buffer.open(QIODevice.WriteOnly)
            if not image.save(buffer,'PNG'):return
            kind,payload,limit='imagem',bytes(buffer.data()),8*1024**2
        elif mime.hasText() and clipboard.text().strip():
            kind,payload,limit='texto',clipboard.text().encode('utf-8'),1024**2
        else:return
        digest=hashlib.sha256(payload).hexdigest()
        if not 0<len(payload)<=limit or digest==self.clipboard_last:return
        self.clipboard_last=digest
        self.request(self.query('control/clipboard',kind=kind),payload,callback=lambda out:None,binary=True,quiet=True,silent=True)
    def can_import_clipboard(self):
        settings = ((self.ui_config or {}).get('settings') or {})
        return (not self.chat_read_only and self.chat_scope == 'direct'
                and self.current_entity() in {'hoshino', 'lilith'} and settings.get('clipboard_import', True) is True)

    def import_clipboard(self):
        if not self.can_import_clipboard():
            return
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime and mime.hasImage():
            image = clipboard.image()
            if image.isNull() or image.width() * image.height() > 16_000_000:
                self.notice.setText('Print inválido ou acima de 16 milhões de pixels.')
                return
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            if not image.save(buffer, 'PNG'):
                self.notice.setText('O print copiado não pôde ser convertido.')
                return
            payload, name = bytes(buffer.data()), 'clipboard-print.png'
        elif mime and mime.hasText():
            payload, name = clipboard.text().encode('utf-8'), 'clipboard-texto.txt'
            if len(payload) > 128 * 1024:
                self.notice.setText('Texto copiado acima de 128 KiB.')
                return
        else:
            self.notice.setText('Copie um texto ou uma imagem primeiro.')
            return
        if not 0 < len(payload) <= 8 * 1024**2:
            self.notice.setText('Conteúdo vazio ou acima de 8 MiB.')
            return
        self.import_chat_attachment(name, payload)

    def import_chat_attachment(self, name, payload):
        e = self.current_entity()
        session_id=self.chat_session.get('id')
        scope = self.chat_scope
        def saved(o):
            if o:
                is_image = Path(name).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
                reference = 'Observe a imagem recebida ' if is_image else 'Leia o anexo '
                reference += o.get('name', o.get('path', '')) + '.'
                if scope==self.chat_scope and e==self.current_entity() and self.chat_session.get('id')==session_id and not self.chat_read_only:
                    self.draft.appendPlainText(reference)
                    self.notice.setText('Anexo importado. Revise o rascunho e clique em Enviar para pedir a leitura.')
                else:
                    drafts = self.drafts if scope == self.chat_scope else self.scope_drafts.setdefault(scope, {})
                    drafts[e]=(drafts.get(e,'')+'\n'+reference).strip()
                    self.notice.setText('Anexo importado para '+e.capitalize()+'; referência guardada no rascunho, não enviada ao arquivo histórico.')
        self.request(self.query('control/attachment',entity=e,name=name),payload,callback=saved,binary=True)

    def load_history_timeline(self, entity, offset, filters, callback):
        return self.request(self.query('control/timeline', entity=entity, offset=offset, **filters),
                            callback=callback, timeout=25)

    def preview_clipboard_attachment(self, entity, name):
        def loaded(payload):
            if payload is None or entity != self.current_entity():
                return
            dialog = QDialog(self)
            dialog.setWindowTitle('Conteúdo copiado · ' + entity.capitalize())
            layout = QVBoxLayout(dialog)
            if name.endswith('.png'):
                picture = QPixmap()
                if not picture.loadFromData(payload, 'PNG'):
                    self.notice.setText('Print indisponível ou PNG inválido.')
                    return
                view = QLabel()
                view.setPixmap(picture.scaled(920, 650, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                view = QPlainTextEdit(payload.decode('utf-8', 'replace'))
                view.setReadOnly(True)
            layout.addWidget(view)
            close = QDialogButtonBox(QDialogButtonBox.Close)
            close.rejected.connect(dialog.reject)
            layout.addWidget(close)
            dialog.resize(760, 490)
            dialog.exec_()
        self.request(self.query('control/clipboard-attachment', entity=entity, name=name),
                     callback=loaded, raw=True)
    def sleep(self,entity):
        self.interrupt(entity);self.request('sleep',{'entity':entity})
    def interrupt(self,entity):
        if self.voice_entity==entity:self.stop_voice()
        self.request('audio/interrupt',{'entity':entity})
    def shutdown(self):
        self.close()
    def loaded_microphone(self,out):
        if not out:return
        self.apply_ambient_policy(out)
        self.mic_settings=out['settings'];self.mic_revision=out['revision'];self.mic_mode.setCurrentIndex(('command','detection').index(self.mic_settings['mode']))
        self.threshold.setValue(self.mic_settings['threshold']);self.silence.setValue(self.mic_settings['silence_ms']);self.segment.setValue(self.mic_settings['segment_seconds']);self.auto_send.setChecked(self.mic_settings['auto_send'])
        self.volume.setValue(self.mic_settings.get('output_volume',100))
        self.hotkey_enabled.setChecked(self.mic_settings.get('hotkey_enabled',False))
        self.hotkey_edit.setKeySequence(QKeySequence(self.mic_settings.get('hotkey','Ctrl+Alt+Space')))
        for box,key in ((self.source,'source'),(self.output,'output')):
            value=self.mic_settings[key]
            if value and box.findData(value)<0:box.addItem('Configurado: '+value,value)
            box.setCurrentIndex(max(0,box.findData(value)))
        self.configure_hotkey()
    def apply_ambient_policy(self,out):
        if not out:return
        policy=out.get('ambient_allowed')
        if isinstance(policy,dict):self.ambient_allowed={e:policy.get(e) is True for e in ENTITIES}
        if self.capture and self.segmenter.mode=='detection' and not self.ambient_allowed.get(self.capture_entity,False):
            self.stop_capture(False);self.notice.setText('Escuta do ambiente desativada. O modo Comando e a voz continuam disponíveis.')
        self.asr_waiting=[q for q in self.asr_waiting if len(q)<6 or q[5]!='detection' or self.ambient_allowed.get(q[1],False)]
        self.chat_controls()
    def stop_hotkey(self):
        process=self.hotkey_process;self.hotkey_process=None;self.hotkey_signature=None
        if self.hotkey_capture is self.capture:self.stop_capture(False)
        self.hotkey_capture=None
        if process:
            process.write(b'quit\n');process.closeWriteChannel();self.owned_timeout(process,1500)
    def configure_hotkey(self):
        signature=(self.mic_settings.get('hotkey_enabled',False),self.mic_settings.get('hotkey','Ctrl+Alt+Space'))
        self.draft.reserve_microphone_hotkey(signature[1] if signature[0] else '')
        if self.hotkey_signature==signature:return
        self.stop_hotkey()
        if not signature[0]:self.hotkey_status.setText('DESLIGADO · marque Habilitar atalho e Salvar microfone. Escolher a tecla não abre captura.');return
        runtime=hotkey_runtime(self.root)
        if runtime is None:
            # 07/11: o painel do PC2 roda no Python do sistema, sem o ambiente do projeto; o atalho ficava mudo.
            self.hotkey_status.setText('Atalho indisponível: falta o pynput. Neste PC: sudo apt install python3-pynput '
                                       'e reabra a Central.');return
        process=QProcess(self);self.hotkey_process=process;self.hotkey_signature=signature;self.hotkey_buffer=b''
        process.setWorkingDirectory(str(self.root))
        def read():
            if self.hotkey_process is not process:return
            self.hotkey_buffer+=bytes(process.readAllStandardOutput())
            if len(self.hotkey_buffer)>8192:self.stop_hotkey();self.hotkey_status.setText('Atalho interrompido: resposta inválida.');return
            while b'\n' in self.hotkey_buffer:
                line,self.hotkey_buffer=self.hotkey_buffer.split(b'\n',1)
                try:event=json.loads(line).get('event')
                except (ValueError,AttributeError):continue
                self.global_hotkey_event(event)
        def finished(*_):
            if self.hotkey_process is process:
                self.hotkey_process=None;self.hotkey_signature=None
                if self.hotkey_capture is self.capture:self.stop_capture(False)
                self.hotkey_capture=None;self.hotkey_status.setText('Atalho global indisponível/encerrado. Em Wayland use X11 ou o botão local.')
            process.deleteLater()
        process.readyReadStandardOutput.connect(read);process.finished.connect(finished)
        process.errorOccurred.connect(lambda code:finished() if code==QProcess.FailedToStart else None)
        self.hotkey_status.setText('Ativando atalho global…')
        process.start(str(runtime),['-B',str(self.root/'app/tools/microfone_controle.py'),'--native-bridge',signature[1]])
    def global_hotkey_event(self,event):
        if event in ('press','release') and time.monotonic()<self.hotkey_test_until:
            self.hotkey_status.setText('Atalho reconhecido: '+self.mic_settings.get('hotkey','')+' · '+('pressionado' if event=='press' else 'solto')+' · teste sem gravação.');return
        if event=='ready':self.hotkey_status.setText('Atalho global ativo: '+self.mic_settings['hotkey']+' · destino: entidade selecionada na Central.')
        elif event=='unavailable':self.hotkey_status.setText('Atalho indisponível nesta sessão. Use X11 ou o botão local.')
        elif event=='press' and not self.closing:
            if self.hotkey_edit.hasFocus():return  # choosing a key is not permission to record
            if not self.window_active:
                self.notice.setText('Atalho ignorado: esta janela está em pausa; a outra janela da Central está em uso.');return
            if self.capture or self.asr_jobs or self.chat_read_only or self.mic_settings['mode']!='command':return
            self.ptt_start();self.hotkey_capture=self.capture
        elif event=='release' and self.hotkey_capture:
            if self.hotkey_capture is self.capture:self.stop_capture(True)
            self.hotkey_capture=None
    def test_hotkey(self):
        if not self.hotkey_process:
            self.hotkey_status.setText('Atalho DESLIGADO: escolha, habilite e Salvar microfone antes do teste.');return
        self.hotkey_test_until=time.monotonic()+10
        self.hotkey_status.setText('Pressione e solte a combinação nos próximos 10 segundos, mesmo em outra janela. Este teste não abre o microfone.')
    def devices(self):
        def inventory(out):
            if not out:return
            detector=out.get('acoustic',{})
            if not self.acoustic_capture_id:
                self.acoustic_status.setText('Detector local: '+('pronto · CPU; ative Detecção para escutar.' if detector.get('available') and detector.get('runtime_available') else 'indisponível; Comando/ASR continua independente.'))
            self.source.clear();self.source.addItem('Entrada padrão','')
            for d in out.get('sources',[]):
                if d.get('kind')=='microphone':self.source.addItem(d.get('label',d['id']),d['id'])
            self.source.setCurrentIndex(max(0,self.source.findData(self.mic_settings.get('source',''))))
        self.request('audio/state',callback=inventory)
        process=QProcess(self);self.device_process=process
        def done(code,_):
            if code==0:
                try:
                    rows=json.loads(bytes(process.readAllStandardOutput()));self.output.clear();self.output.addItem('Saída padrão','')
                    for d in rows:self.output.addItem(d.get('description') or d['name'],d['name'])
                    self.output.setCurrentIndex(max(0,self.output.findData(self.mic_settings.get('output',''))))
                except Exception:self.notice.setText('Inventário de saída indisponível.')
            else:self.notice.setText('Servidor de som não respondeu; nenhuma saída fictícia.')
            process.deleteLater()
        process.finished.connect(done);process.start('pactl',['--format=json','list','sinks']);self.owned_timeout(process,4000)
    def save_mic(self):
        if self.capture:self.notice.setText('Feche o microfone antes de alterar configuração.');return
        settings={'mode':('command','detection')[self.mic_mode.currentIndex()],'source':self.source.currentData() or '',
                  'output':self.output.currentData() or '', 'threshold':self.threshold.value(),'silence_ms':self.silence.value(),
                  'segment_seconds':self.segment.value(),'auto_send':self.auto_send.isChecked(),'output_volume':self.volume.value()}
        settings.update(hotkey_enabled=self.hotkey_enabled.isChecked(),hotkey=self.hotkey_edit.keySequence().toString(QKeySequence.PortableText))
        def saved(out):
            if out:self.mic_settings=settings;self.mic_revision=out['revision'];self.configure_hotkey();self.chat_controls();self.notice.setText('Configuração salva. Microfone só abre por clique ou atalho habilitado.')
            else:self.request('control/microphone',callback=self.loaded_microphone)
        self.request('control/microphone',{'settings':settings,'revision':self.mic_revision},callback=saved)
    def volume_changed(self,value):
        self.volume_label.setText(str(value)+'%'+(' · mudo' if value==0 else ''))
        self.volume_timer.start(150)  # Coalescer arraste; nunca sintetizar de novo.
    def save_volume(self):
        value=self.volume.value()
        def saved(out):
            if out:
                self.mic_settings['output_volume']=value;self.mic_revision=out['revision']
                self.notice.setText('Volume salvo para a Central; saída dos outros aplicativos não foi alterada.')
        self.request('control/microphone',{'settings':{'output_volume':value},'revision':self.mic_revision},callback=saved)
    def apply_volume(self):
        if self.closing or not self.player or self.volume_process:return
        if not shutil.which('pactl'):
            self.notice.setText('Volume durante a fala não confirmado; novo valor será usado no próximo áudio.');return
        player=self.player;name=self.player_stream;process=QProcess(self);self.volume_process=process
        def done(code,_):
            if self.volume_process is not process:return
            self.volume_process=None;process.deleteLater()
            if self.closing or self.player is not player:return
            try:
                index=owned_sink_input(json.loads(bytes(process.readAllStandardOutput())),int(player.processId()),name) if code==0 else None
            except (ValueError,TypeError):index=None
            if index is None:
                self.notice.setText('Volume durante a fala não confirmado; novo valor será usado no próximo áudio.');return
            value=self.volume.value();setter=QProcess(self);self.volume_process=setter
            def adjusted(code,_):
                if self.volume_process is not setter:return
                self.volume_process=None;setter.deleteLater()
                if code!=0:self.notice.setText('Volume durante a fala não confirmado; novo valor será usado no próximo áudio.')
                elif not self.closing and self.player is player and value!=self.volume.value():self.volume_timer.start(150)
            setter.finished.connect(adjusted);setter.errorOccurred.connect(lambda c:adjusted(-1,0) if c==QProcess.FailedToStart else None)
            setter.start('pactl',['set-sink-input-volume',str(index),str(pulse_volume(value))]);self.owned_timeout(setter,3000)
        process.finished.connect(done);process.errorOccurred.connect(lambda c:done(-1,0) if c==QProcess.FailedToStart else None)
        process.start('pactl',['--format=json','list','sink-inputs']);self.owned_timeout(process,3000)
    def toggle_capture(self):
        if self.capture:self.stop_capture(True)
        else:self.start_capture(self.mic_settings['mode'])
    def ptt_start(self):
        if self.mic_settings['mode']!='command':return
        if self.capture or self.asr_jobs or self.live_turns:
            self.notice.setText('Aguarde a conclusão da fala anterior; ela foi preservada.');return
        self.start_capture('command')
    def start_capture(self,mode,test=False):
        if self.live_cancels:
            self.notice.setText('Cancelamento da transcrição anterior ainda não confirmado; aguarde o desfecho.');return
        if mode=='detection' and self.acoustic_stop_pending:
            self.notice.setText('Aguarde a confirmação do cancelamento anterior. Se incerto, encerre a Central cooperativamente antes de reabrir.');return
        if mode=='detection' and not self.ambient_allowed.get(self.current_entity(),False):
            self.notice.setText('Ouvir o ambiente está desativado. Use o modo Comando para falar diretamente.');return
        if not test and self.chat_read_only:self.notice.setText('Abra a conversa de Hoje para gravar uma mensagem.');return
        if not shutil.which('parec'):self.notice.setText('parec indisponível; nenhum microfone iniciado.');return
        if self.capture or self.asr_jobs:self.notice.setText('Aguarde gravação/transcrição atual.');return
        self.segmenter=Segmenter(mode,self.mic_settings['threshold'],self.mic_settings['silence_ms'],self.mic_settings['segment_seconds'])
        self.capture_entity=self.current_entity();self.capture_session=self.chat_session.get('id');self.capture_scope=self.chat_scope;self.capture_test=test;process=QProcess(self);self.capture=process
        self.live_capture_mode=mode
        self.acoustic_windows.clear();self.acoustic_sequence=0;self.acoustic_pending=False;self.acoustic_waiting=None;self.acoustic_dropped=0;self.asr_echo=False
        self.acoustic_capture_id=uuid.uuid4().hex if mode=='detection' and not test else None
        if self.acoustic_capture_id:self.acoustic_status.setText('Detector local escutando · sons prováveis, autoria desconhecida. Sem gravação contínua em disco.')
        session_id=self.capture_session
        scope=self.capture_scope
        args=['--raw','--format=s16le','--rate=16000','--channels=1']
        if self.mic_settings.get('source'):args+=['--device='+self.mic_settings['source']]
        def read():
            if self.capture is not process:return
            raw=bytes(process.readAllStandardOutput());overlap=self.own_playback_overlap()
            if mode=='detection':self.asr_echo=self.asr_echo or overlap
            level,segments=self.segmenter.feed(raw);self.level.setValue(min(100,int(level*500)));self.audio_level.setValue(self.level.value())
            if self.acoustic_capture_id:
                try:windows=self.acoustic_windows.feed(raw)
                except ValueError:
                    self.stop_acoustic();self.acoustic_status.setText('Detector interrompido: captura acumulou áudio demais. Reinicie Detecção manualmente.');windows=[]
                for i,pcm in enumerate(windows):
                    # Horário da borda final da janela, não do resultado tardio.
                    lag=(len(windows)-1-i)*.48+len(self.acoustic_windows.buffer)/32000-.495
                    self.acoustic_window(pcm,overlap,time.time()-max(0,lag))
            if not test:
                for event in self.segmenter.events:
                    self.live_event(event['pcm'],event['ended'])
                    if self.capture is not process:return
                if self.segmenter.voiced:self.live_snapshot(bytes(self.segmenter.buffer))
            if not self.segmenter.buffer:self.asr_echo=overlap
        process.readyReadStandardOutput.connect(read)
        def error(code):
            self.notice.setText('Microfone indisponível/ocupado; confira entrada e servidor de som.')
            if code==QProcess.FailedToStart:self.capture_stopped(process)
        process.errorOccurred.connect(error)
        process.finished.connect(lambda *_:self.capture_stopped(process));process.start('parec',args)
        self.notice.setText('Microfone aberto para '+self.capture_entity.capitalize()+' · '+mode+'. Fechar janela interrompe captura.')
        if test:QTimer.singleShot(5000,lambda:self.stop_capture(True) if self.capture is process else None)
    def capture_stopped(self,process):
        if self.capture is process:
            self.live_failure('Microfone indisponível ou encerrado antes de concluir; envio automático bloqueado.')
            self.capture=None;self.segmenter=None;self.stop_acoustic();self.level.setValue(0);self.audio_level.setValue(0)
        process.deleteLater()
    def stop_capture(self,submit=False):
        if not submit:self.discard_live()
        process=self.capture
        if not process:return
        echo=self.asr_echo
        # Apenas QProcess desta janela; nunca mata outra captura/processo.
        mode=self.segmenter.mode;voiced=self.segmenter.voiced;pcm=self.segmenter.finish();e=self.capture_entity;test=self.capture_test;self.capture=None;self.segmenter=None;self.level.setValue(0);self.audio_level.setValue(0)
        self.stop_acoustic()
        process.terminate();self.owned_timeout(process,1000)
        if submit:
            if test:self.last_test_pcm=pcm;self.notice.setText('Gravação de teste guardada somente nesta janela. Ouvir / Testar ASR não envia conversa.')
            elif voiced or self.live_current or self.live_ignoring:self.live_event(pcm if voiced else b'',ended=True)
            else:self.notice.setText('Nenhuma fala detectada neste trecho; nada foi transcrito ou enviado.')
    def own_playback_overlap(self):
        return self.player is not None or time.monotonic()<self.acoustic_playback_until
    def stop_acoustic(self,*,notify=True):
        identifier=self.acoustic_capture_id;self.acoustic_capture_id=None
        self.acoustic_windows.clear();self.acoustic_waiting=None;self.acoustic_pending=False
        if not notify:
            self.acoustic_stop_pending=None;return  # não enviar IDs ao backend de outra geração
        if identifier:
            connection=(self.base,self.token)
            pending={'capture_id':identifier,'connection':connection,'admitted':False}
            self.acoustic_stop_pending=pending
            self.acoustic_status.setText('Escuta local encerrada; aguardando confirmação de cancelamento no servidor.')
            def stopped(out):
                if self.acoustic_stop_pending is not pending:return
                if out and out.get('cancelled') is True and out.get('capture_id')==identifier:
                    self.acoustic_stop_pending=None
                    self.acoustic_status.setText('Detector local: escuta encerrada e pendências invalidadas no servidor.')
                else:
                    pending['uncertain']=True
                    self.acoustic_status.setText('Escuta local encerrada; cancelamento no servidor não confirmado. Não será repetido automaticamente; encerre a Central cooperativamente para reconciliar.')
            if not self.sync_endpoint():stopped(None);return
            if connection!=(self.base,self.token):return
            admitted=self.request('audio/perception/stop',{'capture_id':identifier},callback=stopped,quiet=True)
            pending['admitted']=bool(admitted)
            if not admitted and self.acoustic_stop_pending is pending:stopped(None)
    def acoustic_window(self,pcm,overlap,observed_at):
        if not self.acoustic_capture_id:return
        packet=(pcm,overlap,observed_at)
        if self.acoustic_pending:
            if self.acoustic_waiting is not None:self.acoustic_dropped+=1
            self.acoustic_waiting=packet;return
        if self.acoustic_waiting is not None:
            self.acoustic_dropped+=1;self.acoustic_waiting=None
        capture_id=self.acoustic_capture_id;sequence=self.acoustic_sequence;self.acoustic_sequence+=1;self.acoustic_pending=True
        def done(out):
            if capture_id!=self.acoustic_capture_id:return
            self.acoustic_pending=False
            if out is None or out.get('cancelled'):
                self.stop_acoustic();self.acoustic_status.setText('Detector indisponível/resultado incerto; ASR continua. Reinicie Detecção para nova tentativa.');return
            if out.get('busy'):self.acoustic_dropped+=1
            events=out.get('events',[])
            if events:
                self.acoustic_status.setText('Som provável: '+', '.join(str(e['label']) for e in events)+(' · sobreposição com a voz do app; não entregue às entidades.' if out.get('playback_overlap') else ' · autoria desconhecida.'))
            if self.acoustic_dropped:self.acoustic_status.setText(self.acoustic_status.text().split(' · Janelas descartadas:')[0]+f' · Janelas descartadas: {self.acoustic_dropped}')
            pending=self.acoustic_waiting;self.acoustic_waiting=None
            if pending and time.time()-pending[2]<5:self.acoustic_window(*pending)
        admitted=self.request(self.query('audio/perception',entity=self.capture_entity,source='native_microphone',capture_id=capture_id,
            sequence=str(sequence),scope=self.capture_scope,playback_overlap=str(overlap).lower(),observed_at=observed_at),pcm,callback=done,binary=True,quiet=True)
        if not admitted and capture_id==self.acoustic_capture_id:
            self.acoustic_pending=False;self.acoustic_sequence-=1;self.acoustic_waiting=packet
    def test_mic(self):
        self.stop_capture(False);self.start_capture('command',True)
    def play_test_mic(self):
        if not self.last_test_pcm:self.notice.setText('Grave primeiro o teste de 5 segundos.');return
        try:self.stop_voice();self.play_bytes(wav_bytes(self.last_test_pcm))
        except ValueError as exc:self.notice.setText(str(exc))
    def test_asr(self):
        if self.last_test_pcm:self.transcribe(self.last_test_pcm,self.current_entity(),test=True)
        else:self.notice.setText('Grave primeiro o teste de microfone.')
    def transcribe(self,pcm,entity,test=False,session_id=None,scope=None,mode='command'):
        if mode=='detection' and not self.ambient_allowed.get(entity,False):return
        if not self.sync_endpoint():return
        try:data=wav_bytes(pcm)
        except ValueError as exc:self.notice.setText(str(exc));return
        session_id=session_id or (self.chat_session.get('id') if entity==self.current_entity() else None)
        scope=scope or self.chat_scope
        if self.asr_jobs:
            if len(self.asr_waiting)>=4:
                if mode!='detection':self.stop_capture(False)
                self.notice.setText('Fila de transcrição cheia: trecho excedente descartado. '+('Detecção continua aberta.' if mode=='detection' else 'Microfone pausado.'));return
            self.asr_waiting.append((pcm,entity,test,session_id,scope,mode));self.notice.setText('Fala guardada nesta janela; aguardando transcrição.');return
        self.asr_jobs['pending']={'entity':entity,'test':test,'session_id':session_id,'scope':scope,'mode':mode}
        def queued(out):
            pending=self.asr_jobs.pop('pending',None)
            if out and pending:self.asr_jobs[out['id']]=pending;self.notice.setText('Transcrevendo · nada enviado à entidade ainda.')
        if not self.request(self.query('audio/transcribe',entity=entity,source='native_microphone',mode=mode),data,callback=queued,binary=True):queued(None)
    def load_audio(self):
        self.listening_panel.refresh()
        self.request('control/audio',callback=self.audio_loaded,quiet=True)
    def audio_loaded(self,out):
        if out is None:return
        # Não sobrescrever edição em progresso a cada poll.
        if self.audio_config is None:
            self.audio_config=out;self.provider.setCurrentText(out['preferred_provider']);self.provider_changed()
        keys=' · '.join(k+': '+('API key CONFIGURADA' if v['key_configured'] else 'API key NÃO CONFIGURADA') for k,v in out['providers'].items())
        self.audio_status.setText(keys+'\nEntrada: '+self.mic_settings.get('source','padrão')+' · só um teste físico comprova captura/audição.')
    def provider_changed(self,*_):
        if not self.audio_config:return
        name=self.provider.currentText();p=self.audio_config['providers'].get(name,{})
        self.provider_enabled.setChecked(bool(p.get('enabled')));self.provider_enabled.setEnabled(name in ('elevenlabs','azure'))
        for e,w in self.voice_ids.items():w.setText(p.get('voices',{}).get(e,self.audio_config.get('local_voices',{}).get(e,{}).get('id','')));w.setEnabled(name in ('elevenlabs','azure'))
        self.tts_model.setEnabled(name=='elevenlabs');self.tts_model.setCurrentText(p.get('model') or 'eleven_multilingual_v2')
    def save_voice(self):
        if not self.audio_config:return
        data={'preferred_provider':self.provider.currentText(),'enabled':self.provider_enabled.isChecked(),
              'voices':{e:w.text().strip() for e,w in self.voice_ids.items()} if self.provider.currentText() in ('elevenlabs','azure') else {},'revision':self.audio_config['revision']}
        if data['preferred_provider']=='elevenlabs':data['model_id']=self.tts_model.currentText()
        def saved(out):
            if out:self.audio_config=None;self.load_audio();self.notice.setText('Provider/modelo salvos sem síntese. A chave precisa estar no ambiente da CENTRAL.')
        self.request('control/audio',data,callback=saved)
    def test_voice(self,entity):
        text=self.test_text.toPlainText().strip()
        if not 1<=len(text)<=2400:self.notice.setText('Digite 1–2400 caracteres para testar.');return
        if QMessageBox.question(self,'Teste de voz','Sintetizar a frase escolhida? Provider externo pode consumir quota.')!=QMessageBox.Yes:return
        data={'entity':entity,'confirm':True,'text':text,'provider':self.provider.currentText()}
        if data['provider']=='elevenlabs':data['model']=self.tts_model.currentText()
        self.begin_speech(entity,'audio/test',data,True)
    def begin_speech(self,entity,route,data,test=False):
        # Atualizar antes de capturar epoch/pending: o primeiro clique após
        # restart é novo, não uma resposta antiga a ser cancelada.
        if not self.sync_endpoint():return False
        continuous=self.capture and not self.capture_test and self.segmenter.mode=='detection'
        if not continuous:self.stop_capture(False)
        self.stop_voice();epoch=self.voice_epoch
        self.voice_pending={'entity':entity,'epoch':epoch}
        def queued(out):
            if epoch!=self.voice_epoch:
                if out:self.request('audio/cancel',{'id':out['id']})
                return
            self.voice_pending={}
            if out:self.voice_job=out['id'];self.voice_entity=entity;self.voice_test=test;self.voice_index=0;self.voice_receipt_sequence=0;self.voice_done=False;self.notice.setText('Preparando voz; provider real será exibido após síntese.')
            else:self.finish_voice()
        admitted=bool(self.request(route,data,callback=queued))
        if not admitted:queued(None)
        return admitted
    def handle_new_voice(self,entity,replies,streams):
        # Busy is temporary, not evidence that a reply was spoken. Disabled or
        # archived views intentionally consume observations: no retrospective quota.
        if self.chat_read_only or self.chat_before or self.chat_query or not self.auto_voice.isChecked() or (entity=='alistair' and self.chat_scope!='global'):
            self.voice_seen.update(m['id'] for m in replies)
            self.stream_seen.update(s['id'] for s in streams)
            return
        for m in replies:
            if any(s in self.stream_seen for s in (m.get('metadata') or {}).get('speech_streams',[])):
                self.voice_seen.add(m['id'])
        # Finish older complete replies before attaching a more recent stream.
        pending=next((m for m in replies if m['id'] not in self.voice_seen),None)
        matching=next((s for s in streams if pending and s['id'] in (pending.get('metadata') or {}).get('speech_streams',[])),None)
        stream=matching or (min(streams,key=lambda j:j.get('created_at',0)) if streams and not pending else None)
        speaker=pending.get('sender',entity) if pending else stream.get('entity',entity) if stream else entity
        if not self.can_auto_speak(speaker):return
        if stream:
            if self.begin_speech(speaker,'audio/stream',{'entity':speaker,'stream_id':stream['id']}):
                self.stream_seen.add(stream['id'])
                if pending:self.voice_seen.add(pending['id'])
        elif pending:
            if self.begin_speech(speaker,'audio/synthesize',{'entity':speaker,'message_id':pending['id']}):
                # Accepted/uncertain transport is never retried automatically.
                self.voice_seen.add(pending['id'])
                self.stream_seen.update((pending.get('metadata') or {}).get('speech_streams',[]))
    def can_auto_speak(self,entity):
        return not self.chat_read_only and not self.chat_before and not self.chat_query and self.auto_voice.isChecked() and entity!='alistair' and not self.player and not self.voice_job and not self.voice_pending and not self.asr_jobs and not self.asr_waiting and (not self.capture or (not self.capture_test and self.segmenter.mode=='detection'))
    def finish_voice(self):
        resume=self.resume_capture;notice=self.notice.text();self.stop_voice(cancel=False)
        if resume and not self.closing and resume[1]==self.current_entity():self.start_capture(resume[0]);self.notice.setText(notice+' · Microfone retomado após a fala.')
    def poll_audio(self):
        self.poll_live_cancels()
        self.pump_live()
        progress=getattr(self,'playback_progress',None)
        if progress and self.player is progress['process'] and progress['started'] and time.monotonic()-progress['last']>=1:
            progress['last']=time.monotonic()
            progress['report']('progress',progress['last']-progress['started'])
        if self.acoustic_waiting and not self.acoustic_pending and self.acoustic_capture_id:
            pending=self.acoustic_waiting;self.acoustic_waiting=None
            if time.time()-pending[2]<5:self.acoustic_window(*pending)
        if self.capture and self.segmenter.mode=='detection' and not self.ambient_policy_polling and time.monotonic()-self.ambient_policy_checked>=1:
            self.ambient_policy_polling=True;self.ambient_policy_checked=time.monotonic()
            def policy(out):self.ambient_policy_polling=False;self.apply_ambient_policy(out)
            if not self.request('control/microphone',callback=policy,quiet=True):self.ambient_policy_polling=False
        if not self.asr_jobs and self.asr_waiting and not self.closing:
            queued=self.asr_waiting.pop(0);pcm,entity,test,session=queued[:4];scope=queued[4] if len(queued)>4 else self.chat_scope
            self.transcribe(pcm,entity,test,session_id=session,scope=scope,mode=queued[5] if len(queued)>5 else 'command')
        for identifier in list(self.asr_jobs):
            if identifier=='pending' or self.asr_jobs[identifier].get('polling'):continue
            self.asr_jobs[identifier]['polling']=True
            if not self.request(self.query('audio/job',id=identifier),callback=lambda o,i=identifier:self.asr_result(i,o),quiet=True):self.asr_jobs[identifier]['polling']=False
        if self.voice_job and not self.voice_fetching and not self.player:
            self.voice_fetching=True;identifier=self.voice_job;epoch=self.voice_epoch
            def speech(out):
                self.voice_fetching=False
                if epoch!=self.voice_epoch or not out:return
                if out['status'] in ('error','interrupted'):
                    self.notice.setText(out.get('error') or 'Voz interrompida.');self.finish_voice();return
                result=out.get('result') or {};chunks=result.get('chunks',[])
                if self.voice_index<len(chunks):
                    chunk=chunks[self.voice_index]
                    if chunk['index']!=self.voice_index:self.notice.setText('Ordem de áudio não confirmada.');self.stop_voice();return
                    self.notice.setText('Provider REAL: '+str(chunk.get('provider'))+' · voz '+str(chunk.get('voice'))+' · modelo '+str(chunk.get('model') or 'não informado'))
                    self.voice_fetching=True
                    def fetched(data):
                        self.voice_fetching=False
                        if epoch==self.voice_epoch and data:self.play_bytes(data,identifier,self.voice_entity,self.voice_index)
                    if not self.request(self.query('audio/file',id=identifier,chunk=self.voice_index),callback=fetched,raw=True):self.voice_fetching=False
                elif out['status']=='done':self.finish_voice()
            if not self.request(self.query('audio/job',id=identifier),callback=speech,quiet=True):self.voice_fetching=False
    def asr_result(self,identifier,out):
        pending=self.asr_jobs.get(identifier)
        if not pending:return
        if pending.get('live'):self.live_result(identifier,out);return
        pending['polling']=False
        if out is None:return
        if out['status'] not in ('done','error','interrupted'):return
        self.asr_jobs.pop(identifier,None)
        if out['status']!='done':self.notice.setText(out.get('error') or 'Transcrição interrompida.');return
        if pending.get('mode')=='detection' and not self.ambient_allowed.get(pending['entity'],False):return
        text=(out.get('result') or {}).get('text','').strip();e=pending['entity']
        if not text:self.notice.setText('Nenhuma fala útil detectada. Nada enviado.');return
        if self.mic_settings['auto_send'] and not pending['test'] and pending.get('session_id'):
            e=pending['entity'];session=pending['session_id'];scope=pending.get('scope',self.chat_scope);key=(scope,e,session,text)
            data={'entity':e,'text':text,'wake':True,'submission_id':self.submissions.setdefault(key,uuid.uuid4().hex),
                  'conversation_session_id':session,'audio_job_id':identifier,'draft_origin':True,'automatic_asr':True,'chat_scope':scope}
            def sent(result):
                if result:
                    self.submissions.pop(key,None);self.notice.setText('Fala transcrita e aceita para '+e.capitalize()+'.');self.refresh()
                else:
                    self.keep_transcript(e,text,identifier,scope=scope)
                    self.notice.setText('Envio da fala não confirmado; texto guardado no rascunho. Não foi repetido automaticamente.')
            if not self.request('send',data,callback=sent):sent(None)
            return
        if pending['test']:self.audio_transcript.setPlainText(text)
        self.keep_transcript(e,text,identifier,scope=pending.get('scope'))
        self.notice.setText('Transcrição para '+e.capitalize()+': '+text+' · rascunho.' )
    def keep_transcript(self,e,text,identifier,scope=None):
        if scope and scope!=self.chat_scope:
            draft=self.scope_drafts.setdefault(scope,{name:'' for name in ENTITIES});draft[e]=(draft.get(e,'')+'\n'+text).strip();return
        self.drafts[e]=self.draft.toPlainText() if e==self.current_entity() else self.drafts[e]
        self.drafts[e]=(self.drafts[e]+'\n'+text).strip();self.origins[e]={'id':identifier,'text':text}
        if e==self.current_entity():self.draft.setPlainText(self.drafts[e])
    def play_bytes(self,data,job=None,entity=None,index=None):
        if not shutil.which('paplay'):self.notice.setText('paplay indisponível; áudio não reproduzido.');self.stop_voice();return
        self.player_file=Path(self.temp.name)/('play-'+uuid.uuid4().hex+'.wav');self.player_file.write_bytes(data);os.chmod(self.player_file,0o600)
        process=QProcess(self);self.player=process;self.player_stream='central-native-'+uuid.uuid4().hex;initial_volume=self.volume.value()
        args=['--volume='+str(pulse_volume(initial_volume)),'--stream-name='+self.player_stream]
        if self.mic_settings.get('output'):args+=['--device='+self.mic_settings['output']]
        args.append(str(self.player_file));file=self.player_file;epoch=self.voice_epoch;connection=(self.base,self.token)
        def report(event,position=None):
            if job and self.sync_endpoint() and epoch==self.voice_epoch and connection==(self.base,self.token):
                data={'entity':entity,'id':job,'chunk':index,'playback_event':event,'player':'native','observed_at':time.time()}
                self.voice_receipt_sequence=getattr(self,'voice_receipt_sequence',0)+1
                data['sequence']=self.voice_receipt_sequence
                if position is not None:data['position_seconds']=position
                self.request('audio/job',data)
        self.playback_progress=dict(process=process,started=None,last=0,report=report)
        def started():
            if self.player is not process:return
            at=time.monotonic();self.playback_progress.update(started=at,last=at);report('started')
        process.started.connect(started)
        process.started.connect(lambda:self.volume_timer.start(150) if self.player is process and self.volume.value()!=initial_volume else None)
        def finished(code,_):
            if self.player is process:
                self.acoustic_playback_until=time.monotonic()+1.1
                self.player=None;self.player_file=None
                self.playback_progress=None
                if not getattr(process,'voice_stop',False):
                    report('ended' if code==0 else 'failed')
                    if code==0 and epoch==self.voice_epoch and index is not None:self.voice_index=index+1
                    elif code!=0:self.notice.setText('Player não confirmou reprodução. Confira a saída.');self.stop_voice()
            file.unlink(missing_ok=True);process.deleteLater()
        def error(code):
            self.notice.setText('Falha ao iniciar player. Nenhuma reprodução confirmada.')
            if code==QProcess.FailedToStart:finished(-1,QProcess.NormalExit)
        process.finished.connect(finished);process.errorOccurred.connect(error)
        process.start('paplay',args)
    def stop_voice(self,*,cancel=True):
        self.playback_progress=None
        self.voice_epoch+=1;job=self.voice_job;e=self.voice_entity;self.voice_job=None;self.voice_fetching=False;self.voice_test=False;self.voice_entity=None;self.resume_capture=None;self.voice_pending={}
        if job and cancel:
            self.request('audio/cancel',{'id':job})
        connection=(self.base,self.token)
        def confirm():
            if job and cancel and connection==(self.base,self.token):
                self.request('audio/job',{'entity':e,'id':job,'chunk':None,'playback_event':'cancelled','player':'native','observed_at':time.time()})
        if self.player:
            self.acoustic_playback_until=time.monotonic()+1.1
            process=self.player
            if not getattr(process,'voice_stop',False):
                process.voice_stop=True;confirmed=[False]
                def stopped(*_):
                    if confirmed[0] or process.state()!=QProcess.NotRunning:return
                    confirmed[0]=True
                    if self.player is process:self.player=None
                    confirm()
                process.finished.connect(stopped);process.terminate();self.owned_timeout(process,1000)
                stopped()
        else:confirm()
    def load_memory(self):
        entity=self.current_entity()
        def loaded(out):
            if out is None or entity!=self.current_entity():return
            self.memory_list.clear()
            for m in out['items']:
                content=m.get('content',m.get('conteudo',m.get('what_happened',m.get('valor',m.get('input',m.get('resumo',''))))))
                item=QTreeWidgetItem([str(m.get('tipo'))+' / '+str(m.get('id')),str(content)[:300],str(m.get('fonte',m.get('source')))+' / '+str(m.get('confianca',m.get('confidence')))])
                item.setData(0,Qt.UserRole,m);self.memory_list.addTopLevelItem(item)
            self.memory_list.resizeColumnToContents(0)
        self.request(self.query('control/memory',entity=entity,q=self.memory_query.text(),scope='chat'),callback=loaded,quiet=True)
    def memories_authorized(self):
        return bool(self.memory_access and self.memory_entity==self.current_entity() and time.monotonic()<self.memory_until)
    def unlock_memories(self):
        e=self.current_entity();generation=self.memory_generation
        password,ok=QInputDialog.getText(self,'Abrir Memórias','Senha local de Memórias:',QLineEdit.Password)
        if not ok:return
        def opened(out):
            if not out or not out.get('unlocked') or e!=self.current_entity() or generation!=self.memory_generation:return
            if not self.nav.currentItem() or self.nav.currentItem().text()!='Memórias':return
            self.memory_access=out['access_token'];self.memory_entity=e;self.memory_until=time.monotonic()+out['expires_in']
            self.memory_timer.start(out['expires_in']*1000);self.memory_gate.setCurrentIndex(1);self.load_knowledge()
            self.notice.setText('Memórias de '+e.capitalize()+' abertas por até 5 minutos. Sair da aba ou trocar entidade bloqueia novamente.')
        self.request('control/knowledge/unlock',dict(entity=e,password=password),callback=opened)
    def lock_memories(self,revoke=True):
        if revoke and self.memory_access:
            self.request('control/knowledge/lock',dict(entity=self.memory_entity),callback=lambda _:None,quiet=True)
        self.memory_access='';self.memory_entity=None;self.memory_until=0;self.memory_generation+=1;self.memory_timer.stop()
        if hasattr(self,'memory_gate'):self.memory_gate.setCurrentIndex(0)
        if hasattr(self,'knowledge_panel'):
            for dialog in self.knowledge_panel.findChildren(QDialog):dialog.reject();dialog.deleteLater()
            self.knowledge_panel.clear();self.knowledge_panel.entity=None;self.knowledge_panel.summary.setText('Memórias bloqueadas.')
        if hasattr(self,'logic_workshop'):
            workshop=self.logic_workshop
            for dialog in workshop.findChildren(QDialog):dialog.reject();dialog.deleteLater()
            workshop.dirty=False;workshop.records=[];workshop.selector.clear();workshop.new();workshop.loaded_entity=None
    def load_knowledge(self):
        if not self.memories_authorized():
            self.lock_memories(revoke=bool(self.memory_access));return
        e=self.current_entity();panel=self.knowledge_panel
        generation=self.memory_generation
        query=(panel.search.text().strip(),panel.kind.currentData(),panel.page)
        def loaded(out):
            if self.memories_authorized() and generation==self.memory_generation and e==self.current_entity() and query==(panel.search.text().strip(),panel.kind.currentData(),panel.page):panel.render(out)
        self.request(self.query('control/knowledge',entity=e,q=query[0],type=query[1],page=query[2]),callback=loaded,quiet=True)
    def edit_knowledge(self,data,done):
        if not self.memories_authorized():self.lock_memories();self.notice.setText('Desbloqueie Memórias antes de alterar um cartão.');done(None);return
        entity=self.current_entity()
        def saved(out):
            if out and out.get('verified') is True:
                self.notice.setText('Conhecimento atualizado com backup. Histórico e outras entidades preservados.');self.load_knowledge();self.refresh()
            done(out)
        self.request('control/knowledge',dict(data,entity=entity),callback=saved)
    def set_password(self,on_saved=None):
        if self.password_dialog is not None:
            self.password_dialog.raise_();self.password_dialog.activateWindow();return
        dialog=PasswordSetup(self);self.password_dialog=dialog;acknowledged=False
        def active():return self.password_dialog is dialog
        def finished(*_):
            if active():self.password_dialog=None
            dialog.deleteLater()
        dialog.finished.connect(finished)
        def check(error=''):
            if not active():return
            dialog.set_busy(True)
            def state(out):
                if not active():return
                if not isinstance(out,dict) or type(out.get('configured'))is not bool:
                    dialog.known=False;dialog.set_busy(False)
                    dialog.error.setText(error or 'Não foi possível conferir a senha. Use Conferir estado; nenhum cadastro será repetido automaticamente.');return
                dialog.state(out['configured'])
                if acknowledged and out['configured']:
                    if self.memory_access:self.lock_memories(revoke=False)
                    message='Senha de exclusão salva e conferida. Nenhuma memória foi apagada.'
                    self.notice.setText(message);self.memory_status.setText(message);dialog.accept()
                    if callable(on_saved):on_saved()
                    return
                dialog.set_busy(False)
                if acknowledged:
                    dialog.known=False;dialog.save_button.setEnabled(False)
                    dialog.error.setText('O cadastro foi recebido, mas a gravação ainda não foi confirmada. Use Conferir estado; não reenvie a senha.')
                else:dialog.error.setText(error)
            if not self.request('control/password',callback=state):
                dialog.known=False;dialog.set_busy(False);dialog.error.setText('Consulta não enviada. Aguarde e use Conferir estado.')
        def save(data):
            def saved(out):
                nonlocal acknowledged
                if not active():return
                if not isinstance(out,dict) or out.get('configured')is not True:
                    check(self.notice.text() if out is None else 'Cadastro não confirmado. Confira o estado antes de tentar novamente.');return
                acknowledged=True;check()
            if not self.request('control/password',data,callback=saved):
                dialog.set_busy(False);dialog.error.setText('Cadastro não enviado. Aguarde os pedidos em andamento e tente salvar novamente.')
        dialog.save_requested.connect(save);dialog.check_requested.connect(check)
        dialog.open();check()
    def erase_memory(self,all_memories):
        if self.memory_delete_busy:self.memory_status.setText('Uma operação de memória já está em andamento.');return
        entity=self.current_entity();targets=[{'table':m['table'],'id':str(m['id'])} for item in self.memory_list.selectedItems() if (m:=item.data(0,Qt.UserRole)).get('id')]
        if not all_memories and any(t['table']=='messages' for t in targets):self.notice.setText('O histórico bruto é somente leitura aqui. Use Apagar todas para limpar também as conversas, com prévia, senha e backup.');return
        if not all_memories and not targets:self.notice.setText('Selecione uma memória primeiro.');return
        data={'entity':entity,'all':all_memories,'targets':targets if not all_memories else []};self.memory_delete_busy=True
        def fail(message=None):
            self.memory_delete_busy=False;message=message or self.notice.text() or 'Operação não confirmada.'
            self.memory_status.setText(message);QMessageBox.warning(self,'Memória não apagada / não confirmada',message)
        def cancel():self.memory_delete_busy=False;self.memory_status.setText('Exclusão cancelada. Nenhum pedido de exclusão enviado.')
        def preview(out):
            if out is None:fail();return
            text='Entidade: '+entity.capitalize()+'\nRegistros: '+self.pretty(out['counts'])+'\n'+out.get('note','')+'\nUm backup será criado antes. A entidade deve estar dormindo. Continuar?'
            if QMessageBox.question(self,'Confirmar exclusão de memórias',text,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:cancel();return
            password,ok=QInputDialog.getText(self,'Senha de exclusão','Senha definida na central:',QLineEdit.Password)
            if not ok:cancel();return
            payload=data|{'confirm':True,'password':password,'fingerprint':out['fingerprint'],'request_id':'memory-'+uuid.uuid4().hex}
            if all_memories:payload['scope']=out.get('scope')
            self.memory_status.setText('Criando backup e apagando os registros confirmados de '+entity.capitalize()+'…')
            def erased(result):
                if result is None:fail();return
                self.memory_delete_busy=False
                if not result.get('verified'):fail('O backend não confirmou a exclusão. Não repita sem consultar o diagnóstico.');return
                self.notice.setText('Exclusão VERIFICADA em '+entity.capitalize()+': '+str(result['deleted'])+' registros. Backup: '+str(result['backup']))
                self.memory_status.setText(self.notice.text());self.load_memory();self.load_knowledge()
                if result.get('chat_cleared'):
                    self.stop_voice();self.reset_chat_view();self.refresh()
            if not self.request('control/memory/delete',payload,callback=erased,timeout=90):fail('Pedido não enviado. Aguarde a Central e tente novamente.')
        def prepare(out):
            if out is None:fail();return
            affected=set(ENTITIES)if all_memories else {entity}
            presence=next((p for p in out.get('presence',[]) if p.get('entity_id')==entity),{})
            busy=(any(p.get('status')not in('offline','sleeping')for p in out.get('presence',[])if p.get('entity_id')in affected) or
                  any(j.get('entity')in affected and j.get('status') in ('queued','running') for j in out.get('jobs',[])) or
                  any(r.get('entity')in affected for r in out.get('resources',[])))
            if not busy:
                self.memory_status.setText('Preparando a prévia de '+entity.capitalize()+'…')
                if not self.request('control/memory/preview',data,callback=preview):fail('Prévia não enviada. Nenhuma memória foi apagada.')
                return
            if not presence:fail('Estado da entidade indisponível; não é seguro apagar.');return
            subject='As três entidades precisam dormir para limpar conversas compartilhadas. Apenas os dados de '+entity.capitalize()+' serão apagados.' if all_memories else entity.capitalize()+' precisa dormir antes de apagar memórias.'
            if QMessageBox.question(self,'Preparar exclusão',subject+' Solicitar sono e aguardar?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:cancel();return
            deadline=time.monotonic()+35
            def observed(state):
                if self.closing or self.shutdown_pending:cancel();return
                if state is None:fail();return
                statuses={p.get('entity_id'):p.get('status')for p in state.get('presence',[])}
                if (all(statuses.get(e,'offline')in('sleeping','offline')for e in affected) and
                        not any(j.get('entity')in affected and j.get('status') in ('queued','running') for j in state.get('jobs',[])) and
                        not any(r.get('entity')in affected for r in state.get('resources',[]))):
                    prepare(state);return
                if time.monotonic()>deadline:fail('Sono ainda não confirmado. Nenhuma memória foi apagada. Aguarde e confira o estado.');return
                QTimer.singleShot(500,lambda:self.request(self.query('state',entity=entity,daily=1),callback=observed))
            def slept(result):
                if result is None:fail();return
                self.memory_status.setText('Aguardando sono confirmado de '+entity.capitalize()+'…')
                self.request(self.query('state',entity=entity,daily=1),callback=observed)
            pending=iter(sorted(affected))
            def sleep_next(result=True):
                if result is None:fail();return
                target=next(pending,None)
                if target is None:slept(result);return
                if not self.request('sleep',{'entity':target},callback=sleep_next):fail('Pedido de sono não enviado; nada foi apagado.')
            sleep_next()
        def security(out):
            if out is None:fail();return
            if not out.get('configured'):
                self.memory_delete_busy=False
                self.memory_status.setText('Defina primeiro a senha de exclusão. Depois use Apagar novamente. Nenhuma memória foi apagada.')
                QMessageBox.information(self,'Senha de exclusão necessária',self.memory_status.text());self.set_password();return
            if not self.request(self.query('state',entity=entity,daily=1),callback=prepare):fail('Não foi possível consultar o estado; nada foi apagado.')
        if not self.request('control/password',callback=security):fail('Não foi possível verificar a senha configurada; nada foi apagado.')
    def load_tools(self):
        e=self.current_entity()
        def loaded(out):
            if not out or e!=self.current_entity():return
            # Só atualizar catálogo ao entrar/mudar entidade, para preservar edição.
            if self.tool_config and self.tool_config.get('entity')==e:return
            self.tool_config=out;self.tools.clear()
            for capability in out.get('controls',[]):
                state=Qt.Unchecked if not capability['enabled'] else Qt.PartiallyChecked if capability.get('legacy_restrictions') else Qt.Checked
                item=QTreeWidgetItem([capability['label'],capability['description']]);item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
                item.setData(0,Qt.UserRole,{'key':capability['key'],'initial':int(state)});item.setCheckState(0,state);self.tools.addTopLevelItem(item)
                item.setToolTip(0,'Existem restrições antigas parciais. Marque para permitir o grupo inteiro ou desmarque para bloquear.' if state==Qt.PartiallyChecked else capability['description'])
            self.tools_note.setText(out.get('note',''));self.tools.resizeColumnToContents(0)
        self.request(self.query('control/capabilities',entity=e),callback=loaded,quiet=True)
    def reload_tools(self):self.tool_config=None;self.load_tools()
    def save_tools(self):
        if not self.tool_config or self.tool_config.get('entity')!=self.current_entity():return
        changes={};entity=self.current_entity()
        for i in range(self.tools.topLevelItemCount()):
            item=self.tools.topLevelItem(i);origin=item.data(0,Qt.UserRole)
            if origin and int(item.checkState(0))!=origin['initial']:changes[origin['key']]=item.checkState(0)==Qt.Checked
        if not changes:self.notice.setText('Nenhuma permissão foi alterada.');return
        def saved(out):
            if out and entity==self.current_entity():
                self.tool_config=None;self.load_tools();self.request('control/microphone',callback=self.loaded_microphone,quiet=True)
                self.notice.setText('Permissões salvas para próximos usos. Nada foi iniciado automaticamente.')
        self.request('control/tools',{'entity':entity,'capabilities':changes,'revision':self.tool_config['revision']},callback=saved)
    def load_apis(self):
        self.request('control/apis',callback=self.render_apis,quiet=True)
    def render_apis(self,out):
        if not isinstance(out,dict):return
        self.api_state=out;self.api_list.clear()
        nomes={'hoshino':'Hoshino','lilith':'Lilith','alistair':'Alistair'}
        for api in out.get('apis',[]):
            uso=', '.join(nomes.get(e,e) for e in api.get('usada_por',[])) or 'ninguém'
            texto=f"{api['nome']} · {api['rotulo']} · {api['modelo']} · {'chave salva' if api['tem_chave'] else 'sem chave'} · usada por: {uso}"
            sit=api.get('situacao') or {}
            if sit.get('estado')=='ok':texto+=f" · funcionou em {sit.get('quando')}"
            elif sit.get('estado')=='erro':texto+=f" · erro em {sit.get('quando')}: {str(sit.get('detalhe',''))[:70]}"
            item=QListWidgetItem(texto);item.setData(Qt.UserRole,api);self.api_list.addItem(item)
        for e,box in self.api_choice.items():
            box.blockSignals(True);box.clear();box.addItem('Local (Ollama, neste PC)',None)
            for api in out.get('apis',[]):box.addItem(api['nome']+' · '+api['modelo'],api['id'])
            box.setCurrentIndex(max(0,box.findData(out.get('entidades',{}).get(e))));box.blockSignals(False)
    def api_selected(self):
        item=self.api_list.currentItem()
        if not item:self.notice.setText('Escolha uma API na lista.');return None
        return item.data(Qt.UserRole)
    def api_send(self,data,done_text):
        if not self.api_state:self.notice.setText('APIs ainda não carregadas; tente de novo.');return
        def saved(out):
            if out:self.render_apis(out);self.notice.setText(done_text)
        self.request('control/apis',dict(data,revision=self.api_state.get('revision')),callback=saved)
    def api_dialog(self,api):
        if not self.api_state:self.notice.setText('APIs ainda não carregadas; tente de novo.');return
        dialog=QDialog(self);dialog.setWindowTitle('Alterar API' if api else 'Adicionar API');form=QFormLayout(dialog)
        nome=QLineEdit((api or {}).get('nome',''));provedor=QComboBox()
        for p in self.api_state.get('provedores',[]):provedor.addItem(p['rotulo'],p['id'])
        url=QLineEdit((api or {}).get('url',''));modelo=QLineEdit(((api or {}).get('modelo','')) if api else '')
        chave=QLineEdit();chave.setEchoMode(QLineEdit.Password)
        chave.setPlaceholderText('Deixe vazio para manter a chave salva' if api and api.get('tem_chave') else 'Cole a chave aqui')
        def presets():
            p=next((x for x in self.api_state.get('provedores',[]) if x['id']==provedor.currentData()),{})
            url.setPlaceholderText(p.get('url') or 'https://…/v1/chat/completions');modelo.setPlaceholderText(p.get('modelo') or 'nome do modelo')
        provedor.currentIndexChanged.connect(lambda _:presets())
        if api:provedor.setCurrentIndex(max(0,provedor.findData(api.get('provedor'))))
        presets()
        for rotulo,campo in (('Nome',nome),('Provedor',provedor),('Endereço (só se for diferente)',url),('Modelo',modelo),('Chave',chave)):form.addRow(rotulo,campo)
        botoes=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);form.addRow(botoes)
        botoes.accepted.connect(dialog.accept);botoes.rejected.connect(dialog.reject)
        if dialog.exec_()!=QDialog.Accepted:return
        data=dict(action='salvar',nome=nome.text().strip(),provedor=provedor.currentData(),url=url.text().strip(),modelo=modelo.text().strip())
        if api:data['id']=api['id']
        if chave.text().strip():data['chave']=chave.text().strip()
        chave.clear()
        self.api_send(data,'API salva. Escolha abaixo quem usa cada uma.')
    def api_edit_selected(self):
        api=self.api_selected()
        if api:self.api_dialog(api)
    def api_remove_selected(self):
        api=self.api_selected()
        if not api:return
        if QMessageBox.question(self,'Remover API','Remover "'+api['nome']+'" e a chave dela? Quem usava volta para o modelo local.')!=QMessageBox.Yes:return
        self.api_send(dict(action='remover',id=api['id']),'API removida; quem usava voltou para o modelo local.')
    def api_forget_key_selected(self):
        api=self.api_selected()
        if api:self.api_send(dict(action='apagar_chave',id=api['id']),'Chave apagada deste PC.')
    def api_assign(self,entity):
        box=self.api_choice[entity];escolhida=box.currentData()
        self.api_send(dict(action='atribuir',entity=entity,id=escolhida),
                      entity.capitalize()+(' usa agora '+box.currentText()+' (vale na próxima resposta).' if escolhida else ' usa agora o modelo local.'))
    def load_models(self):
        self.load_apis()
        e=self.current_entity()
        self.execution_box.setVisible(e=='alistair')
        if e=='alistair':self.load_execution()
        def loaded(out):
            if not out or e!=self.current_entity():return
            if self.model_config and self.model_config.get('entity')==e:return
            self.model_config=out;self.models.clear()
            for model in out['options']:self.models.addItem(model['model'])
            self.models.setCurrentText(out['primary']);self.context.setRange(out['context_min'],out['context_max']);self.context.setSingleStep(out['context_step'] if out.get('context_step',1)>1 else 1024);self.context.setValue(out['context'])  # passo 1 = livre; como a Central web, 1024
            self.update_model_output_limit();self.out_tokens.setValue(out['output'])
            self.fill_gpu_layers(out.get('gpu_layers'))
            prompt=out.get('prompt_identity') or {}
            prompt_note=('' if not prompt else
                '\nPrompt de sistema: '+('reduzido — os pesos selecionados foram treinados em '+str(prompt.get('trained_corpus'))
                                          if prompt.get('trained_corpus') and prompt.get('mode')=='reduzido' else prompt.get('mode','completo'))+
                (' (forçado por HOSHINO_PROMPT_IDENTIDADE='+str(prompt.get('override'))+')' if prompt.get('override') not in (None,'auto') else ''))
            self.model_hint.setText(out['impact_note']+prompt_note);self.model_detail.setPlainText(self.pretty(out))
        self.request(self.query('control/models',entity=e),callback=loaded,quiet=True)
        self.load_model_versions(e)
        def files(out):
            if out is None:return
            self.files.clear()
            for f in out['items']:
                item=QTreeWidgetItem([f['path'],str(round(f['size_bytes']/1024**2,2))+' MiB']);item.setData(0,Qt.UserRole,f);self.files.addTopLevelItem(item)
        self.request('control/files',callback=files,quiet=True)

    def load_execution(self,force=False):
        def loaded(out):
            if not out or self.current_entity()!='alistair':return
            if force or self.execution_config is None:
                s=out['settings'];self.execution_destination.setCurrentIndex(max(0,self.execution_destination.findData(s['destination'])))
                self.execution_ip.setText(s['xbox_ip']);self.execution_start.setChecked(s['auto_start']);self.execution_sync.setChecked(s['auto_sync']);self.execution_lan.setChecked(s['trusted_lan'])
                self.execution_config=out
            state=out['xbox'];fresh='atual' if state.get('fresh') else 'antigo/não confirmado agora'
            limits=out.get('model_limits',{});configured=limits.get('configured')or{};applied=limits.get('applied')or{}
            limits_note=('\nLimites salvos: contexto '+str(configured.get('context','?'))+' / saída '+str(configured.get('output','?'))+
                         ' · últimos aplicados noXbox: contexto '+str(applied.get('context','não confirmado'))+' / saída '+str(applied.get('output','não confirmado'))+
                         (' · aguardando sincronização'if limits.get('pending')else' · sincronizados na última preparação')+
                         (' · cache confirmado no último uso'if state.get('context_verified')else' · cache aguardando primeira resposta')+
                         ('\n'+limits['error']if limits.get('error')else''))if limits else''
            self.execution_status.setText(out['note']+'\nAcesso salvo: '+('sim'if out['credentials_configured']else'não')+' · certificado: '+('sim'if out['certificate_configured']else'não')+'\nXbox: '+str(state.get('state','não conferido'))+' · observação '+fresh+(' · operação pendente: '+str(state['pending'].get('operation')) if state.get('pending') else '')+('\n'+state['reason'] if state.get('reason')else '')+limits_note)
        self.request('control/alistair/execution',callback=loaded,quiet=True)

    def import_execution_certificate(self):
        name,_=QFileDialog.getOpenFileName(self,'Certificado público do Device Portal Xbox','','Certificado público (*.cer *.pem)')
        if not name:return
        try:
            raw=Path(name).read_bytes()
            if len(raw)>16384:raise ValueError('Certificado excessivo.')
            if b'PRIVATE KEY'in raw:raise ValueError('Não selecione chave privada.')
            if b'BEGIN CERTIFICATE'in raw:self.execution_certificate=raw.decode('ascii')
            else:
                import ssl
                self.execution_certificate=ssl.DER_cert_to_PEM_cert(raw)
            self.notice.setText('Certificado público selecionado; será validado contra a raiz já conhecida ao salvar.')
        except Exception:self.notice.setText('Certificado público inválido; nada foi importado.')

    def save_execution(self):
        if self.current_entity()!='alistair' or not self.execution_config:return
        payload=dict(settings=dict(destination=self.execution_destination.currentData(),xbox_ip=self.execution_ip.text().strip(),auto_start=self.execution_start.isChecked(),auto_sync=self.execution_sync.isChecked(),trusted_lan=self.execution_lan.isChecked()),revision=self.execution_config['revision'])
        if self.execution_user.text() or self.execution_password.text():payload.update(username=self.execution_user.text().strip(),password=self.execution_password.text())
        if self.execution_certificate:payload['certificate_pem']=self.execution_certificate
        def saved(out):
            self.execution_password.clear();self.execution_user.clear()
            if out:
                self.execution_certificate='';self.load_execution(True);self.model_config=None;self.load_models();self.notice.setText(out['note'])
        self.request('control/alistair/execution',payload,callback=saved,timeout=20)

    def check_execution(self,action):
        if self.current_entity()!='alistair' or not self.execution_config:return
        if QMessageBox.question(self,'Executor Xbox','Conferir e sincronizar a configuração técnica pode fechar/reabrir somente o app Alistair noXbox. Alistair deve estar dormindo. Não envia bancos, não instala modelos novos e não repete pedidos incertos. Continuar?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.notice.setText('Conferindo executor Xbox. Não repita se demorar; hashes físicos podem levar alguns minutos.')
        self.request('control/alistair/execution/check',dict(action=action,revision=self.execution_config['revision']),callback=lambda out:self.load_execution(True),timeout=1200)
    def load_model_versions(self,e):
        def loaded(out):
            if not out or e!=self.current_entity() or 'families' not in out:return
            previous=self.version_family.currentData();self.version_data=out
            self.version_family.blockSignals(True);self.version_family.clear()
            for family in out['families']:self.version_family.addItem(family['label'],family['model_id'])
            primary=out.get('selection',{}).get('primary',previous)
            idx=self.version_family.findData(primary);self.version_family.setCurrentIndex(max(0,idx))
            self.version_family.blockSignals(False);self.version_family_changed()
        self.request(self.query('control/model-versions',entity=e),callback=loaded,quiet=True)
    def version_family_changed(self,*_):
        d=self.version_data;self.version_source.blockSignals(True);self.version_source.clear()
        if d and d['entity']==self.current_entity():
            family=next((f for f in d['families'] if f['model_id']==self.version_family.currentData()),{})
            labels={'original':'Original · intacto','checkpoint':'Último checkpoint · experimental',
                    'trained':'Último treino concluído · experimental','stable':'Última estável · avaliada'}
            selected=d.get('selection',{}).get('models',{}).get(family.get('model_id'),{})
            for entry in family.get('entries',[]):
                self.version_source.addItem(labels[entry['kind']],entry)
                if entry['source_sha256']==selected.get('source_sha256'):self.version_source.setCurrentIndex(self.version_source.count()-1)
        self.version_source.blockSignals(False);self.version_source_changed()
    def version_source_changed(self,*_):
        row=self.version_source.currentData()
        if not row:self.version_status.setText('Nenhuma versão íntegra disponível para esta família.');return
        status='Pronta para selecionar' if row['ready'] else 'Precisa de preparação e verificação física'
        quality=('Experimental — não homologada como estável. ' if row['experimental'] else 'Original/estável preservado. ')
        if row['evaluation_available']:quality+=f"Avaliação registrada: {row['behavioral_passed']}/{row['behavioral_total']} verificações. "
        current=(self.version_data or {}).get('selection',{});active=current.get('models',{}).get(current.get('primary'),{})
        self.version_status.setText(status+'\n'+quality+f"\nReferência: {row['ref']} · SHA {row['source_sha256'][:12]}"+
                                   ('\nSelecionada: '+active['alias'] if active else '\nSelecionada: configuração original'))
    def use_model_version(self,prepare):
        d=self.version_data;row=self.version_source.currentData()
        if not d or d['entity']!=self.current_entity():return
        if not row:return
        if not prepare and not row['ready']:
            self.notice.setText('Prepare esta versão primeiro e atualize após o término.');return
        consent=False
        if row['experimental']:
            consent=QMessageBox.question(self,'Versão experimental',
                'Este candidato não foi aprovado como estável e pode errar identidade, memória ou ações. '
                'Ele não substituirá os pesos originais. Deseja '+('preparar' if prepare else 'usar')+' esta versão?',
                QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
            if not consent:return
        payload=dict(entity=d['entity'],model_id=row['model_id'],kind=row['kind'],ref=row['ref'],
                     revision=d['revision'],experimental_consent=consent)
        def done(out):
            if out:
                self.model_config=None;self.load_models()
                self.notice.setText(('Preparação local registrada; acompanhe no Laboratório e atualize versões ao terminar.' if prepare else
                                     'Versão selecionada para o próximo despertar. Identidade e memória preservadas.'))
        self.request('control/model-versions'+('/prepare' if prepare else ''),payload,callback=done)
    def fill_gpu_layers(self,layers):
        self.gpu_layers.blockSignals(True);self.gpu_layers.clear()
        if not layers:
            self.gpu_layers.addItem('Definido pelo destino do Alistair (4B inteiro)',None);self.gpu_layers.setEnabled(False)
        else:
            total=layers['total']
            self.gpu_layers.addItem('Automático — escada medida pela VRAM livre',None)
            for n in sorted(layers['measured'],reverse=True):
                self.gpu_layers.addItem(f'{n} na GPU · {total-n} na CPU'+(' (todas na GPU)' if n==total else ''),n)
            self.gpu_layers.setCurrentIndex(max(0,self.gpu_layers.findData(layers['fixed'])) if layers['fixed'] is not None else 0)
            self.gpu_layers.setEnabled(True)
        self.gpu_layers.blockSignals(False)
    def save_model(self):
        self.context.interpretText();self.out_tokens.interpretText()  # texto ainda no campo vale o valor mais próximo
        if self.model_config:
            payload={'entity':self.current_entity(),'model':self.models.currentText(),'context':self.context.value(),'output':self.out_tokens.value(),'revision':self.model_config['revision']}
            layers=self.model_config.get('gpu_layers')
            if layers:payload.update(gpu_layers=self.gpu_layers.currentData(),layers_revision=layers['revision'])
            self.request('control/models',payload,callback=lambda o:self.model_saved(o))
    def poll_gpu_alerts(self):
        # Um pedido por vez; resposta perdida (troca de conexão) libera depois de 15 s.
        if self.closing or not self.connected:return
        if self.gpu_alert_sent is not None and time.monotonic()-self.gpu_alert_sent<15:return
        self.gpu_alert_sent=time.monotonic()
        def received(out):
            self.gpu_alert_sent=None
            if out is not None:self.render_gpu_alerts(out.get('alerts') or [])
        self.request('control/gpu-alerts',callback=received,quiet=True,silent=True)  # backend antigo (404) fica mudo
    def render_gpu_alerts(self,alerts):
        self.gpu_alerts=alerts
        visible=[a for a in alerts if a.get('key') not in self.gpu_alert_dismissed]
        if not visible:self.gpu_alert_box.hide();return
        self.gpu_alert_text.setText('\n\n'.join('⚠ '+a['title']+'\n'+a['text'] for a in visible));self.gpu_alert_box.show()
        for a in visible:
            # Avisa de novo quando passa a haver mensagem sua esperando.
            key=a['key']+(':mensagem' if a.get('message_waiting') else '')
            if key in self.gpu_alert_notified:continue
            self.gpu_alert_notified.add(key);QApplication.alert(self,0)
            QProcess.startDetached('notify-send',['-a','Hoshino e Lilith','-u','critical' if a.get('message_waiting') else 'normal',
                                                  '-i','dialog-warning',a['title'],a['text']])
    def open_gpu_alert_models(self):
        visible=[a for a in self.gpu_alerts if a.get('key') not in self.gpu_alert_dismissed]
        if visible and visible[0].get('entity') in ENTITIES:self.entity.setCurrentIndex(ENTITIES.index(visible[0]['entity']))
        self.nav.setCurrentRow(PAGES.index('Modelos'))
    def dismiss_gpu_alert(self):
        self.gpu_alert_dismissed.update(a.get('key') for a in self.gpu_alerts);self.gpu_alert_box.hide()
    def update_model_output_limit(self,*_):
        maximum=(getattr(self,'model_config',None)or{}).get('output_max',8192)
        self.out_tokens.setMaximum(max(128,min(maximum,self.context.value()-512)))
    def model_saved(self,out):
        if out:self.model_config=None;self.load_models();self.notice.setText('Salvo. Executor será usado após dormir/acordar; identidade/memória independentes.')
    def import_model(self):
        name,_=QFileDialog.getOpenFileName(self,'Importar pesos existentes sem ativar novo executor','','GGUF (*.gguf)')
        if not name:return
        path=Path(name)
        def queued(out):
            if not out:return
            source=path.open('rb');offset=0;identifier=out['id']
            def chunk(_=True):
                nonlocal offset
                block=source.read(2*1024**2)
                if not block:source.close();self.request('control/import/finish',{'id':identifier},callback=lambda r:self.notice.setText('Arquivo verificado, não adotado como executor novo.') if r else None);return
                start=offset;offset+=len(block)
                def written(r):
                    if r is None:source.close();self.notice.setText('Transferência não confirmada; staging preservado.');return
                    self.notice.setText(f'Importação: {offset}/{path.stat().st_size} bytes');chunk()
                self.request(self.query('control/upload',id=identifier,offset=start),block,callback=written,binary=True)
            chunk()
        self.request('control/import',{'entity':self.current_entity(),'name':path.name,'size':path.stat().st_size},callback=queued)
    def export_model(self):
        selected=self.files.selectedItems()
        if selected:self.request('control/export',{'entity':self.current_entity(),'id':selected[0].data(0,Qt.UserRole)['id']})
    def load_interface(self):
        def loaded(out):
            if out is None or self.ui_config is not None:return
            self.ui_config=out;s=out['settings'];self.overlay_enabled.setChecked(s.get('overlay_enabled',False));self.topmost.setChecked(s.get('always_on_top',True));self.balloons.setChecked(s.get('balloons',True));self.silent.setChecked(s.get('silent',False));self.balloon_seconds.setValue(s.get('balloon_seconds',7))
            self.reduced_motion.setChecked(s.get('reduced_motion',False))
            self.clipboard_import.setChecked(s.get('clipboard_import', True) is True)
            self.clipboard_auto.setChecked(s.get('clipboard_auto', True) is True)
            self.timeline_page_size.setCurrentIndex(max(0,self.timeline_page_size.findData(s.get('timeline_page_size',50))))
            self.chat_controls()
            for entity,(mode,color,picture,mood) in self.orb_controls.items():
                style=s.get('orb_styles',{}).get(entity,{})
                mode.setCurrentIndex(1 if style.get('mode')=='image' else 0);color.setText(style.get('base_color',COLORS[entity]));picture.setText(style.get('image_path',''));mood.setChecked(style.get('mood_tint',True))
        self.request('control/interface',callback=loaded,quiet=True)
        self.request('control/rede',callback=self.render_lan,quiet=True,silent=True)
        self.request('control/vram',callback=self.render_vram,quiet=True,silent=True)
    def pc2_local_path(self):return self.root/'compartilhado/runtime/launcher/painel_pc2.json'
    def pc2_local(self):
        try:data=json.loads(self.pc2_local_path().read_text())
        except (OSError,ValueError):data={}
        return data if isinstance(data,dict) else {}
    def pc2_save_local(self,key,checked):
        path=self.pc2_local_path();path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(dict(self.pc2_local(),**{key:bool(checked)}))+'\n')
        what={'comandos':'Abrir e executar coisas','tela':'Ver a tela','ouvir_pc1':'Som do PC1','mic_para_pc1':'Microfone para o PC1'}[key]
        self.notice.setText(what+' neste PC: '+('permitido.' if key in ('comandos','tela') and checked else 'ligado.' if checked else 'desligado.'))
        if key in ('ouvir_pc1','mic_para_pc1'):self.pc2_bridge_apply()
    def pc2_bridge_apply(self):
        """Liga/desliga a ponte de áudio conforme as opções deste PC (só no painel do PC2)."""
        if self.closing or not self.remote_panel():return
        if getattr(self,'pc2_bridge',None) is None:
            if not (shutil.which('parec') and shutil.which('pacat')):
                self.pc2_bridge_status.setText('Ponte de áudio: parec/pacat ausentes (pacote pulseaudio-utils).');return
            self.pc2_bridge=native_ponte.Cliente(self.base,self.token)
        local=self.pc2_local()
        self.pc2_bridge.ligar('som',local.get('ouvir_pc1',True) is not False)
        self.pc2_bridge.ligar('microfone',local.get('mic_para_pc1',True) is not False)
    def pc2_bridge_show(self):
        bridge=getattr(self,'pc2_bridge',None)
        if bridge is None:return
        bridge.base=(self.base or '').rstrip('/');bridge.token=self.token  # código trocado no PC1: a próxima reconexão já usa o novo
        state=bridge.estado()
        self.pc2_bridge_status.setText('Ponte de áudio · som do PC1: '+state['som']+' · microfone: '+state['microfone']+'.')
    def pc2_collect_senses(self):
        # Sensores do próprio projeto (janela ativa, janelas, mídia, tempo parado, carga), num processo à parte.
        if self.closing or not self.connected or not self.remote_panel() or self.pc2_sense_process is not None:return
        code=('import json,sys;sys.path.insert(0,sys.argv[1]);import sensors;print(json.dumps(sensors.estado(),ensure_ascii=False))')
        process=QProcess(self);self.pc2_sense_process=process
        def finished(*_):
            self.pc2_sense_process=None
            try:estado=json.loads(bytes(process.readAllStandardOutput()).decode('utf-8','replace') or 'null')
            except ValueError:estado=None
            process.deleteLater()
            if isinstance(estado,dict):self.pc2_send_senses(estado)
        process.finished.connect(finished);process.start(sys.executable,['-c',code,str(Path(__file__).resolve().parents[1]/'tools')])
        self.owned_timeout(process,8000)
    def pc2_send_senses(self,estado):
        def sent(out):
            if out:self.pc2_sense_sent=time.time();self.pc2_status.setText('Sentidos deste PC: enviados às '+time.strftime('%H:%M:%S')+
                ' (janela ativa, apps abertos, mídia, tempo parado, carga).')
        self.request('control/pc2/sentidos',{'estado':estado},callback=sent,quiet=True,silent=True)
    def pc2_poll_commands(self):
        if self.closing or not self.connected or not self.remote_panel() or self.pc2_command is not None:return
        if self.pc2_poll_sent is not None and time.monotonic()-self.pc2_poll_sent<15:return
        self.pc2_poll_sent=time.monotonic()
        def got(out):
            self.pc2_poll_sent=None
            command=(out or {}).get('comando')
            if not command:return
            if command.get('tipo')=='tela':
                if self.pc2_screen.isChecked():self.pc2_send_screen(command)
            elif self.pc2_allow.isChecked():self.pc2_run_command(command)
        self.request('control/pc2/proximo',{'permitido':self.pc2_allow.isChecked(),'permitido_tela':self.pc2_screen.isChecked()},
                     callback=got,quiet=True,silent=True)
    def pc2_send_screen(self,command):
        # Print da tela onde está o mouse (Barrier/várias telas), reduzido a 1920 px; vai só para o PC1 analisar.
        from PyQt5.QtGui import QCursor
        screen=QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        image=screen.grabWindow(0).toImage() if screen else None
        if image is None or image.isNull():
            self.request('control/pc2/resultado',{'id':command['id'],'codigo':None,'saida':'','erro':'não consegui capturar a tela'},callback=lambda out:None,quiet=True,silent=True);return
        if image.width()>1920:image=image.scaledToWidth(1920,Qt.SmoothTransformation)
        buffer=QBuffer();buffer.open(QIODevice.WriteOnly);image.save(buffer,'PNG')
        self.request(self.query('control/pc2/tela',id=command['id']),bytes(buffer.data()),callback=lambda out:None,binary=True,quiet=True,silent=True)
        self.pc2_status.setText(str(command.get('entidade','?')).capitalize()+' viu a tela deste PC às '+time.strftime('%H:%M:%S')+'.')
    def pc2_run_command(self,command):
        process=QProcess(self);self.pc2_command=(command,process);process.setProcessChannelMode(QProcess.MergedChannels)
        process.setWorkingDirectory(str(Path.home()));timeout=max(1,min(int(command.get('timeout') or 30),300))
        timer=QTimer(process);timer.setSingleShot(True)
        def expired():
            if process.state()!=QProcess.NotRunning:process.kill();self.pc2_finish_command(command,None,bytes(process.readAll()).decode('utf-8','replace'),f'tempo esgotado ({timeout} s); processo encerrado')
        def finished(code,status):
            timer.stop()
            if self.pc2_command and self.pc2_command[0] is command:
                crashed=status!=QProcess.NormalExit
                self.pc2_finish_command(command,None if crashed else int(code),bytes(process.readAll()).decode('utf-8','replace'),'processo interrompido' if crashed else None)
        timer.timeout.connect(expired);process.finished.connect(finished)
        process.start('/bin/bash',['-lc',command['comando']]);timer.start(timeout*1000)
        self.pc2_status.setText('Executando comando de '+str(command.get('entidade','?')).capitalize()+': '+command['comando'][:80])
    def pc2_finish_command(self,command,code,output,error):
        if not self.pc2_command or self.pc2_command[0] is not command:return
        self.pc2_command=None
        data={'id':command['id'],'codigo':code,'saida':(output or '')[-64*1024:]}
        if error:data['erro']=error
        self.request('control/pc2/resultado',data,callback=lambda out:None,quiet=True,silent=True)
        self.pc2_status.setText('Último comando ('+time.strftime('%H:%M:%S')+'): '+command['comando'][:60]+(' · saída '+str(code) if code is not None else ' · '+str(error)))
    def render_vram(self,out):
        self.vram_state=out
        if not out:self.vram_box.hide();return
        self.vram_box.show();self.vram_margin.blockSignals(True);self.vram_margin.clear()
        for m in out.get('options',[]):
            note=' (padrão)' if m==out.get('default_mib') else ' (piso; só com o desktop leve)' if m==out.get('minimum_mib') else ''
            self.vram_margin.addItem(f'{m} MiB{note}',m)
        self.vram_margin.setCurrentIndex(max(0,self.vram_margin.findData(out.get('margin_mib'))));self.vram_margin.blockSignals(False)
        self.vram_preview()
    def vram_preview(self,*_):
        out=self.vram_state or {};chosen=self.vram_margin.currentData()
        if not out or chosen is None:return
        total,used=out.get('total_mib'),out.get('used_mib')
        lines=[]
        if total:
            usable=min(total,8192)-chosen
            lines.append(f'Placa: {total:,} MiB · em uso agora: {used:,} MiB · com esta margem a placa pode ficar ocupada até {usable:,} MiB no total (sistema + modelos).'.replace(',','.'))
        if chosen!=out.get('margin_mib'):lines.append(f"Atual: {out.get('margin_mib')} MiB. Salvar vale no próximo pedido de GPU; entidade acordada usa o piso novo depois de dormir e acordar.")
        if chosen<512:lines.append('Abaixo de 512 MiB: use só com o desktop leve e sem outros apps na GPU. A estimativa do 9B em 33 camadas fica uns 350 MiB abaixo do real; a margem é o que cobre esse erro.')
        self.vram_info.setText('\n'.join(lines))
    def save_vram(self):
        if not self.vram_state:self.notice.setText('Configuração de VRAM ainda não carregou.');return
        data={'margin_mib':self.vram_margin.currentData(),'revision':self.vram_state.get('revision')}
        def saved(out):
            if out:self.render_vram(out);self.notice.setText(f"Margem de VRAM salva: {out.get('margin_mib')} MiB livres na placa.")
        self.request('control/vram',data,callback=saved)
    def render_lan(self,out):
        # No PC2 o backend recusa (403): a seção fica escondida.
        self.lan_state=out
        if not out:self.lan_box.hide();return
        self.lan_box.show();self.lan_enabled.setChecked(out.get('enabled') is True)
        address=(out.get('addresses') or ['IP-DO-PC1'])[0]
        lines=[('Ligado' if out.get('enabled') else 'Desligado')+(f" · porta {out.get('active_port')} aberta agora" if out.get('active') else (' · a porta não abriu (veja Diagnóstico)' if out.get('enabled') else ''))]
        if out.get('enabled') and out.get('code'):
            lines.append(f"Endereço: http://{address}:{out.get('port')}  ·  Código: {out['code']}")
            lines.append(self.lan_command())
            try:net=str(ipaddress.ip_network(address+'/24',strict=False))
            except ValueError:net='10.0.0.0/24'
            lines.append(f"Se o firewall (ufw) estiver ligado: sudo ufw allow from {net} to any port {out.get('port')} proto tcp")
        bridge=out.get('ponte_audio') or {}
        if out.get('enabled'):
            parts=[]
            if 'som' in bridge:parts.append(f"o PC2 ({bridge['som']['cliente']}) está ouvindo o som daqui há {bridge['som']['segundos']//60} min")
            if 'microfone' in bridge:parts.append(f"o microfone do PC2 está chegando em voz_do_pc2 há {bridge['microfone']['segundos']//60} min")
            lines.append('Ponte de áudio (sem SonoBus): '+('; '.join(parts) if parts else 'nenhum painel do PC2 conectado agora')+'.')
        self.lan_info.setText('\n'.join(lines))
    def lan_command(self):
        out=self.lan_state or {};address=(out.get('addresses') or ['IP-DO-PC1'])[0]
        return ('No PC2: git clone https://github.com/atominen/hoshino-e-lilith.git ~/hoshino-e-lilith-painel && '
                f"bash ~/hoshino-e-lilith-painel/scripts/instalar_painel_pc2.sh {address} {out.get('code','CODIGO')}")
    def copy_lan_command(self):
        if not (self.lan_state or {}).get('code'):self.notice.setText('Ligue e salve o acesso pela rede antes de copiar o comando.');return
        text=self.lan_command().removeprefix('No PC2: ')
        self.clipboard_last=hashlib.sha256(text.encode()).hexdigest()  # o código não vai para a área compartilhada
        QApplication.clipboard().setText(text);self.notice.setText('Comando do PC2 copiado (não foi guardado na área compartilhada).')
    def save_lan(self,regenerate):
        data={'enabled':self.lan_enabled.isChecked()}
        if regenerate:data['regenerate']=True
        def saved(out):
            if out:self.render_lan(out);self.notice.setText('Acesso pela rede salvo e aplicado agora'+(' · código novo: o PC2 precisa do novo comando.' if regenerate else '.'))
        self.request('control/rede',data,callback=saved)
    def save_interface(self):
        if self.ui_config:
            styles={entity:dict(mode='image' if mode.currentIndex() else 'energy',base_color=color.text(),image_path=picture.text(),mood_tint=mood.isChecked()) for entity,(mode,color,picture,mood) in self.orb_controls.items()}
            self.request('control/interface',{'revision':self.ui_config['revision'],'settings':{'overlay_enabled':self.overlay_enabled.isChecked(),'always_on_top':self.topmost.isChecked(),'balloons':self.balloons.isChecked(),'silent':self.silent.isChecked(),'balloon_seconds':self.balloon_seconds.value(),'reduced_motion':self.reduced_motion.isChecked(),'orb_styles':styles,'clipboard_import':self.clipboard_import.isChecked(),'clipboard_auto':self.clipboard_auto.isChecked(),'timeline_page_size':self.timeline_page_size.currentData()}},callback=lambda o:self.interface_saved(o))
    def stop_page_animation(self,*_):
        self.page_animation.stop();self.page_effect.setEnabled(False)
    def interface_saved(self,out):
        if out:self.ui_config=None;self.load_interface();self.notice.setText('Preferências salvas. Fechar a Central pede confirmação para encerrar o projeto; fechar só os orbes não encerra entidades.')
    def closeEvent(self,event):
        event.ignore()
        if self.closing or self.shutdown_pending:return
        if self.ui_only_smoke:self.finish_window_only();return
        # 07/11 (pedido humano): fechar o painel do PC2 fecha também a Central do PC1, com a opção de fechar só esta janela.
        if self.remote_panel():self.close_remote_panel();return
        if QMessageBox.question(self,'Fechar o projeto',
                'Encerrar a Central, os orbes e Hoshino, Lilith e Alistair?\n'
                'O projeto aguardará o encerramento seguro dos trabalhos. Memórias e arquivos salvos serão preservados.\n'
                'Áudio e rascunhos ainda não enviados serão descartados. Trabalhos incertos podem impedir a saída.\n'
                'O computador e outros programas não serão desligados.',
                QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        if self.memory_access:self.lock_memories()
        self.stop_hotkey();self.stop_capture(False);self.stop_voice();self.asr_waiting.clear()
        for identifier in list(self.asr_jobs):
            if identifier!='pending':self.request('audio/cancel',{'id':identifier},quiet=True)
        self.asr_jobs.clear();self.report_focus(True)
        self.shutdown_pending=True;self.shutdown_generation=hashlib.sha256(self.token.encode()).hexdigest();self.shutdown_requested_at=time.time()
        for timer in (self.state_timer,self.audio_timer,self.detail_timer,self.focus_timer,self.chat_stream_timer):timer.stop()
        self.centralWidget().setEnabled(False);self.notice.setText('Encerrando com segurança… A janela fechará após confirmação.');self.shutdown_timer.start()
        def accepted(out):
            if out is None and getattr(self,'refused_since',None):
                # 07/11: a Central já tinha sido encerrada (pelo PC2); não há recibo novo a esperar.
                self.notice.setText('A Central já estava fechada; esta janela fecha agora.')
                QTimer.singleShot(500,self.finish_window_only);return
            if out is None:self.notice.setText('Pedido de encerramento não confirmado. Verificando o recibo, sem repetir o pedido…')
        self.request('control/shutdown',{'confirm':True},callback=accepted)
    def poll_shutdown(self):
        if not self.shutdown_pending:return
        try:
            if hashlib.sha256(endpoint(self.root)[1].encode()).hexdigest()!=self.shutdown_generation:
                self.shutdown_failed('A Central mudou durante o encerramento. Não vou fechar outra instância sem confirmação.');return
        except (OSError,ValueError):pass
        path=self.root/'compartilhado/runtime/launcher/shutdown-result.json'
        try:
            if path.is_symlink() or path.stat().st_size>1024**2:raise ValueError('Recibo inválido')
            receipt=json.loads(path.read_text())
            valid=receipt.get('generation')==self.shutdown_generation and receipt.get('at',0)>=self.shutdown_requested_at-1
            if valid and receipt.get('status')=='blocked':self.shutdown_failed('Um trabalho ainda está ativo ou incerto. Consulte Diagnóstico; nada foi morto à força.');return
            if valid and receipt.get('status')=='complete':
                if type(receipt.get('pid')) is not int or receipt['pid']<=0 or not isinstance(receipt.get('process_stamp'),str) or not receipt['process_stamp']:raise ValueError('Posse do processo não confirmada')
                try:
                    fields=Path('/proc/'+str(int(receipt['pid']))+'/stat').read_text().rsplit(')',1)[1].split()
                    running=fields[0] not in ('Z','X') and fields[19]==receipt.get('process_stamp')
                except (OSError,ValueError,KeyError,IndexError):running=False
                if not running:self.shutdown_timer.stop();self.finish_window_only();return
        except (OSError,ValueError,TypeError):pass
        if time.time()-self.shutdown_requested_at>70:self.shutdown_failed('Não foi possível confirmar o encerramento completo. A janela permanece aberta para diagnóstico; nenhum pedido foi repetido.')
    def shutdown_failed(self,message):
        self.shutdown_timer.stop();self.shutdown_pending=False;self.centralWidget().setEnabled(True);self.notice.setText(message);self.state_timer.start();self.chat_stream_timer.start()
        QMessageBox.warning(self,'Encerramento não concluído',message)
    def ask_remote_close(self):
        box=QMessageBox(self);box.setWindowTitle('Fechar');box.setIcon(QMessageBox.Question)
        box.setText('Fechar a Central do PC1 também?')
        box.setInformativeText('“Fechar tudo” encerra com segurança a Central do PC1 e Hoshino, Lilith e Alistair, como o botão '
                               'de fechar de lá. “Fechar só esta janela” deixa o PC1 e as entidades funcionando.')
        tudo=box.addButton('Fechar tudo',QMessageBox.AcceptRole);so=box.addButton('Fechar só esta janela',QMessageBox.DestructiveRole)
        box.addButton('Cancelar',QMessageBox.RejectRole);box.setDefaultButton(tudo);box.exec_()
        return 'tudo' if box.clickedButton() is tudo else 'so' if box.clickedButton() is so else None
    def close_remote_panel(self):
        choice=self.ask_remote_close()
        if choice=='so':self.finish_window_only();return
        if choice!='tudo':return
        self.remote_shutdown_at=time.time();self.centralWidget().setEnabled(False)
        self.notice.setText('Pedindo à Central do PC1 que encerre com segurança… esta janela fecha junto.')
        def accepted(out):
            if out is None:
                self.remote_shutdown_at=None;self.centralWidget().setEnabled(True)
                self.notice.setText('A Central do PC1 não confirmou o encerramento. Nada foi fechado.')
        self.request('control/shutdown',{'confirm':True},callback=accepted)
    def close_with_central(self,why):
        if self.closing:return
        self.notice.setText(why);QTimer.singleShot(800,self.finish_window_only)
    def track_remote_central(self,out):
        """Porta da Central recusando por 10 s (ou logo após pedir o encerramento) = Central fechada; a janela fecha junto.
        07/11: vale no PC1 também. Fechada pelo painel do PC2, a janela do PC1 ficava aberta e depois não fechava mais."""
        if not isinstance(out,dict) or self.closing:return
        if not out.get('refused'):self.refused_since=None;return
        now=time.monotonic();self.refused_since=getattr(self,'refused_since',None) or now
        if self.shutdown_pending:return  # o próprio encerramento confere o recibo
        if getattr(self,'remote_shutdown_at',None) or now-self.refused_since>=10:
            self.close_with_central('A Central foi fechada; esta janela fecha junto.')
    def finish_window_only(self):
        """Local cleanup after verified shutdown, or explicit offline UI smoke."""
        self.shutdown_timer.stop()
        self.stop_page_animation()
        self.volume_timer.stop()
        self.stop_hotkey()
        self.stop_capture(False);self.stop_voice();self.report_focus(True)
        if getattr(self,'pc2_bridge',None) is not None:self.pc2_bridge_timer.stop();self.pc2_bridge.parar()
        for identifier in list(self.asr_jobs):
            if identifier!='pending':self.request('audio/cancel',{'id':identifier},quiet=True)
        self.closing=True;self.asr_waiting.clear();self.state_timer.stop();self.audio_timer.stop();self.detail_timer.stop();self.focus_timer.stop();self.chat_stream_timer.stop();self.hide()
        def wait():
            if self.workers or any(p.state()!=QProcess.NotRunning for p in self.findChildren(QProcess)):QTimer.singleShot(100,wait)
            else:self.temp.cleanup();QApplication.instance().quit()
        wait()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--entity',choices=ENTITIES,default='hoshino');parser.add_argument('--verify',action='store_true');parser.add_argument('--smoke-seconds',type=float);parser.add_argument('--snapshot',type=Path);parser.add_argument('--smoke-page',choices=PAGES);parser.add_argument('--smoke-audio-tab',type=int,choices=(0,1),default=0);args=parser.parse_args()
    if args.verify:print('QtWidgets nativo disponível; sem navegador/captura/backend iniciado.');return 0
    if args.smoke_seconds is not None and not 1<=args.smoke_seconds<=30:raise ValueError('Ensaio de UI entre 1 e 30 segundos.')
    app=QApplication(['hoshino-e-lilith','-name','hoshino-e-lilith']);app.setQuitOnLastWindowClosed(False);app.setApplicationName('hoshino-e-lilith')
    app.setApplicationDisplayName('Central');app.setDesktopFileName('hoshino-e-lilith');app.setWindowIcon(QIcon(str(args.root/'desktop/hoshino-e-lilith.svg')))
    socket_path=str(args.root/'compartilhado/runtime/launcher/native-ui.sock');socket=QLocalSocket();socket.connectToServer(socket_path)
    if socket.waitForConnected(250):socket.write(json.dumps({'entity':args.entity}).encode());socket.waitForBytesWritten(300);socket.disconnectFromServer();return 0
    lock_path=args.root/'compartilhado/runtime/launcher/native-ui.lock';lock_path.parent.mkdir(parents=True,exist_ok=True)
    lock=lock_path.open('a+')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Janela existente ainda iniciando; nenhum backend novo iniciado.');return 0
    server=QLocalServer();server.setSocketOptions(QLocalServer.UserAccessOption);QLocalServer.removeServer(socket_path)
    if not server.listen(socket_path):raise ValueError('Não foi possível registrar janela nativa.')
    app.setStyleSheet(STYLE)
    window=Central(args.root,args.entity);window.show()
    window.ui_only_smoke=args.smoke_seconds is not None
    if args.smoke_seconds is not None:window.setWindowTitle('SIMULAÇÃO OFFLINE · central nativa');window.pages['Áudio'].insertWidget(1,QLabel('SIMULAÇÃO OFFLINE · sem microfone, alto-falante ou ElevenLabs real.'))
    if args.smoke_page:window.nav.setCurrentRow(PAGES.index(args.smoke_page))
    if args.smoke_seconds is not None:window.audio_tabs.setCurrentIndex(args.smoke_audio_tab)
    def opened():
        connection=server.nextPendingConnection()
        def read():
            try:
                data=json.loads(bytes(connection.readAll()));e=data.get('entity','hoshino')
                if e in ENTITIES:window.focus_entity(e)
            except (ValueError,TypeError):pass
            connection.disconnectFromServer()
        connection.readyRead.connect(read);connection.disconnected.connect(connection.deleteLater)
    server.newConnection.connect(opened)
    if args.snapshot:QTimer.singleShot(900,lambda:window.grab().save(str(args.snapshot)))
    if args.smoke_seconds is not None:QTimer.singleShot(int(args.smoke_seconds*1000),window.close)
    import resource
    started=time.monotonic();before=resource.getrusage(resource.RUSAGE_SELF);result=app.exec_();server.close();QLocalServer.removeServer(socket_path)
    if args.smoke_seconds:
        after=resource.getrusage(resource.RUSAGE_SELF);elapsed=time.monotonic()-started;cpu=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
        print('NATIVE_UI_METRICS '+json.dumps({'ui_only':True,'elapsed_seconds':round(elapsed,3),'cpu_seconds':round(cpu,3),'cpu_percent_one_core':round(100*cpu/elapsed,2),'peak_rss_kib':after.ru_maxrss,'no_browser':True,'backend_shutdown_sent':False}))
    return result


if __name__=='__main__':raise SystemExit(main())
