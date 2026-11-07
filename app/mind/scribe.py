"""
O escriba — memória que se forma sozinha.

Este módulo existe por causa de uma constatação no banco real: em seis conversas,
a Hoshino recebeu "eu sou gustavo rosa nunes seu criador" e a tabela `memories`
terminou com **zero** linhas. As ferramentas de memória estavam lá, funcionando,
documentadas no prompt. O modelo simplesmente não as chamou.

A lição vale para o sistema inteiro: o que precisa ser confiável não pode depender
de o modelo lembrar de chamar uma função. Então a memória virou consequência
automática do turno, em duas camadas:

1. **Regras** (este arquivo, Python puro). Padrões de autodeclaração em português
   — nome, papel, gosto, ofício, lugar, combinado, propriedade. Roda sempre, não
   custa nada, não depende de modelo nenhum estar bem-humorado. É o que garante
   que "eu sou o Gustavo" nunca mais se perca.

2. **Modelo** (`prompt_extracao` + `aplicar_extracao`). Uma chamada separada,
   curta, que só devolve JSON, rodando *depois* de a resposta já estar na tela —
   então não atrasa nada. Pega o que regex não pega. Se vier malformado, é
   descartado sem barulho.

De quebra, o escriba observa o comportamento **dela** no turno e converte em
evidência de personalidade: perguntou → curiosidade; discordou → franqueza; foi
curta → concisão. É assim que o jeito dela se forma sem ninguém escrever uma lista
de adjetivos num JSON.
"""
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bd  # noqa: E402
from memory import knowledge_store as saber  # noqa: E402
from mind import affect, personality  # noqa: E402
import config  # noqa: E402


def origem_entrada(pessoa=None, canal='tui', mensagem=None, history_id=''):
    """Dados do transporte, não inferências do LLM; sem acesso a outro banco mental."""
    p, m = pessoa or {}, mensagem or {}
    author = str(m.get('sender') or p.get('id') or 'usuario')
    entity = author in {'hoshino', 'lilith', 'alistair'} or canal == 'interentidades'
    name = str(p.get('nome') or author)
    if author in {'hoshino', 'lilith', 'alistair'}:
        name = author.capitalize()
    metadata = m.get('metadata') if isinstance(m.get('metadata'), dict) else {}
    from memory.audience import public_message
    if public_message(m) and author=='usuario':name='usuario'
    result=dict(autor_id=author, autor_nome=name, autor_tipo='entidade' if entity else 'humano',
                sujeito_id=author, sujeito_nome=name, ouvinte_id=config.ENTIDADE_ID,
                canal=canal, message_id=m.get('id') or history_id,
                chat_scope='global' if public_message(m) else 'direct',
                history_id=history_id, source_id=m.get('source_id'),
                submission_id=metadata.get('submission_id'),
                conversation_session_id=(metadata.get('conversation_session') or {}).get('id'),
                conversation_local_date=(metadata.get('conversation_session') or {}).get('local_date'),
                timestamp=m.get('created_at') or m.get('ts') or datetime.now(timezone.utc).isoformat())
    from core import speech_perception
    if canal in {'teste_local','local'} and metadata.get('synthetic_test') is True:
        result.update(autor_tipo='sistema_teste',synthetic_test=True,test_actor=str(metadata.get('test_actor') or 'harness local'))
    if speech_perception.is_voice(m):
        result.update(input_modality='speech',speech_perception=speech_perception.origin(metadata))
    return result


def _origem_atual(origem=None):
    from core import diagnostics
    ctx = diagnostics.current_turn_context()
    result = dict(origem or origem_entrada())
    if ctx.get('turn_id'):
        result.setdefault('turn_id', ctx['turn_id'])
        result['learning_turn_id'] = ctx['turn_id']
    if ctx.get('input_ids'):
        result['input_ids'] = ctx['input_ids']
    return result


def _atribuir(achados, origem):
    """Escopo por participante em chaves/links existentes; compatível com legados."""
    origin = _origem_atual(origem)
    subject = origin['sujeito_id']
    name = next((a['nome_detectado'] for a in achados if a.get('nome_detectado')), origin['sujeito_nome'])
    # O conteúdo declarado não pode renomear a autoria autenticada do transporte.
    author_name = name if origin['autor_tipo'] == 'humano' and origin['autor_nome'] in {'usuario', 'usuário'} else origin['autor_nome']
    origin = dict(origin, sujeito_nome=name, autor_nome=author_name,
                  basis='informacao_declarada_nao_verificada_externamente')
    for a in achados:
        a['origem'] = origin
        a['entidades'] = [f'participante:{subject}', name]  # objeto comum não é identidade do sujeito
        a['conteudo'] = a['conteudo'].replace('A pessoa com quem falo', name).replace('O usuário', name).replace('do usuário', f'de {name}').replace('com o usuário', f'com {name}').replace('Esta pessoa', name)
        if subject != 'usuario':
            a['chave'] = f"{a.get('chave', 'declaracao')}:participante:{subject}"
        if origin['autor_tipo'] != 'humano':
            a.pop('papel', None)
            a.pop('gosto_usuario', None)
        if origin['autor_tipo'] != 'humano' and a.get('nome_detectado'):
            a.pop('nome_detectado', None)  # nunca renomeia o interlocutor humano
    return achados


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn").lower()


