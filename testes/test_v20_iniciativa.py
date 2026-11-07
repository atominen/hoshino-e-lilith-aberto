import tempfile
import unittest
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
import threading
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import config
from memory.sqlite import init_db
from core import bd, kernel, autonomy, dispatch
from social import people
from tools import agenda
from unittest.mock import patch


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        config.DB_PATH = str(Path(self.tmp.name) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)
        # agenda importa DB_PATH ao carregar; precisa acompanhar o banco da fixture.
        self.agenda_db = patch.object(agenda, "DB_PATH", config.DB_PATH)
        self.agenda_db.start()
        self.addCleanup(self.agenda_db.stop)

    def tearDown(self):
        self.tmp.cleanup()


class InitiativeV20(Base):
    def test_first_session_internal_idle_clock_does_not_invent_social_contact_or_change_gates(self):
        from mind import drives, emotions, psych_state, reflection
        with patch.object(drives, '_estado', return_value={}), \
             patch.object(emotions, 'influencia_nos_impulsos', return_value={}), \
             patch.object(psych_state, 'influencia', return_value={}), \
             patch.object(reflection, 'precisa_refletir', return_value=False):
            base = dict(usuario_presente=None, segundos_ociosos=0,
                        ultima_interacao_conhecida=False)
            before = drives.avaliar(base)
            after = drives.avaliar(dict(base, segundos_sem_interacao_observados=3600))
            self.assertEqual(after['conexao'], before['conexao'])
            self.assertEqual(after['curiosidade'], before['curiosidade'])
            self.assertGreater(after['ocio']['pressao'], before['ocio']['pressao'])
            # Corrigir medição não é baixar limiar nem forçar atividade para
            # aprovar o ensaio: a modulação conservadora original permanece.
            self.assertIsNone(drives.dominante(after))

    def test_silence_without_presence_evidence_is_unknown_not_rejection(self):
        from core import situation
        with patch.object(config,'ESTADO_MENTE',str(Path(self.tmp.name)/'state.json')):
            now=datetime.now()
            observed=situation.atualizar({'ociosidade_x11':-1},
                ultima_interacao=now-timedelta(hours=5),agora=now)
            self.assertIsNone(observed['usuario_presente'])
            self.assertFalse(observed['interpretacao_presenca']['presenca_fisica_confirmada'])
            self.assertFalse(any(e['tipo'] in {'rejeicao','abandono','sumiu'} for e in observed['eventos']))

    def test_drive_refractory_survives_module_reload_and_is_entity_scoped(self):
        import importlib
        from mind import drives
        now=datetime(2026,10,9,12,0,0,123000)
        with patch.object(config,'ESTADO_MENTE',str(Path(self.tmp.name)/'hoshino.json')):
            self.assertTrue(drives.satisfazer('curiosidade',now))
            importlib.reload(drives)
            self.assertEqual(drives._refratario('curiosidade',now),0.)
        with patch.object(config,'ESTADO_MENTE',str(Path(self.tmp.name)/'lilith.json')):
            self.assertEqual(drives._refratario('curiosidade',now),1.)

    def test_spontaneous_contact_has_recorded_anchor_and_cooldown(self):
        from mind import scribe
        scribe.curiosidade_nova('Que livros o visitante gosta?',sobre='pessoa Visitante',origem='pessoa')
        now=datetime.now().replace(hour=12)
        sit=dict(agora=now,eventos=[],usuario_presente=True,carga={})
        pressure={'conexao':{'pressao':.99}}
        with patch.object(config,'HORARIO_SILENCIO',(0,0)):
            decision=kernel.deliberar(sit,pressure,{'ultima_fala':None})
            self.assertEqual(decision['tipo'],'conhecer')
            self.assertIn('livros',decision['ancora']['texto'])
            blocked=kernel.deliberar(sit,pressure,{'ultima_fala':now})
            self.assertEqual(blocked['tipo'],'nada')

    def test_reflexao_nao_vira_ancora_social(self):
        situacao = {"eventos": [], "usuario_presente": True}
        # Sem curiosidade sobre a pessoa, não existe fala espontânea.
        self.assertEqual(kernel.buscar_ancora(situacao), {})

    def test_intencao_interna_nunca_publica(self):
        ok, motivo = autonomy.validar_fala_autonoma(
            "Eu deveria abrir um arquivo e testar uma coisa que descobri.",
            {"tipo": "investigar", "motivo": "curiosidade interna"})
        self.assertFalse(ok)
        self.assertIn("interna", motivo)

    def test_biografia_aleatoria_e_barrada(self):
        ok, motivo = autonomy.validar_fala_autonoma(
            "Eu sou programador(a) profissional e trabalho com backend em Python.",
            {"tipo": "falar", "motivo": "puxar assunto", "ancora": {"texto": "Python"}})
        self.assertFalse(ok)
        self.assertIn("autoapresentação", motivo)

    def test_conhecer_precisa_ser_pergunta(self):
        ok, motivo = autonomy.validar_fala_autonoma(
            "Quero saber mais sobre você?", 
            {"tipo": "conhecer", "motivo": "curiosidade", "ancora": {"texto": "sobre você"}})
        self.assertTrue(ok)
        self.assertEqual(motivo, "ok")

    def test_conversa_nao_cria_confianca(self):
        p = people.identificar(nome="Visitante", canal="discord", canal_id="123")
        antes = float(p["confianca"])
        for _ in range(30):
            p = people.registrar_evento(p["id"], "conversa", "conversa normal")
        self.assertAlmostEqual(float(p["confianca"]), antes, places=6)
        self.assertNotIn(p["estagio"], {"amiga", "de casa"})

    def test_confianca_evidenciada_pode_subir_estagio(self):
        p = people.identificar(nome="Pessoa", canal="tui", canal_id="local")
        for _ in range(8):
            p = people.registrar_evento(p["id"], "cumpriu_o_que_disse", "evidência")
        self.assertGreater(float(p["confianca"]), 0.25)

    def test_impulso_de_conexao_sem_assunto_nao_fala(self):
        with agenda._conn() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0], 0)
        agora = datetime.now()
        situacao = {
            "agora": agora, "eventos": [], "usuario_presente": True,
            "lembretes_vencidos": 0, "prazos_proximos": 0,
            "carga": {"memoria_usada_pct": 20, "load1": 0.2, "disco_usado_pct": 40},
        }
        pressoes = {
            "conexao": {"pressao": 0.95},
            "curiosidade": {"pressao": 0.10},
            "competencia": {"pressao": 0.10},
            "coerencia": {"pressao": 0.10},
        }
        dec = kernel.deliberar(situacao, pressoes, {"ultima_fala": None, "modo_silencioso": False})
        self.assertNotIn(dec["tipo"], {"avisar", "falar", "conhecer"})

    def test_autonomia_interna_nao_recebe_ferramentas_de_criacao(self):
        nomes = {e["function"]["name"] for e in dispatch.esquemas(
            "investigar algo que descobri", grupos_extras=["memoria"],
            modo_operacao="autonomo_interno")}
        self.assertNotIn("criar_ferramenta", nomes)
        self.assertNotIn("criar_projeto", nomes)
        self.assertNotIn("escrever_na_oficina", nomes)
        self.assertNotIn("execute_command", nomes)

    def test_objetivo_autonomo_pode_receber_criacao_justificada(self):
        nomes = {e["function"]["name"] for e in dispatch.esquemas(
            "criar uma ferramenta para meu objetivo", grupos_extras=["ferramentas", "oficina"],
            modo_operacao="autonomo_objetivo")}
        self.assertIn("criar_ferramenta", nomes)


