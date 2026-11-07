"""Qwen-Image local, GPU arbitrada, parâmetros exatos e progresso persistente."""
from __future__ import annotations

import os
import queue
import re
import statistics
import sys
import subprocess
import threading
import time
import uuid
from pathlib import Path

import config
from core import diagnostics
from core import gpu_resource
from core import job_bus, resource_manager

_LOCK = threading.RLock()
_JOBS: dict[str, dict] = {}
_QUEUE: queue.Queue = queue.Queue(maxsize=2)
_WORKER = None
_ULTIMO_ERRO = ""
PRESETS = {"baixo": (512, 512, 8), "medio": (768, 768, 16),
           "alto": (1024, 1024, 24), "muito_alto": (1536, 1536, 32)}


class ImageYielded(RuntimeError):
    pass


def _sd_cli() -> str:
    return str(getattr(config, "IMAGE_SD_CLI", "") or "")


def _modelos() -> dict[str, str]:
    modelos = {
        "diffusion": str(config.IMAGE_DIFFUSION_MODEL),
        "llm": str(config.IMAGE_LLM_MODEL),
        "vae": str(config.IMAGE_VAE_MODEL),
    }
    ausentes = [f"{nome}={caminho}" for nome, caminho in modelos.items()
                if not Path(caminho).is_file()]
    if ausentes:
        raise RuntimeError(
            "arquivos do gerador ausentes: " + "; ".join(ausentes)
        )
    return modelos


def _normalizar_parametros(prompt, negative_prompt, largura, altura, passos, cfg, seed, nome, preset=""):
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("informe um prompt")
    preset = str(preset or "").strip().lower().replace("é", "e").replace(" ", "_")
    if preset in PRESETS:
        if any(value is not None for value in (largura, altura, passos)):
            raise ValueError("escolha um preset OU dimensões/passos explícitos, não ambos")
        largura, altura, passos = PRESETS[preset]
    elif preset not in {"", "personalizada"}:
        raise ValueError("preset inválido: baixo, medio, alto, muito_alto ou personalizada")
    elif preset == "personalizada" and any(value is None for value in (largura, altura, passos)):
        raise ValueError("personalizada exige largura, altura e passos explícitos")
    def exact_integer(value, default):
        value = default if value is None else value
        integer = int(value)
        if isinstance(value, bool) or (isinstance(value, float) and value != integer):
            raise ValueError("dimensões e passos devem ser inteiros, sem arredondamento")
        return integer
    largura = exact_integer(largura, config.IMAGE_WIDTH)
    altura = exact_integer(altura, config.IMAGE_HEIGHT)
    passos = exact_integer(passos, config.IMAGE_STEPS)
    cfg = float(config.IMAGE_CFG if cfg is None else cfg)
    if not all(256 <= value <= 2048 and value % 8 == 0 for value in (largura, altura)):
        raise ValueError("dimensões devem ser múltiplas de 8, entre 256 e 2048; nada foi reduzido")
    if not 1 <= passos <= 100:
        raise ValueError("passos devem estar entre 1 e 100; nada foi reduzido")
    if not 1.0 <= cfg <= 12.0:
        raise ValueError("cfg deve estar entre 1 e 12")
    stem = (Path(str(nome or "")).stem or config.ENTIDADE_ID)[:100]
    stem = f"{stem}_{uuid.uuid4().hex[:12]}"
    destino_dir = Path(config.IMAGE_OUTPUT_DIR)
    destino_dir.mkdir(parents=True, exist_ok=True)
    return {
        "prompt": prompt,
        "negative_prompt": str(negative_prompt or ""),
        "largura": largura,
        "altura": altura,
        "passos": passos,
        "cfg": cfg,
        "seed": int(seed),
        "preset": preset or "personalizada",
        "destino": str(destino_dir / f"{stem}.png"),
    }


