"""Quietude de texto no barramento real, em SQLite temporário e relógio de fixture."""
import tempfile,unittest,threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
from core import interentity as bus

BASE=datetime(2026,10,26,12,tzinfo=timezone.utc).timestamp()


class TextBursts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='typed-burst-');self.addCleanup(self.temp.cleanup)
        p=patch.object(bus,'DB_PATH',Path(self.temp.name)/'bus.db');p.start();self.addCleanup(p.stop)

    def send(self,text,at=0,recipient='hoshino',scope='direct',metadata=None,sender='usuario'):
        stamp=datetime.fromtimestamp(BASE+at,timezone.utc).isoformat()
        with patch.object(bus,'_agora',return_value=stamp):
            return bus.send(sender,recipient,text,chat_scope=scope,metadata=metadata)

    def inbox(self,at,**kw):return bus.inbox('hoshino',settle_text_seconds=2,now=BASE+at,**kw)

    def test_two_seconds_after_latest_send_and_original_order(self):
        first=self.send('Primeira parte');second=self.send('Segunda parte',1.5)
        self.assertEqual(self.inbox(2.1),[])
        rows=self.inbox(3.5);self.assertEqual([r['id'] for r in rows],[first['id'],second['id']])
        self.assertTrue(all(r['_text_burst_ready'] for r in rows))

    def test_pending_is_not_marked_delivered(self):
        sent=self.send('Ainda digitando')
        self.assertEqual(self.inbox(1.9),[])
        self.assertIsNone(bus.peek('hoshino')[0]['delivered_at'])
        self.assertEqual(self.inbox(2)[0]['id'],sent['id'])

    def test_latest_outside_page_also_extends_quiet_window(self):
        for i in range(25):self.send(str(i),i*.05)
        self.assertEqual(self.inbox(2.1,limit=20),[])
        self.assertEqual(len(self.inbox(3.2,limit=20)),20)

    def test_voice_other_scope_and_entity_do_not_delay_this_thread(self):
        direct=self.send('Direto');voice=self.send('Fala confirmada',1.8,metadata={'audio_job_id':'voice-final'})
        self.send('Global novo',1.9,scope='global');self.send('Outra entidade',1.9,recipient='lilith')
        rows=self.inbox(2);self.assertEqual([r['id'] for r in rows],[direct['id'],voice['id']])
        self.assertNotIn('_text_burst_ready',rows[-1])

    def test_interentity_chat_and_explicit_stop_do_not_wait(self):
        entity=self.send('Comentário público',sender='lilith')
        stop=self.send('Pare de falar',.2)
        rows=self.inbox(.3);self.assertEqual([r['id'] for r in rows],[entity['id'],stop['id']])

    def test_waiting_text_page_does_not_hide_independent_voice_or_entity(self):
        for i in range(25):self.send(str(i),i*.05)
        voice=self.send('Fala confirmada',1.3,metadata={'audio_job_id':'final'})
        entity=self.send('Mensagem da outra entidade',1.4,sender='lilith')
        self.assertEqual([r['id'] for r in self.inbox(1.5,limit=20)],[voice['id'],entity['id']])

    def test_failed_or_processing_envelope_does_not_hold_new_message(self):
        ready=self.send('Pedido válido')
        self.send('Pedido antigo com efeito incerto',1.9,metadata={'processing':{'status':'uncertain'}})
        rows=self.inbox(2);self.assertEqual([r['id'] for r in rows],[ready['id']])

    def test_concurrent_send_cannot_use_an_older_quiet_snapshot(self):
        first=self.send('Primeira parte')
        insert_now=threading.Event();inserted=threading.Event();errors=[]
        original=bus._transaction
        def writer():
            try:
                insert_now.wait(2);self.send('Fragmento recém enviado',3)
            except Exception as exc:errors.append(exc)
            finally:inserted.set()
        thread=threading.Thread(target=writer);thread.start()
        class Connection:
            def __init__(self,conn):self.conn=conn
            def __getattr__(self,key):return getattr(self.conn,key)
            def execute(self,sql,*args):
                if sql.startswith('SELECT * FROM entity_messages') and sql.endswith('ORDER BY rowid'):
                    insert_now.set();inserted.wait(.15)
                return self.conn.execute(sql,*args)
        @contextmanager
        def wrapped():
            with original() as conn:yield Connection(conn)
        try:
            with patch.object(bus,'_transaction',wrapped):rows=self.inbox(3)
        finally:
            insert_now.set();thread.join(3)
        self.assertFalse(errors);self.assertFalse(thread.is_alive())
        self.assertEqual([r['id'] for r in rows],[first['id']])
        self.assertEqual(self.inbox(4),[])

    def test_read_only_settle_does_not_cancel_or_acknowledge(self):
        old=self.send('Objetivo anterior');self.send('Pare',.2)
        self.inbox(.3,mark_delivered=False)
        row=next(r for r in bus.peek('hoshino') if r['id']==old['id'])
        self.assertIsNone(row['read_at']);self.assertIsNone(row['delivered_at'])

    def test_correction_barrier_preserves_other_scope_and_inflight_effects(self):
        direct=self.send('Direto anterior')
        global_message=self.send('Global anterior',scope='global')
        inflight=self.send('Efeito já em andamento')
        bus.processing_outcome(inflight['id'],'hoshino','processing')
        self.send('Na verdade use somente o novo pedido',.2)
        self.assertEqual(self.inbox(.3),[])
        rows={r['id']:r for r in bus.inbox('hoshino',unread_only=False,include_held=True)}
        self.assertEqual(rows[direct['id']]['metadata']['processing']['status'],'superseded')
        self.assertIsNone(rows[global_message['id']]['read_at'])
        self.assertEqual(rows[inflight['id']]['metadata']['processing']['status'],'processing')


if __name__=='__main__':unittest.main()
