"""Entrada compatível dos probes. Executa o MESMO runner NF4/RM do painel.

Não mantém outro preparo PEFT, mapa GPU ou loop de treinamento. Relatórios
históricos são preservados; um smoke não prova qualidade/uso prolongado.
"""
from __future__ import annotations
import argparse,json,subprocess,uuid
from pathlib import Path
from .treinos_unificados import MODELS as CATALOG,home_data,DATASETS
from .treino_nf4_curto import type_for

LAB=Path.home()/'laboratorio-lora'
ALIASES={'4b':'alistair-4b','6b':'yi-6b','7b-hunyuan':'hunyuan-7b','7b-qwen25':'qwen25-7b','9b':'qwen35-9b'}
MODELS={alias:(CATALOG[mid][0],*type_for(Path(CATALOG[mid][0]))) for alias,mid in ALIASES.items()}

def manifest(home):
    rows={r['id']:r for r in home_data(home)}
    return {alias:dict(rows[mid],type_expected=MODELS[alias][1],multimodal_expected=MODELS[alias][2],
                 status='STRUCTURE_OK' if rows[mid]['installed'] else 'CHECK_REQUIRED',
                 safe_smoke_enabled=rows[mid]['train_enabled']) for alias,mid in ALIASES.items()}

def smoke(home,name,entity,outdir):
    if name not in ALIASES or entity not in DATASETS:raise ValueError('Probe/entidade inválido')
    row=manifest(home)[name]
    if not row['safe_smoke_enabled']:raise RuntimeError('Perfil bloqueado; consulte diagnóstico/benchmark atual')
    if row['exclusive_entity'] and entity!=row['exclusive_entity']:raise ValueError('Modelo exclusivo de Alistair')
    output=Path(outdir)/(uuid.uuid4().hex[:16]+'-'+name)
    command=[str(Path(home)/'.venv-rocm/bin/python'),'-u','-m','laboratorio.treino_nf4_curto',
        '--model',row['path'],'--train',str(Path(home)/DATASETS[entity][0]),
        '--validation',str(Path(home)/DATASETS[entity][1]),'--entity',entity,'--mode','smoke','--out',str(output)]
    result=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],check=False)
    if result.returncode:raise RuntimeError('Probe falhou: '+str(result.returncode))
    return json.loads(output.with_suffix('.json').read_text())

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('plan','smoke'))
    p.add_argument('--home',type=Path,default=LAB);p.add_argument('--model',choices=tuple(ALIASES))
    p.add_argument('--entity',choices=tuple(DATASETS),default='hoshino');p.add_argument('--out',type=Path)
    p.add_argument('--confirm',action='store_true');a=p.parse_args()
    if a.action=='plan':result=manifest(a.home.resolve())
    else:
        if not a.confirm or not a.model or not a.out:raise ValueError('Probe exige --confirm, --model e --out')
        result=smoke(a.home.resolve(),a.model,a.entity,a.out)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