def _observar_log(text: str, p: dict, job_id: str, started: float):
    """Lê progresso emitido pelo processo; contadores de carregamento não são steps."""
    current = job_bus.get(job_id, config.ENTIDADE_ID)
    if current is None:
        return
    details = current["details"]
    phase = details.get("phase", "loading")
    step = details.get("step", 0)
    seconds_per_step = details.get("seconds_per_step")
    for line in re.split(r"[\r\n]", text):
        if "sampling completed" in line:
            phase = "decoding"
        if phase == "decoding":
            continue
        match = re.search(r"\|[= >]+\|\s*(\d+)/(\d+)\s*-\s*([\d.]+)s/it", line)
        if match and int(match[2]) == p["passos"]:
            phase = "sampling"
            step = max(step, int(match[1]))
            seconds_per_step = float(match[3])
    eta = (p["passos"] - step) * seconds_per_step if phase == "sampling" and seconds_per_step else None
    job_bus.publish(job_id, config.ENTIDADE_ID, "running", phase=phase, step=step,
                    elapsed_seconds=round(time.monotonic() - started, 1),
                    seconds_per_step=seconds_per_step, eta_seconds=eta,
                    eta_scope="difusão; decodificação ainda não estimada" if eta is not None else None)


def _executar_sd(p: dict, log_path: Path, job_id: str) -> tuple[int, str]:
    cli = _sd_cli()
    if not cli or not Path(cli).is_file():
        raise RuntimeError(
            f"sd-cli não encontrado: {cli or '(não configurado)'}")

    modelos = _modelos()

    cmd = [
        cli,
        "--diffusion-model", modelos["diffusion"],
        "--vae", modelos["vae"],
        "--llm", modelos["llm"],
        "--cfg-scale", str(p["cfg"]),
        "--steps", str(p["passos"]),
        "--sampling-method", str(config.IMAGE_SAMPLER),
        "--backend", config.IMAGE_BACKEND,
        "--params-backend", config.IMAGE_PARAMS_BACKEND,
        "--max-vram", str(p.get('gpu_vram_gib',config.IMAGE_MAX_VRAM_GIB)),
        "--offload-to-cpu",
        "--diffusion-fa",
        "--vae-tiling",
        "-W", str(p["largura"]),
        "-H", str(p["altura"]),
        "-p", p["prompt"],
        "-o", p["destino"],
        "--log-level", "info",
    ]
    if p["negative_prompt"]:
        cmd.extend(["-n", p["negative_prompt"]])

    cmd.extend(["-s", str(p["seed"])])

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        supervisor = Path(__file__).resolve().parents[2] / "scripts/image_child.py"
        proc = subprocess.Popen([sys.executable, "-I", str(supervisor), str(os.getpid()), *cmd],
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        started = time.monotonic()
        offset = 0
        pending = ""
        try:
            while True:
                if resource_manager.higher_priority_waiting(2,include_audio=True):
                    diagnostics.emit('image.cancel_for_interactive',job_id=job_id,priority=4,resume_supported=False,auto_retry=False)
                    raise ImageYielded('Imagem interrompida para atender conversa/áudio. Este backend não suporta retomada; não será repetida automaticamente.')
                try:
                    proc.wait(timeout=2)
                    done = True
                except subprocess.TimeoutExpired:
                    done = False
                with log_path.open("rb") as reader:
                    reader.seek(offset)
                    raw = reader.read()
                    offset = reader.tell()
                pending += raw.decode("utf-8", errors="replace")
                # Uma barra pode chegar dividida entre duas leituras.
                boundary = max(pending.rfind("\n"), pending.rfind("\r"))
                if boundary >= 0:
                    _observar_log(pending[:boundary + 1], p, job_id, started)
                    pending = pending[boundary + 1:]
                elif not done:
                    _observar_log("", p, job_id, started)
                if done:
                    if pending:
                        _observar_log(pending, p, job_id, started)
                    break
                if time.monotonic() - started > int(config.IMAGE_TIMEOUT):
                    raise TimeoutError("geração excedeu o tempo configurado; parâmetros não foram reduzidos")
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    saida = ""
    try:
        saida = log_path.read_text(
            encoding="utf-8", errors="replace")[-12000:]
    except OSError:
        pass

    return proc.returncode, saida


def _gerar_job(job_id: str, p: dict) -> None:
    global _ULTIMO_ERRO
    log_path = Path(config.IMAGE_RUNTIME_DIR) / "diagnostics" / f"imagem_{job_id}.log"
    try:
        _JOBS[job_id].update(status="running", started_at=time.time())
        job_bus.publish(job_id, config.ENTIDADE_ID, "running", phase="waiting_gpu", step=0)
        # Um único lease para toda a janela em que o SD usa a GPU.
        with gpu_resource.lease("image",wait=600) as acquired:
            p = dict(p)
            if acquired and 'vram_budget_bytes' in acquired:
                p['gpu_vram_gib'] = acquired['vram_budget_bytes']/1024**3
                job_bus.publish(job_id,config.ENTIDADE_ID,'running',gpu_vram_gib=p['gpu_vram_gib'],
                                gpu_budget_adjusted=p['gpu_vram_gib']!=config.IMAGE_MAX_VRAM_GIB)
            _JOBS[job_id]["ollama_descarregado"] = "residência avaliada; unload somente quando necessário e vantajoso"
            started = time.monotonic()
            job_bus.publish(job_id, config.ENTIDADE_ID, "running", phase="loading", started_at=time.time())
            rc, log = _executar_sd(p, log_path, job_id)
        if rc != 0 or not Path(p["destino"]).is_file():
            tail = log[-1200:].replace("\n", " ")
            raise RuntimeError(f"sd-cli saiu com código {rc}; log={tail}")
        from PIL import Image
        with Image.open(p["destino"]) as generated:
            generated.verify()
        with Image.open(p["destino"]) as generated:
            if generated.size != (p["largura"], p["altura"]):
                raise RuntimeError("dimensões da imagem diferentes do pedido")
        diagnostics.emit(
            "image.generated", job_id=job_id, path=p["destino"],
            width=p["largura"], height=p["altura"], steps=p["passos"], seed=p["seed"])
        _JOBS[job_id].update(
            status="done", path=p["destino"], resolution=f'{p["largura"]}x{p["altura"]}',
            model=config.IMAGE_MODEL_ID, finished_at=time.time(), log=str(log_path))
        job_bus.publish(job_id, config.ENTIDADE_ID, "done", path=p["destino"], log=str(log_path),
                        phase="verified", step=p["passos"], eta_seconds=0,
                        elapsed_seconds=round(time.monotonic() - started, 1))
        _ULTIMO_ERRO = ""
    except Exception as exc:
        _ULTIMO_ERRO = f"{type(exc).__name__}: {exc}"
        diagnostics.emit("image.generate_failed", level="ERROR", job_id=job_id, error=_ULTIMO_ERRO)
        status = 'interrupted' if isinstance(exc,ImageYielded) else 'error'
        _JOBS[job_id].update(status=status, error=_ULTIMO_ERRO, finished_at=time.time(), log=str(log_path))
        job_bus.publish(job_id, config.ENTIDADE_ID, status, error=_ULTIMO_ERRO, log=str(log_path),auto_retry=False,resume_supported=False)


def _worker_loop():
    while True:
        job_id, params = _QUEUE.get()
        try:
            if job_id is None:
                return
            _gerar_job(job_id, params)
        finally:
            _QUEUE.task_done()


def _garantir_worker():
    global _WORKER
    if _WORKER is not None and _WORKER.is_alive():
        return
    _WORKER = threading.Thread(target=_worker_loop, name="hoshino-image-worker", daemon=True)
    _WORKER.start()


def disponibilidade(job_id: str = "") -> str:
    cli_ok = bool(_sd_cli() and Path(_sd_cli()).is_file())
    diffusion_ok = Path(config.IMAGE_DIFFUSION_MODEL).is_file()
    llm_ok = Path(config.IMAGE_LLM_MODEL).is_file()
    vae_ok = Path(config.IMAGE_VAE_MODEL).is_file()

    base = (
        f"modelo={config.IMAGE_MODEL_ID} | "
        f"diffusion={Path(config.IMAGE_DIFFUSION_MODEL).name} | "
        f"llm={Path(config.IMAGE_LLM_MODEL).name} | "
        f"vae={Path(config.IMAGE_VAE_MODEL).name} | "
        f"arquivos={'ok' if diffusion_ok and llm_ok and vae_ok else 'ausente'} | "
        f"device={config.IMAGE_DEVICE} | params=RAM/offload-cpu | "
        f"sd_cli={'ok' if cli_ok else 'ausente'} | fila={_QUEUE.qsize()}"
    )

    if job_id:
        persisted = job_bus.get(str(job_id), config.ENTIDADE_ID)
        job = ({"job_id": persisted["id"], "status": persisted["status"], **persisted["details"]}
               if persisted else None)
        if not job:
            return base + " | job=nao_encontrado"
        return base + " | " + " ".join(
            f"{k}={v}" for k, v in job.items())

    return base + (f" | erro={_ULTIMO_ERRO}" if _ULTIMO_ERRO else "")


def tem_trabalho_pendente() -> bool:
    return any(j.get("status") in {"queued", "running"} for j in list(_JOBS.values()))


def gerar_imagem(prompt: str, negative_prompt: str = "", largura: int | None = None,
                 altura: int | None = None, passos: int | None = None,
                 cfg: float | None = None, seed: int = -1, nome: str = "", preset: str = "") -> str:
    if not _sd_cli() or not Path(_sd_cli()).is_file():
        return f"ERRO_IMAGEM: sd-cli ausente em {_sd_cli() or '(não configurado)'}"
    try:
        params = _normalizar_parametros(prompt, negative_prompt, largura, altura, passos, cfg, seed, nome, preset)
        _modelos()  # Falha antes de enfileirar se a infraestrutura estiver incompleta.
    except Exception as exc:
        return f"ERRO_IMAGEM: {type(exc).__name__}: {exc}"
    _garantir_worker()
    job_id = f"img-{uuid.uuid4().hex[:12]}"
    _JOBS[job_id] = {
        "job_id": job_id, "status": "queued", "created_at": time.time(),
        "prompt_chars": len(params["prompt"]), "resolution": f'{params["largura"]}x{params["altura"]}',
        "steps": params["passos"], "seed": params["seed"],
    }
    history = [job["details"]["elapsed_seconds"] for job in job_bus.status(limit=200)
               if job["status"] == "done" and job["details"].get("model") == config.IMAGE_MODEL_ID
               and job["details"].get("resolution") == _JOBS[job_id]["resolution"]
               and job["details"].get("steps") == params["passos"] and job["details"].get("elapsed_seconds")]
    job_bus.publish(job_id, config.ENTIDADE_ID, "queued", resolution=_JOBS[job_id]["resolution"],
                    steps=params["passos"], seed=params["seed"], preset=params["preset"],
                    model=config.IMAGE_MODEL_ID, phase="queued", path=params["destino"],
                    estimated_seconds=statistics.median(history) if history else None,
                    estimate_samples=len(history))
    try:
        _QUEUE.put_nowait((job_id, params))
    except queue.Full:
        _JOBS[job_id].update(status="error", error="fila de imagens cheia")
        job_bus.publish(job_id, config.ENTIDADE_ID, "error", error="fila de imagens cheia")
        return f"ERRO_IMAGEM: fila de imagens cheia. job_id={job_id}"
    diagnostics.emit("image.queued", job_id=job_id, prompt_chars=len(params["prompt"]))
    return f"IMAGEM_ENFILEIRADA=SIM\nJOB_ID={job_id}\nRESOLUCAO={params['largura']}x{params['altura']}\nSTATUS=queued\nUse estado_imagem com job_id={job_id} para consultar."


def descarregar() -> str:
    # O modelo é um processo por job; não há pesos residentes neste processo.
    return "modelo de imagem é carregado por job e descarregado ao finalizar."
