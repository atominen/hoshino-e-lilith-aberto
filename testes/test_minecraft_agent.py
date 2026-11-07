"""Decisões simuladas, critérios físicos e checkpoint no SQLite isolado."""
import asyncio
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import config
from core import minecraft_agent as agent,task_state
from memory.sqlite import init_db

def world(**values):
    return {'connected':True,'verified':True,'gameMode':'survival','host':'fixture','port':37837,
        'version':'1.16.5','sessionId':'s1','dimension':'overworld','_observation_receipt_id':'obs1',
        'inventory':[],**values}

class Goals(unittest.TestCase):
    def test_chat_burst_is_presented_in_order_without_replay_after_buffer_rotation(self):
        from core import minecraft_cognition as cognition
        cp={};rows=[{'id':f's1:{i}','seq':i,'sessionId':'s1','username':'Gustavo','message':str(i)} for i in range(9,41)]
        state=world(username='LilithMC',recentChat=rows)
        self.assertEqual(cognition.chat_gap(state,cp),8)
        all_ids=[]
        for _ in range(4):
            messages=cognition.pending_chat(state,cp);all_ids.extend(m['seq'] for m in messages)
            cognition.mark_chat_presented(state,cp,messages)
        self.assertEqual(all_ids,list(range(9,41)))
        state['recentChat']=rows[1:]+[dict(rows[-1],id='s1:41',seq=41,message='nova')]
        self.assertEqual([m['seq'] for m in cognition.pending_chat(state,cp)],[41])
        self.assertEqual(cognition.chat_gap(state,cp),0)

    def test_reply_steps_do_not_inflate_work_stagnation_or_replace_work_trajectory(self):
        from core import minecraft_cognition as cognition
        criteria,cp,state,perception=self.cognitive_fixture()
        cognition.update_monitor(cp,cognition.measure(criteria,cp,state,perception))
        cp['steps']=1;cp['minecraft_reply_steps']=1
        result=cognition.update_monitor(cp,cognition.measure(criteria,cp,state,perception))
        self.assertEqual(result['actions_without_progress'],0)
        cognition.record_transition(criteria,cp,state,state,'minecraft_chat',{'texto':'oi'},
            {'ok':True,'status':'success','receipt_id':'chat1'})
        self.assertEqual(cp.get('trajectory',[]),[])

    def test_game_chat_is_scoped_to_session_excludes_self_and_only_new_messages(self):
        from core import minecraft_cognition as cognition
        cp={'minecraft_chat_presented':['s1:1']}
        state=world(username='LilithMC',recentChat=[
            {'id':'s1:1','sessionId':'s1','username':'Gustavo','message':'já mostrada'},
            {'id':'s1:2','sessionId':'s1','username':'Gustavo','message':'oi'},
            {'id':'s1:3','sessionId':'s1','username':'LilithMC','message':'eco'},
            {'id':'old:1','sessionId':'old','username':'Gustavo','message':'outra sessão'}])
        self.assertEqual([m['id'] for m in cognition.pending_chat(state,cp)],['s1:2'])
        view=cognition.decision_view({'estado_observado':state,'chat_do_minecraft':cognition.pending_chat(state,cp)})
        self.assertNotIn('recentChat',view['estado_observado'])
        self.assertEqual(view['chat_do_minecraft'][0]['username'],'Gustavo')

    def test_compact_decision_keeps_facts_and_receipts_without_duplicate_goal_gaps(self):
        from core import minecraft_cognition as cognition
        source={'objetivo':'fixture','subobjetivo_atual':{'item':'furnace','total':1},
            'estado_observado':{'inventory':[{'name':'iron_ore','count':16}],'health':20},
            'percepcao':{'receitas':[{'item':'furnace','variantes':[]}]},
            'falta_para_concluir':{'fabricar':{'iron_helmet':1}},'progresso_observado':{'actions_without_progress':4},
            'ultimos_recibos':[{'receipt_id':'r1','output':'forno observado em 1,2,3'}],
            'trajetoria':[{'tool':'minecraft_coletar','receipt_id':'r1','inventory_delta':{'coal':1},
                'remaining_after':{'fabricar':{'iron_helmet':1}}}]}
        before=copy.deepcopy(source);compact=cognition.decision_view(source)
        self.assertEqual(compact['estado_observado'],source['estado_observado'])
        self.assertEqual(compact['percepcao'],source['percepcao'])
        self.assertEqual(compact['ultimos_recibos'],source['ultimos_recibos'])
        self.assertEqual(compact['falta_para_concluir'],source['falta_para_concluir'])
        self.assertNotIn('remaining_after',compact['trajetoria'][0])
        compact['estado_observado']['health']=0;self.assertEqual(source,before)

    def test_structured_choice_rejects_invented_option_extra_args_and_long_note(self):
        from core import minecraft_cognition as cognition
        options={'estado':{'tool':'minecraft_estado','arguments':{}},'outra':{}}
        for value in [{'opcao':'inventada','comentario':''},{'opcao':'estado','comentario':'','args':{}},
                      {'opcao':'estado','comentario':'x'*241},{'opcao':'estado','comentario':False}]:
            with self.assertRaises(agent.DecisionRejected):cognition.parse_choice(json.dumps(value),options)
        self.assertEqual(cognition.parse_choice('{"opcao":"outra","comentario":"Consultar receita."}',options),
                         ('outra','Consultar receita.'))

    def test_setup_options_preserve_explicit_new_lan_target_and_allow_other_tools(self):
        from core import minecraft_cognition as cognition
        target={'host':'127.0.0.1','port':34993,'version':'1.16.5','username':'LilithMC'}
        options=cognition.setup_options(target)
        self.assertEqual(options['conectar_destino']['tool'],'minecraft_conectar')
        self.assertEqual(options['conectar_destino']['arguments'],target)
        self.assertIn('outra',options)
        self.assertNotIn('conectar_destino',cognition.setup_options({}))
    def cognitive_fixture(self):
        criteria=agent.targets('Minecraft: fabrique uma picareta de madeira.')
        cp=agent.initial('fixture',criteria)
        state=world(inventory=[{'name':'oak_log','count':5},{'name':'oak_planks','count':2},{'name':'stick','count':4}])
        perception={'receitas':[
            {'item':'wooden_pickaxe','variantes':[{'ingredientes':[
                {'nome':'oak_planks','precisa':3,'tem':2},{'nome':'stick','precisa':2,'tem':4}]}]},
            {'item':'oak_planks','variantes':[{'ingredientes':[{'nome':'oak_log','precisa':1,'tem':5}]}]}]}
        return criteria,cp,state,perception

    def test_goal_monitor_does_not_call_extra_logs_or_movement_goal_progress(self):
        from core import minecraft_cognition as cognition
        criteria,cp,state,perception=self.cognitive_fixture()
        initial=cognition.measure(criteria,cp,state,perception)
        self.assertEqual(initial['final_missing'],2);self.assertEqual(initial['material_missing'],1)
        cognition.update_monitor(cp,initial)
        for step in range(1,4):
            cp['steps']=step;state['position']={'x':step,'y':64,'z':1}
            state['inventory'][0]['count']+=1
            result=cognition.update_monitor(cp,cognition.measure(criteria,cp,state,perception))
        self.assertEqual(result['actions_without_progress'],3)
        self.assertNotIn('no_progress',result)  # não substitui a proteção de ausência de efeito

    def test_observed_planks_reduce_material_deficit_without_finishing_pickaxe(self):
        from core import minecraft_cognition as cognition
        criteria,cp,state,perception=self.cognitive_fixture()
        cognition.update_monitor(cp,cognition.measure(criteria,cp,state,perception))
        cp['steps']=1;state['inventory'][1]['count']=6
        perception['receitas'][0]['variantes'][0]['ingredientes'][0]['tem']=6
        result=cognition.update_monitor(cp,cognition.measure(criteria,cp,state,perception))
        self.assertEqual(result['actions_without_progress'],0)
        self.assertEqual(result['material_missing'],0);self.assertEqual(result['final_missing'],2)
        self.assertFalse(agent.finished(criteria,cp,state))

    def test_missing_recipe_information_stays_unknown_in_goal_monitor(self):
        from core import minecraft_cognition as cognition
        criteria,cp,state,_=self.cognitive_fixture()
        result=cognition.measure(criteria,cp,state,{})
        self.assertIsNone(result['material_missing']);self.assertEqual(result['final_missing'],2)

    def test_goal_monitor_does_not_increment_twice_for_same_executed_step(self):
        from core import minecraft_cognition as cognition
        criteria,cp,state,perception=self.cognitive_fixture()
        measure=cognition.measure(criteria,cp,state,perception)
        cognition.update_monitor(cp,measure);cp['steps']=3
        self.assertEqual(cognition.update_monitor(cp,measure)['actions_without_progress'],3)
        self.assertEqual(cognition.update_monitor(cp,measure)['actions_without_progress'],3)

    def test_transition_records_actual_delta_and_goal_gaps_with_receipt(self):
        from core import minecraft_cognition as cognition
        criteria,cp,before,_=self.cognitive_fixture();after=copy.deepcopy(before)
        after['inventory'][0]['count']=6;after['position']={'x':2,'y':64,'z':1}
        cognition.record_transition(criteria,cp,before,after,'minecraft_coletar',{'nome':'oak_log'},
            {'status':'success','receipt_id':'tool-grounded'})
        row=cp['trajectory'][-1]
        self.assertEqual(row['inventory_delta'],{'oak_log':1});self.assertTrue(row['moved'])
        self.assertEqual(row['remaining_after'],{'fabricar':{'wooden_pickaxe':1},'ter_no_inventario':{'wooden_pickaxe':1}})
        self.assertEqual(row['receipt_id'],'tool-grounded')

    def test_subgoal_requires_observed_item_valid_total_and_entity_authorship(self):
        from core import minecraft_cognition as cognition
        _,cp,state,perception=self.cognitive_fixture()
        for data in ({'item':'invented_magic','total':1,'note':'x'},
                     {'item':'oak_planks','total':True,'note':'x'},
                     {'item':'oak_planks','total':2,'note':'already met'}):
            with self.assertRaises(ValueError):cognition.accept_subgoal(cp,data,state,perception,'lilith')
        result=cognition.accept_subgoal(cp,{'item':'oak_planks','total':3,'note':'Preparar ingrediente que falta.'},state,perception,'lilith')
        self.assertEqual(result['author'],'lilith');self.assertEqual(result['total'],3)
        self.assertEqual(cognition.subgoal_status(cp,state)['missing'],1)
        state['inventory'][1]['count']=3
        self.assertEqual(cognition.subgoal_status(cp,state)['missing'],0)
        self.assertFalse(cp['crafted'])  # meta intermediária não fabrica nem comprova fabricação

    def test_required_workbench_is_an_available_subgoal_even_when_none_is_nearby(self):
        from core import minecraft_cognition as cognition
        _,cp,state,perception=self.cognitive_fixture()
        perception['receitas'][0]['variantes'][0]['exige_bancada']=True
        selected=cognition.accept_subgoal(cp,{'item':'crafting_table','total':1,'note':'Preparar estação exigida.'},state,perception,'lilith')
        self.assertEqual(selected['item'],'crafting_table')

    def test_observed_ore_can_be_an_authorial_subgoal(self):
        # 27/10: ferro a 9,7 blocos, mas a meta só aceitava inventário/receitas e ela escolheu iron_block.
        from core import minecraft_cognition as cognition
        _,cp,state,perception=self.cognitive_fixture()
        perception['arredores']={'iron_ore':{'mais_proximo':{'x':1,'y':55,'z':1},'distancia':9.7},
                                 'grass_block':{'mais_proximo':{'x':0,'y':63,'z':0},'distancia':1}}
        self.assertIn('iron_ore',cognition.subgoal_candidates(perception,state))
        self.assertNotIn('grass_block',cognition.subgoal_candidates(perception,state))
        selected=cognition.accept_subgoal(cp,{'item':'iron_ore','total':3,'note':'Minério visto abaixo.'},state,perception,'lilith')
        self.assertEqual(selected['item'],'iron_ore')

    def test_smelting_is_offered_only_with_furnace_ore_and_fuel_never_as_crafting(self):
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state['inventory']=[{'name':'iron_ore','count':5},{'name':'coal','count':2}]
        smelt={'processo':'fornalha','exige_forno':True,'forno_a_4_blocos':False,'tem_combustivel':True,
               'ingredientes':[{'nome':'iron_ore','precisa':1,'tem':5}],'faltam_unidades':0}
        perception={'receitas':[{'item':'iron_ingot','variantes':[smelt]}]}
        options=cognition.action_options(perception,state)
        self.assertNotIn('fabricar:iron_ingot',options);self.assertNotIn('fundir:iron_ore',options)
        smelt['forno_a_4_blocos']=True
        options=cognition.action_options(perception,state)
        self.assertNotIn('fabricar:iron_ingot',options)
        self.assertEqual(options['fundir:iron_ore']['tool'],'minecraft_forno')
        self.assertEqual(options['fundir:iron_ore']['arguments'],{'acao':'processar','entrada':'iron_ore',
            'combustivel':'coal','quantidade':5,'quantidade_combustivel':1})
        state['inventory']=[{'name':'iron_ore','count':5}]
        self.assertNotIn('fundir:iron_ore',cognition.action_options(perception,state))  # sem combustível

    def test_own_furnace_run_offers_retrieval_and_no_second_load(self):
        # 27/10 17:37: 8 iron_ore no forno, nenhuma opção de retirar; o plano dela era recarregar o forno ocupado.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state['position']={'x':-97,'y':69,'z':-62}
        state['inventory']=[{'name':'iron_ore','count':8},{'name':'coal','count':19}]
        smelt={'processo':'fornalha','exige_forno':True,'forno_a_4_blocos':True,'tem_combustivel':True,
               'ingredientes':[{'nome':'iron_ore','precisa':1,'tem':8}],'faltam_unidades':0}
        perception={'receitas':[{'item':'iron_ingot','variantes':[smelt]}],
                    'arredores':{'furnace':{'mais_proximo':{'x':-97,'y':69,'z':-61}}}}
        run={'position':{'x':-97,'y':69,'z':-61},'input':'iron_ore','expectedOutput':'iron_ingot','remaining':8,
             'count':8,'fuel':'coal','fuelCount':1,'depositedAt':'2000-01-01T00:00:00.000Z'}
        state['furnaceRuns']=[run]
        options=cognition.action_options(perception,state,{'item':'iron_ingot','total':8})
        self.assertEqual(options['retirar:iron_ingot']['tool'],'minecraft_forno')
        self.assertEqual(options['retirar:iron_ingot']['arguments'],{'acao':'retirar'})
        self.assertIn('estimados prontos: 8',options['retirar:iron_ingot']['effect'])
        self.assertIn('slot vazio não é falta de combustível',options['retirar:iron_ingot']['effect'])
        self.assertIn('1 coal',options['retirar:iron_ingot']['effect'])
        self.assertNotIn('processamento',options['retirar:iron_ingot']['effect'])  # fase antiga não é fato atual
        state['furnaceRuns']=[{**run,'count':16,'remaining':16}]  # 1 carvão funde só 8
        self.assertIn('estimados prontos: 8',cognition.action_options(perception,state)['retirar:iron_ingot']['effect'])
        state['furnaceRuns']=[run]
        self.assertIn('atende sua meta atual',options['retirar:iron_ingot']['effect'])
        self.assertNotIn('fundir:iron_ore',options)  # o forno com carga própria recusaria outra
        state['position']={'x':-80,'y':69,'z':-62}  # longe: aproximar informa, não retira
        options=cognition.action_options(perception,state)
        self.assertNotIn('retirar:iron_ingot',options);self.assertIn('fundir:iron_ore',options)
        self.assertIn('no forno em (-97,69,-61), você depositou 8 iron_ore',options['aproximar:furnace']['effect'])
        run['depositedAt']='sem hora'
        self.assertNotIn('estimados prontos',cognition.action_options(perception,{**state,'position':{'x':-97,'y':69,'z':-62}})['retirar:iron_ingot']['effect'])
        state['furnaceRuns']=[{**run,'remaining':0}]
        self.assertNotIn('retirar:iron_ingot',cognition.action_options(perception,{**state,'position':{'x':-97,'y':69,'z':-62}}))

    def test_her_plan_steps_are_checked_against_facts_not_rewritten(self):
        # 27/10 18:20: o plano textual "repor combustível" seguia sem aviso, sem passos conferíveis.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        content=json.dumps({'opcao':'estado','comentario':'ok','plano':[
            {'passo':'Retirar os lingotes do forno','feito_quando':{'tipo':'ter','item':'iron_ingot','quantidade':8}},
            {'passo':'Ficar perto do forno','feito_quando':{'tipo':'perto','item':'furnace','quantidade':1}},
            {'passo':'Segurar a picareta','feito_quando':{'tipo':'equipado','item':'wooden_pickaxe','quantidade':1}}]})
        self.assertEqual(cognition.parse_choice(content,{'estado':{}}),('estado','ok'))
        steps=cognition.parse_plan(content);self.assertEqual(len(steps),3)
        self.assertIsNone(cognition.parse_plan(json.dumps({'opcao':'estado','comentario':'ok'})))  # mantém o atual
        for bad in ([],[{'passo':'x','feito_quando':{'tipo':'perto','item':'iron_ore','quantidade':1}}],
                    [{'passo':'','feito_quando':{'tipo':'ter','item':'coal','quantidade':1}}],
                    [{'passo':'x','feito_quando':{'tipo':'ter','item':'Coal!','quantidade':1}}],
                    [{'passo':'x','feito_quando':{'tipo':'ter','item':'coal','quantidade':0}}],
                    [{'passo':'x','feito_quando':{'tipo':'ter','item':'coal_ore','quantidade':1}}]):  # 27/10 18:33
            with self.subTest(bad=bad),self.assertRaises(ValueError):cognition.parse_plan(json.dumps({'plano':bad}))
        with self.assertRaisesRegex(ValueError,'use ter coal'):
            cognition.parse_plan(json.dumps({'plano':[{'passo':'x','feito_quando':{'tipo':'ter','item':'coal_ore','quantidade':1}}]}))
        cp={'plan_steps':steps,'plan_steps_step':10,'steps':10}
        state.update(inventory=[{'name':'iron_ingot','count':3}],heldItem={'name':'wooden_pickaxe','count':1})
        perception={'arredores':{'furnace':{'mais_proximo':{'x':0,'y':0,'z':0},'distancia':2.2}}}
        view=cognition.plan_view(cp,state,perception)
        self.assertEqual([x['cumprido'] for x in view['passos']],[False,True,True])
        self.assertEqual(view['proximo_pendente'],'Retirar os lingotes do forno')
        self.assertIsNone(cognition.plan_view(cp,state,{})['passos'][1]['cumprido'])  # forno não observado
        cp['steps']=15;view=cognition.plan_view(cp,state,perception)
        self.assertIn('Nenhum passo novo cumprido em 5',view['aviso'])
        state['inventory']=[{'name':'iron_ingot','count':8}];cp['steps']=16
        view=cognition.plan_view(cp,state,perception)
        self.assertIn('Todos os passos',view['aviso']);self.assertEqual(view['acoes_sem_novo_passo_cumprido'],0)
        self.assertIn('plano',cognition.choice_schema({'estado':{}})['properties'])
        self.assertNotIn('plano',cognition.choice_schema({'estado':{}})['required'])

    def test_receipt_window_keeps_work_not_reconnections_or_rejections(self):
        # 27/10 18:20: reconexões de manutenção e recusas tiraram da janela o depósito no forno.
        from core import minecraft_cognition as cognition
        events=[{'tool':'web_search','status':'success','receipt_id':'w'},
                {'tool':'minecraft_forno','status':'success','receipt_id':'f'},
                {'tool':'minecraft_coletar','status':'success','receipt_id':'c'},
                {'tool':'minecraft_conectar','status':'success','receipt_id':'k1'},
                {'tool':None,'status':'rejected_before_effect','output':'Decisão recusada: raciocínio esgotado.'},
                {'tool':'minecraft_conectar','status':'success','receipt_id':'k2'},
                {'tool':None,'status':'rejected_before_effect','output':'Decisão recusada: outra.'}]
        work,rejection=cognition.work_receipts(events,True)
        self.assertEqual([e['receipt_id'] for e in work],['w','f','c']);self.assertEqual(rejection,'Decisão recusada: outra.')
        self.assertEqual(cognition.work_receipts(events,False)[0],events[-4:])  # desconectada: conexão importa
        self.assertIsNone(cognition.work_receipts(events[:3],True)[1])
        cp={'steps':5,'target':{},'trajectory':[]}
        cognition.record_transition({},cp,{},{},'minecraft_conectar',{},{'status':'success'})
        self.assertEqual(cp['trajectory'],[])

    def test_research_and_confirmed_learning_are_her_written_options(self):
        # 27/10: pedido humano — pesquisar na internet e consolidar habilidades confirmadas.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        options=cognition.action_options({},state)
        self.assertEqual(options['pesquisar']['tool'],'web_search');self.assertNotIn('registrar_aprendizado',options)
        self.assertEqual(cognition.option_arguments(options['pesquisar'],json.dumps({'consulta':' forno 1.16 carvão '})),
                         {'query':'forno 1.16 carvão'})
        for content in (json.dumps({'opcao':'pesquisar'}),json.dumps({'consulta':''}),'texto'):
            with self.subTest(content=content),self.assertRaises(ValueError):
                cognition.option_arguments(options['pesquisar'],content)
        cp={'steps':112,'trajectory':[
            {'step':110,'tool':'minecraft_coletar','status':'success','receipt_id':'c','inventory_delta':{'coal':1}},
            {'step':111,'tool':'minecraft_forno','status':'success','receipt_id':'tool-f','inventory_delta':{'iron_ingot':8}}]}
        achieved=cognition.recent_achievement(cp);self.assertEqual(achieved,['tool-f'])  # coleta não é produção
        options=cognition.action_options({},state,None,achieved)
        self.assertIn('tool-f',options['registrar_aprendizado']['effect'])
        learned={'nome':'Fundir ferro','passos':['Colocar 8 iron_ore e 1 coal no forno','Retirar após ~80 s'],
                 'resultado_esperado':'8 iron_ingot'}
        args=cognition.option_arguments(options['registrar_aprendizado'],json.dumps({'aprendizado':learned}),achieved)
        self.assertEqual(args['passos'],learned['passos']);self.assertIn('tool-f',args['notas'])
        self.assertEqual(args['tags'],['minecraft'])
        with self.assertRaises(ValueError):
            cognition.option_arguments(options['registrar_aprendizado'],json.dumps({'aprendizado':{**learned,'passos':[]}}))
        cp['trajectory'].append({'step':112,'tool':'registrar_procedimento','status':'success','receipt_id':'k'});cp['steps']=113
        self.assertEqual(cognition.recent_achievement(cp),[])  # já registrado depois da conquista
        schema=cognition.choice_schema({'pesquisar':{}})['properties']
        self.assertIn('consulta',schema);self.assertIn('aprendizado',schema)
        self.assertEqual(cognition.parse_choice(json.dumps({'opcao':'pesquisar','comentario':'','consulta':'x'}),{'pesquisar':{}})[0],'pesquisar')
        perception={'arredores':{'coal_ore':{'ferramenta_ok':False,'ferramentas':['wooden_pickaxe']},'oak_log':{'ferramenta_ok':True}}}
        self.assertEqual(cognition.blocked_collection(perception),{'coal_ore':['wooden_pickaxe']})

    def test_subgoal_names_what_enters_the_inventory_and_kit_pieces_are_marked(self):
        # 27/10 20:23: meta coal_ore 4 nunca avançava; capacete/peitoral fabricáveis sem ligação ao objetivo.
        from core import minecraft_cognition as cognition
        _,cp,state,_=self.cognitive_fixture()
        perception={'arredores':{'coal_ore':{'mais_proximo':{'x':1,'y':59,'z':1}},'iron_ore':{'mais_proximo':{'x':1,'y':55,'z':1}}}}
        names=cognition.subgoal_candidates(perception,state)
        self.assertIn('coal',names);self.assertNotIn('coal_ore',names);self.assertIn('iron_ore',names)
        with self.assertRaisesRegex(ValueError,'use coal'):
            cognition.accept_subgoal(cp,{'item':'coal_ore','total':4,'note':'x'},state,perception,'lilith')
        state['inventory']=[{'name':'iron_ingot','count':8}]
        helmet={'item':'iron_helmet','bancada_a_4_blocos':True,'variantes':[{'exige_bancada':True,
                'ingredientes':[{'nome':'iron_ingot','precisa':5,'tem':8}]}]}
        options=cognition.action_options({'receitas':[helmet]},state,None,(),['iron_helmet','iron_boots'])
        self.assertIn('peças que faltam',options['fabricar:iron_helmet']['effect'])
        self.assertNotIn('peças',cognition.action_options({'receitas':[helmet]},state)['fabricar:iron_helmet']['effect'])

    def test_chat_is_her_channel_to_the_human_and_facts_reach_the_decision(self):
        # 27/10: conversa pelo chat do jogo; forno vazio, perigo e comentário divergente como fatos.
        from core import minecraft_cognition as cognition, capabilities
        _,_,state,_=self.cognitive_fixture()
        perception={'arredores':{'furnace':{'mais_proximo':{'x':1,'y':64,'z':1},'distancia':9}}}
        options=cognition.action_options(perception,state)
        chat=options['falar_no_chat'];self.assertEqual(chat['tool'],'minecraft_chat')
        self.assertEqual(cognition.option_arguments(chat,json.dumps({'consulta':'Humano, onde tem ferro?'})),{'texto':'Humano, onde tem ferro?'})
        with self.assertRaisesRegex(ValueError,'falar_no_chat exige'):cognition.option_arguments(chat,json.dumps({'consulta':'x'*241}))
        self.assertIn('nada seu para retirar',options['aproximar:furnace']['effect'])
        state.update(health=8,food=5,nearbyEntities=[{'name':'zombie','distance':6.2,'lineOfSight':True},
                                                     {'name':'cow','distance':3,'lineOfSight':True},{'name':'creeper','distance':5,'lineOfSight':False}])
        alerts=cognition.danger(state)['alertas']
        self.assertEqual(len(alerts),3);self.assertIn('zombie a 6.2',alerts[2])
        self.assertEqual(cognition.danger({'health':20,'food':20}),{})
        known={'coal_ore','dark_oak_log','crafting_table'}
        self.assertIn('coal_ore',cognition.choice_divergence('Minerar coal_ore para o forno.','coletar:dark_oak_log',known))
        self.assertIsNone(cognition.choice_divergence('Coletar dark_oak_log.','coletar:dark_oak_log',known))
        self.assertIsNone(cognition.choice_divergence('Ok.','estado',known))
        self.assertFalse(capabilities.operation_mutates('minecraft_forno',{'acao':'estado'}))
        self.assertTrue(capabilities.operation_mutates('minecraft_forno',{'acao':'retirar'}))
        self.assertIn('explicacao',cognition.choice_schema({'estado':{}})['properties'])

    def test_defense_and_death_recovery_are_her_options_with_the_despawn_clock(self):
        # 28/10: morreu à noite várias vezes; o humano pediu ensinar fuga/ataque e os 5 min dos itens caídos.
        from datetime import datetime, timedelta, timezone
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state['position']={'x':0,'y':64,'z':0}
        state['nearbyEntities']=[{'id':42,'name':'zombie','distance':3.0,'lineOfSight':True,'position':{'x':3,'y':64,'z':0}},
                                 {'name':'cow','distance':1,'position':{'x':1,'y':64,'z':0}}]
        options=cognition.action_options({},state)
        self.assertEqual(options['fugir:zombie']['arguments'],{'x':-12,'y':64,'z':0,'distancia':2})
        self.assertEqual(options['atacar:zombie']['arguments'],{'alvo':'zombie','entidade_id':42,'max_distance':5})
        state['nearbyEntities'][0].update(distance=9.0,position={'x':9,'y':64,'z':0})
        options=cognition.action_options({},state)
        self.assertIn('fugir:zombie',options);self.assertNotIn('atacar:zombie',options)  # longe demais para golpear
        now=datetime(2026,10,28,2,0,tzinfo=timezone.utc)
        death={'position':{'x':5,'y':70,'z':5},'items':[{'name':'oak_log','count':3}],
               'at':(now-timedelta(seconds=60)).isoformat(),'itemsDespawnAt':(now+timedelta(seconds=240)).isoformat()}
        view=cognition.death_view({'lastDeath':death},now)
        self.assertEqual(view['itens_que_caíram'],['3 oak_log']);self.assertIn('240 s',view['situacao'])
        self.assertIn('já sumiram',cognition.death_view({'lastDeath':death},now+timedelta(seconds=300))['situacao'])
        state.update(nearbyEntities=[],lastDeath={**death,'at':datetime.now(timezone.utc).isoformat(),
            'itemsDespawnAt':(datetime.now(timezone.utc)+timedelta(seconds=290)).isoformat()})
        recover=cognition.action_options({},state)['recuperar_itens']
        self.assertEqual(recover['arguments'],{'x':5,'y':70,'z':5,'distancia':1})
        self.assertNotIn('sem picareta',recover['effect'])  # local no mesmo nível
        state['position']={'x':0,'y':94,'z':0}
        self.assertIn('24 blocos abaixo e você está sem picareta',cognition.action_options({},state)['recuperar_itens']['effect'])
        self.assertIn('5 minutos',cognition.CHOICE_PROMPT)

    def test_placed_station_counts_as_owned_and_station_goals_stay_at_one(self):
        # 28/10: com a bancada colocada, meta crafting_table 12 e fabricou outra bancada.
        from core import minecraft_cognition as cognition
        _,cp,state,_=self.cognitive_fixture()
        state['inventory']=[{'name':'oak_planks','count':8}]
        table={'item':'crafting_table','bancada_a_4_blocos':True,'variantes':[{'exige_bancada':False,
               'ingredientes':[{'nome':'oak_planks','precisa':4,'tem':8}]}]}
        near={'receitas':[table],'arredores':{'crafting_table':{'mais_proximo':{'x':1,'y':64,'z':0},'distancia':2.0}}}
        self.assertNotIn('fabricar:crafting_table',cognition.action_options(near,state))
        self.assertIn('fabricar:crafting_table',cognition.action_options({'receitas':[table]},state))  # nenhuma por perto
        with self.assertRaisesRegex(ValueError,'basta'):
            cognition.accept_subgoal(cp,{'item':'crafting_table','total':12,'note':'x'},state,near,'lilith')

    def test_pending_plan_item_is_linked_to_the_table_it_needs(self):
        # 28/10: plano pedia stone_pickaxe, bancada a mais de 4 blocos, nada ligava a aproximação ao plano.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state['inventory']=[{'name':'cobblestone','count':11},{'name':'stick','count':2}]
        pick={'item':'stone_pickaxe','bancada_a_4_blocos':False,'variantes':[{'exige_bancada':True,
              'ingredientes':[{'nome':'cobblestone','precisa':3,'tem':11},{'nome':'stick','precisa':2,'tem':2}]}]}
        perception={'receitas':[pick],'arredores':{'crafting_table':{'mais_proximo':{'x':1,'y':64,'z':0},'distancia':6}}}
        options=cognition.action_options(perception,state,{'item':'wooden_pickaxe'},(),(),'stone_pickaxe')
        self.assertIn('o próximo passo do seu plano stone_pickaxe exige bancada',options['aproximar:crafting_table']['effect'])
        pick['bancada_a_4_blocos']=True
        options=cognition.action_options(perception,state,None,(),(),'stone_pickaxe')
        self.assertIn('atende o próximo passo do seu plano',options['fabricar:stone_pickaxe']['effect'])

    def test_plan_item_to_obtain_skips_equip_steps_of_items_already_owned(self):
        # 28/10: passo 'equipado wooden_pickaxe' (já possuída) prendia a percepção; o seguinte pedia stone_pickaxe.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state.update(inventory=[{'name':'wooden_pickaxe','count':1}],heldItem={'name':'stick','count':1})
        cp={'plan_steps':[{'passo':'a','feito_quando':{'tipo':'equipado','item':'wooden_pickaxe','quantidade':1}},
                          {'passo':'b','feito_quando':{'tipo':'equipado','item':'stone_pickaxe','quantidade':1}},
                          {'passo':'c','feito_quando':{'tipo':'ter','item':'coal','quantidade':4}}]}
        self.assertEqual(cognition.plan_item_to_obtain(cp,state),'stone_pickaxe')
        state['inventory'].append({'name':'stone_pickaxe','count':1})
        self.assertEqual(cognition.plan_item_to_obtain(cp,state),'coal')

    def test_cooked_meat_group_bow_and_arrows_objectives(self):
        # Pedido humano 28/10: 30 carnes assadas (iguais ou diferentes), depois arco, depois 30 flechas.
        base=('Minecraft: conecte LilithMC ao servidor já aberto em host 10.0.0.200, porta 25565, versão 1.16.5 e auth '
              'offline, se estiver desconectada. ')
        meat=agent.targets(base+'Consiga 30 carnes assadas de animais, iguais ou diferentes.')
        self.assertEqual(meat['groups'],{'cooked_meat':30})
        cp=agent.initial('g',meat);cp['session_id']='s'
        state={'connected':True,'verified':True,'gameMode':'survival','sessionId':'s','equipment':{},
               'inventory':[{'name':'cooked_beef','count':20},{'name':'cooked_chicken','count':6}]}
        gap=agent.remaining(meat,cp,state)['ter_no_inventario_qualquer']
        self.assertEqual(list(gap.values()),[4]);self.assertTrue(next(iter(gap)).startswith('cooked_meat (cooked_beef'))
        state['inventory'].append({'name':'cooked_porkchop','count':4})
        self.assertEqual(agent.remaining(meat,cp,state),{})
        self.assertEqual(agent.targets(base+'Fabrique um arco.'),
                         {'inventory':{'bow':1},'equipped':{},'placed':{},'crafted':{'bow':1}})
        self.assertEqual(agent.targets(base+'Fabrique 30 flechas.')['crafted'],{'arrow':30})

    def test_own_furnace_out_of_sight_offers_going_back(self):
        # 28/10: forno dela a 34 blocos com 8 salmões; sem visão do bloco, ia construir outro.
        from core import minecraft_cognition as cognition
        state={'position':{'x':-211,'y':63,'z':-222},'inventory':[],'furnaceRuns':[{'position':{'x':-238,'y':63,'z':-242},
               'input':'salmon','expectedOutput':'cooked_salmon','count':8,'remaining':8,'fuel':'coal','fuelCount':1,
               'depositedAt':'2000-01-01T00:00:00.000Z'}]}
        back=cognition.action_options({},state)['ir_ao_forno']
        self.assertEqual(back['arguments'],{'x':-238,'y':63,'z':-242,'distancia':3});self.assertIn('estimados prontos: 8',back['effect'])
        # 29/10: outro forno (vazio) mais perto; aproximar levava a ele e ela ficava a 5 blocos do dela, em laço.
        near={'arredores':{'furnace':{'mais_proximo':{'x':-235,'y':62,'z':-240}}}}
        state={**state,'position':{'x':-232,'y':62,'z':-240},'furnaceRuns':[{**state['furnaceRuns'][0],'position':{'x':-237,'y':63,'z':-241}}]}
        options=cognition.action_options(near,state)
        self.assertEqual(options['ir_ao_forno']['arguments'],{'x':-237,'y':63,'z':-241,'distancia':3})
        self.assertIn('é outro forno; a sua carga está no forno em (-237,63,-241)',options['aproximar:furnace']['effect'])

    def test_hunger_offers_eating_what_she_has(self):
        # 28/10: fome 3/20, vida 7, numa caverna, sem opção de comer.
        from core import minecraft_cognition as cognition
        state={'food':3,'health':7,'inventory':[{'name':'cooked_beef','count':2},{'name':'cobblestone','count':9}]}
        options=cognition.action_options({},state)
        self.assertEqual(options['comer:cooked_beef']['arguments'],{'nome':'cooked_beef'})
        self.assertNotIn('comer:cobblestone',options)
        self.assertNotIn('comer:cooked_beef',cognition.action_options({},{**state,'food':20}))

    def test_kill_a_mob_objective_hunt_options_and_receipt(self):
        # Pedido humano 27/10: depois do kit, matar um mob qualquer; jogador nunca é alvo.
        from core import minecraft_cognition as cognition
        goal=('Minecraft: conecte LilithMC ao servidor já aberto em host 10.0.0.200, porta 25565, versão 1.16.5 e auth '
              'offline, se estiver desconectada. Mate um mob qualquer em sobrevivência, sem atacar jogadores.')
        criteria=agent.targets(goal)
        self.assertEqual(criteria['killed'],{'mob':1})
        cp=agent.initial(goal,criteria);cp['session_id']='s'
        state={'connected':True,'verified':True,'gameMode':'survival','sessionId':'s','inventory':[],'equipment':{},
               'nearbyEntities':[{'id':7,'name':'cow','type':'mob','distance':5.0,'position':{'x':1,'y':64,'z':1}},
                                 {'id':8,'name':'player','type':'player','username':'ATO','distance':2.0,'position':{'x':0,'y':64,'z':1}},
                                 {'id':9,'name':'villager','type':'mob','distance':3.0,'position':{'x':2,'y':64,'z':1}}]}
        self.assertEqual(agent.remaining(criteria,cp,state),{'matar':{'mob':1}})
        options=cognition.action_options({},state,hunt=True)
        self.assertEqual([k for k in options if k.startswith('cacar:')],['cacar:cow'])
        self.assertEqual(options['cacar:cow']['arguments'],{'alvo':'cow','entidade_id':7,'perseguir':True,'max_distance':11,'quantidade':1})
        self.assertEqual(options['seguir:ATO']['arguments'],{'nome':'ATO','distancia':2})
        self.assertIn('solta beef e leather',options['cacar:cow']['effect'])
        self.assertNotIn('cacar:cow',cognition.action_options({},state))
        meat_only=cognition.action_options({},{**state,'nearbyEntities':[*state['nearbyEntities'],
            {'id':11,'name':'bat','type':'mob','distance':2.0,'position':{'x':0,'y':64,'z':0}}]},hunt={'beef','porkchop'})
        self.assertEqual([k for k in meat_only if k.startswith('cacar:')],['cacar:cow'])
        # Subsolo sem animais (28/10: caçava morcegos): opção de voltar ao último ponto sob o céu.
        cave={**state,'skyLight':0,'nearbyEntities':[{'id':5,'name':'bat','type':'mob','distance':3.0,'position':{'x':1,'y':30,'z':1}}]}
        up=cognition.action_options({},cave,hunt=True,surface={'x':-152,'y':76,'z':-197})['subir_a_superficie']
        self.assertEqual(up['arguments'],{'x':-152,'y':76,'z':-197,'distancia':2});self.assertIn('só: bat',up['effect'])
        self.assertNotIn('subir_a_superficie',cognition.action_options({},state,hunt=True,surface={'x':-152,'y':76,'z':-197}))
        agent.record(cp,'minecraft_atacar',{},{'ok':True,'receipt_id':'tool-k','output':json.dumps(
            {'alvo':'cow','entidade_id':7,'golpes':3,'morto':False,'sessionId':'s'})},'')
        self.assertEqual(cp.get('kills') or [],[])
        agent.record(cp,'minecraft_atacar',{},{'ok':True,'receipt_id':'tool-k2','output':json.dumps(
            {'alvo':'cow','entidade_id':7,'golpes':4,'morto':True,'sessionId':'s'})},'')
        self.assertEqual(agent.remaining(criteria,cp,state),{})

    def test_hunt_and_collect_quantity_with_goal_progress(self):
        # Pedido humano 29/10: caçar/coletar escolhendo a quantidade, vendo tem/meta do objetivo.
        from core import minecraft_cognition as cognition
        criteria={'crafted':{},'inventory':{'iron_ingot':10,'iron_ore':10},'placed':{},'equipped':{},'groups':{'cooked_meat':30}}
        cows=[{'id':i,'name':'cow','type':'mob','distance':5.0+i,'position':{'x':i,'y':64,'z':1}} for i in range(1,4)]
        state={'connected':True,'sessionId':'s','inventory':[{'name':'cooked_salmon','count':7},{'name':'salmon','count':1},
               {'name':'iron_ingot','count':2}],'equipment':{},'nearbyEntities':cows,'position':{'x':0,'y':64,'z':0},
               'furnaceRuns':[{'position':{'x':40,'y':64,'z':0},'input':'salmon','expectedOutput':'cooked_salmon','count':8,
                               'remaining':8,'fuel':'coal','fuelCount':1,'depositedAt':'2026-10-28T19:11:48Z'}]}
        progress=cognition.goal_progress(criteria,state)
        self.assertEqual(progress['cooked_meat'],{'tem':7,'meta':30,'cruas_no_inventario':1,'no_seu_forno':8,'falta_obter':14})
        self.assertEqual(progress['iron_ingot'],{'tem':2,'meta':10})
        perception={'arredores':{'iron_ore':{'mais_proximo':{'x':1,'y':55,'z':1},'ferramenta_ok':True,'veio':3}}}
        options=cognition.action_options(perception,state,hunt={'beef'},goal=criteria)
        hunt=options['cacar:cow']
        self.assertEqual(hunt['arguments']['quantidade'],3)  # 3 vacas à vista, faltam 14
        self.assertEqual(hunt['quantidade'],{'arg':'quantidade','min':1,'max':8,'padrao':3})
        self.assertIn('cooked_meat 7/30 (cruas 1, no seu forno 8, faltam obter 14)',hunt['effect'])
        self.assertEqual(cognition.option_arguments(hunt,json.dumps({'opcao':'cacar:cow','comentario':'','quantidade':2}))['quantidade'],2)
        self.assertEqual(cognition.option_arguments(hunt,json.dumps({'opcao':'cacar:cow','comentario':''}))['quantidade'],3)
        with self.assertRaises(ValueError):cognition.option_arguments(hunt,json.dumps({'opcao':'cacar:cow','comentario':'','quantidade':9}))
        self.assertIn('você tem 0/10 iron_ore que o objetivo pede',options['coletar:iron_ore']['effect'])  # 1.16.5: minério solta minério
        ore=options['coletar:iron_ore']
        self.assertEqual(cognition.option_arguments(ore,json.dumps({'opcao':'coletar:iron_ore','comentario':'','quantidade':12}))['quantidade'],12)
        self.assertEqual(cognition.parse_choice(json.dumps({'opcao':'cacar:cow','comentario':'ok','quantidade':2}),options)[0],'cacar:cow')
        cp={'kills':[],'session_id':'s'}
        agent.record({**cp,'events':[]},'minecraft_atacar',{},{'ok':True,'receipt_id':'tool-q','output':json.dumps(
            {'alvo':'cow','entidade_id':1,'morto':True,'mortos':2,'abatidos':[{'alvo':'cow','entidade_id':1},
             {'alvo':'cow','entidade_id':2}],'sessionId':'s'})},'')
        serial={**cp,'events':[]}
        agent.record(serial,'minecraft_atacar',{},{'ok':True,'receipt_id':'tool-q2','output':json.dumps(
            {'alvo':'cow','entidade_id':1,'morto':True,'mortos':2,'abatidos':[{'alvo':'cow','entidade_id':1},
             {'alvo':'cow','entidade_id':2}],'sessionId':'s'})},'')
        self.assertEqual([k['entity_id'] for k in serial['kills']],[1,2])

    def test_objective_items_already_made_and_plan_excess_are_reported(self):
        # 28/10: com capacete feito, planejou "ter 5 iron_helmet" de reserva usando lingotes das peças que faltavam.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state={**state,'inventory':[{'name':'iron_ingot','count':9}]}
        perception={'receitas':[{'item':'iron_helmet','bancada_a_4_blocos':True,'variantes':[{'exige_bancada':True,
            'ingredientes':[{'nome':'iron_ingot','tem':9,'precisa':5}]}]}]}
        options=cognition.action_options(perception,state,done=['iron_helmet'])
        self.assertIn('outro não avança o objetivo',options['fabricar:iron_helmet']['effect'])
        criteria={'crafted':{'iron_helmet':1,'iron_leggings':1},'inventory':{'iron_sword':1}}
        steps=[{'passo':'reserva','feito_quando':{'tipo':'ter','item':'iron_helmet','quantidade':5}},
               {'passo':'calças','feito_quando':{'tipo':'ter','item':'iron_leggings','quantidade':1}},
               {'passo':'lingotes','feito_quando':{'tipo':'ter','item':'iron_ingot','quantidade':20}}]
        self.assertEqual(cognition.plan_excess(steps,criteria),'Plano registrado, mas pede mais do que o objetivo exige: '
                         'iron_helmet 5 (o objetivo pede 1); o excedente consome material das peças que faltam.')
        self.assertIsNone(cognition.plan_excess(steps[1:],criteria))

    def test_collect_option_takes_the_observed_vein_with_a_cap(self):
        # 28/10: o humano viu ferro e carvão ficando para trás; cada decisão pegava um bloco só.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        perception={'arredores':{'iron_ore':{'mais_proximo':{'x':1,'y':55,'z':1},'ferramenta_ok':True,'veio':5},
                                 'coal_ore':{'mais_proximo':{'x':2,'y':55,'z':1},'ferramenta_ok':True,'veio':14},
                                 'oak_log':{'mais_proximo':{'x':3,'y':64,'z':1},'ferramenta_ok':True},
                                 'stone':{'mais_proximo':{'x':4,'y':60,'z':1},'ferramenta_ok':True,'veio':30}}}
        options=cognition.action_options(perception,state)
        self.assertEqual(options['coletar:iron_ore']['arguments']['quantidade'],5)
        self.assertEqual(options['coletar:coal_ore']['arguments']['quantidade'],8)  # limite para minério
        self.assertEqual(options['coletar:oak_log']['arguments']['quantidade'],1)   # sem veio informado
        self.assertEqual(options['coletar:stone']['arguments']['quantidade'],4)
        self.assertIn('5 bloco(s) de iron_ore do veio',options['coletar:iron_ore']['effect'])

    def test_armor_in_inventory_is_offered_for_its_real_slot(self):
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state['inventory']=[{'name':'iron_helmet','count':1},{'name':'iron_boots','count':1}]
        state['equipment']={'head':None,'torso':None,'legs':None,'feet':{'name':'iron_boots'}}
        options=cognition.action_options({},state)
        self.assertEqual(options['equipar:iron_helmet']['arguments'],{'nome':'iron_helmet','destino':'head'})
        self.assertNotIn('equipar:iron_boots',options)  # já está no slot

    def test_collect_option_needs_the_observed_harvest_tool(self):
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        perception={'arredores':{'iron_ore':{'mais_proximo':{'x':1,'y':55,'z':1},'ferramenta_ok':False,'ferramentas':['stone_pickaxe']},
                                 'coal_ore':{'mais_proximo':{'x':1,'y':59,'z':1},'ferramenta_ok':True}}}
        options=cognition.action_options(perception,state)
        self.assertNotIn('coletar:iron_ore',options);self.assertIn('coletar:coal_ore',options)

    def test_options_point_out_what_serves_her_own_current_subgoal(self):
        # 27/10: meta autoral "furnace 1" correta, mas a decisão seguinte coletava carvão.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state['inventory']=[{'name':'cobblestone','count':16},{'name':'crafting_table','count':4},{'name':'coal','count':5}]  # 30/10: dentro da margem
        furnace={'item':'furnace','bancada_a_4_blocos':False,'variantes':[{'exige_bancada':True,
                 'ingredientes':[{'nome':'cobblestone','precisa':8,'tem':16}]}]}
        perception={'receitas':[furnace],'arredores':{
            'crafting_table':{'mais_proximo':{'x':-96,'y':69,'z':-61}},'coal_ore':{'mais_proximo':{'x':1,'y':59,'z':1},'ferramenta_ok':True}}}
        goal={'item':'furnace','total':1,'note':'Criar forno.'}
        options=cognition.action_options(perception,state,goal)
        for name in ('aproximar:crafting_table','equipar:crafting_table'):
            self.assertIn('sua meta furnace exige bancada',options[name]['effect'])
        self.assertNotIn('meta',options['coletar:coal_ore']['effect'])
        furnace['bancada_a_4_blocos']=True
        self.assertIn('atende sua meta atual',cognition.action_options(perception,state,goal)['fabricar:furnace']['effect'])
        self.assertNotIn('meta',cognition.action_options(perception,state)['fabricar:furnace']['effect'])  # sem meta, sem anotação

    def test_collect_option_states_how_much_of_the_drop_is_already_owned(self):
        # 27/10: com 18 carvões, a opção de coletar carvão (sem essa informação) a afastava da bancada.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state['inventory']=[{'name':'coal','count':8},{'name':'cobblestone','count':9}]  # 30/10: mais de 10 sobrando some
        perception={'arredores':{'coal_ore':{'mais_proximo':{'x':1,'y':59,'z':1},'ferramenta_ok':True},
                                 'stone':{'mais_proximo':{'x':0,'y':63,'z':0},'ferramenta_ok':True},
                                 'oak_log':{'mais_proximo':{'x':3,'y':64,'z':3},'ferramenta_ok':True}}}
        options=cognition.action_options(perception,state)
        self.assertIn('você já tem 8 coal',options['coletar:coal_ore']['effect'])
        self.assertIn('você já tem 9 cobblestone',options['coletar:stone']['effect'])
        self.assertIn('você já tem 0 oak_log',options['coletar:oak_log']['effect'])

    def test_smelting_requirement_makes_furnace_a_known_subgoal(self):
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        perception={'receitas':[{'item':'iron_ingot','variantes':[{'processo':'fornalha','exige_forno':True,'forno_a_4_blocos':False,
            'ingredientes':[{'nome':'iron_ore','precisa':1,'tem':16}]}]}]}
        self.assertIn('furnace',cognition.subgoal_candidates(perception,state))

    def test_owned_station_is_not_offered_again_as_fabrication(self):
        # 27/10 13:18: com 3 bancadas no inventário, a opção oferecida levou à 4ª.
        from core import minecraft_cognition as cognition
        _,_,state,_=self.cognitive_fixture()
        state['inventory']=[{'name':'oak_planks','count':7},{'name':'crafting_table','count':3}]
        recipe={'item':'crafting_table','variantes':[{'exige_bancada':False,'ingredientes':[{'nome':'oak_planks','precisa':4,'tem':7}]}]}
        options=cognition.action_options({'receitas':[recipe]},state)
        self.assertNotIn('fabricar:crafting_table',options);self.assertIn('equipar:crafting_table',options)
        state['inventory']=[{'name':'oak_planks','count':7}]
        self.assertIn('fabricar:crafting_table',cognition.action_options({'receitas':[recipe]},state))

    def test_station_subgoal_does_not_accumulate_what_is_already_owned(self):
        # 27/10: "crafting_table 20" com nota "colocar a mesa" fez fabricar bancadas em laço.
        from core import minecraft_cognition as cognition
        _,cp,state,perception=self.cognitive_fixture()
        state['inventory'].append({'name':'crafting_table','count':3})
        perception['arredores']={'crafting_table':{'mais_proximo':{'x':0,'y':64,'z':0}}}
        with self.assertRaisesRegex(ValueError,'acao_direta'):
            cognition.accept_subgoal(cp,{'item':'crafting_table','total':20,'note':'Colocar a mesa.'},state,perception,'lilith')
        state['inventory'].pop()
        selected=cognition.accept_subgoal(cp,{'item':'crafting_table','total':1,'note':'Preciso de uma bancada.'},state,perception,'lilith')
        self.assertEqual(selected['total'],1)

    def test_action_options_ground_fabrication_in_current_inventory_not_optimistic_flag(self):
        from core import minecraft_cognition as cognition
        _,_,state,perception=self.cognitive_fixture()
        for recipe in perception['receitas']:
            for variant in recipe['variantes']:variant['pode_agora']=True;variant['exige_bancada']=False
        options=cognition.action_options(perception,state)
        self.assertEqual(options['fabricar:oak_planks']['arguments'],{'nome':'oak_planks','quantidade':1})
        self.assertNotIn('fabricar:wooden_pickaxe',options)  # faltam tábuas, mesmo com flag incorreta
        state['inventory'][1]['count']=3
        perception['receitas'][0]['variantes'][0]['exige_bancada']=True
        self.assertNotIn('fabricar:wooden_pickaxe',cognition.action_options(perception,state))
        perception['receitas'][0]['bancada_a_4_blocos']=True
        self.assertIn('fabricar:wooden_pickaxe',cognition.action_options(perception,state))

    def test_action_options_preserve_free_choice_and_use_observed_workstation_position(self):
        from core import minecraft_cognition as cognition
        _,_,state,perception=self.cognitive_fixture()
        perception['arredores']={'crafting_table':{'mais_proximo':{'x':7,'y':64,'z':9},'distancia':9}}
        options=cognition.action_options(perception,state)
        self.assertEqual(options['aproximar:crafting_table']['arguments'],{'x':7,'y':64,'z':9,'distancia':3})
        self.assertIn('outra',options);self.assertNotIn('equipar:crafting_table',options)

    def test_model_can_decline_new_inventory_subgoal_for_placement_or_equipment(self):
        from core import minecraft_cognition as cognition
        _,cp,state,perception=self.cognitive_fixture()
        cp['subgoal']={'item':'crafting_table','total':1,'author':'lilith','selected_step':0,'note':'x'}
        state['inventory'].append({'name':'crafting_table','count':1})
        result=cognition.accept_subgoal(cp,{'item':'acao_direta','total':0,'note':'Agora vou colocar a bancada.'},state,perception,'lilith')
        self.assertIsNone(cp['subgoal']);self.assertEqual(result['author'],'lilith')
        self.assertEqual(cp['subgoal_review_step'],0);self.assertEqual(cp['subgoal_history'][-1]['missing'],0)

    def test_transition_does_not_invent_inventory_loss_or_gain_across_unverified_sessions(self):
        from core import minecraft_cognition as cognition
        criteria,cp,state,_=self.cognitive_fixture()
        for before,after in ((state,{'connected':False}),({'connected':False},state),(state,state|{'sessionId':'s2'})):
            cognition.record_transition(criteria,cp,before,after,'minecraft_estado',{}, {'status':'success','receipt_id':'obs'})
            self.assertIsNone(cp['trajectory'][-1]['inventory_delta'])
            self.assertIsNone(cp['trajectory'][-1]['moved']);self.assertFalse(cp['trajectory'][-1]['comparable'])

    def test_address_only_scope_prefix_keeps_the_named_goal(self):
        criteria=agent.targets('Minecraft host 127.0.0.1 porta 37837: fabrique uma bancada.')
        self.assertIsNotNone(criteria)
        self.assertEqual(criteria['crafted'],{'crafting_table':1})

    def test_an_extra_unrecognized_stage_cannot_be_omitted_from_goal_criteria(self):
        for text in ('Minecraft: fabrique uma bancada. Depois faça uma casa.',
                     'Minecraft: fabrique uma picareta de madeira. Monte uma casa.',
                     'Minecraft: fabrique uma bancada e depois arrume a aldeia.',
                     'Minecraft: fabrique uma picareta de madeira. Acenda um forno.',
                     'Minecraft: durma e fabrique uma picareta de madeira.'):
            self.assertIsNone(agent.targets(text),text)

    def test_finishing_rechecks_that_criteria_cover_the_current_whole_goal(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        text='Minecraft: fabrique uma picareta de madeira. Depois faça uma casa.'
        task=task_state.iniciar_ou_continuar(('test','mixed-goal',''),text)
        partial=agent.targets('Minecraft: fabrique uma picareta de madeira.')
        cp=agent.initial(text,partial);cp['session_id']='s1'
        state=world(inventory=[{'name':'wooden_pickaxe','count':1}])
        agent.record(cp,'minecraft_craft',{'nome':'wooden_pickaxe'},dict(ok=True,status='success',
            receipt_id='partial-craft',output=json.dumps({'item':'wooden_pickaxe','before':[],'after':state['inventory']})),'')
        with self.assertRaisesRegex(ValueError,'CRITERIA_INCOMPLETE'):
            agent.finish_task(task,partial,cp,state)
        self.assertEqual(task_state.status_id(task.id),'active')

    def test_named_goal_is_not_satisfied_by_connection_or_promises(self):
        goal=agent.targets('Minecraft: fabrique e coloque uma bancada e fabrique uma picareta de madeira.')
        self.assertEqual(goal['inventory'],{'wooden_pickaxe':1})
        self.assertEqual(goal['placed'],{'crafting_table':1})
        self.assertEqual(goal['crafted'],{'crafting_table':1,'wooden_pickaxe':1})
        cp=agent.initial('goal',goal)
        state=world(inventory=[{'name':'wooden_pickaxe','count':1}]);cp['session_id']='s1'
        self.assertFalse(agent.finished(goal,cp,state))  # até um item dado é insuficiente
        cp['crafted']={'crafting_table':1,'wooden_pickaxe':1};cp['placed']={'crafting_table':1}
        cp['placement_records']={'fixture':{'name':'crafting_table','position':{'x':1,'y':64,'z':1},'session_id':'s1','dimension':'overworld'}}
        agent.confirm_placements(cp,'crafting_table',[{'position':{'x':1,'y':64,'z':1}}],state)
        self.assertTrue(agent.finished(goal,cp,state))

    def test_remaining_reports_only_unmet_criteria_with_the_same_verifier(self):
        goal=agent.targets('Minecraft: fabrique e coloque uma bancada e fabrique uma picareta de madeira.')
        cp=agent.initial('goal',goal);cp['session_id']='s1';cp['crafted']={'crafting_table':2,'oak_planks':8}
        state=world(inventory=[{'name':'crafting_table','count':2}])
        self.assertEqual(agent.remaining(goal,cp,state),{'fabricar':{'wooden_pickaxe':1},
            'colocar_no_mundo_conferido':{'crafting_table':1},'ter_no_inventario':{'wooden_pickaxe':1}})
        cp['crafted']['wooden_pickaxe']=1;cp['placed']={'crafting_table':1}
        cp['placement_records']={'k':{'name':'crafting_table','position':{'x':1,'y':64,'z':1},'session_id':'s1','dimension':'overworld'}}
        state['inventory']=[{'name':'wooden_pickaxe','count':1}]
        agent.confirm_placements(cp,'crafting_table',[{'position':{'x':1,'y':64,'z':1}}],state)
        self.assertEqual(agent.remaining(goal,cp,state),{});self.assertTrue(agent.finished(goal,cp,state))

    def test_full_diamond_armor_requires_each_slot_and_crafting(self):
        goal=agent.targets('Minecraft: fabrique e equipe uma armadura completa de diamante.')
        self.assertEqual(len(goal['equipped']),4)
        cp=agent.initial('goal',goal)
        state=world(equipment={slot:{'name':name} for slot,name in goal['equipped'].items()});cp['session_id']='s1'
        self.assertFalse(agent.finished(goal,cp,state))
        cp['crafted']={name:1 for name in goal['equipped'].values()}
        self.assertTrue(agent.finished(goal,cp,state))
        state['equipment']['feet']=None;self.assertFalse(agent.finished(goal,cp,state))

    def test_full_iron_kit_requires_armor_equipped_and_tools_crafted(self):
        goal=agent.targets('Minecraft: fabrique e equipe um kit completo de ferro em sobrevivência.')
        armor={'head':'iron_helmet','torso':'iron_chestplate','legs':'iron_leggings','feet':'iron_boots'}
        tools={'iron_sword':1,'iron_pickaxe':1,'iron_axe':1,'iron_shovel':1}
        self.assertEqual(goal['equipped'],armor);self.assertEqual(goal['inventory'],tools)
        self.assertEqual(goal['crafted'],{**{n:1 for n in armor.values()},**tools})
        cp=agent.initial('goal',goal);cp['session_id']='s1';cp['crafted']=dict(goal['crafted'])
        state=world(equipment={slot:{'name':n} for slot,n in armor.items()},inventory=[{'name':n,'count':1} for n in tools])
        self.assertTrue(agent.finished(goal,cp,state))
        state['inventory']=state['inventory'][:-1];self.assertFalse(agent.finished(goal,cp,state))
        self.assertIsNone(agent.targets('Minecraft: fabrique um kit completo de ferro e uma casa.'))

    def test_advice_and_future_mention_are_not_action_goals(self):
        self.assertIsNone(agent.targets('Minecraft: explique como fabricar uma bancada, sem executar.'))
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira. A meta final posterior é armadura de diamante.')
        self.assertFalse(goal['equipped']);self.assertEqual(goal['inventory'],{'wooden_pickaxe':1})

    def test_unsupported_extra_goal_or_large_count_never_gets_partial_contract(self):
        for text in ('Minecraft: fabrique uma bancada e uma casa.',
                     'Minecraft: fabrique uma bancada e escreva um arquivo.',
                     'Minecraft: fabrique uma bancada e equipe uma armadura completa de diamante.',
                     'Minecraft: fabrique uma picareta de diamante e colete 2 diamantes.',
                     'Minecraft no modo copiloto: fabrique uma bancada.',
                     'Minecraft: colete 100 diamantes.'):
            self.assertIsNone(agent.targets(text),text)

    def test_creative_or_unknown_mode_is_not_survival_approval(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.')
        cp=agent.initial('goal',goal);cp['crafted']['wooden_pickaxe']=1
        for mode in (None,'creative'):
            state={'connected':True,'verified':True,'gameMode':mode,'inventory':[{'name':'wooden_pickaxe','count':1}]}
            self.assertFalse(agent.finished(goal,cp,state))

    def test_actual_recipe_delta_and_placement_receipts_are_required(self):
        goal=agent.targets('Minecraft: fabrique e coloque uma bancada.')
        cp=agent.initial('goal',goal);cp['session_id']='s1'
        result={'ok':True,'status':'success','receipt_id':'tool-real','output':json.dumps({
            'item':'crafting_table','before':[],'after':[{'name':'crafting_table','count':1}]})}
        agent.record(cp,'minecraft_craft',{'nome':'crafting_table'},result,'Resultado observado.')
        self.assertEqual(cp['crafted'],{'crafting_table':1})
        agent.record(cp,'minecraft_colocar_bloco',{},dict(result,receipt_id='tool-fake-place',output='Coloquei a bancada.'),'')
        self.assertFalse(cp['placed'])
        agent.record(cp,'minecraft_colocar_bloco',{},dict(result,receipt_id='tool-place-proof',output=json.dumps({
            'placed':{'name':'crafting_table','verified':True,'position':{'x':1,'y':64,'z':1},'sessionId':'s1','dimension':'overworld'}})),'')
        self.assertEqual(cp['placed'],{'crafting_table':1})

    def test_reused_receipt_cannot_count_crafting_twice(self):
        cp=agent.initial('goal',agent.targets('Minecraft: fabrique uma bancada.'))
        r={'ok':True,'status':'success','receipt_id':'same-receipt','output':json.dumps({
            'item':'crafting_table','before':[],'after':[{'name':'crafting_table','count':1}]})}
        agent.record(cp,'minecraft_craft',{},r,'');agent.record(cp,'minecraft_craft',{},r,'')
        self.assertEqual(cp['crafted']['crafting_table'],1)

    def test_consulted_recipes_survive_later_receipts_and_long_output(self):
        cp=agent.initial('goal',agent.targets('Minecraft: fabrique uma bancada.'))
        variants=[{'requiresTable':False,'result':{'id':183,'metadata':None,'count':1},
            'ingredients':[{'name':wood+'_planks','count':4}]} for wood in ('oak','spruce','birch','jungle',
            'acacia','dark_oak','crimson','warped')]*3
        output=json.dumps(variants,indent=2);self.assertGreater(len(output),3000)
        agent.record(cp,'minecraft_receitas',{'nome':'crafting_table'},
            {'ok':True,'status':'success','receipt_id':'tool-recipes','output':output},'')
        agent.record(cp,'minecraft_receitas',{'nome':'oak_planks'},{'ok':False,'status':'error',
            'output':json.dumps([{'requiresTable':False,'result':{'count':9},'ingredients':[{'name':'diamond','count':1}]}])},'')
        for index in range(6):
            agent.record(cp,'minecraft_estado',{},{'ok':True,'status':'success','receipt_id':f'state{index}','output':'{}'},'')
        known=agent.known_recipes(cp)
        self.assertEqual(list(known),['crafting_table'])  # recibo com erro não vira conhecimento
        line,=known['crafting_table']  # variantes repetidas são compactadas numa linha
        self.assertTrue(line.startswith('sem bancada, rende 1: 4 oak_planks | 4 spruce_planks'),line)
        self.assertIn('4 dark_oak_planks',line);self.assertEqual(line.count('|'),7)
        self.assertLess(len(json.dumps(known)),400)  # a visão não deve induzir enumeração longa
        legacy=agent.initial('goal',agent.targets('Minecraft: fabrique uma bancada.'))
        legacy['events']=[{'tool':'minecraft_receitas','arguments':{'nome':'oak_planks'},'status':'success',
            'receipt_id':'tool-legacy','output':json.dumps(variants[:1])},
            {'tool':'minecraft_receitas','arguments':{'nome':'stick'},'status':'success',
            'receipt_id':'tool-cut','output':output[:3000]}]
        self.assertEqual(list(agent.known_recipes(legacy)),['oak_planks'])  # output cortado não é inventado

    def test_wrong_server_or_new_session_cannot_finish_old_crafting(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        cp['target']={'host':'fixture','port':37837};cp['session_id']='s1';cp['crafted']['wooden_pickaxe']=1
        for changes in ({'port':25565},{'sessionId':'s2'}):
            self.assertFalse(agent.finished(goal,cp,world(inventory=[{'name':'wooden_pickaxe','count':1}],**changes)))

    def test_reconnection_to_same_world_and_player_keeps_progress(self):
        goal=agent.targets('Minecraft: fabrique e coloque uma bancada.');cp=agent.initial('goal',goal)
        first=world(username='LilithMC');self.assertEqual(agent._bind(cp,first),'')
        cp['crafted']['crafting_table']=1
        cp['placement_records']={'k':{'name':'crafting_table','position':{'x':1,'y':64,'z':1},'session_id':'s1','dimension':'overworld'}}
        cp['placed']={'crafting_table':1}
        again=world(username='LilithMC',sessionId='s2',inventory=[{'name':'crafting_table','count':0}])
        self.assertIn('reconcilie',agent._bind(cp,again));self.assertEqual(cp['session_id'],'s1')
        agent.review_session_continuity(cp,again,reviewer='operador_fixture',reason='Mundo e recibos conferidos',
            evidence=['receipt-before','receipt-after'])
        self.assertEqual(agent._bind(cp,again),'');self.assertEqual(cp['session_id'],'s2')
        self.assertEqual(cp['crafted'],{'crafting_table':1});self.assertIn('s1',cp['previous_sessions'])
        agent.confirm_placements(cp,'crafting_table',[],again);self.assertEqual(cp['placed_present']['crafting_table'],0)
        agent.confirm_placements(cp,'crafting_table',[{'position':{'x':1,'y':64,'z':1}}],again)
        self.assertEqual(cp['placed_present']['crafting_table'],1)  # reencontrada no mundo, não lembrada
        self.assertTrue(agent.finished(goal,cp,again))
        self.assertNotIn('reviewed_reconnection',cp)
        self.assertEqual(cp['session_reviews'][0]['reviewer'],'operador_fixture')
        self.assertIn('reconcilie',agent._bind(cp,world(username='LilithMC',sessionId='s3')))

    def test_session_review_does_not_clear_pending_effect_or_authorize_other_source(self):
        cp=agent.initial('goal',agent.targets('Minecraft: fabrique uma bancada.'))
        agent._bind(cp,world(username='LilithMC'));cp['pending']={'tool':'minecraft_craft','mutates':True}
        args=dict(reviewer='operador',reason='Verificação',evidence=['receipt-real'])
        with self.assertRaisesRegex(ValueError,'SESSION_REVIEW_INVALID'):
            agent.review_session_continuity(cp,world(username='LilithMC',sessionId='s2'),**args)
        self.assertTrue(cp['pending']);cp['pending']=None
        for changed in ({'username':'OtherMC'},{'port':25565}):
            cp['target']={'host':'fixture','port':37837}
            with self.assertRaisesRegex(ValueError,'SESSION_REVIEW_INVALID'):
                agent.review_session_continuity(cp,world(**({'username':'LilithMC','sessionId':'s2'}|changed)),**args)

    def test_reconnection_as_other_player_still_pauses(self):
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal)
        agent._bind(cp,world(username='LilithMC'));cp['crafted']['crafting_table']=1
        self.assertIn('jogador',agent._bind(cp,world(username='OutraMC',sessionId='s2')))
        self.assertEqual(cp['session_id'],'s1')

    def test_same_placement_position_is_not_two_present_blocks(self):
        goal=agent.targets('Minecraft: fabrique e coloque 2 crafting_table.');cp=agent.initial('goal',goal)
        cp['session_id']='s1';cp['crafted']['crafting_table']=2
        point={'x':1,'y':64,'z':1}
        for rid in ('place1','place2'):
            agent.record(cp,'minecraft_colocar_bloco',{},dict(ok=True,status='success',receipt_id=rid,output=json.dumps({
                'placed':{'name':'crafting_table','verified':True,'position':point,'sessionId':'s1','dimension':'overworld'}})),'')
        self.assertFalse(agent.finished(goal,cp,world()))
        agent.confirm_placements(cp,'crafting_table',[{'position':point}],world())
        self.assertEqual(cp['placed_present']['crafting_table'],1)
        self.assertFalse(agent.finished(goal,cp,world()))

    def test_checkpoint_requires_same_task_goal_and_preserves_pending_mutation(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.')
        task=SimpleNamespace(id='checkpoint-test',objetivo='goal')
        cp=agent.initial(task.objetivo,goal);cp['pending']={'tool':'minecraft_craft','arguments':{'nome':'wooden_pickaxe'},'mutates':True}
        agent.save(task,cp);loaded=agent.load(task,goal)
        self.assertEqual(loaded['pending'],cp['pending'])
        with self.assertRaisesRegex(ValueError,'GOAL_CHANGED'):
            agent.load(SimpleNamespace(id=task.id,objetivo='outro goal'),goal)

    def test_database_completion_requires_physical_goal_and_retains_actual_receipts(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','observed-finish','')
        task=task_state.iniciar_ou_continuar(key,'Minecraft: fabrique uma picareta de madeira.')
        goal=agent.targets(task.objetivo);cp=agent.initial(task.objetivo,goal)
        state=world();cp['session_id']='s1'
        with self.assertRaisesRegex(ValueError,'GOAL_NOT_VERIFIED'):agent.finish_task(task,goal,cp,state)
        self.assertEqual(task_state.status_id(task.id),'active')
        state['inventory']=[{'name':'wooden_pickaxe','count':1}]
        agent.record(cp,'minecraft_craft',{'nome':'wooden_pickaxe'},
            {'ok':True,'status':'success','receipt_id':'tool-actual-fixture','output':json.dumps({
                'item':'wooden_pickaxe','before':[],'after':state['inventory']})},'Resultado anterior observado.')
        agent.save(task,cp);agent.finish_task(task,goal,cp,state)
        loaded=task_state.carregar_por_id(task.id)
        self.assertEqual(loaded.status,'completed');self.assertEqual(loaded.ultima_acao,'minecraft_goal_verified')
        self.assertEqual(loaded.etapas[0]['ferramentas_executadas_lista'],['tool-actual-fixture'])


    def test_verified_goal_closes_every_pending_fragment_of_the_same_objective(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        # 30/10: "depois da queda" não corta mais a frase; o fragmento de RP usa um conector real ("e depois").
        text='Minecraft: fabrique uma picareta de madeira. RP: a energia caiu e depois voltamos. Quero ver você jogar.'
        task=task_state.iniciar_ou_continuar(('test','observed-fragments',''),text)
        self.assertGreater(len(task.etapas),1)
        goal=agent.targets(task.objetivo);cp=agent.initial(task.objetivo,goal);cp['session_id']='s1'
        state=world(inventory=[{'name':'wooden_pickaxe','count':1}])
        agent.record(cp,'minecraft_craft',{'nome':'wooden_pickaxe'},{'ok':True,'status':'success','receipt_id':'tool-frag',
            'output':json.dumps({'item':'wooden_pickaxe','before':[],'after':state['inventory']})},'')
        agent.finish_task(task,goal,cp,state)
        loaded=task_state.carregar_por_id(task.id)
        self.assertEqual(loaded.status,'completed');self.assertTrue(all(e['status']=='done' for e in loaded.etapas))
        self.assertEqual(loaded.etapas[0]['ferramentas_executadas_lista'],['tool-frag'])


class Loop(unittest.IsolatedAsyncioTestCase):
    async def test_only_one_reply_per_new_message_is_exempt_from_work_stagnation(self):
        criteria=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('fixture',criteria)
        cp['no_progress']=3;state=world(recentChat=[{'id':'s1:1','sessionId':'s1','username':'Gustavo','message':'oi'}])
        await agent.run(criteria,cp,ask=AsyncMock(side_effect=[{'tool':'minecraft_chat','arguments':{'texto':t}} for t in ['oi','de novo']]),
            execute=AsyncMock(return_value={'ok':True,'status':'success','receipt_id':'accepted','output':'aceito'}),
            observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),persist=lambda _:None,
            allowed={'minecraft_chat'},validate=lambda *_:'',limit=2)
        self.assertEqual(cp['no_progress'],4)

    async def test_new_incoming_chat_can_receive_same_reply_without_replaying_old_context(self):
        criteria=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('fixture',criteria)
        state=world(recentChat=[{'id':'s1:1','sessionId':'s1','username':'Gustavo','message':'oi'}])
        async def execute(*_):
            state['recentChat']=[{'id':'s1:2','sessionId':'s1','username':'Gustavo','message':'oi de novo'}]
            return {'ok':True,'status':'success','receipt_id':'chat-'+str(len(cp['events'])),'output':'aceito'}
        sender=AsyncMock(side_effect=execute)
        await agent.run(criteria,cp,ask=AsyncMock(return_value={'tool':'minecraft_chat','arguments':{'texto':'Oi!'}}),
            execute=sender,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),persist=lambda _:None,
            allowed={'minecraft_chat'},validate=lambda *_:'',limit=2)
        self.assertEqual(sender.await_count,2)

    async def test_conversation_preserves_task_and_does_not_count_as_work_or_stagnation(self):
        criteria=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('fixture',criteria)
        cp['no_progress']=3;state=world(recentChat=[{'id':'s1:1','sessionId':'s1','username':'Gustavo','message':'oi'}])
        await agent.run(criteria,cp,ask=AsyncMock(return_value={'tool':'minecraft_chat','arguments':{'texto':'Oi!'}}),
            execute=AsyncMock(return_value={'ok':True,'status':'success','receipt_id':'chat-accepted','output':'aceito'}),
            observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),persist=lambda _:None,
            allowed={'minecraft_chat'},validate=lambda *_:'',limit=1)
        self.assertEqual(cp['no_progress'],3);self.assertFalse(agent.finished(criteria,cp,state))
        self.assertEqual(cp['crafted'],{});self.assertEqual(cp['events'][-1]['receipt_id'],'chat-accepted')

    async def test_disconnected_state_query_is_allowed_before_joining_a_world(self):
        criteria=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('fixture',criteria)
        state={'connected':False,'verified':False,'connectionState':'idle','inventory':[]}
        result=await agent.run(criteria,cp,ask=AsyncMock(return_value={'tool':'minecraft_estado','arguments':{}}),
            execute=AsyncMock(return_value={'ok':True,'status':'success','receipt_id':'setup-state','output':json.dumps(state),'mutates':False}),
            observe=AsyncMock(return_value=state),persist=lambda _:None,allowed={'minecraft_estado'},validate=lambda *_:'',limit=1)
        self.assertEqual(result['used'],['minecraft_estado'])
        self.assertEqual(cp['events'][-1]['receipt_id'],'setup-state')
    async def test_real_agent_loop_keeps_receipt_backed_transition_for_next_choice(self):
        criteria=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('fixture',criteria)
        state=world(inventory=[{'name':'oak_log','count':1}])
        async def execute(tool,args):
            state['inventory'][0]['count']=2
            return {'ok':True,'status':'success','receipt_id':'transition-real','output':'collected'}
        result=await agent.run(criteria,cp,ask=AsyncMock(return_value={'tool':'minecraft_coletar','arguments':{'nome':'oak_log'}}),
            execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),persist=lambda _:None,
            allowed={'minecraft_coletar'},validate=lambda *_:'',limit=1)
        self.assertEqual(result['status'],'paused')
        self.assertEqual(cp['trajectory'][0]['inventory_delta'],{'oak_log':1})
        self.assertEqual(cp['trajectory'][0]['receipt_id'],'transition-real')

    async def test_new_session_with_progress_cannot_complete_from_an_unrelated_item(self):
        criteria=agent.targets('Minecraft: fabrique uma picareta de madeira.')
        cp=agent.initial('goal',criteria);cp['crafted']['wooden_pickaxe']=1
        cp['session_id']='world-A';cp['username']='FixturePlayer'
        execute=AsyncMock();ask=AsyncMock()
        state=world(sessionId='world-B',username='FixturePlayer',inventory=[{'name':'wooden_pickaxe','count':1}])
        outcome=await agent.run(criteria,cp,ask=ask,execute=execute,observe=AsyncMock(return_value=state),
            persist=lambda _:None,allowed={'minecraft_craft'},validate=lambda *_:'',resume=True)
        self.assertEqual(outcome['status'],'paused');self.assertEqual(cp['session_id'],'world-A')
        ask.assert_not_awaited();execute.assert_not_awaited()

    async def test_session_change_during_decision_is_checked_before_effect(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        execute=AsyncMock()
        result=await agent.run(goal,cp,ask=AsyncMock(return_value={'tool':'minecraft_craft','arguments':{}}),
            execute=execute,observe=AsyncMock(side_effect=[world(),world(sessionId='s2')]),persist=lambda x:None,
            allowed={'minecraft_craft'},validate=lambda t,a:'',limit=1)
        self.assertEqual(result['status'],'paused');execute.assert_not_awaited()

    async def test_known_precondition_can_retry_after_ingredients_change(self):
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal)
        state=world(inventory=[{'name':'oak_log','count':3}]);calls=[]
        async def execute(tool,args):
            calls.append(args['nome']);before=copy.deepcopy(state['inventory'])
            if len(calls)==1:return {'ok':False,'status':'error','precondition_failed':True,'effect_started':False,'output':'faltam tábuas'}
            state['inventory']=([{'name':'oak_planks','count':4}] if len(calls)==2 else [{'name':'crafting_table','count':1}])
            return {'ok':True,'status':'success','receipt_id':str(len(calls)),'output':json.dumps({'item':args['nome'],'before':before,'after':state['inventory']})}
        choices=iter(['crafting_table','oak_planks','crafting_table'])
        async def ask(*_):return {'tool':'minecraft_craft','arguments':{'nome':next(choices)}}
        result=await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),
            persist=lambda x:None,allowed={'minecraft_craft'},validate=lambda t,a:'',limit=3)
        self.assertEqual(result['status'],'completed');self.assertEqual(calls,['crafting_table','oak_planks','crafting_table'])

    async def test_changing_held_item_releases_failed_placement(self):
        goal=agent.targets('Minecraft: fabrique e coloque uma bancada.');cp=agent.initial('goal',goal)
        state=world(heldItem={'name':'dark_oak_log','count':1},inventory=[{'name':'crafting_table','count':1}]);calls=[]
        async def execute(tool,args):
            calls.append(tool)
            if tool=='minecraft_equipar':state['heldItem']={'name':'crafting_table','count':1};return {'ok':True,'status':'success','output':'ok'}
            return {'ok':False,'status':'error','precondition_failed':True,'output':'segurando outro item'}
        place={'tool':'minecraft_colocar_bloco','arguments':{'x':1,'y':63,'z':1,'face':'up'}}
        choices=iter([place,{'tool':'minecraft_equipar','arguments':{'nome':'crafting_table','destino':'hand'}},place])
        async def ask(*_):return next(choices)
        await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),
            persist=lambda x:None,allowed={'minecraft_colocar_bloco','minecraft_equipar'},validate=lambda t,a:'',limit=3)
        self.assertEqual(calls,['minecraft_colocar_bloco','minecraft_equipar','minecraft_colocar_bloco'])

    async def test_walking_does_not_release_failed_ingredient_precondition(self):
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal)
        state=world(inventory=[]);calls=[]
        async def execute(tool,args):
            calls.append(tool)
            if tool=='minecraft_ir_para':state['position']={'x':20,'y':64,'z':0};return {'ok':True,'status':'success','output':'movimento terminado'}
            return {'ok':False,'status':'error','precondition_failed':True,'effect_started':False,'output':'faltam tábuas'}
        choices=iter([{'tool':'minecraft_craft','arguments':{'nome':'crafting_table'}},
                      {'tool':'minecraft_ir_para','arguments':{'x':20,'y':64,'z':0}},
                      {'tool':'minecraft_craft','arguments':{'nome':'crafting_table'}}])
        async def ask(*_):return next(choices)
        result=await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),
            persist=lambda x:None,allowed={'minecraft_craft','minecraft_ir_para'},validate=lambda t,a:'',limit=3)
        self.assertEqual(calls,['minecraft_craft','minecraft_ir_para']);self.assertEqual(result['status'],'paused')

    async def test_barrier_levels_review_then_ask_by_chat_before_pausing(self):
        # Pedido humano 27/10: barreira não encerra; nível 1 revisa o plano, nível 2 pergunta pelo chat.
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal)
        state=world(inventory=[{'name':'oak_log','count':3}]);levels=[]
        async def stuck(_,checkpoint):
            levels.append((checkpoint.get('barrier') or {}).get('level',0))
            raise agent.DecisionRejected('sem opção útil')
        result=await agent.run(goal,cp,ask=stuck,execute=AsyncMock(),observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),
            persist=lambda x:None,allowed={'minecraft_craft'},validate=lambda t,a:'',limit=4*agent.PATIENCE)
        self.assertEqual(levels,[0]*agent.PATIENCE+[1]*agent.PATIENCE+[2]*agent.PATIENCE)
        self.assertEqual(result['status'],'paused');self.assertIn('perguntar ao humano',result['reason'])
        # Avanço no mundo encerra a barreira.
        cp2=agent.initial('goal',goal);cp2['barrier']={'level':1,'step':0,'reason':'x'}
        async def craft(*_):return {'tool':'minecraft_craft','arguments':{'nome':'oak_planks'}}
        async def execute(tool,args):
            state['inventory']=[{'name':'oak_log','count':2},{'name':'oak_planks','count':4}]
            return {'ok':True,'status':'success','receipt_id':'r1','output':'{}'}
        await agent.run(goal,cp2,ask=craft,execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),
            persist=lambda x:None,allowed={'minecraft_craft'},validate=lambda t,a:'',limit=1)
        self.assertNotIn('barrier',cp2)

    async def test_controller_refusal_is_not_memorized_as_a_permanent_failure(self):
        # 28/10: recusa por risco (monstros) barrava a mesma coleta mesmo depois de Pacífico.
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal)
        state=world(inventory=[]);calls=[]
        async def execute(tool,args):
            calls.append(tool)
            if len(calls)==1:return {'ok':False,'status':'error','output':'ERRO_CONTROLADOR: Risco observado tem prioridade.'}
            state['inventory']=[{'name':'oak_log','count':1}]
            return {'ok':True,'status':'success','receipt_id':'r2','output':'{}'}
        async def ask(*_):return {'tool':'minecraft_coletar','arguments':{'nome':'oak_log'}}
        await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),
            persist=lambda x:None,allowed={'minecraft_coletar'},validate=lambda t,a:'',limit=2)
        self.assertEqual(calls,['minecraft_coletar','minecraft_coletar']);self.assertEqual(cp['failures'],{})

    async def test_chat_thread_keeps_her_question_and_the_human_reply_in_order(self):
        # 28/10: ela perguntou no chat, o humano respondeu e ela não ligou a resposta à própria pergunta.
        from core import minecraft_cognition as cognition
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal);state=world()
        async def ask(*_):return {'tool':'minecraft_chat','arguments':{'texto':'ATO, você me vê?'}}
        async def execute(tool,args):return {'ok':True,'status':'success','receipt_id':'c1','output':'enviado'}
        await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),
            persist=lambda x:None,allowed={'minecraft_chat'},validate=lambda t,a:'',limit=1)
        cognition.mark_chat_presented(state,cp,[{'id':'s:1','seq':1,'username':'ATO','message':'qual é seu objetivo?'}])
        view=cognition.conversation_view(cp)
        self.assertEqual([(l['quem'],l['texto']) for l in view['falas']],[('você','ATO, você me vê?'),('ATO','qual é seu objetivo?')])
        self.assertTrue(view['aguardando_sua_resposta'])
        cp['steps']+=30;self.assertEqual(cognition.conversation_view(cp),{})  # conversa antiga sai da visão

    async def test_decision_without_native_call_is_feedback_not_immediate_pause(self):
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal)
        state=world(inventory=[{'name':'oak_log','count':3}]);seen=[]
        async def ask(_,checkpoint):
            seen.append([e['output'] for e in checkpoint['events']])
            if len(seen)==1:raise agent.DecisionRejected('MINECRAFT_UMA_CHAMADA_NATIVA_OBRIGATORIA: 0 chamadas')
            return {'tool':'minecraft_craft','arguments':{'nome':'oak_planks'}}
        async def execute(tool,args):
            before=copy.deepcopy(state['inventory']);state['inventory']=[{'name':'oak_log','count':2},{'name':'oak_planks','count':4}]
            return {'ok':True,'status':'success','receipt_id':'r1','output':json.dumps({'item':'oak_planks','before':before,'after':state['inventory']})}
        result=await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),
            persist=lambda x:None,allowed={'minecraft_craft'},validate=lambda t,a:'',limit=2)
        self.assertEqual(len(seen),2);self.assertIn('0 chamadas',seen[1][-1])
        self.assertEqual(cp['events'][0]['status'],'rejected_before_effect');self.assertEqual(cp['events'][1]['receipt_id'],'r1')
        self.assertEqual(result['status'],'paused')  # orçamento do teste, não a resposta em texto

    async def test_repeating_successful_call_without_world_change_gets_feedback(self):
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal)
        offline={'connected':False,'sessionId':None};calls=[];seen=[]
        choices=iter([('minecraft_iniciar_ponte',{}),('minecraft_iniciar_ponte',{}),('minecraft_conectar',{'port':37837})])
        async def ask(_,checkpoint):
            seen.append(checkpoint['events'][-1]['output'] if checkpoint['events'] else '')
            tool,args=next(choices);return {'tool':tool,'arguments':args}
        async def execute(tool,args):
            calls.append(tool);return {'ok':True,'status':'success','output':'ponte iniciada' if tool!='minecraft_conectar' else 'ok'}
        await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(return_value=offline),persist=lambda x:None,
            allowed={'minecraft_iniciar_ponte','minecraft_conectar'},validate=lambda t,a:'',limit=3)
        self.assertEqual(calls,['minecraft_iniciar_ponte','minecraft_conectar'])
        self.assertIn('nada mudou',seen[2])

    async def test_repeating_successful_call_after_world_change_is_allowed(self):
        goal=agent.targets('Minecraft: fabrique 2 crafting_table.');cp=agent.initial('goal',goal)
        state=world(inventory=[{'name':'oak_planks','count':8}]);calls=[]
        async def execute(tool,args):
            calls.append(tool);before=copy.deepcopy(state['inventory'])
            state['inventory']=[{'name':'oak_planks','count':8-4*len(calls)},{'name':'crafting_table','count':len(calls)}]
            return {'ok':True,'status':'success','receipt_id':f'c{len(calls)}','output':json.dumps({'item':'crafting_table','before':before,'after':state['inventory']})}
        result=await agent.run(goal,cp,ask=AsyncMock(return_value={'tool':'minecraft_craft','arguments':{'nome':'crafting_table'}}),
            execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),persist=lambda x:None,
            allowed={'minecraft_craft'},validate=lambda t,a:'',limit=2)
        self.assertEqual(calls,['minecraft_craft']*2);self.assertEqual(result['status'],'completed')

    async def test_repeated_decisions_without_call_stop_by_no_progress(self):
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal);execute=AsyncMock()
        result=await agent.run(goal,cp,ask=AsyncMock(side_effect=agent.DecisionRejected('texto sem chamada')),
            execute=execute,observe=AsyncMock(return_value=world()),persist=lambda x:None,
            allowed={'minecraft_craft'},validate=lambda t,a:'',limit=4*agent.PATIENCE)
        self.assertEqual(result['status'],'paused');self.assertIn('sem progresso',result['reason'])
        # Barreira em níveis (27/10): revisar, perguntar pelo chat; só então pausa.
        execute.assert_not_awaited();self.assertEqual(len(cp['events']),3*agent.PATIENCE)

    async def test_patience_allows_using_feedback_after_several_failures(self):
        # Coleta vazia, consulta e recusa informativa: a quarta decisão usa o retorno.
        goal=agent.targets('Minecraft: fabrique e coloque uma bancada.');cp=agent.initial('goal',goal)
        state=world(heldItem={'name':'dark_oak_log','count':1});calls=[]
        async def execute(tool,args):
            calls.append(tool);return {'ok':tool!='minecraft_colocar_bloco','status':'success','output':'sem mudança'}
        choices=iter([('minecraft_coletar',{'nome':'oak_log'}),('minecraft_receitas',{'nome':'stick'}),
                      ('minecraft_colocar_bloco',{'x':1,'y':63,'z':1}),('minecraft_equipar',{'nome':'crafting_table'})])
        async def ask(*_):tool,args=next(choices);return {'tool':tool,'arguments':args}
        await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),persist=lambda x:None,
            allowed={'minecraft_coletar','minecraft_receitas','minecraft_colocar_bloco','minecraft_equipar'},validate=lambda t,a:'',limit=4)
        self.assertEqual(calls[-1],'minecraft_equipar')

    async def test_other_decision_failure_still_pauses_without_retry(self):
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal)
        ask=AsyncMock(side_effect=TimeoutError('prazo'))
        result=await agent.run(goal,cp,ask=ask,execute=AsyncMock(),observe=AsyncMock(return_value=world()),
            persist=lambda x:None,allowed={'minecraft_craft'},validate=lambda t,a:'',limit=10)
        self.assertEqual(result['status'],'paused');self.assertEqual(ask.await_count,1)

    async def test_research_does_not_need_world_connection_or_mutate(self):
        goal=agent.targets('Minecraft: fabrique uma bancada.');cp=agent.initial('goal',goal);calls=[]
        async def execute(tool,args):calls.append(tool);return {'ok':True,'status':'success','output':'receita: 4 tábuas'}
        choices=iter([{'tool':'web_search','arguments':{'query':'receita bancada minecraft'}}])
        async def ask(*_):return next(choices)
        await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(return_value={'connected':False}),
            persist=lambda x:None,allowed={'web_search'},validate=lambda t,a:'',limit=1)
        self.assertEqual(calls,['web_search']);self.assertIn('web_search',agent.READ_ONLY)

    async def test_wrong_destination_never_allows_mutation(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        cp['target']={'host':'fixture','port':37837}
        execute=AsyncMock(return_value={'ok':False,'status':'error'})
        result=await agent.run(goal,cp,ask=AsyncMock(return_value={'tool':'minecraft_craft','arguments':{'nome':'wooden_pickaxe'}}),
            execute=execute,observe=AsyncMock(return_value=world(port=25565)),persist=lambda x:None,
            allowed={'minecraft_craft'},validate=lambda t,a:'',limit=3)
        self.assertEqual(result['status'],'paused');execute.assert_not_awaited()

    async def test_explicit_resume_renews_no_progress_without_replaying_uncertain_effect(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        cp['no_progress']=3;ask=AsyncMock(return_value={'tool':'__done__'})
        await agent.run(goal,cp,ask=ask,execute=AsyncMock(),observe=AsyncMock(return_value=world()),
            persist=lambda x:None,allowed={'minecraft_craft'},validate=lambda t,a:'',limit=1,resume=True)
        self.assertEqual(ask.await_count,1)
        cp['pending']={'tool':'minecraft_craft','mutates':True};ask.reset_mock()
        result=await agent.run(goal,cp,ask=ask,execute=AsyncMock(),observe=AsyncMock(return_value=world()),
            persist=lambda x:None,allowed={'minecraft_craft'},validate=lambda t,a:'',limit=1,resume=True)
        self.assertEqual(result['status'],'uncertain');ask.assert_not_awaited()
    async def test_checkpoint_failure_before_effect_never_calls_executor(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        execute=AsyncMock()
        def fail(_):raise OSError('disk failure fixture')
        with self.assertRaises(OSError):
            await agent.run(goal,cp,ask=AsyncMock(return_value={'tool':'minecraft_craft','arguments':{}}),
                execute=execute,observe=AsyncMock(return_value={'connected':True,'verified':True,'inventory':[]}),
                persist=fail,allowed={'minecraft_craft'},validate=lambda t,a:'',limit=4)
        execute.assert_not_awaited()

    async def test_cancellation_during_decision_does_not_start_effect(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        cancel=[False];execute=AsyncMock()
        async def ask(*_):cancel[0]=True;return {'tool':'minecraft_craft','arguments':{}}
        result=await agent.run(goal,cp,ask=ask,execute=execute,
            observe=AsyncMock(return_value=world()),persist=lambda x:None,
            allowed={'minecraft_craft'},validate=lambda t,a:'',cancelled=lambda:cancel[0],limit=4)
        self.assertEqual(result['status'],'cancelled');execute.assert_not_awaited()

    async def test_pending_effect_on_restart_never_replays(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.')
        cp=agent.initial('goal',goal);cp['pending']={'tool':'minecraft_craft','mutates':True}
        ask,execute=AsyncMock(),AsyncMock()
        result=await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(),persist=lambda x:None,
            allowed={'minecraft_craft'},validate=lambda t,a:'',limit=10)
        self.assertEqual(result['status'],'uncertain');ask.assert_not_awaited();execute.assert_not_awaited()

    async def test_external_tool_is_rejected_before_execution(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        ask=AsyncMock(return_value={'tool':'execute_command','arguments':{'command':'anything'}});execute=AsyncMock()
        result=await agent.run(goal,cp,ask=ask,execute=execute,
            observe=AsyncMock(return_value={'connected':True,'verified':True,'inventory':[]}),persist=lambda x:None,
            allowed={'minecraft_craft'},validate=lambda t,a:'',limit=3)
        self.assertEqual(result['status'],'paused');execute.assert_not_awaited()

    async def test_model_done_without_items_cannot_complete(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        result=await agent.run(goal,cp,ask=AsyncMock(return_value={'tool':'__done__','comment':'Terminei!'}),execute=AsyncMock(),
            observe=AsyncMock(return_value={'connected':True,'verified':True,'inventory':[]}),persist=lambda x:None,
            allowed={'minecraft_craft'},validate=lambda t,a:'',limit=3)
        self.assertEqual(result['status'],'paused')

    async def test_observe_decide_execute_checks_goal_after_real_delta(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        state=world()
        async def execute(tool,args):
            state['inventory']=[{'name':'wooden_pickaxe','count':1}]
            return {'ok':True,'status':'success','receipt_id':'tool-test','output':json.dumps({
                'item':'wooden_pickaxe','before':[],'after':state['inventory']})}
        ask=AsyncMock(return_value={'tool':'minecraft_craft','arguments':{'nome':'wooden_pickaxe'},'comment':'Vou tentar fabricar.'})
        saved=[]
        result=await agent.run(goal,cp,ask=ask,execute=execute,observe=AsyncMock(side_effect=lambda:copy.deepcopy(state)),
            persist=lambda x:saved.append(copy.deepcopy(x)),allowed={'minecraft_craft'},validate=lambda t,a:'',limit=4)
        self.assertEqual(result['status'],'completed');self.assertEqual(ask.await_count,1)
        self.assertTrue(any(x['pending'] for x in saved));self.assertIsNone(saved[-1]['pending'])

    async def test_uncertain_outcome_stops_without_next_decision(self):
        goal=agent.targets('Minecraft: fabrique uma picareta de madeira.');cp=agent.initial('goal',goal)
        ask=AsyncMock(return_value={'tool':'minecraft_craft','arguments':{'nome':'wooden_pickaxe'}})
        result=await agent.run(goal,cp,ask=ask,
            execute=AsyncMock(return_value={'status':'uncertain','outcome_uncertain':True,'output':'RESULTADO_INCERTO'}),
            observe=AsyncMock(return_value=world()),persist=lambda x:None,
            allowed={'minecraft_craft'},validate=lambda t,a:'',limit=10)
        self.assertEqual(result['status'],'uncertain');self.assertEqual(ask.await_count,1)
        self.assertTrue(cp['pending'])



class Stations(unittest.TestCase):
    """30/10 (pedido humano): ela não recuperava as bancadas e fornos que construía."""
    def setUp(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        from core import bd;bd.executar('DROP TABLE IF EXISTS minecraft_stations',strict=True)

    def place(self,cp,name,pos,receipt):
        placed={'name':name,'position':pos,'sessionId':'s1','dimension':'overworld','verified':True}
        agent.record(cp,'minecraft_colocar_bloco',{'nome':name},
                     {'ok':True,'receipt_id':receipt,'status':'success','output':json.dumps({'placed':placed})},'')

    def test_station_is_remembered_offered_and_forgotten_by_fact(self):
        from core import minecraft_cognition as cognition,minecraft_stations as stations
        goal='Minecraft: fabrique um arco.';cp=agent.initial(goal,agent.targets(goal))
        cp['session_id']='s1';cp['target']={'host':'fixture','port':37837}
        self.place(cp,'crafting_table',{'x':10,'y':64,'z':0},'r1')
        far=stations.conferir_e_listar(world(position={'x':0,'y':64,'z':0}),None)  # outra tarefa: lembrada pelo banco
        self.assertEqual([(s['nome'],s['posicao']) for s in far],[('crafting_table',{'x':10,'y':64,'z':0})])
        options=cognition.action_options(None,world(position={'x':0,'y':64,'z':0}),stations=far)
        self.assertEqual(options['ir_a_minha:crafting_table']['arguments'],{'x':10,'y':64,'z':0,'distancia':3})
        self.assertNotIn('recolher:crafting_table',options)
        # De perto: recolher pela coordenada, e colocar outra mostra que ela já tem uma.
        near_state=world(position={'x':9,'y':64,'z':0},inventory=[{'name':'crafting_table','count':1}])
        seen={'arredores':{'crafting_table':{'mais_proximo':{'x':10,'y':64,'z':0},'distancia':1.7}}}
        near=stations.conferir_e_listar(near_state,seen)
        options=cognition.action_options(seen,near_state,stations=near)
        self.assertEqual((options['recolher:crafting_table']['tool'],options['recolher:crafting_table']['arguments']),
                         ('minecraft_minerar',{'x':10,'y':64,'z':0,'esperado':'crafting_table'}))  # a ponte confere o tipo
        self.assertIn('você já tem uma crafting_table sua em (10,64,0)',options['colocar:crafting_table']['effect'])
        self.assertIn('minhas_estacoes',cognition.decision_view({'minhas_estacoes':near}))  # não some na visão curta
        # Recolhida (ou quebrada por outro): de perto, numa percepção lida, ela não aparece mais e é esquecida.
        read={'arredores':{'stone':{'mais_proximo':{'x':9,'y':63,'z':0},'distancia':1.0}}}
        self.assertEqual(len(stations.conferir_e_listar(near_state,{'arredores':{}})),1)  # percepção vazia: não lida
        self.assertEqual(stations.conferir_e_listar(near_state,read),[])
        # Longe (chunk pode não estar carregado), não se afirma nada; a 2 blocos, sim.
        self.place(cp,'furnace',{'x':40,'y':64,'z':0},'r3')
        self.assertEqual(len(stations.conferir_e_listar(world(position={'x':0,'y':64,'z':0}),read)),1)
        self.assertEqual(stations.conferir_e_listar(world(position={'x':38,'y':64,'z':0}),read),[])
        # Fronteira de chunk (revisão Codex): a 1,6 bloco mas no chunk vizinho, pode não ter carregado: não se afirma nada.
        self.place(cp,'furnace',{'x':16,'y':64,'z':0},'r7')
        self.assertEqual([s['posicao']['x'] for s in stations.conferir_e_listar(world(position={'x':15,'y':64,'z':0}),read)],[16])
        # Dimensão: outra não vê; desconhecida não registra nem lista.
        self.place(cp,'furnace',{'x':50,'y':64,'z':0},'r5')
        self.assertEqual(stations.conferir_e_listar(world(dimension='the_nether',position={'x':50,'y':64,'z':0}),None),[])
        self.assertEqual(stations.conferir_e_listar(world(dimension=None,position={'x':50,'y':64,'z':0}),None),[])
        stations.registrar_colocacao(cp['target'],{'name':'furnace','position':{'x':60,'y':64,'z':0},'dimension':None},'r6')
        self.assertEqual([s['posicao']['x'] for s in stations.conferir_e_listar(world(position={'x':60,'y':64,'z':0}),None)],[50,16])
        # Outro servidor não vê as estações deste.
        self.place(cp,'furnace',{'x':30,'y':64,'z':0},'r4')
        self.assertEqual(stations.conferir_e_listar(world(host='outro',position={'x':30,'y':64,'z':0}),None),[])

    def test_known_player_is_shown_by_name_and_kept_in_short_view(self):
        # 30/10 (pedido humano): ATO no jogo é o Gustavo; a visão diz quem é quem.
        from core import minecraft_cognition as cognition
        from social import people
        p=people.identificar('Gustavo','minecraft','ATO');people.definir_papel(p['id'],'humano que dá as tarefas')
        self.assertEqual(people.por_canal('minecraft'),{'ATO':'Gustavo — humano que dá as tarefas'})
        self.assertEqual(people.por_canal('discord'),{})
        self.assertIn('jogadores_conhecidos',cognition.decision_view({'jogadores_conhecidos':people.por_canal('minecraft')}))

    def test_loaded_furnace_is_not_offered_for_recovery(self):
        from core import minecraft_cognition as cognition
        st=[{'nome':'furnace','posicao':{'x':1,'y':64,'z':0},'distancia':1.5,'colocada_em':'2026-10-30T10:00'}]
        run={'position':{'x':1,'y':64,'z':0},'input':'salmon','expectedOutput':'cooked_salmon','remaining':6,
             'count':6,'fuel':'coal','fuelCount':1,'depositedAt':'2000-01-01T00:00:00.000Z'}
        state=world(position={'x':0,'y':64,'z':0},furnaceRuns=[run])
        self.assertNotIn('recolher:furnace',cognition.action_options(None,state,stations=st))
        self.assertIn('recolher:furnace',cognition.action_options(None,world(position={'x':0,'y':64,'z':0}),stations=st))


class GiveItem(unittest.TestCase):
    """30/10 (pedido humano): 'lilith você pode me dar um pouco de pão' — ela não tinha como entregar item."""
    def test_give_option_for_nearby_player_and_her_written_item(self):
        from core import minecraft_cognition as cognition
        state=world(username='LilithMC',position={'x':0,'y':64,'z':0},inventory=[{'name':'bread','count':12}],
                    nearbyEntities=[{'username':'ATO','name':'player','type':'player','distance':5.2,'id':7},
                                    {'username':'LilithMC','distance':0},{'username':'Longe','distance':40}])
        options=cognition.action_options(None,state)
        self.assertEqual(sorted(k for k in options if k.startswith('entregar_a:')),['entregar_a:ATO'])
        give=options['entregar_a:ATO']
        self.assertEqual((give['tool'],give['arguments']),('minecraft_jogar_item',{'para':'ATO'}))
        self.assertEqual(cognition.option_arguments(give,json.dumps({'opcao':'entregar_a:ATO','comentario':'Vou dar pão.',
                         'consulta':'bread','quantidade':3})),{'nome':'bread','quantidade':3,'para':'ATO'})
        self.assertEqual(cognition.option_arguments(give,json.dumps({'consulta':'Bread'}))['quantidade'],1)  # padrão 1
        with self.assertRaises(ValueError):cognition.option_arguments(give,json.dumps({'consulta':'bread','quantidade':0}))
        schema,ask=cognition.text_request(give)
        self.assertIn('quantidade',schema['properties']);self.assertIn('ID do item',ask)
        # Sem ninguém por perto, a opção não aparece.
        self.assertFalse(any(k.startswith('entregar_a:') for k in cognition.action_options(None,world(username='LilithMC'))))


class TrackAndExplore(unittest.TestCase):
    """30/10 (pedido humano): rastrear o alvo mesmo longe e, sem alvo, andar numa direção até encontrar."""
    def test_far_target_is_chased_and_none_means_explore(self):
        from core import minecraft_cognition as cognition
        def opts(*entities):
            return cognition.action_options(None,world(position={'x':0,'y':64,'z':0},nearbyEntities=list(entities)),hunt={'string'})
        spider=lambda d,**k:{'id':9,'name':'spider','type':'mob','distance':d,'position':{'x':int(d),'y':64,'z':0},**k}
        near=opts(spider(10))
        self.assertIn('cacar:spider',near);self.assertFalse(any(k.startswith(('explorar:','ir_atras:')) for k in near))
        deep=opts({**spider(18),'position':{'x':1,'y':46,'z':0}})  # 30/10: presa 18 abaixo, dentro da rocha
        self.assertIn('está 18 blocos abaixo de você',deep['cacar:spider']['effect'])
        self.assertNotIn('blocos abaixo',near['cacar:spider']['effect'])
        far=opts(spider(41,longe=True))
        self.assertEqual(far['ir_atras:spider']['arguments'],{'x':41,'y':64,'z':0,'distancia':6})
        self.assertFalse(any(k.startswith('explorar:') for k in far))
        none=opts({'id':3,'name':'bat','type':'mob','distance':5,'position':{'x':5,'y':64,'z':0}})
        self.assertEqual(sorted(k for k in none if k.startswith('explorar:')),
                         ['explorar:leste','explorar:norte','explorar:oeste','explorar:sul'])
        self.assertEqual(none['explorar:norte']['arguments'],{'direcao':'norte','procurar':['cave_spider','spider'],'blocos':40})
        # Por espécie (revisão Codex): vaca perto não esconde a aranha longe.
        cow={'id':4,'name':'cow','type':'mob','distance':10,'position':{'x':10,'y':64,'z':0}}
        mixed=cognition.action_options(None,world(position={'x':0,'y':64,'z':0},nearbyEntities=[cow,spider(41,longe=True)]),
                                       hunt={'beef','string'})
        self.assertIn('cacar:cow',mixed);self.assertIn('ir_atras:spider',mixed)
        self.assertFalse(any(k.startswith('explorar:') for k in mixed))
        # Sem alvo procurado no objetivo (hunt=True: matar qualquer), não oferece explorar.
        self.assertFalse(any(k.startswith('explorar:') for k in cognition.action_options(None,world(),hunt=True)))


class Surplus(unittest.TestCase):
    """30/10 (pedido humano): sem coletar o que já sobra mais de 10 além do necessário, por enquanto."""
    def test_surplus_hides_collect_and_counts_recipe_needs(self):
        from core import minecraft_cognition as cognition
        goal=agent.targets('Minecraft: fabrique um arco.')
        stone={'arredores':{'stone':{'mais_proximo':{'x':1,'y':63,'z':0},'distancia':1.0,'veio':4,'ferramenta_ok':True}}}
        full=world(inventory=[{'name':'cobblestone','count':331},{'name':'stone_pickaxe','count':1}])
        self.assertEqual(cognition.surplus(full,stone,None,goal)['cobblestone'],{'tem':331,'precisa':0})
        self.assertNotIn('coletar:stone',cognition.action_options(stone,full,goal=goal))
        few=world(inventory=[{'name':'cobblestone','count':5},{'name':'stone_pickaxe','count':1}])
        self.assertIn('coletar:stone',cognition.action_options(stone,few,goal=goal))
        # A receita observada conta como necessário: forno pede 8; 15 ainda não passa de 8+10.
        furnace={**stone,'receitas':[{'item':'furnace','variantes':[{'ingredientes':[{'nome':'cobblestone','precisa':8,'tem':15}]}]}]}
        some=world(inventory=[{'name':'cobblestone','count':15}])
        self.assertNotIn('cobblestone',cognition.surplus(some,furnace,None,goal))
        self.assertIn('cobblestone',cognition.surplus(world(inventory=[{'name':'cobblestone','count':19}]),furnace,None,goal))
        # Revisão Codex: necessidade desconhecida não é zero — diamante sem receita vista nem meta não trava.
        self.assertNotIn('diamond',cognition.surplus(world(inventory=[{'name':'diamond','count':11}]),None,None,goal))
        self.assertIn('diamond',cognition.surplus(world(inventory=[{'name':'diamond','count':40}]),None,{'item':'diamond','total':24},goal))
        # Grupo do objetivo (30 carnes): 20 beef cru é necessário, não excesso.
        meat=agent.targets('Minecraft: consiga 30 carnes assadas de animais, iguais ou diferentes.')
        self.assertNotIn('beef',cognition.surplus(world(inventory=[{'name':'beef','count':20}]),None,None,meat))
        # Bloco que solta outro item e nome com maiúsculas/espaços também são recusados.
        extra={'dirt':{'tem':331,'precisa':0},'cobblestone':{'tem':331,'precisa':0}}
        self.assertIn('331 dirt',cognition.surplus_refusal('grass_block',extra))
        self.assertIn('331 cobblestone',cognition.surplus_refusal(' STONE ',extra))
        self.assertIsNone(cognition.surplus_refusal('oak_log',extra))
        # Releitura sem percepção usa as necessidades vistas na decisão (known).
        self.assertNotIn('cobblestone',cognition.surplus(some,None,None,goal,known={'cobblestone':8}))


class NoPickaxe(unittest.TestCase):
    """30/10 (pedido humano): as picaretas quebraram embaixo da terra; avisar e dizer o que dá para fazer."""
    def test_notice_and_what_she_can_craft(self):
        from core import minecraft_cognition as cognition
        hers=[{'name':'cobblestone','count':331},{'name':'stick','count':5},{'name':'crafting_table','count':1}]
        notice=cognition.no_pickaxe(world(inventory=hers))
        self.assertIn('sem picareta',notice['aviso'])
        self.assertIn('stone_pickaxe = 3 cobblestone + 2 stick',notice['pode_fazer'])
        self.assertIn('1 crafting_table',notice['pode_fazer'])
        self.assertIsNone(cognition.no_pickaxe(world(inventory=[*hers,{'name':'iron_pickaxe','count':1}])))
        self.assertNotIn('pode_fazer',cognition.no_pickaxe(world(inventory=[{'name':'stick','count':1}])))
        planks=cognition.no_pickaxe(world(inventory=[{'name':'birch_planks','count':4},{'name':'stick','count':2}]))
        self.assertIn('wooden_pickaxe = 3 planks',planks['pode_fazer'])
        self.assertIn('sem_picareta',cognition.decision_view({'sem_picareta':notice}))

class ReflectiveQuestion(unittest.TestCase):
    """30/10: "teste de velocidade depois de trocar…: como foi fabricar o arco hoje?" virou tarefa de fabricar arco."""
    QUESTION=('Claude (condutor), teste rápido de velocidade depois de trocar para 33 camadas na GPU: '
              'em duas ou três frases, como foi fabricar o arco hoje?')

    def test_question_about_the_past_is_conversation(self):
        self.assertEqual(len(task_state.decompor(self.QUESTION)),1)  # "depois de" marca tempo, não etapa seguinte
        self.assertFalse(task_state.parece_tarefa(self.QUESTION))
        self.assertFalse(task_state.parece_tarefa('o que você achou de fabricar o arco hoje?'))
        self.assertFalse(task_state.parece_tarefa('você gostou de fazer a bancada?'))
        # Pedidos continuam sendo tarefa: em forma de pergunta, com pergunta depois, com o marcador dentro.
        self.assertFalse(task_state.parece_tarefa(self.QUESTION.replace('GPU:','GPU;')))  # revisão Codex: ponto e vírgula
        self.assertFalse(task_state.parece_tarefa('Lilith, como foi a caçada?'))
        self.assertFalse(task_state.parece_tarefa('Como foi fabricar o arco hoje, Lilith?'))  # revisão Codex: vocativo no fim
        self.assertFalse(task_state.parece_tarefa('como foi caçar a vaca e a aranha?'))
        self.assertTrue(task_state.parece_tarefa('Como foi fabricar o arco e pode fabricar outro?'))  # pedido depois
        self.assertTrue(task_state.parece_tarefa('Como foi fabricar o arco e fabrique outro?'))
        self.assertTrue(task_state.parece_tarefa('Como foi fabricar o arco e por favor fabrique outro?'))
        self.assertFalse(task_state.parece_tarefa('Como foi fabricar o arco e o que você achou de fazer a bancada?'))
        self.assertFalse(task_state.parece_tarefa('Como foi fabricar o arco e fazer a bancada?'))  # infinitivo: ainda pergunta
        for request in ('pode fabricar um arco?','faça o arco. como foi?','Pode fabricar um arco como foi combinado?',
                        'Pode criar um arquivo com o que você aprendeu?','Pode fabricar um arco, como foi combinado?',
                        'Fabrique um arco, como foi combinado?','Crie um arquivo e depois me conte: como foi?'):
            self.assertTrue(task_state.parece_tarefa(request),request)
        self.assertEqual(task_state.decompor('abra o forno e depois pegue as carnes'),['abra o forno','pegue as carnes'])
        self.assertEqual(len(task_state.decompor('pegue a madeira, depois disso faça a bancada')),2)
        self.assertEqual(len(task_state.decompor('Construa um abrigo no Minecraft e depois de terminar me avise.')),2)

    def test_question_does_not_reactivate_or_extend_a_paused_task(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','reflective-question','')
        task=task_state.iniciar_ou_continuar(key,'Minecraft: fabrique um arco')
        self.assertEqual(task.status,'active');steps=[e['texto'] for e in task.etapas]
        task_state.pausar(key);self.assertEqual(task_state.carregar_ultimo(key).status,'paused')
        for question in (self.QUESTION,'Agora, como foi fabricar o arco hoje?'):
            self.assertIsNone(task_state.iniciar_ou_continuar(key,question))
            after=task_state.carregar_ultimo(key)
            self.assertEqual(after.status,'paused');self.assertEqual([e['texto'] for e in after.etapas],steps)

if __name__=='__main__':unittest.main()
