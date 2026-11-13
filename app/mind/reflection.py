"""
Reflexão — como ela aprende sem ninguém ensinar.

Ideia dos Generative Agents (Park et al., 2023): guardar episódios não é aprender.
O agente que só acumula observações fica com um diário e nenhuma conclusão. De
tempos em tempos ele precisa parar, olhar o que viveu e escrever o que *conclui*
disso — essas conclusões voltam como reflexões, nunca como fatos confirmados.

Aqui o ciclo dispara por dois contadores (episódios desde a última reflexão e
tempo decorrido), roda como ação interna — ela não fala com ninguém para refletir —
e o resultado vira:

  * linhas em `reflections` (o pensamento, com os episódios que o geraram);
  * conhecimento em `memories`, para aparecer no recall depois;
  * evidência de introspecção, que com o tempo muda o traço dela.
"""
import os
import json
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import bd, history  # noqa: E402
from memory import knowledge_store as saber  # noqa: E402


def _ultima_reflexao():
    # Uma reflexão sem horário não é prova de que a última ocorreu antes da
    # conhecida. Não esconder a ambiguidade escolhendo simplesmente a válida.
    return bd.um('SELECT created_at FROM reflections '
                 "WHERE tipo='reflexao' OR tipo IS NULL "
                 'ORDER BY project_epoch(created_at) IS NULL DESC, '
                 'project_epoch(created_at) DESC, rowid DESC LIMIT 1', strict=True)


def _limites_episodios():
    ultima = _ultima_reflexao()
    corte = history.timestamp_epoch(ultima['created_at']) if ultima else None
    if ultima and corte is None:
        history._clock_warning('reflection.episodes', 'invalid_last_reflection')
        return None
    return corte, history.timestamp_epoch(history.local_now())


def episodios_desde_ultima() -> int:
    limites = _limites_episodios()
    if limites is None:
        return 0
    corte, agora = limites
    linha = bd.um('SELECT SUM(CASE WHEN project_epoch(created_at) <= ? '
                  'AND (? IS NULL OR project_epoch(created_at) > ?) THEN 1 ELSE 0 END) AS n, '
                  'SUM(CASE WHEN project_epoch(created_at) IS NULL THEN 1 ELSE 0 END) AS invalidos '
                  "FROM episodes WHERE source NOT IN ('initiative_checkpoint','initiative_observation','tool_receipt') OR source IS NULL",
                  (agora, corte, corte), strict=True)
    if linha and linha['invalidos']:
        history._clock_warning('reflection.episodes', 'invalid_episode_time')
    return (linha['n'] or 0) if linha else 0


def minutos_desde_ultima() -> float:
    ultima = _ultima_reflexao()
    if not ultima:
        return 1e6
    segundos = history.elapsed_seconds(ultima['created_at'], history.local_now(),
                                       operation='reflection.cooldown')
    return segundos / 60.0 if segundos is not None else 0.0


def precisa_refletir() -> bool:
    return (episodios_desde_ultima() >= config.REFLEXAO_A_CADA_EPISODIOS
            and minutos_desde_ultima() >= config.REFLEXAO_INTERVALO_MIN)


def material(limite: int = 15) -> list:
    """Os episódios que ainda não viraram conclusão."""
    limites = _limites_episodios()
    if limites is None:
        return []
    corte, agora = limites
    return bd.consultar(
        "SELECT id, created_at, what_happened, action_taken, result, source, context FROM episodes WHERE status='active' "
        # 07/11: o recibo mecânico de ferramenta ("Registro automático de ação… Não há confirmação independente") virava
        # "conclusão" minha sobre recibos: texto do sistema, não experiência.
        "AND (source NOT IN ('initiative_checkpoint','initiative_observation','tool_receipt') OR source IS NULL) "
        "AND project_epoch(created_at) <= ? AND (? IS NULL OR project_epoch(created_at) > ?) "
        "ORDER BY project_epoch(created_at) DESC, id LIMIT ?", (agora, corte, corte, limite), strict=True)


