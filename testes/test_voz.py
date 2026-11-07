"""Regressões de voz legada, sem abrir dispositivos ou sintetizar."""
import asyncio
import unittest
from unittest.mock import Mock, patch

from tools import voice


class VoiceTests(unittest.TestCase):
    def protocol_process(self):
        process=Mock(poll=Mock(return_value=None),stdin=Mock(),stdout=Mock())
        process.stdout.fileno.return_value=93
        return process
    def test_ready_and_result_in_same_pipe_read_do_not_false_timeout(self):
        process=self.protocol_process();process.stdout.readline.side_effect=['READY worker\n','RESULT {"id":"current","ok":true}\n']
        with patch.object(voice,'_iniciar_worker',return_value=process),patch.object(voice.uuid,'uuid4',return_value=Mock(hex='current')), \
                patch.object(voice.select,'select',side_effect=[([process.stdout],[],[]),([],[],[])]) as ready, \
                patch.object(voice.os,'read',return_value=b'READY worker\nRESULT {"id":"current","ok":true}\n') as read, \
                patch.object(voice,'_parar_worker') as stop:
            voice._sintetizar_kokoro('teste','fixture-only.wav')
            self.assertEqual(ready.call_count,1);self.assertEqual(read.call_count,1);stop.assert_not_called()
    def test_eof_with_unterminated_result_is_rejected_not_success(self):
        process=self.protocol_process();process.stdout.readline.return_value='RESULT {"id":"current","ok":true}'
        with patch.object(voice,'_iniciar_worker',return_value=process),patch.object(voice.uuid,'uuid4',return_value=Mock(hex='current')), \
                patch.object(voice.select,'select',return_value=([process.stdout],[],[])), \
                patch.object(voice.os,'read',side_effect=[b'RESULT {"id":"current","ok":true}',b'']),patch.object(voice,'_parar_worker') as stop:
            with self.assertRaisesRegex(RuntimeError,'sem responder'):voice._sintetizar_kokoro('teste','fixture-only.wav')
            stop.assert_called_once()
    def test_complete_foreign_result_buffered_after_response_remains_rejected(self):
        process=self.protocol_process();process.stdout.readline.side_effect=['RESULT {"id":"one","ok":true}\n','RESULT {"id":"foreign","ok":true}\n']
        with patch.object(voice,'_iniciar_worker',return_value=process), \
                patch.object(voice.uuid,'uuid4',side_effect=[Mock(hex='one'),Mock(hex='two')]), \
                patch.object(voice.select,'select',side_effect=[([process.stdout],[],[]),([],[],[])]) as ready, \
                patch.object(voice.os,'read',return_value=b'RESULT {"id":"one","ok":true}\nRESULT {"id":"foreign","ok":true}\n'),patch.object(voice,'_parar_worker') as stop:
            voice._sintetizar_kokoro('primeiro','fixture-only.wav')
            with self.assertRaisesRegex(RuntimeError,'outra solicitação'):voice._sintetizar_kokoro('segundo','fixture-only.wav')
            self.assertEqual(ready.call_count,1);stop.assert_called_once()
    def test_estado_mostra_saida_sem_inicializar_mixer(self):
        with patch.object(voice, "_saida_padrao", return_value="headset"), \
                patch.object(voice, "_garantir_mixer") as mixer:
            self.assertIn("saída padrão: headset", voice.estado())
            mixer.assert_not_called()

    def test_falha_do_mixer_vira_diagnostico(self):
        with patch.object(voice, "ULTIMO_ERRO", ""), patch.object(voice, "_mixer_pronto", False), \
                patch.object(voice, "DISPONIVEL", True), \
                patch.object(voice.pygame.mixer, "init", side_effect=RuntimeError("sem áudio")):
            self.assertFalse(voice._garantir_mixer())
            self.assertIn("sem áudio", voice.ULTIMO_ERRO)

    def test_limpar_para_fala_remove_rubricas_de_emocao(self):
        limpo = voice.limpar_para_fala("*sorri* Olá. (suspira) Eu continuei. [risos] Isso está certo.")
        for rubrica in ("sorri", "suspira", "risos"):
            self.assertNotIn(rubrica, limpo.lower())
        self.assertIn("Olá.", limpo)
        self.assertIn("Eu continuei.", limpo)

    def test_limpar_para_fala_preserva_fala_normal(self):
        text = "Eu gosto de rir quando algo realmente é engraçado."
        self.assertEqual(voice.limpar_para_fala(text), text)

    def test_texto_longo_nao_e_cortado_ou_reproduzido(self):
        with patch.object(voice, "_garantir_mixer") as mixer:
            result = asyncio.run(voice.speak("x" * 2401, forcar=True))
        self.assertIn("Nada foi cortado", result)
        mixer.assert_not_called()

    def test_timeout_descarta_worker_antes_do_proximo_pedido(self):
        with patch.object(voice, "_sintetizar_pedido", side_effect=TimeoutError), \
                patch.object(voice, "_parar_worker") as stop:
            with self.assertRaises(TimeoutError):
                voice._sintetizar_kokoro("teste", "test-only-output.wav")
            stop.assert_called_once()

    def test_resposta_antiga_e_rejeitada(self):
        process = Mock(poll=Mock(return_value=None), stdin=Mock(),
                       stdout=Mock(readline=Mock(return_value='RESULT {"id":"old","ok":true}\n')))
        with patch.object(voice, "_iniciar_worker", return_value=process), \
                patch.object(voice.select, "select", return_value=([process.stdout], [], [])), \
                patch.object(voice.os, "read", return_value=b'RESULT {"id":"old","ok":true}\n'), \
                patch.object(voice, "_parar_worker") as stop:
            with self.assertRaisesRegex(RuntimeError, "outra solicitação"):
                voice._sintetizar_kokoro("teste", "test-only-output.wav")
            stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
