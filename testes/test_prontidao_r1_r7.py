"""Probes R2–R5/R7 permanentes; transportes simulados, SQLite temporário."""
import asyncio
import os
if os.environ.get('HOSHINO_TEST_OFFLINE')!='1':
    raise SystemExit('Use testes/executar_isolado.py; este grupo exige isolamento de bancos/serviços.')
import json
import socket
import sqlite3
import tempfile
import threading
import subprocess
import shutil
import io
import wave
import sys
import unittest
from contextlib import ExitStack, closing, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import config
import main
from alistair_runner import Alistair, ActionUncertain, recall_history, OPERATIONAL_RULES
from core import audio_service, diagnostics, interentity as bus, job_bus, speech_stream, resource_manager
from core import history, task_state, intent
from memory.sqlite import init_db
from memory import knowledge_store as saber
from tools import minecraft, minecraft_launcher
from core import prompting


class PromptBudget(unittest.TestCase):
    def test_game_chat_can_be_answered_without_replacing_the_persistent_objective(self):
        from core import minecraft_agent,action_commentary
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[{'content':'{"opcao":"outra","comentario":"Responder sem abandonar o forno."}'},
            {'tool_calls':[{'function':{'name':'minecraft_chat','arguments':{'texto':'Oi! Continuo preparando o forno.'}}}]}])
        task=SimpleNamespace(id='game-chat',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);original=cp['goal_hash']
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC',
               'recentChat':[{'id':'s:1','sessionId':'s','username':'Gustavo','message':'Oi!'}]}
        async def probe(*_,**callbacks):
            self.assertIn('minecraft_chat',callbacks['allowed'])
            for text in ('/give @s diamond 64','oi\n/gamemode creative','x'*241,'😀'*128+'/gamemode creative','§oi','\ud800'):
                with self.subTest(text=text):self.assertTrue(callbacks['validate']('minecraft_chat',{'texto':text}))
            self.assertFalse(callbacks['validate']('minecraft_chat',{'texto':'Oi!'}))
            action=await callbacks['ask'](state,cp)
            self.assertEqual(action['tool'],'minecraft_chat')
            self.assertEqual(action['arguments']['texto'],'Oi! Continuo preparando o forno.')
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),\
             patch.object(task_state,'pausar'),patch.object(action_commentary,'record_deliberation'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','chat','')))
        v=json.loads(app.chamar_modelo.call_args_list[0].args[0][-1]['content'])
        self.assertEqual(v['chat_do_minecraft'][0]['username'],'Gustavo')
        self.assertIn('s:1',cp['minecraft_chat_presented']);self.assertEqual(cp['goal_hash'],original)

    def test_pending_plan_item_is_examined_and_a_met_subgoal_gives_up_its_slot(self):
        # 28/10: plano pendente "ter stone_pickaxe" e meta wooden_pickaxe já cumprida; a picareta de pedra nunca aparecia.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'opcao':'estado','comentario':'Ver.'})})
        task=SimpleNamespace(id='planitem',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique e equipe um kit completo de ferro.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);cp['steps']=1
        cp['subgoal']={'item':'wooden_pickaxe','total':1,'note':'x','author':'lilith','selected_step':0}
        # 28/10: o passo dela usava 'equipado', não 'ter'; também conta como item a obter.
        cp.update(plan_steps=[{'passo':'Fazer picareta de pedra','feito_quando':{'tipo':'equipado','item':'stone_pickaxe','quantidade':1}}],plan_steps_step=1)
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC',
               'inventory':[{'name':'wooden_pickaxe','count':1},{'name':'cobblestone','count':8},{'name':'stick','count':2}]}
        asked=[]
        def dispatch(tool,args,*rest):
            asked.append(list(args.get('itens') or []));return {'output':json.dumps(state|{'percepcao':{}})}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp);return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',side_effect=dispatch),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','planitem','')))
        first=next(a for a in asked if a)
        self.assertEqual(first[0],'stone_pickaxe');self.assertNotIn('wooden_pickaxe',first[:3])

    def test_tool_ingredients_get_a_slot_even_when_kit_ingredients_fill_the_list(self):
        # 28/10: 6 vagas tomadas por cobblestone/peças/iron_ingot; stick nunca entrava e a picareta nunca era fabricável.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'opcao':'estado','comentario':'Ver.'})})
        task=SimpleNamespace(id='slots',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique e equipe um kit completo de ferro.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);cp['steps']=1
        cp['subgoal']={'item':'cobblestone','total':64,'note':'x','author':'lilith','selected_step':0}
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC',
               'inventory':[{'name':'oak_planks','count':8}]}
        def recipe(item,ingredients):
            return {'item':item,'bancada_a_4_blocos':True,'variantes':[{'exige_bancada':True,
                    'ingredientes':[{'nome':n,'precisa':q,'tem':0} for n,q in ingredients]}]}
        recipes={'iron_helmet':recipe('iron_helmet',[('iron_ingot',5)]),'iron_chestplate':recipe('iron_chestplate',[('iron_ingot',8)]),
                 'wooden_pickaxe':recipe('wooden_pickaxe',[('oak_planks',3),('stick',2)]),'stick':recipe('stick',[('oak_planks',2)]),
                 'iron_ingot':recipe('iron_ingot',[('iron_ore',1)]),'iron_leggings':recipe('iron_leggings',[('iron_ingot',7)])}
        asked=[]
        def dispatch(tool,args,*rest):
            asked.append(list(args.get('itens') or []))
            perception={'arredores':{'stone':{'mais_proximo':{'x':1,'y':60,'z':1},'distancia':3,'ferramenta_ok':False,
                          'ferramentas':['wooden_pickaxe','stone_pickaxe']}},
                        'receitas':[recipes[i] for i in args.get('itens') or [] if i in recipes]}
            return {'output':json.dumps(state|{'percepcao':perception})}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp);return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',side_effect=dispatch),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','slots','')))
        self.assertTrue(any('stick' in a and 'wooden_pickaxe' in a and len(a)<=6 for a in asked),asked)

    def test_missing_harvest_tool_and_its_ingredients_become_craft_options(self):
        # 27/10 21:41: sem picareta, a meta iron_ore estava bloqueada e stone_pickaxe/stick nunca eram opções.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'opcao':'estado','comentario':'Ver.'})})
        task=SimpleNamespace(id='tool',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        cp['subgoal']={'item':'iron_ore','total':10,'note':'x','author':'lilith','selected_step':0}
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC',
               'inventory':[{'name':'oak_planks','count':195},{'name':'cobblestone','count':100}]}
        recipes={'stone_pickaxe':{'item':'stone_pickaxe','bancada_a_4_blocos':True,'variantes':[{'exige_bancada':True,
                    'ingredientes':[{'nome':'cobblestone','precisa':3,'tem':100},{'nome':'stick','precisa':2,'tem':0}]}]},
                 'stick':{'item':'stick','bancada_a_4_blocos':True,'variantes':[{'exige_bancada':False,
                    'ingredientes':[{'nome':'oak_planks','precisa':2,'tem':195}]}]}}
        asked=[]
        def dispatch(tool,args,*rest):
            asked.append(list(args.get('itens') or []))
            perception={'arredores':{'iron_ore':{'mais_proximo':{'x':1,'y':55,'z':1},'distancia':12,'ferramenta_ok':False,
                          'ferramentas':['stone_pickaxe','iron_pickaxe','diamond_pickaxe']}},
                        'receitas':[recipes[i] for i in args.get('itens') or [] if i in recipes]}
            return {'output':json.dumps(state|{'percepcao':perception})}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp);return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',side_effect=dispatch),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','tool','')))
        self.assertIn('stone_pickaxe',asked[-1]);self.assertIn('stick',asked[-1])
        self.assertLessEqual(len(asked[-1]),6)
        view=json.loads(app.chamar_modelo.call_args.args[0][-1]['content'])
        self.assertIn('fabricar:stick',view['possibilidades'])

    def test_barrier_reflection_divergence_furnace_and_danger_reach_her_decision(self):
        # 27/10: explicar o erro do plano (DEPS/Reflexion), ver o forno real, perigo e divergência de comentário.
        from core import minecraft_agent,action_commentary
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[
            {'content':json.dumps({'opcao':'coletar:dark_oak_log','comentario':'Minerar coal_ore para o forno.',
                                   'explicacao':'Eu achava que havia lingotes no forno, mas ele estava vazio.'})},
            {'content':json.dumps({'opcao':'falar_no_chat','comentario':'Perguntar.','consulta':'Humano, onde tem ferro?'})}])
        task=SimpleNamespace(id='reflect',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        cp['barrier']={'level':1,'step':0,'reason':'6 decisões'}
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC',
               'health':7,'food':20,'nearbyEntities':[{'name':'skeleton','distance':9,'lineOfSight':True}]}
        perception={'arredores':{'furnace':{'mais_proximo':{'x':1,'y':64,'z':1},'distancia':2.5},
                                 'dark_oak_log':{'mais_proximo':{'x':2,'y':64,'z':2},'distancia':3,'ferramenta_ok':True}}}
        def dispatch(tool,args,*rest):
            if tool=='minecraft_forno':return {'output':json.dumps({'position':{'x':1,'y':64,'z':1},'input':None,'fuel':None,'output':None,'owned_run':None})}
            return {'output':json.dumps(state|{'percepcao':perception})}
        async def probe(*_,**callbacks):
            first=await callbacks['ask'](state,cp)
            self.assertEqual(first['tool'],'minecraft_coletar')
            cp['barrier']['level']=2
            second=await callbacks['ask'](state,cp)
            self.assertEqual((second['tool'],second['arguments']),('minecraft_chat',{'texto':'Humano, onde tem ferro?'}))
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',side_effect=dispatch),\
             patch.object(action_commentary,'record_deliberation'),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','reflect','')))
        first,second=[json.loads(c.args[0][-1]['content']) for c in app.chamar_modelo.call_args_list]
        self.assertIn('explicacao',first['barreira']['o_que_fazer']);self.assertIn('vida baixa',first['perigo']['alertas'][0])
        self.assertEqual(first['percepcao']['forno_proximo']['output'],None)
        self.assertIn('chat do jogo',second['barreira']['o_que_fazer'])
        self.assertIn('estava vazio',second['minhas_reflexoes'][0]['texto'])
        self.assertIn('coal_ore',second['retorno_escolha'])

    def test_research_learning_and_recall_go_through_her_decision(self):
        # 27/10: pesquisa direta, aprendizado confirmado por recibo e recuperação do que ela guardou.
        from core import minecraft_agent
        from memory import knowledge_store
        learned={'nome':'Fundir ferro','passos':['8 iron_ore + 1 coal no forno','Retirar depois'],'resultado_esperado':'8 iron_ingot'}
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[
            {'content':json.dumps({'opcao':'pesquisar','comentario':'Ver fundição.','consulta':'minecraft fornalha ferro'})},
            {'content':json.dumps({'opcao':'registrar_aprendizado','comentario':'Guardar.','aprendizado':learned})},
            {'content':json.dumps({'opcao':'pesquisar','comentario':'Sem consulta.'})},
            {'content':json.dumps({})}])  # o pedido do texto também volta vazio: recusa
        task=SimpleNamespace(id='learn',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        cp['steps']=2;cp['trajectory']=[{'step':1,'tool':'minecraft_forno','status':'success','receipt_id':'tool-f',
                                         'inventory_delta':{'iron_ingot':8}}]
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC'}
        perception={'arredores':{'coal_ore':{'ferramenta_ok':False,'ferramentas':['wooden_pickaxe']}}}
        async def probe(*_,**callbacks):
            self.assertIn('registrar_procedimento',callbacks['allowed'])
            action=await callbacks['ask'](state,cp)
            self.assertEqual((action['tool'],action['arguments']),('web_search',{'query':'minecraft fornalha ferro'}))
            action=await callbacks['ask'](state,cp)
            self.assertEqual(action['tool'],'registrar_procedimento');self.assertIn('tool-f',action['arguments']['notas'])
            with self.assertRaisesRegex(minecraft_agent.DecisionRejected,'consulta'):await callbacks['ask'](state,cp)
            return {'status':'paused','reason':'fixture','used':[]}
        recall='Procedimentos relevantes:\n[p1] Fundir ferro\n  1. 8 iron_ore + 1 coal no forno'
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state|{'percepcao':perception})}),\
             patch.object(knowledge_store,'consultar_procedimento',return_value=recall) as lookup,\
             patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','learn','')))
        view=json.loads(app.chamar_modelo.call_args_list[0].args[0][-1]['content'])
        self.assertEqual(view['meu_conhecimento'],recall);self.assertIn('minecraft',lookup.call_args.args[0])
        self.assertEqual(view['coleta_sem_ferramenta'],{'coal_ore':['wooden_pickaxe']})
        self.assertIn('registrar_aprendizado',view['possibilidades'])

    def test_survival_reflexes_and_death_reach_her_decision_and_the_human_once(self):
        # 28/10: pedido humano — aviso com tudo o que aconteceu quando um reflexo dispara ou ela morre.
        from core import minecraft_agent
        from social import channels
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'opcao':'estado','comentario':'Ver.'})})
        task=SimpleNamespace(id='reflex',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        reflexes=[{'id':'s:reflex:1','tipo':'sufocamento','posicao':{'x':1,'y':49,'z':2},'vida_antes':12,'vida_depois':14,
                   'detalhe':'cabeça dentro de gravel','acao':'cavei gravel acima;'},
                  {'id':'s:reflex:2','tipo':'morte','causa_provavel':'sufocamento','posicao':{'x':1,'y':49,'z':2},
                   'itens_que_cairam':[{'name':'iron_ore','count':10}],'itens_somem_em':'2026-10-28T05:48:04Z'}]
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC','reflexes':reflexes}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp);await callbacks['ask'](state,cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),\
             patch.object(channels,'enviar') as sent,patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,canal='local',chave_conversa=('local','claude_mc','p')))
        self.assertEqual(sent.call_count,2)  # uma vez por evento, não a cada decisão
        self.assertIn('cavei gravel',sent.call_args_list[0].args[2]);self.assertIn('10 iron_ore',sent.call_args_list[1].args[2])
        self.assertEqual(sent.call_args_list[0].args[:2],('local','claude_mc'))
        first,second=[json.loads(c.args[0][-1]['content']) for c in app.chamar_modelo.call_args_list]
        self.assertEqual(len(first['aviso_sobrevivencia']),2);self.assertNotIn('aviso_sobrevivencia',second)

    def test_option_text_left_blank_is_asked_once_with_a_required_field(self):
        # 28/10: falar_no_chat escolhido três vezes sem texto; cada vez a decisão era recusada.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[
            {'content':json.dumps({'opcao':'falar_no_chat','comentario':'Vou perguntar.'})},
            {'content':json.dumps({'consulta':'ATO, onde tem ferro por aqui?'})},
            {'content':json.dumps({'opcao':'pesquisar','comentario':'Pesquisar.'})},
            {'content':json.dumps({})}])
        task=SimpleNamespace(id='text',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC'}
        async def probe(*_,**callbacks):
            action=await callbacks['ask'](state,cp)
            self.assertEqual((action['tool'],action['arguments']),('minecraft_chat',{'texto':'ATO, onde tem ferro por aqui?'}))
            with self.assertRaises(minecraft_agent.DecisionRejected):await callbacks['ask'](state,cp)  # segue sem texto: recusa
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','text','')))
        follow=app.chamar_modelo.call_args_list[1]
        self.assertEqual(follow.kwargs['formato']['required'],['consulta'])
        self.assertIn('chat do jogo',follow.args[0][-1]['content'])

    def test_exhausted_reasoning_concludes_from_its_own_thinking(self):
        # 28/10: 8192 tokens de raciocínio (~5,5 min) esgotavam e a decisão era descartada.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        exhausted=RuntimeError('LLM_STREAM_INCOMPLETO: limite de geração atingido; resposta não concluída.')
        exhausted.partial_thinking='... então o melhor agora é pesquisar como usar a fornalha.'
        bare=RuntimeError('LLM_STREAM_INCOMPLETO: limite de geração atingido; resposta não concluída.')
        app.chamar_modelo=AsyncMock(side_effect=[exhausted,
            {'content':json.dumps({'opcao':'pesquisar','comentario':'Pesquisar.','consulta':'fornalha minecraft'})},bare])
        task=SimpleNamespace(id='budget',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC'}
        async def probe(*_,**callbacks):
            action=await callbacks['ask'](state,cp)
            self.assertEqual((action['tool'],action['arguments']),('web_search',{'query':'fornalha minecraft'}))
            with self.assertRaises(minecraft_agent.DecisionRejected):await callbacks['ask'](state,cp)  # sem raciocínio: recusa
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),patch.object(task_state,'pausar'),\
             patch.object(main.config,'THINKING',True):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','budget','')))
        first,follow=app.chamar_modelo.call_args_list[:2]
        self.assertEqual(first.kwargs['limite_saida'],4096)
        self.assertEqual((follow.kwargs['think_override'],follow.kwargs['forcar_sem_pensar']),(False,True))
        self.assertIn('pesquisar como usar a fornalha',follow.args[0][-2]['content'])

    def test_exhausted_subgoal_reasoning_uses_decision_budget_and_concludes(self):
        # 30/10: a meta intermediária ficou com 8192 tokens e, esgotada, era jogada fora.
        from core import minecraft_agent, minecraft_cognition
        app=object.__new__(main.InterfaceHoshino)
        exhausted=RuntimeError('LLM_STREAM_INCOMPLETO: limite de geração atingido; resposta não concluída.')
        exhausted.partial_thinking='... a meta certa agora é juntar pedra para o forno.'
        app.chamar_modelo=AsyncMock(side_effect=[exhausted,
            {'content':json.dumps({'item':'acao_direta','total':0,'note':'Juntar pedra.'})},
            {'content':json.dumps({'opcao':'pesquisar','comentario':'Pesquisar.','consulta':'fornalha minecraft'})}])
        task=SimpleNamespace(id='goal',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);cp['steps']=3
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC'}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),patch.object(task_state,'pausar'),\
             patch.object(minecraft_cognition,'subgoal_candidates',return_value=['cobblestone']),\
             patch.object(main.config,'THINKING',True):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','goal','')))
        goal,closing=app.chamar_modelo.call_args_list[:2]
        self.assertEqual(goal.kwargs['limite_saida'],4096)
        self.assertEqual((closing.kwargs['think_override'],closing.kwargs['forcar_sem_pensar']),(False,True))
        self.assertIn('juntar pedra para o forno',closing.args[0][-2]['content'])
        self.assertEqual(closing.kwargs['limite_saida'],300);self.assertEqual(closing.kwargs['formato'],goal.kwargs['formato'])
        self.assertEqual(cp['subgoal_review_step'],3);self.assertNotIn('subgoal_feedback',cp)  # revisão Codex: meta aceita

    def test_chat_arriving_during_a_long_subgoal_reaches_the_choice(self):
        # 30/10: o pedido de pão chegou 30 s depois do início; a meta levou 3 min e a escolha usou o chat antigo.
        from core import minecraft_agent, minecraft_cognition
        app=object.__new__(main.InterfaceHoshino);clock=[0.0]
        async def model(messages,*_,**kw):
            if kw.get('formato',{}).get('required')==['item','total','note']:
                clock[0]=30.0;return {'content':json.dumps({'item':'acao_direta','total':0,'note':'Seguir.'})}
            return {'content':json.dumps({'opcao':'estado','comentario':'Ver.'})}
        app.chamar_modelo=AsyncMock(side_effect=model)
        task=SimpleNamespace(id='chat',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);cp['steps']=3
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC','recentChat':[]}
        said={'id':'s:chat:1','seq':1,'sessionId':'s','username':'ATO','message':'me dá um pouco de pão','at':'2026-10-30T18:40:47Z'}
        fresh={**state,'recentChat':[said]}
        async def probe(*_,**callbacks):
            await callbacks['ask'](dict(state),cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(fresh)}),patch.object(task_state,'pausar'),\
             patch.object(minecraft_cognition,'subgoal_candidates',return_value=['cobblestone']),\
             patch.object(main.time,'monotonic',side_effect=lambda:clock[0]),patch.object(main.config,'THINKING',True):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','chat','')))
        choice=app.chamar_modelo.call_args_list[-1]
        self.assertIn('me dá um pouco de pão',choice.args[0][-1]['content'])

    def test_reply_in_chat_goes_with_the_chosen_action(self):
        # 30/10 (pedido humano): a resposta vem junto com a escolha; revisão Codex: pelo mesmo caminho do chat
        # (validação sem comandos do servidor + conferência de sessão antes do efeito).
        from core import minecraft_agent
        for reply,sent in (('Claro, ATO! Já vou te dar pão.',True),('/give @s diamond 64',False),('oi\n/gamemode creative',False)):
            app=object.__new__(main.InterfaceHoshino)
            app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'opcao':'estado','comentario':'Ver o estado.',
                'resposta_no_chat':reply})})
            app._executar_chamadas_da_etapa=AsyncMock(return_value=[(None,None,{'status':'success','output':'Mensagem enviada.',
                'receipt_id':'chat-1'})])
            task=SimpleNamespace(id='reply',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
            criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
            state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC'}
            async def probe(*_,**callbacks):
                action=await callbacks['ask'](state,cp)
                self.assertEqual(action['tool'],'minecraft_estado')  # a operação escolhida segue
                return {'status':'paused','reason':'fixture','used':[]}
            with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
                 patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),patch.object(task_state,'pausar'):
                asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','reply','')))
            chats=[c for c in app._executar_chamadas_da_etapa.call_args_list if c.args[0][0]['function']['name']=='minecraft_chat']
            if sent:
                self.assertEqual(chats[0].args[0][0]['function']['arguments'],{'texto':reply})
                self.assertTrue(callable(chats[0].kwargs['validar_antes']))  # sessão/destino conferidos antes de falar
                self.assertEqual(cp['chat_log'][-1]['quem'],'você')
            else:
                self.assertEqual(chats,[],reply)  # comando do servidor nunca sai
            self.assertIn('resposta_no_chat',app.chamar_modelo.call_args.kwargs['formato']['properties'])

    def test_surplus_collect_is_refused_also_through_the_catalog(self):
        # 30/10 (pedido humano): com 331 cobblestone e o arco não pedindo pedra, coletar pedra é recusado antes do efeito.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'opcao':'estado','comentario':'Ver.'})})
        task=SimpleNamespace(id='extra',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um arco.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        cp['session_id']='s';cp['target']={'host':'127.0.0.1','port':34993}
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC',
               'inventory':[{'name':'cobblestone','count':331},{'name':'oak_log','count':3}]}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp)
            refused=callbacks['validate']('minecraft_coletar',{'nome':'stone','quantidade':4})
            self.assertIn('você já tem 331 cobblestone',refused);self.assertIn('minecraft_minerar',refused)
            self.assertFalse(callbacks['validate']('minecraft_coletar',{'nome':'oak_log','quantidade':2}))  # 3 não sobra
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','extra','')))

    def test_structured_plan_is_kept_checked_and_receipts_skip_reconnections(self):
        # 27/10 18:20: plano só textual, sem conferência; reconexões e recusas tomavam a janela.
        from core import minecraft_agent
        plan=[{'passo':'Retirar lingotes','feito_quando':{'tipo':'ter','item':'iron_ingot','quantidade':8}}]
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[
            {'content':json.dumps({'opcao':'estado','comentario':'Conferir.','plano':plan})},
            {'content':json.dumps({'opcao':'estado','comentario':'De novo.','plano':[{'passo':'x','feito_quando':
                {'tipo':'perto','item':'iron_ore','quantidade':1}}]})},
            {'content':json.dumps({'opcao':'estado','comentario':'Manter.'})}])
        task=SimpleNamespace(id='plan',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        cp['events']=[{'tool':'minecraft_forno','status':'success','receipt_id':'f','output':'{}'},
                      {'tool':'minecraft_conectar','status':'success','receipt_id':'k','output':'ok'},
                      {'tool':None,'status':'rejected_before_effect','output':'Decisão recusada: raciocínio esgotado.'}]
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC',
               'inventory':[{'name':'iron_ingot','count':3}]}
        async def probe(*_,**callbacks):
            for _ in range(3):
                self.assertEqual((await callbacks['ask'](state,cp))['tool'],'minecraft_estado');cp['steps']+=1
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),\
             patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','plan','')))
        views=[json.loads(c.args[0][-1]['content']) for c in app.chamar_modelo.call_args_list]
        self.assertEqual([e['receipt_id'] for e in views[0]['ultimos_recibos']],['f'])
        self.assertIn('raciocínio esgotado',views[0]['ultima_recusa'])
        self.assertEqual(views[1]['meu_plano']['passos'][0]['cumprido'],False)
        self.assertEqual(views[1]['meu_plano']['proximo_pendente'],'Retirar lingotes')
        self.assertIn('Plano não registrado',views[2]['meu_plano']['retorno'])  # inválido não troca o plano
        self.assertEqual(cp['plan_steps'],plan)
        self.assertIn('plano',app.chamar_modelo.call_args_list[0].kwargs['formato']['properties'])

    def test_reasoning_that_exhausts_the_output_is_a_rejected_decision_not_a_pause(self):
        # 27/10 17:40 e 17:46: a decisão com raciocínio esgotou 4096 tokens e pausou a tarefa.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[
            RuntimeError('LLM_STREAM_INCOMPLETO: limite de geração atingido; resposta não concluída.'),
            RuntimeError('LLM_STREAM_INCOMPLETO: erro de protocolo/backend.')])
        task=SimpleNamespace(id='exhausted',objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':34993,'username':'HoshinoMC'}
        async def probe(*_,**callbacks):
            with self.assertRaisesRegex(minecraft_agent.DecisionRejected,'esgotou o limite de saída'):
                await callbacks['ask'](state,cp)
            with self.assertRaisesRegex(RuntimeError,'protocolo'):  # falha do backend continua pausando
                await callbacks['ask'](state,cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),\
             patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','exhausted','')))
        self.assertEqual(app.chamar_modelo.await_count,2)

    def test_disconnected_observed_option_uses_the_new_human_port_exactly(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'tool_calls':[{'function':{
            'name':'minecraft_escolher_acao','arguments':{'opcao':'conectar_destino'}}}]})
        task=SimpleNamespace(id='new-port-option',objetivo='Minecraft: conecte LilithMC ao mundo LAN em host 127.0.0.1, porta 34993, versão 1.16.5. Fabrique uma picareta de madeira.')
        criteria=minecraft_agent.targets(task.objetivo);self.assertIsNotNone(criteria);cp=minecraft_agent.initial(task.objetivo,criteria)
        async def probe(*_,**callbacks):
            result=await callbacks['ask']({'connected':False},cp)
            self.assertEqual(result['tool'],'minecraft_conectar')
            self.assertEqual(result['arguments'],{'host':'127.0.0.1','port':34993,'version':'1.16.5','username':'LilithMC'})
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','new-port','')))

    def test_minecraft_can_continue_to_placement_without_inventing_inventory_growth(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[{'content':json.dumps({'item':'crafting_table','total':1,'note':'Colocar a bancada que já tenho.'})},
            {'tool_calls':[{'function':{'name':'minecraft_escolher_acao','arguments':{'opcao':'colocar:crafting_table'}}}]}])
        task=SimpleNamespace(id='direct-subgoal',objetivo='Minecraft host 127.0.0.1 porta 40613: fabrique e coloque uma bancada.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);cp['steps']=3
        cp['subgoal']={'item':'crafting_table','total':1,'author':config.ENTIDADE_ID,'selected_step':0,'note':'x'}
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':40613,
               'inventory':[{'name':'crafting_table','count':1}],'heldItem':{'name':'crafting_table'}}
        async def probe(*_,**callbacks):
            result=await callbacks['ask'](state,cp)
            self.assertEqual(result['tool'],'minecraft_colocar_bloco');self.assertEqual(result['arguments'],{'nome':'crafting_table'})  # 28/10: item nomeado, equipado pela ponte
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state|{'percepcao':{'receitas':[{'item':'crafting_table'}]}})}),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','direct','')))
        self.assertEqual(cp['subgoal']['item'],'crafting_table')
        self.assertIn('já atende',cp['subgoal_feedback'])

    def test_minecraft_information_receipts_keep_the_fact_needed_for_next_decision(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]})
        task=SimpleNamespace(id='information-receipts',objetivo='Minecraft host 127.0.0.1 porta 40613: fabrique uma picareta de madeira.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        fact='FATO_NECESSARIO_PARA_DECISAO'
        cp['events']=[{'tool':tool,'status':'success','receipt_id':'info-'+str(i),'output':'prefix '*60+fact}
                      for i,tool in enumerate(('web_search','minecraft_procurar_bloco','minecraft_forno'))]
        async def probe(*_,**callbacks):
            await callbacks['ask']({'connected':False},cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','info','')))
        view=json.loads(app.chamar_modelo.call_args.args[0][-1]['content'])
        self.assertTrue(all(fact in e['output'] for e in view['ultimos_recibos']))

    def test_observed_options_keep_full_native_catalog_when_model_chooses_other(self):
        from core import minecraft_agent,action_commentary
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[
            {'content':'{"opcao":"outra","comentario":"PLANO: consultar a receita antes de agir."}'},
            {'tool_calls':[{'function':{'name':'minecraft_receitas','arguments':{'nome':'furnace'}}}]}])
        task=SimpleNamespace(id='free-catalog-choice',objetivo='Minecraft host 127.0.0.1 porta 40613: fabrique uma picareta de madeira.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':40613}
        async def probe(*_,**callbacks):
            result=await callbacks['ask'](state,cp)
            self.assertEqual(result['tool'],'minecraft_receitas');self.assertEqual(result['arguments'],{'nome':'furnace'})
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state)}),patch.object(task_state,'pausar'),\
             patch.object(action_commentary,'record_deliberation') as notes:
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','other','')))
        free={s['function']['name'] for s in app.chamar_modelo.call_args_list[1].args[1]}
        self.assertTrue({'minecraft_atacar','minecraft_forno','minecraft_craft','web_search'}<=free)
        native=app.chamar_modelo.call_args_list[1]
        with self.subTest('native_protocol'):
            self.assertIn('EXATAMENTE UMA chamada nativa',native.args[0][0]['content'])
            self.assertNotIn('Retorne somente o JSON',native.args[0][0]['content'])
            self.assertNotIn('formato',native.kwargs)
        with self.subTest('continuity_note'):
            self.assertEqual(cp.get('plan'),'PLANO: consultar a receita antes de agir.')
            self.assertTrue(any('consultar a receita' in str(c.args[1]) for c in notes.call_args_list))

    def test_model_selected_observed_option_maps_to_its_exact_operation(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({
            'opcao':'fabricar:oak_planks','comentario':'Transformar as tábuas necessárias.'})})
        task=SimpleNamespace(id='option-choice',objetivo='Minecraft host 127.0.0.1 porta 40613: fabrique uma picareta de madeira.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':40613,'inventory':[{'name':'oak_log','count':5}]}
        perception={'receitas':[{'item':'oak_planks','variantes':[{'exige_bancada':False,
            'ingredientes':[{'nome':'oak_log','precisa':1,'tem':5}]}]}]}
        async def probe(*_,**callbacks):
            result=await callbacks['ask'](state,cp)
            self.assertEqual(result['tool'],'minecraft_craft');self.assertEqual(result['arguments'],{'nome':'oak_planks','quantidade':1})
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state|{'percepcao':perception})}),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','options','')))
        self.assertIsNone(app.chamar_modelo.call_args.args[1])
        schema=app.chamar_modelo.call_args.kwargs['formato']
        self.assertIn('fabricar:oak_planks',schema['properties']['opcao']['enum'])
        self.assertIn('outra',schema['properties']['opcao']['enum'])
        prompt=app.chamar_modelo.call_args.args[0][0]['content']
        self.assertNotIn('foi escolhida por você',prompt)  # passos iniciais ainda não têm meta autoral

    def test_stalled_minecraft_chooses_owned_subgoal_before_native_action(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[
            {'content':json.dumps({'item':'oak_planks','total':3,'note':'Preparar ingrediente pendente.'})},
            {'tool_calls':[{'function':{'name':'minecraft_craft','arguments':{'nome':'oak_planks','quantidade':4}}}]}])
        task=SimpleNamespace(id='subgoal-choice',objetivo='Minecraft host 127.0.0.1 porta 40613: fabrique uma picareta de madeira.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);cp['steps']=3
        cp['plan']='PLANO: coletar troncos.';cp['plan_step']=3
        cp['minecraft_chat_presented']=['s:old']
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':40613,
               'inventory':[{'name':'oak_planks','count':2}],
               'recentChat':[{'id':'s:old','sessionId':'s','username':'Gustavo','message':'MENSAGEM_ANTIGA'}],
               'lastEvent':{'type':'chat','detail':'MENSAGEM_ANTIGA'}}
        perception={'receitas':[{'item':'oak_planks','variantes':[]}]}
        async def probe(*_,**callbacks):
            action=await callbacks['ask'](state,cp)
            self.assertEqual(action['tool'],'minecraft_craft')
            self.assertEqual(action['arguments'],{'nome':'oak_planks','quantidade':4})
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state|{'percepcao':perception})}),\
             patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','subgoal','')))
        self.assertEqual(cp['subgoal']['author'],config.ENTIDADE_ID)
        self.assertEqual(cp['subgoal']['item'],'oak_planks')
        selection=app.chamar_modelo.call_args_list[0]
        self.assertIsNone(selection.args[1]);self.assertIn('formato',selection.kwargs)
        # 27/10: sem raciocínio a meta saía "coal_block 30" e "crafting_table 20"; segue a preferência da entidade.
        self.assertEqual(selection.kwargs['think_override'],bool(config.THINKING))
        self.assertEqual(selection.kwargs['forcar_sem_pensar'],not config.THINKING)
        self.assertGreaterEqual(selection.kwargs['limite_saida'],4096 if config.THINKING else 300)
        view=json.loads(app.chamar_modelo.call_args_list[1].args[0][-1]['content'])
        self.assertNotIn('MENSAGEM_ANTIGA',app.chamar_modelo.call_args_list[0].args[0][-1]['content'])
        self.assertEqual(view['subobjetivo_atual']['missing'],1)
        self.assertIn('anterior',view['meu_plano'].get('aviso',''))
        self.assertIn('progresso_observado',view);self.assertIn('trajetoria',view)

    def test_minecraft_perception_examines_furnace_when_smelting_needs_one(self):
        # 27/10: fundição exigia forno, mas furnace nunca era analisado nem oferecido.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]})
        task=SimpleNamespace(id='furnace-view',objetivo='Minecraft host 127.0.0.1 porta 40613: fabrique uma picareta de ferro.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':40613,'inventory':[{'name':'iron_ore','count':5}]}
        smelt={'item':'iron_ingot','variantes':[{'processo':'fornalha','exige_forno':True,'forno_a_4_blocos':False,
               'ingredientes':[{'nome':'iron_ore','precisa':1,'tem':5}]}]}
        pick={'item':'iron_pickaxe','bancada_a_4_blocos':True,'variantes':[{'exige_bancada':True,'ingredientes':[{'nome':'iron_ingot','precisa':3,'tem':0}]}]}
        asked=[]
        def fake(tool,args,*_):
            asked.append(args.get('itens'));items=args.get('itens') or []
            recipes=[r for r in (pick,smelt) if r['item'] in items]
            return {'output':json.dumps(state|{'percepcao':{'arredores':{},'receitas':recipes}})}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp);return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',side_effect=fake),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','furnace-view','')))
        self.assertTrue(any(items and 'furnace' in items for items in asked),asked)

    def test_failed_optional_subgoal_inference_does_not_stop_the_action_decision(self):
        # 27/10 13:28: a meta com raciocínio esgotou a saída e derrubou a decisão inteira.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[RuntimeError('LLM_STREAM_INCOMPLETO: limite de geração atingido'),
            {'tool_calls':[{'function':{'name':'minecraft_craft','arguments':{'nome':'oak_planks','quantidade':4}}}]}])
        task=SimpleNamespace(id='subgoal-fails',objetivo='Minecraft host 127.0.0.1 porta 40613: fabrique uma picareta de madeira.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);cp['steps']=3
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':40613,
               'inventory':[{'name':'oak_planks','count':2}]}
        perception={'receitas':[{'item':'oak_planks','variantes':[]}]}
        async def probe(*_,**callbacks):
            action=await callbacks['ask'](state,cp)
            self.assertEqual(action['tool'],'minecraft_craft')
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state|{'percepcao':perception})}),\
             patch.object(task_state,'pausar'),patch.object(minecraft_agent,'save'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','subgoal-fails','')))
        self.assertIn('não concluída',cp['subgoal_feedback'])
        self.assertEqual(app.chamar_modelo.call_args_list[0].kwargs['limite_saida'],4096 if config.THINKING else 300)  # 30/10: igual à decisão

    def test_minecraft_cognitive_subgoals_do_not_change_alistair_protocol(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]})
        task=SimpleNamespace(id='alistair-protocol',objetivo='Minecraft host 127.0.0.1 porta 40613: fabrique uma picareta de madeira.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);cp['steps']=3
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':40613}
        async def probe(*_,**callbacks):
            self.assertEqual((await callbacks['ask'](state,cp))['tool'],'minecraft_estado')
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(config,'ENTIDADE_ID','alistair'),patch.object(minecraft_agent,'load',return_value=cp),\
             patch.object(minecraft_agent,'run',side_effect=probe),patch.object(task_state,'pausar'),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state|{'percepcao':{'receitas':[{'item':'oak_planks'}]}})}):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','alistair-protocol','')))
        self.assertEqual(app.chamar_modelo.await_count,1)
        self.assertNotIn('formato',app.chamar_modelo.call_args.kwargs)

    def test_invalid_optional_subgoal_is_feedback_before_separate_valid_action_choice(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[{'content':json.dumps({'item':'invented_magic','total':64,'note':'x'})},
            {'tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]}])
        task=SimpleNamespace(id='invalid-subgoal',objetivo='Minecraft host 127.0.0.1 porta 40613: fabrique uma picareta de madeira.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria);cp['steps']=3
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':40613}
        async def probe(*_,**callbacks):
            self.assertEqual((await callbacks['ask'](state,cp))['tool'],'minecraft_estado')
            self.assertNotIn('subgoal',cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',return_value={'output':json.dumps(state|{'percepcao':{'receitas':[{'item':'oak_planks'}]}})}),\
             patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','invalid-subgoal','')))
        self.assertEqual(app.chamar_modelo.await_count,2)
        self.assertIn('inválido',cp['subgoal_feedback'])

    def test_minecraft_decision_sees_executable_missing_ingredient_conversion(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'tool_calls':[{'function':{
            'name':'minecraft_craft','arguments':{'nome':'oak_planks','quantidade':4}}}]})
        text='Minecraft host 127.0.0.1 porta 40613: fabrique uma picareta de madeira.'
        task=SimpleNamespace(id='ingredient-perception',objetivo=text)
        criteria=minecraft_agent.targets(text);cp=minecraft_agent.initial(text,criteria)
        state={'connected':True,'verified':True,'sessionId':'fixture','host':'127.0.0.1','port':40613}
        pick={'item':'wooden_pickaxe','variantes':[{'pode_agora':False,'ingredientes':[
            {'nome':'oak_planks','precisa':3,'tem':2},{'nome':'stick','precisa':2,'tem':4}]}]}
        plank={'item':'oak_planks','variantes':[{'pode_agora':True,'ingredientes':[
            {'nome':'oak_log','precisa':1,'tem':5}]}]}
        requests=[]
        def read(tool,args,*_):
            self.assertEqual(tool,'minecraft_estado');requests.append(args.get('itens'))
            data={'receitas':[pick,plank] if 'oak_planks' in args.get('itens',[]) else [pick]}
            return {'ok':True,'status':'success','receipt_id':'real-observation-fixture',
                'output':json.dumps(state|{'percepcao':data})}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(main.dispatch,'executar_resultado',side_effect=read),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','ingredient','')))
        view=json.loads(app.chamar_modelo.call_args.args[0][-1]['content'])
        self.assertIn(plank,view['percepcao']['receitas'])
        self.assertEqual(requests,[['wooden_pickaxe'],['wooden_pickaxe','oak_planks']])

    def test_minecraft_native_call_preserves_arguments_without_second_inference(self):
        from core import minecraft_agent,action_commentary
        app=object.__new__(main.InterfaceHoshino);app.chamar_modelo=AsyncMock(return_value={
            'content':'','tool_calls':[{'function':{'name':'minecraft_craft','arguments':{'nome':'oak_planks','quantidade':4}}}]})
        app._obter_args_de_tarefa=AsyncMock(side_effect=AssertionError('segunda inferência trocou o alvo'))
        text='Minecraft host 127.0.0.1 porta 37837: fabrique uma bancada.'
        task=SimpleNamespace(id='decision-contract',chave='decision-contract',objetivo=text)
        criteria=minecraft_agent.targets(text);cp=minecraft_agent.initial(text,criteria)
        async def probe(*_,**callbacks):
            decision=await callbacks['ask']({'connected':True,'verified':True,'sessionId':'fixture',
                'host':'127.0.0.1','port':37837,'inventory':[{'name':'oak_log','count':3}]},cp)
            self.assertEqual(decision['tool'],'minecraft_craft')
            self.assertEqual(decision['arguments'],{'nome':'oak_planks','quantidade':4})
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(task_state,'pausar'),patch.object(action_commentary,'record_deliberation'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','contract','')))
        self.assertIsNone(app.chamar_modelo.call_args.args[1])
        choice=app.chamar_modelo.call_args.kwargs['formato']
        self.assertIn('outra',choice['properties']['opcao']['enum'])
        app._obter_args_de_tarefa.assert_not_awaited()

    def test_minecraft_native_decision_rejects_zero_or_multiple_calls(self):
        from core import minecraft_agent
        for calls in ([],[{'function':{'name':'minecraft_craft','arguments':{}}}]*2):
            app=object.__new__(main.InterfaceHoshino)
            app.chamar_modelo=AsyncMock(return_value={'content':'Uma promessa não executa.','tool_calls':calls})
            task=SimpleNamespace(id='invalid-native',objetivo='Minecraft: fabrique uma bancada.')
            criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
            async def probe(*_,**callbacks):
                await callbacks['ask']({'connected':True},cp)
                self.fail('aceitou quantidade inválida de chamadas')
            with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
                 patch.object(task_state,'pausar'),self.assertRaisesRegex(ValueError,'UMA_CHAMADA'):
                asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','invalid','')))

    def test_minecraft_disconnected_choice_exposes_setup_not_world_actions(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[{'content':'{"opcao":"outra","comentario":"Escolher conexão."}'},
            {'tool_calls':[{'function':{'name':'minecraft_conectar','arguments':{'host':'127.0.0.1','port':37837}}}]}])
        task=SimpleNamespace(id='setup-native',objetivo='Minecraft host 127.0.0.1 porta 37837: fabrique uma bancada.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        async def probe(*_,**callbacks):
            await callbacks['ask']({'connected':False,'observation_error':'ponte indisponível'},cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','setup','')))
        names={s['function']['name'] for s in app.chamar_modelo.call_args.args[1]}
        setup=app.chamar_modelo.call_args_list[0].kwargs['formato']['properties']['opcao']['enum']
        self.assertIn('conectar_destino',setup);self.assertIn('outra',setup)
        self.assertNotIn('minecraft_craft',names);self.assertNotIn('minecraft_receitas',names)
        self.assertNotIn('minecraft_ir_para',names)

    def test_minecraft_decision_view_keeps_recipes_consulted_before_reconnection(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'tool_calls':[{'function':{
            'name':'minecraft_estado','arguments':{}}}]})
        task=SimpleNamespace(id='recipes-view',objetivo='Minecraft host 127.0.0.1 porta 37837: fabrique uma bancada.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        minecraft_agent.record(cp,'minecraft_receitas',{'nome':'crafting_table'},{'ok':True,'status':'success',
            'receipt_id':'tool-old-recipes','output':json.dumps([{'requiresTable':False,'result':{'count':1},
            'ingredients':[{'name':'oak_planks','count':4}]}])},'')
        for tool in ('minecraft_manual','minecraft_iniciar_ponte','minecraft_conectar','minecraft_estado'):
            minecraft_agent.record(cp,tool,{},{'ok':True,'status':'success','receipt_id':'tool-'+tool,'output':'ok'},'')
        async def probe(*_,**callbacks):
            await callbacks['ask']({'connected':True,'verified':True,'sessionId':'fixture','host':'127.0.0.1',
                'port':37837,'inventory':[{'name':'oak_log','count':3}]},cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','recipes-view','')))
        view=json.loads(app.chamar_modelo.call_args.args[0][-1]['content'])
        window=[e.get('receipt_id') for e in view['ultimos_recibos']]
        self.assertNotIn('tool-minecraft_conectar',window);self.assertNotIn('tool-minecraft_iniciar_ponte',window)
        self.assertEqual(view['receitas_consultadas']['crafting_table'],['sem bancada, rende 1: 4 oak_planks'])
        self.assertEqual(view['falta_para_concluir'],{'fabricar':{'crafting_table':1},'ter_no_inventario':{'crafting_table':1}})
        prompt=app.chamar_modelo.call_args.args[0][0]['content']
        self.assertIn('Não reescreva o estado',prompt)

    def test_minecraft_observed_decision_uses_entity_thinking_preference(self):
        from core import minecraft_agent
        task=SimpleNamespace(id='thinking-choice',objetivo='Minecraft host 127.0.0.1 porta 37837: fabrique uma bancada.')
        criteria=minecraft_agent.targets(task.objetivo)
        for enabled in (True,False):
            app=object.__new__(main.InterfaceHoshino)
            app.chamar_modelo=AsyncMock(return_value={'tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]})
            cp=minecraft_agent.initial(task.objetivo,criteria)
            async def probe(*_,**callbacks):
                await callbacks['ask']({'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':37837},cp)
                return {'status':'paused','reason':'fixture','used':[]}
            with patch.object(config,'THINKING',enabled),patch.object(minecraft_agent,'load',return_value=cp),\
                 patch.object(minecraft_agent,'run',side_effect=probe),patch.object(task_state,'pausar'):
                asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','thinking','')))
            kwargs=app.chamar_modelo.call_args.kwargs
            self.assertEqual(kwargs['think_override'],enabled);self.assertEqual(kwargs['forcar_sem_pensar'],not enabled)
            # Raciocínio consome a mesma saída; 1024 tokens cortava a chamada.
            self.assertGreaterEqual(kwargs['limite_saida'],4096 if enabled else 1024)

    def test_minecraft_own_working_plan_persists_between_decisions(self):
        from core import minecraft_agent,action_commentary
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[
            {'content':'PLANO: troncos em tábuas; gravetos; colocar bancada; picareta.',
             'tool_calls':[{'function':{'name':'minecraft_craft','arguments':{'nome':'oak_planks','quantidade':4}}}]},
            {'content':'','tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]}])
        task=SimpleNamespace(id='own-plan',objetivo='Minecraft host 127.0.0.1 porta 37837: fabrique uma bancada.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':37837}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp);await callbacks['ask'](state,cp)
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(task_state,'pausar'),patch.object(action_commentary,'record_deliberation'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','plan','')))
        view=json.loads(app.chamar_modelo.call_args.args[0][-1]['content'])
        self.assertEqual(view['meu_plano'],{'texto':'PLANO: troncos em tábuas; gravetos; colocar bancada; picareta.'})
        self.assertIn('campo plano',app.chamar_modelo.call_args.args[0][0]['content'])  # o prompt oferece o recurso
        self.assertIn('revise quando um passo deixar de servir',app.chamar_modelo.call_args.args[0][0]['content'])  # plano velho não vira ordem
        self.assertEqual(cp['plan'],view['meu_plano']['texto'])  # resposta sem plano não apaga o anterior

    def test_minecraft_player_name_from_goal_is_part_of_authorized_target(self):
        # resume8 conectou como "Lilith", outro jogador sem o progresso da LilithMC.
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'tool_calls':[{'function':{'name':'minecraft_conectar',
            'arguments':{'host':'127.0.0.1','port':37837,'username':'Lilith'}}}]})
        task=SimpleNamespace(id='player-name',objetivo='Minecraft: conecte LilithMC ao mundo LAN em host 127.0.0.1, porta 37837. Fabrique uma bancada.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        seen={}
        async def probe(*_,**callbacks):
            seen['wrong']=callbacks['validate']('minecraft_conectar',{'host':'127.0.0.1','port':37837,'username':'Lilith'})
            decision=await callbacks['ask']({'connected':False},cp)
            seen['default']=decision['arguments']
            return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','player','')))
        self.assertIn('LilithMC',seen['wrong']);self.assertEqual(cp['target']['username'],'LilithMC')
        self.assertFalse(minecraft_agent.identity_matches(cp,{'connected':True,'verified':True,'sessionId':'s',
            'host':'127.0.0.1','port':37837,'username':'Lilith'}))

    def test_minecraft_plan_written_for_other_gaps_comes_back_marked_outdated(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':'','tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]})
        task=SimpleNamespace(id='old-plan',objetivo='Minecraft host 127.0.0.1 porta 37837: fabrique uma bancada.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        cp['plan']='PLANO: fabricar a bancada.';cp['plan_gaps']={'fabricar':{'crafting_table':1},'ter_no_inventario':{'crafting_table':1}}
        cp['crafted']={'crafting_table':1}
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':37837,'inventory':[]}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp);return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','old-plan','')))
        view=json.loads(app.chamar_modelo.call_args.args[0][-1]['content'])
        self.assertEqual(view['meu_plano']['texto'],'PLANO: fabricar a bancada.')  # o plano dela não é apagado
        self.assertIn('desatualizado',view['meu_plano']['aviso'])
        cp.pop('plan_gaps')  # plano salvo antes deste registro
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),patch.object(task_state,'pausar'):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','old-plan','')))
        legacy=json.loads(app.chamar_modelo.call_args.args[0][-1]['content'])
        self.assertIn('anterior',legacy['meu_plano']['aviso'])

    def test_minecraft_decision_sees_perception_and_may_research(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[{'content':'{"opcao":"outra","comentario":"Consultar catálogo."}'},
            {'content':'','tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]}])
        task=SimpleNamespace(id='perceive',objetivo='Minecraft host 127.0.0.1 porta 37837: fabrique uma bancada.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        state={'connected':True,'verified':True,'sessionId':'s','host':'127.0.0.1','port':37837,'inventory':[]}
        reads=[]
        def fake(tool,args,*_):
            reads.append((tool,args));return {'ok':True,'status':'success','receipt_id':'r',
                'output':json.dumps({**state,'percepcao':{'arredores':{'oak_log':{'distancia':3}},'receitas':[]}})}
        async def probe(*_,**callbacks):
            await callbacks['ask'](state,cp);return {'status':'paused','reason':'fixture','used':[]}
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',side_effect=probe),\
             patch.object(task_state,'pausar'),patch.object(main.dispatch,'executar_resultado',side_effect=fake):
            asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','perceive','')))
        self.assertIn(('minecraft_estado',{'itens':['crafting_table']}),reads)
        view=json.loads(app.chamar_modelo.call_args_list[0].args[0][-1]['content'])
        self.assertEqual(view['percepcao']['arredores']['oak_log']['distancia'],3)
        names={s['function']['name'] for s in app.chamar_modelo.call_args.args[1]}
        self.assertIn('web_search',names)
        self.assertEqual(view['possibilidades']['coletar:oak_log']['tool'],'minecraft_coletar')

    def test_minecraft_pause_status_does_not_invent_an_agenda_goal(self):
        from core import minecraft_agent,autonomy
        app=object.__new__(main.InterfaceHoshino)
        task=SimpleNamespace(id='pending-status',objetivo='Minecraft: fabrique uma bancada.')
        criteria=minecraft_agent.targets(task.objetivo);cp=minecraft_agent.initial(task.objetivo,criteria)
        with patch.object(minecraft_agent,'load',return_value=cp),patch.object(minecraft_agent,'run',
                new=AsyncMock(return_value={'status':'paused','reason':'Sem progresso observado.','used':[]})),\
             patch.object(task_state,'pausar'),patch.object(autonomy,'_agenda_real',return_value=('Agenda vazia',False,False)):
            text,_=asyncio.run(app._ciclo_minecraft_observado(task,criteria,chave_conversa=('test','pending','')))
            self.assertEqual(autonomy.checar_afirmacoes_de_agenda(text),(True,''))

    def test_observed_destination_guard_runs_after_acquiring_action_lock(self):
        app=object.__new__(main.InterfaceHoshino);app.sys_log=Mock()
        app._executar_mutacao_protegida=AsyncMock(side_effect=AssertionError('efeito no destino errado'))
        world={'port':37837}
        class Lock:
            async def __aenter__(self):world['port']=25565
            async def __aexit__(self,*_):pass
        app._obter_trava_acao=lambda:Lock()
        async def guard(*_):return 'destino mudou' if world['port']!=37837 else ''
        from core import cognition
        frame=cognition.CognitiveFrame(objetivo='Minecraft',dominio='minecraft',complexidade='alta')
        result=asyncio.run(app._executar_chamadas_da_etapa(
            [{'function':{'name':'minecraft_craft','arguments':{'nome':'crafting_table'}}}],frame,1,set(),
            canal='tui',validar_antes=guard))
        self.assertFalse(result[0][2]['ok']);app._executar_mutacao_protegida.assert_not_awaited()

    def test_observed_minecraft_read_respects_external_policy_before_rpc(self):
        from core import minecraft_agent
        app=object.__new__(main.InterfaceHoshino);app.chamar_modelo=AsyncMock()
        text='Minecraft: fabrique uma picareta de madeira.'
        task=SimpleNamespace(id='policy-mc',chave='policy-mc',objetivo=text)
        criteria=minecraft_agent.targets(text)
        with patch.object(minecraft_agent,'load',return_value=minecraft_agent.initial(text,criteria)),\
             patch.object(main.dispatch,'politica_externa',return_value=(False,'negado fixture')) as policy,\
             patch.object(minecraft,'estado',side_effect=AssertionError('leitura fora do dispatcher')) as raw,\
             patch.object(task_state,'pausar'):
            output,_=asyncio.run(app._ciclo_minecraft_observado(task,criteria,
                chave_conversa=('discord','x','human'),canal='discord',pessoa={'id':'human'}))
        self.assertIn('bloquead',output.casefold());raw.assert_not_called()
        self.assertGreaterEqual(policy.call_count,1);app.chamar_modelo.assert_not_awaited()

    def test_named_minecraft_goal_uses_observed_action_loop(self):
        app=object.__new__(main.InterfaceHoshino)
        app._ciclo_minecraft_observado=AsyncMock(return_value=('resultado do ciclo observado',['minecraft_craft']))
        task=SimpleNamespace(id='observed-route',objetivo='Minecraft: fabrique uma picareta de madeira.',
            etapas=[{'status':'pending','texto':'Minecraft: fabrique uma picareta de madeira.'}])
        output,used=asyncio.run(app.ciclo_de_ferramentas(
            [{'role':'user','content':task.objetivo}],[],tarefa_turno=task,chave_conversa=('test','observed','')))
        self.assertEqual(output,'resultado do ciclo observado');self.assertEqual(used,['minecraft_craft'])
        app._ciclo_minecraft_observado.assert_awaited_once()

    def test_named_minecraft_goal_with_roleplay_fragment_still_uses_observed_loop(self):
        # "voltamos depois da queda" dividiu a tarefa em duas etapas e desviou para o plano fixo. Desde 30/10
        # "depois da" não corta mais; o fragmento de RP aqui usa um conector real ("e depois").
        app=object.__new__(main.InterfaceHoshino)
        app._ciclo_minecraft_observado=AsyncMock(return_value=('resultado do ciclo observado',[]))
        app._planejar_operacoes_de_tarefa=AsyncMock(side_effect=AssertionError('plano fixo usado'))
        text='Minecraft: fabrique uma bancada. RP: “Lilith, a energia caiu e depois voltamos. Quero ver você jogar.”'
        parts=task_state.decompor(text);self.assertGreater(len(parts),1)
        task=SimpleNamespace(id='observed-rp',objetivo=text,etapas=[{'status':'pending','texto':p} for p in parts])
        output,_=asyncio.run(app.ciclo_de_ferramentas([{'role':'user','content':text}],[],tarefa_turno=task,
            chave_conversa=('test','observed-rp','')))
        self.assertEqual(output,'resultado do ciclo observado');app._ciclo_minecraft_observado.assert_awaited_once()

    def test_minecraft_argument_context_uses_current_observation_not_old_static_plan(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':'{"nome":"oak_planks","quantidade":4}'})
        task=SimpleNamespace(id='observed-args',chave='observed-args')
        with patch.object(task_state,'contexto_operacao',side_effect=AssertionError('plano antigo lido')):
            args,error=asyncio.run(app._obter_args_de_tarefa(task,{'ferramenta':'minecraft_craft'},
                contexto_operacional='Estado observado:3oak_log; operação escolhida: produzir tábuas.'))
        self.assertFalse(error);self.assertEqual(args['nome'],'oak_planks')
        self.assertIn('3oak_log',app.chamar_modelo.call_args.args[0][-1]['content'])

    def test_minecraft_planner_timeout_never_falls_back_to_first_action(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('local','fixture-minecraft-timeout','')
        task=task_state.iniciar_ou_continuar(key,'Minecraft: conecte e fabrique uma bancada.')
        app=object.__new__(main.InterfaceHoshino)
        app._fila_chaves={};app._saidas_por_conversa={};app._locks_saida={}
        app._planejar_operacoes_de_tarefa=AsyncMock(return_value=(False,'falha no planejador: TimeoutError'))
        app._obter_args_de_tarefa=AsyncMock(return_value=({},''))
        app._executar_chamadas_da_etapa=AsyncMock(side_effect=AssertionError('ação executada sem plano'))
        output,tools=asyncio.run(app._ciclo_de_ferramentas_impl(
            [{'role':'user','content':task.objetivo}],[],chave_conversa=key,canal='local',tarefa_turno=task))
        self.assertEqual(task_state.status_id(task.id),'paused')
        app._executar_chamadas_da_etapa.assert_not_awaited();self.assertFalse(tools)
        self.assertIn('TimeoutError',output)

    def test_minecraft_incomplete_plan_is_revised_by_model_not_filled_by_controller(self):
        app=object.__new__(main.InterfaceHoshino)
        first={'operacoes':[{'ferramenta':'minecraft_estado','instrucao':'Consultar estado.'}],'concluida':False}
        second={'operacoes':[{'ferramenta':name,'instrucao':description} for name,description in (
            ('minecraft_estado','Consultar estado.'),('minecraft_craft','Fabricar os itens conforme receitas e recursos.'),
            ('minecraft_equipar','Segurar a bancada fabricada.'),('minecraft_colocar_bloco','Colocar a bancada depois de fabricada e equipada.'))],'concluida':False}
        app.chamar_modelo=AsyncMock(side_effect=[{'content':json.dumps(first)},{'content':json.dumps(second)}])
        task=SimpleNamespace(id='mc-plan',chave='mc-plan',workspace_root='',known_paths=[],ultimo_resultado='',
            etapas=[{'status':'pending','texto':'Minecraft: fabrique e coloque uma bancada.'}])
        with patch.object(task_state,'definir_operacoes',return_value=task) as save:
            ok,error=asyncio.run(app._planejar_operacoes_de_tarefa(task))
        self.assertTrue(ok,error);self.assertEqual(app.chamar_modelo.await_count,2)
        operations=save.call_args.args[1]
        self.assertEqual([o['ferramenta'] for o in operations],['minecraft_estado','minecraft_craft','minecraft_equipar','minecraft_colocar_bloco'])
        self.assertFalse(any('required' in o['id'] for o in operations))
        self.assertIn('minecraft_craft',app.chamar_modelo.call_args.args[0][0]['content'])

    def test_minecraft_planning_honors_enabled_reasoning_instead_of_forcing_it_off(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'operacoes':[
            {'ferramenta':'minecraft_estado','instrucao':'Consultar o estado.'}],'concluida':False})})
        task=SimpleNamespace(id='mc-think',chave='mc-think',workspace_root='',known_paths=[],ultimo_resultado='',
            etapas=[{'status':'pending','texto':'Consulte o estado Minecraft.'}])
        for enabled in (True,False):
            with patch.object(config,'THINKING',enabled),patch.object(task_state,'definir_operacoes',return_value=task):
                ok,error=asyncio.run(app._planejar_operacoes_de_tarefa(task))
            self.assertTrue(ok,error)
            self.assertEqual(app.chamar_modelo.call_args.kwargs['think_override'],enabled)
            self.assertEqual(app.chamar_modelo.call_args.kwargs['forcar_sem_pensar'],not enabled)

    def test_minecraft_unrepaired_plan_is_not_persisted_or_executed(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'operacoes':[
            {'ferramenta':'minecraft_estado','instrucao':'Consultar estado.'}],'concluida':False})})
        task=SimpleNamespace(id='mc-plan',chave='mc-plan',workspace_root='',known_paths=[],ultimo_resultado='',
            etapas=[{'status':'pending','texto':'Minecraft: fabrique e coloque uma bancada.'}])
        with patch.object(task_state,'definir_operacoes',return_value=task) as save:
            ok,error=asyncio.run(app._planejar_operacoes_de_tarefa(task))
        self.assertFalse(ok);self.assertIn('PLANO_INCOMPLETO',error)
        self.assertEqual(app.chamar_modelo.await_count,2);save.assert_not_called()

    def test_explicit_minecraft_crafting_and_placement_require_real_operations(self):
        required=main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(
            'Minecraft: usando os recursos atuais, fabrique e coloque sua bancada e fabrique uma picareta de madeira. Confira o resultado.')
        self.assertTrue({'minecraft_craft','minecraft_colocar_bloco','minecraft_estado'}<=required)
        for text in ('Minecraft: não fabrique nem coloque blocos; só consulte o inventário.',
                     'Minecraft: explique como fabricar uma bancada, sem executar.'):
            required=main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(text)
            self.assertNotIn('minecraft_craft',required);self.assertNotIn('minecraft_colocar_bloco',required)

    def test_argument_formatter_reads_schema_and_corrects_tool_name_as_block(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(side_effect=[{'content':json.dumps({'nome':'minecraft_coletar'})},
                                               {'content':json.dumps({'nome':'oak_log','quantidade':3})}])
        task=SimpleNamespace(id='mc-args',chave='mc-args')
        op={'ferramenta':'minecraft_coletar','instrucao':'Obter madeira no mundo observado.'}
        with patch.object(task_state,'contexto_operacao',return_value='Obter madeira no Minecraft.'):
            args,error=asyncio.run(app._obter_args_de_tarefa(task,op))
        self.assertFalse(error);self.assertEqual(args,{'nome':'oak_log','quantidade':3})
        self.assertEqual(app.chamar_modelo.await_count,2)
        system=app.chamar_modelo.call_args_list[0].args[0][0]['content']
        self.assertIn('"properties"',system);self.assertIn('"quantidade"',system)
        self.assertIn('ID de bloco',system)

    def test_task_model_stage_compacts_by_tokens_before_twelve_messages(self):
        app=object.__new__(main.InterfaceHoshino)
        system={'role':'system','content':'I'*26500}
        original={'role':'user','content':'Objetivo: conectar e observar o mundo; não aprovar armadura.'}
        work=[system,original]
        for name,size in [('manual',5200),('conectar',660),('estado',660)]:
            work.extend([{'role':'assistant','content':'','tool_calls':[{'function':{'name':name,'arguments':{}}}]},
                         {'role':'tool','tool_name':name,'content':'R'*size}])
        prompt='Apresente apenas o estado observado.'
        before=json.dumps(work,ensure_ascii=False)
        with patch.object(config,'NUM_CTX',16384),patch.object(config,'CONTEXTO_MAX_TOKENS',16384),patch.object(config,'NUM_PREDICT',4096):
            projected=app._contexto_modelo_tarefa(work,prompt,'Conexão verificada; armadura pendente.')
        self.assertLess(resource_manager.context_requirement(projected,output_max=4096)[1],16385)
        self.assertEqual(json.dumps(work,ensure_ascii=False),before)
        self.assertIn(system,projected);self.assertIn(original,projected)
        self.assertIn(work[-1],projected);self.assertIn(work[-2],projected)
        self.assertIn('armadura pendente',str(projected))
        self.assertEqual(projected[-1],{'role':'user','content':prompt})

    def test_task_model_stage_preserves_small_context_without_projection(self):
        app=object.__new__(main.InterfaceHoshino)
        work=[{'role':'system','content':'Identidade.'},{'role':'user','content':'Pedido.'}]
        self.assertEqual(app._contexto_modelo_tarefa(work,'Relate.','Pendente.'),
                         work+[{'role':'user','content':'Relate.'}])

    def test_minecraft_planner_can_choose_prerequisites_before_crafting(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'operacoes':[
            dict(ferramenta='minecraft_manual',instrucao='Consultar o manual.'),
            dict(ferramenta='minecraft_iniciar_ponte',instrucao='Iniciar somente a ponte.'),
            dict(ferramenta='minecraft_conectar',instrucao='Conectar ao mundo LAN1.16.1 porta35229.'),
            dict(ferramenta='minecraft_craft',instrucao='Fabricar quando houver recursos e bancada.'),
            dict(ferramenta='minecraft_estado',instrucao='Conferir o efeito real.')], 'concluida':False})})
        task=SimpleNamespace(id='fixture-minecraft',chave='fixture-minecraft',workspace_root='',known_paths=[],ultimo_resultado='',
            etapas=[dict(status='pending',texto='Fabricar uma picareta no Minecraft em sobrevivência.')])
        with patch.object(task_state,'definir_operacoes',return_value=task) as save:
            ok,error=asyncio.run(app._planejar_operacoes_de_tarefa(task))
        self.assertTrue(ok,error)
        names=app.chamar_modelo.call_args.kwargs['formato']['properties']['operacoes']['items']['properties']['ferramenta']['enum']
        self.assertTrue({'minecraft_manual','minecraft_iniciar_ponte','minecraft_conectar','minecraft_coletar','minecraft_forno'}<=set(names))
        self.assertNotIn('execute_command',names)
        self.assertEqual([op['ferramenta'] for op in save.call_args.args[1]][:3],['minecraft_manual','minecraft_iniciar_ponte','minecraft_conectar'])

    def test_minecraft_tool_identifier_also_selects_domain_prerequisites(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'operacoes':[
            dict(ferramenta='minecraft_manual',instrucao='Consultar o manual antes da conexão.'),
            dict(ferramenta='minecraft_craft',instrucao='Fabricar quando houver recursos.'),
            dict(ferramenta='minecraft_estado',instrucao='Conferir o efeito real.')],'concluida':False})})
        task=SimpleNamespace(id='fixture-id',chave='fixture-id',workspace_root='',known_paths=[],ultimo_resultado='',
            etapas=[dict(status='pending',texto='Consulte minecraft_manual e inicie a ponte antes de fabricar itens.')])
        with patch.object(task_state,'definir_operacoes',return_value=task):
            ok,error=asyncio.run(app._planejar_operacoes_de_tarefa(task))
        self.assertTrue(ok,error)
        names=app.chamar_modelo.call_args.kwargs['formato']['properties']['operacoes']['items']['properties']['ferramenta']['enum']
        self.assertIn('minecraft_iniciar_ponte',names)
    def test_entity_delivery_keeps_original_target_and_does_not_invent_wake(self):
        app=object.__new__(main.InterfaceHoshino)
        task=SimpleNamespace(id='isolated',chave='isolated',objetivo='Mande um oi ao Alistair e se apresente.')
        operation={'ferramenta':'entidades_enviar_mensagem','etapa':task.objetivo}
        for wrong in ({'entidade':'hoshino','texto':'Oi'}, {'entidade':'alistair','texto':'Oi','acordar':True}):
            app.chamar_modelo=AsyncMock(return_value={'content':json.dumps(wrong)})
            with patch.object(task_state,'contexto_operacao',return_value=task.objetivo):
                args,error=asyncio.run(app._obter_args_de_tarefa(task,operation))
            self.assertFalse(args);self.assertTrue(error)
        correct={'entidade':'alistair','texto':'Oi, Alistair! Sou Lilith.','acordar':False}
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps(correct)})
        with patch.object(task_state,'contexto_operacao',return_value=task.objetivo):
            args,error=asyncio.run(app._obter_args_de_tarefa(task,operation))
        self.assertFalse(error);self.assertEqual(args,correct)
        self.assertFalse(main.InterfaceHoshino._etapa_pode_ser_resolvida_pelo_modelo(task.objetivo))
        self.assertEqual(main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(task.objetivo),{'entidades_enviar_mensagem'})

    def test_known_workspace_prefix_without_slash_is_not_duplicated(self):
        from tools import filesystem
        with tempfile.TemporaryDirectory() as folder,patch.object(filesystem,'OFICINA_DIR',folder):
            path=Path(folder)/'src/main.py'
            self.assertEqual(filesystem.resolver_caminho(str(path).lstrip('/')),path)
            self.assertEqual(filesystem.resolver_caminho('tmp/main.py'),Path(folder)/'tmp/main.py')

    def test_program_rendering_image_does_not_require_image_generator(self):
        required=main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(
            'Crie um programa Python que renderiza uma imagem de buraco negro e execute para verificar o resultado.')
        self.assertNotIn('gerar_imagem',required)
        self.assertIn('execute_command',required)
        self.assertIn('gerar_imagem',main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(
            'Gere uma imagem de uma colher num fundo branco.'))
        self.assertIn('gerar_imagem',main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(
            'Crie um programa e depois gere uma imagem pelo gerador local.'))

    def test_readme_does_not_request_discord_but_explicit_dm_does(self):
        self.assertNotIn('discord_estado',main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(
            'Consulte o README e crie um programa próprio.'))
        self.assertIn('discord_estado',main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(
            'Verifique minha DM no Discord.'))

    def test_open_folder_and_list_does_not_read_directory_as_source_file(self):
        self.assertEqual(task_state._inferir_workspace_operacao(
            "Abra a pasta 'black_hole_sim' e liste seu conteúdo interno para garantir que está vazia ou contém apenas um arquivo Python inicial."),'listar')
        self.assertEqual(task_state._inferir_workspace_operacao(
            'Leia main.py dentro da pasta black_hole_sim.'),'ler')

    def test_compaction_summary_is_scoped_to_conversation_and_survives_restart(self):
        from core import compaction
        init_db.init_database(verbose=False)
        a=('discord','dm-a','human-a'); b=('discord','dm-b','human-b')
        compaction.aplicar('Segredo informado apenas em A.', [], 10, chave_conversa=a)
        compaction.aplicar('Assunto exclusivo de B.', [], 10, chave_conversa=b)
        # Nova consulta abre outra conexão: não depende de cache em RAM.
        self.assertEqual(compaction.ultimo_resumo(a),'Segredo informado apenas em A.')
        self.assertEqual(compaction.ultimo_resumo(b),'Assunto exclusivo de B.')
        self.assertNotIn('Segredo',compaction.prompt_resumo([],chave_conversa=b))
        self.assertEqual(compaction.ultimo_resumo(('localhub','new','')), '')

    def test_unscoped_legacy_summary_is_readable_but_not_injected_into_new_thread(self):
        from core import compaction
        init_db.init_database(verbose=False)
        compaction.aplicar('Resumo legado sem destinatário comprovado.', [], 10)
        self.assertIn('legado',compaction.ultimo_resumo())
        self.assertEqual(compaction.ultimo_resumo(('discord','isolated','')), '')

    def test_compaction_never_silently_slices_input_or_output(self):
        from core import compaction
        long_message='X'*900+' condição obrigatória no final'
        prompt=compaction.prompt_resumo([{'role':'user','content':long_message}],chave_conversa=('localhub','lab',''))
        self.assertIn(long_message,prompt)
        self.assertIn('X'*13000,compaction.prompt_resumo([{'role':'user','content':'X'*13000}]))
        with self.assertRaisesRegex(ValueError,'COMPACTION_SUMMARY_TOO_LARGE'):
            compaction.aplicar('X'*(config.RESUMO_MAX_CHARS+1), [],100)
        self.assertEqual(compaction.ultimo_resumo(),'')

    def test_completed_task_summary_reloads_exact_id_not_other_paused_task(self):
        init_db.init_database(verbose=False)
        key=('test','completed-summary-exact-id','')
        old=task_state.iniciar_ou_continuar(key,'Olhe o anexo antiga.png e identifique o que vê.')
        task_state.pausar(key)
        current=task_state.iniciar_ou_continuar(key,'Leia arquivo-novo.txt.')
        task_state.registrar_ferramenta(key,'workspace','success','OPERACAO=ler\nPATH=/tmp/arquivo-novo.txt\nBYTES=3\nabc')
        self.assertEqual(task_state.status_id(current.id),'completed')
        self.assertEqual(task_state.carregar_ultimo(key).id,old.id)  # API de retomada conserva seu contrato
        app=object.__new__(main.InterfaceHoshino);app.prompt_sistema='Identidade externa.'
        app.chamar_modelo=AsyncMock(return_value=dict(content='Li o arquivo novo: abc.'))
        answer=asyncio.run(app._resumir_desfecho_tarefa(current,'recibo final'))
        self.assertEqual(answer,'Li o arquivo novo: abc.')
        prompt=app.chamar_modelo.call_args.args[0][-1]['content']
        self.assertIn('"estado": "completed"',prompt);self.assertNotIn('imagem antiga',prompt)
        self.assertIn('/tmp/arquivo-novo.txt',prompt)

    def test_minecraft_world_verified_completion_is_not_unverified_claim(self):
        app=object.__new__(main.InterfaceHoshino);app.prompt_sistema='Identidade externa.'
        app.chamar_modelo=AsyncMock(return_value=dict(content='Concluí: estou conectada e tenho as 30 carnes assadas.'))
        task=SimpleNamespace(objetivo='Minecraft: 30 carnes assadas.',status='completed',ultima_acao='minecraft_goal_verified',
            ultimo_resultado='{"verified_goals": {"cooked_salmon": 30}}',etapas=[dict(status='done',operacoes_lista=[
            dict(ferramenta='minecraft_forno',evidencia=dict(status='success',output='{"taken": {"name": "cooked_salmon", "count": 6}}'))])])
        answer=asyncio.run(app._resumir_desfecho_tarefa(task,'Critérios conferidos no mundo.'))
        self.assertEqual(answer,'Concluí: estou conectada e tenho as 30 carnes assadas.')
        self.assertEqual(app.chamar_modelo.call_count,1)  # sem correção que a faça negar a conclusão
        self.assertIn('verified_goals',app.chamar_modelo.call_args.args[0][-1]['content'])

    def test_correction_summary_uses_latest_verifier_and_not_obsolete_source_or_error(self):
        app=object.__new__(main.InterfaceHoshino);app.prompt_sistema='Identidade externa.'
        app.chamar_modelo=AsyncMock(return_value=dict(content='Corrigi o cálculo e os testes previstos passaram.'))
        task=SimpleNamespace(objetivo='Leia, corrija e execute codigo.py.',status='completed',etapas=[dict(status='done',operacoes_lista=[
            dict(ferramenta='workspace',operacao='ler',evidencia=dict(status='success',output='OPERACAO=ler\nPATH=/tmp/codigo.py\nBYTES=30\ntotal += quantidade + centavos')),
            dict(ferramenta='execute_command',evidencia=dict(status='error',output='[oficina | saída 1]\nfalha anterior')),
            dict(ferramenta='workspace',operacao='salvar',evidencia=dict(status='success',output='OPERACAO=salvar\nPATH=/tmp/codigo.py')),
            dict(ferramenta='execute_command',evidencia=dict(status='success',output='[oficina | saída 0]\nOK'))])])
        answer=asyncio.run(app._resumir_desfecho_tarefa(task,'OK'))
        self.assertEqual(answer,'Corrigi o cálculo e os testes previstos passaram.')
        sent=app.chamar_modelo.call_args.args[0][-1]['content']
        self.assertNotIn('total += quantidade + centavos',sent)
        self.assertNotIn('falha anterior',sent)
        self.assertIn('ultima_execucao',sent);self.assertIn('saída 0',sent)

    def test_failed_validation_cannot_be_presented_as_approved_program(self):
        from core import cognition
        frame=cognition.CognitiveFrame(objetivo='Corrija codigo.py',dominio='arquivo',complexidade='alta',etapas_pendentes=['verifique'])
        frame.resultados_ferramentas=[dict(tool='workspace',ok=True,output='arquivo salvo'),
            dict(tool='execute_command',ok=False,output='[oficina isolada | dir: /tmp | saída 1]\nFAILED')]
        self.assertTrue(cognition.precisa_verificacao_de_conclusao('Os testes passaram, programa aprovado.',frame))
        self.assertFalse(cognition.precisa_verificacao_de_conclusao('Executei os testes, mas ainda falharam.',frame))

    def test_failed_verifier_reopens_read_fix_without_erasing_prior_evidence(self):
        init_db.init_database(verbose=False)
        key=('test','repair-after-failed-verifier','')
        task=task_state.iniciar_ou_continuar(key,'Leia, corrija e execute codigo.py na sua oficina.')
        task_state.definir_operacoes(key,[dict(id='delivery',ferramenta='entregar_arquivo',instrucao='Entregue codigo.py após os testes.')])
        task_state.registrar_ferramenta(key,'workspace','success','OPERACAO=ler\nPATH=/tmp/codigo.py\nBYTES=3\nbug',operacao_id='op-contract-read')
        task_state.registrar_ferramenta(key,'workspace','success','OPERACAO=salvar\nPATH=/tmp/codigo.py',operacao_id='op-contract-write')
        failed='[oficina isolada | dir: /tmp | saída 1]\nFAILED (failures=2)'
        receipt=dict(tool='execute_command',status='error',output=failed,ok=False)
        task_state.registrar_ferramenta(key,'execute_command','error',failed,operacao_id='op-contract-run',recibo=receipt)
        # A tentativa seguinte é bloqueada pelo núcleo, não uma nova execução.
        blocked=dict(tool='execute_command',status='error',output='ERRO_CONTROLADOR: chamada já falhou',ok=False)
        task_state.registrar_ferramenta(key,'execute_command','error',blocked['output'],operacao_id='op-contract-run',recibo=blocked)
        task_state.definir_operacoes(key,[])
        next_op=task_state.proxima_operacao(key)
        self.assertEqual(next_op['operacao'],'ler')
        self.assertNotEqual(next_op['operacao_id'],'op-contract-read')
        reloaded=task_state.carregar(key)
        ops=reloaded.etapas[0]['operacoes_lista']
        self.assertIn('op-contract-write',reloaded.etapas[0]['ferramentas_executadas_lista'])
        self.assertIn('delivery',[op['id'] for op in ops])
        self.assertTrue(any('FAILED (failures=2)' in e.get('output','') for op in ops
                            for e in [op.get('evidencia',{})]+op.get('tentativas',[])))
        self.assertIn('FAILED (failures=2)',task_state.contexto_operacao(key))
        pending_ids=[op['id'] for op in ops if op['id'] not in reloaded.etapas[0]['ferramentas_executadas_lista']]
        task_state.definir_operacoes(key,[])
        self.assertEqual(pending_ids,[op['id'] for op in task_state.carregar(key).etapas[0]['operacoes_lista']
                                     if op['id'] not in task_state.carregar(key).etapas[0]['ferramentas_executadas_lista']])
        task_state.registrar_ferramenta(key,'workspace','success','OPERACAO=ler\nPATH=/tmp/codigo.py\nBYTES=3\nbug',operacao_id=next_op['operacao_id'])
        writing=task_state.proxima_operacao(key)
        self.assertEqual(writing['operacao'],'salvar')
        task_state.registrar_ferramenta(key,'workspace','success','OPERACAO=salvar\nPATH=/tmp/codigo.py',operacao_id=writing['operacao_id'])
        ids_after_repair=[op['id'] for op in task_state.carregar(key).etapas[0]['operacoes_lista']]
        task_state.definir_operacoes(key,[])
        self.assertEqual(ids_after_repair,[op['id'] for op in task_state.carregar(key).etapas[0]['operacoes_lista']])
        self.assertEqual(task_state.proxima_operacao(key)['operacao_id'],'op-contract-run')
        self.assertTrue(task_state.proxima_operacao(key)['planejada'])
        self.assertIn('delivery',[op['id'] for op in task_state.carregar(key).etapas[0]['operacoes_lista']])
        self.assertEqual(task_state.status_id(task.id),'active')

    def test_uncertain_execution_never_reopens_or_clears_effect_for_repair(self):
        init_db.init_database(verbose=False)
        key=('test','uncertain-no-repair-replay','')
        task=task_state.iniciar_ou_continuar(key,'Leia, corrija e execute codigo.py.')
        task_state.registrar_ferramenta(key,'workspace','success','leitura',operacao_id='op-contract-read')
        task_state.registrar_ferramenta(key,'workspace','success','escrita',operacao_id='op-contract-write')
        task_state.registrar_ferramenta(key,'execute_command','uncertain','RESULTADO_INCERTO: timeout',operacao_id='op-contract-run')
        task_state.definir_operacoes(key,[])
        self.assertEqual(task_state.status_id(task.id),'paused')
        self.assertEqual(task_state.proxima_operacao(key)['operacao_id'],'op-contract-run')
        self.assertIn('RESULTADO_INCERTO',task_state.contexto_operacao(key))

    def test_explicit_original_verifier_command_is_not_replaced_by_program_execution(self):
        app=object.__new__(main.InterfaceHoshino);app.chamar_modelo=AsyncMock(side_effect=AssertionError('não precisa de inferência'))
        op=dict(ferramenta='execute_command',etapa='Leia, corrija e execute codigo.py na sua oficina. Execute python3 verificador_externo.py -v, que contém os critérios originais.')
        args,error=asyncio.run(app._obter_args_de_tarefa(SimpleNamespace(id='literal-command'),op))
        self.assertFalse(error);self.assertEqual(args['command'],'python3 verificador_externo.py -v')
        self.assertEqual(args['ambiente'],'oficina');app.chamar_modelo.assert_not_awaited()

    def test_summary_rejects_unperformed_execution_then_uses_natural_partial_result(self):
        app=object.__new__(main.InterfaceHoshino);app.prompt_sistema='Identidade externa.'
        app.chamar_modelo=AsyncMock(side_effect=[dict(content='Executei e terminei todos os testes.'),dict(content='Salvei o código. Ainda falta executar o verificador.')])
        task=SimpleNamespace(objetivo='Corrija codigo.py',status='active',etapas=[dict(status='pending',texto='execute o verificador',operacoes_lista=[
            dict(ferramenta='workspace',operacao='salvar',evidencia=dict(status='success',verified=True,output='PATH=/tmp/codigo.py'))])])
        answer=asyncio.run(app._resumir_desfecho_tarefa(task,'PATH=/tmp/codigo.py'))
        self.assertEqual(answer,'Salvei o código. Ainda falta executar o verificador.')
        self.assertEqual(app.chamar_modelo.await_count,2)

    def test_initial_correction_reads_target_not_future_verifier_and_needs_no_model(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(config,'OFICINA_DIR',folder):
            from tools import filesystem
            with patch.object(filesystem,'OFICINA_DIR',folder):
                target=Path(folder)/'codigo.py';target.write_text('def resumir(registros): return 0\n')
                (Path(folder)/'verificador.py').write_text('pass\n')
                app=object.__new__(main.InterfaceHoshino);app.chamar_modelo=AsyncMock(side_effect=AssertionError('não precisa de inferência'))
                task=SimpleNamespace(id='read-fixture',workspace_root='',known_paths=[])
                op=dict(ferramenta='workspace',operacao='ler',etapa='Leia, corrija e execute codigo.py. Execute python3 verificador.py.')
                args,error=asyncio.run(app._obter_args_de_tarefa(task,op))
                self.assertFalse(error);self.assertEqual(args['caminho'],str(target))
                app.chamar_modelo.assert_not_awaited()

    def test_invalid_python_arguments_are_repaired_before_any_write_or_replan(self):
        init_db.init_database(verbose=False)
        source='def resumir(registros):\n    if not isinstance(registros,list):\n        raise ValueError("lista")\n    return 0\n'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'codigo.py';path.write_text(source)
            key=('test','format-before-effect','')
            task_state.iniciar_ou_continuar(key,'Leia e corrija codigo.py. Preserve função resumir(registros).')
            task_state.registrar_ferramenta(key,'workspace','success',f'OPERACAO=ler\nPATH={path}\nBYTES={len(source)}\n'+source)
            task=task_state.carregar(key);op=task_state.proxima_operacao(key)
            args=dict(operacao='salvar',modo='substituir',caminho=str(path),conteudo=source.replace('return 0','return 1'))
            app=object.__new__(main.InterfaceHoshino)
            app.chamar_modelo=AsyncMock(side_effect=[
                dict(content=json.dumps({**args,'conteudo':args['conteudo'].replace('\n',r'\n')})),
                dict(content=json.dumps(args))])
            valid,error=asyncio.run(app._obter_args_de_tarefa(task,op))
            self.assertFalse(error);self.assertEqual(valid['conteudo'],args['conteudo'])
            self.assertEqual(app.chamar_modelo.await_count,2)
            self.assertEqual(path.read_text(),source)
            self.assertEqual(task_state.proxima_operacao(key)['operacao_id'],op['operacao_id'])

    def test_legacy_uncertain_command_is_not_blindly_migrated_or_replayed(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(job_bus,'DB_PATH',Path(folder)/'jobs.sqlite3'):
            job_bus.publish('legacy','hoshino','interrupted',kind='tool',tool='execute_command',
                            signature='hash antigo irreversível',mutates=True,outcome='uncertain')
            self.assertEqual(job_bus.reserve_action('nova','hoshino','nova-assinatura','execute_command'),'legacy')
            self.assertIsNone(job_bus.get('nova'))
            job_bus.publish('legacy','hoshino','interrupted',resolved=True)
            self.assertIsNone(job_bus.reserve_action('nova','hoshino','nova-assinatura','execute_command'))

    def test_replan_preserves_original_requirement_beyond_old_prefix_and_rejects_unrelated_calculation(self):
        init_db.init_database(verbose=False)
        key=('test','original-long-contract','')
        text='Leia, corrija e execute codigo.py. '+('Detalhe necessário. '*65)+'Preserve função resumir(registros).'
        task=task_state.iniciar_ou_continuar(key,text)
        task_state.definir_operacoes(key,[dict(ferramenta='calcular',instrucao='95900')])
        self.assertNotIn('calcular',task_state.ferramentas_pendentes(key))
        self.assertIn('Preserve função resumir(registros)',task_state.contexto_operacao(key))

    def test_durable_uncertain_command_cannot_repeat_after_timeout_or_tty_change(self):
        command=dict(command='echo fixture',ambiente='oficina',timeout=10,usar_tty=False)
        effect=Mock(return_value='RESULTADO_INCERTO: operação pode ter produzido efeito.')
        with patch.object(main.dispatch.ui_policy,'allowed',return_value=True),patch.dict(main.dispatch.HANDLERS,{'execute_command':effect}):
            first=main.dispatch._executar_bruto('execute_command',command)
            second=main.dispatch._executar_bruto('execute_command',{**command,'timeout':80,'usar_tty':True})
        self.assertIn('RESULTADO_INCERTO',first);self.assertIn('não repetida',second)
        effect.assert_called_once()

    def test_operational_summary_uses_relevant_evidence_and_entity_voice_not_last_calculation(self):
        app=object.__new__(main.InterfaceHoshino);app.prompt_sistema='Identidade externa desta entidade.'
        app.chamar_modelo=AsyncMock(return_value={'content':'Salvei o arquivo, mas ainda falta conferir o contrato original.'})
        task=SimpleNamespace(objetivo='Corrija dados.py',status='completed',etapas=[dict(operacoes_lista=[
            dict(ferramenta='workspace',operacao='salvar',evidencia=dict(status='success',verified=True,output='PATH=/tmp/dados.py')),
            dict(ferramenta='calcular',evidencia=dict(status='success',output='95900'))])])
        answer=asyncio.run(app._resumir_desfecho_tarefa(task,'95900'))
        self.assertEqual(answer,'Salvei o arquivo, mas ainda falta conferir o contrato original.')
        messages=app.chamar_modelo.call_args.args[0]
        self.assertIn('/tmp/dados.py',messages[-1]['content']);self.assertNotIn('95900',messages[-1]['content'])
        self.assertEqual(messages[0]['content'],app.prompt_sistema)

    def test_dynamic_prompt_keeps_identity_and_affect_but_omits_unneeded_operational_catalog(self):
        with patch.object(prompting,'_seguro',return_value='ESTADO AFETIVO EXISTENTE'),patch.object(prompting,'_carregar',return_value={}):
            casual=prompting.montar_prompt_sistema(situacao='Bom dia!')
            task=prompting.montar_prompt_sistema(situacao='Corrija codigo.py e execute os testes.')
        self.assertIn('Eu sou',casual);self.assertIn('ESTADO AFETIVO EXISTENTE',casual)
        self.assertLess(len(casual),len(task))
        self.assertIn('Hoshino, Lilith e Alistair',casual)

    def test_vision_partial_protocol_is_not_observation_and_latency_is_split(self):
        from tools import vision
        response=Mock();response.json.return_value=dict(done=False,message={'content':'bola'})
        with patch('core.gpu_resource.lease',return_value=nullcontext(dict(backend='cpu'))),\
             patch.object(resource_manager,'executor_catalog',return_value=[]),patch.object(vision.requests,'post',return_value=response),\
             patch.object(diagnostics,'emit') as telemetry:
            result=vision._consultar(dict(model=config.MODEL_NAME,messages=[dict(role='user',content='objeto?')]))
        self.assertTrue(result.startswith('Erro:'))
        phases=[c.args[0] for c in telemetry.call_args_list]
        self.assertIn('vision.admitted',phases);self.assertIn('vision.completed',phases)

    def test_correction_preserves_public_signature_and_validation_before_write(self):
        source='def resumir(registros):\n    if not isinstance(registros,list):\n        raise ValueError("lista")\n    return 0\n'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'codigo.py';path.write_text(source)
            task=SimpleNamespace(objetivo='Leia, corrija e execute codigo.py. Preserve função resumir(registros).',
                etapas=[dict(operacoes_lista=[dict(ferramenta='workspace',operacao='ler',
                    evidencia=dict(output=f'OPERACAO=ler\nPATH={path}\nBYTES={len(source)}\n'+source))])])
            args=dict(operacao='salvar',modo='substituir',caminho=str(path),conteudo=source.replace('return 0','return 965'))
            self.assertEqual(task_state.validar_contrato_escrita(task,args),'')
            self.assertIn('não encontrado',task_state.validar_contrato_escrita(task,{**args,'modo':'editar','procurar':'trecho inventado','substituir':'outra coisa'}))
            self.assertIn('assinatura',task_state.validar_contrato_escrita(task,{**args,'conteudo':'def solucao(x): return 965'}))
            self.assertIn('validação',task_state.validar_contrato_escrita(task,{**args,'conteudo':'def resumir(registros): return 965'}))
            self.assertEqual(path.read_text(),source)
            path.write_text(source+'# outra escrita\n')
            self.assertIn('mudou desde',task_state.validar_contrato_escrita(task,args))

    def test_negative_edit_of_verifier_does_not_change_mode_of_positive_correction(self):
        operations=task_state.sequencia_correcao('Leia, corrija e execute codigo.py. Não modifique o verificador externo.')
        self.assertEqual(operations[1]['modo'],'substituir')
        operations=task_state.sequencia_correcao('Edite codigo.py substituindo um trecho.')
        self.assertEqual(operations[1]['modo'],'editar')

    def test_delivery_literal_path_overrules_model_invented_parent(self):
        task=SimpleNamespace(workspace_root='',known_paths=[])
        args=task_state.normalizar_argumentos_operacao(task,
            dict(ferramenta='entregar_arquivo',etapa='Entregue Ensaio-20261009/resultado-validado.json.'),
            dict(caminho='Ensaio-Hoshino-20261009/resultado-validado.json'))
        self.assertEqual(args['caminho'],str(Path(config.OFICINA_DIR)/'Ensaio-20261009/resultado-validado.json'))
        self.assertEqual(intent.interpretar('Entregue resultado-validado.json.').ferramenta_principal,'entregar_arquivo')
        for text in ['Entregue "/tmp/pasta com espaço/dados.json".', 'Entregue /tmp/real/dados.json.']:
            args=task_state.normalizar_argumentos_operacao(task,dict(ferramenta='entregar_arquivo',etapa=text),dict(caminho='/tmp/inventado/dados.json'))
            self.assertEqual(args['caminho'],'/tmp/pasta com espaço/dados.json' if 'espaço' in text else '/tmp/real/dados.json')

    def test_correction_does_not_drop_original_output_fields(self):
        source='def resumir(registros):\n    return {"total_centavos":0,"quantidades":{}}\n'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'codigo.py';path.write_text(source)
            task=SimpleNamespace(objetivo='Leia e corrija codigo.py.',etapas=[dict(operacoes_lista=[dict(
                ferramenta='workspace',operacao='ler',evidencia=dict(output=f'OPERACAO=ler\nPATH={path}\nBYTES={len(source)}\n'+source))])])
            args=dict(operacao='salvar',modo='substituir',caminho=str(path),conteudo='def resumir(registros):\n    return {"total":965}\n')
            self.assertIn('formato de saída',task_state.validar_contrato_escrita(task,args))
            self.assertEqual(path.read_text(),source)

    def test_remote_delivery_queue_is_pending_not_received(self):
        from tools import entrega
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'arquivo.txt';source.write_text('teste')
            with patch.object(config,'ENTREGA_SAIDA',str(Path(folder)/'saida')),patch('social.channels.enviar',return_value='out-test-1'):
                output=entrega.entregar(str(source),canal='discord',destino='fixture')
            receipt=main.dispatch._resultado_mecanico('entregar_arquivo',output)
            self.assertEqual(receipt['status'],'pending');self.assertFalse(receipt['ok'])
            self.assertIn('não confirmada',output)

    def test_delivery_missing_file_is_error_not_completed(self):
        result=main.dispatch._resultado_mecanico('entregar_arquivo','Não achei o arquivo: /oficina/inventada/dados.json')
        self.assertFalse(result['ok']);self.assertEqual(result['status'],'error')

    def test_same_effect_signature_ignores_timeout_and_tty_not_command_or_directory(self):
        from core import cognition
        original=dict(command='python3 "pasta com espaço/teste.py"',ambiente='oficina',timeout=10,usar_tty=False)
        changed={**original,'timeout':80,'usar_tty':True,'tty':True,'campo_ignorado_pelo_handler':1}
        self.assertEqual(cognition.assinatura_chamada('execute_command',original),cognition.assinatura_chamada('execute_command',changed))
        self.assertNotEqual(cognition.assinatura_chamada('execute_command',original),cognition.assinatura_chamada('execute_command',{**changed,'command':'python3 outro.py'}))
        self.assertNotEqual(cognition.assinatura_chamada('execute_command',original),cognition.assinatura_chamada('execute_command',{**changed,'diretorio':'/tmp/outra'}))
        self.assertNotEqual(cognition.assinatura_chamada('execute_command',original),cognition.assinatura_chamada('execute_command',{**changed,'entrada':'outra entrada stdin'}))
        self.assertEqual(cognition.assinatura_chamada('execute_command',{'command':'echo teste'}),
                         cognition.assinatura_chamada('execute_command',{'command':'echo teste','ambiente':'sistema','diretorio':None,'entrada':None}))

    def test_local_delivery_has_verified_hash_and_no_overwrite(self):
        from tools import entrega
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'dados.json';source.write_text('{"soma":14}')
            out=root/'saida'
            with patch.object(config,'ENTREGA_SAIDA',str(out)):
                first=entrega.entregar(str(source));second=entrega.entregar(str(source))
            receipt=main.dispatch._resultado_mecanico('entregar_arquivo',first)
            self.assertTrue(receipt['ok']);self.assertTrue(receipt['verified'])
            self.assertFalse(receipt['requires_verification'])
            self.assertIn(hashlib.sha256(source.read_bytes()).hexdigest(),first)
            self.assertEqual((out/'dados.json').read_bytes(),source.read_bytes())
            self.assertEqual((out/'dados-2.json').read_bytes(),source.read_bytes())

    def test_read_fix_execute_sequence_cannot_drop_read_on_replan(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','contract-sequence','')
        current=task_state.iniciar_ou_continuar(key,'Leia, corrija e execute desafio.py na sua oficina.')
        task_state.definir_operacoes(key,[dict(id='write',ferramenta='workspace',operacao='salvar',instrucao='Corrija desafio.py')])
        pending=task_state.proxima_operacao(key)
        self.assertEqual(pending['operacao'],'ler')
        task_state.registrar_ferramenta(key,'workspace','success','OPERACAO=ler\nPATH=/tmp/desafio.py\nBYTES=50\ndef resumir(registros): return 0',operacao_id=pending['operacao_id'])
        task_state.definir_operacoes(key,[dict(id='execute',ferramenta='execute_command',instrucao='Execute desafio.py')])
        self.assertEqual(task_state.proxima_operacao(key)['operacao'],'salvar')
        self.assertIn('def resumir(registros)',task_state.contexto_operacao(key))
        self.assertNotEqual(task_state.status_id(current.id),'completed')

    def test_fix_file_before_running_does_not_resume_old_test_execution(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','fix-before-execution','')
        previous=task_state.iniciar_ou_continuar(key,'Execute python3 desafio.py -v na sua oficina.')
        task_state.definir_operacoes(key,[dict(id='execute',ferramenta='execute_command',instrucao=previous.objetivo)])
        task_state.pausar(key)
        text='Corrija desafio.py: some quantidade vezes centavos. Depois rode os testes na sua oficina.'
        self.assertEqual(intent.interpretar(text).ferramenta_principal,'workspace')
        current=task_state.iniciar_ou_continuar(key,text)
        self.assertNotEqual(current.id,previous.id)
        self.assertEqual(task_state.status_id(previous.id),'paused')
        operation=task_state.proxima_operacao(key)
        self.assertEqual(operation['ferramenta'],'workspace');self.assertEqual(operation['operacao'],'ler')
        self.assertNotEqual(intent.interpretar('Não corrija desafio.py.').ferramenta_principal,'workspace')
        self.assertFalse(task_state.parece_tarefa('Não corrija desafio.py.'))
        self.assertEqual(task_state._detectar_operacoes('Não corrija desafio.py.'),[])
        self.assertEqual(task_state._detectar_operacoes('Não corrija desafio.py. Leia o arquivo desafio.py.')[0]['operacao'],'ler')

    def test_explicit_workshop_execution_is_not_silently_routed_to_user_home(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'command':'python3 desafio.py -v','ambiente':'sistema'})})
        with patch.object(task_state,'contexto_operacao',return_value='Execute os testes'):
            args,error=asyncio.run(app._obter_args_de_tarefa(SimpleNamespace(id='isolated',chave='isolated'),
                dict(ferramenta='execute_command',etapa='Na sua oficina, execute python3 desafio.py -v.')))
            self.assertFalse(error);self.assertEqual(args['ambiente'],'oficina')
            self.assertEqual(args['command'],'python3 desafio.py -v')
            args,error=asyncio.run(app._obter_args_de_tarefa(SimpleNamespace(id='isolated',chave='isolated'),
                dict(ferramenta='execute_command',etapa='No sistema, consulte o volume.')))
            self.assertFalse(error);self.assertEqual(args['ambiente'],'sistema')

    def test_shell_pipeline_cannot_hide_failure_of_earlier_stage(self):
        from tools import terminal
        with tempfile.TemporaryDirectory() as folder:
            failed=subprocess.run(terminal._comando_shell('false | true','oficina',False),
                                  cwd=folder,capture_output=True,text=True,timeout=5)
            passed=subprocess.run(terminal._comando_shell("printf abc | wc -c",'oficina',False),
                                  cwd=folder,capture_output=True,text=True,timeout=5)
        self.assertNotEqual(failed.returncode,0)
        self.assertEqual(passed.returncode,0);self.assertEqual(passed.stdout.strip(),'3')

    def test_tty_shell_preserves_bash_and_pipeline_failure(self):
        from tools import terminal
        if not shutil.which('script'):
            self.skipTest('util-linux script indisponível; não valida PTY neste host')
        with tempfile.TemporaryDirectory() as folder:
            failed=subprocess.run(terminal._comando_shell('false | true','oficina',True),
                                  cwd=folder,capture_output=True,text=True,timeout=5)
        self.assertNotEqual(failed.returncode,0)
        self.assertNotIn('Illegal option',failed.stderr)

    def test_replan_positional_id_cannot_make_new_read_already_completed(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','replan-positional-id','')
        current=task_state.iniciar_ou_continuar(key,'Liste a pasta e leia dados.json.')
        listed=dict(id='op-plan-1',ferramenta='workspace',operacao='listar',instrucao='listar a pasta')
        read=dict(id='op-plan-2',ferramenta='workspace',operacao='ler',instrucao='leia dados.json')
        task_state.definir_operacoes(key,[listed,read])
        task_state.registrar_ferramenta(key,'workspace','success','OPERACAO=listar\nFILE\tdados.json',operacao_id='op-plan-1')
        task_state.definir_operacoes(key,[{**read,'id':'op-plan-1'}])
        pending=task_state.proxima_operacao(key)
        self.assertEqual(pending['operacao'],'ler')
        self.assertNotEqual(pending['operacao_id'],'op-plan-1')
        self.assertEqual(task_state.status_id(current.id),'active')
        # Recarregar do SQLite conserva a ação antiga e só a leitura é pendente.
        reloaded=task_state.carregar(key)
        self.assertEqual(reloaded.etapas[0]['ferramentas_executadas_lista'],['op-plan-1'])
        self.assertEqual(reloaded.etapas[0]['operacoes_lista'][0]['operacao'],'listar')

    def test_replan_does_not_repeat_completed_mutable_operation_under_another_id(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','replan-no-replay','')
        task_state.iniciar_ou_continuar(key,'Salve resultado.json e leia depois.')
        written=dict(id='write',ferramenta='workspace',operacao='salvar',modo='substituir',instrucao='Salve resultado.json.')
        read=dict(id='read',ferramenta='workspace',operacao='ler',instrucao='Leia resultado.json.')
        task_state.definir_operacoes(key,[written,read])
        task_state.registrar_ferramenta(key,'workspace','success','OPERACAO=salvar\nACAO=CRIADO',operacao_id='write')
        task_state.definir_operacoes(key,[{**written,'id':'op-plan-1'},read])
        self.assertEqual(task_state.proxima_operacao(key)['operacao_id'],'read')
        self.assertEqual(task_state.carregar(key).etapas[0]['ferramentas_executadas_lista'],['write'])

    def test_pending_stage_without_executable_operations_is_paused_not_completed(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','pending-no-operation','')
        current=task_state.iniciar_ou_continuar(key,'Leia dados.json.')
        app=object.__new__(main.InterfaceHoshino);app._fila_chaves={};app._saidas_por_conversa={};app._locks_saida={}
        app._planejar_operacoes_de_tarefa=AsyncMock(return_value=(True,''))
        with patch.object(task_state,'proxima_operacao',return_value=None):
            output,tools=asyncio.run(app._ciclo_de_ferramentas_impl(
                [{'role':'user','content':current.objetivo}],[],chave_conversa=key,canal='tui',tarefa_turno=current))
        self.assertEqual(task_state.status_id(current.id),'paused')
        self.assertIn('etapa pendente',output);self.assertFalse(tools)

    def test_listing_suboperation_stays_listing_without_directory_keyword(self):
        self.assertEqual(task_state._inferir_workspace_operacao('listar /tmp/ensaio'),'listar')
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'operacoes':[
            dict(ferramenta='workspace',operacao='ler',instrucao='listar /tmp/ensaio'),
            dict(ferramenta='workspace',operacao='ler',instrucao='Leia dados.json')],'concluida':False})})
        task=SimpleNamespace(id='isolated',chave='isolated',workspace_root='/tmp/ensaio',known_paths=[],ultimo_resultado='',
                             etapas=[dict(status='pending',texto='Liste a pasta e leia dados.json.')])
        with patch.object(task_state,'definir_operacoes',return_value=task) as save:
            ok,error=asyncio.run(app._planejar_operacoes_de_tarefa(task))
        self.assertTrue(ok,error)
        self.assertEqual([o['operacao'] for o in save.call_args.args[1]],['listar','ler'])

    def test_exhausted_replan_pauses_task_instead_of_repeating_blocked_calls(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','exhausted-replan','')
        current=task_state.iniciar_ou_continuar(key,'Olhe o anexo B.png.')
        task_state.definir_operacoes(key,[dict(id='op-vision',ferramenta='observar_imagem_recebida',
                                             instrucao='Olhe o anexo B.png.',planejada=True)])
        app=object.__new__(main.InterfaceHoshino);app._fila_chaves={};app._saidas_por_conversa={};app._locks_saida={}
        app._obter_args_de_tarefa=AsyncMock(return_value=({'nome':'B.png'},''))
        app._executar_chamadas_da_etapa=AsyncMock(return_value=[('observar_imagem_recebida',{'nome':'B.png'},
            dict(ok=False,status='error',output='ERRO_CONTROLADOR: esta chamada já falhou; mude a estratégia.',
                 controlador_replanejar=True))])
        app._planejar_operacoes_de_tarefa=AsyncMock(return_value=(False,'sem alternativa segura'))
        output,tools=asyncio.run(app._ciclo_de_ferramentas_impl(
            [{'role':'user','content':current.objetivo}],[],chave_conversa=key,canal='tui',tarefa_turno=current))
        self.assertEqual(tools,['observar_imagem_recebida'])
        app._executar_chamadas_da_etapa.assert_awaited_once()
        app._planejar_operacoes_de_tarefa.assert_awaited_once()
        self.assertEqual(task_state.status_id(current.id),'paused')
        self.assertIn('não repeti',output.lower());self.assertNotIn('muitas chamadas',output.lower())

    def test_image_parameters_from_request_are_not_lost_to_model_defaults(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'prompt':'One object, white background',
            'largura':768,'altura':768,'passos':8,'seed':-1,'cfg':4,'preset':'medio'})})
        with patch.object(task_state,'contexto_operacao',return_value='Gere imagem'):
            args,error=asyncio.run(app._obter_args_de_tarefa(SimpleNamespace(id='isolated',chave='isolated'),
                dict(ferramenta='gerar_imagem',etapa='Gere uma imagem. Use 512x512, 16 passos, seed 0, cfg 1, sem preset.')))
        self.assertFalse(error)
        self.assertEqual((args['largura'],args['altura'],args['passos'],args['seed'],args['cfg']),(512,512,16,0,1.0))
        self.assertNotIn('preset',args)

    def test_unknown_desktop_action_is_not_success_and_is_rejected_before_effect(self):
        from tools import desktop
        with patch.object(desktop,'DISPONIVEL',True),patch.object(desktop.subprocess,'run') as effect:
            output=desktop.acao('mouse_clicar',x=896,y=707)
        effect.assert_not_called()
        receipt=main.dispatch._resultado_mecanico('acao_desktop',output)
        self.assertEqual(receipt['status'],'error');self.assertFalse(receipt['ok'])
        self.assertTrue(main.dispatch.validar_argumentos('acao_desktop',dict(acao='mouse_clicar',x=896,y=707)))
        self.assertFalse(main.dispatch.validar_argumentos('acao_desktop',dict(acao='clicar',x=896,y=707)))

    def test_read_literal_path_does_not_invent_workspace_prefix(self):
        app=object.__new__(main.InterfaceHoshino);app.chamar_modelo=AsyncMock()
        task=SimpleNamespace(id='isolated',chave='isolated',workspace_root='',known_paths=[])
        args,error=asyncio.run(app._obter_args_de_tarefa(task,dict(ferramenta='workspace',operacao='ler',
            etapa='Leia Ensaio-20261009/resultado-validado.json. Só leia.')))
        self.assertFalse(error)
        self.assertEqual(args['caminho'],str(Path(config.OFICINA_DIR)/'Ensaio-20261009/resultado-validado.json'))
        app.chamar_modelo.assert_not_called()

    def test_completed_last_slot_is_not_reported_as_max_steps_failure(self):
        with patch.object(config,'MAX_PASSOS_TAREFA_LONGA',1):
            self.test_completed_task_does_not_resume_older_paused_vision_in_same_turn()

    def test_read_only_request_does_not_require_or_offer_forbidden_calculation(self):
        text='Leia resultado.json. Só leia; não salve nem calcule outra vez.'
        self.assertNotIn('calcular',main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(text))
        self.assertNotIn('calcular',{s['function']['name'] for s in main.dispatch.contratos_tarefa(text)})

    def test_screen_observation_is_not_replaced_by_negated_click(self):
        self.assertEqual(intent.interpretar('Foque a janela Steam.').ferramenta_principal,'focar_janela')
        self.assertEqual(intent.interpretar('Observe a tela, sem clicar ainda.').ferramenta_principal,'observar_tela')
        self.assertNotEqual(intent.interpretar('Sem clicar ainda.').ferramenta_principal,'acao_desktop')
        self.assertTrue({'focar_janela','observar_tela'} <= main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(
            'Foque a janela Steam. Observe a tela, sem clicar ainda.'))

    def test_peer_status_report_is_not_a_discord_command(self):
        text=('Hoshino está ativa e Lilith offline. O Discord e serviços locais estão operando normalmente. '
              'Não há jobs ativos pendentes. Você quer que eu monitore o canal enquanto aguardo instruções?')
        self.assertNotEqual(intent.interpretar(text).ferramenta_principal,'discord_estado')
        self.assertFalse(task_state.parece_tarefa(text))
        for query in ('Qual o estado do Discord?', 'Discord está online?', 'Estado do Discord'):
            self.assertEqual(intent.interpretar(query).ferramenta_principal,'discord_estado')

    def test_workspace_planner_cannot_list_instead_of_save_or_save_instead_of_read(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'operacoes':[
            dict(ferramenta='workspace',operacao='listar',instrucao='Salvar um arquivo resultado.json na pasta Ensaio para verificar depois.'),
            dict(ferramenta='workspace',operacao='salvar',instrucao='Abre o arquivo resultado.json recém-criado.')], 'concluida':False})})
        task=SimpleNamespace(id='isolated',chave='isolated',workspace_root='',known_paths=[],ultimo_resultado='',
            etapas=[dict(status='pending',texto='Salve resultado.json. Leia o JSON criado.')])
        with patch.object(task_state,'definir_operacoes',return_value=task) as save:
            ok,error=asyncio.run(app._planejar_operacoes_de_tarefa(task))
        self.assertTrue(ok,error)
        self.assertEqual([op['operacao'] for op in save.call_args.args[1]],['salvar','ler'])

    def test_known_workspace_path_is_resolved_before_alias_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);actual=root/'nested'/'dados.json'
            task=SimpleNamespace(workspace_root=str(root),known_paths=[str(actual)])
            args=task_state.normalizar_argumentos_operacao(task,
                dict(ferramenta='workspace',operacao='ler',instrucao='Leia dados.json'),dict(caminho='dados.json'))
            self.assertEqual(args['caminho'],str(actual))

    def test_completed_task_does_not_resume_older_paused_vision_in_same_turn(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','completed-file-paused-image',str(config.MAX_PASSOS_TAREFA_LONGA))
        old=task_state.iniciar_ou_continuar(key,'Olhe o anexo A.png e identifique o que vê.')
        task_state.pausar(key)
        current=task_state.iniciar_ou_continuar(key,'Leia desafio.txt.')
        task_state.definir_operacoes(key,[dict(id='op-read',ferramenta='workspace',operacao='ler',instrucao='Leia desafio.txt.')])
        app=object.__new__(main.InterfaceHoshino);app._fila_chaves={};app._saidas_por_conversa={};app._locks_saida={}
        app._obter_args_de_tarefa=AsyncMock(return_value=({'operacao':'ler','caminho':'desafio.txt'},''))
        app._executar_chamadas_da_etapa=AsyncMock(return_value=[('workspace',{},dict(ok=True,status='success',output='dados reais do teste'))])
        app._planejar_operacoes_de_tarefa=AsyncMock(return_value=(False,'sem LLM real'))
        output,tools=asyncio.run(app._ciclo_de_ferramentas_impl(
            [{'role':'user','content':current.objetivo}],[],chave_conversa=key,canal='tui',tarefa_turno=current))
        self.assertEqual(tools,['workspace']);self.assertIn('dados reais do teste',output)
        self.assertEqual(task_state.status_id(current.id),'completed')
        self.assertEqual(task_state.status_id(old.id),'paused')
        app._obter_args_de_tarefa.assert_awaited_once()

    def test_explicit_received_image_name_preserves_case_without_llm_argument_generation(self):
        app=object.__new__(main.InterfaceHoshino);app.chamar_modelo=AsyncMock()
        args,error=asyncio.run(app._obter_args_de_tarefa(SimpleNamespace(id='isolated'),
            {'ferramenta':'observar_imagem_recebida','etapa':'Olhe o anexo 0123-A.png e identifique o que vê.'}))
        self.assertEqual(args,{'nome':'0123-A.png'});self.assertFalse(error)
        app.chamar_modelo.assert_not_called()
        self.assertFalse(intent.interpretar('Olhe os anexos A.png e B.png.').parametros_sugeridos)

    def test_explicit_output_cannot_overwrite_input_file(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'caminho':'desafio.txt','conteudo':'{}'})})
        task=SimpleNamespace(id='isolated',chave='isolated')
        with patch.object(task_state,'contexto_operacao',return_value='Crie resultado.json'),\
             patch.object(task_state,'normalizar_argumentos_operacao',side_effect=lambda t,o,a:a):
            args,error=asyncio.run(app._obter_args_de_tarefa(task,{'ferramenta':'workspace','operacao':'salvar',
                          'etapa':'Crie resultado.json; não altere outros arquivos.'}))
        self.assertFalse(args);self.assertIn('não sobrescreva outro arquivo',error)

    def test_received_image_requests_expose_vision_not_generator_or_workspace(self):
        text='Olhe o anexo A.png e identifique o que vê.'
        parsed=intent.interpretar(text)
        self.assertEqual(parsed.ferramenta_principal,'observar_imagem_recebida')
        self.assertTrue(task_state.parece_tarefa(text))
        self.assertIn('observar_imagem_recebida',{s['function']['name'] for s in main.dispatch.esquemas(text)})
        self.assertEqual(main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(text),{'observar_imagem_recebida'})
        self.assertNotEqual(intent.interpretar('Não olhe o anexo A.png.').ferramenta_principal,'observar_imagem_recebida')

    def test_veja_received_image_requires_real_observation_not_textual_guess(self):
        text='Téo aqui. Veja a imagem recebida 5afdf7a6a340-B.png e diga o que você vê, em uma frase.'
        parsed=intent.interpretar(text)
        self.assertEqual(parsed.ferramenta_principal,'observar_imagem_recebida')
        self.assertEqual(parsed.parametros_sugeridos,{'nome':'5afdf7a6a340-B.png'})
        self.assertTrue(task_state.parece_tarefa(text))
        self.assertIn('observar_imagem_recebida',{s['function']['name'] for s in main.dispatch.esquemas(text)})
        self.assertEqual(main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(text),{'observar_imagem_recebida'})
        self.assertFalse(main.InterfaceHoshino._etapa_pode_ser_resolvida_pelo_modelo(text))
        for prefix in ('Não','Sem','Nem'):
            self.assertNotEqual(intent.interpretar(prefix+' veja o anexo B.png.').ferramenta_principal,
                                'observar_imagem_recebida')

    def test_receipt_preview_is_bounded_and_does_not_disguise_truncation(self):
        short='OPERACAO=ler\nDados: 3, 1, 4, 1, 5.'
        self.assertIn(short,main.InterfaceHoshino._apresentar_recibo_tarefa(short))
        long=main.InterfaceHoshino._apresentar_recibo_tarefa('resultado\n'+'x'*3000)
        self.assertLess(len(long),700)
        self.assertIn('não é o conteúdo completo',long)

    def test_memory_budget_keeps_whole_provenance_and_labels_deferred_records(self):
        first='tipo=hipótese;fonte=Alistair;confiança=0.0;evidência=msg-A'
        second='tipo=reflexão;fonte=LLM;confiança=0.4;evidência=msg-B;'+'x'*300
        with patch.object(prompting,'_seguro',return_value=''):
            block=prompting.bloco_contexto(conhecimentos=[first,second],memoria_max_chars=100,
                                          incluir_emocao=False,incluir_rede=False)
        self.assertIn(first,block);self.assertNotIn('evidência=msg-B',block)
        self.assertIn('1 registro(s) não incluídos; continuam armazenados',block)
        self.assertIn('não são fatos confirmados',block)

    def test_compaction_counts_dynamic_context_and_tools_below_six_turns(self):
        app=object.__new__(main.InterfaceHoshino);app.prompt_sistema='i'*6000;app.sys_log=Mock();app.pessoa={}
        app.chamar_modelo=AsyncMock(return_value={'content':'Pessoa A informou X; hipótese Y segue incerta.'})
        latest={'role':'user','content':'Bom dia.','_origem':{'message_id':'latest','autor_id':'usuario'}}
        messages=[{'role':'user','content':'old '*2250},{'role':'assistant','content':'old '*1000},latest]
        with patch.object(config,'CONTEXTO_MAX_TOKENS',8192),patch.object(config,'NUM_PREDICT',4096),\
             patch.object(main.compaction,'resgatar_duraveis',return_value=0),\
             patch.object(main.compaction,'aplicar',return_value='[RESUMO] Pessoa A informou X.') as commit:
            asyncio.run(app.compactar_se_precisar(messages,contexto_extra='d'*1000,
                ferramentas=[{'function':{'name':'read','description':'observação'}}]))
        self.assertEqual(messages[-1],latest);self.assertIs(messages[-1],latest)
        self.assertEqual(len(messages),2);commit.assert_called_once();app.chamar_modelo.assert_awaited_once()

    def test_failed_empty_or_unpersisted_summary_never_removes_history(self):
        for failure in ('model','empty','persist'):
            app=object.__new__(main.InterfaceHoshino);app.prompt_sistema='i'*6000;app.sys_log=Mock();app.pessoa={}
            app.chamar_modelo=AsyncMock(side_effect=RuntimeError('mock failure')) if failure=='model' else \
                AsyncMock(return_value={'content':'' if failure=='empty' else 'Resumo atribuído.'})
            messages=[{'role':'user','content':'old '*2250},{'role':'assistant','content':'old '*1000},
                      {'role':'user','content':'Bom dia.','_origem':{'message_id':'latest'}}]
            original=list(messages)
            with patch.object(config,'CONTEXTO_MAX_TOKENS',8192),patch.object(config,'NUM_PREDICT',4096),\
                 patch.object(main.compaction,'resgatar_duraveis',return_value=0),\
                 patch.object(main.compaction,'aplicar',side_effect=sqlite3.OperationalError('mock DB failure')):
                asyncio.run(app.compactar_se_precisar(messages,contexto_extra='d'*1000))
            self.assertEqual(messages,original,failure)

    def test_new_instruction_after_pause_is_not_replaced_by_old_image_result(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','image-pause-new-request','')
        original=task_state.iniciar_ou_continuar(key,'Gere uma imagem de colher no fundo branco.')
        task_state.definir_operacoes(key,[dict(ferramenta='estado_imagem',instrucao='Confira a colher anterior.')])
        task_state.pausar(key)
        text='Agora gere a imagem de um único tênis azul sobre fundo branco.'
        resumed=task_state.iniciar_ou_continuar(key,text)
        self.assertEqual(resumed.id,original.id)
        self.assertTrue(any(e['texto']==text.rstrip('.') and e['status']=='pending' for e in resumed.etapas))
        self.assertEqual(task_state.proxima_operacao(key)['ferramenta'],'estado_imagem')
        task_state.registrar_ferramenta(key,'estado_imagem','success','status=done path=colher.png')
        self.assertEqual(task_state.proxima_operacao(key)['ferramenta'],'gerar_imagem')

    def test_json_creation_cannot_be_reduced_to_calculator_only(self):
        text='Agora crie Ensaio-20261009/resultado.json com a soma e os números ordenados do desafio que leu.'
        self.assertTrue({'workspace','calcular'} <= main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(text))
        selected={s['function']['name'] for s in main.dispatch.contratos_tarefa(text)}
        self.assertTrue({'workspace','calcular'} <= selected)

    def test_argument_stage_preserves_attributed_read_and_calculation_receipts(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'operacao':'salvar',
            'caminho':'resultado.json','conteudo':'{"soma":14,"ordenados":[1,1,3,4,5]}','modo':'substituir'})})
        task=SimpleNamespace(id='isolated',chave='isolated')
        observations=[('workspace','OPERACAO=ler\nDados: 3, 1, 4, 1, 5.'),('calcular','14')]
        with patch.object(task_state,'contexto_operacao',return_value='Crie resultado.json'),\
             patch.object(task_state,'normalizar_argumentos_operacao',side_effect=lambda t,o,a:a):
            args,error=asyncio.run(app._obter_args_de_tarefa(task,
                {'ferramenta':'workspace','operacao':'salvar'},observacoes=observations))
        self.assertFalse(error)
        prompt=app.chamar_modelo.call_args.args[0][-1]['content']
        self.assertIn('Dados: 3, 1, 4, 1, 5.',prompt)
        self.assertIn('"ferramenta": "calcular", "saida": "14"',prompt)
        self.assertEqual(json.loads(args['conteudo'])['soma'],14)

    def test_image_queue_is_pending_not_a_verified_finished_image(self):
        queued='IMAGEM_ENFILEIRADA=SIM\nJOB_ID=img-abcdef1234\nRESOLUCAO=512x512\nSTATUS=queued\nUse estado_imagem.'
        result=main.dispatch._resultado_mecanico('gerar_imagem',queued)
        self.assertEqual(result['status'],'pending'); self.assertTrue(result['outcome_pending'])
        self.assertFalse(result['ok']); self.assertFalse(result['verified']); self.assertFalse(result['auto_retry'])
        self.assertTrue(result['requires_verification'])
        self.assertFalse(main.dispatch._resultado_mecanico('gerar_imagem','O exemplo diz: '+queued)['outcome_pending'])

    def test_pending_image_resumes_verification_without_resubmitting_generation(self):
        init_db.DB_PATH=config.DB_PATH;init_db.init_database(verbose=False)
        key=('test','pending-image-receipt','')
        task_state.iniciar_ou_continuar(key,'Gere uma imagem de uma colher branca.')
        output='IMAGEM_ENFILEIRADA=SIM\nJOB_ID=img-abcdef1234\nRESOLUCAO=512x512\nSTATUS=queued\nUse estado_imagem.'
        receipt=main.dispatch._resultado_mecanico('gerar_imagem',output)
        task_state.registrar_ferramenta(key,'gerar_imagem','pending',output,recibo=receipt)
        task_state.pausar(key)
        resumed=task_state.iniciar_ou_continuar(key,'continue')
        self.assertEqual(resumed.status,'active')
        self.assertEqual(task_state.proxima_operacao(key)['ferramenta'],'estado_imagem')

    def test_read_file_stage_cannot_be_replaced_by_directory_listing(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock(return_value={'content':json.dumps({'operacoes':[
            dict(ferramenta='workspace',operacao='listar',instrucao='Liste a oficina.')], 'concluida':False})})
        task=SimpleNamespace(id='isolated',chave='isolated',workspace_root='',known_paths=[],ultimo_resultado='',
            etapas=[dict(status='pending',texto='Leia o arquivo Ensaio-20261009/desafio.txt na sua oficina.')])
        with patch.object(task_state,'definir_operacoes',return_value=task) as save:
            ok,error=asyncio.run(app._planejar_operacoes_de_tarefa(task))
        self.assertTrue(ok,error)
        self.assertEqual(save.call_args.args[1][0]['operacao'],'ler')

    def test_scroll_arguments_keep_explicit_up_direction_and_tab(self):
        app=object.__new__(main.InterfaceHoshino)
        app.chamar_modelo=AsyncMock()
        args,error=asyncio.run(app._obter_args_de_tarefa(SimpleNamespace(id='isolated'),
            dict(ferramenta='browser_rolar',etapa='Agora role a mesma aba aba-01 400 pixels para cima.',
                 restantes=['browser_rolar','browser_info'])))
        self.assertEqual(args,dict(aba='aba-01',pixels=-400));self.assertFalse(error)
        app.chamar_modelo.assert_not_called()

    def test_explicit_no_execution_does_not_create_or_attach_task(self):
        text='Navegador, arquivos, apps. Quem é você? Não execute ações neste turno.'
        self.assertTrue(intent.execucao_proibida(text))
        self.assertEqual(intent.interpretar(text).acao,'conversar')
        self.assertFalse(task_state.parece_tarefa(text))
        with patch.object(task_state,'_schema'), patch.object(task_state,'pausar') as pause, \
             patch.object(task_state,'carregar') as load:
            self.assertIsNone(task_state.iniciar_ou_continuar('isolated',text))
        pause.assert_called_once_with('isolated'); load.assert_not_called()
        self.assertFalse(intent.execucao_proibida('Não execute código. Abra a Steam.'))

    def test_known_browser_and_app_actions_cannot_be_replaced_by_text_stage(self):
        for text, tool in (('Role a aba aba-01 700 pixels para baixo.', 'browser_rolar'),
                           ('Abra a Steam.', 'abrir_aplicativo'),
                           ('Crie os arquivos A.txt e B.txt.', 'workspace')):
            self.assertFalse(main.InterfaceHoshino._etapa_pode_ser_resolvida_pelo_modelo(text))
            self.assertIn(tool, main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(text))
        self.assertNotIn('browser_abrir',main.InterfaceHoshino._ferramentas_obrigatorias_da_etapa(
            'Não abra https://www.youtube.com. Confira a instrução.'))

    def test_16k_uses_short_operational_text_without_cutting_identity_rules(self):
        with patch.object(config,'CONTEXTO_MAX_TOKENS',16384):
            full=prompting.montar_prompt_sistema(compacto=False)
            automatic=prompting.montar_prompt_sistema()
        self.assertLess(len(automatic),len(full)-1500)
        for section in ('identidade','honestidade','silencio','expressao','acao','continuidade'):
            for rule in prompting._carregar(prompting.CONSTITUICAO_PATH).get(section,[]):
                self.assertIn(rule,automatic)
        self.assertIn(prompting.ESCRITA_CURTO,automatic)
        self.assertIn('CASA COMPARTILHADA',automatic)

    def test_explicit_full_prompt_is_still_available(self):
        with patch.object(config,'CONTEXTO_MAX_TOKENS',16384):
            full=prompting.montar_prompt_sistema(compacto=False)
        self.assertIn(prompting.FERRAMENTAS,full)


class LAN(unittest.TestCase):
    def discover(self, packets):
        sock=Mock()
        sock.recvfrom.side_effect=list(packets)+[socket.timeout()]*20
        clock=iter(i*.1 for i in range(50))
        with patch('socket.socket',return_value=sock),patch('time.monotonic',side_effect=lambda:next(clock)):
            result=json.loads(minecraft.descobrir_lan(.6))
        sock.close.assert_called_once()
        return result

    def test_standard_unicode_duplicates_and_multiple_worlds(self):
        a=('[MOTD]Mundo do Gustavo — floresta 🌲[/MOTD][AD]51234[/AD]'.encode(),('192.168.1.3',4445))
        b=(b'[MOTD]Outro mundo[/MOTD][AD]51235[/AD]',('192.168.1.4',4445))
        result=self.discover([a,a,b])
        self.assertTrue(result['ok'])
        self.assertEqual([m['port'] for m in result['mundos']],[51234,51235])
        self.assertIn('🌲',result['mundos'][0]['motd'])

    def test_invalid_incomplete_and_timeout_are_not_connections(self):
        for packet in (b'[MOTD]a[/MOTD][AD]0[/AD]',b'[MOTD]a[/MOTD][AD]65536[/AD]',
                       b'[MOTD]a[/MOTD][AD]bad[/AD]',b'[MOTD]a[/MOTD][AD]123',b'\xff'):
            self.assertEqual(self.discover([(packet,('192.168.1.3',4445))])['mundos'],[])
        self.assertEqual(self.discover([])['mundos'],[])

    def test_manual_connection_keeps_explicit_host_port(self):
        with patch.object(minecraft,'ponte_saude',return_value='{"protocol":3}'),\
             patch.object(minecraft,'_rpc',return_value='manual') as rpc:
            minecraft.conectar(host='192.168.1.8',port=52123,username='LilithMC')
        self.assertEqual(rpc.call_args_list[0].args[1]['host'],'192.168.1.8')
        self.assertEqual(rpc.call_args_list[0].args[1]['port'],52123)


class Stream(unittest.TestCase):
    def test_hunyuan_answer_protocol_wrapper_is_not_visible_speech_or_prose(self):
        from core.audio_text import clean_for_speech
        self.assertEqual(main.limpar_raciocinio('<think>privado</think>\n<answer>Eu sou Lilith.</answer>'),
                         'Eu sou Lilith.')
        self.assertEqual(clean_for_speech('<answer>Eu sou Lilith.</answer>'),'Eu sou Lilith.')
        self.assertEqual(main.limpar_raciocinio('Código: `<answer>`'), 'Código: `<answer>`')

    def test_unclosed_private_think_never_leaks_to_final_content(self):
        self.assertEqual(main.limpar_raciocinio('<think>raciocínio sem fechamento'), '')

    def post(self, frames, on_content=None):
        response=Mock(iter_lines=Mock(return_value=iter(json.dumps(f) if not isinstance(f,str) else f for f in frames)))
        with patch.object(main.requests,'post',return_value=response):
            try:
                return main.InterfaceHoshino._post_ollama_stream({'model':'fixture'},'request-stream',on_content)
            finally: response.close.assert_called_once()

    def test_done_is_required_for_final_response(self):
        with self.assertRaisesRegex(RuntimeError,'EOF'):
            self.post([{'message':{'content':'Uma sentença estável.'},'done':False}])
        result=self.post([{'message':{'content':'Completa.'},'done':False},{'done':True}])
        self.assertEqual(result['content'],'Completa.')

    def test_error_invalid_frame_and_timeout_never_succeed(self):
        for frames in ([{'error':'backend failed'}],['invalid JSON'],[{'message':{'content':'parcial'},'done':False}],
                       [{'message':{'content':'cortada'},'done':True,'done_reason':'length'}]):
            with self.assertRaises(RuntimeError): self.post(frames)
        with patch.object(main.time,'monotonic',side_effect=[0,config.TIMEOUT_LLM+1]):
            with self.assertRaises(TimeoutError): self.post([{'done':True}])

    def test_partial_tool_cannot_reach_dispatch(self):
        call={'function':{'name':'minecraft_ir_para','arguments':'{"x":'}}
        for frames in ([{'message':{'tool_calls':[call]}}],
                       [{'message':{'tool_calls':[call]},'done':True}]):
            with patch.object(main.dispatch,'executar_resultado') as execute:
                with self.assertRaises(RuntimeError): self.post(frames)
                execute.assert_not_called()
        result=self.post([{'message':{'tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]},'done':True}])
        self.assertEqual(result['tool_calls'][0]['function']['name'],'minecraft_estado')

    def test_incomplete_generation_invalidates_corresponding_speech(self):
        context={'channel':'localhub','validator':lambda _:True,'cancelled':lambda:False,'streams':[]}
        stream=Mock()
        token=speech_stream.context.set(context)
        self.addCleanup(speech_stream.context.reset,token)
        app=object.__new__(main.InterfaceHoshino)
        with patch.object(speech_stream,'SpeechStream',return_value=stream),\
             patch.object(main.gpu_resource,'lease',return_value=nullcontext({'backend':'cpu'})),\
             patch.object(main.gpu_resource,'routed_payload',side_effect=lambda p,_:p),\
             patch.object(app,'_post_ollama_stream',side_effect=RuntimeError('EOF')):
            with self.assertRaises(RuntimeError): app._post_ollama_stream_com_lease({'model':'fixture'},'request-stream')
        stream.stop.assert_called_once_with('generation_failed')
        stream.finish.assert_not_called()
        self.assertEqual(context['streams'],[stream])

    def test_custom_response_adapter_cannot_bypass_done_or_complete_tool(self):
        for result in ({'message':{'content':'parcial'}},
                       {'done':True,'message':{'tool_calls':[{'function':{'name':'workspace','arguments':'{"x":'}}]}},
                       {'done':True,'done_reason':'length','message':{'content':'parcial'}}):
            response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:result,close=Mock())
            with patch.object(main.requests,'post',return_value=response):
                with self.assertRaises(RuntimeError): main.InterfaceHoshino._post_ollama_stream({'model':'fixture'},'request')
            response.close.assert_called_once()


class AlistairDurable(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='alistair-r4-'); self.addCleanup(self.tmp.cleanup)
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        base=Path(self.tmp.name)
        identity=base/'identity.json'; identity.write_text('{"nome":"Alistair"}')
        for obj,key,value in ((config,'DB_PATH',str(base/'mind.db')),(config,'SELF_MODEL_PATH',str(identity)),
                              (bus,'DB_PATH',base/'bus.db'),(job_bus,'DB_PATH',base/'jobs.db')):
            self.stack.enter_context(patch.object(obj,key,value))
        self.stack.enter_context(patch('alistair_runner.alistair_backend.configured',return_value=None))
        self.stack.enter_context(patch('core.activity_context.build',return_value=({},'')))
        self.al=Alistair()

    def message(self, sender='usuario', text='Olá'):
        sent=bus.send(sender,'alistair',text)
        return next(m for m in bus.inbox('alistair',200) if m['id']==sent['id'])

    def seed_recall(self,rows):
        with closing(sqlite3.connect(config.DB_PATH)) as db,db:
            db.executemany('INSERT INTO alistair_turns VALUES(?,?,?,?,?)',rows)

    def recall(self,text,sender='usuario'):
        with closing(sqlite3.connect(config.DB_PATH)) as db:
            return recall_history(db,sender,text)

    def test_recall_name_and_recent_correction_survive_noise_restart(self):
        self.seed_recall([('first','usuario','Meu nome é Nome Antigo.','ok',0),('changed','usuario','Corrigindo: me chame de Aurora.','ok',8)]+
                        [(str(i),'usuario',f'Conversa sobre astronomia número {i}','ok',i+10) for i in range(70)])
        self.al=Alistair();_,recalled,info=self.recall('Qual meu nome?')
        ids=[r['source_id'] for r in recalled]
        self.assertIn('changed',ids);self.assertIn('first',ids);self.assertLess(ids.index('changed'),ids.index('first'))
        self.assertTrue(next(r for r in recalled if r['source_id']=='changed')['possible_correction'])
        self.assertTrue(all(r['sender']=='usuario' and r['type']=='citacao_historica' for r in recalled))
        self.assertFalse(info['window_limited'])

    def test_recall_accents_rules_and_configuration_not_first_four(self):
        self.seed_recall([(str(i),'usuario','Olá assunto sem relação','ok',i) for i in range(5)]+
                        [('rule','usuario','Nossa regra: nunca iniciar o jogo sem perguntar.','ok',6),
                         ('config','usuario','Configuração: o microfone usa volume 45.','ok',7)]+
                        [(f'later-{i}','usuario','Mais uma conversa diferente','ok',20+i) for i in range(50)])
        self.assertIn('rule',[r['source_id'] for r in self.recall('Quais os combinados?')[1]])
        self.assertIn('config',[r['source_id'] for r in self.recall('Qual a configuracao do microfone?')[1]])

    def test_standing_rule_reused_without_explicit_memory_question(self):
        self.seed_recall([('first','usuario','Oi','ok',0),
                         ('rule','usuario','Combinado: pergunte antes de acordar alguém.','ok',1)]+
                        [(str(i),'usuario','Astronomia','ok',i+2) for i in range(12)])
        recalled=self.recall('Quero conversar com a Lilith')[1]
        rule=next(r for r in recalled if r['source_id']=='rule')
        self.assertTrue(rule['possible_rule']);self.assertEqual(rule['type'],'citacao_historica')

    def test_recall_does_not_promote_own_output_or_cross_senders(self):
        self.seed_recall([('u','usuario','Oi','Seu nome é INVENTADO',0),('l','lilith','Meu nome é SEGREDO_LILITH','ok',1)]+
                        [(str(i),'usuario','outro assunto','ok',i+2) for i in range(8)])
        text=json.dumps(self.recall('Qual meu nome?')[1],ensure_ascii=False)
        self.assertNotIn('INVENTADO',text);self.assertNotIn('SEGREDO_LILITH',text)
        self.assertIn('u',text)

    def test_recall_quotes_questions_and_corrections_remain_attributed_not_facts(self):
        self.seed_recall([('q','usuario','Imagine que meu nome seja Fantasia?','ok',0)]+
                        [(str(i),'usuario','outro assunto','ok',i+1) for i in range(8)])
        record=self.recall('Qual o nome?')[1][0]
        self.assertEqual(record['type'],'citacao_historica');self.assertEqual(record['text'],'Imagine que meu nome seja Fantasia?')
        self.assertIn('perguntas, citações, hipóteses',OPERATIONAL_RULES)

    def test_recall_bounded_with_old_format_and_budget(self):
        self.seed_recall([(str(i),'usuario','Nome configuração regra '+('x'*700),'ok',i) for i in range(2010)])
        recent,recalled,info=self.recall('Qual nome e configuração?')
        self.assertEqual(len(recent),4);self.assertEqual(info['scanned'],2000);self.assertTrue(info['window_limited'])
        self.assertLessEqual(len(recalled),8);self.assertLessEqual(sum(len(r['text']) for r in recalled),3600)
        self.assertTrue(any(r['excerpt'] for r in recalled))

    def test_operational_prompt_has_limits_without_personal_seeds(self):
        message=self.message(text='Projete e execute uma migração de infraestrutura inteira.')
        answer='Isso é grande demais para eu executar com segurança. Posso organizar os requisitos primeiro.'
        with patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':answer}}) as infer,patch.object(self.al,'call_tool') as tools:
            self.assertEqual(self.al.chat(message),answer);tools.assert_not_called()
        prompt=infer.call_args.args[0]['messages'][0]['content']
        self.assertIn('Não recuso uma consulta simples',prompt);self.assertIn('decisão de alto impacto',prompt)
        self.assertIn('não os dados pessoais do usuário',prompt);self.assertNotIn('Gustavo',prompt)

    def test_alistair_snapshot_does_not_embed_historical_job_payloads(self):
        jobs=[{'id':f'old-{i}','entity':'hoshino','kind':'audio_tts','status':'done',
               'details':{'text':'historico enorme '*10000}} for i in range(100)]
        jobs += [{'id':f'live-{i}','entity':'lilith','kind':'image','status':'running'} for i in range(8)]
        with patch.object(job_bus,'status',return_value=jobs),\
             patch.object(resource_manager,'status',return_value=[]),\
             patch('alistair_runner.world_state.brief',return_value={'available':True,'fresh_facts':{'central.resources':jobs,'system.load1':0.5}}):
            snapshot=self.al.snapshot()
            message=self.message(text='Olá, como você está?')
            with patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':'Oi!'}}) as infer:
                self.al.chat(message)
        self.assertEqual(snapshot['job_counts']['done'],100)
        self.assertEqual(snapshot['active_jobs_omitted'],2)
        self.assertEqual(len(snapshot['jobs']),6)
        self.assertNotIn('historico enorme',json.dumps(snapshot))
        self.assertLess(len(json.dumps(snapshot)),2000)
        prompt=infer.call_args.args[0]['messages'][0]['content']
        self.assertNotIn('historico enorme',prompt)
        self.assertLess(len(prompt),9000)

    def test_initial_context_budget_preserves_inputs_rules_and_recalled_correction(self):
        self.seed_recall([('first','usuario','Meu nome é Antigo.','ok',0),
                          ('correction','usuario','Corrigindo: me chame de Aurora.','ok',1)] +
                         [(str(i),'usuario',f'Combinado {i}: preserve os arquivos de teste.',
                           'explicação antiga '*300,i+2) for i in range(8)])
        message=self.message(text='Qual meu nome? Não acorde ninguém.')
        with patch.object(config,'NUM_CTX',4096),patch.object(config,'NUM_PREDICT',768),\
             patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':'Aurora.'}}) as infer:
            self.al.chat(message)
        payload=infer.call_args.args[0];messages=payload['messages'][:-1]  # resposta final anexada após HTTP
        self.assertEqual(messages[-1]['content'],message['text'])
        self.assertIn('Corrigindo: me chame de Aurora.',messages[0]['content'])
        for i in range(4,8):
            self.assertIn(f'Combinado {i}: preserve os arquivos de teste.',[m['content'] for m in messages])
        self.assertIn('respostas anteriores omitidas',messages[0]['content'])
        _,required=resource_manager.context_requirement(messages,payload['tools'],output_max=768)
        self.assertLessEqual(required,4096)

    def test_oversized_current_input_is_not_cut_or_sent_to_model(self):
        message=self.message(text='Entrada atual integral: '+('x'*11000))
        with patch.object(config,'NUM_CTX',4096),patch.object(config,'NUM_PREDICT',768),\
             patch.object(self.al,'infer') as infer:
            with self.assertRaisesRegex(ValueError,'Contexto excede'):
                self.al.chat(message)
        infer.assert_not_called()

    def test_tool_round_can_drop_only_old_replies_without_repeating_effect(self):
        self.seed_recall([(str(i),'usuario',f'Combinado {i}: não apagar arquivos.',
                          'resposta antiga '*30,i) for i in range(4)])
        message=self.message(text='Acorde Hoshino uma vez e confirme o recibo.')
        answers=[{'message':{'role':'assistant','tool_calls':[{'function':{
            'name':'entidades_acordar','arguments':{'entidade':'hoshino'}}}]}},
                 {'message':{'role':'assistant','content':'Pedido registrado.'}}]
        with patch.object(config,'NUM_CTX',4096),patch.object(config,'NUM_PREDICT',768),\
             patch.object(self.al,'call_tool',return_value={'accepted':True,'detail':'x'*1200}) as execute,\
             patch.object(self.al,'infer',side_effect=answers) as infer:
            self.assertEqual(self.al.chat(message),'Pedido registrado.')
        execute.assert_called_once();self.assertEqual(infer.call_count,2)
        messages=infer.call_args.args[0]['messages']
        self.assertTrue(any(m['role']=='tool' and 'x'*1200 in m['content'] for m in messages))
        self.assertTrue(any(m.get('tool_calls') for m in messages))
        for i in range(4):
            self.assertIn(f'Combinado {i}: não apagar arquivos.',[m['content'] for m in messages if m['role']=='user'])

    def test_state_query_replaces_only_stale_snapshot_and_keeps_receipt(self):
        message=self.message(text='Consulte quem está acordado.')
        answers=[{'message':{'role':'assistant','tool_calls':[{'function':{
            'name':'central_estado','arguments':{}}}]}},
                 {'message':{'role':'assistant','content':'Hoshino.'}}]
        with patch.object(self.al,'snapshot',return_value={'marker':'estado_atual'}) as snapshot, \
             patch.object(self.al,'infer',side_effect=answers) as infer:
            self.al.chat(message)
        messages=infer.call_args.args[0]['messages']
        self.assertNotIn('estado_velho',messages[0]['content'])
        self.assertIn('IDENTIDADE PRÓPRIA',messages[0]['content'])
        self.assertNotIn(message['id'],messages[0]['content'])  # ids ficam nos registros, não invalidam o prefixo
        snapshot.assert_called_once()
        self.assertTrue(any(m['role']=='tool' and 'estado_atual' in m['content'] for m in messages))

    async def test_crash_restart_is_held_and_later_messages_are_visible(self):
        bad=self.message(text='antiga')
        bus.processing_outcome(bad['id'],'alistair','processing')  # queda depois do início
        self.al=Alistair()
        good=self.message('hoshino','Eu sou Hoshino.')
        self.assertNotIn(bad['id'],[m['id'] for m in bus.inbox('alistair',200)])
        with patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':'Olá, Hoshino.'}}) as infer:
            self.assertTrue(await self.al.process_message(good))
        system=infer.call_args.args[0]['messages'][0]['content']
        self.assertIn('"sender": "hoshino"',system)
        self.assertNotIn(good['id'],system)
        with closing(sqlite3.connect(config.DB_PATH)) as db:
            self.assertEqual(db.execute('SELECT input FROM alistair_turns WHERE source_id=?',(good['id'],)).fetchone()[0],good['text'])
        replies=bus.conversation('alistair','hoshino')
        self.assertEqual(len([m for m in replies if m['sender']=='alistair']),1)
        self.assertEqual(bus.peek('alistair')[0]['id'],bad['id'])

    async def test_many_failed_messages_do_not_hide_new_message_after_restart(self):
        for i in range(12):
            message=self.message(text=f'falha {i}')
            with patch.object(self.al,'chat',side_effect=RuntimeError('worker crash')):
                self.assertFalse(await self.al.process_message(message))
        self.al=Alistair()
        fresh=self.message(text='nova')
        self.assertEqual([m['id'] for m in bus.inbox('alistair',200)],[fresh['id']])
        with patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':'Resposta nova.'}}):
            self.assertTrue(await self.al.process_message(fresh))
        self.assertEqual(bus.inbox('alistair',200),[])
        self.assertEqual(len(bus.peek('alistair',200)),12)

    async def test_alistair_false_unload_remains_unconfirmed(self):
        bus.request_sleep('alistair')
        with patch.object(self.al,'load'),patch.object(self.al,'unload',return_value=False),\
             patch.object(self.al,'heartbeat',new=AsyncMock()):
            await self.al.run()
        self.assertEqual(bus.presence('alistair')['detail'],'processo encerrado; unload=unconfirmed')

    def test_first_contact_survives_more_than_four_turns_and_restart(self):
        with closing(sqlite3.connect(config.DB_PATH)) as db,db:
            for i in range(12):
                db.execute('INSERT INTO alistair_turns VALUES(?,?,?,?,?)',
                    (f'old-{i}','usuario','Meu nome é Gustavo e moro em Marte.' if i==0 else f'assunto {i}','ok',float(i)))
        self.al=Alistair()
        message=self.message(text='Onde eu moro?')
        with patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':'Você disse Marte.'}}) as infer:
            self.al.chat(message)
            self.al.chat(message)
        self.assertEqual(infer.call_count,1)
        system=infer.call_args.args[0]['messages'][0]['content']
        self.assertIn('Marte',system); self.assertIn('old-0',system)
        other=self.message('lilith','Onde eu moro?')
        with patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':'Não sei.'}}) as infer:
            self.al.chat(other)
        self.assertNotIn('Marte',infer.call_args.args[0]['messages'][0]['content'])

    def test_uncertain_effect_is_never_repeated_by_next_tool_round(self):
        # Ação explícita; cumprimentos completos não oferecem ferramentas.
        message=self.message(text='Acorde Lilith e confira o resultado.')
        tool={'role':'assistant','tool_calls':[{'function':{'name':'entidades_acordar','arguments':{'entidade':'lilith'}}}]}
        with patch.object(Alistair,'infer',return_value={'message':tool}) as infer,\
             patch.object(Alistair,'call_tool',side_effect=RuntimeError('effect uncertain')) as call:
            for instance in (self.al,Alistair()):
                with self.assertRaises(ActionUncertain): instance.chat(message)
            self.assertEqual(infer.call_count,2)
            self.assertEqual(call.call_count,1)


class SleepAndRPC(unittest.TestCase):
    def test_entity_exit_does_not_claim_failed_unload_succeeded(self):
        import entity_runner
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        import iniciar_entidades as launcher
        path=Path(config.RUNTIME_DIR)/'entity.lock'
        path.parent.mkdir(parents=True,exist_ok=True)
        with patch.object(main,'InterfaceHoshino',return_value=Mock()),\
             patch.object(config,'RAIZ',Path(config.RUNTIME_DIR).parent),\
             patch('core.ollama_lifecycle.encerrar',return_value=False),\
             patch.object(entity_runner.signal,'signal'),patch.object(bus,'set_status') as status:
            self.assertEqual(entity_runner.main(),0)
        self.assertIn('processo encerrado; unload=unconfirmed',status.call_args.args[2])
        self.assertNotIn('confirmed',status.call_args.args[2].replace('unconfirmed',''))

    def test_sleep_prevents_late_speech_submission(self):
        service=object.__new__(audio_service.AudioService)
        with patch.object(bus,'sleep_requested',return_value=True):
            with self.assertRaises(ValueError): service.submit_speech('hoshino',text='fala antiga')
            with self.assertRaises(ValueError): service.submit_stream('hoshino','stream-old')

    def test_sleep_interrupts_only_target_tts_not_other_tts_or_asr(self):
        service=object.__new__(audio_service.AudioService)
        service.playback_owner='fixture-current-central'
        service.lock=threading.RLock()
        service.cancels={k:threading.Event() for k in ('h','l','asr')}
        jobs={'h':dict(entity='hoshino',kind='audio_tts',status='running'),
              'l':dict(entity='lilith',kind='audio_tts',status='running'),
              'asr':dict(entity='hoshino',kind='audio_asr',status='running')}
        service.get=jobs.__getitem__
        service.cancel=Mock(side_effect=lambda k:service.cancels[k].set())
        self.assertEqual(service.interrupt_entity('hoshino'),['h'])
        self.assertTrue(service.cancels['h'].is_set())
        self.assertFalse(service.cancels['l'].is_set())
        self.assertFalse(service.cancels['asr'].is_set())

    def test_own_bridge_is_closed_external_bridge_is_never_signalled(self):
        own=Mock(pid=12345); own.poll.return_value=None
        with patch.object(minecraft_launcher,'_bridge_proc',own):
            self.assertTrue(minecraft_launcher.parar_ponte_propria())
        own.terminate.assert_called_once(); own.wait.assert_called_once(); own.kill.assert_not_called()
        with patch.object(minecraft_launcher,'_bridge_proc',None),patch('os.kill') as kill:
            self.assertFalse(minecraft_launcher.parar_ponte_propria())
            kill.assert_not_called()

    def test_foreign_receipts_and_mutable_timeout_remain_uncertain(self):
        health={'protocol':3,'state':{'sessionId':'session'}}
        for field,value in (('request_id','foreign'),('entity_id','lilith'),('session_id','old'),('parent_id','foreign')):
            def response(*a,**kwargs):
                data={**kwargs['json'],'ok':True,'resultado':'sucesso',field:value}
                return SimpleNamespace(raise_for_status=lambda:None,json=lambda:data)
            with diagnostics.context(turn_id='turn-rpc',tool_id='tool-rpc'),\
                 patch.object(minecraft,'_ponte_compativel',return_value=(health,'')),\
                 patch.object(minecraft.requests,'post',side_effect=response) as post:
                self.assertTrue(minecraft._rpc('goto',{'x':1}).startswith('RESULTADO_INCERTO'))
                self.assertEqual(post.call_count,1)
        with patch.object(minecraft,'_ponte_compativel',return_value=(health,'')),\
             patch.object(minecraft.requests,'post',side_effect=minecraft.requests.Timeout) as post:
            self.assertTrue(minecraft._rpc('craft',{}).startswith('RESULTADO_INCERTO'))
            self.assertEqual(post.call_count,1)


class SleepInference(unittest.IsolatedAsyncioTestCase):
    def fixture(self):
        app = object.__new__(main.InterfaceHoshino)
        app._draining = False
        app._obter_trava_modelo = lambda: nullcontext()
        app._post_ollama_json_com_lease = Mock(return_value=SimpleNamespace(
            raise_for_status=lambda:None, json=lambda:{'done':True,'done_reason':'stop','message': {'content':'fixture'}}, status_code=200))
        return app

    def model_setup(self):
        stack = ExitStack()
        stack.enter_context(patch.object(main.resource_manager, 'choose_executor',
            return_value=SimpleNamespace(model='fixture', num_ctx=4096, tier='principal')))
        stack.enter_context(patch.object(main.resource_manager, 'thinking_for_cycle', return_value=False))
        stack.enter_context(patch.object(main, 'progress', Mock()))
        stack.enter_context(patch.object(config, 'STREAM_LLM', False))
        # A fixture de sono possui janela 4096: reserva saída menor que ela,
        # como o contrato adaptativo exige; não estamos testando overflow aqui.
        stack.enter_context(patch.object(config, 'NUM_PREDICT', 512))
        return stack

    async def test_inference_duration_uses_monotonic_not_wall_clock(self):
        app=self.fixture()
        wall=Mock();wall.now.side_effect=AssertionError('Relógio de parede não mede duração')
        clock=SimpleNamespace(monotonic=Mock(side_effect=[100.0,100.125]))
        with self.model_setup(),patch.object(main,'datetime',wall),patch.object(main,'time',clock), \
             patch.object(main.diagnostics,'llm_end') as end:
            result=await app.chamar_modelo([{'role':'user','content':'fixture'}])
        self.assertEqual(result['content'],'fixture')
        self.assertEqual(end.call_args.args[2],125)
        wall.now.assert_not_called()

    async def test_nonstream_partial_response_is_not_completed_or_automatically_retried(self):
        for data in ({'message':{'content':'parcial'}}, {'done':True,'done_reason':'length','message':{'content':'parcial'}}):
            app=self.fixture();app._post_ollama_json_com_lease.return_value.json=lambda:data
            with self.model_setup(),self.assertRaisesRegex(RuntimeError,'INCOMPLETA'):
                await app.chamar_modelo([{'role':'user','content':'fixture'}])
            app._post_ollama_json_com_lease.assert_called_once()

    async def test_sleep_blocks_inference_before_model_selection(self):
        app = self.fixture(); app._draining = True
        with patch.object(main.resource_manager, 'choose_executor') as choose:
            with self.assertRaises(main.TurnoCancelado):
                await app.chamar_modelo([{'role':'user','content':'fixture'}])
        choose.assert_not_called()
        app._post_ollama_json_com_lease.assert_not_called()

    async def test_sleep_while_waiting_model_lock_does_not_start_request(self):
        app = self.fixture()
        class Lock:
            async def __aenter__(self): app._draining = True
            async def __aexit__(self, *args): pass
        app._obter_trava_modelo = lambda: Lock()
        with self.model_setup(), self.assertRaises(main.TurnoCancelado):
            await app.chamar_modelo([{'role':'user','content':'fixture'}])
        app._post_ollama_json_com_lease.assert_not_called()
        self.assertEqual(getattr(app, '_llm_http_ativos', 0), 0)

    async def test_sleep_prevents_recovery_and_retry_after_connection_failure(self):
        app = self.fixture()
        class Lock:
            async def __aenter__(self): pass
            async def __aexit__(self, *args): pass
        app._obter_trava_modelo = lambda: Lock()
        def failed(*args, **kwargs):
            app._draining = True
            raise main.requests.exceptions.ConnectionError('fixture disconnected')
        app._post_ollama_json_com_lease.side_effect = failed
        with self.model_setup(), patch.object(main.ollama_lifecycle, 'recuperar') as recover, \
             self.assertRaises(main.TurnoCancelado):
            await app.chamar_modelo([{'role':'user','content':'fixture'}])
        app._post_ollama_json_com_lease.assert_called_once()
        recover.assert_not_called()
        self.assertEqual(app._llm_http_ativos, 0)

    async def test_sleep_blocks_new_tool_step_without_turn_callback(self):
        app = self.fixture(); app._draining = True
        with patch.object(main.dispatch, 'executar_resultado') as execute, \
             self.assertRaises(main.TurnoCancelado):
            await app._executar_chamadas_da_etapa(
                [{'function': {'name':'browser_abrir', 'arguments': {'url':'https://example.org/'}}}],
                SimpleNamespace(), 1, set())
        execute.assert_not_called()


class ExtractionContracts(unittest.IsolatedAsyncioTestCase):
    def fixture(self):
        app = object.__new__(main.InterfaceHoshino)
        app._memory_generation = 0
        app.sys_log = Mock()
        return app

    async def test_extractor_requests_bounded_array_without_reasoning(self):
        app = self.fixture()
        app.chamar_modelo = AsyncMock(return_value={'content': '[]'})
        origin = {'autor_id': 'usuario', 'ouvinte_id': 'lilith', 'message_id': 'fixture-only'}
        with patch.object(main.scribe, 'conhecido_sobre', return_value=[]), \
             patch.object(main.scribe, 'aplicar_extracao', return_value=[]) as apply:
            await app.extrair_memoria('Abra a página de teste, sem dados pessoais.', 'Falhou.', origem=origin)
        kwargs = app.chamar_modelo.call_args.kwargs
        self.assertEqual(kwargs['priority'], 5)
        self.assertEqual(kwargs['formato'], main.scribe.SCHEMA_EXTRACAO)
        self.assertEqual(kwargs['formato']['type'], 'array')
        self.assertEqual(kwargs['formato']['maxItems'], 8)
        self.assertTrue(kwargs['forcar_sem_pensar'])
        self.assertFalse(kwargs['think_override'])
        apply.assert_called_once_with('[]', origem=origin, revisoes=None)

    async def test_extraction_timeout_does_not_commit_or_claim_learning(self):
        app = self.fixture()
        app.chamar_modelo = AsyncMock(side_effect=TimeoutError('fixture timeout'))
        with patch.object(main.scribe, 'conhecido_sobre', return_value=[]), \
             patch.object(main.scribe, 'aplicar_extracao') as apply, \
             patch.object(diagnostics, 'emit') as emit:
            await app.extrair_memoria('Uma entrada de teste suficientemente longa.', 'Sem resultado.')
        apply.assert_not_called()
        app.sys_log.write.assert_not_called()
        emit.assert_called_once_with('memory.extraction_failed', level='ERROR',
                                    error_type='TimeoutError', auto_retry=False)

    def test_extraction_schema_preserves_types_zero_and_missing_confidence(self):
        items = main.scribe.SCHEMA_EXTRACAO['items']
        props = items['properties']
        self.assertTrue({'observacao','hipotese','reflexao','interpretacao','inferencia'} <=
                        set(props['tipo']['enum']))
        self.assertEqual(props['confianca']['minimum'], 0)
        self.assertIn('null', props['confianca']['type'])
        self.assertNotIn('confianca', items['required'])


class Trace(unittest.IsolatedAsyncioTestCase):
    async def test_actual_turn_memory_tool_rpc_tts_playback_are_correlated(self):
        from test_mensagens_causalidade import app_fixture
        init_db.DB_PATH=config.DB_PATH; init_db.init_database(verbose=False)
        app=app_fixture()
        app.extrair_memoria=AsyncMock()  # extrator já possui teste próprio; sem inferência extra
        app.atualizar_pessoa=Mock()
        sent=bus.send('usuario','hoshino','Meu nome é Gustavo. Consulte o estado Minecraft.',
                      metadata={'submission_id':'submission-trace'})
        incoming=next(m for m in bus.inbox('hoshino',200) if m['id']==sent['id'])
        llm=[]; rpc=[]
        def post(url,**kwargs):
            payload=kwargs['json']
            if url.endswith('/rpc'):
                rpc.append(payload)
                result={**payload,'ok':True,'resultado':{'connected':True,'verified':True,'health':20,
                    'sessionId':'session-trace','connectionState':'ready','inventory':[],'nearbyEntities':[]}}
                return SimpleNamespace(raise_for_status=lambda:None,json=lambda:result)
            llm.append(payload)
            msg=({'role':'assistant','tool_calls':[{'function':{'name':'minecraft_estado','arguments':{}}}]}
                 if len(llm)==1 else {'role':'assistant','content':'Olá, Gustavo. O estado foi consultado.'})
            return SimpleNamespace(raise_for_status=lambda:None,close=lambda:None,
                iter_lines=lambda **_:iter([json.dumps({'message':msg,'done':True,'done_reason':'stop'})]))
        with patch.object(config,'DEBOUNCE_CONVERSA_MS',0),patch.object(main.situation,'descrever',return_value='conversa'),\
             patch.object(task_state,'iniciar_ou_continuar',return_value=None),\
             patch.object(saber.vetor,'salvar'),patch.object(saber.vetor,'buscar',return_value=[]),\
             patch.object(minecraft,'_ponte_compativel',return_value=({'protocol':3,'state':{'sessionId':'session-trace'}},'')),\
             patch.object(main.requests,'post',side_effect=post):
            app._interentity_inflight.add(incoming['id'])
            app.receber_de_pessoa(incoming['text'],canal='localhub',pessoa=app.pessoa,
                                 responder_para='usuario',mensagem_local=incoming)
            await asyncio.wait_for(asyncio.gather(*list(app._workers_por_chave.values())),5)
            if getattr(app,'_background_tasks',None): await asyncio.gather(*app._background_tasks)
        response=next(m for m in bus.user_conversation('hoshino') if m['sender']=='hoshino')
        metadata=json.loads(response['metadata'])
        turn=metadata['turn_id']
        self.assertEqual(metadata['input_ids'],[incoming['id']])
        # Consulta preventiva read-only e chamada explícita do modelo são IDs
        # distintos. Não confundir duas observações com duplicação de mutação.
        self.assertEqual(len(rpc),2)
        self.assertTrue(all(p['action']=='state' for p in rpc))
        self.assertTrue(all(p['turn_id']==turn and p['session_id']=='session-trace' for p in rpc))
        self.assertEqual(len([p for p in rpc if p['parent_id']==turn]),1)
        explicit=next(p for p in rpc if p['parent_id']!=turn)
        self.assertTrue(explicit['parent_id'])
        self.assertNotEqual(rpc[0]['request_id'],rpc[1]['request_id'])
        with closing(sqlite3.connect(config.DB_PATH)) as db:
            db.row_factory=sqlite3.Row
            records=[saber.registro(dict(r)) for r in db.execute('SELECT * FROM memories')]
        fact=next(r for r in records if 'Gustavo' in r['content'])
        evidence=fact['evidencias'][0]
        self.assertEqual(evidence['turn_id'],turn)
        self.assertEqual(evidence['message_id'],incoming['id'])
        self.assertEqual(evidence['submission_id'],'submission-trace')
        self.assertEqual(evidence['autor_id'],'usuario')
        session=json.loads(response['metadata'])['conversation_session']
        self.assertEqual(evidence['conversation_session_id'],session['id'])
        self.assertEqual(evidence['conversation_local_date'],session['local_date'])
        with closing(sqlite3.connect(history.DB)) as db:
            refs=[json.loads(row[0]).get('conversation_session') for row in db.execute(
                "SELECT metadata FROM messages WHERE turn_id=? AND direction='out'",(turn,))]
        self.assertIn(session,refs)
        root=Path(config.RUNTIME_DIR)/'trace-audio'
        service=audio_service.AudioService(root)
        def synthesize(text,path,*_):
            data=io.BytesIO()
            with wave.open(data,'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*1600)
            path.write_bytes(data.getvalue())
            return {'provider':'mock-local','voice':'fixture'}
        try:
            with patch.object(service,'_synthesize_chunk',side_effect=synthesize):
                job=service.submit_speech('hoshino',message_id=response['id'])
                await asyncio.wait_for(asyncio.to_thread(service.pending.join),3)
            self.assertEqual(service.get(job['id'])['status'],'done')
            self.assertEqual(job_bus.get(job['id'])['details']['conversation_session_id'],session['id'])
            service.playback_event('hoshino',job['id'],'autoplay_denied',0)
            service.playback_event('hoshino',job['id'],'cancelled',0)
        finally: service.close()
        with closing(sqlite3.connect(history.DB)) as db:
            events=[(kind,json.loads(data)) for kind,data in db.execute('SELECT kind,data FROM events WHERE turn_id=?',(turn,))]
        kinds={kind for kind,_ in events}
        for kind in ('executor.selected','llm.start','gpu.compute_acquired','gpu.compute_released',
                     'tool.start','tool.end','minecraft.rpc.end','memory.committed','voice.job_finished','voice.playback'):
            self.assertIn(kind,kinds)
        playback=next(data for kind,data in events if kind=='voice.playback')
        self.assertEqual(playback['audio_id'],job['id'])
        self.assertEqual(playback['input_ids'],[incoming['id']])
        self.assertEqual(playback['conversation_session_id'],session['id'])
        receipt=next(data for kind,data in events if kind=='minecraft.rpc.end' and data.get('request_id')==explicit['request_id'])
        self.assertEqual(receipt['bridge_session_id'],'session-trace')
        self.assertEqual(receipt['request_id'],explicit['request_id'])
        self.assertEqual(receipt['tool_id'],explicit['parent_id'])


if __name__=='__main__': unittest.main()