PROMPT = """[ESTOU REFLETINDO SOBRE MIM, SEM ENVIAR MENSAGEM A OUTRA PESSOA.]

As conclusões reutilizáveis entram na minha memória semântica, não no diário
privado. Uma nota que quero reservar usa DIARIO; só compartilho se eu escolher.

Coisas que aconteceram comigo ultimamente:

{episodios}

Olhando o conjunto, eu escrevo de 1 a 3 conclusões minhas. Não é resumo: é o que
eu *concluo*, e que muda como eu vou agir daqui em diante.

Conclusão boa é específica e utilizável: "ele pede as coisas de madrugada e detesta
explicação longa nessa hora" serve. "Tivemos interações produtivas" não serve —
isso não muda nada em mim.

Também vale concluir sobre mim mesma: o que eu fiz bem, onde errei, o que quero
tentar diferente da próxima vez.

Se eu quiser reservar uma reflexão no meu diário, posso acrescentar uma linha
DIARIO: seguida de uma nota pessoal curta. É opcional; não é para transcrever
meu raciocínio interno nem compartilhar automaticamente. Posso não escrever.
Se uma experiência sustentar uma lição aplicável, posso acrescentar LICAO_JSON:
{{"episodios":["id real"],"interpretacao":"...","condicao":"quando vale",
"licao":"o que tentarei","excecoes":["quando não vale"]}}. É interpretação,
não fato novo; uso somente IDs fornecidos e posso não extrair lição alguma.

Formato: uma conclusão por linha, começando com "- ". Sem título, sem introdução,
sem comentário no fim. Se realmente não houver nada a concluir, escreva apenas: NADA"""


def prompt_reflexao(episodios: list = None) -> str:
    episodios = episodios if episodios is not None else material()
    if not episodios:
        return ""
    # 07/11: a nota fixa do sistema no resultado também virava lição; o que conta é o que aconteceu.
    limpos = [{k: v for k, v in dict(e).items()
               if not (k == 'result' and str(v).startswith('resposta registrada; efeitos das ferramentas'))}
              for e in episodios]
    linhas = [json.dumps(e,ensure_ascii=False) for e in limpos]
    return PROMPT.format(episodios="\n".join(linhas))


def aplicar(bruto: str, episodios: list = None) -> list:
    """Grava as conclusões. Devolve as que entraram."""
    if not bruto or re.fullmatch(r"\s*NADA[.!]?\s*", bruto, re.IGNORECASE):
        return []
    episodios = episodios or []
    ids = ",".join(e["id"] for e in episodios[:15])
    guardadas = []
    for linha in bruto.splitlines():
        if linha.strip().startswith('LICAO_JSON:'):
            from memory import cognitive_notes
            from core import diagnostics
            try:
                lesson=json.loads(linha.strip()[11:].strip())
                if not isinstance(lesson,dict) or set(lesson)-{'episodios','interpretacao','condicao','licao','excecoes'}:
                    raise ValueError('Formato de lição inválido.')
                if not set(lesson['episodios']).issubset({e['id'] for e in episodios}):
                    raise ValueError('Lição referiu episódio não apresentado.')
                cognitive_notes.learn_experience(lesson['episodios'],lesson['interpretacao'],
                    lesson['condicao'],lesson['licao'],lesson.get('excecoes'))
            except (ValueError,KeyError,TypeError,PermissionError) as exc:
                diagnostics.emit('experience.invalid_lesson',entity=config.ENTIDADE_ID,error=type(exc).__name__)
            continue
        if linha.strip().startswith('DIARIO:'):
            from memory import cognitive_notes
            texto=linha.strip()[7:].strip()
            if texto:
                cognitive_notes.diary_write('Reflexão voluntária',texto,
                                            [dict(table='episodes',id=e['id']) for e in episodios[:15]])
            continue
        if len(guardadas)>=3:continue
        texto = re.sub(r"^\s*[-*•]\s*", "", linha).strip()
        if len(texto) < 15 or len(texto) > 400:
            continue
        if re.match(r"^(conclus|reflex|resumo|episódi)", texto, re.IGNORECASE):
            continue
        rid = bd.novo_id("refl", 6)
        try:
            # Os dois registros existem juntos ou nenhum existe. Índice vetorial
            # é opcional; a recuperação SQLite já inclui estas reflexões.
            with bd.conexao(escrita=True) as conn:
                conn.execute(
                    "INSERT INTO reflections (id, created_at, tema, conteudo, evidencias, tipo, "
                    "importancia, status) VALUES (?,?,?,?,?,'reflexao',0.7,'active')",
                    (rid, history.utc_timestamp(), texto[:60], texto, ids))
                saber.remember(texto, entidades=[config.ENTIDADE_NOME, "usuário"], tipo="reflexao",
                               confianca=0.6, fonte="reflexao", evidencias=[e['id'] for e in episodios[:15]],
                               conexao=conn)
        except Exception as exc:  # memória não derruba o turno nem conta sucesso
            from core import diagnostics
            diagnostics.persistence_failure("reflection.apply", bd.caminho(), exc, retry_safe=False)
            continue
        guardadas.append(texto)
        if len(guardadas) >= 3:
            continue
    return guardadas


