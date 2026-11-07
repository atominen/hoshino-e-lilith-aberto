/* Browser real; transporte simulado por padrão, nenhuma GPU/entidade iniciada. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=process.argv[2],real=process.argv[3],shot=process.argv[4];
const {chromium}=require('/home/gustavo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const errors=[],calls=[],entities=['hoshino','lilith','alistair'];
const curation={id:'a'.repeat(16),entity:'hoshino',state:'proposed',example_hashes:{'fixture:001':'hash-fixture-1','fixture:002':'hash-fixture-2'},
 proposal_data:{entity:'hoshino',status:'PROPOSTA_NAO_APROVADA',reason:'Proposta simulada, nenhum professor chamado.',human_reviews:{
  'fixture:002':{decision:'approved',reviewer:'codex_assisted',example_sha256:'hash-fixture-2',note:'Curadoria assistida autorizada — fixture.'}},
  examples:[1,2].map(i=>({source_id:'fixture:00'+i,category:'naturalidade',user:'Situação '+i,assistant:'Resposta '+i,reason:'Motivo concreto '+i,confidence:0,
   messages:[{role:'user',content:'Situação '+i},{role:'assistant',content:'Resposta '+i}]}))}};
const catalog=[{id:'alistair-4b',label:'4B — fixture',installed:true,bytes:4000000000,architecture:'qwen3_5',state:'measured_candidate',description:'Simulado',shards:2,train_enabled:true,exclusive_entity:'alistair'},
 {id:'qwen35-9b',label:'9B — fixture OOM',installed:true,bytes:18000000000,architecture:'qwen3_5',state:'oom',description:'OOM histórico simulado',shards:4,train_enabled:false}];
function fixture(u,body){
 const p=u.pathname,e=u.searchParams.get('entity')||'hoshino';
 if(p==='/api/bootstrap')return {csrf:'fixture-not-a-secret'};
 if(p==='/api/status')return {pipeline:{},disk_free_gib:80,partials:[]};
 if(['/api/mods','/api/treinos/jobs','/api/treinos/artifacts','/api/professor-moe/snapshots'].includes(p))return [];
 if(p==='/api/professor-moe/jobs')return [{id:'f'.repeat(16),entity:'hoshino',purpose:'candidate_review',snapshot:'fixture',state:'candidate_review_failed',evidence_count:8},
  {id:curation.id,entity:'hoshino',state:'proposed',evidence_count:2}];
 if(p==='/api/professor-moe/detail'&&u.searchParams.get('id')===curation.id)return curation;
 if(p==='/api/professor-moe/review-example'){
  curation.proposal_data.human_reviews[body.source_id]={decision:body.decision,note:body.note,as_reference:body.as_reference,
   reviewer:'human',example_sha256:body.expected_hash};return {ok:true,result:{training_started:false}};
 }
 if(p==='/api/professor-moe/detail')return {id:'f'.repeat(16),entity:'hoshino',state:'candidate_review_failed',proposal_data:{purpose:'candidate_review',
   quality_audit:{passed:false,complete:true},reviews:[{source_id:'eval:identity',concerns:['persona_conflict'],reason:'Fixture sem inferência real.'}]}};
 if(p==='/api/treinos/catalog')return catalog;
 if(p==='/api/treinos/datasets')return [{id:e==='alistair'?'datasets-alistair-seed:alistair':'pacote_neural_v3:'+e,label:'Corpus fixture '+e,original:true}];
 if(p==='/api/treinos/preview')return {ok:true,result:{allowed:body.model!=='qwen35-9b',entity:body.entity,dataset:body.dataset,blocker:'Fixture OOM'}};
 if(p==='/api/treinos/recovery-preview')return {ok:true,result:{allowed:true,needed:false,entity:body.entity,model_id:body.model,activate:false}};
 if(p==='/api/treinos/prepare-12h')return {ok:true,result:{allowed:false,execution_started:false,blockers:['Fixture sem benchmark físico'],tasks:[]}};
 if(p==='/api/professor-moe/status')return {ready:false,executor_ready:false,size_bytes:0,integrity:'fixture'};
 if(p==='/api/presets-auto')return {method:'fixture',entities:{}};
 if(p==='/api/personalizacao/status')return {entities:entities.map(id=>({id,name:id,datasets:[],training_jobs:0,teacher_jobs:0,
   cognitive_profiles:id==='alistair'?[]:[{name:'perfil-'+id+'-fixture.json',traits:1,experiences:0,valid:true}],stable_versions:[]}))};
 if(p==='/api/personalizacao/capture')return {ok:true,result:{name:'perfil-'+body.entity+'-fixture.json',entity:body.entity,training_started:false,production_changed:false}};
 if(p==='/api/night')return {state:'idle',fixture:true};
 if(p==='/api/night/schedule-once')return {state:'not_scheduled'};
 if(p==='/api/treinos/prepare-custom')return {ok:true,result:{allowed:false,starts_at:1792807200,ends_at:1792846800,train_minutes_per_model:57,evaluation_minutes_per_model:30,reserve_minutes:51,tasks:[],blockers:['Fixture: falta medição física']}};
 if(p==='/api/night/config')return body?{ok:true,result:body.settings}:{settings:{enabled:false,automatic_data_approval:false,start_time:'00:30',idle_minutes:30,window_minutes:600,train_minutes:10,allow_idle:true,shutdown_after:false},readiness:{state:'fixture'}};
 throw Error('API não coberta na fixture: '+p);
}
(async()=>{
 if(real&&!/^http:\/\/127\.0\.0\.1:\d+$/.test(real))throw Error('Apenas painel loopback explicitamente escolhido');
 const browser=await chromium.launch({executablePath:'/home/gustavo/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome',headless:true,
   args:['--disable-gpu','--disable-background-networking',...(!real?['--host-resolver-rules=MAP * 127.0.0.1']:[])]});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1080}});
  if(!real)await context.route('**/*',async route=>{
   const u=new URL(route.request().url());
   if(u.pathname.startsWith('/api/')){
    calls.push({path:u.pathname,method:route.request().method(),body:route.request().postDataJSON()});
    try{return await route.fulfill({json:fixture(u,route.request().postDataJSON())});}
    catch(e){errors.push(e.message);return route.fulfill({status:404,json:{error:e.message}});}
   }
   const file={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[u.pathname];
   if(!file)return route.abort();
   await route.fulfill({contentType:file.endsWith('.html')?'text/html':file.endsWith('.js')?'application/javascript':'text/css',
                       body:fs.readFileSync(path.join(root,'laboratorio/web',file))});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(real||'http://127.0.0.1:18788/');
  await page.waitForFunction(()=>document.querySelector('#train-model').options.length>=2);
  if(!real){
   await page.waitForFunction(()=>!document.querySelector('#night-auto-save').disabled);
   assert.equal(await page.locator('#night-auto-poweroff').isChecked(),false);
   assert.equal(await page.locator('#night-auto-ai').isChecked(),false);
   assert(calls.some(c=>c.method==='GET'&&c.path==='/api/night/config'));
  }
  assert(!(await page.locator('#modelos').innerText()).includes('configuração atual ainda falha'));
  assert.equal(await page.getByRole('heading',{name:'Log histórico do pipeline',exact:true}).count(),1);
  assert.equal(await page.locator('#train-action option[value=evaluate]').count(),1);
  for(const id of ['train-resume','train-candidate','train-dataset','train-review','train-promote','train-rollback','train-auto-promote',
   'profile-entity','profile-refs','profile-capture','moe-profile','night-window','night-teacher','long-prepare','long-start','long-resume',
   'night-auto-time','night-auto-idle','night-auto-save','night-auto-read','night-auto-enabled'])assert.equal(await page.locator('#'+id).count(),1);
  if(!real){
   await page.locator('#train-model').selectOption('qwen35-9b');assert(await page.locator('#train-start').isDisabled());
   await page.locator('#train-check').click();await page.waitForFunction(()=>document.querySelector('#train-report').textContent.includes('Fixture OOM'));
   await page.locator('#train-model').selectOption('alistair-4b');await page.locator('#train-action').selectOption('train');
   assert.equal(await page.locator('#train-resume').isDisabled(),false);
   await page.getByText('Sessão noturna — supervisor da Central',{exact:true}).click();
   await page.locator('#night-refresh').click();await page.waitForFunction(()=>document.querySelector('#night-report').textContent.includes('idle'));
   await page.locator('#night-auto-read').click();await page.waitForFunction(()=>document.querySelector('#night-auto-report').textContent.includes('fixture'));
   assert.equal(await page.locator('#night-auto-time').inputValue(),'00:30');assert.equal(await page.locator('#night-auto-idle').inputValue(),'30');
   assert.equal(await page.locator('#night-auto-enabled').isChecked(),false);
   await page.locator('#long-prepare').click();await page.waitForFunction(()=>document.querySelector('#long-report').textContent.includes('execution_started'));
   assert(await page.locator('#long-start').isDisabled());
   assert(!calls.some(c=>c.method==='POST'&&!c.path.endsWith('/preview')&&!c.path.endsWith('/prepare-12h')));
   await page.locator('#custom-start').fill('2026-10-23T23:00');await page.locator('#custom-end').fill('2026-10-24T10:00');
   await page.locator('#custom-preview').click();await page.waitForFunction(()=>document.querySelector('#custom-report').textContent.includes('Fixture: falta medição física'));
   assert(await page.locator('#custom-schedule').isDisabled());
   const custom=calls.find(c=>c.path==='/api/treinos/prepare-custom');
   assert.equal(custom.body.starts_at,'2026-10-23T23:00');assert.equal(custom.body.ends_at,'2026-10-24T10:00');
   assert(!calls.some(c=>c.method==='POST'&&c.path==='/api/night/schedule-once'));
   await page.locator('#personalizacao-cards .identity-card').filter({has:page.getByRole('heading',{name:'hoshino',exact:true})}).getByRole('button',{name:'Selecionar para treinar'}).click();
   await page.waitForFunction(()=>document.querySelector('#train-dataset').value==='pacote_neural_v3:hoshino');
   page.on('dialog',d=>d.accept());
   await page.getByText('Recuperar executor ausente — pesos locais',{exact:true}).click();
   await page.locator('#recovery-check').click();
   await page.waitForFunction(()=>document.querySelector('#recovery-report').textContent.includes('Já instalado'));
   await page.locator('#recovery-start').click();
   assert(!calls.some(c=>c.path==='/api/treinos/recovery-start'));
   await page.locator('#night-auto-time').fill('01:15');await page.locator('#night-auto-idle').fill('45');
   await page.locator('#night-auto-save').click();await page.waitForFunction(()=>document.querySelector('#night-auto-report').textContent.includes('01:15'));
   const policy=calls.find(c=>c.method==='POST'&&c.path==='/api/night/config');assert.equal(policy.body.settings.idle_minutes,45);assert.equal(policy.body.settings.enabled,false);
   assert.equal(policy.body.settings.automatic_data_approval,false);assert.equal(await page.locator('#night-auto-ai').isChecked(),false);
   await page.locator('#profile-entity').selectOption('lilith');await page.locator('#profile-capture').click();
   await page.waitForFunction(()=>document.querySelector('#profile-report').textContent.includes('"production_changed": false'));
   assert.equal(await page.locator('#moe-profile').inputValue(),'perfil-lilith-fixture.json');
   await page.getByRole('button',{name:'Ver detalhes',exact:true}).first().click();
   await page.waitForFunction(()=>document.querySelector('#moe-review-note').textContent.includes('crítica independente'));
   assert(await page.locator('#moe-export').isDisabled());
   assert((await page.locator('#moe-review-items').innerText()).includes('eval:identity'));
   await page.getByRole('button',{name:'Ver detalhes',exact:true}).nth(1).click();
   await page.waitForFunction(()=>document.querySelector('.review-example[data-source-id="fixture:001"]'));
   let card=page.locator('.review-example[data-source-id="fixture:001"]');
   const assisted=await page.locator('.review-example[data-source-id="fixture:002"] .review-decision').innerText();
   assert(assisted.includes('CURADORIA ASSISTIDA AUTORIZADA'));assert(!assisted.includes('POR VOCÊ'));
   assert(await card.locator('input[data-export]').isDisabled());
   await card.getByRole('button',{name:'Reprovar',exact:true}).click();
   assert(!calls.some(c=>c.path.endsWith('/review-example')));
   await card.locator('textarea').fill('Ficou genérico <script>falha()</script>');
   await card.getByRole('button',{name:'Reprovar',exact:true}).click();
   await page.waitForFunction(()=>document.querySelector('.review-example .review-decision.rejected'));
   assert(await card.locator('input[data-export]').isDisabled());
   assert.equal(await card.locator('textarea').inputValue(),'Ficou genérico <script>falha()</script>');
   await card.getByRole('button',{name:'Aprovar',exact:true}).click();
   await page.waitForFunction(()=>document.querySelector('.review-example[data-source-id="fixture:001"] .review-decision.approved'));
   assert(!(await card.locator('input[data-export]').isDisabled()));
   const decision=calls.find(c=>c.path.endsWith('/review-example'));
   assert.equal(decision.body.expected_hash,'hash-fixture-1');
   assert(!calls.some(c=>c.path.endsWith('/export')));
   assert(!calls.some(c=>c.path.endsWith('/run')||c.path.endsWith('/start')||c.path.endsWith('/auto-promote')));
   // Mesmo painel, link direto somente leitura: nunca aprovar ao abrir a revisão.
   curation.proposal_data.purpose='reference_examples';curation.proposal_data.authored_by='local_professor';
   const reviewsBefore=calls.filter(c=>c.path.endsWith('/review-example')).length;
   await page.goto('http://127.0.0.1:18788/?review='+curation.id);
   await page.waitForFunction(()=>document.querySelector('#moe-review-note').textContent.includes('DIÁLOGOS GERADOS PELO PROFESSOR'));
   assert(await page.locator('#moe-export').isDisabled());
   assert((await page.locator('#moe-review-result').innerText()).includes('diálogo inteiro'));
   assert.equal(calls.filter(c=>c.path.endsWith('/review-example')).length,reviewsBefore);
   await page.goto('http://127.0.0.1:18788/?review=INVALIDO');
   await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Identificador de revisão inválido'));
   assert.equal(calls.filter(c=>c.path.endsWith('/review-example')).length,reviewsBefore);
  }else{
   // Somente leitura no painel físico: jamais salvar política/autorizar GPU.
   await page.getByText('Sessão noturna — supervisor da Central',{exact:true}).click();
   await page.locator('#night-auto-read').click();
   await page.waitForFunction(()=>!document.querySelector('#night-auto-report').textContent.startsWith('Desativada por padrão.'));
   assert.equal(await page.locator('#night-auto-time').inputValue(),'00:30');
   assert.equal(await page.locator('#night-auto-idle').inputValue(),'30');
   const refs=page.locator('#moe-jobs .job-row').filter({hasText:'hoshino · Referências autorais'});
   if(await refs.count()){
    await refs.first().getByRole('button',{name:'Ver detalhes',exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('.review-example').length===3);
    assert(await page.locator('#moe-export').isDisabled());
    assert.equal(await page.locator('.review-example').first().getByRole('button',{name:'Aprovar',exact:true}).count(),1);
    assert.equal(await page.locator('.review-example').first().getByRole('button',{name:'Reprovar',exact:true}).count(),1);
    // Navegação somente leitura: não decide nem altera dados de produção.
    await page.locator('#moe-review').scrollIntoViewIfNeeded();
   }
  }
  await page.waitForTimeout(500);assert.deepEqual(errors,[]);
  if(shot){
   if(real&&await page.locator('#moe-review').isVisible())await page.locator('#moe-review').screenshot({path:shot});
   else await page.screenshot({path:shot,fullPage:true});
  }
  console.log(JSON.stringify({passed:true,real_panel:!!real,hardware_validated:false,errors,calls:calls.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