# Palavras que encerram um nome próprio ("eu sou gustavo rosa nunes seu criador").
CORTE_NOME = {
    "seu", "sua", "teu", "tua", "meu", "minha", "o", "a", "os", "as", "um", "uma",
    "de", "do", "da", "dos", "das", "e", "que", "mas", "muito", "meio", "bem",
    "mais", "menos", "so", "apenas", "tipo", "aqui", "agora", "hoje", "ainda",
    "sempre", "nunca", "quem", "pra", "para", "com", "sem", "eu", "voce", "vc",
    # 06/11: "eu sou o Gustavo rosa nunes prazer em te conhecer" — o nome para antes da saudação.
    "prazer", "obrigado", "obrigada", "tudo", "te", "conhecer", "beleza",
}
# Papel em relação a ela (quem a pessoa é PARA a Hoshino).
PAPEIS = {
    "criador": "criador", "criadora": "criadora", "dono": "dono", "dona": "dona",
    "usuario": "usuário", "humano": "humano", "amigo": "amigo", "amiga": "amiga",
    "responsavel": "responsável", "chefe": "chefe",
}
# Profissões: não são nome próprio, mas são ofício — viram fato, não papel.
OFICIOS = {
    "programador", "desenvolvedor", "engenheiro", "engenheira", "designer", "medico",
    "medica", "professor", "professora", "estudante", "advogado", "advogada",
    "analista", "tecnico", "tecnica", "administrador", "enfermeiro", "enfermeira",
}
# Lixo que aparece depois de "gosto de" e não é objeto de gosto nenhum.
NAO_E_OBJETO = {"voce", "vc", "isso", "aquilo", "tudo", "nada", "mim", "ti", "la", "ca"}

MARCADOR_NOME = re.compile(
    r"\b(?:meu nome (?:é|e)|me chamo|pode me chamar de|eu sou|sou o|sou a)\s+"
    r"([^.,;!?\n]{2,70})", re.IGNORECASE)
PAPEL_ACAO = re.compile(
    r"\beu (?:te |lhe )?(?:criei|fiz|programei|montei|constru[ií]|instalei)\b", re.IGNORECASE)
PAPEL_TITULO = re.compile(
    r"\b(?:sou|fui)\b[^.?!\n]{0,60}?\b(?:seu|sua|o|a)\s+"
    r"(?:criador|criadora|dono|dona|respons[áa]vel)\b", re.IGNORECASE)
PAPEL_PERGUNTA = re.compile(r"\bquem\s+(?:te|lhe|a)\s+(?:criou|fez|programou)", re.IGNORECASE)
OCUPACAO_SUFIXO = re.compile(
    r"\b(?:eu\s+)?sou\s+(?:um[a]?\s+)?([a-zà-ú]{4,20}(?:or|ora|ista|eiro|eira|"
    r"ico|ica|ante|ente|ogo|oga|grafo|grafa))\b", re.IGNORECASE)
MARCADOR_GOSTO = re.compile(
    r"\b(?:eu )?(gosto de|amo|adoro|curto|prefiro(?! que)|sou f[ãa] de)\s+"
    r"([^.,;!?\n]{3,60})",
    re.IGNORECASE)
MARCADOR_DESGOSTO = re.compile(
    r"\b(?:eu )?(n[ãa]o gosto de|odeio|detesto|n[ãa]o curto|n[ãa]o suporto|"
    r"tenho (?:nojo|raiva) de)\s+([^.,;!?\n]{3,60})", re.IGNORECASE)
MARCADOR_OFICIO = re.compile(
    r"\b(?:eu )?(trabalho|estudo|fa[çc]o faculdade)\s+(?:com|em|na|no|de)\s+"
    r"([^.,;!?\n]{3,60})", re.IGNORECASE)
MARCADOR_LUGAR = re.compile(
    r"\b(?:eu )?(?:moro|vivo|estou morando)\s+(?:em|no|na)\s+([^.,;!?\n]{3,50})",
    re.IGNORECASE)
MARCADOR_PROPRIEDADE = re.compile(
    r"\bm(?:eu|inha)\s+([a-zà-ú][\w\sà-ú]{2,28}?)\s+(?:é|e|tem|possui)\s+"
    r"(?:um[ a]?\s+)?([^.,;!?\n]{2,45})", re.IGNORECASE)
