"""
A chave da internet.

Desligar a internet dela precisa significar três coisas ao mesmo tempo, senão não
é desligar de verdade:

1. **A ferramenta recusa.** Pesquisa, leitura de página e download param, com uma
   mensagem clara em vez de um erro de rede confuso.
2. **Ela sabe que está sem.** O estado entra no prompt em primeira pessoa. Sem
   isso, o modelo promete "vou pesquisar e te falo", tenta, falha, e a conversa
   inteira vira desculpa — que é o pior dos dois mundos.
3. **O plano muda.** A curiosidade dela continua existindo; o que muda é o caminho.
   Offline, investigar vira olhar a própria memória, olhar a tela, ou perguntar à
   pessoa — o kernel consulta este módulo antes de escolher.

O que **nunca** é bloqueado: `localhost` e `127.0.0.1`. O modelo dela roda no
Ollama local — cortar isso não seria modo avião, seria desligar a Hoshino. A mesma
regra vale para qualquer serviço que você suba na própria máquina.

O estado fica em `runtime/rede.json`, fora do estado da mente, porque é política
sua e não humor dela: sobrevive a reinício, dá para editar na mão, e o histórico
de quem ligou/desligou e por quê fica registrado.
"""
import json
import os
import sys
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

ARQUIVO = os.path.join(config.RUNTIME_DIR, "rede.json")
LOCAIS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}
MAX_HISTORICO = 20


def _ler() -> dict:
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        padrao = os.environ.get("HOSHINO_OFFLINE", "0") != "1"
        return {"ativa": padrao, "motivo": "", "por": "padrão",
                "desde": datetime.now().isoformat(timespec="seconds"), "historico": []}


def _gravar(dados: dict) -> None:
    try:
        os.makedirs(os.path.dirname(ARQUIVO), exist_ok=True)
        tmp = ARQUIVO + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ARQUIVO)
    except OSError:
        pass


def ativa() -> bool:
    return bool(_ler().get("ativa", True))


def estado() -> dict:
    dados = _ler()
    return {"ativa": dados.get("ativa", True), "motivo": dados.get("motivo", ""),
            "por": dados.get("por", ""), "desde": dados.get("desde", "")}


def _mudar(novo: bool, motivo: str, por: str) -> str:
    dados = _ler()
    antes = dados.get("ativa", True)
    agora = datetime.now().isoformat(timespec="seconds")
    if antes == novo:
        return (f"A internet já está {'ligada' if novo else 'desligada'}"
                + (f" desde {dados.get('desde', '')[:16]}." if dados.get("desde") else "."))
    historico = dados.get("historico", [])
    historico.insert(0, {"quando": agora, "para": "ligada" if novo else "desligada",
                         "por": por[:40], "motivo": motivo[:200]})
    _gravar({"ativa": novo, "motivo": motivo[:200], "por": por[:40], "desde": agora,
             "historico": historico[:MAX_HISTORICO]})
    if novo:
        return "Internet religada. Pesquisa, leitura de página e download voltaram."
    return ("Internet desligada. Só continua valendo o que é local: o Ollama, os "
            "arquivos, a tela, a memória e a oficina.")


def desligar(motivo: str = "", por: str = "usuário") -> str:
    return _mudar(False, motivo or "sem motivo declarado", por)


def ligar(motivo: str = "", por: str = "usuário") -> str:
    return _mudar(True, motivo or "sem motivo declarado", por)


def alternar(por: str = "usuário") -> str:
    return ligar(por=por) if not ativa() else desligar(por=por)


# ------------------------------------------------------------------ guardas
def e_local(url: str) -> bool:
    """Endereço da própria máquina — nunca bloqueado."""
    if not url:
        return False
    try:
        alvo = urlparse(url if "://" in url else f"http://{url}")
        host = (alvo.hostname or "").lower()
    except ValueError:
        return False
    return host in LOCAIS or host.endswith(".local")


def permitido(url: str = "") -> bool:
    return ativa() or e_local(url)


def exigir(operacao: str = "acessar a internet", url: str = "") -> tuple:
    """(pode, mensagem). A mensagem é o que a ferramenta devolve ao recusar."""
    if permitido(url):
        return True, ""
    dados = estado()
    detalhe = f" ({dados['motivo']})" if dados.get("motivo") else ""
    return False, (f"REDE_DESLIGADA: não posso {operacao} — a internet está desligada"
                   f"{detalhe}. Continua funcionando o que é local: memória, arquivos, "
                   f"tela, oficina e o modelo no Ollama. Para religar: ferramenta "
                   f"`ligar_internet` ou a tecla F10.")


# ------------------------------------------------------------------- prompt
def bloco_para_prompt() -> str:
    """Em primeira pessoa: é uma condição minha, não um aviso de sistema."""
    if ativa():
        return ""
    dados = estado()
    motivo = f" Motivo: {dados['motivo']}." if dados.get("motivo") else ""
    return ("[ESTOU SEM INTERNET AGORA]" + motivo + " Não adianta eu tentar pesquisar, "
            "abrir link ou baixar nada — vai voltar recusado. Então eu não prometo "
            "procurar, não digo 'vou verificar e te falo' e não invento o que eu teria "
            "achado. O que eu ainda posso fazer: consultar o que já está na minha "
            "memória, olhar a tela, ler arquivos, rodar coisa na oficina e perguntar "
            "para a pessoa. Se algo realmente depender da internet, eu digo isso de uma "
            "vez em vez de enrolar.")


def caminhos_offline() -> list:
    """O que sobra para matar curiosidade sem rede — usado pelo kernel."""
    return ["recordar", "observar", "perguntar", "minimo"]


def resumo() -> str:
    dados = estado()
    if dados["ativa"]:
        return "internet: ligada"
    return (f"internet: DESLIGADA desde {dados['desde'][:16]}"
            + (f" ({dados['motivo']})" if dados["motivo"] else ""))
