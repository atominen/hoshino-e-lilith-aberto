"""
Memória de conhecimento — v2.

Três problemas da versão anterior:

1. **Bug de substituição.** `remember()` marcava como 'superseded' QUALQUER
   conhecimento ativo do mesmo tipo que mencionasse a mesma entidade. Ou seja:
   registrar "Gustavo prefere respostas diretas" e depois "Gustavo usa Linux
   Mint" apagava o primeiro. A memória se autodestruía conforme aprendia.
   Agora só substitui o mesmo atributo identificado por chave explícita.
   Semelhança textual não prova conflito: coisas compatíveis convivem.

2. **Só guardava frases.** Existia um único formato: uma frase solta com tipo.
   Não havia como guardar *propriedade* ("a placa tem 8GB de VRAM", "o PC roda
   Linux Mint") nem *como as coisas funcionam* ("para reiniciar o Ollama, use
   systemctl restart ollama; o serviço do sistema ignora OLLAMA_MODELS").
   Agora existem as duas coisas, em tabelas próprias e consultáveis.

3. **Recuperação só por distância vetorial.** Trazia os 2 mais "parecidos" sem
   considerar recência, confiança ou uso, e não marcava acesso. Agora a
   recuperação é híbrida e alimenta os contadores de uso.
"""
import json
import math
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime

from memory.vector import chroma_store as vetor

from config import DB_PATH, PESOS_RECALL
from core.history import elapsed_seconds

from memory.records import TIPOS_VALIDOS, confianca_valida, categoria, registro, card_priorities
from memory import audience
PALAVRAS_VAZIAS = {"de", "da", "do", "das", "dos", "para", "por", "com", "que", "uma",
                   "um", "no", "na", "nos", "nas", "ao", "aos", "em", "e", "o", "a",
                   "os", "as", "ele", "ela", "isso", "sobre", "como", "mais", "muito"}


def _conn(escrita=False):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA busy_timeout=5000")
        if escrita:
            conn.execute('BEGIN IMMEDIATE')
        return conn
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.connect', DB_PATH, exc)
        raise


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _tokens(texto: str) -> set:
    return {p for p in re.findall(r"\w+", _normalizar(texto))
            if len(p) > 2 and p not in PALAVRAS_VAZIAS}


def _semelhanca(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _entidades_lista(entidades):
    if entidades is None:
        return []
    if isinstance(entidades, str):
        return [entidades.strip()] if entidades.strip() else []
    return [str(e).strip() for e in entidades if str(e).strip()]


def formatar_registro(r):
    """Não confundir categoria/confiabilidade com confirmação externa de um fato."""
    refs = r.get('evidencias', [])
    if isinstance(refs,dict) and refs.get('kind')=='conceptual_model':
        refs=dict(refs,sources=[{k:v for k,v in source.items() if k!='context'} |
            {'authorship':_source_authorship(source.get('context'))} for source in refs.get('sources',[])])
    evidencias = json.dumps(refs, ensure_ascii=False)
    legado = (f"; tipo armazenado={r['tipo_armazenado']}" if
              r.get("tipo_armazenado") != r["tipo"] else "")
    ausencia = "; confiança ausente no legado, usando default" if r.get("confianca_armazenada") is None else ""
    return (f"[{r['tipo']}] {r.get('semantic_text',r['content'])} "
            f"(id={r.get('id', '?')}; fonte={r['fonte']}; confiança={r['confianca']}; "
            f"origem={r.get('created_at') or 'não registrada'}; evidências={evidencias}{legado}{ausencia})")


def _source_authorship(context):
    try:
        value=json.loads(context) if isinstance(context,str) else context
        return value.get('autoria',{}) if isinstance(value,dict) else {}
    except (ValueError,TypeError):return {'legacy_context_unparsed':True}


def _confirmar(tabela, identificador, campos):
    """Leitura independente após commit, usando o mesmo banco, não o vetor."""
    with __import__('contextlib').closing(_conn()) as c:
        linha = c.execute(f"SELECT {','.join(campos)} FROM {tabela} WHERE id=?", (identificador,)).fetchone()
    if linha != tuple(campos.values()):
        raise RuntimeError('Gravação ocorreu, mas a leitura independente não confirmou os valores.')
    return f'[PERSISTÊNCIA VERIFICADA id={identificador}]'


def _evidencias_turno(evidencias):
    from core import diagnostics
    if evidencias is not None:
        return list(evidencias) if isinstance(evidencias, (list, tuple)) else [evidencias]
    return [dict(origin, turn_id=diagnostics.current_turn_id(), basis='registro_por_ferramenta',
                 sujeito_id=None, sujeito_nome=None)
            for origin in diagnostics.current_turn_context().get('input_sources', [])]


def _diagnosticar_commit(operation, identifier, tipo, confidence, source, evidence):
    from core import diagnostics
    diagnostics.emit('memory.committed', operation=operation, entity=__import__('config').ENTIDADE_ID,
                     memory_id=identifier, type=tipo, confidence=confidence, source=source,
                     evidence=evidence, database=str(DB_PATH), verified=True)


def _indexar(*args):
    """SQL já confirmado; falha opcional do índice não autoriza repetir INSERT."""
    try:
        if vetor.salvar(*args):
            return ''
    except Exception as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.vector_index', __import__('config').VECTOR_DIR, exc,
                                        retry_safe=True, committed=True)
    return ' (SQLite salvo; índice vetorial não atualizado)'


