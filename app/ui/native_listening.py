"""Painel da escuta real da Central; não captura nem inicia modelo na UI."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QLabel,QLineEdit,QHBoxLayout,QPushButton,QTreeWidget,QTreeWidgetItem
from native_controls import QComboBox

class ListeningPanel(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.generation=0;self.pending=None
        layout=QVBoxLayout(self)
        note=QLabel('Escolha o que cada entidade escuta. Ativa pode virar assunto; passiva fica disponível para consulta. Ignorar encerra a escuta do canal.');note.setWordWrap(True);layout.addWidget(note)
        self.status=QLabel('Atualize para consultar as fontes disponíveis.');self.status.setWordWrap(True);layout.addWidget(self.status)
        form=QFormLayout();self.source=QComboBox();self.source.addItem('Selecione uma fonte…',None)
        self.channel=QLineEdit();self.channel.setPlaceholderText('Ex.: jogo, navegador, ambiente');self.channel.setMaxLength(60)
        self.attention=QComboBox()
        for label,value in [('Ativa · pode virar assunto','ativa'),('Passiva · consultar depois','passiva'),('Ignorar · não escutar','ignorar')]:self.attention.addItem(label,value)
        form.addRow('Fonte',self.source);form.addRow('Nome do canal',self.channel);form.addRow('Atenção',self.attention);layout.addLayout(form)
        self.channels=QTreeWidget();self.channels.setHeaderLabels(['Canal','Origem','Atenção','Estado']);layout.addWidget(self.channels,1)
        self.channels.itemSelectionChanged.connect(self.selected)
        row=QHBoxLayout();layout.addLayout(row)
        for label,action in [('Atualizar fontes',self.refresh),('Ouvir fonte',self.open_source),('Alterar atenção',self.change_attention),('Fechar canal',self.stop_selected),('Fechar todos desta entidade',self.stop_all)]:
            button=QPushButton(label);button.clicked.connect(action);row.addWidget(button)
        self.detail=QLabel('A origem indica o aplicativo ou dispositivo; não identifica quem falou.');self.detail.setWordWrap(True);layout.addWidget(self.detail)

    def clear(self):
        self.generation+=1;self.pending=None;self.channels.clear();self.source.clear();self.source.addItem('Selecione uma fonte…',None)
        self.channel.clear();self.status.setText('Consultando escuta da entidade selecionada…')

    def render(self,state):
        if not isinstance(state,dict) or state.get('entity')!=self.window.current_entity():return
        previous=self.source.currentData();selected=self.selected_channel()
        if 'sources' in state:
            self.source.clear();self.source.addItem('Selecione uma fonte…',None)
            kinds={'microphone':'Microfone','output_mix':'Som geral do PC','application_stream':'Aplicativo isolado'}
            for source in state['sources']:
                enabled=source['kind']!='application_stream' or source.get('isolated_capture')
                self.source.addItem(kinds.get(source['kind'],'Fonte')+' · '+source['label']+(' · indisponível' if not enabled else ''),source['id'])
                if not enabled:self.source.model().item(self.source.count()-1).setEnabled(False)
            self.source.setCurrentIndex(max(0,self.source.findData(previous)))
        self.channels.clear()
        for channel in state.get('channels',[]):
            item=QTreeWidgetItem([channel['channel'],channel['source']['label'],channel['attention'],channel['status']])
            item.setData(0,Qt.UserRole,channel);self.channels.addTopLevelItem(item)
            if channel['channel']==selected:self.channels.setCurrentItem(item)
        self.status.setText(self.window.current_entity().capitalize()+': '+str(len(state.get('channels',[])))+' canais · '+str(state.get('capture_count',0))+' fontes capturadas no app'+
            ((' · '+str(state['uncertain_count'])+' encerramentos não confirmados') if state.get('uncertain_count') else '')+
            ('' if state.get('allowed') else ' · Ouvir o ambiente está desativado nas Ferramentas.'))

    def selected_channel(self):
        row=self.channels.currentItem();return row.data(0,Qt.UserRole)['channel'] if row else ''

    def selected(self):
        item=self.channels.currentItem()
        if not item:return
        row=item.data(0,Qt.UserRole);self.channel.setText(row['channel'])
        self.attention.setCurrentIndex(max(0,self.attention.findData(row['attention'])))
        self.source.setCurrentIndex(max(0,self.source.findData(row['source_id'])))
        self.detail.setText(row.get('error') or ('Transcrevendo…' if row.get('pending') else
            ('Sobrecarga: '+str(row['dropped_segments'])+' trechos não processados.' if row.get('dropped_segments') else 'Escuta com origem marcada; pessoa desconhecida.')))

    def refresh(self):
        if self.pending is not None:return
        view=(self.window.current_entity(),self.generation);token=object();self.pending=token
        def received(state):
            if self.pending is token:self.pending=None
            if view!=(self.window.current_entity(),self.generation):return
            if state is None:self.status.setText('Escuta não confirmada. Atualize antes de repetir uma alteração.');return
            self.render(state)
        request=self.window.request(self.window.query('audio/listening',entity=view[0]),callback=received,quiet=True)
        if request is None:self.pending=None

    def mutate(self,action,**data):
        entity=self.window.current_entity();view=(entity,self.generation)
        def received(state):
            if view!=(self.window.current_entity(),self.generation):return
            if state is None:self.status.setText('Resultado não confirmado; atualize o estado antes de repetir.');return
            self.render(state)
        self.window.request('audio/listening',dict(action=action,entity=entity,**data),callback=received)

    def open_source(self):
        source=self.source.currentData();channel=self.channel.text().strip()
        if not source or not channel:self.status.setText('Selecione uma fonte e dê um nome ao canal.');return
        self.mutate('open',source_id=source,channel=channel,attention=self.attention.currentData())
    def change_attention(self):
        channel=self.selected_channel()
        if channel:self.mutate('attention',channel=channel,attention=self.attention.currentData())
    def stop_selected(self):
        channel=self.selected_channel()
        if channel:self.mutate('stop',channel=channel)
    def stop_all(self):self.mutate('stop',channel='')
