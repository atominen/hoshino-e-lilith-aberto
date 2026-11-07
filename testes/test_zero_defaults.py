import unittest
from pathlib import Path
from unittest.mock import patch
from core import dispatch
from tools import desktop
from play.chess import session


class Zero(unittest.TestCase):
    def test_intervalo_sorteio_zero(self):
        r = dispatch.HANDLERS['sortear']({'tipo':'inteiro','minimo':0,'maximo':0}, False)
        self.assertIn('MIN=0 MAX=0 RESULTADOS=0', r)
        r = dispatch.HANDLERS['sortear']({'tipo':'inteiro','minimo':None,'maximo':None}, False)
        self.assertIn('MIN=1 MAX=100', r)

    def test_pixels_zero(self):
        with patch.object(dispatch.browser, 'rolar', return_value='ok') as scroll:
            dispatch.HANDLERS['browser_rolar']({'pixels':0}, False)
        self.assertEqual(scroll.call_args.args[0], 0)

    def test_distancia_zero_pipeline_minecraft(self):
        with patch.object(dispatch.minecraft, 'ir_para', return_value='ok') as go:
            dispatch.HANDLERS['minecraft_ir_para']({'x':0,'y':0,'z':0,'distancia':0}, False)
        self.assertEqual(go.call_args.args[-1], 0)
        with patch.object(dispatch.minecraft, 'seguir_jogador', return_value='ok') as follow:
            dispatch.HANDLERS['minecraft_seguir_jogador']({'nome':'Teste','distancia':0}, False)
        self.assertEqual(follow.call_args.args[-1], 0)
        source = (Path(__file__).resolve().parents[1] / 'compartilhado/servicos/minecraft/bridge.js').read_text()
        self.assertIn('args.range ?? 1', source)
        self.assertIn('args.distance ?? 2', source)

    def test_rating_zero_vs_ausente(self):
        self.assertEqual(session.nivel_atual({'praticas':0,'rating':0})[0], 1)
        levels = [(1,0,None,{},''), (2,100,0,{},'')]
        with patch.object(session, 'NIVEIS', levels):
            self.assertEqual(session.nivel_atual({'praticas':0,'rating':0})[0], 2)

    def test_espera_zero(self):
        # Teste sem GUI: instala só o backend fictício que o adaptador consulta.
        with patch.object(desktop, '_BACKEND', 'pyautogui'), patch.object(desktop, '_pyautogui', __import__('unittest.mock').mock.Mock()), patch('time.sleep') as sleep:
            r = desktop.acao('esperar', segundos=0)
        self.assertIn('0.0s', r)
        sleep.assert_called_once_with(0)

    def test_dispositivo_audio_zero_nao_e_padrao(self):
        import sys
        from tools.transcricao import FonteDeAudio
        backend = __import__('unittest.mock').mock.Mock()
        source = FonteDeAudio(dispositivo=0)
        self.assertEqual(source.dispositivo, 0)
        with patch.dict(sys.modules, {'sounddevice': backend}):
            source._abrir_sounddevice()
        self.assertEqual(backend.RawInputStream.call_args.kwargs['device'], 0)

    def test_relogio_zero_preserva_tempo_decorrido(self):
        from core import progress
        progress.limpar()
        with patch('core.progress.time.monotonic', return_value=0):
            progress.iniciar('Relógio de regressão')
        with patch('core.progress.time.monotonic', return_value=5):
            r = progress.snapshot()
        self.assertEqual(r['elapsed_s'], 5)
        self.assertEqual(r['silence_s'], 5)
        progress.limpar()


if __name__ == '__main__':
    unittest.main()
