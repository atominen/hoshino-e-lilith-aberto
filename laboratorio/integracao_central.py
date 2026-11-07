"""Integração opt-in no menu principal, sem alterar backend/entidades.

A atualização do Qt adiciona entrada no menu; clicar abre o laboratório em localhost.
A atualização do navegador oferece link ao mesmo painel (sem iniciar processos).
"""
from __future__ import annotations
from pathlib import Path

NATIVE_FILE = Path('app/ui/central_native.py')
BROWSER_FILE = Path('app/ui/control.js')


def patch_native(source: str) -> str:
    if "self.pages['Laboratório Neural']" in source:
        return source
    targets = [
        ("'Modelos','Recursos'", "'Modelos','Laboratório Neural','Recursos'"),
        ("'Executores locais e arquivos instalados.','Residência", "'Executores locais e arquivos instalados.','Treinamentos separados e curadoria MoE, somente mediante autorização.','Residência"),
        ("self.build_models();self.build_settings()", "self.build_models();self.build_laboratory();self.build_settings()"),
    ]
    for old,new in targets:
        if source.count(old)!=1:
            raise RuntimeError('Central nativa divergente: não é seguro alterar automaticamente '+old)
        source=source.replace(old,new,1)
    anchor='    def build_settings(self):'
    if source.count(anchor)!=1:
        raise RuntimeError('Método de configuração da Central não encontrado')
    code='''    def build_laboratory(self):
        """Somente interface. O laboratório mantém seu próprio processo e autenticação."""
        layout=self.pages['Laboratório Neural']
        note=QLabel('Treinamento separado de Hoshino, Lilith e Alistair.\\n'
                    'Professor MoE prepara e revisa propostas sem alterar a Central.\\n'
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

'''
    return source.replace(anchor,code+anchor,1)


def patch_browser(source: str) -> str:
    if "panels.get('Laboratório Neural')" in source:
        return source
    old="'Modelos','Áudio','Recursos'"
    if source.count(old)!=1:
        raise RuntimeError('Menu da Central web divergente; integração recusada')
    source=source.replace(old,"'Modelos','Laboratório Neural','Áudio','Recursos'",1)
    anchor="  nav.append(node('div','Somente neste PC · cloud desligada','footnote'));"
    if source.count(anchor)!=1:
        raise RuntimeError('Âncora de menu web não encontrada')
    code='''  const laboratory=panels.get('Laboratório Neural');
  laboratory.append(node('p','Treinamento de entidades e curadoria MoE rodam em um serviço localhost separado, iniciado pelo painel nativo ou manualmente.','section-note'));
  const labLink=node('a','Abrir Laboratório Neural · localhost:8788');
  labLink.href='http://127.0.0.1:8788';labLink.target='_blank';labLink.rel='noopener noreferrer';
  laboratory.append(labLink);
'''
    return source.replace(anchor,code+anchor,1)


def prepared_changes(project: Path) -> dict[Path,str]:
    result={}
    for file,patch in ((NATIVE_FILE,patch_native),(BROWSER_FILE,patch_browser)):
        target=project/file
        if target.is_symlink() or not target.is_file():
            raise RuntimeError('Central original ausente ou simbólica: '+str(target))
        source=target.read_text(encoding='utf-8')
        patched=patch(source)
        if patched!=source:
            if file.suffix=='.py':
                compile(patched,str(file),'exec')
            result[file]=patched
    return result
