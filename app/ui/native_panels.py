"""Projeções visuais dos endpoints existentes; histórico efêmero e limitado."""
import json
import math
import re
from datetime import datetime
from collections import deque
from PyQt5.QtCore import Qt, QPointF, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QGroupBox,QTreeWidget,QTreeWidgetItem,QLineEdit,QPlainTextEdit,QCheckBox,QPushButton,QDialog,QTextBrowser,QDialogButtonBox,QFormLayout,QMessageBox,QInputDialog,QGraphicsDropShadowEffect
from native_controls import QTabWidget,QComboBox,QDoubleSpinBox
import html

GIB=1024**3
TIERS=(('Bronze','bronze','#c98a5b'),('Ferro','ferro','#91a0af'),('Ouro','ouro','#e8bd62'),('Diamante','diamante','#82d8f7'))


class MemoryCard(QGroupBox):
    """Realce curto por hover/foco; sem loop, IA, bitmap ou mudança de layout."""
    def __init__(self,title,tier='ferro',motion_enabled=None):
        super().__init__(title);self.setObjectName('memoryCard');self.setFocusPolicy(Qt.StrongFocus)
        self.motion_enabled=motion_enabled or (lambda:True);self._hover=0.
        color=next((color for _,key,color in TIERS if key==tier),TIERS[0][2])
        self.setProperty('importance',tier)
        self.setStyleSheet('QGroupBox#memoryCard{border:1px solid '+color+';border-radius:13px;margin-top:12px;padding:14px;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #242a3c,stop:1 #191e2c);} QGroupBox#memoryCard::title{subcontrol-origin:margin;left:14px;padding:0 6px;color:'+color+';}')
        self.shadow=QGraphicsDropShadowEffect(self);self.shadow.setColor(QColor(color));self.setGraphicsEffect(self.shadow);self.hoverProgress=0
        self.hover_animation=QPropertyAnimation(self,b'hoverProgress',self);self.hover_animation.setDuration(160);self.hover_animation.setEasingCurve(QEasingCurve.OutCubic)
    def _get_hover(self):return self._hover
    def _set_hover(self,value):
        self._hover=float(value);self.shadow.setBlurRadius(5+13*self._hover);self.shadow.setOffset(0,1+2*self._hover)
    hoverProgress=pyqtProperty(float,fget=_get_hover,fset=_set_hover)
    def highlight(self,active):
        self.hover_animation.stop()
        if not self.motion_enabled():self.hoverProgress=0;return
        self.hover_animation.setStartValue(self.hoverProgress);self.hover_animation.setEndValue(1. if active else 0.);self.hover_animation.start()
    def enterEvent(self,event):self.highlight(True);super().enterEvent(event)
    def leaveEvent(self,event):self.highlight(self.hasFocus());super().leaveEvent(event)
    def focusInEvent(self,event):self.highlight(True);super().focusInEvent(event)
    def focusOutEvent(self,event):self.highlight(self.underMouse());super().focusOutEvent(event)


