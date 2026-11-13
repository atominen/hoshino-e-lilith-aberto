"""Modelo externo SÓ PARA AS PROVAS (pedido humano, 07/11/2026).

Mesmo prompt, mesmas ferramentas e mesmo código, com um modelo forte no lugar do 9B: separa defeito nosso (prompt,
ferramenta, código) de limite do modelo (que vai para o treino).

É um intermediário local que fala como o Ollama (POST /api/chat) e repassa para uma API compatível com a da OpenAI
(Gemini pelo Google AI Studio, por padrão). As provas existentes só trocam o endereço. A tradução de formato é a
mesma do executor por API das entidades (app/core/executor_api.py).

- Chave em compartilhado/config/teste_api.env (fora do Git): GEMINI_API_KEY=... ou GROQ_API_KEY=...
- Mande só casos de teste: nada de memórias, diários ou conversas reais das entidades.

Uso:  python3 scripts/modelo_externo.py [--provedor gemini|groq] [--modelo NOME] [--porta 11499]
      depois aponte a prova para http://127.0.0.1:11499/api/chat (EVAL_URL=... ou AB_URL=...)
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "app"))
from core import executor_api as ea  # noqa: E402
from core.executor_api import PROVEDORES, Cliente, do_openai, para_openai  # noqa: E402,F401  (reexportados)


def servir(cliente: Cliente, porta: int):
    class Manipulador(BaseHTTPRequestHandler):
        def log_message(self, *args):  # sem registro do conteúdo
            pass

        def do_POST(self):
            if self.path.rstrip("/") != "/api/chat":
                self.send_error(404)
                return
            try:
                corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                saida = json.dumps({"model": cliente.modelo, "done": True,
                                    "message": cliente.chat(corpo, tentativas=3, limite_s=120)},
                                   ensure_ascii=False).encode()
                self.send_response(200)
            except Exception as exc:  # noqa: BLE001 — a prova vê o erro, não um sucesso falso
                saida = json.dumps({"error": str(exc)[:500]}).encode()
                self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(saida)))
            self.end_headers()
            self.wfile.write(saida)

    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)
    print(f"Modelo externo {cliente.provedor}/{cliente.modelo} em http://127.0.0.1:{porta}/api/chat (só provas)",
          flush=True)
    servidor.serve_forever()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--api", help="id de uma API cadastrada na Central (aba Modelos); usa a chave dela")
    p.add_argument("--provedor", choices=sorted(PROVEDORES), default="gemini")
    p.add_argument("--modelo")
    p.add_argument("--porta", type=int, default=11499)
    a = p.parse_args()
    if a.api:
        api = ea.carregar()["apis"].get(a.api)
        if not api:
            raise SystemExit(f"API {a.api!r} não está cadastrada na Central.")
        cliente = Cliente(api["provedor"], a.modelo or ea.modelo_de(api), url=ea.url_de(api), ident=a.api)
    else:
        cliente = Cliente(a.provedor, a.modelo)
    servir(cliente, a.porta)
