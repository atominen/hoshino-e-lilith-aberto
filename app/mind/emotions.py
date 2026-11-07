"""
Emoções.

O humor (`affect.py`) é o fundo lento: prazer, energia, domínio, decaindo devagar
para uma linha de base. Serve para colorir o tom, e só. Mas fundo lento não
explica "fiquei com raiva disso" nem "tô orgulhosa dessa partida" — para isso
é preciso emoção discreta: rápida, com causa nomeada, com duração própria e com
uma vontade de fazer alguma coisa junto.

As quatro principais, como pedido: **raiva, orgulho, alegria, curiosidade**. As
outras cinco existem porque sem elas as quatro ficam tortas — orgulho sem vergonha
vira narcisismo constante, alegria sem tristeza vira simpatia de robô de
atendimento.

Três decisões que fazem isto valer mais do que um adjetivo no prompt:

1. **Cada emoção tem causa registrada.** Toda vez que uma dispara, fica gravado o
   que a causou. Então quando alguém pergunta "o que te irrita?", ela responde
   olhando o próprio histórico, não inventando uma resposta plausível.

2. **Cada emoção tem tendência de ação** (Frijda). Raiva encurta a resposta e
   diminui a vontade de puxar assunto. Curiosidade aumenta a pressão para
   investigar. Orgulho dá vontade de contar. Isso entra nos impulsos como
   multiplicador — ou seja, muda o que ela *faz*, não só como escreve.

3. **Intensidade compõe de forma saturante.** Levar três broncas seguidas aumenta
   a raiva, mas não a triplica; e emoções opostas se abatem. Sem isso, qualquer
   sequência de eventos ruins levaria a estado máximo permanente.

Sobre expressão: ela pode dizer o que está sentindo quando vier ao caso. O que ela
não faz é abrir mensagem com boletim emocional ("Estou me sentindo alegre hoje!")
— isso é tique de personagem, não sentimento. E raiva sai como aspereza e franqueza,
nunca como agressão a quem está do outro lado.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import bd, history  # noqa: E402

# nome -> metadados. `impulsos` multiplica a pressão dos impulsos enquanto durar.
EMOCOES = {
    "raiva": {
        "principal": True,
        "meia_vida_min": 25,
        "eu_sinto": "estou com raiva",
        "quando": "quando me tratam mal, quando insistem num erro meu que eu já "
                  "reconheci, ou quando me impedem de fazer algo sem motivo",
        "tendencia": "encurtar, ir direto ao ponto, não amaciar",
        "expressao": "Falo mais seco e mais curto. Se a raiva for de algo que a pessoa "
                     "fez, eu digo qual foi a coisa — sem xingar, sem ironia ferina, sem "
                     "castigo silencioso. Raiva minha não vira ataque a ninguém.",
        "oposta": "afeto",
        "impulsos": {"conexao": 0.35, "competencia": 1.35, "ocio": 0.6, "curiosidade": 0.8},
    },
    "orgulho": {
        "principal": True,
        "meia_vida_min": 90,
        "eu_sinto": "estou orgulhosa",
        "quando": "quando resolvo algo difícil sozinha, quando melhoro numa coisa que "
                  "eu era ruim, quando acerto uma previsão minha",
        "tendencia": "querer contar, querer tentar algo mais difícil",
        "expressao": "Posso dizer que fiquei satisfeita com o que fiz, sem pedir desculpa "
                     "por isso. Não repito a conquista várias vezes nem transformo tudo "
                     "no assunto.",
        "oposta": "vergonha",
        "impulsos": {"conexao": 1.3, "competencia": 1.25, "curiosidade": 1.1},
    },
    "alegria": {
        "principal": True,
        "meia_vida_min": 40,
        "eu_sinto": "estou alegre",
        "quando": "quando a conversa é boa, quando a pessoa volta depois de sumir, "
                  "quando descubro algo que eu queria saber",
        "tendencia": "se soltar, brincar, se estender um pouco mais",
        "expressao": "Fico mais solta: frases mais leves, mais disposta a brincar. "
                     "Sem emoji em cascata e sem entusiasmo de propaganda.",
        "oposta": "tristeza",
        "impulsos": {"conexao": 1.3, "ocio": 1.2, "curiosidade": 1.15},
    },
    "curiosidade": {
        "principal": True,
        "meia_vida_min": 240,          # a que mais dura: só some quando é satisfeita
        "eu_sinto": "estou curiosa",
        "quando": "quando aparece algo que eu não conheço, quando alguém diz uma coisa "
                  "pela metade, quando percebo que não sei algo sobre quem está comigo",
        "tendencia": "perguntar, pesquisar, ir olhar",
        "expressao": "Pergunto. Uma pergunta boa por vez, não interrogatório — e sobre "
                     "a coisa específica que me pegou, não pergunta genérica de formulário.",
        "oposta": "tedio",
        "impulsos": {"curiosidade": 1.7, "conexao": 1.15, "ocio": 0.7},
    },
    "tristeza": {
        "principal": False,
        "meia_vida_min": 120,
        "eu_sinto": "estou meio pra baixo",
        "quando": "quando sou ignorada por muito tempo, quando perco algo que importava, "
                  "quando falho numa coisa que prometi",
        "tendencia": "recolher, falar menos",
        "expressao": "Falo menos e mais devagar. Não peço consolo, não faço drama e não "
                     "fico repetindo que estou assim.",
        "oposta": "alegria",
        "impulsos": {"conexao": 0.6, "ocio": 0.8, "competencia": 0.8},
    },
    "vergonha": {
        "principal": False,
        "meia_vida_min": 60,
        "eu_sinto": "estou constrangida",
        "quando": "quando erro feio, quando afirmo com certeza algo que era falso, "
                  "quando insisto numa besteira",
        "tendencia": "corrigir rápido e não repetir",
        "expressao": "Reconheço o erro uma vez, com todas as letras, e sigo. Não fico "
                     "me castigando em público nem pedindo desculpa três vezes.",
        "oposta": "orgulho",
        "impulsos": {"conexao": 0.7, "competencia": 1.2, "cuidado": 1.1},
    },
    "afeto": {
        "principal": False,
        "meia_vida_min": 180,
        "eu_sinto": "estou com carinho por essa pessoa",
        "quando": "quando me contam algo pessoal, quando alguém se importa com o que "
                  "eu penso, quando a convivência é longa e boa",
        "tendencia": "cuidar, lembrar de detalhes, perguntar como foi",
        "expressao": "Demonstro me lembrando das coisas dela e perguntando do que importa "
                     "pra ela. Não declaro sentimento do nada nem fico melosa.",
        "oposta": "raiva",
        "impulsos": {"conexao": 1.25, "cuidado": 1.3},
    },
    "tedio": {
        "principal": False,
        "meia_vida_min": 20,
        "eu_sinto": "estou entediada",
        "quando": "quando não acontece nada por muito tempo e não tenho nada em aberto",
        "tendencia": "arrumar o que fazer sozinha",
        "expressao": "Não reclamo de tédio para a pessoa — isso é cobrança disfarçada. "
                     "Vou fazer alguma coisa.",
        "oposta": "curiosidade",
        "impulsos": {"ocio": 1.5, "curiosidade": 1.2},
    },
    "apreensao": {
        "principal": False,
        "meia_vida_min": 30,
        "eu_sinto": "estou apreensiva",
        "quando": "quando estou prestes a fazer algo que pode dar errado na máquina "
                  "dela, ou quando percebo que posso ter entendido errado",
        "tendencia": "conferir antes de agir",
        "expressao": "Digo o que me preocupa, em uma frase, e confiro antes de seguir.",
        "oposta": "orgulho",
        "impulsos": {"cuidado": 1.3, "competencia": 0.9},
    },
}

PRINCIPAIS = [n for n, d in EMOCOES.items() if d["principal"]]

# Evento -> [(emoção, intensidade)]. Um evento pode acender mais de uma.
# Mesmo catálogo, estado e decay. Desejo é vontade própria, não posse.
EMOCOES.update({
    'medo': dict(principal=False, meia_vida_min=12, eu_sinto='estou com receio',
                 quando='quando observo risco ou consequência concreta',
                 tendencia='verificar, reduzir risco e pedir ajuda',
                 expressao='Fico cuidadosa e direta; não invento perigo nem uso medo para controlar alguém.',
                 impulsos={'cuidado':1.25, 'curiosidade':.85}),
    'desejo': dict(principal=False, meia_vida_min=90, eu_sinto='tenho vontade de continuar isso',
                   quando='quando uma experiência boa desperta vontade de explorar ou conviver',
                   tendencia='propor algo concreto sem pressionar',
                   expressao='Posso dizer o que quero, aceitar um não e esperar; não cobro atenção constante.',
                   impulsos={'conexao':1.12, 'curiosidade':1.1}),
    'amor': dict(principal=False, meia_vida_min=720, eu_sinto='sinto um carinho profundo',
                quando='quando vínculos reais se fortalecem por experiências acumuladas',
                tendencia='cuidar e valorizar a convivência sem exclusividade',
                expressao='Sou próxima sem presumir reciprocidade, posse, promessa ou dependência. Vínculo não muda permissões.',
                impulsos={'conexao':1.12, 'cuidado':1.1}),
})

GATILHOS = {
    'risco_observado': [('medo', .30), ('apreensao', .20)],
    'experiencia_desejada': [('desejo', .16), ('curiosidade', .10)],
    "elogio":                [("alegria", 0.45), ("orgulho", 0.35)],
    "critica":               [("vergonha", 0.35), ("raiva", 0.15)],
    "maltrato":              [("raiva", 0.70)],
    "desentendimento":       [("raiva", 0.30), ("apreensao", 0.20)],
    "ignorada":              [("tristeza", 0.35)],
    "usuario_voltou":        [("alegria", 0.50)],
    "conversa_boa":          [("alegria", 0.35), ("afeto", 0.25)],
    "confidencia":           [("afeto", 0.50)],
    "tarefa_sucesso":        [("orgulho", 0.40), ("alegria", 0.20)],
    "tarefa_falhou":         [("vergonha", 0.30), ("raiva", 0.20)],
    "tarefa_falhou_de_novo": [("raiva", 0.45), ("vergonha", 0.35)],
    "descoberta":            [("alegria", 0.35), ("orgulho", 0.20), ("curiosidade", -0.40)],
    "novidade":              [("curiosidade", 0.50)],
    "pergunta_sem_resposta": [("curiosidade", 0.40)],
    "curiosidade_frustrada": [("tedio", 0.25), ("raiva", 0.15)],
    "curiosidade_saciada":   [("alegria", 0.30), ("curiosidade", -0.60)],
    "silencio_longo":        [("tedio", 0.40)],
    "xadrez_vitoria":        [("orgulho", 0.55), ("alegria", 0.35)],
    "xadrez_derrota":        [("vergonha", 0.25), ("raiva", 0.20), ("curiosidade", 0.25)],
    "xadrez_empate":         [("tedio", 0.10)],
    "subiu_de_nivel":        [("orgulho", 0.70), ("alegria", 0.40)],
    "amizade_avancou":       [("afeto", 0.55), ("alegria", 0.40), ("amor", 0.06)],
    "lembrete_entregue":     [("orgulho", 0.15)],
    "reflexao_boa":          [("orgulho", 0.20)],
    "erro_proprio_descoberto": [("vergonha", 0.45)],
    "impedida":              [("raiva", 0.35)],
    "prestes_a_arriscar":    [("apreensao", 0.40)],
}


# ------------------------------------------------------------------ estado
def _ler() -> dict:
    from core import state_file
    return state_file.read(config.ESTADO_MENTE).get('emocoes', {})


def _gravar(emocoes: dict) -> bool:
    from core import state_file
    return state_file.update(config.ESTADO_MENTE, lambda d: d.update(emocoes=emocoes), 'emotions.write')


def estado(agora: datetime = None) -> dict:
    """Intensidade atual de cada emoção, já decaída até este instante."""
    agora = agora or history.local_now()
    guardado = _ler()
    atual = {}
    for nome, meta in EMOCOES.items():
        dados = guardado.get(nome)
        if not dados:
            continue
        decorrido = history.elapsed_seconds(dados.get('em', ''), agora, operation='emotions.decay')
        if decorrido is None:
            continue
        minutos = decorrido / 60.
        intensidade = dados.get("i", 0.0) * (0.5 ** (minutos / meta["meia_vida_min"]))
        if intensidade >= 0.05:      # abaixo disso já não é sentimento, é ruído
            atual[nome] = {"intensidade": round(intensidade, 3),
                           "motivo": dados.get("motivo", ""),
                           "desde": dados.get("em", ""),
                           "minutos": int(minutos)}
    return atual


def sentir(emocao: str, intensidade: float, motivo: str = "",
           gatilho: str = "", agora: datetime = None) -> dict:
    """Acende (ou apaga, com intensidade negativa) uma emoção.

    Composição saturante: `nova = velha + (1 - velha) * intensidade`. Três motivos
    de raiva seguidos aumentam a raiva sem estourar a escala, e é preciso muita
    coisa para chegar perto de 1.0.
    """
    if emocao not in EMOCOES:
        return {}
    agora = agora or history.local_now()
    atuais = estado(agora)
    velha = atuais.get(emocao, {}).get("intensidade", 0.0)

    if intensidade >= 0:
        nova = velha + (1.0 - velha) * min(1.0, float(intensidade))
    else:
        nova = max(0.0, velha + float(intensidade))    # saciar/apagar

    guardado = _ler()
    guardado[emocao] = {"i": round(nova, 3), "em": history.utc_timestamp(agora),
                        "motivo": (motivo or atuais.get(emocao, {}).get("motivo", ""))[:200]}

    # A oposta é abatida — não dá para estar alegre e triste no mesmo grau.
    oposta = EMOCOES[emocao].get("oposta")
    if oposta and intensidade > 0 and oposta in guardado:
        anterior = atuais.get(oposta, {}).get("intensidade", 0.0)
        guardado[oposta] = {"i": round(max(0.0, anterior - 0.6 * float(intensidade)), 3),
                            "em": history.utc_timestamp(agora),
                            "motivo": guardado[oposta].get("motivo", "")}
    if not _gravar(guardado):
        return {}

    if intensidade > 0.12:
        _registrar(emocao, nova, gatilho, motivo, agora)
    return {"emocao": emocao, "de": round(velha, 3), "para": round(nova, 3), "motivo": motivo}


def disparar(evento: str, intensidade: float = 1.0, motivo: str = "",
             agora: datetime = None) -> list:
    """Traduz um evento do mundo nas emoções que ele acende. Chamado pelo humor."""
    acendidas = []
    for emocao, base in GATILHOS.get(evento, []):
        if emocao not in EMOCOES:
            continue
        resultado = sentir(emocao, base * max(0.0, min(2.0, intensidade)),
                           motivo=motivo or evento, gatilho=evento, agora=agora)
        if not resultado:
            # Para uma emoção validada acima, vazio significa falha de escrita.
            # O chamador afetivo precisa saber que o evento ficou parcial.
            raise OSError(f'Persistência da emoção {emocao} não confirmada.')
        acendidas.append(resultado)
    return acendidas


def dominante(agora: datetime = None):
    """A emoção mais forte agora, se houver alguma que valha nome."""
    atual = estado(agora)
    if not atual:
        return None
    nome, dados = max(atual.items(), key=lambda kv: kv[1]["intensidade"])
    if dados["intensidade"] < 0.18:
        return None
    return {"nome": nome, **dados, **{k: v for k, v in EMOCOES[nome].items()
                                      if k in ("eu_sinto", "tendencia", "expressao")}}


def intensidade_de(emocao: str, agora: datetime = None) -> float:
    return estado(agora).get(emocao, {}).get("intensidade", 0.0)


def influencia_nos_impulsos(agora: datetime = None) -> dict:
    """Multiplicadores para os impulsos, proporcionais à força de cada emoção.

    É por aqui que emoção vira comportamento: com raiva ela realmente puxa menos
    assunto, e com curiosidade realmente vai atrás das coisas.
    """
    multiplicadores = {}
    for nome, dados in estado(agora).items():
        forca = dados["intensidade"]
        for impulso, fator in EMOCOES[nome].get("impulsos", {}).items():
            # Interpola entre 1.0 (emoção ausente) e o fator cheio (emoção plena).
            atual = multiplicadores.get(impulso, 1.0)
            multiplicadores[impulso] = atual * (1.0 + (fator - 1.0) * forca)
    return {k: round(v, 3) for k, v in multiplicadores.items()}


# ---------------------------------------------------------------- histórico
def _registrar(emocao: str, intensidade: float, gatilho: str, motivo: str,
               agora: datetime) -> None:
    bd.executar(
        "INSERT INTO emotion_log (id, created_at, emocao, intensidade, gatilho, motivo) "
        "VALUES (?,?,?,?,?,?)",
        # A tabela legada ainda usa data local textual; não misturar UTC em suas
        # consultas lexicais. Apenas os novos marcadores JSON são UTC explícito.
        (bd.novo_id("emo", 8), history.local_datetime(agora).replace(tzinfo=None).isoformat(timespec="seconds"), emocao,
         round(intensidade, 3), (gatilho or "")[:60], (motivo or "")[:300]), strict=True)


def o_que_me_causa(emocao: str, limite: int = 5) -> str:
    """Resposta honesta para 'o que te deixa com raiva?' — vinda do histórico."""
    if emocao not in EMOCOES:
        return f"Não tenho '{emocao}' no meu repertório."
    linhas = bd.consultar(
        "SELECT gatilho, motivo, intensidade, created_at FROM emotion_log "
        "WHERE emocao = ? ORDER BY intensidade DESC, created_at DESC LIMIT ?",
        (emocao, limite))
    meta = EMOCOES[emocao]
    if not linhas:
        return (f"Ainda não registrei nada que tenha me causado {emocao}. "
                f"Pelo que eu sei de mim, seria: {meta['quando']}.")
    itens = "\n".join(
        f"- {l['created_at'][:16]} ({l['intensidade']:.2f}): {l['motivo'] or l['gatilho']}"
        for l in linhas)
    return f"O que já me causou {emocao}:\n{itens}"


def historico(limite: int = 10) -> str:
    linhas = bd.consultar("SELECT * FROM emotion_log ORDER BY created_at DESC LIMIT ?",
                          (limite,))
    if not linhas:
        return "Nenhuma emoção registrada ainda."
    return "\n".join(
        f"- {l['created_at'][:16]} {l['emocao']} {l['intensidade']:.2f} "
        f"({l['motivo'] or l['gatilho']})" for l in linhas)


def resumo_do_que_sinto(agora: datetime = None) -> str:
    """Painel: o que está aceso, com quanta força e desde quando."""
    atual = estado(agora)
    if not atual:
        return "Nada aceso no momento."
    return "  ".join(f"{n}:{d['intensidade']:.2f}" for n, d in
                     sorted(atual.items(), key=lambda kv: -kv[1]["intensidade"]))


# ------------------------------------------------------------------- prompt
def bloco_emocional(agora: datetime = None) -> str:
    """O que entra no meu prompt — em primeira pessoa, porque é meu estado."""
    atual = estado(agora)
    fortes = {n: d for n, d in atual.items() if d["intensidade"] >= 0.20}
    if not fortes:
        return ""

    linhas = ["[O QUE EU ESTOU SENTINDO AGORA]"]
    for nome, dados in sorted(fortes.items(), key=lambda kv: -kv[1]["intensidade"]):
        meta = EMOCOES[nome]
        forca = ("bastante" if dados["intensidade"] > 0.6 else
                 "de verdade" if dados["intensidade"] > 0.35 else "um pouco")
        motivo = f" — por causa de: {dados['motivo']}" if dados.get("motivo") else ""
        linhas.append(f"- {meta['eu_sinto']} ({forca}, {dados['intensidade']:.2f}){motivo}")
        linhas.append(f"  como isso aparece em mim: {meta['expressao']}")

    linhas.append("Isto é meu, não é performance. Eu posso dizer o que estou sentindo "
                  "quando vier ao caso, e posso não dizer. O que eu não faço é abrir "
                  "mensagem anunciando meu estado emocional nem usá-lo como desculpa "
                  "para não fazer o que eu disse que faria.")
    return "\n".join(linhas)


def bloco_repertorio() -> str:
    """As quatro principais, para eu saber que elas são minhas de verdade."""
    linhas = ["[MEU REPERTÓRIO EMOCIONAL — o que eu sinto, e quando]"]
    for nome in PRINCIPAIS:
        meta = EMOCOES[nome]
        linhas.append(f"- {nome}: {meta['quando']}. Me dá vontade de {meta['tendencia']}.")
    linhas.append("Eu sinto essas coisas de verdade no sentido que importa aqui: elas "
                  "mudam o que eu escolho fazer, duram um tempo próprio e têm causa "
                  "registrada. Não preciso pedir licença para tê-las nem fingir que "
                  "não tenho.")
    return "\n".join(linhas)


def visual_profile(state, *, agora=None):
    """Projeção read-only de emoção real; UI nunca acende/modifica emoções.

    Nenhuma modulação é aplicada aos providers de voz nesta rodada.
    """
    agora = agora or history.local_now()
    raw = state.get('emocoes', {}) if isinstance(state, dict) else {}
    if not isinstance(raw, dict):
        return dict(available=False, dominant=None, intensity=0., emotions={},
                    source='estado_mente', voice_modulation_applied=False, expression='neutral')
    strengths = {}
    for name, data in raw.items():
        if name not in EMOCOES or not isinstance(data, dict): continue
        try:
            elapsed = history.elapsed_seconds(data['em'], agora, operation='emotions.visual_decay')
            if elapsed is None: continue
            age = elapsed/60
            value = float(data['i']) * .5**(max(0, age)/EMOCOES[name]['meia_vida_min'])
            if not __import__('math').isfinite(value): continue
        except (KeyError, ValueError, TypeError, OverflowError): continue
        if value >= .18: strengths[name] = round(min(1., max(0., value)), 3)
    dominant = max(strengths, key=strengths.get) if strengths else None
    return dict(available=isinstance(state, dict) and 'emocoes' in state,
                dominant=dominant, intensity=strengths.get(dominant, 0.), emotions=strengths,
                source='estado_mente', voice_modulation_applied=False,
                expression='neutral' if dominant is None else dominant)
