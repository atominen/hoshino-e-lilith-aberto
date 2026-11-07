/* A UI é uma projeção descartável das APIs locais. Não confirma ações. */
'use strict';
const control = (() => {
  const names = {hoshino:'Hoshino',lilith:'Lilith',alistair:'Alistair'};
  const pages = ['Conversa','Entidades','Atividade','Memória do chat','Memórias','Modelos','Laboratório Neural','Áudio','Recursos','Ferramentas','Serviços','Configurações','Diagnóstico'];
  const panels = new Map();
  let active='Conversa',modelGeneration=0;
  let memoryAccess='',memoryEntity='',memoryExpires=0,memoryEpoch=0,memoryTimer=null;
  const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el};
  // Opções só mudam por escolha explícita; roda/touchpad continuam rolando.
  document.addEventListener('wheel',event=>{
    const field=event.target instanceof Element?event.target.closest('select,input:is([type=number],[type=range],[type=date],[type=time],[type=datetime-local],[type=month],[type=week])'):null;
    if(!field)return;
    event.preventDefault();
    const scale=event.deltaMode===1?16:event.deltaMode===2?innerHeight:1;
    const dx=event.deltaX*scale,dy=event.deltaY*scale;
    for(let parent=field.parentElement;parent;parent=parent.parentElement){
      const style=getComputedStyle(parent);
      const y=/(auto|scroll)/.test(style.overflowY)&&parent.scrollHeight>parent.clientHeight&&
        (dy<0?parent.scrollTop>0:dy>0&&parent.scrollTop+parent.clientHeight<parent.scrollHeight);
      const x=/(auto|scroll)/.test(style.overflowX)&&parent.scrollWidth>parent.clientWidth&&
        (dx<0?parent.scrollLeft>0:dx>0&&parent.scrollLeft+parent.clientWidth<parent.scrollWidth);
      if(x||y){parent.scrollBy({left:dx,top:dy,behavior:'instant'});return}
    }
    window.scrollBy({left:dx,top:dy,behavior:'instant'});
  },{capture:true,passive:false});
  const nav=node('nav',null,'sidebar');nav.setAttribute('aria-label','Central');
  const brand=node('div','H · L · A','brand');brand.append(node('small','Central local · identidades separadas'));nav.append(brand);
  const chatLayout=document.querySelector('.layout'),cards=document.querySelector('.cards');
  cards.querySelectorAll('.card').forEach((card,i)=>{const entity=Object.keys(names)[i];card.dataset.entity=entity;const facts=node('div','Executor, humor e tarefa: consultando backend…','entity-facts');facts.id='facts-'+entity;card.querySelector('.status').after(facts);for(const [label,page] of [['Conversar','Conversa'],['Memória do chat','Memória do chat'],['Atividade','Atividade']]){const b=node('button',label);b.onclick=()=>{selectEntity(entity);show(page)};card.querySelector('.actions').append(b)}});
  const live=node('p','Consultando operações…','live-status');live.id='live-status';chatLayout.firstElementChild.querySelector('header').after(live);
  const stable=node('div',null,'speech-preview');stable.id='stable-response';stable.hidden=true;live.after(stable);
  const currentJobs=document.querySelector('#jobs').parentElement;
  const resourceDetails=document.querySelector('#resources').parentElement;
  const worldDetails=document.querySelector('#world-health').parentElement;
  for(const page of pages){const panel=node('main');panel.dataset.page=page;panel.hidden=page!==active;const head=node('div',null,'page-title');head.append(node('h2',page));if(page!=='Conversa')head.append(node('p','Estado do backend · sem capacidades novas'));panel.append(head);panels.set(page,panel);document.body.append(panel);const b=node('button',page);b.dataset.page=page;b.onclick=()=>show(page);nav.append(b)}
  const laboratory=panels.get('Laboratório Neural');
  laboratory.append(node('p','Treinamento de entidades e curadoria MoE rodam em um serviço localhost separado, iniciado pelo painel nativo ou manualmente.','section-note'));
  const labLink=node('a','Abrir Laboratório Neural · localhost:8788');
  labLink.href='http://127.0.0.1:8788';labLink.target='_blank';labLink.rel='noopener noreferrer';
  laboratory.append(labLink);
  nav.append(node('div','Somente neste PC · cloud desligada','footnote'));document.body.prepend(nav);
  for(const card of cards.querySelectorAll('.card')){const entity=card.dataset.entity;if(entity==='alistair')continue;const stop=node('button','Interromper fala');stop.onclick=()=>{stopSpeech(entity);api('audio/interrupt',{entity}).then(()=>{$('notice').textContent='Interrupção solicitada somente para '+names[entity]+'.'}).catch(e=>{$('notice').textContent=e.message})};card.querySelector('.actions').append(stop)}
  panels.get('Conversa').append(chatLayout);panels.get('Entidades').append(cards);panels.get('Atividade').append(currentJobs);panels.get('Recursos').append(resourceDetails);resourceDetails.open=true;panels.get('Diagnóstico').append(worldDetails);worldDetails.open=true;
  const subtitle=document.querySelector('body>header small');subtitle.textContent='Hoshino · Lilith · Alistair — controle e presença, sem misturar memórias';
  const shutdown=node('button','Encerrar tudo com segurança');shutdown.onclick=async()=>{if(!confirm('Solicitar sono e encerramento cooperativo da central e entidades? Jobs bloqueados/incertos podem impedir a saída; nenhum processo externo será morto.'))return;try{const out=await api('control/shutdown',{confirm:true});$('notice').textContent=out.note}catch(e){$('notice').textContent=e.message}};document.querySelector('body>header').append(shutdown);
  function selectEntity(entity){if($('entity').value!==entity){$('entity').value=entity;$('entity').dispatchEvent(new Event('change'))}}
  function show(page){if(active==='Memórias'&&page!=='Memórias')lockMemoryAccess();active=page;for(const [name,panel] of panels)panel.hidden=name!==page;nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',b.dataset.page===page?'page':'false'));if(control.load)control.load(page);}
  const result={node,panels,names,show,selectEntity,get active(){return active}};
  const chatScope=node('select');chatScope.setAttribute('aria-label','Canal da conversa');
  chatScope.add(new Option('Global · principal','global'));chatScope.add(new Option('Direto · entidade selecionada','direct'));
  chatLayout.firstElementChild.querySelector('header').append(chatScope);
  const roomNote=node('p','Global: todas as entidades acordadas recebem, sem acordar as demais. Direto: só a escolhida. Trocas entre entidades são públicas. Nome: perspectiva individual selecionada.','section-note');
  chatScope.parentElement.after(roomNote);
  const legacyFeed=$('private').parentElement;legacyFeed.hidden=true;legacyFeed.setAttribute('aria-hidden','true');
  chatLayout.style.gridTemplateColumns='1fr';
  const audioControls=document.querySelector('.audio-panel');audioControls.dataset.persistent='true';panels.get('Áudio').append(audioControls);audioControls.open=true;
  const nativeMic=node('button','Abrir Central nativa · detecção / comando e atalho global');
  nativeMic.dataset.persistent='true';
  nativeMic.onclick=async()=>{try{await api('control/native/open',{});}catch(e){$('notice').textContent=e.message}};
  panels.get('Áudio').append(nativeMic,node('p','Captura do navegador: comando por botão. Detecção contínua e atalho global estão na Central nativa, aba Áudio. Nenhuma gravação inicia ao abrir esta página.'));
  const scopeDrafts=new Map();let oldScope='global';
  chatScope.onchange=()=>{scopeDrafts.set(oldScope+'|'+$('entity').value,$('text').value);oldScope=chatScope.value;
    cancelRecording();stopSpeech();$('text').value=scopeDrafts.get(oldScope+'|'+$('entity').value)||'';drafts.clear();drafts.set($('entity').value,$('text').value);draftOrigins.clear();resetChatView();refresh()};
  const oldFeed=feed;
  feed=function(id,items){oldFeed(id,items);if(id==='chat'){const rows=$(id).querySelectorAll('.message .meta');items.forEach((m,i)=>{if(rows[i]&&m.sender==='usuario')rows[i].textContent=(window.centralHumanName||'Usuário')+' → '+(m.metadata?.broadcast_targets?'Global · '+m.metadata.broadcast_targets.join(', '):m.recipient)+' · '+new Date(m.created_at).toLocaleString()+' · '+processingLabel(m)})}};
  // Mantém os mesmos envelopes/recibos; apenas seleciona a vista e o canal.
  const oldApi=api;
  api=async function(path,data,keepalive){if(path.startsWith('state?')){const params=new URLSearchParams(path.split('?')[1]);params.set('chat_scope',chatScope.value);path='state?'+params}
    if(path==='send')data={...data,chat_scope:chatScope.value};
    const protectedMemory=['control/knowledge','control/logic'].includes(path.split('?')[0]),epoch=memoryEpoch;
    try{const out=await oldApi(path,data,keepalive,protectedMemory?memoryAccess:'');if(protectedMemory&&epoch!==memoryEpoch)throw Error('Memórias bloqueadas durante o pedido; nenhuma ação foi repetida.');if(path.startsWith('state?')){window.centralHumanName=out.human_display_names?.[$('entity').value]||'Usuário';window.dispatchEvent(new CustomEvent('central-state',{detail:out}));}return out}
    catch(error){if(protectedMemory&&error.status===403)lockMemoryAccess(false);throw error}};
  window.addEventListener('central-state',e=>{
    const out=e.detail,leases=out.resources||[],jobs=out.jobs||[];
    const playing=jobs.find(j=>j.id===speechJobId);
    if(playing?.details?.playback_cancel_at||['interrupted','error'].includes(playing?.status))stopSpeech(playing.entity);
    for(const entity of Object.keys(names)){const p=(out.presence||[]).find(x=>x.entity_id===entity),own=jobs.filter(j=>j.entity===entity&&['queued','running'].includes(j.status)),lease=leases.find(r=>r.entity===entity&&r.model_key)||leases.find(r=>r.entity===entity);const d=own[0]?.details||{};
      $('facts-'+entity).textContent='Executor: '+(d.model||lease?.model_key?.split('|').at(-1)||lease?.model||'não informado')+' · processamento: '+(lease?.resource||'sem lease')+'\nTarefa: '+(d.phase||own[0]?.kind||'nenhuma registrada')+' · fila: '+own.filter(j=>j.status==='queued').length+'\nHumor: indisponível · último erro: '+(out.failures?.[entity]||'nenhum no supervisor');
      if(p?.status==='awake'&&own.length)$('state-'+entity).textContent=(own[0].status==='queued'?'Esperando recurso':'Em atividade')+' · '+(d.phase||own[0].kind);
    }
    const own=jobs.filter(j=>j.entity===$('entity').value&&['queued','running'].includes(j.status));$('live-status').textContent=own.length?own.map(j=>jobLabel(j)).join(' · '):'Sem trabalho ativo registrado · mensagens seguem a caixa postal';
    const stream=own.find(j=>j.kind==='llm_speech'&&j.details?.stable_only);const sentences=stream?.details?.sentences||[];const text=sentences.map(s=>typeof s==='string'?s:s.text||'').join(' ');$('stable-response').textContent=text;$('stable-response').hidden=!text;
  });
  // Expõe apenas operações existentes; nunca encerramento do backend ao fechar.
  window.centralControl=result;
  const globalSelect=node('select');globalSelect.setAttribute('aria-label','Entidade nos painéis');
  for(const [id,name] of Object.entries(names))globalSelect.append(new Option(name,id));
  globalSelect.onchange=()=>{selectEntity(globalSelect.value);show(active)};document.querySelector('body>header').append(globalSelect);
  $('entity').addEventListener('change',()=>{if(memoryEntity&&memoryEntity!==$('entity').value)lockMemoryAccess();globalSelect.value=$('entity').value;if(active!=='Conversa')show(active)});
  function lockMemoryAccess(revoke=true){const access=memoryAccess,entity=memoryEntity;memoryAccess='';memoryEntity='';memoryExpires=0;memoryEpoch++;clearTimeout(memoryTimer);emptyPanel('Memórias');if(active==='Memórias')memoryLockPanel();if(revoke&&access)oldApi('control/knowledge/lock',{entity},true,access).catch(()=>{})}
  function memoryLockPanel(){const panel=emptyPanel('Memórias');panel.append(node('p','Memórias protegidas. Use a mesma senha local já definida. Sair da aba, trocar entidade ou completar 5 minutos bloqueia novamente.','section-note'));
    const form=node('form'),password=node('input');password.type='password';password.maxLength=200;password.autocomplete='current-password';password.setAttribute('aria-label','Senha de Memórias');
    const open=button('Desbloquear Memórias',()=>form.requestSubmit());form.append(password,open);panel.append(form);
    panel.append(button('Definir / alterar senha na Central nativa',()=>task(async()=>{await api('control/native/open',{})})));
    form.onsubmit=event=>{event.preventDefault();const secret=password.value,entity=$('entity').value,epoch=memoryEpoch;password.value='';open.disabled=true;task(async()=>{try{const out=await api('control/knowledge/unlock',{entity,password:secret});if(active!=='Memórias'||epoch!==memoryEpoch||entity!==$('entity').value)return;memoryAccess=out.access_token;memoryEntity=entity;memoryExpires=Date.now()+out.expires_in*1000;memoryTimer=setTimeout(()=>lockMemoryAccess(),out.expires_in*1000);await memoryCardsPanel()}finally{open.disabled=false}})}}
  async function memoryCardsPanel(){if(!memoryAccess||memoryEntity!==$('entity').value||Date.now()>=memoryExpires){lockMemoryAccess();return}
    const entity=$('entity').value,out=await api('control/knowledge?entity='+entity);if(active!=='Memórias'||entity!==$('entity').value)return;const panel=emptyPanel('Memórias');
    panel.append(button('Bloquear Memórias agora',()=>lockMemoryAccess()),node('p',out.note,'section-note'),button('Criar / editar / apagar cartões na Central nativa',()=>task(async()=>{await api('control/native/open',{})})));
    for(const card of out.items||[]){const section=node('section',null,'memory-card');section.dataset.importance=card.importance||'ferro';section.append(node('h3',card.title));const level=node('select');level.setAttribute('aria-label','Importância de '+card.title);for(const tier of ['ferro','ouro','diamante','platina'])level.add(new Option(tier[0].toUpperCase()+tier.slice(1),tier));level.value=card.importance||'ferro';section.append(level,button('Aplicar importância',()=>task(async()=>{await api('control/knowledge',{entity,action:'importance',card_id:card.id,card_revision:card.card_revision,importance:level.value});await memoryCardsPanel()})));for(const entry of card.entries||[])section.append(node('p',(entry.label?entry.label+': ':'')+entry.text));panel.append(section)}}
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&memoryAccess)lockMemoryAccess()});window.addEventListener('pagehide',()=>lockMemoryAccess());
  function emptyPanel(page){const panel=panels.get(page);for(const child of [...panel.children].slice(1)){if(child.dataset.persistent!=='true')child.remove()}return panel}
  function field(label,value,type='text'){const box=node('label',label),input=node('input');input.type=type;if(type==='checkbox')input.checked=!!value;else input.value=value??'';box.append(input);return [box,input]}
  function selectField(label,values,value){const box=node('label',label),input=node('select');for(const [id,text] of values)input.append(new Option(text,id));input.value=value;box.append(input);return [box,input]}
  const bytes=v=>v==null?'indisponível':(v/1073741824).toFixed(2)+' GiB';
  function kv(pairs){const list=node('dl',null,'kv');for(const [key,value] of pairs){list.append(node('dt',key),node('dd',value==null?'indisponível':String(value)))}return list}
  const button=(label,fn)=>{const b=node('button',label);b.type='button';b.onclick=fn;return b};
  function notice(message){$('notice').textContent=message}
  async function task(fn){try{await fn()}catch(e){notice(e.message)}}
  function modelPanel(out){
    const generation=++modelGeneration;
    const panel=emptyPanel('Modelos'),section=node('section');panel.append(section);
    section.append(node('h3',names[out.entity]+' · executores independentes da identidade'),node('p',out.impact_note,'section-note'));
    const form=node('div',null,'form-grid');section.append(form);
    const [mBox,model]=selectField('Principal instalado/compatível',out.options.map(o=>[o.model,o.model]),out.primary);if(!out.options.length){model.append(new Option(out.primary+' · indisponível/não confirmado',out.primary));model.disabled=true}
    const [cBox,ctx]=field('Contexto principal · '+out.context_min+'–'+out.context_max,out.context,'number');ctx.min=out.context_min;ctx.max=out.context_max;ctx.step=out.context_step>1?out.context_step:1024;
    const [oBox,output]=field('Limite de saída · 128–'+out.output_max,out.output,'number');output.min=128;output.max=Math.min(out.output_max,Number(ctx.value)-512);
    ctx.addEventListener('change',()=>{output.max=Math.min(out.output_max,Number(ctx.value)-512);if(Number(output.value)>Number(output.max)){output.value=output.max;notice('Limite de saída ajustado no formulário para reservar espaço de entrada. Salve para aplicar.')}});
    form.append(mBox,cBox,oBox);section.append(kv([['Leve',out.light?.model||'Não se aplica (Alistair 4B)'],['Contexto leve',out.light_context==null?'não se aplica':out.light_context+' · READ-ONLY'],['Aplicação','Exige entidade dormir/acordar; não troca durante resposta'],['Residência',out.residency.map(r=>r.model+' · '+r.state+' · '+bytes(r.vram_bytes)).join('\n')||'Sem observação atual; desconhecido'],['Impacto de pesos',bytes(out.options.find(o=>o.model===model.value)?.size_bytes)]]));
    const estimate=node('p','Contexto maior aumenta o cache de memória; o orçamento da máquina selecionada e as margens continuam limitando a alocação.','section-note');section.append(estimate);
    section.append(button('Aplicar após sono confirmado',()=>task(async()=>{await api('control/models',{entity:out.entity,model:model.value,context:Number(ctx.value),output:Number(output.value),revision:out.revision});notice('Configuração salva com backup. Será usada no próximo despertar.');load('Modelos')})),button('Restaurar limites de referência no formulário',()=>{ctx.value=out.entity==='alistair'?4096:16384;output.value=out.entity==='alistair'?768:4096}));
    if(out.entity==='hoshino'||out.entity==='lilith'){
      const modes=node('section');panel.append(modes);
      modes.append(node('h3','Modo de execução por identidade'));
      api('control/neural9b?entity='+out.entity).then(status=>{
        if(active!=='Modelos'||$('entity').value!==out.entity)return;
        const [modeBox,mode]=selectField('Escolher executor', [['original','Original (intacto)'],['neural9b','Neural 9B (LoRA próprio)']],status.mode);
        const unavailable=mode.querySelector('option[value="neural9b"]');unavailable.disabled=!status.neural_ready;
        modes.append(modeBox,node('p','Alias: '+status.neural_alias+' · '+(status.neural_ready?'instalado':'aguardando exportação GGUF/registro Ollama')+' · Troca apenas com entidade dormindo.','section-note'));
        modes.append(button('Aplicar modo de execução',()=>task(async()=>{
          const saved=await api('control/neural9b',{entity:out.entity,mode:mode.value,revision:status.revision});
          notice('Modo '+saved.mode+' salvo. Acorde a entidade para aplicar.');load('Modelos');
        })));
      }).catch(e=>notice(e.message));
    }
    const catalog=node('section');catalog.append(node('h3','Arquivos e aliases instalados · sem download automático'));
    for(const row of out.catalog){const card=node('div',null,'row-card');card.append(node('strong',row.model),kv([['Estado',row.installed?'arquivos locais com tamanho esperado':'incompleto; não selecionável'],['Tamanho',bytes(row.size_bytes)],['Quantização',row.quantization],['Backend',row.backend],['Manifesto',row.path],['SHA-256',row.hash+' · '+row.hash_kind]]));catalog.append(card)}
    if(!out.catalog.length)catalog.append(node('p','Nenhum manifesto legível instalado nesta entidade.','empty'));panel.append(catalog);
    if(out.entity==='alistair')executionPanel(panel,generation).catch(e=>notice(e.message));
    if(result.filesPanel)result.filesPanel(panel,out);
  }
  async function executionPanel(panel,generation){
    const out=await api('control/alistair/execution');if(active!=='Modelos'||$('entity').value!=='alistair'||generation!==modelGeneration)return;
    const section=node('section'),form=node('div',null,'form-grid');section.append(node('h3','Onde executar Alistair'),node('p',out.note,'section-note'),form);panel.insertBefore(section,panel.children[1]);
    const s=out.settings,[dBox,destination]=selectField('Destino',Object.entries(out.destinations),s.destination),[ipBox,ip]=field('IP do Xbox',s.xbox_ip),[startBox,start]=field('Abrir executor ao acordar Alistair',s.auto_start,'checkbox'),[syncBox,sync]=field('Conferir/sincronizar arquivos técnicos',s.auto_sync,'checkbox'),[lanBox,lan]=field('LAN de confiança · inferência HTTP, não expor à internet',s.trusted_lan,'checkbox'),[uBox,user]=field('Usuário do acesso remoto Xbox',''),[pBox,password]=field('Senha do acesso remoto (vazio mantém salva)','','password');password.autocomplete='new-password';
    const certBox=node('label','Certificado público PEM do Xbox (não chave privada)'),cert=node('textarea');cert.maxLength=16384;certBox.append(cert);form.append(dBox,ipBox,startBox,syncBox,lanBox,uBox,pBox,certBox);
    section.append(kv([['Acesso remoto salvo',out.credentials_configured],['Certificado salvo',out.certificate_configured],['Estado Xbox',out.xbox.state||'não conferido'],['Observação',out.xbox.fresh?'atual':'antiga/não confirmada agora'],['Pendência',out.xbox.pending?.operation||'nenhuma registrada']]));
    if(out.model_limits){const l=out.model_limits,c=l.configured||{},a=l.applied||{};section.append(kv([['Limites salvos','Contexto '+(c.context??'?')+' / saída '+(c.output??'?')],['Últimos limites aplicados no Xbox','Contexto '+(a.context??'não confirmado')+' / saída '+(a.output??'não confirmado')],['Sincronização dos limites',l.error||(l.pending?'Aguardando despertar ou conferência com Alistair dormindo':'Sincronizados na última preparação')],['Cache físico',out.xbox.context_verified?'Confirmado no último uso':'Aguardando primeira resposta']]))}
    section.append(button('Salvar destino · Alistair dormindo',()=>task(async()=>{
      const data={revision:out.revision,settings:{destination:destination.value,xbox_ip:ip.value.trim(),auto_start:start.checked,auto_sync:sync.checked,trusted_lan:lan.checked}};
      if(user.value||password.value){data.username=user.value.trim();data.password=password.value}if(cert.value.trim())data.certificate_pem=cert.value.trim();
      try{await api('control/alistair/execution',data);notice('Destino salvo para o próximo despertar. Banco e memória continuam noPC.');load('Modelos')}finally{password.value='';user.value=''}
    })));
    for(const [action,label]of [['prepare','Conferir/sincronizar agora'],['reconcile','Reconciliar pendência · sem repetir']])section.append(button(label,()=>task(async()=>{
      if(!confirm('Conferir executor Xbox com Alistair dormindo? Pode fechar/reabrir somente o app de inferência. Não repita por demora/timeout.'))return;
      notice('Conferindo Xbox; hashes físicos podem levar alguns minutos.');await api('control/alistair/execution/check',{action,revision:out.revision});load('Modelos');
    })));
  }
  async function audioPanel(){
    const out=await api('control/audio'),panel=emptyPanel('Áudio'),section=node('section');panel.append(section);
    section.append(node('h3','Voz · router existente, fallback Qwen obrigatório'));
    const form=node('div',null,'form-grid');const [pBox,provider]=selectField('Preferência',[['elevenlabs','ElevenLabs'],['azure','Azure pt-BR Standard'],['qwen3_tts','Qwen3-TTS local'],['kokoro','Kokoro legado']],out.preferred_provider);
    const [eBox,enabled]=field('Habilitar provider externo (pode consumir quota ao falar)',!!out.providers[out.preferred_provider]?.enabled,'checkbox');form.append(pBox,eBox);
    const ids={};for(const id of ['hoshino','lilith']){const [box,input]=field(names[id]+' · Voice ID',out.providers[out.preferred_provider]?.voices?.[id]||out.local_voices[id]?.id);ids[id]=input;form.append(box)}
    function update(){const remote=['azure','elevenlabs'].includes(provider.value);enabled.disabled=!remote;enabled.checked=!!out.providers[provider.value]?.enabled;for(const id of Object.keys(ids)){ids[id].value=out.providers[provider.value]?.voices?.[id]||out.local_voices[id]?.id||'';ids[id].disabled=!remote}}
    const [modelBox,ttsModel]=selectField('Modelo TTS ElevenLabs',(out.eleven_models||['eleven_multilingual_v2','eleven_flash_v2_5','eleven_turbo_v2_5']).map(id=>[id,id]),out.providers.elevenlabs.model||'eleven_multilingual_v2');form.append(modelBox);
    provider.onchange=()=>{update();ttsModel.disabled=provider.value!=='elevenlabs'};update();ttsModel.disabled=provider.value!=='elevenlabs';section.append(form);
    section.append(kv(Object.entries(out.providers).map(([id,p])=>[id+' · API key',p.key_configured?'CONFIGURADA no ambiente':'NÃO CONFIGURADA'])));
    section.append(node('p','Chaves não são recebidas nem exibidas. Sem chave, a rota local permanece. Azure preservado; RunPod/cloud desativados. Alistair continua textual. Kokoro exige configuração/restart de worker se não for o backend local atual.','section-note'));
    section.append(button('Salvar provider/vozes',()=>task(async()=>{await api('control/audio',{preferred_provider:provider.value,enabled:enabled.checked,voices:['azure','elevenlabs'].includes(provider.value)?Object.fromEntries(Object.entries(ids).map(([id,i])=>[id,i.value.trim()])):{},revision:out.revision,...(provider.value==='elevenlabs'?{model_id:ttsModel.value}:{})});notice('Router atualizado sem síntese/quota. Fallback local preservado.');await refreshAudioState();audioPanel()})));
    const tests=node('section');tests.append(node('h3','Testes isolados · somente ao clicar'),node('p','Teste explícito funciona sem acordar LLM; pode consumir quota. Provider real aparece no job. Síntese não comprova audição.','section-note'));
    const testText=node('textarea');testText.value='Olá! Este é um teste da minha voz em português.';testText.maxLength=2400;testText.setAttribute('aria-label','Frase de teste de voz');tests.append(testText);
    for(const id of ['hoshino','lilith'])tests.append(button('Testar voz de '+names[id],()=>{if(confirm('Sintetizar um teste de '+names[id]+'? Provider externo habilitado pode consumir quota.'))speakRequest(id,'audio/test',{entity:id,confirm:true,text:testText.value,provider:provider.value,...(provider.value==='elevenlabs'?{model:ttsModel.value}:{})})}));tests.append(button('Interromper áudio desta aba',()=>stopSpeech()));
    const outputSection=node('section');outputSection.append(node('h3','Dispositivos desta aba'),node('p','Microfone/ASR de teste usam o botão “Falar uma mensagem” em Conversa; a transcrição fica em rascunho, nunca é enviada automaticamente.','section-note'),button('Abrir gravação/ASR',()=>show('Conversa')));
    const [sinkBox,sink]=selectField('Saída do navegador',[['','Padrão do sistema']],''),[volumeBox,volume]=field('Volume de reprodução (aba)',1,'range');volume.min=0;volume.max=1;volume.step=.05;volume.value=$('voice-player').volume;
    volume.oninput=()=>{$('voice-player').volume=Number(volume.value)};outputSection.append(sinkBox,volumeBox);
    if(!$('voice-player').setSinkId){sink.disabled=true;outputSection.append(node('p','Seleção de saída indisponível neste navegador. Use o painel de som do Linux; nenhuma alteração fictícia.','section-note'))}
    else {for(const d of (await navigator.mediaDevices?.enumerateDevices()||[]).filter(d=>d.kind==='audiooutput'))sink.append(new Option(d.label||'Saída sem nome',d.deviceId));sink.onchange=()=>task(async()=>{await $('voice-player').setSinkId(sink.value);notice('Saída selecionada nesta aba. Valide fisicamente nos fones/caixas.')})}
    outputSection.append(button('Testar som local (sem TTS)',()=>task(async()=>{const C=window.AudioContext||window.webkitAudioContext;if(!C)throw Error('Web Audio indisponível.');const ctx=new C();try{if(sink.value&&ctx.setSinkId)await ctx.setSinkId(sink.value);else if(sink.value)throw Error('Teste de tom não suporta esta saída neste navegador.');await ctx.resume();const osc=ctx.createOscillator(),gain=ctx.createGain();gain.gain.value=.06*Number(volume.value);osc.frequency.value=440;osc.connect(gain);gain.connect(ctx.destination);osc.start();await pause(350);osc.stop();notice('Tom gerado; apenas você pode confirmar audição.')}finally{await ctx.close()}})));
    outputSection.append(kv([['ASR','faster-whisper CPU · parâmetros atuais READ-ONLY'],['Configuração ASR',JSON.stringify(out.asr.configuration)],['Entrada física','Exige permissão e teste real; lista não é prova de captura']]));panel.append(tests,outputSection);
  }
  async function resourcesPanel(){const out=await api('control/resources'),panel=panels.get('Recursos');let section=$('resource-metrics');if(!section){section=node('section');section.id='resource-metrics';panel.insertBefore(section,panel.children[1])}section.replaceChildren();section.append(node('h3','Sistema · compute ≠ residência'),kv([['CPU',out.cpu_percent==null?'primeira amostra/indisponível':out.cpu_percent+'%'],['RAM disponível / total',bytes(out.ram_available)+' / '+bytes(out.ram_total)],['Swap livre / total',bytes(out.swap_free)+' / '+bytes(out.swap_total)+' · NÃO é RAM rápida'],['VRAM',out.gpu.metrics.known?bytes(out.gpu.metrics.used_bytes)+' / '+bytes(out.gpu.hard_limit_bytes):'incerta → serialização conservadora'],['GPU busy',out.gpu.metrics.utilization==null?'indisponível':out.gpu.metrics.utilization+'%'],['Margem VRAM',bytes(out.gpu.policy.margin_bytes)],['Concorrência validada',String(out.gpu.policy.concurrency_validated)],['Disco livre',bytes(out.disk_free)]]));
    const cache=out.ram_prompt_cache||{},caps=cache.per_entity_mib||{},cacheBytes=value=>Number.isFinite(value)?bytes(value*1024**2):'indisponível';
    section.append(node('h3','Cache de prompts RAM · política prevista'),kv([['Teto combinado',cacheBytes(cache.aggregate_mib)],...['hoshino','lilith','alistair'].map(id=>[names[id],cacheBytes(caps[id])])]),node('p','Próximo boot gerenciado; aplicação no runner e uso real ainda não confirmados. Não é cache de pesos ou memória mental.','section-note'));
    if(cache.valid===false)section.append(node('p','Configuração inválida: cache desativado para o próximo boot.','section-note'));
    const profiles=out.resource_profiles||{},observed=profiles.observations||{};
    section.append(node('h3','Perfis dinâmicos · última decisão por tarefa'),node('p',(profiles.available||[]).map(p=>p.label).join(' · '),'section-note'),kv(['hoshino','lilith','alistair'].map(id=>{const p=observed[id];return [names[id],p?p.label+' · '+p.ts+(p.held?' · proteção contra trocas frequentes':''):'sem decisão observada']})),node('p','Histórico limitado, não perfil ativo confirmado. Custos são heurísticos; ganho de velocidade ainda exige medição. Sem troca de modelo no meio da resposta.','section-note'));
    section.append(node('h3','Compute leases'),node('pre',JSON.stringify(out.leases,null,2)),node('h3','Fila P0–P5'),node('pre',JSON.stringify(out.gpu.queue.map(q=>({...q,waiting_seconds:Math.max(0,Date.now()/1000-q.enqueued_at)})),null,2)),node('h3','Residência observada · estado pode vencer'),node('pre',JSON.stringify(out.gpu.residency,null,2)));
  }
  function filters(page,kind){const panel=panels.get(page);let bar=panel.querySelector('.toolbar');if(bar)return bar;bar=node('form',null,'toolbar');for(const [key,placeholder] of (kind==='memory'?[['q','Busca textual'],['author','Autor'],['source','Fonte'],['turn','Turn ID'],['type','Tipo: fato/hipotese/...'],['confidence','Confiança mínima 0–1']]:[['q','Busca de evento/ID'],['turn','Turn ID'],['tool','Ferramenta'],['level','Severidade INFO/WARN/ERROR'],['origin','Origem'],['since','Desde (ISO)'],['until','Até (ISO)']])){const input=node('input');input.name=key;input.placeholder=placeholder;input.setAttribute('aria-label',placeholder);bar.append(input)}bar.append(button('Buscar',()=>load(page)));bar.onsubmit=e=>{e.preventDefault();load(page)};panel.append(bar);return bar}
  function queryFilters(bar){return new URLSearchParams([...new FormData(bar)].filter(([_,v])=>v.trim())).toString()}
  async function memoryPanel(){const panel=panels.get('Memória do chat'),bar=filters('Memória do chat','memory');let content=panel.querySelector('.memory-list');if(!content){content=node('section',null,'memory-list');panel.append(content)}const out=await api('control/memory?scope=chat&entity='+$('entity').value+'&'+queryFilters(bar));content.replaceChildren(node('p',out.note+' · READ-ONLY','section-note'));for(const r of out.items){const card=node('div',null,'row-card');card.append(node('span',r.tipo,'tag'),node('p',r.content||r.what_happened||r.conteudo||r.input||r.chave+': '+r.valor),kv([['Entidade',names[r.entity]],['Confiança',r.confianca==null?'não registrada':r.confianca],['Fonte',r.fonte||r.source||r.sender||'não registrada'],['Data',r.created_at],['ID',r.id||r.source_id]]));const details=node('details');details.append(node('summary','Autoria, sujeito e evidência existentes'),node('pre',JSON.stringify(r,null,2)));card.append(details);content.append(card)}if(!out.items.length)content.append(node('p','Nenhum registro dentro da leitura limitada/filtros.','empty'))}
  async function activityPanel(){const panel=panels.get('Atividade'),bar=filters('Atividade','activity');let content=$('activity-list');if(!content){content=node('section');content.id='activity-list';panel.append(content)}const out=await api('control/activity?entity='+$('entity').value+'&'+queryFilters(bar));content.replaceChildren(node('h3','Timeline operacional · ordem local, sem causalidade global'),node('p','Janela limitada de diagnostics/history. Não mostra prompts, tokens privados ou cadeia de pensamento.','section-note'));for(const e of out.items){const card=node('details');card.append(node('summary',e.ts+' · '+e.level+' · '+e.event+' · '+(e.data?.turn_id||e.turn_id||'sem turno')),node('pre',JSON.stringify(e,null,2)));content.append(card)}if(!out.items.length)content.append(node('p','Nenhum evento registrado nesta janela.','empty'));
    let commands=$('command-list');if(!commands){commands=node('section');commands.id='command-list';panel.append(commands)}const c=await api('control/commands?entity='+$('entity').value);commands.replaceChildren(node('h3','Comandos existentes · leitura incremental do log limitado'));for(const job of c.items){const card=node('div',null,'row-card');card.append(kv([['Entidade',names[job.entity]],['Comando',job.comando],['Diretório',job.cwd],['Início',job.inicio],['Fim',job.fim],['Exit code',job.codigo],['Estado',job.status],['Saída',job.stream]]),node('pre',job.output));commands.append(card)}if(!c.items.length)commands.append(node('p','Nenhum comando registrado. Sem terminal remoto.','empty'));
  }
  async function capabilitiesPanel(){
    const entity=$('entity').value,out=await api('control/capabilities?entity='+entity);
    if(active!=='Ferramentas'||entity!==$('entity').value)return;
    const panel=emptyPanel('Ferramentas'),checks=[];panel.append(node('p',out.note,'section-note'));
    for(const item of out.controls||[]){
      const row=node('label',null,'row-card'),checkbox=node('input');checkbox.type='checkbox';checkbox.checked=item.enabled;
      checkbox.indeterminate=!!item.legacy_restrictions&&item.enabled;checkbox.dataset.capability=item.key;
      checkbox.addEventListener('change',()=>checkbox.dataset.changed='true');
      row.append(checkbox,node('strong',' '+item.label),node('p',item.description,'section-note'));
      if(checkbox.indeterminate)row.append(node('small','Restrição antiga parcial: marque para permitir o grupo inteiro ou desmarque para bloquear.'));
      panel.append(row);checks.push(checkbox);
    }
    const buttons=node('div',null,'toolbar'),save=node('button','Salvar permissões'),reload=node('button','Atualizar');
    reload.onclick=()=>capabilitiesPanel().catch(e=>notice(e.message));
    save.onclick=async()=>{
      const changes=Object.fromEntries(checks.filter(c=>c.dataset.changed==='true').map(c=>[c.dataset.capability,c.checked]));
      if(!Object.keys(changes).length){notice('Nenhuma permissão foi alterada.');return}
      save.disabled=true;
      try{await api('control/tools',{entity,capabilities:changes,revision:out.revision});notice('Permissões salvas. Nada foi iniciado automaticamente.');await capabilitiesPanel()}
      catch(e){notice(e.message)}finally{save.disabled=false}
    };buttons.append(save,reload);panel.append(buttons);
  }
  async function servicesPanel(){const out=await api('control/audio'),panel=emptyPanel('Serviços');for(const name of ['elevenlabs','azure']){const p=out.providers[name],section=node('section');section.append(node('h3',name==='elevenlabs'?'ElevenLabs':'Azure legado preservado'),kv([['Habilitado',p.enabled],['API key',p.key_configured?'CONFIGURADA':'NÃO CONFIGURADA'],['Conexão',p.connection],['Latência','Veja jobs/atividade após teste explícito'],['Vozes',JSON.stringify(p.voices)]]));panel.append(section)}const runpod=node('section');runpod.append(node('h3','RunPod · futuro'),node('p','DESATIVADO · nenhum backend novo, conexão ou gasto nesta rodada.','section-note'));panel.append(runpod,button('Configurar providers existentes',()=>show('Áudio')))}
  async function interfacePanel(){const out=await api('control/interface'),panel=emptyPanel('Configurações');panel.append(node('p','Executores → Modelos; providers → Áudio. Recursos, Minecraft, Discord e parâmetros ASR preservados em leitura/diagnóstico; não há editor genérico de arquivos.','section-note'));const section=node('section'),form=node('div',null,'form-grid'),inputs={};for(const [id,label] of [['overlay_enabled','Overlay/orbes opcionais'],['always_on_top','Sempre no topo'],['balloons','Balões de mensagens'],['silent','Modo silencioso visual']]){const [box,input]=field(label,out.settings[id],'checkbox');inputs[id]=input;form.append(box)}const [box,seconds]=field('Duração de balão · 2–20 segundos',out.settings.balloon_seconds,'number');seconds.min=2;seconds.max=20;form.append(box);section.append(node('h3','Interface e overlay'),form,button('Salvar preferências',()=>task(async()=>{await api('control/interface',{revision:out.revision,settings:{...Object.fromEntries(Object.entries(inputs).map(([k,i])=>[k,i.checked])),balloon_seconds:Number(seconds.value)}});notice('Preferências salvas. Overlay opcional; falha não encerra entidades.');interfacePanel()})));if(result.overlayButtons)result.overlayButtons(section);panel.append(section)}
  async function load(page){try{const entity=$('entity').value;if(page==='Modelos'){const out=await api('control/models?entity='+entity);if(active==='Modelos'&&entity===$('entity').value)modelPanel(out)}if(page==='Áudio')await audioPanel();if(page==='Recursos')await resourcesPanel();if(page==='Memória do chat')await memoryPanel();if(page==='Atividade')await activityPanel();if(page==='Ferramentas')await capabilitiesPanel();if(page==='Serviços')await servicesPanel();if(page==='Configurações')await interfacePanel();}catch(e){notice(e.message)}}
  async function entityDetails(){try{const out=await api('control/entities');for(const [id,detail] of Object.entries(out)){const card=document.querySelector('.card[data-entity="'+id+'"]');let info=card.querySelector('details');if(!info){info=node('details');info.append(node('summary','Executor, estado e serviços reais'));card.append(info)}while(info.children.length>1)info.lastChild.remove();info.append(kv([['Principal configurado',detail.configured_primary],['Leve configurado',detail.configured_light?.model||'não se aplica'],['Último executor observado',detail.executor_observation?.data?.model||detail.executor_observation?.data?.chosen_model||'indisponível'],['Data da observação',detail.executor_observation?.ts],['Última ação',detail.last_action?.event||'não registrada'],['Último erro',detail.last_error?.event||'nenhum registrado na janela'],['Minecraft',detail.minecraft],['Discord',detail.discord],['Estado psicológico',detail.psychological_state?JSON.stringify(detail.psychological_state):'indisponível']]));}}catch(e){notice(e.message)}}
  const baseLoad=load;load=async page=>{await baseLoad(page);if(page==='Entidades')await entityDetails()};
  result.load=load;
  const previousLoad=result.load;
  result.load=async page=>{await previousLoad(page);if(page==='Memórias')await task(memoryCardsPanel)};
  result.filesPanel=async(panel,out)=>{try{const inventory=await api('control/files');if(!panel.isConnected||control.active!=='Modelos'||out.entity!==$('entity').value)return;const section=node('section');section.append(node('h3','Arquivos de pesos · transferência segura'),node('p',inventory.note+' · Disco livre '+bytes(inventory.disk_free)+'; reserva '+bytes(inventory.reserve_bytes)+'. Exportação copia para Entregas/saída, sem manter vários GiB na RAM do navegador.','section-note'));
    const file=node('input');file.type='file';file.accept='.gguf';file.setAttribute('aria-label','GGUF local para arquivar');const hash=node('input');hash.placeholder='SHA-256 esperado (opcional)';hash.setAttribute('aria-label','SHA-256 esperado');const progress=node('p','Nenhuma transferência iniciada.','section-note');let transfer=null,cancelled=false;
    const cancel=button('Cancelar transferência',()=>task(async()=>{cancelled=true;if(transfer){await api('control/transfer/cancel',{id:transfer});progress.textContent='Cancelamento solicitado: só staging próprio será removido.'}}));cancel.disabled=true;
    const upload=button('Importar arquivo local (não ativar LLM)',()=>task(async()=>{const source=file.files[0];if(!source)throw Error('Selecione um GGUF existente.');if(!confirm('Arquivar '+source.name+'? Não ativa novo executor nem substitui pesos.'))return;upload.disabled=true;cancel.disabled=false;cancelled=false;try{const started=await api('control/import',{entity:out.entity,name:source.name,size:source.size,...(hash.value.trim()?{sha256:hash.value.trim().toLowerCase()}:{})});transfer=started.id;for(let offset=0;offset<source.size&&!cancelled;offset+=started.chunk_bytes){const chunk=source.slice(offset,offset+started.chunk_bytes);const response=await fetch('/api/control/upload?id='+encodeURIComponent(transfer)+'&offset='+offset,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/octet-stream'},body:chunk});const result=await response.json();if(!response.ok)throw Error(result.error||'Fragmento não confirmado.');progress.textContent='Recebido '+Math.round(result.offset/source.size*100)+'% · '+bytes(result.offset)+' / '+bytes(source.size)}if(!cancelled){const result=await api('control/import/finish',{id:transfer});progress.textContent='SHA-256 '+result.sha256+' · '+result.path+' · arquivo verificado, compatibilidade de executor NÃO estabelecida.'}}finally{upload.disabled=false;cancel.disabled=true}}));
    section.append(file,hash,upload,cancel,progress);for(const r of inventory.items){const row=node('details');row.append(node('summary',(r.consumers.join(', ')||'Arquivo sem consumidor automático')+' · '+r.name+' · '+bytes(r.size_bytes)),kv([['Caminho',r.path],['Hash esperado',r.sha256||'não disponível'],['Hash integral confirmado',r.hash_verified]]),button('Exportar cópia local com verificação',()=>task(async()=>{if(!confirm('Copiar '+bytes(r.size_bytes)+' para Entregas/saída? Espaço e integridade serão verificados.'))return;const job=await api('control/export',{entity:out.entity,id:r.id});transfer=job.id;cancel.disabled=false;progress.textContent='Cópia aceita, ainda NÃO verificada. Acompanhe em Atividade: '+job.id+' · destino '+job.path})));section.append(row)}panel.append(section)}catch(e){notice(e.message)}};
  result.overlayButtons=section=>section.append(button('Abrir orbes (Qt local)',()=>task(async()=>{const out=await api('control/overlay/start',{});notice(out.note||'Overlay já em execução.')})),button('Status do overlay',()=>task(async()=>{const out=await api('control/overlay');notice(out.process_alive?'Processo do overlay vivo; confira visualmente os três orbes.':'Overlay não está em execução. Backend/entidades permanecem independentes.')})));
  const focusId=submissionId();const reportFocus=()=>api('control/focus',{client_id:focusId,focused:document.hasFocus()&&!document.hidden},true).catch(()=>{});
  window.addEventListener('focus',reportFocus);window.addEventListener('blur',reportFocus);document.addEventListener('visibilitychange',reportFocus);
  const focusTimer=setInterval(reportFocus,15000);reportFocus();
  window.addEventListener('pagehide',()=>{clearInterval(focusTimer);api('control/focus',{client_id:focusId,focused:false,closed:true},true).catch(()=>{});window.removeEventListener('focus',reportFocus);window.removeEventListener('blur',reportFocus);document.removeEventListener('visibilitychange',reportFocus)});
  const requestedEntity=new URLSearchParams(location.search).get('entity');if(names[requestedEntity])selectEntity(requestedEntity);
  $('microphone').addEventListener('change',()=>{try{localStorage.setItem('central-microphone',$('microphone').value)}catch{}});
  const attach=node('input');attach.type='file';attach.hidden=true;attach.setAttribute('aria-label','Anexo para entrada da entidade');$('compose').append(attach);document.querySelector('#compose .actions').append(button('Anexar arquivo',()=>{if(!chatReadOnly)attach.click()}));
  attach.onchange=()=>task(async()=>{if(chatReadOnly)throw Error('Abra Hoje antes de anexar uma mensagem.');const source=attach.files[0];if(!source)return;const entity=$('entity').value,session=chatSession?.id;if(source.size>8*1024**2)throw Error('Anexo limitado a 8 MiB; use Modelos para pesos GGUF.');const response=await fetch('/api/control/attachment?entity='+entity+'&name='+encodeURIComponent(source.name),{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/octet-stream'},body:source});const out=await response.json();if(!response.ok)throw Error(out.error||'Anexo não confirmado.');const same=$('entity').value===entity&&chatSession?.id===session&&!chatReadOnly;const existing=same?$('text').value:(drafts.get(entity)||'');const draft=existing+'\nDeixei o arquivo "'+out.name+'" na sua entrada de arquivos. ';drafts.set(entity,draft);if(same)$('text').value=draft;notice('Arquivo recebido na entrada de '+names[entity]+'. Referência guardada no rascunho; o conteúdo não foi executado.');attach.value=''});
  let panelBusy=false;const timer=setInterval(async()=>{if(document.hidden||panelBusy||!['Atividade','Recursos'].includes(active))return;panelBusy=true;try{await load(active)}finally{panelBusy=false}},5000);
  window.addEventListener('pagehide',()=>clearInterval(timer));
  queueMicrotask(()=>show('Conversa'));
  return result;
})();