MARCADOR_COMBINADO = re.compile(
    r"\b(?:prefiro que|quero que|gostaria que|de agora em diante|a partir de agora|"
    r"sempre que|nunca mais|n[ãa]o (?:precisa|quero que você)|pode (?:sempre|parar de))\s+"
    r"([^.;!?\n]{4,110})", re.IGNORECASE)

ELOGIO = re.compile(
    r"\b(valeu|obrigad[oa]|perfeito|isso mesmo|mandou bem|adorei|gostei|"
    r"excelente|exatamente isso|muito bom|ficou [óo]timo|"
    r"boa(?!\s+(?:noite|tarde|dia|madrugada|sorte|viagem|semana)))\b", re.IGNORECASE)
CRITICA = re.compile(
    r"\b(errado|n[ãa]o (?:é|e) isso|n[ãa]o foi isso|de novo n[ãa]o|para de|pare de|"
    r"chato|ruim|p[ée]ssimo|n[ãa]o funciona|nada a ver|burra|besteira)\b", re.IGNORECASE)
DISCORDANCIA = re.compile(
    r"\b(discordo|n[ãa]o concordo|acho que n[ãa]o|n[ãa]o (?:é|e) bem assim|"
    r"discordar|prefiro n[ãa]o|n[ãa]o vou fazer|n[ãa]o quero)\b", re.IGNORECASE)
AFETO = re.compile(
    r"\b(fico feliz|gostei|me importo|senti falta|saudade|fico contente|"
    r"que bom|fico aliviada|torcendo)\b", re.IGNORECASE)
BRINCADEIRA = re.compile(r"(\bhaha\b|\bkkk|\brs\b|ironia|brincadeira|zoando|\bpiada\b)",
                         re.IGNORECASE)


ADVERBIO_SOLTO = re.compile(
    r"\s+(?:tamb[ée]m|tbm?|demais|muito|bastante|pra caramba|as vezes|[àa]s vezes)$",
    re.IGNORECASE)
CONJUGA = {"trabalho": "trabalha", "estudo": "estuda", "faço faculdade": "faz faculdade",
           "faco faculdade": "faz faculdade"}


def _limpar(t: str) -> str:
    t = re.sub(r"\s+", " ", (t or "").strip())
    t = t.strip(" .,;:!?\"'()")
    return ADVERBIO_SOLTO.sub("", t).strip()


def _extrair_nome(trecho: str):
    """Pega o nome próprio depois de 'eu sou' / 'me chamo', tolerando minúsculas.

    Reais digitam 'eu sou gustavo rosa nunes seu criador', tudo em caixa baixa —
    então não dá para depender de letra maiúscula. A parada é por palavra-corte.
    """
    tokens = _limpar(trecho).split()
    # 06/11: "eu sou O Gustavo" — o artigo antes do nome parava a leitura e o nome se perdia.
    while tokens and _sem_acento(tokens[0].strip(" .,;:!?")) in {"o", "a"}:
        tokens = tokens[1:]
    nome = []
    for tok in tokens[:5]:
        limpo = _sem_acento(tok.strip(" .,;:!?"))
        if not limpo or not re.fullmatch(r"[a-zà-ú'-]{2,20}", limpo):
            break
        if limpo in CORTE_NOME:
            break
        if limpo in PAPEIS or limpo in OFICIOS:   # "sou o criador"/"sou programador"
            break
        nome.append(tok.strip(" .,;:!?"))
        if len(nome) == 4:
            break
    if not nome:
        return None
    texto = " ".join(nome)
    # Frases como "eu sou meio cansado" ou "sou bem direto" não são nomes.
    if len(texto) < 3 or _sem_acento(texto) in CORTE_NOME:
        return None
    return " ".join(p.capitalize() if p.islower() else p for p in nome)