class KnowledgePanel(QWidget):
    """Cards are views of existing records, never a parallel knowledge store."""
    KINDS=(('Pessoas','person'),('Itens / assuntos','item'),('Conceitos','concept'),('Estados','state'),('Estruturas','structure'),('Modos','mode'),('Regras aprendidas','rule'),('Manuais','manual'),('Relações / amizades','relation'),('Como fazer','procedure'))
    def __init__(self,reload,edit=None,motion_enabled=None):
        super().__init__();self.reload=reload;self.edit=edit;self.motion_enabled=motion_enabled;self.page=0;self.entity=None;self.cards=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);row=QHBoxLayout();layout.addLayout(row)
        self.search=QLineEdit();self.search.setPlaceholderText('Pessoa, objeto, conceito ou informação…');self.search.setMaxLength(200);row.addWidget(self.search,1)
        self.kind=QComboBox()
        for title,key in [('Tudo',''),*self.KINDS]:self.kind.addItem(title,key)
        row.addWidget(self.kind);button=QPushButton('Buscar / atualizar');row.addWidget(button)
        create=QPushButton('Novo cartão');row.addWidget(create);create.setEnabled(edit is not None);create.clicked.connect(self.create)
        button.clicked.connect(self.reset);self.search.returnPressed.connect(self.reset);self.kind.currentIndexChanged.connect(self.reset)
        self.summary=QLabel('Conhecimento próprio da entidade selecionada.');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        importance_hint=QLabel('Importância: Bronze → Ferro → Ouro → Diamante. Bronze guarda sozinho o que a pessoa disse, mesmo passageiro. Define organização e destaque, não confiança/veracidade. Todos podem ser apagados explicitamente.');importance_hint.setWordWrap(True);importance_hint.setObjectName('subtitle');layout.addWidget(importance_hint)
        self.grid=QGridLayout();self.grid.setSpacing(16);self.grid.setContentsMargins(8,4,8,10);self.grid.setAlignment(Qt.AlignTop);layout.addLayout(self.grid)
        pages=QHBoxLayout();layout.addLayout(pages);self.previous=QPushButton('Anterior');self.next=QPushButton('Próxima')
        pages.addWidget(self.previous);pages.addStretch();pages.addWidget(self.next)
        self.previous.clicked.connect(lambda:self.move(-1));self.next.clicked.connect(lambda:self.move(1))
        self.previous.setEnabled(False);self.next.setEnabled(False);layout.addStretch()
    def reset(self,*_):self.page=0;self.reload()
    def move(self,direction):self.page=max(0,self.page+direction);self.reload()
    def clear(self):
        self.cards=[]
        while self.grid.count():
            widget=self.grid.takeAt(0).widget()
            if widget:widget.deleteLater()
        self.previous.setEnabled(False);self.next.setEnabled(False)
    def render(self,out):
        self.clear()
        if not isinstance(out,dict) or out.get('entity') not in ('hoshino','lilith','alistair'):self.summary.setText('Conhecimento indisponível. Nenhuma informação foi inventada.');return
        self.entity=out['entity'];self.cards=out.get('items',[])
        self.summary.setText(self.entity.capitalize()+f" · {out.get('total',0)} cartões na consulta · página {self.page+1}\n"+out.get('note',''))
        for index,card in enumerate(self.cards):
            importance=card.get('importance','ferro');group=MemoryCard(card['title'],importance,self.motion_enabled);group.setMinimumWidth(220);box=QVBoxLayout(group)
            tier_row=QHBoxLayout();box.addLayout(tier_row);badge=QLabel('◆ '+importance.capitalize());badge.setAccessibleName('Importância '+importance);tier_row.addWidget(badge)
            if self.edit and card.get('card_revision'):
                level=QComboBox();level.setAccessibleName('Importância de '+card['title'])
                for title,key,_ in TIERS:level.addItem(title,key)
                level.setCurrentIndex(max(0,level.findData(importance)));tier_row.addWidget(level)
                apply=QPushButton('Aplicar');apply.clicked.connect(lambda _,c=card,l=level,b=apply:self.set_importance(c,l,b));tier_row.addWidget(apply)
            category=dict((key,title) for title,key in self.KINDS).get(card['kind'],card['kind'])
            hint=QLabel(category+' · '+str(len(card['entries']))+' registros');hint.setObjectName('subtitle');box.addWidget(hint)
            for item in card['entries'][:3]:
                text=(item.get('label')+': ' if item.get('label') else '')+item['text']
                label=QLabel(text[:180]+('…' if len(text)>180 else ''));label.setTextFormat(Qt.PlainText);label.setWordWrap(True);box.addWidget(label)
            more=QPushButton('Ver informações e fontes');more.clicked.connect(lambda _,c=card:self.details(c));box.addWidget(more)
            if self.edit:
                controls=QHBoxLayout();box.addLayout(controls)
                change=QPushButton('Editar');change.clicked.connect(lambda _,c=card:self.editor(c));controls.addWidget(change)
                remove=QPushButton('Apagar cartão');remove.clicked.connect(lambda _,c=card:self.remove(c));controls.addWidget(remove)
            self.grid.addWidget(group,index//2,index%2)
        if not self.cards:
            empty=QLabel('Ainda não há conhecimento estruturado nesta consulta. Histórico de conversa não é convertido em fatos automaticamente.');empty.setWordWrap(True);self.grid.addWidget(empty,0,0,1,2)
        self.previous.setEnabled(self.page>0);self.next.setEnabled(bool(out.get('has_more')))
    def set_importance(self,card,level,button):
        value=level.currentData()
        if value==card.get('importance','ferro'):return
        button.setEnabled(False)
        def done(out):
            button.setEnabled(True)
            if out and out.get('verified') is True:self.reload()
        self.edit(dict(action='importance',card_id=card['id'],card_revision=card['card_revision'],importance=value),done)
    def details(self,card):
        dialog=QDialog(self);dialog.setWindowTitle(card['title']);dialog.resize(650,520);layout=QVBoxLayout(dialog);view=QTextBrowser();layout.addWidget(view)
        parts=['<h2>'+html.escape(card['title'])+'</h2><p>Conhecimento de '+html.escape(card['entity'].capitalize())+' · registros não são confirmação externa.</p>']
        for item in card['entries']:
            confidence=item.get('confidence');confidence='não registrada' if confidence is None else f'{confidence:.0%}'
            parts+=['<h3>'+html.escape(item.get('label') or item['type'])+'</h3>', '<p>'+html.escape(item['text']).replace('\n','<br>')+'</p>',
                    '<p>Tipo: '+html.escape(item['type'])+' · Confiança: '+confidence+'<br>Fonte: '+html.escape(item.get('source',''))+
                    '<br>Registro: '+html.escape(str(item.get('record_id')))+' · '+html.escape(str(item.get('created_at') or 'data não registrada'))+'</p>']
            if item.get('subject_resolution')=='name_only':parts.append('<p>Referência legada por nome; identidade do sujeito não confirmada por ID.</p>')
            if item.get('evidence'):parts.append('<pre>'+html.escape(json.dumps(item['evidence'],ensure_ascii=False,indent=2))+'</pre>')
        view.setHtml(''.join(parts));buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec_()

    @staticmethod
    def records(card):
        return list({(e['table'],e['record_id']):e for e in card['entries']}.values())

    def submit(self,dialog,button,data):
        button.setEnabled(False)
        def done(out):
            button.setEnabled(True)
            if out and out.get('verified') is True:dialog.accept();self.reload()
            else:QMessageBox.warning(dialog,'Não confirmado','Não foi alterado/confirmado. Consulte o aviso da Central. Coloque a entidade para dormir e atualize o cartão antes de tentar outra edição; não repita uma operação incerta.')
        self.edit(data,done)

    def create(self):
        if not self.entity or not self.edit:return
        dialog=QDialog(self);dialog.setWindowTitle('Novo conhecimento · '+self.entity.capitalize());dialog.resize(550,400)
        layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form)
        title=QLineEdit();title.setMaxLength(120);kind=QComboBox()
        for label,key in self.KINDS:kind.addItem(label,key)
        content=QPlainTextEdit();form.addRow('Título / nome',title);form.addRow('Categoria',kind);layout.addWidget(content)
        note=QLabel('Informação fornecida por você. Não altera identidade, permissões ou regras técnicas. Entidade deve estar dormindo; backup automático.');note.setWordWrap(True);layout.addWidget(note)
        save=QPushButton('Criar cartão');layout.addWidget(save)
        save.clicked.connect(lambda:self.submit(dialog,save,dict(action='create',title=title.text(),kind=kind.currentData(),content=content.toPlainText())))
        dialog.exec_()

    def editor(self,card):
        records=self.records(card)
        if not records:return
        dialog=QDialog(self);dialog.setWindowTitle('Editar · '+card['title']);dialog.resize(650,600)
        layout=QVBoxLayout(dialog);selector=QComboBox()
        for record in records:selector.addItem(record['table']+' · '+str(record['record_id']),record)
        layout.addWidget(QLabel('Cada registro tem versão e autoria próprias. Edite um de cada vez. Entidade deve estar dormindo.'))
        layout.addWidget(selector);form=QFormLayout();layout.addLayout(form);fields={}
        labels={'nome':'Nome / forma de chamar','apelidos':'Outros nomes (lista JSON)','papel':'Relação / papel','notas':'Observações','entity':'Assunto','chave':'Propriedade','valor':'Valor','unidade':'Unidade','content':'Conhecimento','type':'Tipo','passos':'Passos','objetivo':'Objetivo','precondicoes':'Condições','resultado_esperado':'Resultado esperado','confidence':'Confiança','confianca':'Confiança','familiaridade':'Familiaridade','afinidade':'Afinidade'}
        def populate(*_):
            while form.rowCount():form.removeRow(0)
            fields.clear()
            for key,value in selector.currentData().get('fields',{}).items():
                if key in {'confidence','confianca','familiaridade','afinidade'}:
                    widget=QDoubleSpinBox();widget.setRange(0,1);widget.setSingleStep(.05);widget.setValue(value if value is not None else 0)
                else:widget=QPlainTextEdit(str(value or ''));widget.setMaximumHeight(90)
                fields[key]=widget;form.addRow(labels.get(key,key),widget)
        selector.currentIndexChanged.connect(populate);populate()
        save=QPushButton('Salvar este registro com backup');layout.addWidget(save)
        def submit():
            record=selector.currentData();values={k:(w.value() if isinstance(w,QDoubleSpinBox) else w.toPlainText()) for k,w in fields.items()}
            values={k:v for k,v in values.items() if v!=record['fields'].get(k) and not (record['fields'].get(k) is None and v in ('',0))}
            self.submit(dialog,save,dict(action='update',records=[dict(table=record['table'],id=record['record_id'],revision=record['revision'],fields=values)]))
        save.clicked.connect(submit);dialog.exec_()

    def remove(self,card):
        if QMessageBox.question(self,'Apagar conhecimento','Apagar os registros deste cartão de '+card['entity'].capitalize()+'?\nRegistros compartilhados entre cartões também desaparecem desses cartões. O chat bruto não será apagado e pode voltar a informar esse assunto. Backup preservado.')!=QMessageBox.Yes:return
        password,ok=QInputDialog.getText(self,'Confirmar exclusão','Senha local de exclusão (a mesma da aba Memória):',QLineEdit.Password)
        if not ok:return
        records=[dict(table=r['table'],id=r['record_id'],revision=r['revision']) for r in self.records(card)]
        def done(out):
            if out and out.get('verified') is True:self.reload()
        self.edit(dict(action='delete',confirm=True,records=records,password=password,card_id=card['id'],card_revision=card.get('card_revision')),done)
