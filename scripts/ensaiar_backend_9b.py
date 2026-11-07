"""Bancada isolada do 9B: servidor Ollama temporário (porta 11450), store da Lilith só leitura.

Uso (entidades e seus Ollama parados):
  python3 -I scripts/ensaiar_backend_9b.py '[["base",{}],["fa",{"OLLAMA_FLASH_ATTENTION":"1"}]]' '[32,33]'
Mede prompt frio, prompt com prefixo reaproveitado e geração. Resultado de 05/11 no README da pasta de saída.
"""
import json,os,subprocess,sys,time,urllib.request,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]; OUT=ROOT/'compartilhado/runtime/ensaios/backend-9b-20261105'; OUT.mkdir(parents=True,exist_ok=True)
MODEL='lilith-qwen3.5-9b-oficial-cd76ec205963:latest'; PORT=11450; URL=f'http://127.0.0.1:{PORT}'
docs=''.join(p.read_text(errors='replace') for p in sorted((ROOT/'docs').glob('MINECRAFT_*.md')))
SYS=docs[:22000]
def post(path,body,timeout=900):
    r=urllib.request.Request(URL+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r,timeout=timeout).read())
def serve(env_extra,tag):
    env=dict(os.environ,OLLAMA_HOST=f'127.0.0.1:{PORT}',OLLAMA_MODELS=str(ROOT/'compartilhado/modelos/ollama-lilith'),
             OLLAMA_VULKAN='1',OLLAMA_NOPRUNE='1',OLLAMA_KEEP_ALIVE='10m',**env_extra)
    p=subprocess.Popen(['ollama','serve'],env=env,stdout=open(OUT/f'server_{tag}.log','w'),stderr=subprocess.STDOUT)
    for _ in range(60):
        try: urllib.request.urlopen(URL+'/api/tags',timeout=1); return p
        except Exception: time.sleep(.5)
    p.kill(); raise SystemExit('servidor não subiu')
def call(user,num_gpu,ctx,predict=200,think=False):
    b=post('/api/chat',dict(model=MODEL,stream=False,think=think,keep_alive='10m',
        messages=[dict(role='system',content=SYS),dict(role='user',content=user)],
        options=dict(num_gpu=num_gpu,num_ctx=ctx,num_predict=predict,temperature=0,seed=1)))
    ps=json.loads(urllib.request.urlopen(URL+'/api/ps').read())
    vram=sum(m.get('size_vram',0) for m in ps.get('models',[]))
    return dict(prompt_n=b.get('prompt_eval_count'),prompt_s=(b.get('prompt_eval_duration') or 0)/1e9,
        gen_n=b.get('eval_count'),gen_s=(b.get('eval_duration') or 0)/1e9,load_s=(b.get('load_duration') or 0)/1e9,
        vram_gb=vram/1e9,text=b['message'].get('content','')[:400])
res={}
for tag,extra in [(a,dict(e)) for a,e in json.loads(sys.argv[1])]:
    p=serve(extra,tag)
    try:
        r=[]
        for ng in json.loads(sys.argv[2]):
            a=call('Resuma em três frases o que aconteceu com o arco.',ng,24576)
            b=call('Liste as etapas que faltam depois do arco, em uma frase cada.',ng,24576)
            r.append(dict(num_gpu=ng,frio=a,quente=b))
            print(tag,ng,{k:(round(v,2) if isinstance(v,float) else v) for k,v in b.items() if k!='text'},'| frio prompt',a['prompt_n'],round(a['prompt_s'],1),flush=True)
            post('/api/generate',dict(model=MODEL,keep_alive=0))
            time.sleep(2)
        res[tag]=r
    finally:
        p.terminate(); p.wait(20)
    time.sleep(2)
json.dump(res,open(OUT/f'resultado_{int(time.time())}.json','w'),ensure_ascii=False,indent=1)