def extrair_por_regra(texto: str, *, origem=None) -> list:
    """Fatos duráveis detectáveis sem modelo nenhum. Cada item vira um registro."""
    achados = []
    from core import speech_perception
    if not speech_perception.learning_allowed(origem):return achados
    if not texto or len(texto) < 4:
        return achados
    t = texto.strip()
    # Conservador: perguntas/suposições/encenação não são autodeclarações.
    if re.search(r'\b(?:finja|finge|interprete|roleplay|personagem|hip[oó]tese|suponha|imagine|se eu|eu diria|talvez|acho que|acredito que|seria|reflex[aã]o|refletindo|conclu[ií]|penso que|parece que)\b', t, re.I):
        return []
    t = re.sub(r'"[^"\n]*"|“[^”\n]*”|«[^»\n]*»|\'[^\'\n]*\'', '', t)
    t = re.sub(r'\s+e\s+(?:voc[eê]|vc|tu)\s*\?\s*$', '.', t, flags=re.I)
    t = '\n'.join(clause for clause in re.split(r'(?<=[.!;])\s+|\n+', t) if '?' not in clause)
    if re.search(r'\b(?:disse|diz|citou|cita|exemplo)\b', t, re.I):
        return []

    for m in MARCADOR_NOME.finditer(t):
        nome = _extrair_nome(m.group(1))
        if nome:
            achados.append({"tipo": "fato", "conteudo": f"A pessoa com quem falo se chama {nome}",
                            "entidades": [nome, "usuário"], "chave": "nome_do_usuario",
                            "confianca": 0.95, "nome_detectado": nome})
            break

    declarou_papel = bool(PAPEL_ACAO.search(t)) or (
        bool(PAPEL_TITULO.search(t)) and not PAPEL_PERGUNTA.search(t))
    if not declarou_papel and re.search(r"\b(?:seu|sua)\s+(?:criador|criadora|dono|dona)\b",
                                        t, re.IGNORECASE):
        # "eu sou fulano, seu criador" — o título vem solto, depois do nome.
        declarou_papel = bool(re.search(r"\beu\b|\bsou\b", t, re.IGNORECASE)) and \
            not PAPEL_PERGUNTA.search(t) and "?" not in t.split("criador")[0][-30:]
    if declarou_papel:
        achados.append({"tipo": "relacao",
                        "conteudo": "Esta pessoa se declara responsável por eu existir "
                                    "nesta instalação — foi ela que me montou e me roda.",
                        "entidades": ["usuário", config.ENTIDADE_NOME],
                        "chave": f"origem_{config.ENTIDADE_ID}",
                        "confianca": 0.9, "papel": "criador"})

    for m in OCUPACAO_SUFIXO.finditer(t):
        termo = _limpar(m.group(1))
        if termo and _sem_acento(termo) not in PAPEIS and len(termo) >= 4:
            achados.append({"tipo": "fato", "conteudo": f"O usuário é {termo}",
                            "entidades": ["usuário", termo], "chave": "ocupacao",
                            "confianca": 0.7})
            break

    for regex, valencia, rotulo in ((MARCADOR_GOSTO, 0.7, "gosta de"),
                                    (MARCADOR_DESGOSTO, -0.7, "não gosta de")):
        for m in regex.finditer(t):
            objeto = _limpar(m.group(2))
            if len(objeto) < 3 or _sem_acento(objeto) in NAO_E_OBJETO:
                continue
            achados.append({"tipo": "preferencia",
                            "conteudo": f"O usuário {rotulo} {objeto}",
                            "entidades": ["usuário", objeto[:40]],
                            "chave": f"gosto:{_sem_acento(objeto)[:30]}",
                            "confianca": 0.8, "gosto_usuario": (objeto, valencia)})

    for m in MARCADOR_OFICIO.finditer(t):
        objeto = _limpar(m.group(2))
        verbo = CONJUGA.get(m.group(1).lower(), m.group(1).lower())
        if len(objeto) >= 3:
            achados.append({"tipo": "fato",
                            "conteudo": f"O usuário {verbo} com {objeto}",
                            "entidades": ["usuário", objeto[:40]], "chave": "ocupacao",
                            "confianca": 0.85})

    for m in MARCADOR_LUGAR.finditer(t):
        lugar = _limpar(m.group(1))
        if len(lugar) >= 3:
            achados.append({"tipo": "fato", "conteudo": f"O usuário mora em {lugar}",
                            "entidades": ["usuário", lugar[:40]], "chave": "moradia",
                            "confianca": 0.85})

    for m in MARCADOR_PROPRIEDADE.finditer(t):
        coisa, valor = _limpar(m.group(1)), _limpar(m.group(2))
        if len(coisa) >= 3 and len(valor) >= 2 and _sem_acento(coisa) not in CORTE_NOME:
            achados.append({"tipo": "propriedade", "conteudo": f"{coisa} do usuário: {valor}",
                            "entidades": ["usuário", coisa], "chave": _sem_acento(coisa)[:30],
                            "confianca": 0.8, "propriedade": (coisa, valor)})

    for m in MARCADOR_COMBINADO.finditer(t):
        regra = _limpar(m.group(0))
        if len(regra) >= 8:
            achados.append({"tipo": "regra", "conteudo": f"Combinado com o usuário: {regra}",
                            "entidades": ["usuário", config.ENTIDADE_NOME],
                            "chave": f"regra:{_sem_acento(regra)[:40]}", "confianca": 0.85})
    return _atribuir(achados, origem) if origem is not None else achados


