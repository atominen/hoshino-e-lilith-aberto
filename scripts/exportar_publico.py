"""Gera a cópia pública e segura do projeto (pedido humano 07/11/2026).

Decisão do Gustavo: código + documentação + o último banco de treino (v6); o nome dele pode aparecer; a referência às
obras de partida fica. Segredos nunca: tokens, código de pareamento, chaves, e-mails, memórias, conversas, diários,
pesos, dados de execução.

Como funciona (falha fechada):
1. a cópia sai do que está COMMITADO (`git archive HEAD`), nunca da árvore de trabalho;
2. entra o banco v6 compilado (`laboratorio-local/banco_treino_v6/` e `pacote_identidade_v6/`);
3. o README público (`docs/publico/README_PUBLICO.md`) substitui o README do repositório privado;
4. uma varredura final procura e-mail, chave, token (inclusive o VALOR dos arquivos de segredo locais), pasta de
   runtime/memória, banco de dados que não seja o de treino, áudio e arquivo grande. Achou algo: para e não publica.

Publicar é outro passo, manual e com aval humano (gh repo create ... --public). Uso:
  python3 -I scripts/exportar_publico.py [destino]     (padrão: ~/hoshino-e-lilith-aberto)
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / 'hoshino-e-lilith-aberto'
BANCO = RAIZ / 'laboratorio-local' / 'banco_treino_v6' / 'banco.sqlite3'
PACOTE = RAIZ / 'laboratorio-local' / 'pacote_identidade_v6'
README = RAIZ / 'docs' / 'publico' / 'README_PUBLICO.md'
LIMITE_ARQUIVO = 25 * 1024 ** 2

EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
# Endereços que não são de pessoa: noreply, exemplos, coautoria dos commits e UUID de applet do Cinnamon.
EMAIL_OK = re.compile(r'@(?:users\.noreply\.github\.com|example\.(?:com|org)|exemplo\.(?:com|org)|anthropic\.com|'
                      r'cinnamon\.org)$', re.I)
SEGREDO = re.compile(
    r'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|\bsk_[A-Za-z0-9]{20,}|\bsk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|'
    r'xox[bpas]-[A-Za-z0-9-]{10,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|'
    r'discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+|\b[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27,}\b|'
    r'Bearer\s+[A-Za-z0-9._-]{24,}')
# app/memory/ é código; memória de verdade mora em entidades/<nome>/memory e em runtime/.
PROIBIDO_CAMINHO = re.compile(r'(^|/)(runtime|diarios?|gravacoes|recordings)(/|$)|(^|/)entidades/[^/]+/memory(/|$)|'
                              r'(^|/)\.env$|'
                              r'\.(?:db|wav|mp3|ogg|flac|gguf|safetensors|bin|pt|pth)$', re.I)


_NOME_SECRETO = re.compile(r'KEY|TOKEN|SECRET|PASS|SENHA|PWD|CREDENTIAL|WEBHOOK', re.I)
_PULAR = ('site-packages', 'venv', 'node_modules', '__pycache__', 'workspace')


def _segredos_locais() -> dict[str, str]:
    """Valores reais dos segredos desta instalação, para garantir que nenhum aparece na cópia:
    o conteúdo dos arquivos de token, as variáveis de nome secreto dos .env e os valores dos JSON de segredo."""
    import json
    valores = {}
    for base in (RAIZ / 'compartilhado' / 'runtime', RAIZ / 'entidades'):
        if not base.is_dir():
            continue
        for p in base.rglob('*'):
            if not p.is_file() or any(parte in _PULAR for parte in p.parts):
                continue
            nome = p.name.lower()
            try:
                texto = p.read_text(encoding='utf-8', errors='ignore') if p.stat().st_size < 65536 else ''
            except OSError:
                continue
            origem = str(p.relative_to(RAIZ))
            if 'token' in nome and p.suffix in ('', '.token', '.txt', '.key'):
                valor = texto.strip()
                if len(valor) >= 12:
                    valores[valor] = origem
            elif nome.endswith('.env'):
                for linha in texto.splitlines():
                    if '=' in linha and not linha.lstrip().startswith('#'):
                        chave, valor = linha.split('=', 1)
                        valor = valor.strip().strip('"\'')
                        if _NOME_SECRETO.search(chave) and len(valor) >= 12:
                            valores[valor] = origem
            elif 'secret' in nome and nome.endswith('.json'):
                try:
                    dados = json.loads(texto)
                except ValueError:
                    continue
                pilha = [dados]
                while pilha:
                    x = pilha.pop()
                    if isinstance(x, dict):
                        pilha.extend(x.values())
                    elif isinstance(x, list):
                        pilha.extend(x)
                    elif isinstance(x, str) and len(x) >= 12:
                        valores[x] = origem
    return valores


def exportar():
    sujo = subprocess.run(['git', '-C', str(RAIZ), 'status', '--porcelain', '--untracked-files=no'],
                          capture_output=True, text=True, check=True).stdout.strip()
    if sujo:
        print('Aviso: há mudanças não commitadas; a cópia usa só o que está commitado (HEAD).')
    DESTINO.mkdir(parents=True, exist_ok=True)
    for item in DESTINO.iterdir():  # recomeça limpo, preservando o histórico git da cópia pública
        if item.name == '.git':
            continue
        shutil.rmtree(item) if item.is_dir() and not item.is_symlink() else item.unlink()
    arquivo = subprocess.run(['git', '-C', str(RAIZ), 'archive', 'HEAD'], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(arquivo)) as tar:
        tar.extractall(DESTINO, filter='data')
    (DESTINO / 'README.md').write_text(README.read_text(encoding='utf-8'), encoding='utf-8')
    destino_banco = DESTINO / 'banco_treino_v6'
    (destino_banco / 'pacote').mkdir(parents=True, exist_ok=True)
    if not BANCO.is_file() or not PACOTE.is_dir():
        raise SystemExit('Banco v6 não encontrado: rode scripts/montar_banco_v6.py antes.')
    shutil.copy2(BANCO, destino_banco / 'banco.sqlite3')
    for p in sorted(PACOTE.iterdir()):
        if p.is_file() and not p.name.startswith('.'):
            shutil.copy2(p, destino_banco / 'pacote' / p.name)
    (destino_banco / 'README.md').write_text(
        '# Banco de treinamento v6 (compilado)\n\n'
        'Gerado por `scripts/montar_banco_v6.py` a partir de `laboratorio/identidade/v5` e `v6`. Rascunho: ainda não\n'
        'usado em treino. Formato e princípios em [`laboratorio/identidade/v6/README.md`](../laboratorio/identidade/v6/README.md).\n\n'
        '- `banco.sqlite3`: tabelas `exemplos`, `aspectos`, `fontes`, `meta` e a view `resumo`.\n'
        '- `pacote/<entidade>_train|validation|holdout.jsonl`: o que o treinador atual aceita (texto, até 256 tokens).\n'
        '- `pacote/<entidade>_completo.jsonl`: com papéis `system`/`tool` e `tool_calls`.\n'
        '- `pacote/<entidade>_preferencias.jsonl`: pares `chosen`/`rejected` (os `rejected` incluem erros reais do 9B).\n'
        '- `pacote/RELATORIO.md`: contagens por entidade e aspecto.\n', encoding='utf-8')


def varrer() -> list[str]:
    achados = []
    segredos = _segredos_locais()
    for p in sorted(DESTINO.rglob('*')):
        if '.git' in p.relative_to(DESTINO).parts or not p.is_file():
            continue
        rel = str(p.relative_to(DESTINO))
        if p.stat().st_size > LIMITE_ARQUIVO:
            achados.append(f'{rel}: arquivo grande ({p.stat().st_size // 1024 ** 2} MiB)')
        if PROIBIDO_CAMINHO.search(rel) and not rel.endswith('.example'):
            achados.append(f'{rel}: caminho proibido (runtime, memória, áudio, pesos ou .env)')
        if rel.endswith(('.sqlite3', '.sqlite')) and rel != 'banco_treino_v6/banco.sqlite3':
            achados.append(f'{rel}: banco de dados fora do banco de treino')
        dados = p.read_bytes()
        texto = dados.decode('utf-8', errors='ignore')
        for m in EMAIL.finditer(texto):
            if not EMAIL_OK.search(m.group(0)):
                achados.append(f'{rel}: e-mail {m.group(0)}')
        for m in SEGREDO.finditer(texto):
            achados.append(f'{rel}: padrão de segredo {m.group(0)[:12]}…')
        for valor, origem in segredos.items():
            if valor in texto:
                achados.append(f'{rel}: contém o valor do segredo local de {origem}')
    return achados


def main():
    exportar()
    achados = varrer()
    arquivos = [p for p in DESTINO.rglob('*') if p.is_file() and '.git' not in p.relative_to(DESTINO).parts]
    total = sum(p.stat().st_size for p in arquivos)
    print(f'Cópia pública em {DESTINO}: {len(arquivos)} arquivos, {total / 1024 ** 2:.1f} MiB')
    if achados:
        print('\nBLOQUEADO — não publicar:', *sorted(set(achados))[:80], sep='\n- ')
        sys.exit(1)
    print('Varredura: nada encontrado (e-mail, chave, token, valor de segredo local, runtime, memória, áudio, pesos).')


if __name__ == '__main__':
    os.umask(0o022)
    main()
