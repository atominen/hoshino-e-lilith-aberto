"""Fixtures offline: nenhum console, credencial, memória ou motor real."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from core import alistair_execution as execution, alistair_backend as backend, xbox_alistair as xbox


def native(pid=123,seq=1,diagnostic=False):
    return dict(schema_version=1,service='xllama-resource-probe',package_full_name=xbox.PFN,process_id=pid,
                diagnostics_only=diagnostic,snapshot_not_atomic=True,ram_gpu_pools_may_overlap=True,
                sequence=str(seq),monotonic_ms=str(seq*100),
                app_memory=dict(source='Windows.System.MemoryManager',supported=True,usage_bytes=str(3*1024**3),
                    limit_bytes=str(5*1024**3),headroom_bytes=str(2*1024**3),usage_level=1),
                gpu_memory=dict(source='IDXGIAdapter3.QueryVideoMemoryInfo',enumeration_complete=True,
                    adapters=[dict(supported=True,local=dict(supported=True,budget_bytes=str(4*1024**3),
                        usage_bytes=str(2*1024**3),headroom_bytes=str(2*1024**3)))]))


PAYLOAD=dict(model='alistair-qwen3.5-4b:latest',stream=False,think=False,
             messages=[dict(role='system',content='Identidade fixture.'),dict(role='user',content='oi')],
             options=dict(num_ctx=8192,num_predict=128,num_gpu=0,num_thread=4,temperature=.45))
TOOL={'type':'function','function':{'name':'central_estado','description':'Lê estado','parameters':{'type':'object','properties':{}}}}


class ModelLimitsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.env=self.root/'entidades/alistair/config/alistair.env';self.env.parent.mkdir(parents=True)

    def test_same_saved_limits_and_primary_context_precedes_legacy(self):
        self.env.write_text('HOSHINO_NUM_CTX=2048\nexport HOSHINO_CONTEXT_TOKENS="4096"\nHOSHINO_NUM_PREDICT=512\nOTHER=preserve\n')
        self.assertEqual(xbox.model_limits(self.root),dict(context=4096,output=512))
        self.env.write_text('HOSHINO_NUM_CTX=2048\nHOSHINO_NUM_PREDICT=256\n')
        self.assertEqual(xbox.model_limits(self.root),dict(context=2048,output=256))

    def test_defaults_and_malformed_or_unsafe_values(self):
        self.assertEqual(xbox.model_limits(self.root),dict(context=8192,output=768))
        for context,output in [('16384','768'),('4097','768'),('2048','1800'),('4096','-1'),('$(echo 8192)','768')]:
            self.env.write_text(f'HOSHINO_CONTEXT_TOKENS={context}\nHOSHINO_NUM_PREDICT={output}\n')
            with self.subTest(context=context,output=output),self.assertRaises(ValueError):xbox.model_limits(self.root)
        for context,output in [(True,128),(4096,True)]:
            with self.assertRaises(ValueError):xbox.validate_limits(context,output)

    def test_manifest_tracks_context_not_only_output(self):
        bundle=dict(files=[dict(name='model.gguf',sha256='a'*64,size=1)])
        controls=xbox.controls(bundle,context=4096)
        self.assertEqual(json.loads(controls['manifest.json'])['models'][0]['n_ctx'],4096)
        self.assertEqual(controls['gguf_gpu_layers.txt'],b'33\n')


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_default_local_no_network_and_legacy_preserved(self):
        self.assertEqual(execution.destination(self.root),'local');self.assertIsNone(backend.configured(self.root))
        old=self.root/'compartilhado/config/alistair_pc2.json';old.parent.mkdir(parents=True)
        old.write_text(json.dumps(dict(enabled=True)))
        self.assertEqual(execution.destination(self.root),'pc2');self.assertFalse(execution.is_remote(self.root))
        self.assertEqual(json.loads(old.read_text()),dict(enabled=True))

    def test_selection_bad_schema_bool_or_public_ip_fails(self):
        for data in ({'destination':'cloud'},{'auto_start':1},{'xbox_ip':'8.8.8.8'},{'password':'no'}):
            with self.subTest(data=data):
                xbox.write_json(execution.path(self.root),data)
                with self.assertRaises(ValueError):execution.settings(self.root)

    def test_explicit_local_ignores_legacy_without_changing_it(self):
        old=self.root/'compartilhado/config/alistair_pc2.json';xbox.write_json(old,dict(enabled=True))
        xbox.write_json(execution.path(self.root),dict(destination='local'))
        self.assertIsNone(backend.configured(self.root));self.assertTrue(json.loads(old.read_text())['enabled'])

    def test_secrets_private_not_exposed_by_settings(self):
        xbox.save_secret(self.root,'fixture','fixture-secret')
        self.assertEqual(xbox.secret_path(self.root).stat().st_mode&0o777,0o600)
        self.assertNotIn('password',execution.settings(self.root))
        xbox.secret_path(self.root).chmod(0o644)
        with self.assertRaises(ValueError):xbox.secrets(self.root)


class WireTests(unittest.TestCase):
    def test_applied_context_and_output_bound_requests_without_silent_reduction(self):
        payload=copy.deepcopy(PAYLOAD);payload['options'].update(num_ctx=4096,num_predict=256)
        self.assertEqual(xbox.translate(payload,context_limit=4096,output_limit=512)['max_completion_tokens'],256)
        for option,value in [('num_ctx',8192),('num_predict',513)]:
            bad=copy.deepcopy(payload);bad['options'][option]=value
            with self.subTest(option=option),self.assertRaises(ValueError):xbox.translate(bad,context_limit=4096,output_limit=512)

    def test_native_kv_must_match_loaded_context(self):
        log='offloaded 33/33 layers to GPU\nLoRA host placement: OFF (baseline)\nCPU KV buffer size = 128.00 MiB\n'
        xbox.confirm_profile(log,False,4096)
        with self.assertRaisesRegex(ValueError,'KV'):xbox.confirm_profile(log,False,8192)

    def test_lazy_kv_only_before_first_generation_never_when_publishing_reply(self):
        log='offloaded 33/33 layers to GPU\nLoRA host placement: OFF (baseline)\n'
        self.assertFalse(xbox.confirm_profile(log,False,4096,allow_lazy_context=True))
        with self.assertRaises(ValueError):xbox.confirm_profile(log,False,4096)
        with self.assertRaises(ValueError):xbox.confirm_profile(log+'prefill starting:\nsession generate:\n',False,4096,allow_lazy_context=True)

    def test_text_and_order_not_mutated_or_cut(self):
        payload=copy.deepcopy(PAYLOAD);before=copy.deepcopy(payload);wire=xbox.translate(payload)
        self.assertEqual(payload,before);self.assertEqual(wire['messages'],payload['messages'])
        self.assertEqual(wire['max_completion_tokens'],128);self.assertEqual(wire['model'],xbox.MODEL)
        self.assertEqual(wire['chat_template_kwargs'],dict(enable_thinking=False))

    def test_tool_results_keep_exact_content_and_matching_ids(self):
        payload=copy.deepcopy(PAYLOAD);payload['tools']=[TOOL]
        payload['messages'] += [dict(role='assistant',content='',tool_calls=[dict(id='call_1',type='function',function=dict(name='central_estado',arguments={'q':'fixture'}))]),
                                dict(role='tool',tool_name='central_estado',content='{"ok":true,"exact":19}')]
        wire=xbox.translate(payload)
        self.assertEqual(wire['messages'][-1],dict(role='tool',tool_call_id='call_1',content='{"ok":true,"exact":19}'))
        self.assertEqual(json.loads(wire['messages'][-2]['tool_calls'][0]['function']['arguments']),{'q':'fixture'})

    def test_receipt_name_is_validated_but_not_duplicated_on_openai_wire(self):
        payload=copy.deepcopy(PAYLOAD);payload['tools']=[TOOL]
        payload['messages'] += [dict(role='assistant',content='',tool_calls=[dict(id='unique_call',function=dict(name='central_estado',arguments={}))]),
                                dict(role='tool',tool_name='central_estado',tool_call_id='unique_call',content='fixture')]
        wire=xbox.translate(payload)
        call=wire['messages'][-2]['tool_calls'][0]
        receipt=wire['messages'][-1]
        self.assertEqual(call['function']['name'],'central_estado')
        self.assertEqual(receipt['tool_call_id'],call['id']);self.assertNotIn('name',receipt)
        payload['messages'][-1]['tool_name']='other'
        with self.assertRaises(ValueError):xbox.translate(payload)

    def test_receipt_mismatch_missing_or_unhandled_fields_rejected(self):
        variants=[PAYLOAD|{'messages':[dict(role='tool',content='{}',tool_name='central_estado')]},
                  PAYLOAD|{'messages':[dict(role='user',content='oi',images=['x'])]},
                  PAYLOAD|{'messages':[dict(role='user',content='oi',thinking='cannot discard')]},
                  PAYLOAD|{'options':{'num_ctx':16384}},PAYLOAD|{'options':{'num_predict':-1}},
                  PAYLOAD|{'stream':True},PAYLOAD|{'options':{'num_ctx':True}},PAYLOAD|{'options':{'temperature':float('nan')}}]
        for payload in variants:
            with self.subTest(payload=payload),self.assertRaises(ValueError):xbox.translate(payload)

    def test_response_complete_only_and_offered_tools(self):
        value=dict(model=xbox.MODEL,choices=[dict(finish_reason='stop',message=dict(role='assistant',content='Oi.'))])
        self.assertEqual(xbox.response_message(value,[])['content'],'Oi.')
        for finish in ('length',None,'error'):
            invalid=copy.deepcopy(value);invalid['choices'][0]['finish_reason']=finish
            with self.assertRaises(ValueError):xbox.response_message(invalid,[])
        call=dict(id='c1',type='function',function=dict(name='central_estado',arguments='{}'))
        value['choices'][0]=dict(finish_reason='tool_calls',message=dict(role='assistant',content=None,tool_calls=[call]))
        self.assertEqual(xbox.response_message(value,[TOOL])['tool_calls'][0]['function']['arguments'],{})
        with self.assertRaises(ValueError):xbox.response_message(value,[])

    def test_reasoning_spill_is_not_published_as_speech(self):
        value=dict(model=xbox.MODEL,choices=[dict(finish_reason='stop',message=dict(role='assistant',content='internal fixture\n</think>\nfixture final'))])
        with self.assertRaisesRegex(ValueError,'raciocínio'):xbox.response_message(value,[])

    def test_resources_require_game_exact_scope_and_consistent_counters(self):
        self.assertGreater(xbox.resource_guard(native(),123)['gpu_headroom_bytes'],0)
        for change in ('app','gpu','scope','sequence','level'):
            raw=native()
            if change=='app':raw['app_memory']['limit_bytes']=str(1024**3)
            if change=='gpu':raw['gpu_memory']['adapters'][0]['local']['headroom_bytes']='1'
            if change=='scope':raw['package_full_name']='other'
            if change=='sequence':raw['sequence']=True
            if change=='level':raw['app_memory']['usage_level']=3
            with self.subTest(change=change),self.assertRaises(ValueError):xbox.resource_guard(raw,123)

    def test_only_technical_paths(self):
        for directory,name in [(xbox.LOCAL,'database.db'),('\\LocalState\\..\\identity','model.gguf')]:
            with self.assertRaises(ValueError):xbox.file_route(directory=directory,name=name)
        self.assertIn('manifest.json',xbox.file_route(name='manifest.json'))


class PortalInventoryTests(unittest.TestCase):
    def inventory(self,rows,**kwargs):
        portal=object.__new__(xbox.Portal)
        portal.get=Mock(side_effect=[{'InstalledPackages':[{'PackageFullName':xbox.PFN}]},{'Processes':rows}])
        return portal.inventory(**kwargs)

    @staticmethod
    def row(name,pid=123,package=xbox.PFN):
        return dict(ImageName=name,ProcessId=pid,PackageFullName=package,IsRunning=True)

    def test_one_executor_with_own_windows_broker_is_not_concurrent(self):
        self.assertEqual(self.inventory([self.row('RuntimeBroker.exe',3520),self.row('xllama.exe',6368)]),6368)

    def test_broker_lingering_after_app_exit_is_not_an_executor(self):
        self.assertIsNone(self.inventory([self.row('RuntimeBroker.exe',3520)]))

    def test_stopped_broker_is_not_an_executor_or_unknown_process(self):
        self.assertIsNone(self.inventory([self.row('RuntimeBroker.exe',3520)|{'IsRunning':False}]))

    def test_stopping_app_pid_must_disappear_not_only_turn_false(self):
        row=self.row('xllama.exe',6368)|{'IsRunning':False}
        with self.assertRaises(ValueError):self.inventory([row])
        self.assertEqual(self.inventory([row],stopping=True),6368)
        self.assertIsNone(self.inventory([],stopping=True))

    def test_stopping_does_not_allow_unknown_or_concurrent_processes(self):
        for rows in ([self.row('unknown.exe',1)|{'IsRunning':False}],
                     [self.row('xllama.exe',1),self.row('xllama.exe',2)]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):self.inventory(rows,stopping=True)

    def test_second_executor_foreign_package_or_unknown_companion_stays_blocked(self):
        variants=[ [self.row('xllama.exe',1),self.row('xllama.exe',2)],
                   [self.row('xllama.exe',1,package='other.xllama')],
                   [self.row('xllama.exe',1),self.row('unknown.exe',2)],
                   [self.row('xllama.exe',1),self.row('RuntimeBroker.exe',1)] ]
        for rows in variants:
            with self.subTest(rows=rows),self.assertRaises(ValueError):self.inventory(rows)

    def test_uncertain_process_flags_or_pid_stay_blocked(self):
        for change in ({'IsRunning':False},{'ProcessId':True},{'ProcessId':0}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.inventory([self.row('xllama.exe')|change])


class PortalUploadTests(unittest.TestCase):
    def test_upload_uses_singular_route_and_exact_streamed_multipart(self):
        from urllib.parse import parse_qs,urlsplit
        portal=object.__new__(xbox.Portal);record=[]
        def mutate(method,target,chunks,headers):
            record.append((method,target,b''.join(chunks),headers))
        portal.mutate=Mock(side_effect=mutate)
        value=b'1\n';portal.upload('resource-probe.flag',value,len(value),hashlib.sha256(value).hexdigest())
        portal.mutate.assert_called_once()
        method,target,body,headers=record[0]
        self.assertEqual(method,'POST');self.assertEqual(urlsplit(target).path,'/api/filesystem/apps/file')
        self.assertEqual(parse_qs(urlsplit(target).query)['path'],[xbox.LOCAL])
        self.assertEqual(parse_qs(urlsplit(target).query)['extract'],['false'])
        self.assertEqual(len(body),int(headers['Content-Length']))
        self.assertIn(b'filename="resource-probe.flag"',body);self.assertIn(b'\r\n\r\n1\n\r\n--',body)

    def test_upload_rejects_non_technical_filename_before_sending(self):
        portal=object.__new__(xbox.Portal);portal.mutate=Mock()
        with self.assertRaises(ValueError):portal.upload('memory.db',b'x',1,hashlib.sha256(b'x').hexdigest())
        portal.mutate.assert_not_called()


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.portal=Mock();self.portal.inventory.return_value=123
        self.client=xbox.Client(self.root,settings=dict(destination='xbox',xbox_ip='127.0.0.1',auto_start=True,auto_sync=True,trusted_lan=True),portal_factory=lambda *args:self.portal)
        self.state=dict(state='ready',pending=None,model_alias=PAYLOAD['model'],observed_at=time.time(),
                        context=8192,model_limits=dict(context=8192,output=768))
        xbox.write_json(self.client.path,self.state)
        self.sequence=0
        def observe(*args,**kwargs):
            self.sequence+=1
            return xbox.resource_guard(native(seq=self.sequence),123)
        self.client.observe=Mock(side_effect=observe)
        self.answer=dict(model=xbox.MODEL,choices=[dict(finish_reason='stop',message=dict(role='assistant',content='Resposta fixture.'))],usage=dict(completion_tokens=5,prompt_tokens=8))
        profile=patch.object(xbox,'confirm_profile',return_value=True);self.profile=profile.start();self.addCleanup(profile.stop)

    def test_success_commits_only_technical_state_not_transcript(self):
        delta='prefill starting: n=3\nsession generate: n=5 prefill=1ms (3 tok)\n'
        with patch.object(xbox,'log_current',side_effect=['baseline\n','baseline\n'+delta]),patch.object(self.client,'monitored_request',return_value=self.answer):
            result=self.client.infer('one',PAYLOAD)
        self.assertTrue(result['done']);raw=self.client.path.read_text()
        self.assertNotIn('Resposta fixture',raw);self.assertNotIn('Identidade fixture',raw)
        state=json.loads(raw);self.assertIsNone(state['pending']);self.assertEqual(state['state'],'ready')

    def test_timeout_survives_restart_blocks_any_new_send(self):
        with patch.object(xbox,'log_current',return_value=''),patch.object(self.client,'monitored_request',side_effect=TimeoutError),self.assertRaises(backend.RemotePending):
            self.client.infer('one',PAYLOAD)
        state=xbox.read_json(self.client.path);self.assertEqual(state['pending']['id'],'one')
        another=xbox.Client(self.root,settings=self.client.settings,portal_factory=Mock())
        with self.assertRaises(backend.RemotePending):another.infer('two',PAYLOAD)
        another.portal_factory.assert_not_called()

    def test_context_cut_or_truncation_never_releases_tools(self):
        for i,(delta,answer) in enumerate([('api: dropped 1 oldest message(s)\nprefill starting:\nsession generate:\n',self.answer),
                             ('prefill starting:\nsession generate:\n',dict(model=xbox.MODEL,choices=[dict(finish_reason='length',message=dict(role='assistant',content='incomplete'))]))]):
            xbox.write_json(self.client.path,self.state)
            with patch.object(xbox,'log_current',side_effect=['base\n','base\n'+delta]),patch.object(self.client,'monitored_request',return_value=answer),self.assertRaises(backend.RemotePending):self.client.infer('one'+str(i),PAYLOAD)
            self.assertEqual(xbox.read_json(self.client.path)['state'],'blocked')

    def test_readiness_is_cached_only_no_start(self):
        self.assertTrue(self.client.ready());self.portal.inventory.assert_not_called()
        xbox.write_json(self.client.path,self.state|{'observed_at':time.time()-31})
        self.assertFalse(self.client.ready())

    def test_changed_or_unapplied_limits_reject_before_any_network_or_receipt(self):
        self.state['model_limits']['output']=512;xbox.write_json(self.client.path,self.state)
        self.assertFalse(self.client.ready())
        with self.assertRaisesRegex(backend.RemoteUnavailable,'aplicada'):self.client.infer('not-sent',PAYLOAD)
        self.client.observe.assert_not_called();self.portal.mutate.assert_not_called()
        self.assertFalse((self.client.path.parent/'requests').exists())

    def test_prepared_smaller_context_bounds_usage_counts(self):
        self.state.update(context=4096,model_limits=dict(context=4096,output=768));xbox.write_json(self.client.path,self.state)
        payload=copy.deepcopy(PAYLOAD);payload['options']['num_ctx']=4096
        self.answer['usage']['prompt_tokens']=4097
        with patch.object(xbox,'model_limits',return_value=self.state['model_limits']),patch.object(xbox,'log_current',side_effect=['base\n','base\nprefill starting:\nsession generate:\n']),patch.object(self.client,'monitored_request',return_value=self.answer),self.assertRaises(backend.RemotePending):
            self.client.infer('over-applied-window',payload)

    def test_pending_reconcile_is_read_only_and_never_replays(self):
        xbox.write_json(self.client.path,self.state|{'pending':dict(operation='infer',id='one'),'state':'blocked'})
        with patch.object(xbox,'log_current',return_value='prefill starting:\nsession generate:\n'):
            result=self.client.reconcile()
        self.assertFalse(result['replayed']);self.portal.mutate.assert_not_called()
        state=xbox.read_json(self.client.path);self.assertIsNone(state['pending']);self.assertEqual(state['state'],'needs_prepare')

    def test_never_stop_unknown_or_busy_instance(self):
        self.state['managed_pid']=444;xbox.write_json(self.client.path,self.state)
        self.assertFalse(self.client.unload());self.portal.mutate.assert_not_called()
        self.state['managed_pid']=123;xbox.write_json(self.client.path,self.state)
        with patch.object(xbox,'log_current',return_value='prefill starting:'),self.assertRaises(backend.RemotePending):self.client.unload()
        self.portal.mutate.assert_not_called()

    def test_state_lock_rejects_parallel_control(self):
        with self.client.locked():
            with self.assertRaises(backend.RemotePending):
                with self.client.locked():pass

    def test_current_process_telemetry_must_advance(self):
        del self.client.observe
        with patch.object(self.client,'api',return_value=native()):
            self.client.observe(self.portal)
            with self.assertRaises(ValueError):self.client.observe(self.portal)

    def test_prepare_refuses_untrusted_lan_without_connecting(self):
        self.client.settings['trusted_lan']=False
        self.client.portal_factory=Mock()
        with self.assertRaises(ValueError):self.client.prepare()
        self.client.portal_factory.assert_not_called()

    def test_native_reused_call_ids_are_namespaced_per_request(self):
        payload=PAYLOAD|{'tools':[TOOL]}
        self.answer['choices'][0]=dict(finish_reason='tool_calls',message=dict(role='assistant',content=None,tool_calls=[dict(id='call_1',function=dict(name='central_estado',arguments='{}'))]))
        ids=[]
        for identifier in ('round1','round2'):
            with patch.object(xbox,'log_current',side_effect=['base\n','base\nprefill starting:\nsession generate:\n']),patch.object(self.client,'monitored_request',return_value=self.answer):
                ids.append(self.client.infer(identifier,payload)['message']['tool_calls'][0]['id'])
        self.assertNotEqual(*ids)

    def test_complete_tool_at_output_cap_is_rejected(self):
        self.answer['usage']['completion_tokens']=128
        with patch.object(xbox,'log_current',side_effect=['base\n','base\nprefill starting:\nsession generate:\n']),patch.object(self.client,'monitored_request',return_value=self.answer),self.assertRaises(backend.RemotePending):
            self.client.infer('one',PAYLOAD)

    def test_even_completed_inference_id_cannot_be_reposted_after_restart(self):
        with patch.object(xbox,'log_current',side_effect=['base\n','base\nprefill starting:\nsession generate:\n']),patch.object(self.client,'monitored_request',return_value=self.answer):
            self.client.infer('one',PAYLOAD)
        another=xbox.Client(self.root,settings=self.client.settings,portal_factory=Mock())
        with self.assertRaisesRegex(backend.RemotePending,'ID já enviado'):another.infer('one',PAYLOAD)
        another.portal_factory.assert_not_called()


class FakePortal:
    def __init__(self,bundle):
        self.leaf='fixture-leaf';self.pid=123;self.next_pid=124;self.calls=[];self.hashes=[];self.dirs={xbox.LOCAL,xbox.LOCAL+'\\models',xbox.MODEL_DIR}
        self.files={(xbox.LOCAL,n):v for n,v in xbox.controls(bundle).items()}
        for f in bundle['files']:self.files[xbox.MODEL_DIR,f['name']]=Path(f['source']).read_bytes()
    def read(self,name,directory=xbox.LOCAL):
        if name=='xllama.log':
            log='App::OnLaunched\n'
            if self.files.get((xbox.LOCAL,'resource-probe.flag'))!=b'1\n':
                log+='offloaded 33/33 layers to GPU\nSession: GGUF model loaded\nLoRA host placement: '+('opt-in ON'if self.files[xbox.LOCAL,'gguf_lora_host.flag']==b'1\n'else'OFF (baseline)')+'\n'
                context=json.loads(self.files[xbox.LOCAL,'manifest.json'])['models'][0]['n_ctx']
                log+=f'CPU KV buffer size = {context/32:.2f} MiB\n'
                if self.files[xbox.LOCAL,'gguf_lora_host.flag']==b'1\n':log+='D3D12 LoRA host placement: 248 F16 pairs, unchanged values\nCPU LoRA buffer size = 15.48 MiB\n'
            return log.encode()
        return self.files.get((directory,name))
    def inventory(self, *, stopping=False):return self.pid
    def get(self,route):
        from urllib.parse import parse_qs,urlsplit
        directory=parse_qs(urlsplit(route).query)['path'][0]
        rows=[dict(Name=n,FileSize=len(v),Type=0,LastWriteTime=hashlib.sha256(v).hexdigest())for (d,n),v in self.files.items()if d==directory]
        for d in self.dirs:
            if d.rsplit('\\',1)[0]==directory:rows.append(dict(Name=d.rsplit('\\',1)[1],FileSize=0,Type=16))
        return dict(Items=rows)
    def hash_file(self,name,size,directory):
        self.hashes.append(name);return hashlib.sha256(self.files[directory,name]).hexdigest()
    def mutate(self,method,target):
        self.calls.append((method,target))
        if method=='DELETE':self.pid=None
        else:self.pid=self.next_pid;self.next_pid+=1
    def upload(self,name,source,size,digest,directory=xbox.LOCAL):
        self.calls.append(('upload',name))
        self.files[directory,name]=source if isinstance(source,bytes)else Path(source).read_bytes()
    def mkdir(self,parent,name):self.dirs.add(parent+'\\'+name)
    def close(self):pass


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.bundle=dict(alias=PAYLOAD['model'],fingerprint='fixture',files=[])
        for name in ('model.gguf','adapter.gguf'):
            p=self.root/name;p.write_bytes(('fixture '+name).encode())
            self.bundle['files'].append(dict(name=name,size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source=str(p)))
        self.portal=FakePortal(self.bundle)
        self.client=xbox.Client(self.root,settings=dict(destination='xbox',xbox_ip='127.0.0.1',auto_start=True,auto_sync=True,trusted_lan=True),portal_factory=lambda *args:self.portal)
        self.seq=0
        def api(*args,**kwargs):
            self.seq+=1;return native(self.portal.pid,self.seq,self.portal.files.get((xbox.LOCAL,'resource-probe.flag'))==b'1\n')
        self.client.api=Mock(side_effect=api)
        self.bundle_patch=patch.object(xbox,'local_bundle',side_effect=lambda *a:copy.deepcopy(self.bundle));self.bundle_patch.start();self.addCleanup(self.bundle_patch.stop)

    def save_limits(self,context,output):
        path=self.root/'entidades/alistair/config/alistair.env';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(f'HOSHINO_CONTEXT_TOKENS={context}\nHOSHINO_NUM_PREDICT={output}\n')

    def test_saved_context_sync_reloads_only_controls_and_confirms_native_cache(self):
        self.client.prepare();self.portal.calls.clear();self.save_limits(4096,512)
        state=self.client.prepare()
        self.assertEqual(state['context'],4096);self.assertEqual(state['model_limits'],dict(context=4096,output=512))
        self.assertEqual(json.loads(self.portal.files[xbox.LOCAL,'manifest.json'])['models'][0]['n_ctx'],4096)
        self.assertEqual([m for m,t in self.portal.calls if m in ('DELETE','POST')],['DELETE','POST','DELETE','POST'])
        uploads=[n for m,n in self.portal.calls if m=='upload']
        self.assertIn('manifest.json',uploads);self.assertFalse(any(n.endswith('.gguf')for n in uploads))
        self.portal.calls.clear();self.client.prepare();self.assertEqual(self.portal.calls,[])

    def test_output_only_change_records_limits_without_reloading_existing_idle_model(self):
        self.client.prepare();self.portal.calls.clear();self.save_limits(8192,512)
        state=self.client.prepare();self.assertEqual(state['model_limits']['output'],512)
        self.assertEqual(self.portal.calls,[])

    def test_invalid_settings_before_connect_and_change_during_preparation_blocked(self):
        self.save_limits(16384,768);self.client.portal_factory=Mock()
        with self.assertRaises(ValueError):self.client.prepare()
        self.client.portal_factory.assert_not_called()
        self.client.portal_factory=lambda *a:self.portal;self.save_limits(8192,768)
        with patch.object(xbox,'model_limits',side_effect=[dict(context=8192,output=768),dict(context=4096,output=768)]),self.assertRaises(backend.RemotePending):self.client.prepare()
        self.assertEqual(xbox.read_json(self.client.path)['state'],'blocked')

    def test_busy_generation_never_restarts_for_new_context(self):
        self.save_limits(4096,512)
        with patch.object(xbox,'log_current',return_value='prefill starting:'),self.assertRaises(backend.RemotePending):self.client.prepare()
        self.assertEqual(self.portal.calls,[])

    def test_ready_bundle_not_uploaded_or_restarted_and_hashes_not_repeated(self):
        self.assertEqual(self.client.prepare()['state'],'ready')
        self.assertEqual(len(self.portal.hashes),2);self.assertEqual(self.portal.calls,[])
        self.client.prepare();self.assertEqual(len(self.portal.hashes),2);self.assertEqual(self.portal.calls,[])

    def test_cold_start_checks_game_even_with_matching_catalog_and_sync_disabled(self):
        self.portal.pid=None;self.client.settings['auto_sync']=False
        state=self.client.prepare()
        self.assertEqual(state['state'],'ready')
        self.assertEqual([m for m,t in self.portal.calls if m in ('POST','DELETE')],['POST','DELETE','POST'])
        self.assertEqual([n for m,n in self.portal.calls if m=='upload'],['resource-probe.flag','resource-probe.flag'])

    def test_ready_does_not_show_stale_errors_and_preserves_the_failure(self):
        xbox.write_json(self.client.path,dict(state='needs_prepare',pending=None,error_type='HTTPError',reason='fixture old failure'))
        state=self.client.prepare()
        self.assertEqual(state['state'],'ready');self.assertNotIn('reason',state);self.assertNotIn('error_type',state)
        self.assertEqual(state['resolved_errors'][-1]['reason'],'fixture old failure')

    def test_profile_sync_stops_then_diagnostic_then_host1_and_normal(self):
        self.portal.files[xbox.LOCAL,'gguf_lora_host.flag']=b'0\n'
        state=self.client.prepare()
        self.assertEqual(state['state'],'ready');self.assertEqual(state['host_mode'],1)
        self.assertEqual(self.portal.files[xbox.LOCAL,'resource-probe.flag'],b'0\n')
        self.assertEqual([m for m,t in self.portal.calls if m in ('DELETE','POST')],['DELETE','POST','DELETE','POST'])
        self.assertEqual(state['managed_pid'],self.portal.pid)

    def test_new_adapter_immutable_and_catalog_only_after_hash(self):
        old=self.portal.files[xbox.MODEL_DIR,'adapter.gguf'];self.client.prepare()
        p=self.root/'new-adapter';p.write_bytes(b'new fixture adapter');sha=hashlib.sha256(p.read_bytes()).hexdigest()
        self.bundle['files'][1].update(source=str(p),size=p.stat().st_size,sha256=sha);self.bundle['fingerprint']='new'
        state=self.client.prepare();name='adapter-'+sha+'.gguf'
        self.assertEqual(self.portal.files[xbox.MODEL_DIR,'adapter.gguf'],old)
        self.assertEqual(self.portal.files[xbox.MODEL_DIR,name],p.read_bytes())
        self.assertEqual(json.loads(self.portal.files[xbox.LOCAL,'manifest.json'])['models'][0]['lora'],name)
        self.assertIn(name,self.portal.hashes);self.assertEqual(state['fingerprint'],'new')
        uploads=[n for op,n in self.portal.calls if op=='upload']
        self.assertLess(uploads.index(name),uploads.index('manifest.json'))

    def test_corruption_blocks_before_any_mutation_and_never_overwrites(self):
        self.portal.files[xbox.MODEL_DIR,'adapter.gguf']=b'x'*len(self.portal.files[xbox.MODEL_DIR,'adapter.gguf'])
        with self.assertRaises(ValueError):self.client.prepare()
        self.assertEqual(self.portal.calls,[]);self.assertEqual(xbox.read_json(self.client.path)['state'],'blocked')
        with self.assertRaises(backend.RemotePending):self.client.prepare()

    def test_original_disables_host_without_deleting_old_adapter(self):
        self.bundle['files']=self.bundle['files'][:1]
        state=self.client.prepare();self.assertEqual(state['host_mode'],0)
        self.assertIn((xbox.MODEL_DIR,'adapter.gguf'),self.portal.files)
        self.assertNotIn('lora',json.loads(self.portal.files[xbox.LOCAL,'manifest.json'])['models'][0])

    def test_upload_failure_keeps_diagnostic_and_old_catalog_and_blocks_start(self):
        p=self.root/'new-adapter';p.write_bytes(b'new fixture adapter');sha=hashlib.sha256(p.read_bytes()).hexdigest()
        self.bundle['files'][1].update(source=str(p),size=p.stat().st_size,sha256=sha)
        old=self.portal.files[xbox.LOCAL,'manifest.json'];upload=self.portal.upload
        def broken(name,*a,**kw):
            if name.startswith('adapter-'):raise OSError('fixture disk full')
            return upload(name,*a,**kw)
        self.portal.upload=broken
        with self.assertRaises(OSError):self.client.prepare()
        self.assertEqual(self.portal.files[xbox.LOCAL,'manifest.json'],old)
        self.assertEqual(self.portal.files[xbox.LOCAL,'resource-probe.flag'],b'1\n')
        self.assertIsNone(self.portal.pid);self.assertIsNotNone(xbox.read_json(self.client.path)['pending'])


if __name__=='__main__':unittest.main()
