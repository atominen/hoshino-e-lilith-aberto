"""Falas/previews locais; PCM sintético e nenhum motor, microfone ou banco real."""
import array
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/ui'))
from native_audio import Segmenter,FRAME_BYTES,RATE
try:
    from native_asr import LiveTranscript
except ImportError:
    LiveTranscript=None

VOICE=array.array('h',[3000]*(FRAME_BYTES//2)).tobytes()
QUIET=bytes(FRAME_BYTES)


class LiveCapture(unittest.TestCase):
    def turn(self):
        self.assertIsNotNone(LiveTranscript,'Controlador da fala ainda ausente')
        return LiveTranscript('hoshino','session-one','global','detection',True)

    def test_short_pause_does_not_end_turn_until_two_seconds(self):
        s=Segmenter('detection',silence_ms=2000)
        s.feed(VOICE*10+QUIET*39)
        self.assertEqual(getattr(s,'events',None),[])
        s.feed(VOICE+QUIET*39);self.assertEqual(s.events,[])
        s.feed(QUIET);self.assertEqual(len(s.events),1);self.assertTrue(s.events[0]['ended'])

    def test_silence_crossing_physical_limit_still_ends_after_two_seconds(self):
        s=Segmenter('detection',silence_ms=2000);s.maximum=FRAME_BYTES*45
        s.feed(VOICE*35+QUIET*10)
        self.assertIsNotNone(getattr(s,'events',None),'Falta distinguir corte físico do fim da fala')
        self.assertFalse(s.events[0]['ended'])
        s.feed(QUIET*29);self.assertEqual(s.events,[])
        s.feed(QUIET);self.assertTrue(s.events[0]['ended']);self.assertEqual(s.events[0]['pcm'],b'')

    def test_preview_revisions_replace_text_without_completing_turn(self):
        t=self.turn();t.preview(VOICE*20,now=0);p=t.take()
        t.complete(p,'preview-one',{'text':'Eu gosto de casa'})
        self.assertEqual(t.text(),'Eu gosto de casa');self.assertFalse(t.ready())
        t.preview(VOICE*40,now=1);p=t.take();t.complete(p,'preview-two',{'text':'Eu gosto de café'})
        self.assertEqual(t.text(),'Eu gosto de café');self.assertFalse(t.ready())

    def test_only_latest_preview_waits_and_final_has_priority(self):
        t=self.turn();t.preview(VOICE*20,now=0);p=t.take()
        t.preview(VOICE*40,now=1);t.preview(VOICE*60,now=2)
        self.assertIsNone(t.take());t.seal(VOICE*65,ended=True)
        t.complete(p,'stale',{'text':'antigo'})
        final=t.take();self.assertFalse(final.preview);self.assertEqual(final.pcm,VOICE*65)
        t.complete(final,'final',{'text':'Frase completa.'})
        self.assertTrue(t.ready());self.assertEqual(t.text(),'Frase completa.');self.assertEqual(t.jobs(),['final'])

    def test_preview_frequency_is_bounded_by_time_and_audio(self):
        t=self.turn();t.preview(VOICE*19,now=0);self.assertIsNone(t.take())
        t.preview(VOICE*20,now=0);p=t.take();t.complete(p,'p',{'text':'Oi'})
        t.preview(VOICE*40,now=.9);self.assertIsNone(t.take())
        t.preview(VOICE*40,now=1);self.assertIsNotNone(t.take())

    def test_physical_parts_wait_for_real_end_and_join_in_order(self):
        t=self.turn();t.seal(VOICE*20,ended=False);p=t.take()
        t.complete(p,'part-zero',{'text':'Primeira parte.'});self.assertFalse(t.ready())
        t.seal(VOICE*20,ended=True);p=t.take();t.complete(p,'part-one',{'text':'Segunda parte.'})
        self.assertTrue(t.ready());self.assertEqual(t.text(),'Primeira parte. Segunda parte.')
        self.assertEqual(t.jobs(),['part-zero','part-one'])

    def test_release_exactly_on_boundary_finishes_existing_part(self):
        t=self.turn();t.seal(VOICE*20,ended=False);p=t.take();t.end()
        t.complete(p,'part-zero',{'text':'Terminou.'});self.assertTrue(t.ready())

    def test_preview_error_does_not_poison_final_but_final_error_blocks_send(self):
        t=self.turn();t.preview(VOICE*20,now=0);p=t.take();t.complete(p,'p',{},error='no_speech')
        t.seal(VOICE*25,ended=True);p=t.take();t.complete(p,'f',{'text':'Oi.'})
        self.assertTrue(t.ready())
        t=self.turn();t.seal(VOICE*20,ended=True);p=t.take();t.complete(p,'f',{},error='failed')
        self.assertFalse(t.ready());self.assertTrue(t.failed)

    def test_preview_survives_waiting_and_failed_final_for_manual_recovery(self):
        t=self.turn();t.preview(VOICE*20,now=0);p=t.take()
        t.complete(p,'p',{'text':'Texto provisório.'});t.seal(VOICE*25,ended=True)
        self.assertEqual(t.text(),'Texto provisório.')
        p=t.take();t.complete(p,'f',{},error='failed')
        self.assertEqual(t.text(),'Texto provisório.');self.assertFalse(t.ready())

    def test_discard_ignores_late_acceptance_and_results(self):
        t=self.turn();t.seal(VOICE*20,ended=True);p=t.take();t.discard()
        t.complete(p,'late',{'text':'Não enviar.'});self.assertFalse(t.ready());self.assertEqual(t.text(),'')

    def test_four_waiting_final_parts_are_bounded(self):
        t=self.turn();t.seal(VOICE*20,ended=False);p=t.take()
        for _ in range(4):t.seal(VOICE*20,ended=False)
        with self.assertRaises(BufferError):t.seal(VOICE*20,ended=True)
        self.assertTrue(t.failed);self.assertFalse(t.ready())


if __name__=='__main__':unittest.main()
