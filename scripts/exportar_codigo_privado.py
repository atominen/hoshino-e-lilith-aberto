#!/usr/bin/env python3
"""Exporta somente fontes, nunca a árvore inteira de dados da instalação."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES=('instalar.py','iniciar_entidades.py','rodar_testes.sh','requirements.txt','requirements-hoshino-v32-extra.txt')
MINECRAFT_FILES=('bridge.js','package.json','package-lock.json','config.example.json','README.md','start_bridge.sh','install_bridge.sh','prepare_local_server.sh')
SKIP={'__pycache__','.git','node_modules','runtime','memory','workspace','ambientes','modelos','versions','attachments'}
EXTENSIONS={'.py','.sh','.cjs','.js','.html','.css','.svg'}
README='''# Hoshino · Lilith · Alistair

Projeto pessoal privado de companheirismo e operação local. **Não publicar.**
Hoshino/Lilith mantêm identidade, memória e relações separadas dos executores
9B/7B. Alistair usa o 4B existente, CPU obrigatório e GPU oportunista mediada
pelo mesmo Resource Manager. AMD 8 GiB: execução conservadora, cloud desligada.

Este repositório contém código e templates iniciais, **não** as mentes atuais,
chaves, bancos, histórico, runtime, ambientes Python ou pesos da instalação.
Atualizar código não autoriza sobrescrever dados. Backup mental é separado/local.

## PC2 — Linux Mint / Athlon 3000G

```bash
git clone https://github.com/atominen/hoshino-e-lilith.git
cd hoshino-e-lilith
python3 instalar.py --perfil pc2 --pacote /caminho/alistair_pc2.tar
```

O primeiro comando do instalador apenas planeja. Transfira o pacote privado
`pacotes/alistair_pc2.tar` do PC principal e seu SHA-256 por pendrive/LAN.
Ele já contém o **mesmo** modelo 4B e motor CPU. Pesos não vão para Git e este
instalador não procura variantes novas nem depende de internet para modelos.

Para aplicar, inclua `--destino /home/SEU_USUARIO/alistair_pc2 --sha256 HASH
--aplicar`; opcionalmente `--dependencias` instala python3/libgomp1 por apt.
Depois execute `bash /home/SEU_USUARIO/alistair_pc2/iniciar.sh` e siga o pareamento
em [pc2/LEIA-ME.md](pc2/LEIA-ME.md). Nada inicia automaticamente, não abre firewall
e não move a mente para o PC2. Instalação/reinstalação recusa destino existente.

## PC principal

`python3 instalar.py --perfil principal` mostra o plano. `--aplicar
--dependencias` prepara dependências, sem baixar modelos/iniciar entidades.
Uma instalação nova ainda precisa importar os **modelos existentes**, configurar
daemons/canais e validar os serviços locais. Não é um clone das experiências
da instalação original. Use os exemplos de configuração e a central nativa.
Templates de identidade terminam em `.json.example`: copie-os apenas em uma
instalação nova e nunca por cima de uma identidade existente. Arquivos reais
`self_model.json`/`constitution.json` locais são ignorados pelo Git.

Chaves somente no ambiente: `ELEVENLABS_API_KEY`. Nunca no Git/frontend/log.
ElevenLabs/Azure reais são testes explícitos e podem consumir quota; suíte offline
nunca os chama. [Arquitetura](docs/ARQUITETURA_ATIVIDADE_20261007.md).

## Validação

`bash rodar_testes.sh` usa fixtures temporárias e proíbe serviços reais, internet,
microfone e alterações de mentes existentes. Testes humanos/hardware são
separados. Não se pode chamar uma ação incerta de sucesso.

## Uso e propriedade

Código pessoal sem autorização de distribuição. Dependências de terceiros
mantêm suas próprias licenças, listadas em `third_party/`. Não há licença aberta
para o código próprio. Não tornar o repositório público nem adicionar colaboradores
sem decisão explícita do proprietário.
'''
IGNORE='''# Dados locais nunca entram em Git. Adicionar fontes sempre explicitamente.
**/.env
**/*.env
**/*.db
**/*.sqlite*
**/runtime/
**/memory/
**/workspace/
**/versions/
**/__pycache__/
**/node_modules/
**/*.log
**/*.jsonl
**/*.backup-*
**/*.gguf
**/*.safetensors
compartilhado/ambientes/
compartilhado/modelos/
pacotes/
arquivo/
compat/
**/lan.key
**/worker.json
**/pareamento/
**/central_security.json
**/identity/self_model.json
**/identity/constitution.json
compartilhado/config/*
!compartilhado/config/*.example
entidades/*/config/*
!entidades/*/config/*.example
entidades/*/models/
'''


def inputs(root):
    root=Path(root).resolve()
    result=[]
    for name in ROOT_FILES:
        if (root/name).is_file(): result.append(root/name)
    for directory in ('app','scripts','testes','pc2','third_party'):
        for path in sorted((root/directory).rglob('*')):
            relative=path.relative_to(root)
            if any(part in SKIP for part in relative.parts) or path.is_symlink() or not path.is_file():continue
            if path.suffix not in EXTENSIONS and directory!='third_party':continue
            if directory=='third_party' and any(part in {'repos','src','build'} for part in relative.parts):continue
            if path.stat().st_size>2*1024**2:raise ValueError('Fonte grande demais; revisar: '+str(relative))
            result.append(path)
    for name in MINECRAFT_FILES:
        path=root/'compartilhado/servicos/minecraft'/name
        if path.is_file():result.append(path)
    for entity in ('hoshino','lilith','alistair'):
        for name in ('entidade.json','identity/constitution.json'):
            path=root/'entidades'/entity/name
            if path.is_file():result.append(path)
    for name in ('ARQUITETURA_ATIVIDADE_20261007.md','RELATORIO_ATIVIDADE_PRESENCA_20261007.md','INSTALACAO_PRIVADA_PC2.md'):
        path=root/'docs'/name
        if path.is_file():result.append(path)
    # Assets mínimos de propriedade de cada entidade, nunca a pasta de entregas.
    for path in (root/'app/ui/assets').rglob('*.json'):
        if path.is_file() and not path.is_symlink():result.append(path)
    return sorted(set(result))


def export(root, destination):
    root,destination=Path(root).resolve(),Path(destination).absolute()
    if destination.exists():raise ValueError('Destino existente; não sobrescrevo outra exportação.')
    files=inputs(root)
    contents={}
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Fonte fora da raiz.')
        content=path.read_text(encoding='utf-8')
        # Bloqueio defensivo; não imprime o valor suspeito em erros.
        if re.search(r'(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s*\n[A-Za-z0-9+/]{32,})',content):
            raise ValueError('Possível credencial em fonte: '+str(path.relative_to(root)))
        if re.search(r'(?:api_key|bot_token|speech_key|password)\s*[:=]\s*[\'"][A-Za-z0-9_/-]{24,}[\'"]',content,re.I):
            raise ValueError('Possível segredo literal em fonte: '+str(path.relative_to(root)))
        name=str(path.relative_to(root))
        if name.endswith('/identity/constitution.json'): name += '.example'
        contents[name]=content
    contents.update({'README.md':README,'.gitignore':IGNORE})
    for entity in ('hoshino','lilith','alistair'):
        # Seeds novos; deliberadamente NÃO exporta self_model atual/evoluído.
        contents[f'entidades/{entity}/identity/self_model.json.example']=json.dumps({'identity':{
            'name':entity.capitalize(),'self_concept':f'Eu sou {entity.capitalize()}, uma entidade individual desta instalação local.',
            'nature':'Minha identidade e memória são externas ao executor; não invento experiências anteriores.'}},ensure_ascii=False,indent=2)+'\n'
        contents[f'entidades/{entity}/config/{entity}.env.example']='# Template não secreto; configure os aliases já instalados antes de acordar.\nHOSHINO_ENTIDADE='+entity+'\n'
    destination.mkdir(parents=True)
    records={}
    for name,content in contents.items():
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        # Escrita é implementação do exportador, não edição dos arquivos reais.
        target.write_text(content,encoding='utf-8')
        records[name]=dict(bytes=len(content.encode()),sha256=hashlib.sha256(content.encode()).hexdigest())
    manifest=dict(schema=1,private_only=True,credentials=False,mental_data=False,models=False,files=records)
    (destination/'EXPORTACAO.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return dict(folder=str(destination),files=len(contents),bytes=sum(r['bytes'] for r in records.values()),
                minds_exported=False,models_exported=False,credentials_exported=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destino',type=Path)
    args=parser.parse_args();print(json.dumps(export(ROOT,args.destino),ensure_ascii=False,indent=2))
