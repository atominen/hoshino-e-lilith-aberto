"""Inventário factual de entradas e streams; monitor de sink não isola app."""
import json
import shutil
import subprocess
import time
from core.job_bus import _process_stamp

_cached = None
_at = 0.0


def inventory(refresh=False):
    global _cached, _at
    if not refresh and _cached is not None and time.monotonic() - _at < 10:
        return _cached
    result = {"available": False, "sources": [], "streams": [], "default_output": None,
              "physical_microphone_detected": False, "application_capture_isolated": False}
    if not shutil.which("pactl"):
        result["detail"] = "Inventário do sistema indisponível; o navegador lista seus próprios microfones."
        return result
    try:
        def get(what):
            p = subprocess.run(["pactl", "--format=json", "list", what], capture_output=True, text=True, timeout=3)
            if p.returncode != 0:
                raise RuntimeError("servidor de som indisponível")
            return json.loads(p.stdout)
        for source in get("sources"):
            name = source.get("name", "")
            if name.startswith('hoshino.listen.'):continue
            properties = source.get("properties", {})
            monitor = (name.endswith(".monitor") or properties.get("device.class") == "monitor"
                       or bool(source.get("monitor_source"))
                       or source.get("monitor_of_sink") not in (None, "", 4294967295, "4294967295"))
            label = source.get("description")
            if not label or label == "(null)":
                label = properties.get("device.description") or name
                if monitor:
                    label += " · monitor da saída"
            physical = not monitor and ("HARDWARE" in source.get("flags", []) or properties.get("device.api") in {"alsa", "bluez5"})
            result["sources"].append({"id": name, "label": label, "physical": physical,
                                      "kind": "output_mix" if monitor else "microphone",
                                      "application": None, "isolated_capture": False,
                                      "serial":str(properties.get('object.serial',''))})
        for stream in get("sink-inputs"):
            props = stream.get("properties", {})
            if str(props.get('node.name','')).startswith('hoshino.listen.'):continue
            serial=str(props.get('object.serial',''));pid=int(props.get('application.process.id') or 0)
            stamp=_process_stamp(pid) if pid else None
            can_isolate=bool(serial and pid and stamp and all(shutil.which(c) for c in ('pw-loopback','pw-link','pw-dump','parec')))
            result["streams"].append({"id": f'pw:{serial}:{pid}:{stamp}' if serial else f"sink-input:{stream.get('index')}", "kind": "application_stream",
                                       "application": props.get("application.name") or props.get("application.process.binary") or "desconhecido",
                                       "label": props.get("application.name") or "stream de reprodução",
                                       "isolated_capture": can_isolate,"serial":serial,"pid":pid})
        p = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=3)
        result["default_output"] = p.stdout.strip() if p.returncode == 0 else None
        result["available"] = True
        result["physical_microphone_detected"] = any(s["physical"] for s in result["sources"])
        result["detail"] = "Fontes do sistema são separadas de streams de aplicativos; monitores misturam a saída do sink."
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        result["detail"] = "Não foi possível consultar o servidor de som."
    _cached, _at = result, time.monotonic()
    return result