# ---------------------------------------------------------------------------
# Conhecimento em frase (fato, regra, relação, confiança, preferência...)
# ---------------------------------------------------------------------------

FONTES_REVISAVEIS = ("escriba_llm",)


def semelhantes(conteudo: str, limite: int = 3, *, fontes=FONTES_REVISAVEIS) -> list[dict]:
    """Anotações ativas parecidas com ``conteudo``, só das ``fontes`` dadas, mais parecida primeiro.

    Para o revisor de memória (07/11) comparar uma anotação nova com as já guardadas. Só leitura: não marca acesso
    (não é lembrança usada numa resposta). Parecida = palavras em comum ou proximidade no índice vetorial; quem
    decide se é a mesma coisa é o revisor, então aqui o filtro é largo."""
    conteudo = (conteudo or "").strip()
    limite = max(0, min(10, int(limite)))
    fontes = tuple(fontes or ())
    if not conteudo or not limite or not fontes:
        return []
    conn = _conn()
    try:
        linhas = conn.execute(f"SELECT id, type, content FROM memories WHERE status='active' AND source IN "
                              f"({','.join('?' for _ in fontes)})", fontes).fetchall()
    finally:
        conn.close()
    if not linhas:
        return []
    distancias = {r["id"]: r.get("distancia") for r in vetor.buscar("conhecimento", conteudo, 30)}
    notas = []
    chaves = _tokens(conteudo) - GENERICAS_REVISAO
    for mem_id, tipo, texto in linhas:
        outras = _tokens(texto) - GENERICAS_REVISAO
        lexical = len(chaves & outras) / len(chaves | outras) if chaves and outras else 0.0
        d = distancias.get(mem_id)
        semantica = 1.0 / (1.0 + d) if isinstance(d, (int, float)) and math.isfinite(d) and d >= 0 else 0.0
        if lexical >= LIMIAR_SEMELHANTE_LEXICO or semantica >= LIMIAR_SEMELHANTE_VETOR:
            notas.append((max(lexical, semantica), dict(id=mem_id, tipo=tipo, conteudo=texto)))
    notas.sort(key=lambda n: -n[0])
    return [registro_ for _, registro_ in notas[:limite]]


# "A pessoa ..." está em quase toda anotação; sozinha não faz duas parecidas.
GENERICAS_REVISAO = {"pessoa", "usuario", "usuaria", "entidade", "lilith", "hoshino", "alistair"}
LIMIAR_SEMELHANTE_LEXICO = 0.12
LIMIAR_SEMELHANTE_VETOR = 0.5  # calibrado 07/11 nos pares da avaliação (ensaios/revisor-memoria-20261107)