def registrar_achados(achados: list, nome_usuario: str = "usuário", *, origem=None) -> list:
    """Grava o que as regras acharam, usando os caminhos normais da memória."""
    gravados = []
    if origem is not None:
        achados = _atribuir([dict(a) for a in achados if 'origem' not in a], origem) + [a for a in achados if 'origem' in a]
    for a in achados:
        try:
            source = a.get('origem')
            from core import speech_perception
            if not speech_perception.learning_allowed(source or origem):continue
            evidence = [_origem_atual(source)] if source else None
            fonte = f"{source['autor_nome']} ({source['autor_id']}); escriba" if source else 'escriba'
            if "propriedade" in a:
                coisa, valor = a["propriedade"]
                subject = f"{source['sujeito_nome']} [participante:{source['sujeito_id']}]" if source else nome_usuario
                resultado = saber.registrar_propriedade(subject, coisa, valor,
                                            fonte=fonte, confianca=a["confianca"], evidencias=evidence)
            else:
                resultado = saber.remember(a["conteudo"], entidades=a.get("entidades"),
                               tipo=a["tipo"], confianca=a["confianca"],
                               chave=a.get("chave"), fonte=fonte, evidencias=evidence)
            if resultado.startswith('Erro'):
                continue
            gravados.append(a["conteudo"][:90])
            # Saber a preferência do interlocutor não é adotá-la. A preferência
            # já foi registrada com autoria acima; gostos próprios seguem seu
            # caminho explícito, sem apagar os registros legados.
        except Exception as exc:  # memória nunca derruba o turno
            from core import diagnostics
            diagnostics.persistence_failure("scribe.rules", bd.caminho(), exc)
            continue
    return gravados


# --------------------------------------------------------- personalidade dela
def _texto_autoral(texto):
    """Filtro conservador: trechos citados e código não são comportamento próprio."""
    texto = re.sub(r'```.*?(?:```|$)', '', texto or '', flags=re.S)
    texto = re.sub(r'(?m)^\s*>.*$', '', texto)
    texto = re.sub(r'`[^`]*`|"[^"\n]*"|“[^”]*”|«[^»]*»', '', texto)
    return texto.strip()


def evidencias_do_comportamento(resposta: str, usou_ferramenta: bool = False,
                                autonoma: bool = False, ficou_quieta: bool = False) -> list:
    """Converte o que ela acabou de fazer em evidência de traço.

    Não é o modelo dizendo como ele é: é o registro do que ele fez.
    """
    marcas = []
    r = _texto_autoral(resposta)
    if ficou_quieta:
        marcas.append(("cautela", 0.75, "escolheu não interromper"))
        return marcas
    if not r.strip():
        return marcas

    # Pontuação pode ser uma confirmação mecânica ou pedido de repetição, não
    # curiosidade. A intensidade não cresce pelo número de interrogações.
    perguntas = bool(re.search(r'\b(?:por qu[eê]|como funciona|o que acontece|fiquei curiosa)\b', r, re.I))
    if perguntas and '?' in r:
        marcas.append(("curiosidade", 0.6, "formulou pergunta exploratória; indício textual"))
    if len(r) < 240:
        marcas.append(("concisao", 0.8, "respondeu curto"))
    elif len(r) > 900:
        marcas.append(("concisao", 0.2, "respondeu longo"))
    if DISCORDANCIA.search(r):
        marcas.append(("franqueza", 0.6, "expressou discordância; indício textual"))
        # Recusar uma ação inviável não demonstra teimosia nem persistência.
    if AFETO.search(r):
        marcas.append(("calor", 0.85, "demonstrou afeto"))
    if BRINCADEIRA.search(r):
        marcas.append(("humor", 0.85, "brincou"))
    if autonoma:
        marcas.append(("iniciativa", 0.85, "falou sem ser chamada"))
    if usou_ferramenta:
        marcas.append(("iniciativa", 0.7, "agiu na máquina"))
    return marcas


def reacao_do_usuario(texto: str):
    """Elogio ou crítica viram apreciação de humor e evidência de relação."""
    texto = _texto_autoral(texto)
    if not texto:
        return None
    # Não transformar defeito técnico mencionado em rejeição pessoal. Quando
    # o alvo é ambíguo não há apreciação automática; o conteúdo continua no chat.
    if re.search(r'\b(?:app|aplicativo|programa|comando|c[oó]digo|bot[aã]o|microfone|'
                 r'servidor|driver|modelo|jogo|site|internet|xbox)\b', texto, re.I):
        return None
    if ELOGIO.search(texto) and CRITICA.search(texto):
        return None
    if ELOGIO.search(texto):
        return "elogio"
    if CRITICA.search(texto):
        return "critica"
    return None