def _registro_recuperado(r):
    """Referência compacta ao contexto noturno, sem reintroduzir todo o dia.

    O envelope integral continua no registro original/inspector. Oito fontes
    são uma prévia explícita, não a alegação de que toda evidência foi exibida.
    Strings e JSON legados conservam o contrato anterior.
    """
    links = r['evidencias']
    try:
        envelope = json.loads(links)
    except (ValueError, TypeError):
        envelope = None
    if isinstance(envelope, dict) and envelope.get('kind') == 'night_reflection_context':
        sources = envelope.get('sources')
        if isinstance(sources, list) and all(isinstance(s, dict) for s in sources):
            preview = []
            for source in sources[:8]:
                ref = {k: source[k] for k in ('table', 'id', 'file', 'line', 'timestamp', 'type', 'confidence') if k in source}
                context = source.get('context')
                author = context.get('autoria') if isinstance(context, dict) else None
                if isinstance(author, dict):
                    ref['autoria'] = {k: author[k] for k in ('autor_id', 'autor_nome', 'message_id', 'turn_id', 'canal') if k in author}
                preview.append(ref)
            links = {k: envelope[k] for k in ('kind', 'entity', 'day', 'as_of', 'scope', 'material_sha256', 'limits', 'reason') if k in envelope}
            links.update(sources_preview=preview, sources_count=len(sources), sources_omitted=max(0, len(sources)-8),
                         full_evidence_ref=dict(table='reflections', id=r['id']))
    return saber.registro(dict(id=r['id'], type='reflexao', content=r['conteudo'], confidence=None,
                               source='reflections', created_at=r['created_at'], links=links))


def ultimas(limite: int = 3) -> list:
    return [saber.formatar_registro(_registro_recuperado(r)) for r in bd.consultar(
        "SELECT id, conteudo, created_at, evidencias FROM reflections WHERE status='active' AND (tipo='reflexao' OR tipo IS NULL) "
        "ORDER BY project_epoch(created_at) DESC, id LIMIT ?", (limite,))]


def bloco_para_prompt(limite: int = 3) -> str:
    linhas = bd.consultar("SELECT id, tipo, conteudo, evidencias, created_at FROM reflections "
                          "WHERE status='active' AND (tipo='reflexao' OR tipo IS NULL) ORDER BY project_epoch(created_at) DESC, id LIMIT ?", (limite,))
    if not linhas:
        return ""
    return "[REFLEXÕES PRÓPRIAS — NÃO SÃO FATOS CONFIRMADOS]\n" + \
           "\n".join('- ' + saber.formatar_registro(_registro_recuperado(l)) for l in linhas)