def remember(conteudo: str, entidades=None, tipo: str = "fato", confianca: float = 0.7,
             chave: str = None, fonte: str = "conversa", evidencias=None, conexao=None, substituir=()) -> str:
    """Registra algo aprendido. Só substitui registro anterior em conflito real.

    ``substituir``: ids que o revisor de memória apontou como repetidos ou velhos diante deste registro. Só vale para
    anotações ainda ativas do próprio escriba-modelo (``FONTES_REVISAVEIS``); elas ficam ``superseded`` e o novo
    registro guarda o vínculo em ``supersedes``. Nada é apagado."""
    conteudo = (conteudo or "").strip()
    if not conteudo:
        return "Erro: conteúdo vazio, nada para registrar."
    tipo = categoria(tipo, fonte)
    entidades = _entidades_lista(entidades)
    confianca = confianca_valida(confianca, 0.7)
    evidencias = _evidencias_turno(evidencias)

    conn = conexao if conexao is not None else _conn(escrita=True)
    try:
        cur = conn.cursor()

        # Só uma chave explícita identifica o atributo a atualizar. Similaridade
        # lexical não distingue manhã/noite, afirmação/negação ou condições.
        substituidos = []
        if entidades or chave:
            cur.execute("""SELECT id, content, entities, chave, source, type, links FROM memories
                           WHERE status='active'""")
            for mem_id, texto, ents_json, chave_antiga, origem, tipo_antigo, old_links in cur.fetchall():
                # A reflexão legada não pode substituir um fato nem o inverso.
                if categoria(tipo_antigo, origem) != tipo:
                    continue
                try:
                    old_subjects = {e.get('sujeito_id') for e in json.loads(old_links or '[]') if isinstance(e, dict) and e.get('sujeito_id')}
                except (ValueError, TypeError):
                    old_subjects = set()
                subjects = {e.get('sujeito_id') for e in evidencias if isinstance(e, dict) and e.get('sujeito_id')}
                if subjects and not old_subjects:
                    continue  # autoria legada desconhecida não é adivinhada para supersession
                if old_subjects and subjects and old_subjects.isdisjoint(subjects):
                    continue  # mesmo atributo/objeto não torna dois participantes o mesmo sujeito
                try:
                    ents = set(_normalizar(e) for e in json.loads(ents_json or "[]"))
                except json.JSONDecodeError:
                    ents = set()
                mesmas = bool(ents & {_normalizar(e) for e in entidades}) or (not ents and not entidades)
                if not mesmas:
                    continue
                if chave and chave_antiga and _normalizar(chave) == _normalizar(chave_antiga):
                    substituidos.append(mem_id)
            if substituidos:
                cur.execute(
                    f"UPDATE memories SET status='superseded', valid_to=? "
                    f"WHERE id IN ({','.join('?' * len(substituidos))})",
                    [_now()] + substituidos)

        alvos = [str(m) for m in (substituir or ()) if m and str(m) not in substituidos]
        if alvos:
            cur.execute(f"SELECT id FROM memories WHERE status='active' AND id IN ({','.join('?' * len(alvos))}) "
                        f"AND source IN ({','.join('?' * len(FONTES_REVISAVEIS))})", alvos + list(FONTES_REVISAVEIS))
            revisados = [linha[0] for linha in cur.fetchall()]
            if revisados:
                cur.execute(f"UPDATE memories SET status='superseded', valid_to=? "
                            f"WHERE id IN ({','.join('?' * len(revisados))})", [_now()] + revisados)
                substituidos += revisados

        mem_id = f"mem-{uuid.uuid4().hex[:12]}"
        cur.execute(
            """INSERT INTO memories (id, type, created_at, valid_from, source, confidence,
                                     importance, content, entities, links, supersedes, chave, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
            (mem_id, tipo, _now(), _now(), fonte, confianca, 0.5, conteudo,
             json.dumps(entidades, ensure_ascii=False), json.dumps(evidencias if evidencias is not None else [], ensure_ascii=False),
             json.dumps(substituidos), chave))
        if conexao is not None:
            return f"Registrado [{tipo}]: {conteudo}"  # chamador confirma a transação inteira
        conn.commit()
        conn.close()

        recibo = _confirmar('memories', mem_id, dict(type=tipo, content=conteudo, confidence=confianca, source=fonte))
        _diagnosticar_commit('knowledge.remember', mem_id, tipo, confianca, fonte, evidencias)
        aviso = _indexar("conhecimento", mem_id, conteudo,
                     {"tipo": tipo, "data": _now(), "confianca": confianca,
                      "entidades": ", ".join(entidades), "fonte": fonte})
        extra = f" (substituiu {len(substituidos)} registro(s) em conflito)" if substituidos else ""
        return f"Registrado [{tipo}]: {conteudo}{extra}{aviso}\n{recibo}"
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.remember', DB_PATH, exc, retry_safe=False)
        raise
    finally:
        if conexao is None:
            conn.close()


# ---------------------------------------------------------------------------
# Propriedades: características de uma coisa
# ---------------------------------------------------------------------------

def registrar_propriedade(entidade: str, propriedade: str, valor: str, unidade: str = None,
                          confianca: float = 0.8, fonte: str = "conversa", *, evidencias=None) -> str:
    """Guarda uma característica de algo: 'RX 6650 XT' / 'VRAM' / '8' / 'GB'.

    Diferente de um fato solto, propriedade tem chave e valor — então dá para
    perguntar depois "quanto de VRAM a placa tem?" e substituir só aquele campo
    quando o valor mudar, sem mexer no resto do que se sabe da coisa.
    """
    entidade = (entidade or "").strip()
    propriedade = (propriedade or "").strip()
    if not entidade or not propriedade:
        return "Erro: preciso da entidade e do nome da propriedade."
    valor = "" if valor is None else str(valor).strip()
    evidencias = _evidencias_turno(evidencias)
    if evidencias:
        fonte = json.dumps(dict(kind='memory_provenance', source=fonte, evidence=evidencias), ensure_ascii=False)

    conn = _conn(escrita=True)
    try:
        cur = conn.cursor()
        cur.execute("""SELECT id, valor FROM properties
                       WHERE status='active' AND lower(entity)=lower(?) AND lower(chave)=lower(?)""",
                    (entidade, propriedade))
        anterior = cur.fetchone()
        if anterior:
            cur.execute("UPDATE properties SET status='superseded', valid_to=? WHERE id=?",
                        (_now(), anterior[0]))
        prop_id = f"prop-{uuid.uuid4().hex[:10]}"
        cur.execute("""INSERT INTO properties (id, entity, chave, valor, unidade, confidence,
                                               source, created_at, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                    (prop_id, entidade, propriedade, valor, unidade, confianca_valida(confianca, 0.8), fonte, _now()))
        conn.commit()
        conn.close()

        texto = f"{entidade}: {propriedade} = {valor}{(' ' + unidade) if unidade else ''}"
        recibo = _confirmar('properties', prop_id, dict(entity=entidade, chave=propriedade, valor=valor,
                           confidence=confianca_valida(confianca, .8), source=fonte))
        _diagnosticar_commit('knowledge.property', prop_id, 'propriedade', confianca_valida(confianca, .8), fonte, evidencias)
        aviso = _indexar("conhecimento", prop_id, texto,
                     {"tipo": "propriedade", "entidade": entidade, "data": _now()})
        if anterior and anterior[1] != valor:
            return f"Propriedade atualizada — {texto} (antes: {anterior[1]}){aviso}\n{recibo}"
        return f"Propriedade registrada — {texto}{aviso}\n{recibo}"
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.registrar_propriedade', DB_PATH, exc, retry_safe=False)
        raise
    finally:
        conn.close()


def propriedades_de(entidade: str) -> str:
    """Tudo que se sabe sobre as características de uma coisa."""
    if audience.public_turn():
        return _public_recall(entidade, properties_only=True)
    entidade = (entidade or "").strip()
    if not entidade:
        return "Erro: informe a entidade."
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT chave, valor, unidade, confidence, source, created_at, id FROM properties
                       WHERE status='active' AND lower(entity) LIKE lower(?)
                       ORDER BY chave""", (f"%{entidade}%",))
        linhas = cur.fetchall()
        if linhas:
            cur.execute("""UPDATE properties SET access_count=COALESCE(access_count,0)+1
                           WHERE status='active' AND lower(entity) LIKE lower(?)""",
                        (f"%{entidade}%",))
            conn.commit()
        conn.close()
        if not linhas:
            return f"Não tenho propriedades registradas de '{entidade}'."
        corpo = "\n".join(
            f"- {chave}: {valor}{(' ' + und) if und else ''}"
            f" (tipo=propriedade; confiança={confianca_valida(conf, 0.8)}; fonte={fonte or 'não registrada'}; origem={criado}; id={pid})"
            for chave, valor, und, conf, fonte, criado, pid in linhas)
        return f"Propriedades de '{entidade}':\n{corpo}"
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.propriedades_de', DB_PATH, exc, retry_safe=True)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Procedimentos: como as coisas funcionam / como se faz
# ---------------------------------------------------------------------------

def registrar_procedimento(nome: str, objetivo: str, passos, precondicoes: str = None,
                           resultado_esperado: str = None, tags=None, ambiente: str = None,
                           notas: str = None, confianca: float = 0.7) -> str:
    """Guarda como algo funciona ou como se faz algo, em passos.

    É a memória que faltava: antes, cada vez que ela descobria como reiniciar um
    serviço ou como o Ollama trata OLLAMA_MODELS, isso sumia junto com o
    contexto. Agora fica, com contador de quantas vezes funcionou.
    """
    nome = (nome or "").strip()
    if not nome:
        return "Erro: dê um nome ao procedimento (ex: 'reiniciar o Ollama')."
    if isinstance(passos, str):
        passos = [p.strip() for p in re.split(r"\n|;|\d+\)\s*", passos) if p.strip()]
    passos = [str(p).strip() for p in (passos or []) if str(p).strip()]
    if not passos:
        return "Erro: um procedimento precisa de pelo menos um passo."
    tags = _entidades_lista(tags)
    confianca = confianca_valida(confianca, 0.7)

    conn = _conn(escrita=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nome, objetivo FROM procedures WHERE status='active'")
        for proc_id, nome_antigo, obj_antigo in cur.fetchall():
            if _semelhanca(nome_antigo, nome) >= 0.8 or (
                    objetivo and obj_antigo and _semelhanca(obj_antigo, objetivo) >= 0.85):
                cur.execute("""UPDATE procedures SET passos=?, precondicoes=?, resultado_esperado=?,
                               tags=?, ambiente=?, notas=?, confidence=? WHERE id=?""",
                            (json.dumps(passos, ensure_ascii=False), precondicoes,
                             resultado_esperado, json.dumps(tags, ensure_ascii=False),
                             ambiente, notas, float(confianca), proc_id))
                conn.commit()
                conn.close()
                recibo = _confirmar('procedures', proc_id, dict(passos=json.dumps(passos, ensure_ascii=False), confidence=confianca))
                aviso = _indexar("procedimento", proc_id,
                             f"{nome}. Objetivo: {objetivo}. Passos: " + " | ".join(passos),
                             {"nome": nome, "data": _now()})
                return f"Procedimento '{nome_antigo}' [{proc_id}] atualizado com os passos novos.{aviso}\n{recibo}"

        proc_id = f"proc-{uuid.uuid4().hex[:10]}"
        cur.execute("""INSERT INTO procedures (id, nome, objetivo, passos, precondicoes,
                           resultado_esperado, tags, ambiente, sucessos, falhas,
                           created_at, notas, confidence, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, 'active')""",
                    (proc_id, nome, objetivo, json.dumps(passos, ensure_ascii=False),
                     precondicoes, resultado_esperado, json.dumps(tags, ensure_ascii=False),
                     ambiente, _now(), notas, float(confianca)))
        conn.commit()
        conn.close()
        recibo = _confirmar('procedures', proc_id, dict(nome=nome, passos=json.dumps(passos, ensure_ascii=False), confidence=confianca))
        aviso = _indexar("procedimento", proc_id,
                     f"{nome}. Objetivo: {objetivo}. Passos: " + " | ".join(passos),
                     {"nome": nome, "data": _now()})
        return f"Procedimento [{proc_id}] '{nome}' registrado com {len(passos)} passo(s).{aviso}\n{recibo}"
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.registrar_procedimento', DB_PATH, exc, retry_safe=False)
        raise
    finally:
        conn.close()


def registrar_resultado_procedimento(identificador: str, funcionou: bool,
                                     observacao: str = None) -> str:
    """Diz se um procedimento funcionou desta vez — é assim que ela aprende o que
    realmente dá certo, em vez de repetir uma receita que falha sempre."""
    conn = _conn(escrita=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT nome, sucessos, falhas, notas FROM procedures WHERE id=?",
                    (identificador,))
        linha = cur.fetchone()
        if not linha:
            conn.close()
            return f"Procedimento '{identificador}' não existe."
        nome, sucessos, falhas, notas = linha
        sucessos = (sucessos or 0) + (1 if funcionou else 0)
        falhas = (falhas or 0) + (0 if funcionou else 1)
        nota_nova = "\n".join(filter(None, [notas, f"[{_now()}] {observacao}" if observacao else None]))
        total = sucessos + falhas
        confianca = round(0.3 + 0.7 * (sucessos / total), 2) if total else 0.5
        cur.execute("""UPDATE procedures SET sucessos=?, falhas=?, ultima_utilizacao=?,
                       notas=?, confidence=? WHERE id=?""",
                    (sucessos, falhas, _now(), nota_nova, confianca, identificador))
        conn.commit()
        conn.close()
        recibo = _confirmar('procedures', identificador, dict(sucessos=sucessos, falhas=falhas, confidence=confianca))
        return (f"Procedimento '{nome}': {sucessos} sucesso(s) / {falhas} falha(s), "
                f"confiança agora {confianca}.\n{recibo}")
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.registrar_resultado_procedimento', DB_PATH, exc, retry_safe=False)
        raise
    finally:
        conn.close()


def consultar_procedimento(objetivo: str, limite: int = 3) -> str:
    """Busca como fazer algo entre os procedimentos registrados."""
    objetivo = (objetivo or "").strip()
    if not objetivo:
        return "Erro: diga o que você quer fazer."
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT id, nome, objetivo, passos, precondicoes, resultado_esperado,
                          sucessos, falhas, confidence, ambiente, created_at
                       FROM procedures WHERE status='active'""")
        todos = cur.fetchall()
        conn.close()
        if not todos:
            return ("Não tenho nenhum procedimento registrado ainda. Quando descobrir como "
                    "algo funciona, use registrar_procedimento para não perder.")

        ids_vetor = {r["id"]: r["distancia"] for r in vetor.buscar("procedimento", objetivo, 5)}
        pontuados = []
        for (pid, nome, obj, passos, pre, res, suc, fal, conf, amb, criado) in todos:
            texto = f"{nome} {obj or ''} {passos or ''}"
            base = _semelhanca(texto, objetivo)
            if pid in ids_vetor and ids_vetor[pid] is not None:
                base = max(base, 1.0 / (1.0 + float(ids_vetor[pid])))
            pontuados.append((base * 0.75 + confianca_valida(conf, 0.5) * 0.25, pid, nome, obj, passos,
                          pre, res, suc, fal, conf, amb, criado))
        pontuados.sort(reverse=True, key=lambda x: x[0])
        melhores = [p for p in pontuados[:limite] if p[0] > 0.12]
        if not melhores:
            return f"Nada registrado sobre como fazer '{objetivo}'."

        blocos = []
        for (score, pid, nome, obj, passos_json, pre, res, suc, fal, conf, amb, criado) in melhores:
            try:
                passos = json.loads(passos_json or "[]")
            except json.JSONDecodeError:
                passos = [passos_json]
            corpo = [f"[{pid}] {nome}" + (f" — {obj}" if obj else "")]
            if pre:
                corpo.append(f"  Antes: {pre}")
            corpo += [f"  {i}. {p}" for i, p in enumerate(passos, 1)]
            if res:
                corpo.append(f"  Esperado: {res}")
            if amb:
                corpo.append(f"  Ambiente: {amb}")
            corpo.append(f"  Histórico: {suc or 0} ok / {fal or 0} falhas (confiança {confianca_valida(conf, .5)}; tipo=procedimento; fonte=não registrada; origem={criado})")
            blocos.append("\n".join(corpo))
        return "Procedimentos relevantes:\n" + "\n\n".join(blocos)
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.consultar_procedimento', DB_PATH, exc, retry_safe=True)
        raise
    finally:
        conn.close()


