#!/usr/bin/env python3
"""Aquisição explícita YAMNet/LiteRT em CPU; nunca abre microfone ou Central."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import venv
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT)]
from core import acoustic_perception as acoustic


def install():
    if sys.version_info[:2]!=(3,12):raise RuntimeError('Use /usr/bin/python3 (Python3.12) para isolar o runtime.')
    folder=acoustic.MODEL_DIR
    path=folder/'yamnet.tflite'
    if path.exists():acoustic._verified_model()
    else:
        with urlopen(acoustic.MODEL_URL,timeout=30) as response:raw=response.read(acoustic.MODEL_BYTES+1)
        if len(raw)!=acoustic.MODEL_BYTES or hashlib.sha256(raw).hexdigest()!=acoustic.MODEL_SHA:
            raise RuntimeError('Download divergente; não instalar.')
        folder.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as out:out.write(raw)
    runtime=ROOT/'compartilhado/ambientes/percepcao-acustica'
    if not (runtime/'bin/python').exists():venv.EnvBuilder(with_pip=False).create(runtime)
    with urlopen('https://pypi.org/pypi/ai-edge-litert/2.3.0/json',timeout=20) as response:meta=json.load(response)
    wheel=next(f for f in meta['urls'] if f['filename']=='ai_edge_litert-2.3.0-cp312-cp312-manylinux_2_27_x86_64.whl')
    digest='dc9f56c23e0dcf182b6c35f23fbb102ed048296588882b806d5eff7654c04c88'
    if wheel['digests']['sha256']!=digest:raise RuntimeError('Wheel LiteRT divergente.')
    command=[str(ROOT/'compartilhado/ambientes/principal/bin/python'),'-m','pip','--python',str(runtime/'bin/python'),
             'install','--only-binary=:all:','numpy==2.2.6',wheel['url']+'#sha256='+digest]
    result=subprocess.run(command,capture_output=True,text=True,timeout=300)
    if result.returncode:raise RuntimeError('Instalação isolada falhou: '+result.stderr[-1600:])
    receipt=dict(engine='YAMNet',model_url=acoustic.MODEL_URL,model_sha256=acoustic.MODEL_SHA,
                 model_bytes=acoustic.MODEL_BYTES,runtime='ai-edge-litert==2.3.0',wheel_sha256=digest,
                 license='Apache-2.0',license_url='https://github.com/tensorflow/models/blob/master/LICENSE',device='cpu',capture_started=False)
    (folder/'installation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--install',action='store_true');args=parser.parse_args()
    if not args.install:parser.error('Instalação exige --install; importação não baixa nem instala.')
    install()
