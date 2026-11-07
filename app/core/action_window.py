"""Adaptação do ciclo Building/Registered/Ended do Neuro SDK (MIT, Vedal AI).

Origem: Unity/Assets/Actions/ActionWindow.cs, 0cad33ac692f6cc90d36747fea9bbc53ca34b97a.
Sem Unity, websocket Neuro ou acesso ao cérebro privado: contratos locais de
ferramentas, validação estrita e resultados correlacionados por id.
"""
import copy
import json
import threading


def validate(schema, value, path="args"):
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path}: esperado objeto.")
        properties = schema.get("properties", {})
        unknown = set(value) - set(properties)
        if unknown:
            raise ValueError(f"{path}: campos desconhecidos: {', '.join(sorted(unknown))}.")
        for field in schema.get("required", []):
            if field not in value:
                raise ValueError(f"{path}.{field}: obrigatório.")
        for field, item in value.items():
            validate(properties[field], item, path + "." + field)
    elif kind == "string":
        if not isinstance(value, str) or not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 12000):
            raise ValueError(f"{path}: texto inválido ou fora do limite.")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{path}: esperado booleano, não texto/número.")
    else:
        raise ValueError(f"{path}: tipo de contrato não suportado.")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: valor inválido; opções: {schema['enum']}.")


class ActionWindow:
    def __init__(self):
        self.state = "building"
        self._actions, self._receipts = {}, {}
        self.lock = threading.RLock()

    def add(self, tool):
        with self.lock:
            if self.state != "building":
                raise ValueError("Janela registrada é imutável.")
            function = tool["function"]
            name = function["name"]
            if name in self._actions:
                raise ValueError("Ação já registrada.")
            self._actions[name] = copy.deepcopy(function["parameters"])
        return self

    def register(self):
        with self.lock:
            if self.state != "building" or not self._actions:
                raise ValueError("Janela vazia/já registrada.")
            self.state = "registered"
        return self

    def execute(self, identifier, name, args, executor):
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200:
            raise ValueError("Id de ação inválido.")
        signature = json.dumps([name, args], sort_keys=True, ensure_ascii=False, allow_nan=False)
        with self.lock:
            if self.state != "registered":
                raise ValueError("Janela não está ativa.")
            if identifier in self._receipts:
                receipt = self._receipts[identifier]
                if receipt["signature"] != signature:
                    raise ValueError("Id de ação reutilizado com parâmetros diferentes.")
                return copy.deepcopy(receipt["result"])
            try:
                if name not in self._actions:
                    raise ValueError("Ação não registrada.")
                validate(self._actions[name], args)
                # Execução permanece sob lock: ids simultâneos não repetem efeitos.
                result = {"ok": True, "action_id": identifier, "result": executor(name, args)}
            except Exception as exc:
                result = {"ok": False, "action_id": identifier, "error": str(exc)[:1000]}
            self._receipts[identifier] = {"signature": signature, "result": copy.deepcopy(result)}
            return result

    def end(self):
        with self.lock:
            self.state = "ended"

    def __enter__(self):
        return self.register()

    def __exit__(self, *args):
        self.end()