def _concept_source_texts(conn):
    """Search interpretations through their local evidence, not invented keywords.

    A lesson may paraphrase an event and omit its subject name. The original
    episode stays the source of that name; no generated claim becomes a fact.
    Legacy non-JSON links remain readable. Diaries are never search material.
    """
    found = {}
    for table, columns in (('episodes',('what_happened','action_taken','result','context')),
                           ('memories',('content','entities')), ('reflections',('tema','conteudo'))):
        if not conn.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():
            continue
        present={row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
        text_expr="||char(10)||".join(f"COALESCE(origin.{column},'')" for column in columns if column in present) or "''"
        extra = " AND (origin.tipo IS NULL OR origin.tipo!='diario')" if table=='reflections' else ''
        for mid, text in conn.execute(f"""SELECT m.id,{text_expr} FROM memories m
                JOIN json_each(CASE WHEN json_valid(m.links) THEN m.links ELSE '{{}}' END,'$.sources') ref
                JOIN {table} origin ON origin.id=json_extract(ref.value,'$.id')
                WHERE m.status='active' AND m.source='oficina_logica'
                AND json_extract(ref.value,'$.table')=? {extra}""", (table,)):
            found.setdefault(mid, []).append(text or '')
    return {mid:'\n'.join(texts) for mid,texts in found.items()}


def como_funciona(topico: str) -> str:
    """Resposta consolidada: propriedades + procedimentos + regras sobre um tópico.

    É o atalho para 'como isso funciona?' — junta o que ela sabe da coisa
    (propriedades), como se mexe nela (procedimentos) e o que foi combinado
    sobre ela (regras/fatos).
    """
    if audience.public_turn():return _public_recall(topico)
    topico = (topico or "").strip()
    if not topico:
        return "Erro: informe o tópico."
    partes = []

    props = propriedades_de(topico)
    if not props.startswith("Não tenho"):
        partes.append(props)

    procs = consultar_procedimento(topico)
    if not procs.startswith("Nada registrado") and not procs.startswith("Não tenho"):
        partes.append(procs)

    conn = _conn()
    try:
        cur = conn.cursor()
        linhas = _memories_about(conn, topico, 8)
        conn.close()
        if linhas:
            partes.append("O que sei sobre isso:\n" + "\n".join(
                "- " + formatar_registro(registro(dict(zip(
                    ('id', 'type', 'content', 'confidence', 'source', 'created_at', 'links'), l)))) for l in linhas))

        if not partes:
            return (f"Não sei como '{topico}' funciona — não tenho nada registrado. "
                    f"Se descobrirmos agora, eu registro com registrar_procedimento "
                    f"ou registrar_propriedade.")
        return "\n\n".join(partes)
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.como_funciona', DB_PATH, exc, retry_safe=True)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Recuperação híbrida
# ---------------------------------------------------------------------------

def _recencia(iso: str) -> float:
    seconds = elapsed_seconds(iso)
    if seconds is None:
        return 0.5
    return math.exp(-seconds / (86400 * 30.0))  # meia-vida de ~3 semanas


def recall_episodes(query: str, limit: int = 3) -> list[str]:
    """O vetor sugere IDs; somente o episódio SQLite ativo fornece o conteúdo.

    Não projeta textos órfãos/desatualizados do índice como lembranças reais.
    A busca integral de chat continua disponível quando este recorte não basta.
    """
    limit = max(0, min(20, int(limit)))
    if not (query or '').strip() or not limit:
        return []
    hits = vetor.buscar('episodio', query, limit * 3)
    selected = []
    seen = set()
    conn = _conn()
    try:
        for hit in hits:
            identifier = hit.get('id')
            if not isinstance(identifier, str) or identifier in seen:
                continue
            seen.add(identifier)
            row = conn.execute("SELECT what_happened,created_at,source,context FROM episodes WHERE id=? AND status='active'",
                               (identifier,)).fetchone()
            if row is None:
                continue
            text, timestamp, source, context = row
            if not audience.visible(conn,'episodes',dict(id=identifier,context=context)):continue
            distance = hit.get('distancia')
            strong = type(distance) in (int, float) and math.isfinite(distance) and 0 <= distance <= (1 / .7 - 1)
            if not strong and _semelhanca(query, text) <= .05:
                continue
            selected.append(f'[{timestamp}; id={identifier}; fonte={source or "não registrada"}] {text}')
            if len(selected) >= limit:
                break
        return selected
    finally:
        conn.close()


def recall(query: str, limit: int = 5, *, estruturado=False) -> list:
    """Conhecimento relevante para a mensagem atual, por significado + recência +
    confiança + uso. Marca acesso no que foi recuperado."""
    query = (query or "").strip()
    limit = max(0, min(50, int(limit)))
    if not query or not limit:
        return []

    conn = _conn()
    try:
        cur = conn.cursor()
        person_column='person_id' if any(r[1]=='person_id' for r in conn.execute('PRAGMA table_info(memories)')) else 'NULL'
        cur.execute(f"""SELECT id, type, content, confidence, created_at, access_count, chave, source, links, entities, {person_column}
                       FROM memories WHERE status='active'""")
        memorias = cur.fetchall()

        cur.execute("""SELECT id, entity, chave, valor, unidade, confidence, created_at, access_count, source
                       FROM properties WHERE status='active'""")
        propriedades = cur.fetchall()

        candidatos = []
        priority=card_priorities(conn)
        origins = _concept_source_texts(conn)
        for (mid, tipo, conteudo, conf, criado, usos, _chave, fonte, links, entities, person_id) in memorias:
            if not audience.visible(conn,'memories',dict(id=mid,type=tipo,links=links)):continue
            r = registro(dict(id=mid, type=tipo, content=conteudo, confidence=conf, created_at=criado, source=fonte, links=links))
            tier,bonus=priority('memories',dict(id=mid,type=tipo,links=links,entities=entities,person_id=person_id))
            r['importance']=tier
            candidatos.append({"id": mid, "texto": formatar_registro(r), "conf": r['confianca'], "registro": r,
                               "priority_bonus":bonus,
                               "criado": criado, "usos": usos or 0, "tabela": "memories",
                               "bruto": r.get('semantic_text', conteudo)+'\n'+origins.get(mid,'')})
        for (pid, ent, chave, valor, und, conf, criado, usos, fonte) in propriedades:
            if not audience.visible(conn,'properties',dict(id=pid,source=fonte)):continue
            texto = f"{ent}: {chave} = {valor}{(' ' + und) if und else ''}"
            r = registro(dict(id=pid, type='propriedade', content=texto, confidence=conf, created_at=criado, source=fonte), 0.8)
            tier,bonus=priority('properties',dict(id=pid,entity=ent));r['importance']=tier
            candidatos.append({"id": pid, "texto": formatar_registro(r), "conf": r['confianca'], "registro": r,
                               "priority_bonus":bonus,
                               "criado": criado, "usos": usos or 0, "tabela": "properties",
                               "bruto": texto})
        if not candidatos:
            conn.close()
            return []

        distancias = {r["id"]: r.get("distancia") for r in vetor.buscar("conhecimento", query, limit * 3)}
        pesos = PESOS_RECALL
        for c in candidatos:
            sim = _semelhanca(c["bruto"], query)
            if c['id'] in origins:
                terms = _tokens(query)
                if terms:
                    sim = max(sim, .25*len(terms & _tokens(origins[c['id']]))/len(terms))
            d = distancias.get(c["id"])
            # O índice é auxiliar. Distância inválida não pode produzir score
            # infinito/NaN; proximidade fraca não vence só por ser recente/usada.
            semantic = 0.0
            if type(d) in (int, float) and math.isfinite(d) and d >= 0:
                semantic = 1.0 / (1.0 + d)
            c['relevante'] = sim > 0.05 or semantic >= 0.7
            sim = max(sim, semantic)
            c["score"] = (pesos["similaridade"] * sim
                          + pesos["recencia"] * _recencia(c["criado"])
                          + pesos["confianca"] * float(c["conf"])
                          + pesos["uso"] * min((c["usos"] or 0) / 10.0, 1.0)
                          + c['priority_bonus'])
            c["sim"] = sim

        candidatos = [c for c in candidatos if c['relevante']]
        candidatos.sort(key=lambda c: c["score"], reverse=True)
        escolhidos = candidatos[:limit]

        for c in escolhidos:  # registra uso — alimenta o peso "uso" na próxima vez
            cur.execute(f"UPDATE {c['tabela']} SET access_count=COALESCE(access_count,0)+1, "
                        f"last_accessed=? WHERE id=?" if c["tabela"] == "memories" else
                        f"UPDATE {c['tabela']} SET access_count=COALESCE(access_count,0)+1 "
                        f"WHERE id=?",
                        (_now(), c["id"]) if c["tabela"] == "memories" else (c["id"],))
        conn.commit()
        conn.close()
        return [c["registro"] if estruturado else c["texto"] for c in escolhidos]
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.recall', DB_PATH, exc, retry_safe=True)
        raise
    finally:
        conn.close()


def _memories_about(conn, topic, limit):
    origins = _concept_source_texts(conn)
    related = [mid for mid,text in origins.items() if _normalizar(topic) in _normalizar(text)]
    placeholders = ','.join('?' for _ in related) or 'NULL'
    return conn.execute(f"""SELECT id,type,content,confidence,source,created_at,links FROM memories
            WHERE status='active' AND (entities LIKE ? OR content LIKE ? OR id IN ({placeholders}))
            ORDER BY created_at DESC LIMIT ?""", (f'%{topic}%', f'%{topic}%', *related, limit)).fetchall()


def _public_recall(query, properties_only=False):
    rows=recall(query,limit=25,estruturado=True)
    if properties_only:rows=[row for row in rows if row['tipo']=='propriedade']
    return '\n'.join(formatar_registro(row) for row in rows) or (
        'Não tenho registros relevantes com origem pública confirmada neste canal. '
        'Isso não significa que registros privados ou antigos tenham sido apagados.')


def list_facts_about(entidade: str) -> str:
    """Tudo que está registrado sobre uma entidade: frases, propriedades e procedimentos."""
    if audience.public_turn():return _public_recall(entidade)
    entidade = (entidade or "").strip()
    if not entidade:
        return "Erro: informe uma entidade para consultar."
    padrao = f"%{entidade}%"
    conn = _conn()
    try:
        cur = conn.cursor()
        memorias = _memories_about(conn, entidade, 25)
        cur.execute("""SELECT chave, valor, unidade, confidence, source, created_at FROM properties
                       WHERE status='active' AND lower(entity) LIKE lower(?)""", (padrao,))
        props = cur.fetchall()
        cur.execute("""SELECT id, nome FROM procedures
                       WHERE status='active' AND (nome LIKE ? OR objetivo LIKE ? OR tags LIKE ?)""",
                    (padrao, padrao, padrao))
        procs = cur.fetchall()
        conn.close()

        if not memorias and not props and not procs:
            return (f"Não tenho nada registrado sobre '{entidade}'. Não preencha essa lacuna "
                    f"com suposição — pergunte ou diga que não sabe.")
        partes = []
        if props:
            partes.append("Propriedades:\n" + "\n".join(
                f"- [propriedade] {c}: {v}{(' ' + u) if u else ''} (confiança={confianca_valida(conf, 0.8)}; fonte={fonte or 'não registrada'}; origem={criado})"
                for c, v, u, conf, fonte, criado in props))
        if memorias:
            partes.append("Conhecimento:\n" + "\n".join(
                "- " + formatar_registro(registro(dict(zip(
                    ('id', 'type', 'content', 'confidence', 'source', 'created_at', 'links'), l))))
                for l in memorias))
        if procs:
            partes.append("Procedimentos ligados: " + ", ".join(f"[{i}] {n}" for i, n in procs))
        return f"Sobre '{entidade}':\n" + "\n\n".join(partes)
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.list_facts_about', DB_PATH, exc, retry_safe=True)
        raise
    finally:
        conn.close()


def esquecer(identificador: str) -> str:
    """Marca um registro como inativo (não apaga o histórico)."""
    conn = _conn()
    try:
        cur = conn.cursor()
        for tabela in ("memories", "properties", "procedures"):
            cur.execute(f"UPDATE {tabela} SET status='retired' WHERE id=?", (identificador,))
            if cur.rowcount:
                conn.commit()
                conn.close()
                vetor.remover("conhecimento", identificador)
                vetor.remover("procedimento", identificador)
                return f"Registro {identificador} desativado."
        conn.close()
        return f"Não achei nenhum registro com ID '{identificador}'."
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.esquecer', DB_PATH, exc, retry_safe=False)
        raise
    finally:
        conn.close()


def estatisticas() -> str:
    """Quanto ela realmente sabe — útil para ela não superestimar a própria memória."""
    conn = _conn()
    try:
        cur = conn.cursor()
        dados = {}
        for tabela in ("memories", "properties", "procedures", "episodes"):
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tabela} WHERE status='active'")
                dados[tabela] = cur.fetchone()[0]
            except sqlite3.OperationalError as exc:
                from core import diagnostics
                diagnostics.persistence_failure('knowledge.count', DB_PATH, exc, retry_safe=True, table=tabela)
                dados[tabela] = 'indisponível'
        cur.execute("SELECT type, COUNT(*) FROM memories WHERE status='active' GROUP BY type")
        por_tipo = ", ".join(f"{t}: {n}" for t, n in cur.fetchall()) or "nada"
        conn.close()
        return (f"Memória: {dados['episodes']} episódios, {dados['memories']} conhecimentos "
                f"({por_tipo}), {dados['properties']} propriedades, "
                f"{dados['procedures']} procedimentos. {vetor.estado()}")
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('knowledge.estatisticas', DB_PATH, exc, retry_safe=True)
        raise
    finally:
        conn.close()
