"""Permissões agrupadas: configurações/barramentos temporários, sem hardware."""
import asyncio
import copy
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch,Mock,AsyncMock

import config
import test_central_control as fixture
from test_audio_service import wav_bytes
from core import ui_policy as policy,interentity as bus,job_bus


class SimpleCapabilities(unittest.TestCase):
    def setUp(self):
        fixture.CentralControlTests.setUp(self)
        for name,value in [('RAIZ',self.root),('ENTIDADE_ID','hoshino'),('BUS_DIR',str(self.root/'channels'))]:
            p=patch.object(config,name,value);p.start();self.addCleanup(p.stop)

    def save(self,changes,entity='hoshino'):
        return self.control.save_tools(dict(entity=entity,capabilities=changes,revision=self.control.ui_settings()['revision']))

    def test_catalog_is_small_clear_entity_scoped_and_no_memory_switch(self):
        out=self.control.capabilities('hoshino');controls=out['controls']
        self.assertEqual(len(controls),10)
        self.assertEqual({x['key'] for x in controls},policy.KEYS)
        self.assertEqual(next(x['label'] for x in controls if x['key']=='read'),'Ler arquivos')
        self.assertEqual(next(x['label'] for x in controls if x['key']=='write'),'Escrever arquivos')
        self.assertTrue(all(x['enabled'] for x in controls))
        self.assertFalse(any('memória' in x['label'].lower() or 'voz' in x['label'].lower() for x in controls))
        self.assertEqual([x['key'] for x in self.control.capabilities('alistair')['controls']],['ambient'])

    def test_whole_discord_minecraft_and_image_include_aliases_but_not_other_entity(self):
        self.save({'discord':False,'minecraft':False,'image':False})
        for name in ('discord_enviar','discord_localizar_usuario','iniciar_discord','encerrar_discord',
                     'discord_abrir_canal','minecraft_conectar','iniciar_minecraft','encerrar_minecraft',
                     'minecraft_nova_funcao','gerar_imagem','estado_imagem','descarregar_imagem'):
            self.assertFalse(policy.allowed(self.root,'hoshino',name),name)
            self.assertTrue(policy.allowed(self.root,'lilith',name),name)

    def test_read_and_write_filter_workspace_operations_and_runtime_aliases_independently(self):
        self.save({'write':False})
        schema={'function':{'name':'workspace','parameters':{'properties':{'operacao':{'enum':['ler','abrir','listar','buscar','salvar','pasta']}}}}}
        before=copy.deepcopy(schema);filtered=policy.filter_schemas(self.root,'hoshino',[schema])
        self.assertEqual(filtered[0]['function']['parameters']['properties']['operacao']['enum'],['ler','abrir','listar','buscar'])
        self.assertEqual(schema,before)
        for op in ('salvar','write','editar','append','mkdir'):
            self.assertFalse(policy.allowed(self.root,'hoshino','workspace',{'operacao':op}))
        for op in ('ler','read','abrir','listar','buscar'):
            self.assertTrue(policy.allowed(self.root,'hoshino','workspace',{'operacao':op}))
        from core import dispatch
        handler=Mock(side_effect=AssertionError('Não pode escrever'))
        with patch.dict(dispatch.HANDLERS,workspace=handler):
            result=dispatch.executar('workspace',{'operacao':'salvar','caminho':'teste.txt','conteudo':'fixture'})
        self.assertIn('ACESSO_BLOQUEADO',result);handler.assert_not_called()
        self.save({'write':True,'read':False})
        self.assertTrue(policy.allowed(self.root,'hoshino','workspace',{'operacao':'salvar'}))
        self.assertFalse(policy.allowed(self.root,'hoshino','workspace',{'operacao':'ler'}))

    def test_memory_personality_voice_and_command_are_not_ambient_tools(self):
        self.save({key:False for key in policy.KEYS})
        for name in ('registrar_conhecimento','consultar_conhecimento','historico_chat','diario','oficina_logica',
                     'learn_preference','como_estou','quem_e','usuario_forma_de_tratamento','estado_voz','testar_voz','parar_voz'):
            self.assertTrue(policy.allowed(self.root,'hoshino',name),name)
        self.assertTrue(policy.allowed(self.root,'hoshino','definir_modo_microfone',{'modo':'pressionado'}))
        self.assertFalse(policy.allowed(self.root,'hoshino','definir_modo_microfone',{'modo':'aberto'}))

    def test_group_save_preserves_unedited_legacy_restrictions_and_other_settings(self):
        path=self.root/'compartilhado/config/interface.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        settings={'disabled_tools':{'hoshino':['discord_enviar','consultar_conhecimento','workspace'],'lilith':['gerar_imagem']},
                  'microphone':{'hotkey':'Ctrl+Alt+Space'},'orb_styles':{'hoshino':{'mode':'energy'}}}
        path.write_text(json.dumps(settings))
        self.save({'minecraft':False})
        self.assertFalse(policy.allowed(self.root,'hoshino','discord_enviar'))
        self.save({'discord':True,'read':True})
        after=json.loads(path.read_text())
        self.assertEqual(after['microphone'],settings['microphone']);self.assertEqual(after['orb_styles'],settings['orb_styles'])
        self.assertEqual(after['disabled_tools']['lilith'],['gerar_imagem'])
        self.assertIn('consultar_conhecimento',after['disabled_tools']['hoshino'])
        self.assertTrue(policy.allowed(self.root,'hoshino','discord_enviar'))
        self.assertTrue(policy.allowed(self.root,'hoshino','workspace',{'operacao':'ler'}))
        self.assertFalse(policy.allowed(self.root,'hoshino','workspace',{'operacao':'salvar'}))

    def test_invalid_group_values_and_stale_revision_never_write(self):
        revision=self.control.ui_settings()['revision'];self.save({'discord':False})
        path=self.root/'compartilhado/config/interface.json';before=path.read_bytes()
        for changes in ({'memory':False},{'discord':'false'},{},[],{'discord':None}):
            with self.assertRaises(ValueError):self.save(changes)
        with self.assertRaises(ValueError):
            self.control.save_tools(dict(entity='hoshino',capabilities={'discord':True},revision=revision))
        self.assertEqual(path.read_bytes(),before)

    def test_disabled_ambient_blocks_asr_before_file_or_worker_but_command_is_allowed(self):
        self.save({'ambient':False})
        with patch.object(self.audio,'_submit',return_value={'id':'fixture'}) as submit:
            with self.assertRaisesRegex(ValueError,'ambiente'):
                self.audio.submit_transcription('hoshino',wav_bytes(),mode='detection')
            submit.assert_not_called()
            self.audio.submit_transcription('hoshino',wav_bytes(),mode='command')
            self.assertEqual(submit.call_args.args[3]['capture_mode'],'command')
        self.assertFalse(self.control.microphone()['ambient_allowed']['hoshino'])
        self.assertTrue(self.control.microphone()['ambient_allowed']['lilith'])

    def test_global_capture_filters_targets_and_receipt_stays_idempotent(self):
        for entity in bus.ENTITIES:bus.register(entity,'awake')
        first=bus.send_global('Fala captada.',submission_id='ambient-fixture-001',eligible_targets=['hoshino','alistair'])
        self.assertEqual(first['deliveries'],['alistair','hoshino'])
        self.assertEqual(bus.peek('lilith'),[])
        again=bus.send_global('Fala captada.',submission_id='ambient-fixture-001',eligible_targets=['lilith'])
        self.assertEqual(again['id'],first['id']);self.assertEqual(bus.peek('lilith'),[])

    def test_saved_audio_mode_cannot_be_disguised_as_command_when_sending(self):
        self.save({'ambient':False})
        job=dict(id='fixture-audio',entity='hoshino',kind='audio_asr',status='done',
                 details={'capture_mode':'detection','result':{'text':'Frase de teste.'}})
        data=dict(audio_job_id=job['id'],draft_origin=True,text='Frase de teste.',capture_mode='command')
        with patch.object(job_bus,'get',return_value=job):
            self.assertEqual(self.audio.get(job['id'])['capture_mode'],'detection')
            with self.assertRaisesRegex(ValueError,'ambiente'):
                fixture.launcher.audio_origin(self.audio,'hoshino',data)
            job['details']['capture_mode']='command'
            self.assertEqual(fixture.launcher.audio_origin(self.audio,'hoshino',data)['capture_mode'],'command')

    def test_disabled_discord_keeps_pending_and_cannot_receive_queue_or_deliver_new_messages(self):
        from social import channels
        from integracoes import discord_bot
        pending=channels.publicar_entrada('discord','Fixture pendente.',source_id='source-1')
        self.save({'discord':False})
        self.assertEqual(channels.receber(consumir=True),[])
        with self.assertRaises(PermissionError):channels.publicar_entrada('discord','Nova entrada.')
        with self.assertRaises(PermissionError):channels.enviar('discord','123','Nova saída.')
        receiver=SimpleNamespace(send=AsyncMock())
        self.assertFalse(asyncio.run(discord_bot.entregar_mensagem(receiver,{'id':'fixture','texto':'Não enviar.'},Mock())))
        receiver.send.assert_not_called()
        with patch.dict('sys.modules',{'discord':None}):self.assertEqual(discord_bot.main(),0)
        self.save({'discord':True})
        self.assertEqual(channels.receber(consumir=False)[0]['id'],pending)

    def test_ambient_capture_is_stopped_and_minecraft_cannot_probe_or_start_when_disabled(self):
        from social import escuta
        from tools import minecraft,minecraft_launcher
        transcriber=SimpleNamespace(parar_escuta=Mock())
        self.save({'ambient':False,'minecraft':False})
        with patch.object(escuta,'_CANAIS',{'fixture':{'transcritor':transcriber}}),patch.object(escuta,'sugerir_dispositivo') as device:
            self.assertEqual(escuta.coletar(),[]);transcriber.parar_escuta.assert_called_once()
            self.assertIn('ACESSO_BLOQUEADO',escuta.ouvir('fixture','não iniciar'))
            device.assert_not_called()
        with patch.object(minecraft,'_ponte_compativel') as probe,patch.object(minecraft_launcher,'_saude_ponte') as health:
            self.assertIn('ACESSO_BLOQUEADO',minecraft._rpc('connect'))
            self.assertIn('ACESSO_BLOQUEADO',minecraft_launcher.iniciar_ponte())
            probe.assert_not_called();health.assert_not_called()


if __name__=='__main__':unittest.main()
