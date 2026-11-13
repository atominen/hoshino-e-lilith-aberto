"""Do exemplo do banco às fichas do treino: o mesmo formato no montador e no treinador (sem torch).

Texto (até 07/11): pessoa/entidade em texto, até 256 fichas, só a última fala da entidade é alvo.

Ferramenta (12/11, pedido humano "atualize o banco de treinamento"): com os pesos treinados no v5 e no v6 a Lilith
escrevia "Vou conectar agora" e não chamava nada (0/5; o 9B original: 5/5). O banco só ensinava texto, porque este
treinador recusava os papéis `tool` e `tool_calls`. Agora o exemplo com ferramenta é montado pelo próprio modelo de
chat do Qwen3.5 (o mesmo que o Ollama usa na inferência), com as definições das ferramentas no system, e TODA fala
da entidade vira alvo: as chamadas (`<tool_call>…`) e a resposta final. O resto (system, pessoa, resultado da
ferramenta) fica mascarado. Prova da medição: compartilhado/runtime/ensaios/acao-minecraft-20261112/.
"""
from __future__ import annotations

MAX_TEXTO = 256
# As definições das ferramentas no system custam ~250 fichas de cabeçalho mais ~60–120 por ferramenta.
MAX_FERRAMENTA = 768
PAPEIS_FERRAMENTA = ('user', 'assistant', 'tool')


def _template(tok, mensagens, *, tools=None, gerar=False):
    return tok.apply_chat_template(mensagens, tools=tools, tokenize=False, add_generation_prompt=gerar,
                                   enable_thinking=False)


def _ids(tok, texto):
    return tok(texto, add_special_tokens=False).input_ids


def tokenize_texto(tok, messages, identity=None):
    """Formato original (inalterado): alvo só na última fala da entidade."""
    if len(messages) < 2 or messages[-1].get('role') != 'assistant':
        return None
    if any(not isinstance(m.get('content'), str) or m.get('role') not in ('user', 'assistant') for m in messages):
        return None
    context = [{'role': 'system', 'content': identity}] if identity else []
    prefix = tok.apply_chat_template(context + messages[:-1], tokenize=False, add_generation_prompt=True,
                                     enable_thinking=False)
    full = tok.apply_chat_template(context + messages, tokenize=False, add_generation_prompt=False,
                                   enable_thinking=False)
    a = _ids(tok, prefix)
    b = _ids(tok, full)
    if b[:len(a)] != a or len(b) > MAX_TEXTO or len(a) == len(b):
        return None
    return b, [-100] * len(a) + b[len(a):]


def ferramentas_validas(tools) -> bool:
    if not isinstance(tools, list) or not tools:
        return False
    for t in tools:
        if not isinstance(t, dict) or t.get('type') != 'function':
            return False
        f = t.get('function')
        if not isinstance(f, dict) or not isinstance(f.get('name'), str):
            return False
        if not isinstance(f.get('parameters', {}), dict):
            return False
    return True


def tokenize_ferramenta(tok, messages, identity=None, tools=None):
    """Exemplo com chamada de ferramenta: alvo nas falas da entidade da última rodada (chamadas e resposta final).

    O modelo de chat do Qwen3.5 reescreve as falas de rodadas anteriores (tira o bloco de pensamento vazio), então só a
    última rodada, depois da última fala da pessoa, tem prefixo estável. As rodadas anteriores ficam como contexto."""
    if not ferramentas_validas(tools) or len(messages) < 2 or messages[-1].get('role') != 'assistant':
        return None
    oferecidas = {t['function']['name'] for t in tools or []}
    chamou = False
    for m in messages:
        if m.get('role') not in PAPEIS_FERRAMENTA or not isinstance(m.get('content', ''), str):
            return None
        calls = m.get('tool_calls')
        if calls:
            if m['role'] != 'assistant' or not isinstance(calls, list):
                return None
            for c in calls:
                nome = ((c or {}).get('function') or {}).get('name')
                if nome not in oferecidas or not isinstance(c['function'].get('arguments', {}), dict):
                    return None  # chamar o que não foi oferecido ensinaria a inventar ferramenta
            chamou = True
    if not chamou or messages[0].get('role') != 'user' or messages[-1].get('tool_calls'):
        return None
    context = [{'role': 'system', 'content': identity}] if identity else []
    ids = _ids(tok, _template(tok, context + messages, tools=tools))
    if len(ids) > MAX_FERRAMENTA:
        return None
    labels = [-100] * len(ids)
    ultima_fala = max(i for i, m in enumerate(messages) if m['role'] == 'user')
    for i, m in enumerate(messages):
        if m['role'] != 'assistant' or i < ultima_fala:
            continue
        a = _ids(tok, _template(tok, context + messages[:i], tools=tools, gerar=True))
        b = _ids(tok, _template(tok, context + messages[:i + 1], tools=tools))
        # O modelo de chat precisa ser estável em prefixo; se reescrever turnos antigos, recusa (não adivinha).
        if b[:len(a)] != a or ids[:len(b)] != b or len(b) == len(a):
            return None
        labels[len(a):len(b)] = ids[len(a):len(b)]
    return ids, labels


def tokenize(tok, messages, identity=None, tools=None):
    return tokenize_ferramenta(tok, messages, identity, tools) if tools else tokenize_texto(tok, messages, identity)


def max_length(com_ferramenta: bool) -> int:
    return MAX_FERRAMENTA if com_ferramenta else MAX_TEXTO
