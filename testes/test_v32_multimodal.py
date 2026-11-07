from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import config
from core import capabilities, dispatch
from tools import image_gen
from core.tts_router import TTSRouter, load_settings


def ok(name: str, condition: bool):
    if not condition:
        raise AssertionError(name)
    print(f"ok - {name}")


names = {item["function"]["name"] for item in dispatch.ESQUEMAS}
ok("cérebro usa variante Qwen3.5 9B uncensored", "Qwen3.5-9B-Uncensored-GGUF" in config.MODEL_NAME)
ok("contexto operacional reduzido para 16k", config.CONTEXTO_LLM_TOKENS == 16384)
ok("workspace é superfície pública", "workspace" in names)
ok("gerador de imagem exposto", "gerar_imagem" in names)
ok("estado da imagem exposto", "estado_imagem" in names)
ok("descarregar imagem exposto", "descarregar_imagem" in names)
ok("estado da imagem é consulta", capabilities.info("estado_imagem").mutates is False)
ok("imagem não bloqueia o turn", image_gen.gerar_imagem("").startswith("ERRO_IMAGEM:"))
ok("ASR configurado como large-v3/faster", config.WHISPER_MODELO == "large-v3" and config.TRANSCRITOR == "faster")
ok("ASR usa CPU int8", config.AUDIO_DEVICE == "cpu" and config.AUDIO_COMPUTE_TYPE == "int8")
ok("até 2 oradores", config.AUDIO_MAX_ORADORES == 2)
ok("TTS local Kokoro CPU", config.TTS_BACKEND == "kokoro" and "Kokoro" in config.TTS_MODEL and config.TTS_DEVICE == "cpu")
audio = TTSRouter(load_settings(ROOT)).state()
ok("fallback obrigatório Qwen3-TTS preservado", audio["local_fallback"] == "qwen3_tts")
ok("sem Azure configurado usa rota local existente", not audio["azure_configured"] and audio["preferred"] == audio["configured_local"])
ok("imagem Qwen-Image 2.1 Q6_K", config.IMAGE_MODEL_ID == "Qwen-Image-2.1-Q6_K")
ok("difusão GGUF configurada", Path(config.IMAGE_DIFFUSION_MODEL).name == "qwen_image_2.1-Q6_K.gguf")
ok("encoder e VAE separados", Path(config.IMAGE_LLM_MODEL).name == "Qwen3-VL-8B-Instruct-Q5_K_M.gguf"
   and Path(config.IMAGE_VAE_MODEL).name == "qwen_image_2.1_vae_bf16.safetensors")
ok("difusão Vulkan, encoder/VAE CPU", config.IMAGE_BACKEND == "te=cpu,diffusion=vulkan0,vae=cpu")
ok("parâmetros residentes na RAM", config.IMAGE_PARAMS_BACKEND == "te=cpu,diffusion=cpu,vae=cpu")
ok("VRAM da imagem respeita margem dos 8 GiB", 0 < config.IMAGE_MAX_VRAM_GIB <= 7)
print("V32_MULTIMODAL_OK")
