"""Sondas de revisão: funções atuais via AST, SQLite em RAM, sem importar o app.

Não é benchmark de LLM nem suíte de aprovação. Os resultados descrevem o
comportamento atual, inclusive defeitos; não congelam esse comportamento como
expectativa correta. Não abre bancos, configurações ou identidades reais.
"""
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]
HASHES = {}


def extract(relative, names, namespace):
    path = ROOT / relative
    source = path.read_text()
    HASHES[relative] = hashlib.sha256(source.encode()).hexdigest()
    selected = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in names for t in node.targets
        ):
            selected.append(node)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    missing = set(names) - namespace.keys()
    if missing:
        raise RuntimeError(f'Contrato mudou: nomes ausentes {sorted(missing)}')


class FixtureConnection(sqlite3.Connection):
    def close(self):
        # recall fecha sua conexão; manter apenas esta conexão :memory: para
        # inspecionar o efeito, e fechá-la explicitamente ao terminar.
        pass


def main():
    env = dict(json=json, math=math, re=re, sqlite3=sqlite3,
               unicodedata=unicodedata, uuid=uuid, datetime=datetime, timezone=timezone,
               ZoneInfo=ZoneInfo, ZoneInfoNotFoundError=ZoneInfoNotFoundError,
               config=SimpleNamespace(LOCAL_TIMEZONE='America/Sao_Paulo'))
    extract('app/core/history.py', {'local_timezone','local_now','local_datetime','elapsed_seconds'}, env)
    extract('app/memory/records.py', {
        'TIPOS_VALIDOS', 'normalizar', 'confianca_valida', 'categoria',
        'render_model', 'registro', 'CARD_KINDS', 'CARD_TIERS', 'card_targets', 'card_priorities'}, env)
    # This probe tests direct-context ranking; audience contracts have their own isolated group.
    env['audience']=SimpleNamespace(visible=lambda *a,**kw:True)
    extract('app/config.py', {'PESOS_RECALL'}, env)
    extract('app/memory/sqlite/init_db.py', {'TABELAS'}, env)
    extract('app/memory/knowledge_store.py', {
        'PALAVRAS_VAZIAS', '_now', '_normalizar', '_tokens', '_semelhanca',
        '_entidades_lista', 'remember', '_recencia', 'recall',
        '_concept_source_texts', 'formatar_registro', '_source_authorship'}, env)
    db = sqlite3.connect(':memory:', factory=FixtureConnection)
    try:
        for table in ('memories', 'properties', 'episodes', 'reflections'):
            db.execute(env['TABELAS'][table])
        env['_conn'] = lambda: db
        env['_evidencias_turno'] = lambda evidence: evidence or []
        # Distância sintética deliberadamente ruim. Não representa um embedding
        # medido; demonstra o limiar do ranking com essa entrada controlada.
        env['vetor'] = SimpleNamespace(buscar=lambda *a: [])
        a = 'A pessoa gosta de café brasileiro forte sem açúcar pela manhã.'
        b = 'A pessoa gosta de café brasileiro forte sem açúcar pela noite.'
        for text in (a, b):
            env['remember'](text, entidades=['pessoa'], tipo='preferencia',
                            fonte='fixture', evidencias=[], conexao=db)
        conflict = dict(similarity=env['_semelhanca'](a, b),
                        rows=db.execute('SELECT content,status FROM memories ORDER BY rowid').fetchall())
        db.execute('DELETE FROM memories')
        env['remember']('A bicicleta é vermelha.', entidades=['bicicleta'],
                        confianca=1, fonte='fixture', conexao=db)
        mid = db.execute('SELECT id FROM memories').fetchone()[0]
        db.execute('UPDATE memories SET access_count=10')
        env['vetor'] = SimpleNamespace(buscar=lambda *a: [{'id': mid, 'distancia': 100.0}])
        irrelevant = env['recall']('Qual a capital da Mongólia?', estruturado=True)
        extract('app/mind/scribe.py', {
            'ELOGIO', 'CRITICA', 'DISCORDANCIA', 'AFETO', 'BRINCADEIRA',
            '_texto_autoral', 'evidencias_do_comportamento', 'reacao_do_usuario'}, env)
        samples = ['O comando está errado?', 'A frase citada era: "senti falta".',
                   'Não entendi. Pode repetir?']
        output = dict(
            method='AST de funções atuais; SQLite :memory:; vetor simulado; sem LLM',
            source_sha256=HASHES,
            coexistence=conflict,
            irrelevant_recall=dict(query='Qual a capital da Mongólia?',
                                   vector_distance=100.0,
                                   returned=[r['content'] for r in irrelevant]),
            behavioral_signals={s: env['evidencias_do_comportamento'](s) for s in samples},
            reaction_to_software_bug=env['reacao_do_usuario']('O programa está errado e não funciona.'),
            recency_same_instant=dict(
                local_naive=env['_recencia'](datetime.now().isoformat()),
                utc_aware=env['_recencia'](datetime.now(timezone.utc).isoformat())),
        )
        print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        sqlite3.Connection.close(db)


if __name__ == '__main__':
    main()
