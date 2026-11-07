#!/usr/bin/env python3
"""CLI stdlib do laboratório, executável diretamente na pasta do projeto."""
import argparse
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:sys.path.insert(0,str(HERE.parent))
from laboratorio.core import Laboratory
from laboratorio.controle import schedule,resume_if_same


def cli(argv=None):
    p=argparse.ArgumentParser(description='Hoshino/Lilith Laboratório — painel, mods e agenda local')
    p.add_argument('--project',type=Path,default=HERE.parent)
    p.add_argument('--home',type=Path,default=Path.home()/'laboratorio-lora')
    subs=p.add_subparsers(dest='command',required=True)
    subs.add_parser('status')
    mods=subs.add_parser('mods');mods.add_argument('action',choices=['list','enable','disable']);mods.add_argument('id',nargs='?')
    subs.add_parser('build')
    subs.add_parser('overlay')
    subs.add_parser('models')
    subs.add_parser('datasets')
    subs.add_parser('jobs')
    pr=subs.add_parser('preview');pr.add_argument('--model',required=True);pr.add_argument('--operation',choices=['train','convert','ollama_test','cycle_30m'],required=True);pr.add_argument('--dataset',default='');pr.add_argument('--minutes',type=int,default=30);pr.add_argument('--adapter',default='');pr.add_argument('--entity',default='hoshino')
    job=subs.add_parser('job');job.add_argument('--model',required=True);job.add_argument('--operation',choices=['train','convert','ollama_test','cycle_30m'],required=True);job.add_argument('--dataset',default='');job.add_argument('--minutes',type=int,default=30);job.add_argument('--adapter',default='');job.add_argument('--entity',default='hoshino');job.add_argument('--at',default='');job.add_argument('--confirm',action='store_true')
    start=subs.add_parser('launch-job');start.add_argument('--id',required=True)
    srv=subs.add_parser('serve');srv.add_argument('--port',type=int,default=8788)
    sch=subs.add_parser('schedule');sch.add_argument('--pid',type=int,required=True);sch.add_argument('--at',required=True,help='AAAA-MM-DD HH:MM:SS (hora local)')
    res=subs.add_parser('resume-if-same');res.add_argument('--pid',type=int,required=True);res.add_argument('--token',required=True)
    a=p.parse_args(argv)
    lab=Laboratory(a.project,a.home)
    if a.command=='serve':
        from laboratorio.painel import serve
        serve(lab,a.port);return
    if a.command=='resume-if-same':
        value=resume_if_same(a.pid,a.token)
    elif a.command=='schedule': value=schedule(lab,a.pid,a.at)
    elif a.command=='status': value=lab.status()
    elif a.command in ('models','datasets','jobs','preview','job','launch-job'):
        from laboratorio.catalogo import MODELS
        from laboratorio.experimentos import allowed_data,read_jobs,inspect_plan,create_job,launch_job
        if a.command=='models':value=list(MODELS)
        elif a.command=='datasets':value=allowed_data(lab.home)
        elif a.command=='jobs':value=read_jobs(lab.home)
        elif a.command=='launch-job':value=launch_job(lab.home,a.id)
        else:
            params={'model':a.model,'operation':a.operation,'dataset':a.dataset,'minutes':a.minutes,'adapter':a.adapter,'entity':a.entity}
            if a.command=='preview':value=inspect_plan(params,lab.home)
            else:
                if not a.confirm:raise ValueError('Adicione --confirm para enviar um trabalho ao laboratório')
                value=create_job(lab.home,params,a.at or None)
    elif a.command=='mods':
        if a.action=='list':value=lab.mods()
        else:
            if not a.id: p.error('ID do mod necessário')
            value={'enabled':lab.set_mod(a.id,a.action=='enable')}
    elif a.command=='build':value=lab.build()
    elif a.command=='overlay':value=lab.overlay_info()
    else: p.error('Comando inválido')
    print(json.dumps(value,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:cli()
    except (ValueError,PermissionError,RuntimeError,FileNotFoundError) as e:
        print('ERRO:',e,file=sys.stderr);sys.exit(2)
