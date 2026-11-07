'use strict';
let csrf='', data=null;
const el=id=>document.getElementById(id);
const fmt=n=>Number.isFinite(Number(n))?(Number(n)/1073741824).toFixed(2)+' GiB':'—';
const safeText=(id,text)=>{const node=el(id);if(node)node.textContent=String(text??'');};
let toastTimer;
function toast(text){const box=el('toast');box.textContent=text;box.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>box.classList.remove('show'),6000)}
async function request(url,body){const options=body?{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Token':csrf},body:JSON.stringify(body)}:{};const r=await fetch(url,options);const v=await r.json();if(!r.ok)throw Error(v.error||('HTTP '+r.status));return v}
function localTonight(){let d=new Date();d.setHours(21,0,0,0);if(d.getTime()<Date.now())d.setDate(d.getDate()+1);let p=x=>String(x).padStart(2,'0');return [d.getFullYear(),p(d.getMonth()+1),p(d.getDate())].join('-')+'T'+p(d.getHours())+':'+p(d.getMinutes())}
function showStatus(s){data=s;const live=s.process_alive;const paused=s.process_stopped;safeText('worker',live?(paused?'PAUSADO':'ATIVO'):'INATIVO');safeText('worker-detail',s.pid?'PID '+s.pid:'PID indisponível');safeText('stage',s.pipeline.stage||'novo');safeText('last-error',s.pipeline.status||'sem estágio final');safeText('disk',(s.disk_free_gib||0)+' GiB');const parts=s.partials||[];safeText('partial',parts.length.toString());safeText('partial-detail',fmt(parts.reduce((sum,p)=>sum+p.bytes,0))+' de temporários');safeText('log',s.log_tail||'Sem eventos registrados.');safeText('logpath',s.log_file||'');const ps=el('partials');ps.replaceChildren();if(!parts.length){const d=document.createElement('div');d.className='empty';d.textContent='Nenhum arquivo parcial encontrado';ps.append(d)}else{parts.forEach((p,i)=>{const d=document.createElement('div');d.className='partial';const a=document.createElement('strong');a.textContent=`Parte ${i+1} · ${fmt(p.bytes)}`;const b=document.createElement('small');b.textContent='Atualizado: '+p.modified;d.append(a,b);ps.append(d)})}const overlay=s.overlay||{};safeText('overlay',overlay.exists?`Cópia ativa: ${overlay.snapshot} · Mods: ${(overlay.enabled||[]).join(', ')||'nenhum'}`:'Nenhum overlay construído.');}
async function showMods(){const mods=await request('/api/mods');const root=el('mods');root.replaceChildren();if(!mods.length){const d=document.createElement('div');d.className='empty';d.textContent='Nenhum mod cadastrado';root.append(d);return}for(const m of mods){let d=document.createElement('div');d.className='mod';let info=document.createElement('div');let name=document.createElement('strong');name.textContent=m.name+' · '+m.version;let desc=document.createElement('p');desc.textContent=m.description;let files=document.createElement('code');files.textContent=m.overrides.join(' • ');info.append(name,desc,files);let btn=document.createElement('button');btn.className='switch'+(m.enabled?' on':'');btn.textContent=m.enabled?'Ativado':'Desativado';btn.addEventListener('click',async()=>{btn.disabled=true;try{await request('/api/mods/'+(m.enabled?'disable':'enable'),{id:m.id});await showMods();toast('Estado de mod atualizado. Reconstrua o overlay para aplicar.')}catch(e){toast('Erro: '+e.message)}finally{btn.disabled=false}});d.append(info,btn);root.append(d)}}
async function refresh(){try{showStatus(await request('/api/status'));await showMods()}catch(e){toast('Erro ao atualizar: '+e.message)}}
async function init(){try{const b=await request('/api/bootstrap');csrf=b.csrf;await refresh()}catch(e){toast('Falha de conexão: '+e.message)}el('refresh').addEventListener('click',refresh);el('build').addEventListener('click',async()=>{const btn=el('build');btn.disabled=true;try{const r=await request('/api/overlay/build',{});toast('Overlay construído: '+r.result.snapshot);await refresh()}catch(e){toast('Falha no build: '+e.message)}finally{btn.disabled=false}});setInterval(()=>{safeText('clock',new Date().toLocaleString('pt-BR'));},1000);setInterval(refresh,10000)}
init();

// Único painel de treinamento: todos os pesos locais, diagnóstico e jobs isolados.
let trainCatalog=[],trainJob=null,trainArtifacts=[];
const originalDatasets={alistair:'pacote_identidade_v5 / alistair',
 lilith:'pacote_identidade_v5 / lilith',hoshino:'pacote_identidade_v5 / hoshino'};
function trainControls(){
 const model=el('train-model').value, ent=el('train-entity').value;
 const row=trainCatalog.find(x=>x.id===model);
 safeText('train-source','Corpus original: '+(originalDatasets[ent]||'não encontrado')+'. Os dados de outra entidade não serão aceitos.');
 const ok=row&&row.train_enabled&&(!row.exclusive_entity||row.exclusive_entity===ent);
 el('train-start').disabled=!ok;
 el('train-check').disabled=!row;
 const note=row?.state==='oom'?'Treinamento bloqueado por OOM; o modelo e os pesos continuam catalogados.':
   row?.state==='testing_only'?'Modelo 0.8B exclusivo de testes.':
   row?.state==='smoke_ok'?'Treino experimental: dois passos aprovados, execução mais longa ainda não homologada.':
   row?.description||'';
 if(row)safeText('train-report',note);
 for(const card of el('model-cards').children)card.classList.toggle('highlight',card.dataset.id===model);
 populateArtifacts();
}
function populateArtifacts(){
 const row=trainCatalog.find(r=>r.id===el('train-model').value),entity=el('train-entity').value;
 for(const [id,field] of [['train-resume','checkpoints'],['train-candidate','path']]){
   const target=el(id),old=target.value;target.replaceChildren(new Option(field==='path'?'Selecione o candidato':'Novo treino',''));
   for(const artifact of trainArtifacts.filter(a=>a.entity===entity&&a.base===row?.path)){
     if(field==='path'&&artifact.final)target.append(new Option(artifact.path.split('/').pop(),artifact.path));
     if(field==='checkpoints')for(const ck of artifact.checkpoints)target.append(new Option(artifact.path.split('/').pop()+' / '+ck.split('/').pop(),ck));
   }
   if([...target.options].some(o=>o.value===old))target.value=old;
 }
 el('train-resume').disabled=el('train-action').value!=='train';
}
async function loadTrainCatalog(){
 const rows=await request('/api/treinos/catalog');trainCatalog=rows;
 trainArtifacts=await request('/api/treinos/artifacts');
 const select=el('train-model'),previous=select.value;select.replaceChildren();
 const container=el('model-cards');container.replaceChildren();
 for(const m of rows){
   if(!['professor-35b','qwen35-08b','qwen25-7b-local'].includes(m.id))select.append(new Option(m.label+' · '+(m.installed?'instalado':'não instalado')+' · '+m.state,m.id));
   if(m.id==='qwen25-7b-local')continue;
   const card=document.createElement('div');card.className='candidate';card.dataset.id=m.id;
   const title=document.createElement('strong');title.textContent=m.label;
   const flags=document.createElement('div');flags.className='traits';flags.textContent=(m.bytes/1073741824).toFixed(2)+' GiB · '+(m.architecture||'arquitetura não lida');
   const desc=document.createElement('p');desc.textContent=m.description;
   const detail=document.createElement('p');detail.textContent=m.installed?'Peso HF/GGUF detectado · '+m.shards+' arquivo(s)':'Pesos ausentes/incompletos';
   if(m.id==='qwen25-7b'){const alt=rows.find(x=>x.id==='qwen25-7b-local');if(alt?.installed){const note=document.createElement('p');note.textContent='Também no SSD: formato local quantizado ('+(alt.bytes/1073741824).toFixed(2)+' GiB), utilizado separadamente para inferência; não é segunda cópia HF treinável.';card.append(note);}}
   card.append(title,flags,desc,detail);
   if(!['professor-35b','qwen35-08b','qwen25-7b-local'].includes(m.id))card.onclick=()=>{select.value=m.id;trainControls()};container.append(card);
 }
 if(rows.some(x=>x.id===previous))select.value=previous;
 else if(rows.some(x=>x.id==='alistair-4b'))select.value='alistair-4b';
 trainControls();
}
function chosenTrain(){return {model:el('train-model').value,entity:el('train-entity').value,
  minutes:Number(el('train-minutes').value),action:el('train-action').value,
  checkpoint:el('train-action').value==='train'?(el('train-resume').value||null):null,
  candidate:el('train-action').value==='evaluate'?(el('train-candidate').value||null):null}}
async function loadTrainingDatasets(){
 const entity=el('train-entity').value,rows=await request('/api/treinos/datasets?entity='+encodeURIComponent(entity));
 if(entity!==el('train-entity').value)return;
 const select=el('train-dataset'),old=select.value;select.replaceChildren();
 for(const d of rows)select.append(new Option(d.label+' · '+(d.original?'original':'curadoria aprovada'),d.id));
 if([...select.options].some(o=>o.value===old))select.value=old;
}
async function previewTrain(){
 const p=await request('/api/treinos/preview',{...chosenTrain(),dataset:el('train-dataset').value||null});
 safeText('train-report',JSON.stringify(p.result,null,2));return p.result;
}
async function previewRecovery(){
 const out=await request('/api/treinos/recovery-preview',{model:el('train-model').value,entity:el('train-entity').value});
 const p=out.result;
 safeText('recovery-report',(p.needed?'Executor ausente. ':'Já instalado; não será substituído. ')
   +(p.source?'Fonte: '+p.source.kind+' · '+p.source.hf_origin+'\n':'')
   +(p.needed?'Espaço exigido: '+(p.required_bytes/1073741824).toFixed(1)+' GiB; livre: '+(p.free_bytes/1073741824).toFixed(1)+' GiB.\n':'')
   +(p.allowed?'Plano permitido.':'Bloqueado: '+(p.blocker||'espaço insuficiente.'))
   +(p.activate?'\nAtiva após conversão, importação e probe completos.':
      p.model_id==='yi-6b'?'\nNão habilita executor experimental.':'\nMantém a seleção atual.'));
 return p;
}
async function launchRecovery(){
 const p=await previewRecovery();if(!p.needed){toast('Executor já instalado; nada alterado.');return}
 if(!p.allowed)throw Error('Plano bloqueado; não converter.');
 if(!confirm('Reconstruir '+p.model_id+' para '+p.entity+' a partir de pesos locais?\n'
  +'Última estável aprovada tem preferência; original preservado. Nenhum download ou treino.'))return;
 const out=await request('/api/treinos/recovery-start',{model:p.model_id,entity:p.entity,confirm:'EXECUTAR_RECUPERACAO_LOCAL'});
 trainJob=out.result.id||null;toast('Recuperação: '+out.result.state);await refreshTrainJobs();
}
async function launchTrain(){
 const p=await previewTrain();if(!p.allowed)throw Error(p.blocker);
 if(!confirm('Iniciar '+p.action+' com '+p.model.label+' para '+p.entity+'?\n'
     +'Dataset: '+p.train+'\nDuração até '+p.minutes+' min. GPU ocupada; sem deploy.'))return;
 const v=await request('/api/treinos/start',{...chosenTrain(),dataset:el('train-dataset').value||null,confirm:'EXECUTAR_TREINO_UNIFICADO'});
 trainJob=v.result.id;toast('Job iniciado: '+trainJob);await refreshTrainJobs();
}
async function refreshTrainJobs(){
 try{
   const list=await request('/api/treinos/jobs');
   if(!trainJob&&list.length)trainJob=list[0].id;
   if(!trainJob)return;
   const job=await request('/api/treinos/job?id='+encodeURIComponent(trainJob));
   const out={id:job.id,state:job.state,entity:job.entity,model:job.model,action:job.action,
     minutes:job.minutes,progress:job.progress||null,error:job.error||null,
     previous_error:job.previous_error||null,operator_verification:job.operator_verification||null,
     receipt:job.artifact||null};
   safeText('train-report',JSON.stringify(out,null,2)+'\n\n'+(job.log_tail||''));
   const active=['started','running','cancel_requested'].includes(job.state);
   el('train-stop').disabled=!active||job.state==='cancel_requested';
   const chosen=trainCatalog.find(x=>x.id===el('train-model').value);
   el('train-start').disabled=active || !chosen?.train_enabled ||
       !!(chosen.exclusive_entity&&chosen.exclusive_entity!==el('train-entity').value);
 }catch(e){safeText('train-report','Falha ao consultar treino: '+e.message)}
}
async function stopTrain(){
 if(!trainJob)return;
 const job=await request('/api/treinos/job?id='+encodeURIComponent(trainJob));
 const message=job.action==='recover'?'Cancelar recuperação local cooperativamente? Artefatos e recibos serão preservados; não garante executor pronto.':
   'Pedir parada cooperativa e checkpoint após o update atual? Aguarde confirmação; crash/OOM não garante snapshot válido.';
 if(!confirm(message))return;
 await request('/api/treinos/stop',{id:trainJob,confirm:'PARAR_TREINO_UNIFICADO'});
 await refreshTrainJobs();
}
for(const id of ['train-model','train-entity','train-minutes','train-action'])el(id).addEventListener('change',trainControls);
el('train-entity').addEventListener('change',()=>loadTrainingDatasets().catch(e=>toast(e.message)));
el('train-check').onclick=()=>previewTrain().catch(e=>safeText('train-report','Plano recusado: '+e.message));
el('train-start').onclick=()=>launchTrain().catch(e=>toast('Treino não iniciado: '+e.message));
el('train-stop').onclick=()=>stopTrain().catch(e=>toast('Parada recusada: '+e.message));
el('train-refresh').onclick=()=>Promise.all([loadTrainCatalog(),refreshTrainJobs()]);
el('recovery-check').onclick=async()=>{try{await previewRecovery()}catch(e){safeText('recovery-report',e.message)}};
el('recovery-start').onclick=async()=>{try{await launchRecovery()}catch(e){safeText('recovery-report',e.message)}};
for(const [id,url,label] of [['train-review','review','Você leu a loss completa e as respostas da recarga e aprova a qualidade?'],['train-promote','promote','Registrar candidato homologado como estável SOMENTE no laboratório?'],['train-rollback','rollback','Restaurar referência estável anterior, preservando todos os adaptadores?']]){
 el(id).onclick=async()=>{if(!confirm(label))return;try{
   const result=await request('/api/treinos/'+url,{...chosenTrain(),candidate:el('train-candidate').value,
     report:el('train-evaluation').value,confirm:true});safeText('train-report',JSON.stringify(result,null,2));
 }catch(e){toast('Operação recusada: '+e.message)}};
}
el('train-auto-promote').onclick=async()=>{try{
 const out=await request('/api/treinos/auto-promote',{entity:el('train-entity').value,model:el('train-model').value,
   candidate:el('train-candidate').value,report:el('train-evaluation').value});
 safeText('train-report',JSON.stringify(out.result,null,2));
}catch(e){toast('Promoção recusada: '+e.message)}};
el('profile-capture').onclick=async()=>{try{
 if(!confirm('Criar snapshot privado para curadoria, incluindo somente as experiências selecionadas? Nenhum treino será iniciado.'))return;
 const entity=el('profile-entity').value,refs=JSON.parse(el('profile-refs').value);
 const out=await request('/api/personalizacao/capture',{entity,refs,confirm:true});
 safeText('profile-report',JSON.stringify(out.result,null,2));el('moe-entity').value=entity;
 await refreshPersonalizacao();el('moe-profile').value=out.result.name;
}catch(e){toast('Perfil: '+e.message)}};
el('night-start').onclick=async()=>{if(!confirm('Você vai dormir e autoriza suspender as entidades durante esta janela?'))return;
 try{const professor=moeJobs.find(j=>j.id===el('night-teacher').value);
 const task=professor?{action:'curate',id:professor.id,entity:professor.entity,minutes:60}:
                     {...chosenTrain(),dataset:el('train-dataset').value||null};
 const result=await request('/api/night/start',{confirm:'VOU_DORMIR_AUTORIZO_LABORATORIO',
   window_minutes:Number(el('night-window').value),tasks:[task]});safeText('night-report',JSON.stringify(result,null,2));}
 catch(e){toast('Sessão não autorizada: '+e.message)}};
el('night-stop').onclick=async()=>{if(!confirm('Parar/recuperar sessão sem repetir treinos?'))return;
 try{safeText('night-report',JSON.stringify(await request('/api/night/stop',{confirm:true}),null,2));}catch(e){toast(e.message)}};
el('night-refresh').onclick=async()=>{try{safeText('night-report',JSON.stringify(await request('/api/night'),null,2));}catch(e){safeText('night-report','Central indisponível: '+e.message)}};
let nightPolicyLoaded=false;
el('night-auto-read').onclick=async()=>{try{
 nightPolicyLoaded=false;el('night-auto-save').disabled=true;
 const out=await request('/api/night/config'),p=out.settings;
 el('night-auto-time').value=p.start_time;el('night-auto-idle').value=p.idle_minutes;
 el('night-auto-window').value=p.window_minutes;el('night-auto-train').value=p.train_minutes;
 el('night-auto-enabled').checked=p.enabled;el('night-auto-absence').checked=p.allow_idle;
 el('night-auto-ai').checked=p.automatic_data_approval===true;
 el('night-auto-poweroff').checked=p.shutdown_after;
 nightPolicyLoaded=true;el('night-auto-save').disabled=false;
 safeText('night-auto-report',JSON.stringify(out,null,2));
}catch(e){safeText('night-auto-report','Central indisponível: '+e.message)}};
el('night-auto-save').onclick=async()=>{try{
 if(!nightPolicyLoaded)throw Error('Consulte a configuração salva antes de alterá-la.');
 if(!confirm(el('night-auto-ai').checked?'Autorizar automação por IA? Pode propor/aprovar dados, treinar e promover após os gates. Pesos originais são preservados.':'Salvar com automação por IA desativada? Treinos manuais permanecem disponíveis.'))return;
 const out=await request('/api/night/config',{confirm:true,settings:{start_time:el('night-auto-time').value,
  idle_minutes:Number(el('night-auto-idle').value),window_minutes:Number(el('night-auto-window').value),
  train_minutes:Number(el('night-auto-train').value),enabled:el('night-auto-enabled').checked,
  allow_idle:el('night-auto-absence').checked,shutdown_after:el('night-auto-poweroff').checked,
  automatic_data_approval:el('night-auto-ai').checked}});
 safeText('night-auto-report',JSON.stringify(out.result,null,2));
}catch(e){toast('Rotina recusada: '+e.message)}};
// Consulta somente leitura: não renderizar defaults como se fossem política real.
el('night-auto-read').onclick();
let preparedLong=null;
let customChecked=null;
const customRequest=()=>({starts_at:el('custom-start').value,ends_at:el('custom-end').value,evaluation_minutes:Number(el('custom-eval').value)});
const customDate=value=>new Date(value*1000).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo'});
function customSummary(p,showStatus=true){
 if(!p)return 'Nenhum agendamento registrado.';
 const states={not_scheduled:'Nenhum agendamento',scheduled:'Agendado',attempting:'Início em verificação',started:'Em execução',blocked:'Bloqueado',cancelled:'Cancelado',finished:'Encerrado'};
 if(p.plan)return ['Agendamento: '+p.id,'Estado: '+(states[p.state]||p.state),customSummary(p.plan,false),p.session_id?'Sessão: '+p.session_id:'',p.error||''].filter(Boolean).join('\n');
 if(!p.tasks)return states[p.state]||('Estado: '+p.state);
 return [showStatus?(p.allowed?'Pronto para agendar · rodada experimental':'Partida bloqueada'):'',
  'Início: '+customDate(p.starts_at)+' · fim: '+customDate(p.ends_at),
  'Sete modelos · '+p.train_minutes_per_model+'min de treino e até '+p.evaluation_minutes_per_model+'min de avaliação por modelo',
  'Reserva para carga e encerramento: '+p.reserve_minutes+'min',
  'A validação e o limite de 3 passagens pelo material podem encerrar antes. Candidatos aguardam avaliação.',
  ...(p.blockers||[])].filter(Boolean).join('\n');
}
for(const id of ['custom-start','custom-end','custom-eval'])el(id).addEventListener('input',()=>{customChecked=null;el('custom-schedule').disabled=true;});
el('custom-preview').onclick=async()=>{try{
 const data=customRequest(),out=await request('/api/treinos/prepare-custom',data);
 customChecked=out.result?.allowed?JSON.stringify(data):null;
 safeText('custom-report',customSummary(out.result));el('custom-schedule').disabled=!customChecked;
}catch(e){customChecked=null;el('custom-schedule').disabled=true;safeText('custom-report',e.message)}};
el('custom-schedule').onclick=async()=>{const data=customRequest();
 if(customChecked!==JSON.stringify(data)||!confirm('Agendar UMA sessão nos horários informados, pausando entidades e preservando originais? Central deve ficar aberta.'))return;
 el('custom-schedule').disabled=true;customChecked=null;
 try{const out=await request('/api/night/schedule-once',{...data,confirm:'AGENDAR_TRES_ORIGINAIS'});safeText('custom-report',customSummary(out.result));}
 catch(e){safeText('custom-report','Não repetir automaticamente. Consulte o agendamento: '+e.message)}
};
el('custom-status').onclick=async()=>{try{
 const out=await request('/api/night/schedule-once');safeText('custom-report',customSummary(out));
 customChecked=null;el('custom-schedule').disabled=true;
 if(out.request){el('custom-start').value=out.request.starts_at;el('custom-end').value=out.request.ends_at;el('custom-eval').value=out.request.evaluation_minutes;}
}catch(e){safeText('custom-report',e.message)}};
el('custom-cancel').onclick=async()=>{if(!confirm('Cancelar somente o agendamento pendente?'))return;try{const out=await request('/api/night/cancel-schedule',{confirm:true});safeText('custom-report',customSummary(out.result))}catch(e){safeText('custom-report',e.message)}};
el('custom-status').onclick();
el('long-prepare').onclick=async()=>{try{
 preparedLong=await request('/api/treinos/prepare-12h',{});
 safeText('long-report',JSON.stringify(preparedLong,null,2));el('long-start').disabled=!preparedLong.allowed;
}catch(e){toast(e.message)}};
el('long-resume').onclick=async()=>{try{
 const p=await request('/api/night/resume-preview',{});
 preparedLong={...p,allowed:true,window_minutes:Number(el('night-window').value)};
 safeText('long-report',JSON.stringify(preparedLong,null,2));el('long-start').disabled=false;
}catch(e){toast(e.message)}};
el('long-start').onclick=async()=>{
 if(!preparedLong?.allowed||!confirm('AUTORIZAÇÃO NOVA: vou dormir e autorizo este plano sequencial prolongado. Bases intactas; candidatos não promovidos. Continuar?'))return;
 try{safeText('night-report',JSON.stringify(await request('/api/night/start',{
   confirm:'VOU_DORMIR_AUTORIZO_LABORATORIO',window_minutes:preparedLong.window_minutes,tasks:preparedLong.tasks}),null,2));
 }catch(e){toast('Plano não iniciou: '+e.message)}
};
Promise.all([loadTrainCatalog(),loadTrainingDatasets()]).then(refreshTrainJobs).catch(e=>toast('Catálogo: '+e.message));
setInterval(()=>{if(!document.hidden)refreshTrainJobs()},10000);

// Curadoria MoE v0.6. Nenhum GET prepara/autoriza inferência.
let moeJobs=[],moeCorpus=[],moeReview=null,moeOwnedDatasets={};
async function refreshPersonalizacao(){
  try{
    const data=await request('/api/personalizacao/status');
    const root=el('personalizacao-cards');root.replaceChildren();
    const choice=el('moe-source-dataset');const previous=choice.value;choice.replaceChildren();
    const entity=el('moe-entity').value;
    moeOwnedDatasets=Object.fromEntries(data.entities.map(e=>[e.id,e.datasets]));
    const owner=data.entities.find(x=>x.id===entity);
    const profile=el('moe-profile'),oldProfile=profile.value;profile.replaceChildren(new Option('Somente corpus de referência (legado)',''));
    for(const p of owner?.cognitive_profiles||[]){const option=new Option(p.valid===false?p.name+' · INVÁLIDO: '+p.error:p.name+' · '+p.traits+' traços · '+p.experiences+' experiências',p.name);option.disabled=p.valid===false;profile.append(option)}
    if([...profile.options].some(o=>o.value===oldProfile))profile.value=oldProfile;
    const canonical='pacote_identidade_v5:'+entity;
    for(const d of owner?.datasets||[]){if(d.id===canonical)choice.append(new Option(d.label+' · ORIGINAL PRINCIPAL',d.id))}
    if([...choice.options].some(o=>o.value===previous))choice.value=previous;
    el('moe-dataset-prepare').disabled=!choice.options.length;
    for(const e of data.entities){
      const card=document.createElement('div');card.className='identity-card';
      const h=document.createElement('h3');h.textContent=e.name;
      const ds=document.createElement('p');ds.textContent='Datasets vinculados: '+e.datasets.length;
      const jobs=document.createElement('p');jobs.textContent='Treinos registrados: '+e.training_jobs;
      const proposals=document.createElement('p');proposals.textContent='Trabalhos do professor: '+e.teacher_jobs;
      const last=document.createElement('p');last.textContent='Último treino: '+(e.last_training?.state||'não registrado');
      const stable=document.createElement('p');stable.textContent='Estáveis no laboratório: '+((e.stable_versions||[]).filter(x=>x.available).map(x=>x.model).join(', ')||'nenhuma homologada');
      const failures=(e.stable_versions||[]).filter(x=>x.error);
      if(failures.length)stable.textContent+=' · erro: '+failures.map(x=>x.error).join('; ');
      const btn=document.createElement('button');btn.className='secondary';btn.textContent='Selecionar para treinar';
      btn.onclick=async()=>{try{el('train-entity').value=e.id;await loadTrainingDatasets();trainControls();el('modelos').scrollIntoView({behavior:'smooth'});}catch(err){toast('Corpus: '+err.message)}};
      card.append(h,ds,jobs,proposals,last,stable,btn);root.append(card);
    }
  }catch(e){toast('Personalização: '+e.message)}
}
async function refreshSnapshots(){
  try{
    const entity=el('moe-entity').value;
    const items=await request('/api/professor-moe/snapshots?entity='+encodeURIComponent(entity));
    if(entity!==el('moe-entity').value)return;
    const select=el('moe-snapshot');select.replaceChildren();
    const blank=new Option(items.length?'Selecione um snapshot validado':'Nenhum snapshot autorizado', '');select.append(blank);
    for(const s of items)select.append(new Option(s.name+' · '+s.rows+' registros',s.name));
    el('moe-prepare').disabled=!items.length;
  }catch(e){toast('Snapshots: '+e.message)}
}
async function refreshMoe(){
  try{
    const [status,jobs]=await Promise.all([request('/api/professor-moe/status'),request('/api/professor-moe/jobs')]);
    moeJobs=jobs;
    const night=el('night-teacher'),old=night.value;night.replaceChildren(new Option('Usar treinamento selecionado',''));
    for(const j of jobs.filter(j=>j.state==='prepared'&&j.purpose!=='candidate_review'))night.append(new Option(j.entity+' · '+j.id+' · '+j.evidence_count+' evidências',j.id));
    if([...night.options].some(o=>o.value===old))night.value=old;
    safeText('moe-state',status.ready?'GGUF detectado':'Download ausente/incompleto');
    safeText('moe-size',((status.size_bytes||0)/1e9).toFixed(2)+' GB · '+status.integrity);
    safeText('moe-executor',status.executor_ready?'Vulkan disponível':'Vulkan ausente');
    safeText('moe-running',jobs.some(j=>['running','started'].includes(j.state))?'Em execução':'Aguardando autorização');
    const root=el('moe-jobs');root.replaceChildren();
    if(!jobs.length){const p=document.createElement('p');p.className='empty';p.textContent='Nenhuma tarefa preparada';root.append(p);return;}
    for(const j of jobs){
      const row=document.createElement('div');row.className='job-row';const info=document.createElement('div');
      const title=document.createElement('strong');title.textContent=j.entity+' · '+(j.purpose==='reference_examples'?(j.reference_origin==='teacher_probe'?'Diálogos do professor para revisar':'Referências autorais'):j.snapshot||'Proposta')+' · '+j.state;
      const detail=document.createElement('small');detail.textContent=j.id+' · '+(j.mode==='heavy_10k'?'TESTE PESADO 10K · ':j.mode==='max_dynamic'?'QUALIDADE MÁXIMA · ':'')+j.evidence_count+' evidências'+(j.progress_target?' · '+(j.progress_generated||0)+'/'+j.progress_target+' pares gerados · '+(j.batches_completed||0)+' lotes verificados':'')+(j.error?' · '+j.error:'');
      info.append(title,detail);row.append(info);
      const see=document.createElement('button');see.className='secondary';see.textContent='Ver detalhes';
      see.onclick=async()=>{try{const d=await request('/api/professor-moe/detail?id='+encodeURIComponent(j.id));el('moe-review-result').textContent=d.log_tail||'Sem log de inferência';if(d.proposal_data)showMoeReview(d);else{el('moe-review').hidden=false;el('moe-review-items').replaceChildren();safeText('moe-review-note','Estado: '+d.state+(d.error?' — '+d.error:''));el('moe-export').disabled=true;}}catch(e){toast(e.message)}};
      row.append(see);
      if(j.state==='prepared'){
        const run=document.createElement('button');run.textContent='Autorizar execução GPU';
        run.disabled=!status.ready||!status.executor_ready;
        run.onclick=async()=>{if(!confirm('Carregar Qwen3.5-35B-A3B na RX 6650 XT e gerar proposta para '+j.entity+'? Executará SOMENTE inferência e encerrará após a sessão.'))return;try{await request('/api/professor-moe/run',{id:j.id,confirm:true});toast('Professor autorizado: '+j.id);await refreshMoe()}catch(e){toast('Professor: '+e.message)}};
        row.append(run);
      }
      if(['running','started'].includes(j.state)){
        const stop=document.createElement('button');stop.className='secondary';stop.textContent='Encerrar professor';
        stop.onclick=async()=>{if(!confirm('Interromper somente o trabalho do professor '+j.id+'?'))return;try{await request('/api/professor-moe/stop',{id:j.id,confirm:true});toast('Parada solicitada');await refreshMoe()}catch(e){toast(e.message)}};
        row.append(stop);
      }
      if(['prepared','failed','needs_revision','proposed','cancelled'].includes(j.state)){
        const del=document.createElement('button');del.className='secondary';del.textContent='Excluir proposta';
        del.onclick=async()=>{
          if(!confirm('Descartar a proposta '+j.id+' do menu? Os datasets originais e trabalhos exportados ficam intactos. Registro preservado para auditoria.'))return;
          try{await request('/api/professor-moe/discard-job',{id:j.id,confirm:true});
            if(moeReview?.id===j.id){moeReview=null;el('moe-review').hidden=true;}
            await refreshMoe();toast('Proposta descartada.');}catch(e){toast('Descarte: '+e.message)}
        };row.append(del);
      }
      root.append(row);
    }
  }catch(e){toast('Professor MoE: '+e.message)}
}
async function showMoeReview(detail){
  moeReview=detail;el('moe-review').hidden=false;
  const p=detail.proposal_data;
  const audit=p.quality_audit;
  if(p.purpose==='candidate_review'){
    const list=el('moe-review-items');list.replaceChildren();
    safeText('moe-review-note',detail.entity+' · crítica independente da candidata · '+detail.state+
      ' · '+(audit?.passed?'contratos sem objeções':'NÃO aprovada')+' · naturalidade humana ainda pendente');
    for(const row of p.reviews||[]){const item=document.createElement('p');
      item.textContent=row.source_id+' · '+(row.concerns.length?row.concerns.join(', '):'sem objeções')+' · '+row.reason;list.append(item);}
    el('moe-export').disabled=true;
    safeText('moe-review-result','Esta crítica não é corpus de treinamento. Consulte a avaliação da candidata para saber se foi promovida.');
    el('moe-review').scrollIntoView({behavior:'smooth',block:'nearest'});return;
  }
  const reference=p.purpose==='reference_examples';
  const stale=audit&&detail.quality_filter_version_current&&audit.filter_version!==detail.quality_filter_version_current;
  safeText('moe-review-note',detail.entity+' · '+(reference?(p.authored_by==='local_professor'?'DIÁLOGOS GERADOS PELO PROFESSOR · NÃO SÃO TREINO · ':'RASCUNHOS AUTORAIS · NÃO SÃO TREINO · '):'' )+p.reason+' · '+p.status+(audit?' · FILTRO REGISTRADO '+(audit.passed?'PASSOU (REVISÃO HUMANA PENDENTE)':'NÃO APROVOU O LOTE')+' · categorias '+(audit.categories||[]).length+' · '+(audit.filter_version||'filtro antigo; seleção será revalidada antes de exportar')+(stale?' · PARECER ANTIGO: o filtro atual '+detail.quality_filter_version_current+' revalidará a seleção antes de exportar.':''):''));
  const list=el('moe-review-items');list.replaceChildren();
  for(const ex of p.examples){
    const label=document.createElement('article');label.className='review-example';label.dataset.sourceId=ex.source_id;
    const saved=p.human_reviews?.[ex.source_id];
    const decision=saved?.example_sha256===detail.example_hashes?.[ex.source_id]?saved.decision:'pending';
    const box=document.createElement('input');box.type='checkbox';box.value=ex.source_id;box.dataset.export='true';
    box.checked=decision==='approved';box.disabled=reference||decision!=='approved'||!!detail.export;
    const title=document.createElement('strong');title.textContent=ex.source_id+' · '+ex.category;
    const state=document.createElement('p');state.className='review-decision '+decision;
    state.textContent=saved?.reviewer==='codex_assisted'&&decision!=='pending'?
      (decision==='approved'?'APROVADO':'REPROVADO')+' · CURADORIA ASSISTIDA AUTORIZADA':
      {approved:'APROVADO POR VOCÊ',rejected:'REPROVADO POR VOCÊ',pending:'AGUARDANDO SUA REVISÃO'}[decision];
    const assistant=document.createElement('p');assistant.style.whiteSpace='pre-wrap';
    assistant.textContent=ex.messages?ex.messages.map(m=>m.role.toUpperCase()+': '+m.content).join('\n'):'RESPOSTA PROPOSTA: '+ex.assistant;
    const reason=document.createElement('small');reason.textContent='Justificativa: '+ex.reason;
    const note=document.createElement('textarea');note.rows=2;note.maxLength=1000;
    note.placeholder='Seu comentário (obrigatório ao reprovar)';note.value=saved?.note||'';note.setAttribute('aria-label','Motivo da revisão de '+ex.source_id);
    const reuse=document.createElement('label');reuse.className='micro';
    const reuseBox=document.createElement('input');reuseBox.type='checkbox';reuseBox.checked=reference||saved?.as_reference===true;
    reuse.append(reuseBox,document.createTextNode(' Usar como referência de comportamento após aprovação (somente esta entidade)'));
    const actions=document.createElement('div');actions.className='experiment-actions';
    for(const [value,text] of [['approved','Aprovar'],['rejected','Reprovar'],['pending','Deixar pendente']]){
      const button=document.createElement('button');button.type='button';button.textContent=text;button.className=value==='approved'?'':'secondary';button.disabled=!!detail.export;
      button.onclick=async()=>{try{
        if(value==='rejected'&&!note.value.trim())throw Error('Escreva o motivo da reprovação.');
        const result=await request('/api/professor-moe/review-example',{id:detail.id,source_id:ex.source_id,decision:value,
          note:note.value,as_reference:reuseBox.checked,expected_hash:detail.example_hashes[ex.source_id],confirm:true});
        await showMoeReview(await request('/api/professor-moe/detail?id='+encodeURIComponent(detail.id)));
        toast('Decisão salva. Nenhum treino iniciado.');
      }catch(e){toast('Curadoria: '+e.message)}};actions.append(button);
    }
    if(p.contrasts?.[ex.source_id]){const contrast=document.createElement('details'),summary=document.createElement('summary'),text=document.createElement('p');
      summary.textContent='Comparar com uma resposta inadequada';text.textContent=p.contrasts[ex.source_id];contrast.append(summary,text);label.append(contrast);}
    if(audit){const technical=document.createElement('p');technical.className='micro';
      const matching=field=>(audit[field]||[]).filter(b=>b.example_hashes?.[ex.source_id]===detail.example_hashes?.[ex.source_id])
        .flatMap(b=>b.reviews||[]).filter(r=>r.source_id===ex.source_id).at(-1);
      const integrity=matching('teacher_semantic_reviews'),quality=matching('conversation_reviews');
      technical.textContent='Integridade: '+(integrity?integrity.reason:'não comprovada neste parecer')+
        ' · Conversação: '+(quality?Object.entries(quality.scores).map(([k,v])=>k+' '+v+'/4').join(' · ')+' — '+quality.reason:'revisão humana necessária');label.append(technical);}
    const del=document.createElement('button');del.className='secondary';del.type='button';del.textContent='Excluir exemplo';
    del.onclick=async(ev)=>{ev.preventDefault();ev.stopPropagation();
      if(!confirm('Retirar este exemplo da proposta ativa? O original ficará no histórico de auditoria, sem alterar datasets.'))return;
      try{await request('/api/professor-moe/discard-examples',{id:detail.id,source_ids:[ex.source_id],confirm:true});
        const revised=await request('/api/professor-moe/detail?id='+encodeURIComponent(detail.id));
        if(revised.proposal_data)showMoeReview(revised);
        else{el('moe-review').hidden=true;moeReview=null;}
        await refreshMoe();toast('Exemplo removido da proposta ativa.');
      }catch(e){toast('Exclusão: '+e.message)}
    };
    label.prepend(box,title,state,assistant,reason,note,reuse,actions);
    if(!reference&&!detail.export)label.append(del);list.append(label);
  }
  try{moeCorpus=moeOwnedDatasets[detail.entity]||[]}catch(e){moeCorpus=[]}
  const base=el('moe-base');base.replaceChildren();
  for(const d of moeCorpus){
    if(d.id==='pacote_identidade_v5:'+detail.entity||
       d.id.startsWith('importados:')){
      base.append(new Option(d.label,d.id));
    }
  }
  el('moe-export').disabled=reference||!!detail.export||!['proposed','needs_revision'].includes(detail.state)||!p.examples.length||!base.options.length;
  el('moe-review-result').textContent=detail.export?'Dataset criado: '+detail.export:reference?'Aprovar vale para o diálogo inteiro. Se gostou só de uma fala, deixe pendente e indique qual no comentário. As referências aprovadas orientam futuras gerações; não podem ser exportadas como treino.':'Aprove cada exemplo e depois selecione os que deseja exportar. Reprovação não apaga evidências; os gates técnicos continuam obrigatórios.';
  el('moe-review').scrollIntoView({behavior:'smooth',block:'nearest'});
}
async function initMoe(){
  el('moe-references').onclick=async()=>{try{
    const r=await request('/api/professor-moe/references',{entity:el('moe-entity').value,confirm:true});
    await showMoeReview(r.result);await refreshMoe();
  }catch(e){toast('Referências: '+e.message)}};
  el('moe-entity').addEventListener('change',async()=>{await Promise.all([refreshSnapshots(),refreshPersonalizacao()])});
  el('moe-refresh').onclick=async()=>{await Promise.all([refreshMoe(),refreshPersonalizacao(),refreshSnapshots()])};
  el('moe-dataset-prepare').onclick=async()=>{try{
    const entity=el('moe-entity').value,dataset=el('moe-source-dataset').value;
    if(!dataset)throw Error('Selecione um corpus da entidade');
    const limit=Number(el('moe-sample-count').value),mode='max_dynamic';
    const res=await request('/api/professor-moe/prepare-dataset',{entity,dataset,limit,mode,profile:el('moe-profile').value||null});
    toast('Preparado: '+res.result.included+' casos, '+(res.result.duplicate_variations_filtered||0)+' variações repetidas filtradas. Professor ainda desligado.');
    await Promise.all([refreshMoe(),refreshSnapshots()]);
  }catch(e){toast('Preparação do dataset: '+e.message)}};
  el('moe-prepare').onclick=async()=>{try{
    const entity=el('moe-entity').value,snapshot=el('moe-snapshot').value,mode='max_dynamic';
    if(!snapshot)throw Error('Selecione um snapshot');
    const r=await request('/api/professor-moe/prepare',{entity,snapshot,mode,profile:el('moe-profile').value||null});
    toast('Preparado sem inferência: '+r.result.id);await refreshMoe();
  }catch(e){toast('Preparação: '+e.message)}};
  el('moe-export').onclick=async()=>{try{
    if(!moeReview?.proposal_data)throw Error('Escolha uma proposta');
    const ids=Array.from(el('moe-review-items').querySelectorAll('input[data-export]:checked:not(:disabled)'),i=>i.value);
    if(ids.length<2)throw Error('Aprovação exige pelo menos dois exemplos');
    const base=el('moe-base').value;
    if(!confirm('Aprovar '+ids.length+' exemplos para '+moeReview.entity+' e criar novo corpus de treinamento? Nada será treinado automaticamente.'))return;
    const res=await request('/api/professor-moe/export',{id:moeReview.id,approved_ids:ids,base_dataset:base,confirm:true});
    safeText('moe-review-result',JSON.stringify(res.result,null,2));
    toast('Dataset derivado criado: '+res.result.dataset);
    await Promise.all([loadTrainCatalog(),refreshMoe(),refreshPersonalizacao()]);
    el('train-entity').value=moeReview.entity;trainControls();await loadTrainingDatasets();
    el('train-dataset').value=res.result.dataset;
  }catch(e){toast('Revisão: '+e.message)}};
  await Promise.all([refreshMoe(),refreshSnapshots(),refreshPersonalizacao()]);
  const reviewId=new URLSearchParams(location.search).get('review');
  if(reviewId){
    if(!/^[a-f0-9]{16}$/.test(reviewId))toast('Identificador de revisão inválido.');
    else try{const detail=await request('/api/professor-moe/detail?id='+reviewId);
      if(!detail.proposal_data)throw Error('Proposta indisponível para revisão.');
      await showMoeReview(detail);
    }catch(e){toast('Revisão: '+e.message)}
  }
  setInterval(()=>{if(!document.hidden)refreshMoe().catch(()=>{})},15000);
  setInterval(()=>{if(!document.hidden)refreshPersonalizacao().catch(()=>{})},60000);
}
initMoe();

// Presets auto v1.0 — consulta read-only; nunca executa treino por GET.
async function refreshAutoPresets(){
  const display=document.getElementById('auto-preset-report');
  if(!display)return;
  try{
    const result=await request('/api/presets-auto');
    const summary={method:result.method,status:result.status,limits:result.limitations,entities:{}};
    for(const entity of ['hoshino','lilith']){
      const row=result.entities?.[entity]||{};
      summary.entities[entity]={calibrated:!!row.calibrated,selected:row.selected||null,
        signature_matches:row.signature_matches??null,created:row.created||null,
        warnings:row.warnings||[],runs:(row.runs||[]).map(r=>({rank:r.rank,
          max_length:r.max_length,ok:!!r.ok,steps:r.steps,peak_vram_gib:r.peak_vram_gib,
          after_val_loss:r.after_val_loss,val_improvement:r.val_improvement,
          steps_per_second:r.steps_per_second}))};
    }
    display.textContent=JSON.stringify(summary,null,2);
  }catch(e){display.textContent='Não foi possível consultar os presets: '+e.message;}
}

refreshAutoPresets();