class AgendaClockTests(Base):
    def setUp(self):
        super().setUp()
        self.now = datetime(2026, 10, 9, 15, tzinfo=timezone.utc)
        clock = patch.object(config, 'LOCAL_TIMEZONE', 'America/Sao_Paulo')
        clock.start(); self.addCleanup(clock.stop)

    def reminder(self, identifier, due, rule=None):
        with closing(agenda._conn()) as c, c:
            c.execute("INSERT INTO reminders(id,message,due_at,repeat_rule,status) VALUES(?,?,?,?, 'pending')",
                      (identifier, 'Ensaio '+identifier, due, rule))

    def test_mixed_due_dates_use_instants_not_text_and_read_does_not_migrate(self):
        for rid, ts in [('past-utc', '2026-10-09T14:30:00Z'), ('future-local', '2026-10-09T12:30:00'),
                        ('past-local', '2026-10-09T11:40:00'), ('past-offset', '2026-10-09T23:50:00+09:00'),
                        ('invalid', 'não é data')]:
            self.reminder(rid, ts)
        with closing(agenda._conn()) as c, c:
            before = c.execute('SELECT id,due_at FROM reminders ORDER BY id').fetchall()
        due = agenda.lembretes_vencidos(self.now)
        self.assertEqual([r['id'] for r in due], ['past-utc', 'past-local', 'past-offset'])
        with closing(agenda._conn()) as c, c:
            self.assertEqual(c.execute('SELECT id,due_at FROM reminders ORDER BY id').fetchall(), before)

    def test_local_format_and_parser_respect_timezone_for_aware_now(self):
        from core import history
        with patch.object(agenda, '_agora', return_value=self.now):
            self.assertEqual(agenda._fmt('2026-10-09T15:00:00Z'), 'hoje 12:00')
        target, rule, error = agenda.interpretar_tempo('amanhã às 9h', self.now)
        self.assertIsNone(error)
        self.assertIsNone(rule)
        self.assertEqual(history.local_datetime(target).hour, 9)
        self.assertEqual(history.local_datetime(target).date().isoformat(), '2026-10-10')
        target, _, error = agenda.interpretar_tempo('20/10 14:30', self.now)
        self.assertIsNone(error)
        self.assertEqual(history.local_datetime(target).hour, 14)

    def test_new_agenda_markers_are_utc_and_existing_naive_fixtures_remain_supported(self):
        from core import history
        with patch.object(agenda, '_agora', return_value=self.now):
            text = agenda.criar_lembrete('Tomar água do ensaio', 'em 30 minutos')
            self.assertTrue(text.startswith('Lembrete [lem-'))
            agenda.add_goal('Objetivo do ensaio', prazo='em 2 horas')
        with closing(agenda._conn()) as c, c:
            reminder = c.execute('SELECT created_at,due_at FROM reminders').fetchone()
            goal = c.execute('SELECT created_at,due_at FROM goals').fetchone()
        self.assertTrue(all(ts.endswith('+00:00') for ts in (*reminder, *goal)))
        self.assertEqual(history.timestamp_order(reminder[1])-history.timestamp_order(reminder[0]), 1800.)
        target, _, error = agenda.interpretar_tempo('em 30 minutos', datetime(2026, 10, 9, 12))
        self.assertIsNone(error)
        self.assertEqual(target, datetime(2026, 10, 9, 12, 30))

    def test_recurring_utc_reminder_reschedules_once_and_local_daily_time_is_preserved(self):
        self.reminder('daily', '2026-10-08T12:00:00Z', 'diario')
        with patch.object(agenda, '_agora', return_value=self.now):
            self.assertIn('próximo', agenda.marcar_entregue('daily'))
        with closing(agenda._conn()) as c, c:
            due, fired = c.execute("SELECT due_at,fired_at FROM reminders WHERE id='daily'").fetchone()
        from core import history
        self.assertEqual(history.local_datetime(due), history.local_datetime('2026-10-10T09:00:00-03:00'))
        self.assertEqual(fired, history.utc_timestamp(self.now))

    def test_interval_rule_is_bounded_after_years_and_invalid_rules_do_not_hang(self):
        result = {}
        finished = threading.Event()
        def attempt():
            try:
                agenda._proxima_ocorrencia(datetime(2026, 10, 1), 'intervalo:0', self.now)
            except ValueError:
                result['rejected'] = True
            finally:
                finished.set()
        threading.Thread(target=attempt, daemon=True).start()
        self.assertTrue(finished.wait(1), 'Regra zero travou em loop; worker isolado será encerrado com o teste.')
        self.assertTrue(result.get('rejected'))
        for rule in ('intervalo:-60', 'intervalo:abc', 'desconhecida'):
            with self.assertRaises(ValueError):
                agenda._proxima_ocorrencia(datetime(2026, 10, 1), rule, self.now)
        target = agenda._proxima_ocorrencia(datetime(2000, 1, 1), 'intervalo:60', self.now)
        from core import history
        self.assertEqual(history.elapsed_seconds(self.now, target), 60.)

    def test_bad_recurrence_is_not_recorded_as_delivered(self):
        self.reminder('broken', '2026-10-09T11:00:00', 'intervalo:abc')
        self.assertIn('NÃO', agenda.marcar_entregue('broken'))
        with closing(agenda._conn()) as c, c:
            row = c.execute("SELECT due_at,status,fired_at FROM reminders WHERE id='broken'").fetchone()
        self.assertEqual(row, ('2026-10-09T11:00:00', 'pending', None))

    def test_invalid_recurrence_does_not_repeat_speech_each_tick_but_remains_visible(self):
        self.reminder('broken', '2026-10-09T11:00:00', 'intervalo:0')
        self.assertEqual(agenda.lembretes_vencidos(self.now), [])
        self.assertIn('[broken]', agenda.listar_lembretes())
        with closing(agenda._conn()) as c, c:
            self.assertEqual(c.execute("SELECT status,fired_at FROM reminders WHERE id='broken'").fetchone(), ('pending', None))

    def test_goal_deadlines_and_upcoming_count_use_same_timezone_contract(self):
        from core import situation
        for identifier, ts in [('past', '2026-10-09T14:00:00Z'), ('soon', '2026-10-09T17:00:00'),
                               ('later', '2026-10-09T23:00:00'), ('invalid', 'não é data')]:
            bd.executar("INSERT INTO goals(id,description,status,due_at) VALUES(?,?,'active',?)", (identifier, identifier, ts), strict=True)
        self.assertEqual([r['id'] for r in agenda.objetivos_vencidos(self.now)], ['past'])
        self.assertEqual(situation._pendencias(self.now)['prazos_proximos'], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
