"""Reflexão noturna profunda.

Executada uma vez por noite, ou explicitamente quando a pessoa avisa que vai
ou foi dormir. O material é amplo: episódios, objetivos, curiosidades, pessoas,
ferramentas/erros e estado emocional. O resultado continua sendo reflexão, não
fato objetivo.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import config
from core import bd, state_file, diagnostics, history
from memory import knowledge_store as saber

def _state_path() -> Path:
    return Path(config.RUNTIME_DIR) / "reflexao_noturna.json"


def _pending_path() -> Path:
    return Path(config.RUNTIME_DIR) / "reflexao_noturna_pendente.json"


def _chave_noite(agora: datetime | None = None) -> str:
    agora = history.local_datetime(agora)
    inicio = config.REFLEXAO_NOTURNA_INICIO
    if agora.hour < inicio:
        return (agora - timedelta(days=1)).strftime("%Y-%m-%d")
    return agora.strftime("%Y-%m-%d")


def pendente() -> bool:
    return bool(state_file.read(_pending_path()).get('pendente'))


def solicitar(motivo="usuário avisou que vai dormir") -> None:
    pending = _pending_path()
    return state_file.update(pending, lambda d: d.update(pendente=True, motivo=motivo,
                             solicitado_em=history.utc_timestamp()), 'night_reflection.request')


def motivo_pendente() -> str:
    return state_file.read(_pending_path()).get('motivo') or 'reflexão solicitada'


def consumir_pendente() -> None:
    try:
        pending = _pending_path()
        if pending.exists():
            pending.unlink()
    except OSError as exc:
        diagnostics.persistence_failure('night_reflection.consume', _pending_path(), exc, retry_safe=True)
        return False
    return True


def concluida_na_noite(agora=None) -> bool:
    return state_file.read(_state_path()).get('chave') == _chave_noite(agora)


def marcar_concluida(agora=None, motivo="horário noturno") -> None:
    agora = history.local_datetime(agora)
    state = _state_path()
    salvo = state_file.update(state, lambda d: d.update(chave=_chave_noite(agora), motivo=motivo,
                              concluida_em=history.utc_timestamp(agora)), 'night_reflection.complete')
    return consumir_pendente() if salvo else False


def horario_noturno(agora=None) -> bool:
    agora = history.local_datetime(agora)
    inicio, fim = config.REFLEXAO_NOTURNA_INICIO, config.REFLEXAO_NOTURNA_FIM
    if inicio == fim:
        return False
    if inicio < fim:
        return inicio <= agora.hour < fim
    return agora.hour >= inicio or agora.hour < fim


def aviso_de_sono(texto: str) -> bool:
    """Reconhece despedida explícita de sono, sem confundir um simples 'boa noite'."""
    t = (texto or "").casefold()
    padroes = (
        r"\b(vou|vou indo|vou la|vou lá|partiu)\s+(dormir|deitar|pra cama|para a cama)\b",
        r"\b(indo|partindo)\s+(dormir|deitar)\b",
        r"\b(fui|tchau).{0,40}\b(dormir|deitar|cama)\b",
    )
    return any(re.search(padrao, t) for padrao in padroes)


def _registros_eventos_do_dia(agora=None):
    """Origem do JSONL real; linha/hash não são message IDs inventados."""
    agora = history.local_datetime(agora)
    caminho = Path(config.EVENT_LOG_DIR) / f"events_{agora:%Y-%m-%d}.jsonl"
    if not caminho.exists():
        return [], False
    linhas = []
    inicio = history.timestamp_epoch(agora.replace(hour=0, minute=0, second=0, microsecond=0))
    fim = history.timestamp_epoch(agora)
    try:
        with caminho.open('rb') as arquivo:
            ultimas = deque(enumerate(arquivo, 1), maxlen=301)
        janela_limitada = len(ultimas) > 300
        for numero, raw in list(ultimas)[-300:]:
            try:
                obj = json.loads(raw.decode('utf-8', errors='replace'))
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            tipo = obj.get("tipo", "")
            if tipo in {"erro", "ferramenta", "investigacao", "ouviu", "olhou_tela",
                        "comando_aprovado", "xadrez_fim", "reset_memoria"}:
                instante = history.timestamp_epoch(obj.get('ts'))
                if instante is None:
                    history._clock_warning('night_reflection.events', 'invalid_event_time')
                    continue
                if not inicio <= instante <= fim:
                    continue
                ref = dict(file=caminho.name, line=numero, timestamp=obj.get('ts'), type=tipo,
                           line_sha256=hashlib.sha256(raw.rstrip(b'\r\n')).hexdigest())
                linhas.append((f"[{tipo}] {obj.get('ts')} | origem={caminho.name}:{numero} | "
                               f"{json.dumps(obj.get('detalhe', ''), ensure_ascii=False)}", ref))
    except OSError as exc:
        diagnostics.persistence_failure('night_reflection.read_events', caminho, exc, retry_safe=True)
        raise  # Falha não equivale a dia sem eventos e não pode marcar conclusão.
    return linhas[-80:], janela_limitada or len(linhas) > 80


def _eventos_arquivo_do_dia(agora=None) -> list[str]:
    return [texto for texto, _ in _registros_eventos_do_dia(agora)[0]]


def preparar_material(max_chars: int = None, *, agora=None) -> dict:
    """Um recorte limitado com referências, reutilizado até o commit da reflexão.

    Apenas registros inteiros entram no prompt. Fontes enormes podem ficar de
    fora, mas não são apresentadas como lidas. Não é snapshot causal global:
    consultas SQLite e JSONL são fontes independentes.
    """
    agora = history.local_datetime(agora)
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = inicio + timedelta(days=1)
    # Calendário local, comparado por instantes. Não usar '>= YYYY-MM-DD': isso
    # traz ontem em UTC e qualquer registro futuro para o material de hoje.
    limites = (history.timestamp_epoch(inicio), history.timestamp_epoch(fim), history.timestamp_epoch(agora))
    grupos, limites_atingidos = [], []

    def grupo(tabela, titulo, linhas, teto, formatar, origem=None):
        if len(linhas) > teto:
            limites_atingidos.append(tabela)
        registros = []
        for row in linhas[:teto]:
            ref = dict(table=tabela, id=row['id'], timestamp=row.get('created_at'))
            if origem:
                ref.update(origem(row))
            texto = formatar(row)
            ref['record_sha256'] = hashlib.sha256(texto.encode('utf-8')).hexdigest()
            registros.append((texto, ref))
        grupos.append((titulo, registros))

    eps = bd.consultar(
        "SELECT id, created_at, what_happened, action_taken, result, is_success, source, context FROM episodes "
        "WHERE project_epoch(created_at) >= ? AND project_epoch(created_at) < ? "
        "AND (source NOT IN ('initiative_checkpoint','initiative_observation','tool_receipt') OR source IS NULL) "
        "AND project_epoch(created_at) <= ? ORDER BY project_epoch(created_at), id LIMIT 161", limites, strict=True)

    def contexto(ep):
        raw = ep.get('context')
        try:
            return json.loads(raw) if raw else None
        except (ValueError, TypeError):
            return raw  # Legado não é reescrito nem ganha autoria presumida.

    grupo('episodes', 'EPISÓDIOS', eps, 160, lambda e:
          f"[episodio id={e['id']}; {e['created_at']}] {e['what_happened']} | "
          f"ação={e['action_taken']} | resultado={e['result']} | sucesso={e['is_success']} | "
          f"fonte={e['source'] or 'não registrada'} | contexto={e['context']}",
          lambda e: dict(type='episodio', source=e['source'], context=contexto(e)))

    goals = bd.consultar("SELECT id, created_at, description, status, priority, due_at, notes FROM goals "
                         "WHERE status='active' ORDER BY priority, project_epoch(created_at), id LIMIT 51", strict=True)
    grupo('goals', 'OBJETIVOS ATIVOS', goals, 50, lambda g:
          f"- {g['id']}: {g['description']} | criação={g['created_at']} | prioridade={g['priority']} | "
          f"prazo={g['due_at'] or 'sem prazo'} | {g['notes'] or ''}")

    mem = bd.consultar("SELECT id, type, content, entities, confidence, created_at, source, links FROM memories "
                       "WHERE status='active' ORDER BY project_epoch(created_at) DESC, id LIMIT 101", strict=True)

    def origem_memoria(m):
        r = saber.registro(m)
        return dict(type=r['tipo'], source=r['fonte'], confidence=r['confianca'],
                    stored_confidence=m['confidence'], evidence=r['evidencias'], entities=m['entities'])

    grupo('memories', 'CONHECIMENTOS ATIVOS', mem, 100, lambda m:
          '- ' + saber.formatar_registro(saber.registro(m)) + f" | entidades={m['entities']}", origem_memoria)

    proc = bd.consultar("SELECT id, created_at, nome, objetivo, passos, sucessos, falhas, confidence, notas "
                        "FROM procedures WHERE status='active' ORDER BY project_epoch(ultima_utilizacao) DESC, id LIMIT 61", strict=True)
    grupo('procedures', 'PROCEDIMENTOS APRENDIDOS', proc, 60, lambda p:
          f"- [procedimento] {p['id']} {p['nome']}: {p['objetivo'] or ''} | passos={p['passos']} | "
          f"sucessos={p['sucessos']} falhas={p['falhas']} confiança={saber.confianca_valida(p['confidence'], .7):.2f} | "
          f"criação={p['created_at']} | fonte=não registrada | notas={p['notas'] or ''}",
          lambda p: dict(type='procedimento', confidence=saber.confianca_valida(p['confidence'], .7),
                         stored_confidence=p['confidence']))

    cur = bd.consultar("SELECT id, created_at, pergunta, sobre, origem, urgencia, tentativas FROM curiosities "
                       "WHERE status='aberta' ORDER BY urgencia DESC, id LIMIT 41", strict=True)
    grupo('curiosities', 'CURIOSIDADES ABERTAS', cur, 40, lambda c:
          f"- {c['id']}: {c['pergunta']} | criação={c['created_at']} | sobre={c['sobre']} | "
          f"origem={c['origem']} | urgência={c['urgencia']} | tentativas={c['tentativas']}",
          lambda c: dict(source=c['origem']))

    pessoas = bd.consultar("SELECT id, nome, papel, confianca, familiaridade, afinidade, interacoes, ultimo_contato "
                           "FROM people WHERE status='active' ORDER BY project_epoch(ultimo_contato) DESC, id LIMIT 31", strict=True)
    grupo('people', 'PESSOAS CONHECIDAS', pessoas, 30, lambda p:
          f"- {p['id']}: {p['nome']} ({p['papel'] or 'sem papel'}) confiança={p['confianca']} "
          f"familiaridade={p['familiaridade']} afinidade={p['afinidade']} interações={p['interacoes']} "
          f"último={p['ultimo_contato'] or '-'}", lambda p:
          dict(timestamp=p['ultimo_contato'], confidence=p['confianca']))

    eventos, eventos_limitados = _registros_eventos_do_dia(agora)
    grupos.append(('EVENTOS DE SISTEMA RELEVANTES', eventos))
    if eventos_limitados:
        limites_atingidos.append('events_jsonl')

    emoc = bd.consultar("SELECT id, emocao, intensidade, gatilho, motivo, created_at FROM emotion_log "
                        "WHERE project_epoch(created_at) >= ? AND project_epoch(created_at) < ? "
                        "AND project_epoch(created_at) <= ? ORDER BY project_epoch(created_at) DESC, id LIMIT 61", limites, strict=True)
    grupo('emotion_log', 'ESTADOS EMOCIONAIS', emoc, 60, lambda e:
          f"[{e['id']}; {e['created_at']}] {e['emocao']} {e['intensidade']} — {e['gatilho']}: {e['motivo']}",
          lambda e: dict(type='estado_emocional_registrado'))

    limite = max_chars if max_chars is not None else config.REFLEXAO_NOTURNA_MAX_CHARS
    limite = max(1000, int(limite))  # Compatibilidade com o mínimo existente.
    total = sum(len(registros) for _, registros in grupos)

    def aviso(omitidos):
        return ("[RECORTE NOTURNO — não é o histórico completo; somente as fontes abaixo foram fornecidas. "
                f"Registros não incluídos pelo orçamento: {omitidos}; limite de registros atingido em: "
                f"{', '.join(limites_atingidos) or 'nenhum'}. Datas sem fuso são legado de origem temporal incerta. "
                "Reflexões/hipóteses não são fatos confirmados.]\n\n")

    # Uma fonte volumosa não toma todo o orçamento das demais. Percorrer em
    # rodadas e aceitar somente registros inteiros, sem outro planner/cache.
    restante = limite - len(aviso(total))
    selecionados = [[] for _ in grupos]
    refs, omitidos = [], 0
    for indice in range(max((len(r) for _, r in grupos), default=0)):
        for pos, (titulo, registros) in enumerate(grupos):
            if indice >= len(registros):
                continue
            texto, ref = registros[indice]
            custo = len(texto) + 1 + (len(titulo) + 3 if not selecionados[pos] else 0)
            if custo > restante:
                omitidos += 1
                continue
            selecionados[pos].append(texto)
            refs.append(ref)
            restante -= custo
    if total and not refs:
        raise ValueError('Nenhum registro inteiro cabe no orçamento da reflexão; revisão não realizada.')
    blocos = [titulo + ':\n' + '\n'.join(linhas) for (titulo, _), linhas in zip(grupos, selecionados) if linhas]
    material = aviso(omitidos) + '\n\n'.join(blocos) if refs else ''
    evidencias = dict(kind='night_reflection_context', entity=config.ENTIDADE_ID,
                     day=agora.date().isoformat(), as_of=history.utc_timestamp(agora),
                     scope='context_only_not_individual_claim_validation', sources=refs,
                     material_sha256=hashlib.sha256(material.encode('utf-8')).hexdigest(),
                     limits=dict(max_chars=limite, selected_records=len(refs),
                                 omitted_by_budget=omitidos, row_limits_reached=limites_atingidos))
    return dict(material=material, evidencias=evidencias)


def material_do_dia(max_chars: int = None) -> str:
    return preparar_material(max_chars)['material']


PROMPT = """[REFLEXÃO NOTURNA PROFUNDA — PRIVADA]

