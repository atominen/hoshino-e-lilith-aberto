"""Small Qt editor for the existing semantic model rows. No inference/timer."""
import json
import math
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QColor, QPen, QBrush, QPolygonF
from PyQt5.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,
    QGraphicsScene,QGraphicsView,QGraphicsRectItem,QGraphicsTextItem,
    QGraphicsLineItem,QGraphicsPolygonItem,QInputDialog,QMessageBox,
    QTableWidget,QTableWidgetItem)
from native_controls import QComboBox,QTabWidget

KINDS=('conceito','componente','evento','hipotese','fato_informado','observacao','pergunta',
       'condicao','decisao','consequencia','objetivo','problema','solucao')
RELATIONS=('causa','consequencia','depende_de','parte_de','contradiz','sustenta','antes',
           'depois','exige','excecao','relacionado')


class Node(QGraphicsRectItem):
    def __init__(self,record,editor):
        super().__init__(0,0,204,106);self.record=record;self.editor=editor
        self.setFlags(self.ItemIsMovable|self.ItemIsSelectable|self.ItemSendsGeometryChanges)
        self.setBrush(QBrush(QColor('#25334a')));self.setPen(QPen(QColor('#a0bbe4'),1.5))
        text=QGraphicsTextItem(record['kind']+'\n'+record['label'][:155],self)
        text.setDefaultTextColor(QColor('#eef3fc'));text.setTextWidth(190);text.setPos(4,4)
        self.setToolTip(record['label']+'\nCondições: '+str(record.get('conditions',[]))+'\nExceções: '+str(record.get('exceptions',[])))
        self.setPos(record.get('x',0),record.get('y',0))
    def itemChange(self,change,value):
        if change==self.ItemPositionHasChanged and getattr(self.editor,'ready',False):
            self.record.update(x=round(value.x(),2),y=round(value.y(),2));self.editor.dirty=True;self.editor.arrows()
        return super().itemChange(change,value)
    def mouseDoubleClickEvent(self,event):self.editor.edit_node(self.record)


class EdgeLabel(QGraphicsTextItem):
    def __init__(self,edge,editor):
        super().__init__(edge['relation']+' · '+edge['basis']);self.edge=edge;self.editor=editor
    def mouseDoubleClickEvent(self,event):self.editor.edit_edge(self.edge)


