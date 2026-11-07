"""ASR da central: fixtures temporárias, sem rede/modelos/memórias reais."""
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from core import audio_transcription as audio
from social import escuta


class AudioTranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hoshino-audio-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "recording.wav"
        self.samples = (0.1 * np.sin(np.arange(16000) * 0.13)).astype(np.float32)
        self.write_audio(self.samples)

    def write_audio(self, samples):
        with wave.open(str(self.path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(16000)
            f.writeframes((samples * 32767).astype("int16").tobytes())

    def fake_recognizer(self, segments):
        self.model = SimpleNamespace(transcribe=lambda *_args, **_kwargs: (
            iter(segments), SimpleNamespace(language="pt", language_probability=1.0)))
        return SimpleNamespace(_modelo=self.model)

    def segment(self, text="Olá, Hoshino.", **kwargs):
        return SimpleNamespace(text=text, start=0.1, end=0.8,
                               no_speech_prob=kwargs.get("no_speech_prob", 0.05),
                               avg_logprob=kwargs.get("avg_log_prob", -0.2))

    def test_primary_source_role_is_not_voice_identification(self):
        recognizer = self.fake_recognizer([self.segment()])
        with patch.object(audio, "_get_recognizer", return_value=recognizer):
            result = audio.transcribe(self.path)
        self.assertEqual(result["speaker"], "usuario")
        self.assertEqual(result["speaker_basis"], "source_role")
        self.assertEqual(result["language"], "pt")
        self.assertEqual(result["segments"][0]["speaker"], "usuario")
        self.assertFalse(result["metadata"]["speaker_identification_performed"])
        self.assertFalse(result["metadata"]["diarization_performed"])
        self.assertIsNone(result["metadata"]["language_probability"])
        self.assertEqual(result["metadata"]["device"], "cpu")

    def test_other_source_does_not_guess_speaker(self):
        recognizer = self.fake_recognizer([self.segment()])
        with patch.object(audio, "_get_recognizer", return_value=recognizer):
            result = audio.transcribe(self.path, source="pc_playback")
        self.assertEqual(result["speaker"], "desconhecido")
        self.assertEqual(result["speaker_basis"], "unknown")
        self.assertIsNone(result["metadata"]["application"])

    def test_silence_rejected_before_model_loading(self):
        self.write_audio(np.zeros(16000, dtype=np.float32))
        with patch.object(audio, "_get_recognizer") as model:
            with self.assertRaises(audio.AudioTranscriptionError) as error:
                audio.transcribe(self.path)
        self.assertEqual(error.exception.code, "no_speech")
        model.assert_not_called()

    def test_empty_vad_or_hallucinations_are_not_success(self):
        cases = [[], [self.segment("Legendas pela comunidade Amara.org")],
                 [self.segment("Olá", no_speech_prob=0.95, avg_log_prob=-2.0)],
                 [self.segment("...")]]
        for segments in cases:
            with self.subTest(segments=segments):
                recognizer = self.fake_recognizer(segments)
                with patch.object(audio, "_get_recognizer", return_value=recognizer):
                    with self.assertRaises(audio.AudioTranscriptionError) as error:
                        audio.transcribe(self.path)
                self.assertEqual(error.exception.code, "no_speech")

    def test_one_word_command_is_allowed(self):
        recognizer = self.fake_recognizer([self.segment("Pare!")])
        with patch.object(audio, "_get_recognizer", return_value=recognizer):
            result = audio.transcribe(self.path)
        self.assertEqual(result["text"], "Pare!")

    def test_stereo_browser_audio_is_resampled_to_mono_16k(self):
        rate = 48000
        samples = (0.1 * np.sin(np.arange(rate) * 0.04)).astype(np.float32)
        stereo = np.column_stack((samples, samples * 0.5))
        with wave.open(str(self.path), "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(rate)
            f.writeframes((stereo * 32767).astype("int16").tobytes())
        seen = []

        def infer(samples, **kwargs):
            seen.append((samples.shape, kwargs))
            return iter([self.segment()]), SimpleNamespace(language="pt")

        recognizer = SimpleNamespace(_modelo=SimpleNamespace(transcribe=infer))
        with patch.object(audio, "_get_recognizer", return_value=recognizer):
            result = audio.transcribe(self.path)
        self.assertEqual(seen[0][0], (16000,))
        self.assertTrue(seen[0][1]["vad_filter"])
        self.assertEqual(result["metadata"]["input_sample_rate"], rate)
        self.assertEqual(result["metadata"]["input_channels"], 2)

    def test_model_exception_does_not_become_transcription_text(self):
        with patch.object(audio, "_get_recognizer", side_effect=RuntimeError("secret diagnostic")):
            with self.assertRaises(audio.AudioTranscriptionError) as error:
                audio.transcribe(self.path)
        self.assertEqual(error.exception.code, "transcription_failed")
        self.assertNotIn("secret diagnostic", str(error.exception))

    def test_rejects_invalid_or_truncated_wav(self):
        self.path.write_bytes(b"not an audio")
        with self.assertRaises(audio.AudioTranscriptionError) as error:
            audio.transcribe(self.path)
        self.assertEqual(error.exception.code, "invalid_audio")
        self.write_audio(self.samples)
        self.path.write_bytes(self.path.read_bytes()[:-100])
        with self.assertRaises(audio.AudioTranscriptionError) as error:
            audio.transcribe(self.path)
        self.assertEqual(error.exception.code, "truncated_audio")

    def test_rejects_too_short_input(self):
        self.write_audio(np.ones(100, dtype=np.float32))
        with self.assertRaises(audio.AudioTranscriptionError) as error:
            audio.transcribe(self.path)
        self.assertEqual(error.exception.code, "duration")

    def test_status_does_not_load_model(self):
        with patch.object(audio, "_get_recognizer") as model:
            self.assertEqual(audio.status()["sharing"], "single_persistent_worker")
        model.assert_not_called()

    def test_lazy_model_is_cpu_int8_and_cache_only(self):
        model = SimpleNamespace(transcribe=lambda *_a, **_k: None)
        with patch.object(audio, "_RECOGNIZER", None), \
                patch("faster_whisper.WhisperModel", return_value=model) as construct, \
                patch("faster_whisper.utils.download_model", return_value=self.temp.name) as cached:
            first = audio._get_recognizer()
            second = audio._get_recognizer()
        self.assertIs(first, second)
        construct.assert_called_once()
        self.assertEqual(construct.call_args.kwargs["device"], "cpu")
        self.assertEqual(construct.call_args.kwargs["compute_type"], "int8")
        self.assertTrue(construct.call_args.kwargs["local_files_only"])
        self.assertTrue(cached.call_args.kwargs["local_files_only"])

    def test_lock_covers_lazy_generator_inference(self):
        active = 0
        max_active = 0
        guard = threading.Lock()

        def segments():
            nonlocal active, max_active
            with guard:
                active += 1
                max_active = max(active, max_active)
            time.sleep(0.05)
            yield self.segment()
            with guard:
                active -= 1

        model = SimpleNamespace(transcribe=lambda *_a, **_k: (segments(), SimpleNamespace(language="pt")))
        recognizer = SimpleNamespace(_modelo=model)
        errors = []

        def call():
            try:
                audio.transcribe(self.path)
            except Exception as exc:
                errors.append(exc)

        with patch.object(audio, "_get_recognizer", return_value=recognizer):
            threads = [threading.Thread(target=call) for _ in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
        self.assertEqual(errors, [])
        self.assertEqual(max_active, 1)
        self.assertTrue(all(not thread.is_alive() for thread in threads))


class AudioSourceSelectionTests(unittest.TestCase):
    sources = [
        {"dispositivo": "alsa_input.usb.microphone", "monitor": False, "rotulo": "microfone"},
        {"dispositivo": "alsa_output.pci.hdmi.monitor", "monitor": True, "rotulo": "saída"},
    ]

    def test_app_hint_never_receives_generic_monitor_or_microphone(self):
        with patch.object(escuta, "fontes_do_sistema", return_value=self.sources):
            for hint in ("discord", "som do jogo", "programa", "chamada", "app"):
                with self.subTest(hint=hint):
                    self.assertEqual(escuta.sugerir_dispositivo(hint), "")

    def test_explicit_real_source_still_allowed(self):
        with patch.object(escuta, "fontes_do_sistema", return_value=self.sources):
            self.assertEqual(escuta.sugerir_dispositivo(self.sources[1]["dispositivo"]),
                             self.sources[1]["dispositivo"])

    def test_system_sound_hint_can_select_mixed_monitor(self):
        with patch.object(escuta, "fontes_do_sistema", return_value=self.sources):
            self.assertEqual(escuta.sugerir_dispositivo("som do sistema"), self.sources[1]["dispositivo"])
            self.assertEqual(escuta.sugerir_dispositivo("meu microfone"), self.sources[0]["dispositivo"])

    def test_named_dedicated_endpoint_can_be_selected(self):
        dedicated = {"dispositivo": "discord_capture.monitor", "monitor": True, "rotulo": "dedicada"}
        with patch.object(escuta, "fontes_do_sistema", return_value=self.sources + [dedicated]):
            self.assertEqual(escuta.sugerir_dispositivo("som do Discord"), dedicated["dispositivo"])

    def test_missing_app_endpoint_opens_no_capture(self):
        with patch.object(escuta, "fontes_do_sistema", return_value=self.sources), \
                patch("tools.transcricao.Transcritor") as capture:
            result = escuta.ouvir("discord", "discord")
            self.assertIn("mistura", result)
            self.assertIn("nenhum canal foi aberto", result)
        capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
