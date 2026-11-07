import json
import sys
from pathlib import Path
from unittest.mock import patch

import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "app"))

from tools import minecraft
from core import dispatch, cognition


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError('http')

    def json(self):
        return self.payload


class MinecraftIntegrationTests(unittest.TestCase):
    def test_uncertain_receipt_carries_bridge_error_first_line(self):
        import requests
        class Recusa:
            def raise_for_status(self):
                raise requests.HTTPError('400', response=self)
            def json(self):
                return {'ok': False, 'erro': 'Error: Server refused to place crafting_table at (-133, 82, -228): '
                        'the block is still air (você está a 1 blocos do ponto de nascimento)\n    at placeBlock (bridge.js:1172:3)'}
        from core import ui_policy
        with patch.object(minecraft, '_ponte_compativel', return_value=({'ok': True, 'protocol': 3, 'state': {'sessionId': 's'}}, '')), \
             patch.object(ui_policy, 'capability_allowed', return_value=True), \
             patch.object(minecraft.requests, 'post', return_value=Recusa()):
            saida = minecraft._rpc('place_block', {'name': 'crafting_table'})
        self.assertTrue(saida.startswith('RESULTADO_INCERTO'))  # continua incerto
        self.assertIn('A ponte respondeu: Server refused to place crafting_table', saida)
        self.assertIn('ponto de nascimento', saida)
        self.assertNotIn('bridge.js:1172', saida)

    def test_equipment_and_furnace_actions_expose_canonical_values(self):
        self.assertEqual(dispatch.validar_argumentos('minecraft_equipar',{'nome':'crafting_table','destino':'hand'}),'')
        self.assertTrue(dispatch.validar_argumentos('minecraft_equipar',{'nome':'crafting_table','destino':'mão'}))
        self.assertEqual(dispatch.validar_argumentos('minecraft_forno',{'acao':'estado'}),'')
        self.assertTrue(dispatch.validar_argumentos('minecraft_forno',{'acao':'status'}))

    def test_crafting_preflight_exact_receipt_is_error_for_replan_not_uncertain(self):
        health={'ok':True,'protocol':3,'state':{'sessionId':'s1'}}
        def post(_url,*,json,timeout):
            return FakeResponse({**{k:json[k] for k in ('request_id','parent_id','entity_id','session_id')},
                'ok':False,'phase':'preflight','effect_state':'not_started','code':'craft_preconditions',
                'erro':'Materiais ausentes','details':{'inventory':[],'recipes':[{'ingredients':[{'name':'oak_planks','count':4}]}]}})
        with patch.object(minecraft,'_ponte_compativel',return_value=(health,'')),patch.object(minecraft.requests,'post',side_effect=post):
            result=minecraft._rpc('craft',{'name':'crafting_table'})
        self.assertTrue(result.startswith('ERRO_PRECONDICAO_MINECRAFT:'))
        self.assertIn('oak_planks',result)
        contract=dispatch._resultado_mecanico('minecraft_craft',result)
        self.assertEqual(contract['status'],'error');self.assertTrue(contract['controlador_replanejar'])

    def test_missing_equipment_exact_preflight_allows_new_decision_only(self):
        health={'ok':True,'protocol':3,'state':{'sessionId':'s1'}}
        for phase,effect,prefix in [('preflight','not_started','ERRO_PRECONDICAO_MINECRAFT:'),
                                    ('verified','not_applied','RESULTADO_INCERTO:')]:
            def post(_url,*,json,timeout):
                return FakeResponse({**{k:json[k] for k in ('request_id','parent_id','entity_id','session_id')},
                    'ok':False,'phase':phase,'effect_state':effect,'code':'equip_preconditions',
                    'erro':'Item ausente','details':{'item':'crafting_table','inventory':[]}})
            with patch.object(minecraft,'_ponte_compativel',return_value=(health,'')),patch.object(minecraft.requests,'post',side_effect=post):
                result=minecraft.equipar('crafting_table')
            self.assertTrue(result.startswith(prefix),result)

    def test_action_refused_during_reflex_allows_new_decision(self):
        # 30/10: a ponte recusa qualquer ação mutável enquanto um reflexo (subir da água, fugir) está rodando.
        health={'ok':True,'protocol':3,'state':{'sessionId':'s1'}}
        def post(_url,*,json,timeout):
            return FakeResponse({**{k:json[k] for k in ('request_id','parent_id','entity_id','session_id')},
                'ok':False,'phase':'preflight','effect_state':'not_started','code':'reflex_busy',
                'erro':'um reflexo de sobrevivência está em andamento (afogamento)','details':{'action':'goto','reflexo':'afogamento'}})
        with patch.object(minecraft,'_ponte_compativel',return_value=(health,'')),patch.object(minecraft.requests,'post',side_effect=post):
            result=minecraft._rpc('goto',{'x':1,'y':64,'z':1})
        self.assertTrue(result.startswith('ERRO_PRECONDICAO_MINECRAFT:'),result);self.assertIn('afogamento',result)

    def test_place_block_without_coordinates_asks_bridge_for_nearby_ground(self):
        self.assertEqual(dispatch.validar_argumentos('minecraft_colocar_bloco',{}),'')
        with patch.object(minecraft,'_rpc',return_value='ok') as rpc:
            minecraft.colocar_bloco()
        rpc.assert_called_once_with('place_block',{})
        with patch.object(minecraft,'_rpc',return_value='ok') as rpc:
            minecraft.colocar_bloco(1,63,2,'up')
        rpc.assert_called_once_with('place_block',{'x':1.0,'y':63.0,'z':2.0,'face':'up'})

    def test_state_can_include_perception_of_surroundings_and_recipes(self):
        self.assertEqual(dispatch.validar_argumentos('minecraft_estado',{'itens':['wooden_pickaxe']}),'')
        with patch.object(minecraft,'_rpc',return_value='{}') as rpc:
            minecraft.estado(['wooden_pickaxe']);minecraft.estado()
        self.assertEqual(rpc.call_args_list[0].args,('state',{'perception':['wooden_pickaxe']}))
        self.assertEqual(rpc.call_args_list[1].args,('state',))
        text=json.dumps(next(s['function'] for s in dispatch.ESQUEMAS if s['function']['name']=='minecraft_coletar'),ensure_ascii=False)
        self.assertIn('sozinho',text)  # coletar acha e quebra; minerar exige coordenada exata

    def test_place_block_schema_explains_solid_reference_and_face(self):
        schema=next(s['function'] for s in dispatch.ESQUEMAS if s['function']['name']=='minecraft_colocar_bloco')
        text=json.dumps(schema,ensure_ascii=False)
        self.assertIn('sólido',text);self.assertIn('onde você está',text)

    def test_placement_verified_without_effect_is_error_for_new_decision(self):
        health={'ok':True,'protocol':3,'state':{'sessionId':'s1'}}
        for state,code,action,tool in (('not_applied','goto_no_path','goto','minecraft_ir_para'),
                                       ('not_applied','collect_no_path','collect','minecraft_coletar'),
                                       ('not_started','place_preconditions','place_block','minecraft_colocar_bloco'),
                                       ('not_started','use_preconditions','use_item','minecraft_usar_item'),
                                       ('not_started','furnace_preconditions','furnace_put','minecraft_forno'),
                                       ('not_started','harvest_preconditions','collect','minecraft_coletar'),
                                       ('not_started','harvest_preconditions','dig','minecraft_minerar')):
            def post(_url,*,json,timeout):
                return FakeResponse({**{k:json[k] for k in ('request_id','parent_id','entity_id','session_id')},
                    'ok':False,'phase':'verified' if state=='not_applied' else 'preflight','effect_state':state,'code':code,
                    'erro':'Server refused','details':{'held':'dark_oak_log'}})
            with patch.object(minecraft,'_ponte_compativel',return_value=(health,'')),patch.object(minecraft.requests,'post',side_effect=post):
                result=minecraft._rpc(action,{'x':1,'y':63,'z':1,'face':'up'})
            self.assertTrue(result.startswith('ERRO_PRECONDICAO_MINECRAFT:'),result);self.assertIn('dark_oak_log',result)
            contract=dispatch._resultado_mecanico(tool,result)
            self.assertEqual(contract['status'],'error');self.assertTrue(contract.get('precondition_failed'))
        def other(_url,*,json,timeout):  # código de outra ação não vale para colocação
            return FakeResponse({**{k:json[k] for k in ('request_id','parent_id','entity_id','session_id')},
                'ok':False,'phase':'preflight','effect_state':'not_started','code':'craft_preconditions','erro':'x'})
        with patch.object(minecraft,'_ponte_compativel',return_value=(health,'')),patch.object(minecraft.requests,'post',side_effect=other):
            self.assertTrue(minecraft._rpc('place_block',{}).startswith('RESULTADO_INCERTO:'))

    def test_post_send_place_timeout_is_uncertain_even_with_matching_snapshot_receipt(self):
        health={'ok':True,'protocol':3,'state':{'sessionId':'s1'}}
        def post(_url,*,json,timeout):
            return FakeResponse({**{k:json[k] for k in ('request_id','parent_id','entity_id','session_id')},
                'ok':False,'phase':'verified','effect_state':'not_applied','code':'place_not_applied',
                'erro':'timeout de ACK, alvo ainda está vazio'})
        with patch.object(minecraft,'_ponte_compativel',return_value=(health,'')),patch.object(minecraft.requests,'post',side_effect=post):
            result=minecraft._rpc('place_block',{'x':1,'y':63,'z':1})
        self.assertTrue(result.startswith('RESULTADO_INCERTO:'),result)
        self.assertEqual(dispatch._resultado_mecanico('minecraft_colocar_bloco',result)['status'],'uncertain')

    def test_preflight_without_exact_session_or_request_stays_uncertain(self):
        health={'ok':True,'protocol':3,'state':{'sessionId':'s1'}}
        for field in ('session_id','request_id'):
            def post(_url,*,json,timeout):
                data={**{k:json[k] for k in ('request_id','parent_id','entity_id','session_id')},
                    'ok':False,'phase':'preflight','effect_state':'not_started','code':'craft_preconditions','erro':'missing'}
                data.pop(field);return FakeResponse(data)
            with patch.object(minecraft,'_ponte_compativel',return_value=(health,'')),patch.object(minecraft.requests,'post',side_effect=post):
                self.assertTrue(minecraft._rpc('craft',{}).startswith('RESULTADO_INCERTO:'))

    def test_explicit_connection_starts_missing_owned_bridge_once(self):
        from tools import minecraft_launcher
        with patch.object(minecraft,'ponte_saude',side_effect=[json.dumps({'ok':False,'erro':'connection refused'}),json.dumps({'ok':True,'protocol':3})]), \
             patch.object(minecraft_launcher,'iniciar_ponte',return_value='ponte iniciada') as start, \
             patch.object(minecraft,'_rpc',side_effect=[json.dumps({'verified':True}),json.dumps({'connected':True,'verified':True})]):
            result=minecraft.conectar(host='127.0.0.1',port=40601,version='1.16.5')
        start.assert_called_once();self.assertIn('CONEXÃO MINECRAFT VERIFICADA',result)

    def test_versions_addresses_and_netmask_do_not_require_calculator(self):
        import main
        from core import intent
        text='Conecte ao Minecraft 1.16.5; alvo anterior 1.16.1/35229, host 127.0.0.1/24.'
        self.assertNotIn('calcular',main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(text))
        self.assertIn('calcular',main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa('Quanto é 12.5/2?'))
        self.assertFalse(intent.contem_expressao_matematica('versão 1.16.5/40601 em 26/10/2026, rede 127.0.0.1/24'))
        self.assertTrue(intent.contem_expressao_matematica('Quanto é 12.5/2?'))

    def test_known_port_prefers_explicit_connection(self):
        from core import intent
        self.assertEqual(intent.interpretar('Conecte ao Minecraft em 127.0.0.1 porta 40601').ferramenta_principal,'minecraft_conectar')
        self.assertEqual(intent.interpretar('Conecte ao Minecraft LAN').ferramenta_principal,'minecraft_conectar_lan')
    def test_minecraft_name_is_not_craft_verb_and_play_keeps_game_tools(self):
        names=dispatch._refinar_grupo('minecraft',dispatch.GRUPOS['minecraft'][0],'O Minecraft está aberto.')
        self.assertNotIn('minecraft_craft',names)
        play=dispatch._refinar_grupo('minecraft',dispatch.GRUPOS['minecraft'][0],'Jogue Minecraft em sobrevivência.')
        self.assertTrue({'minecraft_coletar','minecraft_conectar','minecraft_forno','minecraft_equipar'}<=play)

    def test_furnace_and_recipe_actions_have_tools_and_exact_rpc_receipts(self):
        with patch.object(minecraft,'_rpc',return_value='fixture') as rpc:
            minecraft.forno('processar','iron_ore','coal',3,1)
            self.assertEqual(rpc.call_args.args,('furnace_put',dict(input='iron_ore',fuel='coal',count=3,fuelCount=1)))
            minecraft.forno('estado');self.assertEqual(rpc.call_args.args[0],'furnace_state')
            minecraft.receitas('iron_pickaxe');self.assertEqual(rpc.call_args.args[0],'recipes')
        names={row['function']['name'] for row in dispatch.ESQUEMAS}
        self.assertTrue({'minecraft_forno','minecraft_receitas'}<=names)
    def test_manual_existe(self):
        texto = minecraft.manual()
        self.assertIn('minecraft_estado', texto)
        self.assertIn('Não use observar_tela', texto)

    def test_rpc_estado(self):
        with patch.object(minecraft.requests, 'get', return_value=FakeResponse({
            'ok': True, 'protocol': 3, 'state': {'connected': False}
        })), patch.object(minecraft.requests, 'post', return_value=FakeResponse({
            'ok': True, 'resultado': {'connected': False}
        })) as post:
            resultado = minecraft.estado()
            self.assertIn('connected', resultado)
            self.assertEqual(post.call_args.args[0], 'http://127.0.0.1:8765/rpc')
            self.assertEqual(post.call_args.kwargs['json']['action'], 'state')

    def test_rpc_conectar_verificado(self):
        respostas = [
            FakeResponse({'ok': True, 'resultado': {
                'verified': True, 'connection_state': 'ready', 'session_id': 'abc'
            }}),
            FakeResponse({'ok': True, 'resultado': {
                'connected': True, 'verified': True, 'connectionState': 'ready', 'spawned': True,
                'username': 'HoshinoMC', 'version': '1.16.5'
            }}),
        ]
        with patch.object(minecraft.requests, 'get', return_value=FakeResponse({
            'ok': True, 'protocol': 3, 'state': {'connected': False}
        })) as get, patch.object(minecraft.requests, 'post', side_effect=respostas) as post:
            texto = minecraft.conectar()
            self.assertIn('CONEXÃO MINECRAFT VERIFICADA', texto)
            self.assertGreaterEqual(len(post.call_args_list), 2)
            connect_call = post.call_args_list[0]
            args = connect_call.kwargs['json']['args']
            self.assertEqual(args['version'], '1.16.5')
            self.assertEqual(args['auth'], 'offline')
            self.assertEqual(post.call_args_list[1].kwargs['json']['action'], 'state')
            self.assertEqual(get.call_args.args[0], 'http://127.0.0.1:8765/health')

    def test_rpc_conectar_nao_verificado(self):
        respostas = [
            FakeResponse({'ok': True, 'resultado': 'Conectada'}),
            FakeResponse({'ok': True, 'resultado': {
                'connected': False, 'verified': False, 'connectionState': 'disconnected'
            }}),
        ]
        with patch.object(minecraft.requests, 'get', return_value=FakeResponse({
            'ok': True, 'protocol': 3, 'state': {'connected': False}
        })), patch.object(minecraft.requests, 'post', side_effect=respostas):
            texto = minecraft.conectar()
            self.assertIn('CONEXÃO MINECRAFT NÃO VERIFICADA', texto)
            self.assertNotIn('CONEXÃO MINECRAFT VERIFICADA', texto)

    def test_ponte_antiga_nao_e_aceita(self):
        with patch.object(minecraft.requests, 'get', return_value=FakeResponse({
            'ok': True, 'protocol': 2, 'state': {'connected': True}
        })) as get, patch.object(minecraft.requests, 'post') as post:
            texto = minecraft.conectar()
            self.assertIn('PONTE DESATUALIZADA', texto)
            post.assert_not_called()
            self.assertEqual(get.call_args.args[0], 'http://127.0.0.1:8765/health')

    def test_ponte_sem_protocolo_nao_e_aceita(self):
        with patch.object(minecraft.requests, 'get', return_value=FakeResponse({
            'ok': True, 'state': {'connected': True}
        })), patch.object(minecraft.requests, 'post') as post:
            texto = minecraft.conectar()
            self.assertIn('PONTE DESATUALIZADA', texto)
            self.assertIn('"received_protocol": null', texto)
            post.assert_not_called()

    def test_nenhuma_acao_usa_ponte_antiga(self):
        with patch.object(minecraft.requests, 'get', return_value=FakeResponse({
            'ok': True, 'state': {'connected': True}
        })), patch.object(minecraft.requests, 'post') as post:
            texto = minecraft.chat('oi')
            self.assertIn('PONTE MINECRAFT INCOMPATÍVEL', texto)
            post.assert_not_called()

    def test_schema_dispatch(self):
        nomes = {x['function']['name'] for x in dispatch.ESQUEMAS}
        esperados = {
            'minecraft_manual', 'minecraft_estado', 'minecraft_iniciar_ponte', 'minecraft_conectar', 'minecraft_conectar_lan',
            'minecraft_descobrir_lan', 'minecraft_ir_para', 'minecraft_minerar', 'minecraft_coletar',
            'minecraft_craft', 'minecraft_atacar', 'minecraft_colocar_bloco'
        }
        self.assertTrue(esperados <= nomes)

    def test_atacar_repassa_quantidade_da_caca(self):
        # 29/10: a opção pedia quantidade 5 e a ponte recebia count 1; o dispatch não repassava o campo.
        from unittest.mock import patch
        with patch.object(dispatch.minecraft, 'atacar', return_value='ok') as atacar:
            dispatch.HANDLERS['minecraft_atacar']({'alvo': 'salmon', 'entidade_id': 7, 'perseguir': True, 'quantidade': 5}, None)
        atacar.assert_called_once_with('salmon', 16.0, 7, True, 5)

    def test_grupo_sem_tela(self):
        grupo = dispatch.GRUPOS['minecraft'][0]
        self.assertIn('minecraft_estado', grupo)
        self.assertNotIn('observar_tela', grupo)

    def test_registro_cognitivo_lan(self):
        frame = cognition.criar_frame('conectar no Minecraft LAN e verificar', dispatch.ESQUEMAS)
        cognition.registrar_ferramenta(frame, 'minecraft_conectar_lan', '[CONEXÃO MINECRAFT VERIFICADA]')
        self.assertTrue(frame.verificacoes.get('minecraft'))
        self.assertTrue(cognition.precisa_verificacao_de_conclusao('Estou conectada ao Minecraft.', frame) is False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