EVENT_LABELS={'input.received':'Mensagem recebida','turn.started':'Turno iniciado','executor.selected':'Executor escolhido','gpu.waiting':'Aguardando GPU','gpu.queued':'Pedido na fila GPU','gpu.compute_acquired':'Processamento concedido','gpu.compute_released':'Processamento liberado','tool.receipt':'Recibo de ferramenta','tool.failed':'Ferramenta falhou','memory.committed':'Memória registrada','tts.synthesized':'Voz sintetizada','tts.provider_failed':'Falha do provedor de voz'}
def number(value):
    return float(value) if type(value) in (int,float) and math.isfinite(value) else None
def gib(value):
    return 'indisponível' if number(value) is None else f'{value/GIB:.2f} GiB'
def percent(used,total):
    return 100*used/total if number(used) is not None and number(total) is not None and total>0 else None

class Trend(QWidget):
    def __init__(self,color,parent=None):
        super().__init__(parent);self.samples=deque(maxlen=120);self.color=color;self.setMinimumHeight(66)
    def add(self,value):
        self.samples.append(number(value));self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);w,h=self.width(),self.height()
        p.setPen(QPen(QColor('#303b50'),1))
        for y in (8,h//2,h-8):p.drawLine(0,y,w,y)
        path=QPainterPath();active=False;n=len(self.samples)
        for i,value in enumerate(self.samples):
            if value is None:active=False;continue
            point=QPointF(i*(w-4)/max(1,n-1)+2,h-8-max(0,min(100,value))*(h-16)/100)
            if active:path.lineTo(point)
            else:path.moveTo(point);active=True
        p.setPen(QPen(QColor(self.color),2));p.drawPath(path)

class Metric(QGroupBox):
    def __init__(self,title,color):
        super().__init__(title);layout=QVBoxLayout(self);self.value=QLabel('—');self.value.setStyleSheet('font-size:23px;font-weight:600;color:'+color)
        self.detail=QLabel('Aguardando medição');self.detail.setWordWrap(True);self.trend=Trend(color)
        layout.addWidget(self.value);layout.addWidget(self.detail);layout.addWidget(self.trend)
    def set(self,pct,detail):
        self.value.setText('Indisponível' if pct is None else f'{pct:.1f}%');self.detail.setText(detail);self.trend.add(pct)

def hora_local(record_or_text):
    """06/11 (pedido humano): horário local e completo ("06/11 21:20:05") em vez de UTC/ISO cortado."""
    from datetime import datetime
    if isinstance(record_or_text, dict):
        text = (record_or_text.get('timestamp') or {}).get('local') or record_or_text.get('ts') or ''
    else:
        text = record_or_text or ''
    try:
        moment = datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    except ValueError:
        return str(text) or '—'
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    return moment.strftime('%d/%m %H:%M:%S')


def tree(headers):
    t=QTreeWidget();t.setHeaderLabels(headers);t.setRootIsDecorated(False);t.setAlternatingRowColors(True);t.setUniformRowHeights(True);t.setMinimumHeight(120);return t
def fill(t,rows):
    t.clear()
    for row in rows[:200]:t.addTopLevelItem(QTreeWidgetItem([str(x) if x is not None else '—' for x in row]))
    for i in range(t.columnCount()-1):t.resizeColumnToContents(i)

class ResourcesPanel(QWidget):
    def __init__(self):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);grid=QGridLayout();layout.addLayout(grid)
        self.metrics={}
        for i,(key,title,color) in enumerate((('cpu','CPU','#c6a3ed'),('ram','RAM','#91c9bb'),('vram','VRAM','#ebbf80'),('gpu','GPU · processamento','#94b8ef'))):
            card=Metric(title,color);grid.addWidget(card,i//2,i%2);self.metrics[key]=card
        self.summary=QLabel('');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.cache=QLabel('Cache de prompts RAM: teto ainda indisponível.');self.cache.setWordWrap(True);layout.addWidget(self.cache)
        self.profiles=QLabel('Perfis dinâmicos: sem decisão observada.');self.profiles.setWordWrap(True);layout.addWidget(self.profiles)
        tabs=QTabWidget();layout.addWidget(tabs)
        self.compute=tree(['Recurso','Entidade','Responsável','Tempo','Lease'])
        self.queue=tree(['Prioridade','Entidade','Responsável','Estado','Motivo / fallback'])
        self.resident=tree(['Modelo','Residência','VRAM','Reload'])
        for title,t in (('Compute em uso',self.compute),('Fila',self.queue),('Modelos residentes',self.resident)):tabs.addTab(t,title)
        note=QLabel('Tendências: últimas 120 consultas desta janela, somente enquanto esta aba estiver aberta. Lacunas = sem medição.');note.setWordWrap(True);note.setObjectName('subtitle');layout.addWidget(note)
    def render(self,out):
        if not isinstance(out,dict):
            for card in self.metrics.values():card.set(None,'Consulta indisponível')
            self.summary.setText('Sem resposta atual do backend; valores não confirmados.')
            self.cache.setText('Cache de prompts RAM: sem política atual; uso não medido.')
            self.profiles.setText('Perfis dinâmicos: sem resposta atual; estado não confirmado.')
            for table in (self.compute,self.queue,self.resident):table.clear()
            return
        gpu=out.get('gpu') or {};m=gpu.get('metrics') or {};p=gpu.get('policy') or {}
        total,available=out.get('ram_total'),out.get('ram_available');used=total-available if number(total) is not None and number(available) is not None else None
        self.metrics['cpu'].set(number(out.get('cpu_percent')),'Utilização total do processador')
        self.metrics['ram'].set(percent(used,total),gib(used)+' usada · '+gib(available)+' disponível')
        vram=m.get('used_bytes') if m.get('known') else None
        self.metrics['vram'].set(percent(vram,m.get('total_bytes')),gib(vram)+' / '+gib(m.get('total_bytes')))
        self.metrics['gpu'].set(number(m.get('utilization')),'Fonte: '+str(m.get('source','indisponível')))
        st,sf=out.get('swap_total'),out.get('swap_free');swap=st-sf if number(st) is not None and number(sf) is not None else None
        self.summary.setText('Swap usada: '+gib(swap)+' · Margem VRAM: '+gib(p.get('margin_bytes'))+' · Disco livre: '+gib(out.get('disk_free'))+'\nConcorrência GPU: '+('validada' if p.get('concurrency_validated') else 'conservadora / serializada')+' · Consulta '+datetime.now().strftime('%H:%M:%S'))
        cache=out.get('ram_prompt_cache') or {};caps=cache.get('per_entity_mib') or {}
        cap=lambda value:gib(value*1024**2) if number(value) is not None else 'indisponível'
        self.cache.setText('Cache de prompts RAM · teto combinado previsto: '+cap(cache.get('aggregate_mib'))+'\n'+
            ' · '.join(name.capitalize()+': '+cap(caps.get(name)) for name in ('hoshino','lilith','alistair'))+
            ('\nConfiguração inválida: cache desativado para o próximo boot.' if cache.get('valid') is False else '')+
            '\nPróximo boot gerenciado; aplicação no runner e uso real ainda não confirmados. Não é cache de pesos ou memória mental.')
        profiles=out.get('resource_profiles') or {};observed=profiles.get('observations') or {}
        self.profiles.setText('Perfis dinâmicos · última decisão por tarefa\n'+
            ' · '.join(p['label'] for p in profiles.get('available',[]))+'\n'+
            '\n'.join(name.capitalize()+': '+(p['label']+' · '+str(p.get('ts') or 'sem data')+
                (' · proteção contra trocas frequentes' if p.get('held') else '') if (p:=observed.get(name)) else
                'sem decisão observada') for name in ('hoshino','lilith','alistair'))+
            '\nHistórico limitado, não perfil ativo confirmado. Custos heurísticos; ganho de velocidade ainda não medido. Modelo fixo durante a resposta.')
        fill(self.compute,[(r.get('resource'),r.get('entity'),r.get('owner'),f"{r['lease_seconds']:.1f} s" if number(r.get('lease_seconds')) is not None else None,r.get('lease_id',r.get('token'))) for r in out.get('leases',[])])
        fill(self.queue,[(f"P{r.get('priority','?')}",r.get('request',{}).get('entity'),r.get('request',{}).get('owner'),r.get('state'),r.get('request',{}).get('reason',r.get('request',{}).get('fallback','—'))) for r in gpu.get('queue',[])])
        fill(self.resident,[(r.get('model'),r.get('state'),gib(r.get('vram_bytes')),f"{r['reload_seconds']:.1f} s" if number(r.get('reload_seconds')) is not None else None) for r in gpu.get('residency',[])])

class ActivityPanel(QWidget):
    def __init__(self,include_commands=True):
        super().__init__();self.events=[];layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.summary=QLabel('Nenhum evento consultado');layout.addWidget(self.summary)
        self.search=QLineEdit();self.search.setPlaceholderText('Filtrar por evento, entidade, turno, ferramenta, ID ou origem…');layout.addWidget(self.search)
        self.show_routine=QCheckBox('Mostrar checagens internas repetidas (decisões "nada" e avisos de VRAM)');layout.addWidget(self.show_routine)
        tabs=self.tabs=QTabWidget();layout.addWidget(tabs,1);events_page=QWidget();commands_page=QWidget();events_layout=QVBoxLayout(events_page);commands_layout=QVBoxLayout(commands_page);tabs.addTab(events_page,'Eventos recentes');tabs.addTab(commands_page,'Comandos e saída')
        if not include_commands:tabs.removeTab(1)
        self.timeline=tree(['Horário','Nível','Evento','Entidade','Turno']);events_layout.addWidget(self.timeline,2)
        self.show_details=QCheckBox('Detalhes técnicos do evento selecionado');events_layout.addWidget(self.show_details)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setPlaceholderText('Selecione um evento para ver evidências e IDs.');self.detail.setMaximumHeight(150);self.detail.hide();events_layout.addWidget(self.detail);self.show_details.toggled.connect(self.detail.setVisible)
        self.commands=tree(['Onde','Comando','Estado','Início','Código']);commands_layout.addWidget(self.commands)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setPlaceholderText('Selecione um comando: saída já filtrada pelo backend, stdout/stderr combinados.');commands_layout.addWidget(self.output,1)
        self.search.textChanged.connect(self.filter);self.timeline.itemSelectionChanged.connect(self.selected);self.commands.itemSelectionChanged.connect(self.command_selected)
    def render(self,out):
        if not isinstance(out,dict):self.summary.setText('Consulta indisponível · eventos anteriores não foram atualizados.');return
        self.events=out.get('items',[])[:200];self.filter()
    def filter(self):
        selected=self.timeline.selectedItems();key=selected[0].data(0,Qt.UserRole).get('id') if selected else None
        self.timeline.clear();query=self.search.text().casefold();errors=sum(e.get('level')=='ERROR' for e in self.events)
        for e in self.events:
            if query and query not in json.dumps(e,ensure_ascii=False).casefold():continue
            item=QTreeWidgetItem([hora_local(e)]+[str(e.get(k) or '—') for k in ('level','event','entity','turn_id')]);item.setData(0,Qt.UserRole,e)
            item.setToolTip(0,str(e.get('ts','')))
            item.setText(2,EVENT_LABELS.get(e.get('event'),str(e.get('event','—'))));item.setToolTip(2,str(e.get('event','')))
            item.setForeground(1,QColor('#f2a5ad' if e.get('level')=='ERROR' else '#ebbf80' if e.get('level')=='WARN' else '#91c9bb'))
            self.timeline.addTopLevelItem(item)
            if key is not None and e.get('id')==key:item.setSelected(True)
        self.summary.setText(f'{self.timeline.topLevelItemCount()} eventos exibidos · {errors} eventos de erro · '
                             +('checagens repetidas visíveis' if self.show_routine.isChecked() else 'checagens repetidas escondidas')
                             +' · sem ordem causal global garantida')
        self.selected()
        for i in (0,1,2,3):self.timeline.resizeColumnToContents(i)
    def selected(self):
        items=self.timeline.selectedItems();e=items[0].data(0,Qt.UserRole) if items else None
        self.detail.setPlainText(json.dumps(e,ensure_ascii=False,indent=2) if e else '')
    def render_commands(self,out):
        if not isinstance(out,dict):return
        selected=self.commands.selectedItems();key=selected[0].data(0,Qt.UserRole).get('id') if selected else None
        self.commands.clear()
        for r in out.get('items',[])[:30]:
            item=QTreeWidgetItem([str(r.get('onde') or 'PC1'),str(r.get('comando') or '—')[:160],str(r.get('status') or '—'),
                                  hora_local(r.get('inicio')) if r.get('inicio') else '—',str(r.get('codigo')) if r.get('codigo') is not None else '—'])
            item.setToolTip(1,str(r.get('comando') or ''));item.setData(0,Qt.UserRole,r);self.commands.addTopLevelItem(item)
            if key is not None and key==r.get('id'):item.setSelected(True)
        self.command_selected()
        for i in (0,2,3,4):self.commands.resizeColumnToContents(i)
    def command_selected(self):
        rows=self.commands.selectedItems();self.output.setPlainText(str(rows[0].data(0,Qt.UserRole).get('output','')) if rows else '')

class HistoryTimelinePanel(QWidget):
    """Consulta explícita do histórico persistido de uma entidade."""
    def __init__(self, request, open_attachment):
        super().__init__()
        self.request = request
        self.open_attachment = open_attachment
        self.entity = ''
        self.offset = 0
        self.next_offset = None
        self.filters = {}
        self.generation = 0
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.day = QLineEdit()
        self.day.setPlaceholderText('AAAA-MM-DD · em branco para todos os dias')
        self.search = QLineEdit()
        self.search.setMaxLength(200)
        self.channel = QLineEdit()
        self.channel.setPlaceholderText('Opcional · ex.: localhub, discord, tui')
        self.kind = QComboBox()
        for label, value in [('Mensagens e eventos', ''), ('Só mensagens', 'message'), ('Só eventos', 'event')]:
            self.kind.addItem(label, value)
        self.level = QComboBox()
        self.level.addItem('Todos os níveis', '')
        for value in ('INFO', 'WARN', 'ERROR', 'DEBUG'):
            self.level.addItem(value, value)
        self.routine = QCheckBox('Mostrar checagens internas repetidas (decisões "nada" e avisos de VRAM)')
        for label, control in [('Data', self.day), ('Busca', self.search), ('Canal (mensagens)', self.channel),
                               ('Tipo', self.kind), ('Nível (eventos)', self.level), ('', self.routine)]:
            form.addRow(label, control)
        layout.addLayout(form)
        row = QHBoxLayout()
        for label, action in [('Pesquisar', self.search_first), ('Página anterior', self.previous), ('Próxima página', self.next_page)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.rows = tree(['Horário', 'Tipo', 'Autor / componente', 'Mensagem / evento'])
        layout.addWidget(self.rows, 2)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText('Selecione um registro para ver seu conteúdo e observações.')
        layout.addWidget(self.detail, 1)
        self.preview = QPushButton('Abrir conteúdo copiado')
        self.preview.setEnabled(False)
        self.preview.clicked.connect(self.preview_selected)
        layout.addWidget(self.preview)
        self.rows.itemSelectionChanged.connect(self.selected)
        self.search.returnPressed.connect(self.search_first)

    def set_entity(self, entity):
        if entity != self.entity:
            self.entity = entity
            self.generation += 1
            self.rows.clear()
            self.selected()
            self.filters = {}
            self.offset = 0
            self.next_offset = None
            self.status.setText('Histórico persistido de ' + entity.capitalize() + '. Clique em Pesquisar.'
                                if entity else 'Selecione uma entidade para consultar o histórico.')

    def search_first(self):
        self.filters = dict(day=self.day.text().strip(), q=self.search.text().strip(),
                            channel=self.channel.text().strip(), kind=self.kind.currentData(),
                            level=self.level.currentData(), rotina='1' if self.routine.isChecked() else '')
        if (self.filters['channel'] and (self.filters['level'] or self.filters['kind'] == 'event')
                or self.filters['level'] and self.filters['kind'] == 'message'):
            self.status.setText('Canal filtra mensagens e nível filtra eventos. Ajuste os filtros.')
            return
        self.fetch(0)

    def previous(self):
        if self.offset:
            self.fetch(max(0, self.offset - self.page_size))

    def next_page(self):
        if self.next_offset is not None:
            self.fetch(self.next_offset)

    def fetch(self, offset):
        if not self.entity:
            return
        self.generation += 1
        generation = self.generation
        self.status.setText('Consultando histórico…')
        def loaded(out):
            if generation != self.generation:
                return
            if not isinstance(out, dict):
                self.status.setText('Consulta indisponível. Confira a data e tente novamente.')
                return
            self.offset, self.next_offset = offset, out.get('next_offset')
            self.page_size = out['page_size']
            self.rows.clear()
            for record in out.get('items', []):
                when = hora_local(record)
                message = record['record_kind'] == 'message'
                label = 'Mensagem' if message else record.get('severity') or 'Evento'
                author = record.get('author') if message else record.get('component')
                summary = record.get('content') if message else record.get('kind')
                item = QTreeWidgetItem([str(when), label, str(author or '—'), str(summary or '')[:180]])
                item.setData(0, Qt.UserRole, record)
                self.rows.addTopLevelItem(item)
            self.selected()
            for column in (0, 1, 2):
                self.rows.resizeColumnToContents(column)
            count = self.rows.topLevelItemCount()
            self.status.setText(f'{count} registros · posição {offset + 1 if count else 0} · {out.get("timezone", "")}')
        if not self.request(self.entity, offset, self.filters, loaded):
            self.status.setText('Consulta indisponível no momento.')

    def selection(self):
        items = self.rows.selectedItems()
        return items[0].data(0, Qt.UserRole) if items else {}

    def attachment_names(self):
        record = self.selection()
        source = (record.get('data') or {}).get('attachment_name', '')
        content = record.get('content') or ''
        matches = re.findall(r'\b[0-9a-f]{12}-clipboard-(?:texto\.txt|print\.png)\b', str(source) + '\n' + content)
        return list(dict.fromkeys(matches))

    def selected(self):
        record = self.selection()
        details = record.get('data') or record.get('metadata') or {}
        self.detail.setPlainText(
            (record.get('content') or '') + '\n\n' + json.dumps(details, ensure_ascii=False, indent=2)
            if record else ''
        )
        self.preview.setEnabled(bool(self.attachment_names()))

    def preview_selected(self):
        names = self.attachment_names()
        if len(names) == 1:
            self.open_attachment(self.entity, names[0])
        elif names:
            name, accepted = QInputDialog.getItem(self, 'Conteúdo copiado', 'Anexo', names, editable=False)
            if accepted:
                self.open_attachment(self.entity, name)


class ServicesPanel(QWidget):
    def __init__(self,open_audio):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.summary=QLabel('Consultando configuração…');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        grid=QGridLayout();layout.addLayout(grid);self.providers={}
        for i,(provider,title,color) in enumerate((('elevenlabs','ElevenLabs','#c6a3ed'),('azure','Azure Speech','#94b8ef'))):
            card=QGroupBox(title);body=QVBoxLayout(card);state=QLabel('—');state.setStyleSheet('font-size:21px;color:'+color);body.addWidget(state)
            key=QLabel('Chave: estado indisponível');body.addWidget(key)
            detail=QLabel('');detail.setTextFormat(Qt.PlainText);detail.setWordWrap(True);body.addWidget(detail)
            connection=QLabel('Conexão não testada');connection.setWordWrap(True);body.addWidget(connection)
            grid.addWidget(card,0,i);self.providers[provider]=(state,key,detail,connection)
        self.local=QGroupBox('Voz local · fallback preservado');body=QVBoxLayout(self.local);self.local_detail=QLabel('');self.local_detail.setWordWrap(True);body.addWidget(self.local_detail);layout.addWidget(self.local)
        button=QPushButton('Abrir configurações e testes de áudio');button.clicked.connect(open_audio);layout.addWidget(button)
        note=QLabel('Ler este painel não chama provedores nem gasta créditos. Chave configurada não comprova conexão, quota ou permissão para uma voz. Testes pagos continuam exigindo confirmação.');note.setWordWrap(True);note.setObjectName('subtitle');layout.addWidget(note);layout.addStretch()
    def render(self,out):
        if not isinstance(out,dict):
            self.summary.setText('Consulta indisponível; configuração atual não confirmada.')
            for state,key,detail,connection in self.providers.values():state.setText('Indisponível');key.setText('Chave: estado indisponível');detail.clear();connection.setText('Conexão não testada')
            self.local_detail.clear();return
        self.summary.setText('Preferência configurada: '+str(out.get('preferred_provider','indisponível'))+' · não equivale ao último provedor utilizado')
        for provider,(state,key,detail,connection) in self.providers.items():
            data=out.get('providers',{}).get(provider,{})
            state.setText('Habilitado' if data.get('enabled') is True else 'Desabilitado' if data.get('enabled') is False else 'Indisponível')
            key.setText('API key: '+('CONFIGURADA' if data.get('key_configured') is True else 'NÃO CONFIGURADA' if data.get('key_configured') is False else 'ESTADO INDISPONÍVEL'))
            voices=data.get('voices') or {};detail.setText('Modelo: '+str(data.get('model') or 'não informado')+'\nHoshino: '+str(voices.get('hoshino','não definida'))+'\nLilith: '+str(voices.get('lilith','não definida')))
            connection.setText(str(data.get('connection') or 'Conexão não testada nesta consulta'))
        self.local_detail.setText('Backend configurado: '+str(out.get('local_backend') or 'não informado')+'\nQwen3-TTS e Kokoro mantidos. A voz realmente utilizada consta nos eventos e no resultado de cada teste, inclusive fallback.')