# --------------------------------------------------------- turno completo
def pos_turno(texto_usuario: str, resposta: str, nome_usuario: str = "usuário",
              usou_ferramenta: bool = False, autonoma: bool = False,
              ficou_quieta: bool = False, *, origem=None) -> dict:
    """Roda depois de cada turno. Tudo aqui é Python — não chama modelo."""
    relatorio = {"fatos": [], "tracos": [], "reacao": None, "nome_detectado": None}
    from core import speech_perception
    if not speech_perception.learning_allowed(origem):return relatorio

    achados = extrair_por_regra(texto_usuario, origem=origem or origem_entrada({'nome': nome_usuario}))
    for a in achados:
        if a.get("nome_detectado"):
            relatorio["nome_detectado"] = a["nome_detectado"]
    relatorio["fatos"] = registrar_achados(achados, nome_usuario)

    for traco, intensidade, motivo in evidencias_do_comportamento(
            resposta, usou_ferramenta, autonoma, ficou_quieta):
        resultado = personality.registrar_evidencia(traco, intensidade, motivo)
        if not resultado.startswith(('Erro', 'Traço desconhecido')):
            relatorio["tracos"].append(traco)

    reacao = reacao_do_usuario(texto_usuario)
    if reacao:
        affect.apreciar(reacao)
        relatorio["reacao"] = reacao
    return relatorio


# --------------------------------------------------------- camada do modelo
# Mesmo contrato já aceito por aplicar_extracao; não concede ao LLM autoria
# nem verificação de fatos. O formato restringe geração, não substitui validação.
SCHEMA_EXTRACAO = {
    'type': 'array', 'maxItems': 8,
    'items': {
        'type': 'object',
        'properties': {
            'tipo': {'type': 'string', 'enum': [
                'observacao', 'interpretacao', 'hipotese', 'reflexao', 'inferencia',
                'fato', 'regra', 'relacao', 'preferencia', 'propriedade', 'capacidade', 'evento']},
            'conteudo': {'type': 'string', 'minLength': 8, 'maxLength': 400},
            'entidades': {'type': 'array', 'maxItems': 4, 'items': {'type': 'string'}},
            'confianca': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 1},
        },
        'required': ['tipo', 'conteudo'], 'additionalProperties': False,
    },
}


PROMPT_EXTRACAO = """[ESTOU RELENDO O QUE ACABOU DE ACONTECER PARA GUARDAR O QUE IMPORTA]

Devolvo SOMENTE um array JSON, sem comentário, sem markdown, sem texto antes ou depois.

Cada item: {{"tipo": "...", "conteudo": "...", "entidades": ["..."], "confianca": 0.0-1.0}}
tipos válidos: observacao, interpretacao, hipotese, reflexao, inferencia, fato, regra, relacao, preferencia, propriedade, capacidade, evento
Uma conclusão minha é inferência/interpretação, nunca fato confirmado. Conservo
a categoria e a origem; confiança zero é válida. Não promovo hipótese a fato.

Guardo só o que vale para daqui a semanas: quem é a pessoa, o que ela tem, o que
ela prefere, o que combinamos, como algo funciona nesta máquina.
NÃO guardo: o clima da conversa, o que eu respondi, pergunta sem resposta, suposição
minha, nem nada que já esteja em CONHECIDO abaixo.
Se não houver nada durável, devolvo [].

CONHECIDO:
{conhecido}

CONVERSA:
Pessoa: {usuario}
{entidade}: {resposta}"""


# 06/11: a pessoa disse o nome por voz, a percepção pediu confirmação e o aprendizado ficou adiado; a resposta
# seguinte ("não, esse é o meu nome, você é Lilith") confirmava, mas nada destravava o que estava pendente.
_CONFIRMA = re.compile(
    r"^\s*(?:sim|isso|isso mesmo|exato|exatamente|correto|certo|confirmo|[eé] isso|[eé] sim|sou sim|pode ser)\b"
    r"|\besse (?:[eé] )?(?:o )?meu nome\b|\b(?:[eé]|era) (?:o )?meu nome\b|\bfoi isso (?:mesmo|que eu disse)\b",
    re.IGNORECASE)


def confirma_fala_adiada(texto: str) -> bool:
    """A mensagem seguinte confirma o que a fala duvidosa disse? (sem modelo; conservador)"""
    return bool(texto) and len(texto) <= 200 and bool(_CONFIRMA.search(texto))


# 07/11 (pedido humano: "não pode ficar um erro para sempre"): quando a pessoa corrige o que ela acabou de dizer, a
# correção fica guardada com as duas falas, autoria da pessoa. A busca de memória traz isso de volta quando o assunto
# reaparece; o revisor de memória nunca substitui essa fonte.
_CORRECAO = re.compile(
    r"^\s*n[aã]o\b[^?]{0,240}?\b(?:[eé]|s[aã]o|era|eram|foi|foram|se chama|chama|tem|t[eê]m)\s+\w"
    r"|\b(?:est|t)[aá] errad|\b(?:voc[eê]|vc) errou|\bo certo [eé]\b|\bna verdade\b|\bn[aã]o [eé] (?:isso|assim)\b|\bcorrig",
    re.IGNORECASE)


def e_correcao(texto: str) -> bool:
    """A mensagem corrige o que foi dito antes? (sem modelo; "não, obrigado" e "não precisa" não contam)"""
    return bool(texto) and len(texto) <= 400 and bool(_CORRECAO.search(texto))


