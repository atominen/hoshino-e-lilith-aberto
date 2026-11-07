#!/usr/bin/env python3
"""Resumo somente leitura da qualidade operacional do professor MoE.
Nao abre historias, memorias de entidades nem aciona o modelo.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path

LAB=Path.home()/'laboratorio-lora'

def audit(home:Path):
    root=home/'professor-moe-35b'
    jobs=root/'trabalhos';proposals=root/'propostas'
    out={'generated_proposals':0,'jobs_by_state':{},'jobs_by_mode':{},'audited_heavy':0,
        'heavy_quality_passed':0,'heavy_quality_failed':0,'approved_datasets':0,
        'invalid_json':0,'warning':'Contagens estruturais nao substituem revisao humana'}
    if jobs.is_dir() and not jobs.is_symlink():
        for file in sorted(jobs.glob('*.json'))[:500]:
            if file.is_symlink():continue
            try:
                obj=json.loads(file.read_text(encoding='utf8'))
                if not isinstance(obj,dict):raise ValueError('invalid')
                state=obj.get('state','unknown')
                mode=obj.get('mode','standard')
                if mode not in ('standard','heavy_10k'):mode='unknown'
                rec=out['jobs_by_mode'].setdefault(mode,{'jobs':0,'failed':0,'proposed_or_approved':0})
                rec['jobs']+=1
                if state in ('failed','needs_revision'):rec['failed']+=1
                if state in ('proposed','approved_dataset'):rec['proposed_or_approved']+=1
                out['jobs_by_state'][state]=out['jobs_by_state'].get(state,0)+1
                if state=='approved_dataset':out['approved_datasets']+=1
            except (OSError,ValueError):out['invalid_json']+=1
    if proposals.is_dir() and not proposals.is_symlink():
        for file in sorted(proposals.glob('*.json'))[:500]:
            if file.is_symlink():continue
            try:
                data=json.loads(file.read_text(encoding='utf8'))
                if not isinstance(data,dict) or not isinstance(data.get('examples'),list):raise ValueError('invalid')
                out['generated_proposals']+=1
                qa=data.get('quality_audit')
                if isinstance(qa,dict):
                    out['audited_heavy']+=1
                    out['heavy_quality_passed' if qa.get('passed') is True else 'heavy_quality_failed']+=1
            except (OSError,ValueError):out['invalid_json']+=1
    out['recommended_teacher_mode']='NO_AUTOMATIC_SELECTION: requer qualidade humana, latencia e taxa de erros medidas'
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,default=LAB)
    a=p.parse_args()
    print(json.dumps(audit(a.home.expanduser().resolve()),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