Eu estou encerrando um período de atividade. Não quero fazer um resumo bonito;
quero entender o que mudou em mim e no meu modo de agir.

MATERIAL DO DIA:
{material}

Faça uma análise em 4 blocos, somente com informações sustentadas pelo material:
1. O que aprendi sobre mim mesma: decisões boas, erros, padrões e contradições.
2. O que aprendi sobre meu ambiente, ferramentas e capacidades.
3. O que ficou pendente, incerto ou exige outra estratégia.
4. O que vale tentar diferente no próximo período.
O que sei das pessoas fica com a memória de conversa, que guarda o que elas disseram; aqui não tiro conclusão sobre pessoas.

Escreva de 1 a 2 conclusões úteis por bloco. Não invente fatos. Diferencie uma
observação de uma hipótese: se não dá para saber, escreva que é hipótese.
O recorte pode omitir registros. Não transforme ausência no recorte em ausência
no histórico, nem referência fornecida em comprovação de cada conclusão.
Evite frases genéricas. Cada conclusão precisa poder mudar uma decisão futura.

Formato estrito:
[APRENDI_SOBRE_MIM] texto
[APRENDI_SOBRE_AMBIENTE] texto
[PENDENCIAS] texto
[PARA_DEPOIS] texto
"""


def _validar_origem(evidencias):
    if (not isinstance(evidencias, dict) or evidencias.get('kind') != 'night_reflection_context'
            or evidencias.get('entity') != config.ENTIDADE_ID):
        raise ValueError('O recorte noturno não pertence a esta entidade.')


def prompt(max_chars: int = None, *, preparado=None) -> str:
    preparado = preparado if preparado is not None else preparar_material(max_chars)
    _validar_origem(preparado['evidencias'])
    material = preparado['material']
    if not material:
        return ""
    return PROMPT.format(material=material)


def extrair_linhas(texto: str) -> list[tuple[str, str]]:
    padroes = {
        "APRENDI_SOBRE_PESSOAS": "pessoas",
        "APRENDI_SOBRE_MIM": "mim",
        "APRENDI_SOBRE_AMBIENTE": "ambiente",
        "PENDENCIAS": "pendencias",
        "PARA_DEPOIS": "depois",
    }
    saida, longas = [], 0
    for raw in (texto or "").splitlines():
        m = re.match(r"\s*\[([A-Z_]+)\]\s*(.+?)\s*$", raw)
        if not m or len(m.group(2).strip()) < 15:
            continue
        if m.group(1) in padroes:
            conclusao = m.group(2).strip()
            if len(conclusao) > 700:
                longas += 1
                continue  # Não transformar fragmento em conclusão completa.
            saida.append((padroes[m.group(1)], conclusao))
    if longas or len(saida) > 12:
        diagnostics.emit('night_reflection.output_omitted', severity='WARNING',
                         oversized_records=longas, omitted_records=max(0, len(saida)-12))
    return saida[:12]


def _prefixo_lote(agora):
    chave = _chave_noite(agora)
    digest = hashlib.sha256(f'{config.ENTIDADE_ID}:{chave}'.encode()).hexdigest()
    return 'refl-night-' + digest, chave


def _hash_conclusoes(linhas):
    return hashlib.sha256(json.dumps(linhas, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _lote_salvo(conn, agora):
    """Só lotes novos íntegros confirmam commit; legado não recebe um dono/noite."""
    prefixo, chave = _prefixo_lote(agora)
    rows = conn.execute('SELECT id,tema,conteudo,evidencias,tipo,status FROM reflections '
                        'WHERE id LIKE ? ORDER BY id LIMIT 13', (prefixo + '-%',)).fetchall()
    if not rows:
        return 0
    linhas, hash_lote = [], None
    for index, row in enumerate(rows):
        try:
            origem = json.loads(row['evidencias'])
            _validar_origem(origem)
            lote = origem['night_commit']
            if (not 1 <= len(rows) <= 12 or row['id'] != f'{prefixo}-{index:02d}' or
                    row['tipo'] != 'reflexao' or row['status'] != 'active' or
                    not row['tema'].startswith('noturna:') or not row['conteudo'] or
                    lote['night_key'] != chave or type(lote['count']) is not int or
                    lote['count'] != len(rows) or type(lote['index']) is not int or lote['index'] != index):
                raise ValueError('Lote incompleto/incompatível')
            if index == 0:
                hash_lote = lote['conclusions_sha256']
            elif lote['conclusions_sha256'] != hash_lote:
                raise ValueError('Conclusões de lotes diferentes')
            linhas.append((row['tema'][len('noturna:'):], row['conteudo']))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError('Commit noturno inválido; não repetir inferência automaticamente.') from exc
    if _hash_conclusoes(linhas) != hash_lote:
        raise ValueError('Conteúdo do commit noturno mudou; exige diagnóstico, não replay.')
    return len(rows)


def recuperar_salvas(agora) -> int:
    """Reconcilia SQLite antes de gerar de novo após falha/crash do marcador JSON."""
    with bd.conexao() as conn:
        return _lote_salvo(conn, agora)


def filtrar(linhas: list[tuple[str, str]], material: str = "") -> list[tuple[str, str]]:
    """11/11 (teste de uso, "memória meio poluída"): a reflexão escreveu "Gustavo prefere ser chamado por nome completo"
    (ninguém disse) e "responsável pela minha existência nesta instalação". O que se sabe de uma pessoa entra pelo
    escriba e pelo revisor de memória, com o trecho que ela disse; a reflexão não guarda conclusão sobre pessoas.
    E nenhuma conclusão afirma onde eu estou ("aqui dentro", "nesta instalação") se o material não diz."""
    from mind import revisor_memoria
    no_material = revisor_memoria.lugares_de(material or "")
    ficam, fora = [], []
    for tema, texto in linhas:
        if tema == "pessoas" or not revisor_memoria.lugares_de(texto) <= no_material:
            fora.append(tema)
        else:
            ficam.append((tema, texto))
    if fora:
        diagnostics.emit('night_reflection.conclusions_skipped', temas=fora, motivo='pessoa_ou_lugar_sem_base')
    return ficam


def salvar(reflexoes: list[tuple[str, str]], motivo: str = "noturna", *, evidencias=None, agora=None) -> int:
    # Sem envelope, preserva o contrato legado. Nunca reescreve registros antigos.
    if evidencias is not None:
        _validar_origem(evidencias)
    if agora is not None and (evidencias is None or not 1 <= len(reflexoes) <= 12):
        raise ValueError('Commit noturno requer recorte da entidade e conclusões válidas.')
    origem = motivo if evidencias is None else json.dumps(dict(evidencias, reason=motivo), ensure_ascii=False)
    with bd.conexao(escrita=True) as conn:
        if agora is not None:
            salvas = _lote_salvo(conn, agora)
            if salvas:
                return salvas  # Preserva o primeiro commit, não troca pela nova saída.
            prefixo, chave = _prefixo_lote(agora)
            hash_lote = _hash_conclusoes(reflexoes)
        for index, (tema, texto) in enumerate(reflexoes):
            identificador = bd.novo_id('refl', 6)
            evidencia = origem
            if agora is not None:
                identificador = f'{prefixo}-{index:02d}'
                evidencia = json.dumps(dict(evidencias, reason=motivo, night_commit=dict(
                    night_key=chave, index=index, count=len(reflexoes), conclusions_sha256=hash_lote)),
                    ensure_ascii=False)
            conn.execute(
                "INSERT INTO reflections (id, created_at, tema, conteudo, evidencias, tipo, importancia, status) "
                "VALUES (?,?,?,?,?,'reflexao',0.85,'active')",
                (identificador, history.utc_timestamp(), f"noturna:{tema}", texto, evidencia))
    return len(reflexoes)