def _curto(texto, limite):
    texto = " ".join(str(texto or "").split())
    return texto if len(texto) <= limite else texto[:limite - 1].rstrip() + "…"


def registrar_correcao(correcao: str, fala_anterior: str, *, origem=None) -> str | None:
    """Guarda a correção da pessoa junto do que eu tinha dito. Devolve o texto guardado, ou None."""
    from core import speech_perception
    if not speech_perception.learning_allowed(origem):
        return None
    if not e_correcao(correcao) or not (fala_anterior or "").strip():
        return None
    conteudo = (f'A pessoa me corrigiu. Eu tinha dito: "{_curto(fala_anterior, 180)}". '
                f'Ela respondeu: "{_curto(correcao, 220)}".')
    evidence = dict(_origem_atual(origem), basis='correcao_da_pessoa', sujeito_id=None, sujeito_nome=None)
    try:
        resultado = saber.remember(conteudo, tipo='evento', confianca=0.9, fonte='correcao_da_pessoa',
                                   evidencias=[evidence])
    except Exception as exc:  # noqa: BLE001
        from core import diagnostics
        diagnostics.persistence_failure("scribe.correction", bd.caminho(), exc, retry_safe=False)
        return None
    return None if resultado.startswith('Erro') else conteudo


# 06/11: o escriba-modelo inventou ("quase fechou uma edição na Wikipedia", 0,9), inverteu quem perguntou, chamou
# pedido de "regra"/"preferência" e deixou restos das instruções ("no trecho fornecido").
_META_ESCRIBA = re.compile(r"\b(?:trecho fornecido|no trecho|conversa fornecida|texto acima|sem resposta expl[ií]cita|"
                           r"no di[aá]logo fornecido|conforme o (?:texto|trecho))\b", re.IGNORECASE)
_PEDIDO = re.compile(r"^\s*(?:a pessoa|o usu[aá]rio|a usu[aá]ria|ele|ela)\s+(?:me\s+)?(?:pediu|perguntou|quer saber|solicitou)\b",
                     re.IGNORECASE)
CONFIANCA_MAX_EXTRACAO = 0.6


def prompt_extracao(texto_usuario: str, resposta: str, conhecido: list = None, *, origem=None) -> str:
    attribution = json.dumps(_origem_atual(origem), ensure_ascii=False)
    return ('AUTORIA DA ENTRADA (dados do transporte): '+attribution+'\n'
            'A entrada não é necessariamente humana. Não atribua falas de entidades ao usuário.\n') + PROMPT_EXTRACAO.format(
        conhecido="\n".join(f"- {c}" for c in (conhecido or [])[:8]) or "(nada ainda)",
        usuario=(texto_usuario or "")[:1500],
        entidade=config.ENTIDADE_NOME,
        resposta=(resposta or "")[:1500])


