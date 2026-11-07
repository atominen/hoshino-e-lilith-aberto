"""Frases LLM→TTS→player, com workers, reprodução e transporte simulados."""
import asyncio
import contextlib
import io
import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import speech_stream, job_bus, audio_service as audio, gpu_resource
from tools import voice
import test_audio_service as fixtures
from test_audio_service import ServiceFixture, wav_bytes

ROOT=Path(__file__).resolve().parents[1]


class StreamingServiceTests(ServiceFixture):
    def test_stream_has_verified_audience_for_global_and_direct(self):
        from core import interentity as bus
        for scope in ('direct','global'):
            message=bus.send('usuario','lilith','Olá',chat_scope=scope)
            token=bus.processing_message.set(message)
            try:stream=speech_stream.SpeechStream('lilith','localhub')
            finally:bus.processing_message.reset(token)
            stream.push('Olá. Próxima')
            details=job_bus.get(stream.id)['details']
            self.assertEqual(details.get('chat_scope'),scope)
            self.assertEqual(details.get('room_day'),bus.daily_session('lilith')['local_date'])
            self.assertEqual(details.get('reply_to'),message['id'])

    def wait_chunks(self, job, count):
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            state=self.service.get(job['id'])
            if len((state['result'] or {}).get('chunks',[]))>=count: return state
            time.sleep(.01)
        self.fail('Primeira sentença não foi disponibilizada antes da fala completa')

    def test_first_chunk_available_while_next_chunk_is_synthesizing(self):
        release=threading.Event(); self.addCleanup(release.set)
        def synthesis(request,cancel,_timeout):
            if request['text']=='Segunda frase!': release.wait(2)
            Path(request['output']).write_bytes(wav_bytes())
            return {}
        self.service.tts.call.side_effect=synthesis
        job=self.service.submit_speech('hoshino',text='Primeira frase. Segunda frase!')
        first=self.wait_chunks(job,1)
        self.assertEqual(first['status'],'running')
        self.assertTrue(self.service.file(job['id'],0).is_file())
        with self.assertRaises(ValueError): self.service.file(job['id'])
        release.set(); final=self.wait_done(job)
        self.assertEqual([c['index'] for c in final['result']['chunks']],[0,1])

    def test_tts_runs_before_llm_done_but_final_tail_waits_for_commit(self):
        stream=speech_stream.SpeechStream('lilith','localhub')
        stream.push('Olá. Próxima')
        self.addCleanup(stream.stop,'fixture_cleanup')
        job=self.service.submit_stream('lilith',stream.id)
        self.wait_chunks(job,1)
        self.assertEqual(job_bus.get(stream.id)['status'],'running')
        self.assertEqual(self.service.tts.call.call_args.args[0]['text'],'Olá.')
        stream.finish('Olá. Próxima frase!',commit=False)
        self.wait_chunks(job,2)
        self.assertEqual(self.service.get(job['id'])['status'],'running')
        stream.commit(); self.wait_done(job)
        self.assertEqual([c.args[0]['text'] for c in self.service.tts.call.call_args_list],['Olá.','Próxima frase!'])

    def test_interrupted_stream_cancels_pending_chunks_and_removes_only_own_files(self):
        stream=speech_stream.SpeechStream('hoshino','localhub'); stream.push('Primeira. Segunda')
        job=self.service.submit_stream('hoshino',stream.id); self.wait_chunks(job,1)
        existing=self.service.file(job['id'],0).parent/'audio-existing.wav'; existing.write_bytes(wav_bytes())
        stream.stop('user_interruption'); final=self.wait_done(job,'interrupted')
        self.assertTrue(existing.is_file()); self.assertEqual(self.service.tts.call.call_count,1)
        with self.assertRaises(ValueError): self.service.file(final['id'],0)
        self.assertEqual(list(existing.parent.glob(job['id']+'*.wav')),[])

    def test_audio_waiting_for_resource_cancels_before_worker_runs(self):
        from core import resource_manager
        with resource_manager.lease('cpu_audio','occupied'):
            job=self.service.submit_speech('hoshino',text='Não deve ser falada.')
            self.service.cancel(job['id']); self.wait_idle_bounded()
            self.assertEqual(self.service.get(job['id'])['status'],'interrupted')
        self.service.tts.call.assert_not_called()

    def test_done_textual_stream_can_be_invalidated_without_reopening_job(self):
        stream=speech_stream.SpeechStream('hoshino','localhub'); stream.finish('Conversa concluída.')
        stream.stop('user_interruption')
        self.assertEqual(job_bus.get(stream.id)['status'],'done')
        self.assertTrue(job_bus.get(stream.id)['details']['invalidated'])
        job=self.service.submit_stream('hoshino',stream.id)
        self.wait_done(job,'interrupted'); self.service.tts.call.assert_not_called()

    def test_stream_requires_own_entity_channel_and_stable_producer(self):
        stream=speech_stream.SpeechStream('hoshino','localhub'); stream.push('Olá. Próxima')
        self.addCleanup(stream.stop)
        for entity in ('lilith','alistair','../hoshino','unknown'):
            with self.assertRaises(ValueError): self.service.submit_stream(entity,stream.id)
        for details in (dict(channel='discord',stable_only=True),dict(channel='localhub',stable_only=False)):
            job_bus.publish('invalid','hoshino','running',kind='llm_speech',sentences=['Olá.'],**details)
            with self.assertRaises(ValueError): self.service.submit_stream('hoshino','invalid')

    def test_gate_rejects_unverified_claims_and_prefix_rewrite_cancels(self):
        gate=speech_stream.SpeechStream('hoshino','localhub',validator=lambda s:'concluído' not in s.lower())
        gate.push('Concluído. Próxima')
        self.assertTrue(gate.stopped); self.assertIsNone(job_bus.get(gate.id))
        stream=speech_stream.SpeechStream('hoshino','localhub'); stream.push('Primeira. Próxima')
        stream.push('Revisada. Próxima')
        self.assertTrue(stream.stopped); self.assertEqual(job_bus.get(stream.id)['status'],'interrupted')
        self.assertFalse(job_bus.get(stream.id)['details']['auto_retry'])

    def test_private_thinking_leaked_into_content_is_not_spoken(self):
        for text in ('<think>Algo privado. Próxima','[CICLO INTERNO] Planejo. Próxima'):
            stream=speech_stream.SpeechStream('hoshino','localhub'); stream.push(text)
            self.assertTrue(stream.stopped); self.assertEqual(stream.sentences,[])
            self.assertIsNone(job_bus.get(stream.id))

    def test_combined_wav_preserves_order_when_provider_rate_changes(self):
        import array
        paths=[]
        for i,rate in enumerate((24000,16000)):
            buffer=io.BytesIO()
            with audio.wave.open(buffer,'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
                wav.writeframes(array.array('h',[100*(i+1)]*rate).tobytes())
            path=self.root/f'{i}.wav'; path.write_bytes(buffer.getvalue()); paths.append(path)
        output=self.root/'combined.wav'; audio.combine_wavs(paths,output)
        with audio.wave.open(str(output),'rb') as wav:
            samples=array.array('h'); samples.frombytes(wav.readframes(wav.getnframes()))
            self.assertEqual(wav.getframerate(),24000); self.assertEqual(len(samples),48000)
        self.assertEqual(samples[0],100); self.assertEqual(samples[-1],200)

    def test_compute_is_released_before_final_sentence_commit(self):
        from main import InterfaceHoshino
        app=InterfaceHoshino.__new__(InterfaceHoshino); active=[False]
        @contextlib.contextmanager
        def lease(*_args,**_kwargs):
            active[0]=True
            try: yield {'backend':'cpu'}
            finally: active[0]=False
        def generate(payload,request_id,on_content=None):
            self.assertTrue(active[0]); self.assertEqual(payload['options']['num_gpu'],0)
            on_content('Primeira. Segunda')
            return dict(content='Primeira. Segunda!')
        scope=speech_stream.context.set(dict(channel='localhub',validator=lambda _:True,cancelled=lambda:False,streams=[]))
        try:
            with patch.object(gpu_resource,'lease',side_effect=lease),patch.object(app,'_post_ollama_stream',side_effect=generate):
                app._post_ollama_stream_com_lease({'model':'mock'},'test')
            self.assertFalse(active[0]); stream=speech_stream.context.get()['streams'][0]
            self.assertEqual(stream.sentences,['Primeira.','Segunda!'])
            self.assertEqual(job_bus.get(stream.id)['status'],'running'); stream.commit()
            self.assertEqual(job_bus.get(stream.id)['status'],'done')
        finally: speech_stream.context.reset(scope)

    def test_llm_stream_callback_excludes_thinking_and_tool_content(self):
        from main import InterfaceHoshino
        events=[dict(message={'thinking':'privado'}),dict(message={'content':'Olá. '}),
                dict(message={'content':'Próxima','tool_calls':[{'function':{'name':'test','arguments':{}}}]}),
                dict(message={'content':' não narrar'},done=True)]
        response=Mock(iter_lines=Mock(return_value=[json.dumps(e) for e in events]))
        received=[]
        with patch('main.requests.post',return_value=response):
            result=InterfaceHoshino._post_ollama_stream({'model':'mock'},'test',on_content=received.append)
        self.assertEqual(received,['Olá. ']); self.assertIn('tool_calls',result)
        response.close.assert_called_once()


class StreamingHttpTests(ServiceFixture):
    request=fixtures.HttpAudioTests.request
    close_server=fixtures.HttpAudioTests.close_server

    def setUp(self):
        super().setUp()
        self.server,self.token=fixtures.launcher.make_server(fixtures.launcher.Supervisor(),0,audio=self.service)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(self.close_server)

    def test_stream_endpoint_auth_and_completed_chunks(self):
        stream=speech_stream.SpeechStream('hoshino','localhub'); stream.finish('Olá. Segunda.')
        self.request('/api/audio/stream',{'entity':'hoshino','stream_id':stream.id},headers={'Authorization':''},expected=403)
        self.request('/api/audio/stream',{'entity':'lilith','stream_id':stream.id},expected=400)
        job,_=self.request('/api/audio/stream',{'entity':'hoshino','stream_id':stream.id},expected=202)
        self.wait_done(job)
        body,kind=self.request('/api/audio/file?id='+job['id']+'&chunk=0')
        self.assertTrue(body.startswith(b'RIFF')); self.assertIn('audio/wav',kind)
        self.assertEqual(body,self.service.file(job['id'],0).read_bytes())
        self.assertNotEqual(body,self.service.file(job['id']).read_bytes())
        self.request('/api/audio/file?id='+job['id']+'&chunk=-1',expected=400)


class NativeVoiceTests(unittest.TestCase):
    def test_valid_stop_cancels_queued_and_in_progress_before_playback(self):
        async def run():
            entered=threading.Event(); release=threading.Event()
            def synthesis(_text,output,cancel):
                entered.set(); release.wait(2)
                if not cancel.is_set(): Path(output).write_bytes(wav_bytes())
                audio.check_cancel(cancel)
            with tempfile.TemporaryDirectory(prefix='native-voice-') as tmp,\
                 patch.object(voice,'_lock',asyncio.Lock()),patch.object(voice,'RUNTIME_DIR',tmp),\
                 patch.object(voice,'_garantir_mixer',return_value=True),\
                 patch.object(voice,'_routed_synthesis',side_effect=synthesis),\
                 patch.object(voice.pygame.mixer.music,'play') as play,\
                 patch.object(voice.pygame.mixer.music,'stop'),\
                 patch.object(voice.pygame.mixer.music,'unload'):
                first=asyncio.create_task(voice.speak('Primeira frase.',forcar=True))
                while not entered.is_set(): await asyncio.sleep(.01)
                second=asyncio.create_task(voice.speak('Segunda frase.',forcar=True)); await asyncio.sleep(.01)
                voice.parar(); release.set()
                result=await asyncio.wait_for(asyncio.gather(first,second),2)
                self.assertEqual(result,['fala interrompida','fala interrompida']); play.assert_not_called()
        asyncio.run(run())


class PlayerTests(unittest.TestCase):
    def run_player(self,scenario):
        html=(ROOT/'app/ui/central.html').read_text()
        code=html[html.index('async function waitAudioJob'):html.index('function feed')]
        harness=r'''
const scenario=SCENARIO, calls=[], notices=[], nodes={},playback=[];
let valid=true, speechUrl=null,speechSerial=0,speechBusy=false,speechJobId=null,speechEntity=null,capture=null,capturePending=false;
const speechSeen=new Set(),speechInitialized=new Set(),speechStreamsSeen=new Set(),token='mock',entityNames={hoshino:'Hoshino'};
const listeners=new Map();
const player={ended:false,paused:true,error:null,hidden:true,_src:'',
 addEventListener(name,fn){listeners.set(name,fn)},removeEventListener(name){listeners.delete(name)},
 set src(v){this._src=v;this.ended=false},get src(){return this._src},
 async play(){calls.push('play');if(scenario==='manual'&&!this.once){this.once=true;throw Error('autoplay')}listeners.get('playing')?.();this.ended=true},
 pause(){this.paused=true},removeAttribute(){},load(){}};
nodes['voice-player']=player;nodes['stop-voice']={};nodes['auto-voice']={checked:true};
const $=id=>nodes[id],audioNotice=t=>notices.push(t),URL={createObjectURL:()=> 'blob:mock',revokeObjectURL:()=>{}};
const pause=async ms=>{calls.push('wait:'+ms);if(scenario==='manual'&&ms===50){calls.push('manual-ended');listeners.get('playing')?.();player.ended=true}};
const jobs=[{status:'running',result:{audio_id:'x',chunks:[{index:scenario==='disorder'?1:0}]}},
 {status:'done',result:{audio_id:'x',chunks:[{index:0},{index:1}]}}];
const api=async(path,body)=>{if(path==='audio/job'){playback.push(body);return{recorded:true}}if(path==='audio/cancel'){calls.push('cancel');return{}}calls.push('poll');return jobs.shift()||{status:'done',result:{audio_id:'x',chunks:[{index:0},{index:1}]}}};
const fetch=async url=>{calls.push(url);if(scenario==='cancel')valid=false;return{ok:true,blob:async()=>({})}};
CODE
(async()=>{let error=null;try{if(scenario.startsWith('sleep')){speechEntity='lilith';speechJobId='x';speechBusy=true;stopSpeech(scenario==='sleep-other'?'hoshino':'lilith')}else await playAudioJob('x','hoshino',()=>valid)}catch(e){error=e.message}
 console.log(JSON.stringify({calls,error,notices,playback,speechEntity,speechBusy,speechSerial}))})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('SCENARIO',json.dumps(scenario)).replace('CODE',code)
        node=Path('/home/gustavo/.nvm/versions/node/v24.19.0/bin/node')
        result=subprocess.run([str(node),'-e',harness],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr); return json.loads(result.stdout)

    def test_player_consumes_chunks_once_in_order_without_replaying_full_wav(self):
        result=self.run_player('normal'); self.assertIsNone(result['error'])
        self.assertEqual([c for c in result['calls'] if c.startswith('/api/')],
                         ['/api/audio/file?id=x&chunk=0','/api/audio/file?id=x&chunk=1'])

    def test_cancel_during_fetch_cannot_start_stale_audio(self):
        result=self.run_player('cancel'); self.assertNotIn('play',result['calls'])

    def test_disorder_is_rejected_before_playback(self):
        result=self.run_player('disorder'); self.assertIn('ordem',result['error'])
        self.assertNotIn('play',result['calls'])

    def test_autoplay_denial_waits_for_manual_play_before_next_sentence(self):
        result=self.run_player('manual'); self.assertIsNone(result['error'])
        self.assertLess(result['calls'].index('manual-ended'),result['calls'].index('/api/audio/file?id=x&chunk=1'))
        self.assertEqual(result['playback'][0]['playback_event'],'autoplay_denied')
        self.assertEqual([p['chunk'] for p in result['playback'] if p['playback_event']=='ended'],[0,1])

    def test_hoshino_sleep_does_not_stop_lilith_player(self):
        result=self.run_player('sleep-other')
        self.assertIsNone(result['error'])
        self.assertEqual(result['speechEntity'],'lilith')
        self.assertTrue(result['speechBusy']);self.assertEqual(result['speechSerial'],0)
        self.assertEqual(result['playback'],[])

    def test_sleep_stops_target_player_and_records_cancellation(self):
        result=self.run_player('sleep-own')
        self.assertIsNone(result['error'])
        self.assertIsNone(result['speechEntity']);self.assertFalse(result['speechBusy'])
        self.assertEqual(result['playback'][0]['playback_event'],'cancelled')


if __name__=='__main__': unittest.main()