class LogicWorkshop(QWidget):
    def __init__(self,central):
        super().__init__();self.central=central;self.ready=False;self.dirty=False;self.loaded_entity=None
        self.previous=None;self.records=[];self.graph={'nodes':[],'edges':[],'tables':[]};self.node_items={};self.arrow_items=[]
        layout=QVBoxLayout(self);row=QHBoxLayout();layout.addLayout(row)
        self.selector=QComboBox();row.addWidget(self.selector,1)
        self.button(row,'Consultar modelos',self.refresh);self.button(row,'Novo',self.new)
        self.title=QLineEdit();self.title.setPlaceholderText('Assunto / título');layout.addWidget(self.title)
        self.refs=QLineEdit();self.refs.setPlaceholderText('Evidências: episodes:ID, memories:ID (ou selecione no inspetor)');layout.addWidget(self.refs)
        row=QHBoxLayout();layout.addLayout(row)
        self.button(row,'Usar seleção do inspetor',self.use_selection)
        self.button(row,'Adicionar nó',self.add_node);self.button(row,'Conectar',self.add_edge)
        self.button(row,'Remover selecionado',self.remove_selected)
        self.button(row,'Salvar revisão',self.save)
        tabs=QTabWidget();layout.addWidget(tabs,1);self.scene=QGraphicsScene();self.scene.setSceneRect(-100,-100,1800,1200)
        self.view=QGraphicsView(self.scene);self.view.setMinimumHeight(360);tabs.addTab(self.view,'Diagrama · arraste / duplo clique')
        table_page=QWidget();tl=QVBoxLayout(table_page);self.table_selector=QComboBox();tl.addWidget(self.table_selector)
        controls=QHBoxLayout();tl.addLayout(controls);self.button(controls,'Nova tabela',self.add_table);self.button(controls,'Nova linha',self.add_row)
        self.table=QTableWidget();tl.addWidget(self.table);tabs.addTab(table_page,'Condições / comparação / evidências')
        self.info=QLabel('Interpretações revisáveis. Setas não comprovam causalidade. Edição administrativa requer entidade dormindo; sem IA ou chamadas pagas.');self.info.setWordWrap(True);layout.addWidget(self.info)
        self.mode=QComboBox();self.mode.addItem('Rascunho · hipótese não validada','rascunho');self.mode.addItem('Com evidências · interpretação revisável','fundamentado')
        layout.insertWidget(1,self.mode);self.mode.activated.connect(lambda _:self.changed())
        self.selector.activated.connect(self.select);self.table_selector.activated.connect(self.select_table)
        self.table.cellChanged.connect(self.table_changed);self.title.textEdited.connect(lambda _:self.changed())
    def button(self,row,label,fn):
        button=QPushButton(label);button.clicked.connect(lambda:fn());row.addWidget(button)
    def changed(self):self.dirty=True
    def discard(self):
        return not self.dirty or QMessageBox.question(self,'Oficina','Descartar alterações locais não salvas?')==QMessageBox.Yes
    def new(self):
        if not self.discard():return
        self.loaded_entity=self.central.current_entity();self.previous=None;self.graph={'nodes':[],'edges':[],'tables':[]}
        self.mode.setCurrentIndex(0)
        self.title.clear();self.refs.clear();self.dirty=False;self.render();self.info.setText('Novo rascunho de '+self.loaded_entity+'. Hipóteses e conceitos podem ser anotados sem inventar evidências.')
    def refresh(self):
        if not self.discard():return
        entity=self.central.current_entity()
        if entity=='alistair':self.info.setText('Oficina privada disponível somente para Hoshino e Lilith.');return
        def received(out):
            if not out or entity!=self.central.current_entity():return
            self.records=out.get('items',[]);self.selector.clear();self.selector.addItems([r['title'] for r in self.records])
            self.loaded_entity=entity;self.dirty=False
            if self.records:self.select(0)
            else:self.new()
        self.central.request(self.central.query('control/logic',entity=entity),callback=received)
    def select(self,index):
        if not self.discard() or not 0<=index<len(self.records):return
        record=self.records[index];self.previous=record['id'];self.graph=json.loads(json.dumps(record['graph']))
        self.title.setText(record['title']);self.refs.setText(', '.join(r['table']+':'+r['id'] for r in record['evidence']))
        self.mode.setCurrentIndex(self.mode.findData(record.get('mode','fundamentado')))
        label='rascunho não validado' if record.get('mode')=='rascunho' else 'interpretação, não fato confirmado'
        self.dirty=False;self.render();self.info.setText('Entidade: '+str(self.loaded_entity)+' · revisão '+self.previous+' · '+label+'.')
    def render(self):
        self.ready=False;self.scene.clear();self.arrow_items=[];self.node_items={}
        for i,node in enumerate(self.graph['nodes']):
            if 'x' not in node:node.update(x=(i%4)*270,y=(i//4)*150)
            item=Node(node,self);self.scene.addItem(item);self.node_items[node['id']]=item
        self.ready=True;self.arrows()
        self.table_selector.clear();self.table_selector.addItems([t['title'] for t in self.graph.get('tables',[])])
        self.select_table(0)
    def arrows(self):
        for item in self.arrow_items:self.scene.removeItem(item)
        self.arrow_items=[]
        for edge in self.graph['edges']:
            a=self.node_items.get(edge['from']);b=self.node_items.get(edge['to'])
            if not a or not b:continue
            start=a.sceneBoundingRect().center();end=b.sceneBoundingRect().center();delta=end-start
            distance=math.hypot(delta.x(),delta.y()) or 1
            end=end-QPointF(delta.x()/distance*112,delta.y()/distance*60)
            line=QGraphicsLineItem(start.x(),start.y(),end.x(),end.y());line.setPen(QPen(QColor('#d8b98c'),2));line.setZValue(-1)
            angle=math.atan2(delta.y(),delta.x());tip=QGraphicsPolygonItem(QPolygonF([end,end-QPointF(12*math.cos(angle-.4),12*math.sin(angle-.4)),end-QPointF(12*math.cos(angle+.4),12*math.sin(angle+.4))]))
            tip.setBrush(QBrush(QColor('#d8b98c')));label=EdgeLabel(edge,self)
            label.setDefaultTextColor(QColor('#d8b98c'));label.setPos((start+end)/2)
            label.setToolTip(json.dumps(edge,ensure_ascii=False));label.setFlag(label.ItemIsSelectable,True);label.setData(0,self.graph['edges'].index(edge))
            for item in (line,tip,label):self.scene.addItem(item);self.arrow_items.append(item)
    def add_node(self):
        if self.loaded_entity is None:self.new()
        label,ok=QInputDialog.getMultiLineText(self,'Nó','Descrição:')
        if not ok or not label.strip():return
        kind,ok=QInputDialog.getItem(self,'Nó','Categoria:',KINDS,0,False)
        if not ok:return
        self.graph['nodes'].append({'id':'n'+str(max([int(n['id'][1:]) for n in self.graph['nodes'] if n['id'][1:].isdigit()]+[0])+1),'label':label,'kind':kind,'x':200,'y':100})
        self.dirty=True;self.render()
    def edit_node(self,node):
        label,ok=QInputDialog.getMultiLineText(self,'Editar nó','Descrição:',node['label'])
        if not ok:return
        kind,ok=QInputDialog.getItem(self,'Tipo','Categoria:',KINDS,KINDS.index(node['kind']),False)
        if not ok:return
        conditions,ok=QInputDialog.getMultiLineText(self,'Condições','Uma condição por linha:','\n'.join(node.get('conditions',[])))
        if not ok:return
        exceptions,ok=QInputDialog.getMultiLineText(self,'Exceções','Uma exceção por linha:','\n'.join(node.get('exceptions',[])))
        if not ok:return
        node.update(label=label,kind=kind,conditions=conditions.splitlines(),exceptions=exceptions.splitlines());self.dirty=True;self.render()
    def add_edge(self):
        ids=[n['id'] for n in self.graph['nodes']]
        if len(ids)<2:self.info.setText('Adicione pelo menos dois nós.');return
        source,ok=QInputDialog.getItem(self,'Conexão','Origem:',ids,0,False)
        if not ok:return
        target,ok=QInputDialog.getItem(self,'Conexão','Destino:',ids,1,False)
        if not ok:return
        relation,ok=QInputDialog.getItem(self,'Conexão','Significado:',RELATIONS,0,False)
        if not ok:return
        basis,ok=QInputDialog.getItem(self,'Conexão','Base da relação:',['hipotese','inferencia','observacao','fonte_informada'],0,False)
        if not ok:return
        edge={'from':source,'to':target,'relation':relation,'basis':basis}
        if self.edit_edge(edge):self.graph['edges'].append(edge);self.dirty=True;self.arrows()
    def edit_edge(self,edge):
        relation,ok=QInputDialog.getItem(self,'Relação','Significado:',RELATIONS,RELATIONS.index(edge['relation']),False)
        if not ok:return False
        bases=['hipotese','inferencia','observacao','fonte_informada'];basis=edge['basis'].replace('ê','e')
        basis,ok=QInputDialog.getItem(self,'Relação','Base:',bases,bases.index(basis),False)
        if not ok:return False
        conditions,ok=QInputDialog.getMultiLineText(self,'Relação','Condições — uma por linha:','\n'.join(edge.get('conditions',[])))
        if not ok:return False
        exceptions,ok=QInputDialog.getMultiLineText(self,'Relação','Exceções — uma por linha:','\n'.join(edge.get('exceptions',[])))
        if not ok:return False
        edge.update(relation=relation,basis=basis,conditions=conditions.splitlines(),exceptions=exceptions.splitlines())
        self.dirty=True;self.arrows();return True
    def remove_selected(self):
        nodes={item.record['id'] for item in self.scene.selectedItems() if isinstance(item,Node)}
        edges={item.data(0) for item in self.scene.selectedItems() if isinstance(item,QGraphicsTextItem) and item.parentItem() is None}
        self.graph['nodes']=[n for n in self.graph['nodes'] if n['id'] not in nodes]
        self.graph['edges']=[e for i,e in enumerate(self.graph['edges']) if i not in edges and e['from'] not in nodes and e['to'] not in nodes]
        self.dirty=True;self.render()
    def use_selection(self):
        rows=[i.data(0,Qt.UserRole) for i in self.central.memory_list.selectedItems()]
        self.refs.setText(', '.join(r['table']+':'+r['id'] for r in rows if r.get('table') in {'episodes','memories','reflections'}))
    def add_table(self):
        title,ok=QInputDialog.getText(self,'Tabela','Título:')
        if not ok:return
        columns,ok=QInputDialog.getText(self,'Tabela','Colunas separadas por vírgula:')
        if not ok:return
        self.graph['tables'].append({'title':title,'columns':[s.strip() for s in columns.split(',')],'rows':[]});self.dirty=True;self.render();self.table_selector.setCurrentIndex(len(self.graph['tables'])-1);self.select_table(self.table_selector.currentIndex())
    def select_table(self,index):
        self.table.blockSignals(True);self.table.clear();self.table.setRowCount(0);self.table.setColumnCount(0)
        if 0<=index<len(self.graph['tables']):
            t=self.graph['tables'][index];self.table.setColumnCount(len(t['columns']));self.table.setHorizontalHeaderLabels(t['columns']);self.table.setRowCount(len(t['rows']))
            for r,row in enumerate(t['rows']):
                for c,cell in enumerate(row):self.table.setItem(r,c,QTableWidgetItem(cell))
        self.table.blockSignals(False)
    def add_row(self):
        i=self.table_selector.currentIndex()
        if i<0:return
        self.graph['tables'][i]['rows'].append(['—']*len(self.graph['tables'][i]['columns']));self.dirty=True;self.select_table(i)
    def table_changed(self,row,column):
        i=self.table_selector.currentIndex()
        if i>=0:self.graph['tables'][i]['rows'][row][column]=self.table.item(row,column).text();self.dirty=True
    def save(self):
        if self.loaded_entity!=self.central.current_entity():self.info.setText('Entidade mudou: consulte/abra um modelo desta entidade antes de salvar.');return
        refs=[]
        try:
            for value in self.refs.text().split(','):
                if not value.strip():continue
                table,identifier=value.strip().split(':',1);refs.append({'table':table,'id':identifier})
        except ValueError:self.info.setText('Escolha evidências no inspetor ou informe tabela:ID.');return
        reason=''
        if self.previous:
            reason,ok=QInputDialog.getText(self,'Revisão','Por que a interpretação mudou?')
            if not ok:return
        data={'entity':self.loaded_entity,'titulo':self.title.text(),'diagrama':self.graph,'evidencias':refs,'anterior':self.previous,'motivo':reason,'modo':self.mode.currentData()}
        def saved(out):
            if out and out.get('verified'):
                self.previous=out['id'];self.dirty=False;self.info.setText('Gravação confirmada · '+out['id']+' · conteúdo continua revisável.');self.refresh()
        self.central.request('control/logic',data,callback=saved)