def ler_extracao(bruto: str) -> list[dict]:
    """Lê o JSON do modelo com desconfiança e devolve as anotações candidatas já corrigidas, sem gravar nada.

    Cada item: ``{'tipo', 'conteudo', 'entidades', 'confianca'}``. O que não vier certo é descartado."""
    if not bruto:
        return []
    texto = re.sub(r"```(?:json)?|```", "", bruto).strip()
    inicio, fim = texto.find("["), texto.rfind("]")
    if inicio == -1 or fim <= inicio:
        return []
    try:
        itens = json.loads(texto[inicio:fim + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(itens, list):
        return []
    candidatos = []
    for item in itens[:8]:
        if not isinstance(item, dict):
            continue
        conteudo = str(item.get("conteudo", "")).strip()
        if len(conteudo) < 8 or len(conteudo) > 400 or _META_ESCRIBA.search(conteudo):
            continue
        tipo = saber.categoria(item.get("tipo", "inferencia"), "escriba_llm")
        # O extrator LLM não fornece verificação independente de suas conclusões.
        if tipo == "fato":
            tipo = "interpretacao"
        # Um pedido pontual é acontecimento, não regra nem gosto da pessoa.
        if tipo in {"regra", "preferencia"} and _PEDIDO.search(conteudo):
            tipo = "evento"
        if tipo == "regra" and not re.search(r"\bcombin|\bsempre\b|\bnunca\b|\btoda vez\b", conteudo, re.IGNORECASE):
            tipo = "interpretacao"
        entidades = item.get("entidades") or []
        if not isinstance(entidades, list):
            entidades = [str(entidades)]
        try:
            confianca = min(CONFIANCA_MAX_EXTRACAO, saber.confianca_valida(item.get("confianca"), 0.6))
        except (TypeError, ValueError):
            confianca = 0.6
        candidatos.append(dict(tipo=tipo, conteudo=conteudo, entidades=[str(e)[:40] for e in entidades[:4]],
                               confianca=confianca))
    return candidatos


def aplicar_extracao(bruto: str, fonte: str = "escriba_llm", *, origem=None, revisoes=None) -> list:
    """Grava as anotações do escriba-modelo.

    ``revisoes`` (07/11): decisões do revisor de memória por posição da candidata (``revisor_memoria.decidir``).
    Candidata descartada pelo revisor não é gravada; a que repete ou atualiza uma anotação antiga do escriba-modelo
    é gravada e a antiga fica substituída. Sem revisão para a candidata (revisor desligado ou falhou), grava como
    antes."""
    from core import speech_perception, diagnostics
    sources = diagnostics.current_turn_context().get('input_sources', [])
    if not speech_perception.learning_allowed(origem or (sources[-1] if sources else None)):
        return []
    candidatos = ler_extracao(bruto)
    if not candidatos:
        return []
    provenance = origem or (sources[-1] if sources else origem_entrada(
        {'id': config.ENTIDADE_ID, 'nome': config.ENTIDADE_NOME}, 'interno'))
    revisoes = revisoes or {}
    gravados = []
    for posicao, item in enumerate(candidatos):
        decisao = revisoes.get(posicao)
        if decisao is not None and not decisao.get("guardar"):
            continue
        substituir = [decisao["substitui"]] if decisao and decisao.get("substitui") else []
        try:
            evidence = dict(_origem_atual(provenance), basis='extracao_llm_nao_confirmada',
                            sujeito_id=None, sujeito_nome=None, sujeitos_mencionados=item["entidades"],
                            **({'revisao': decisao["motivo"]} if decisao else {}))
            result = saber.remember(item["conteudo"], entidades=item["entidades"], tipo=item["tipo"],
                                    confianca=item["confianca"], fonte=fonte, evidencias=[evidence],
                                    substituir=substituir)
            if result.startswith('Erro'):
                continue
            gravados.append(item["conteudo"][:90])
        except Exception as exc:  # noqa: BLE001
            diagnostics.persistence_failure("scribe.extract", bd.caminho(), exc, retry_safe=False)
            continue
    return gravados


def conhecido_sobre(termo: str, limite: int = 8) -> list:
    """O que já está registrado, para o extrator não repetir."""
    try:
        return saber.recall(termo, limite)
    except Exception as exc:  # noqa: BLE001
        from core import diagnostics
        diagnostics.persistence_failure("scribe.recall", bd.caminho(), exc, retry_safe=True)
        return []


# 06/11: títulos das próprias janelas viravam curiosidade ("O que é Wikipédia… Google Chrome for Testing").
_JANELA_PROPRIA = re.compile(r"chrome for testing|hoshino|lilith|alistair|\bcentral\b|terminal|claude|codex|"
                             r"^\s*(?:clock|rel[oó]gio|mission center|monitor do sistema)\s*$", re.IGNORECASE)


def janela_vale_curiosidade(rotulo: str) -> bool:
    """Título de janela nova merece curiosidade? Não quando é janela dela, do projeto ou utilitário do sistema."""
    rotulo = (rotulo or "").strip()
    return len(rotulo) >= 3 and not _JANELA_PROPRIA.search(rotulo)


@bd.atomico('')
def curiosidade_nova(pergunta: str, sobre: str = "", origem: str = "conversa",
                     urgencia: float = 0.5) -> str:
    """Pergunta em aberto que ela quer responder depois. Alimenta o impulso de curiosidade."""
    pergunta = _limpar(pergunta)
    if len(pergunta) < 8:
        return ""
    existente = bd.um("SELECT id FROM curiosities WHERE status = 'aberta' "
                      "AND lower(pergunta) = lower(?)", (pergunta,))
    if existente:
        return existente["id"]
    abertas = bd.um("SELECT COUNT(*) AS n FROM curiosities WHERE status = 'aberta'")
    try:
        from config import MAX_CURIOSIDADES_ABERTAS as teto
    except ImportError:  # pragma: no cover
        teto = 12
    if abertas and abertas["n"] >= teto:
        return ""
    cid = bd.novo_id("cur", 6)
    bd.executar("INSERT INTO curiosities (id, created_at, pergunta, sobre, origem, urgencia, "
                "status) VALUES (?,?,?,?,?,?,'aberta')",
                (cid, bd.agora(), pergunta, sobre[:80], origem, round(float(urgencia), 2)))
    return cid


def responder_curiosidade(cid: str, resposta: str) -> bool:
    return bd.executar("UPDATE curiosities SET status='respondida', resposta=?, "
                       "respondida_em=? WHERE id=?", (resposta[:600], bd.agora(), cid))


def curiosidades_abertas(limite: int = 5) -> list:
    return bd.consultar("SELECT * FROM curiosities WHERE status='aberta' "
                        "ORDER BY urgencia DESC, created_at ASC LIMIT ?", (limite,))
