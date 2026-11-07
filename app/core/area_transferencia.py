"""Área de transferência compartilhada (pedido humano 06/11).

Tudo o que a pessoa copia fica salvo sozinho em ``compartilhado/area_de_transferencia``, sem botão de importar.
Quem grava é a Central (a janela recebe o aviso do sistema a cada cópia e manda ao backend). As entidades só
leem, quando pedirem, pela ferramenta ``area_de_transferencia``.

- Itens: ``itens/<data>-<hora>-<sha12>.txt|png`` e um índice JSONL (o mais novo por último).
- Cópia repetida (mesmo conteúdo do último item) não duplica.
- Guarda os 300 itens mais novos, até 256 MiB. O mais antigo sai primeiro.
- Senha copiada de gerenciador que marca a cópia como segredo (x-kde-passwordManagerHint) não chega aqui:
  a Central descarta antes de enviar.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

MAX_TEXT = 1024 ** 2
MAX_IMAGE = 8 * 1024 ** 2
MAX_PIXELS = 16_000_000
MAX_ITEMS = 300
MAX_BYTES = 256 * 1024 ** 2
READ_CHARS = 12_000
KINDS = {'texto': '.txt', 'imagem': '.png'}


def folder(root) -> Path:
    return Path(root) / 'compartilhado/area_de_transferencia'


@contextlib.contextmanager
def _locked(root):
    base = folder(root)
    (base / 'itens').mkdir(parents=True, exist_ok=True)
    with (base / '.lock').open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield base


def _read_index(base: Path) -> list[dict]:
    rows = []
    try:
        lines = (base / 'indice.jsonl').read_text(encoding='utf-8').splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('kind') in KINDS and isinstance(row.get('file'), str):
            rows.append(row)
    return rows


def _write_index(base: Path, rows: list[dict]) -> None:
    fd, temp = tempfile.mkstemp(prefix='.indice-', dir=base)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
            out.flush(); os.fsync(out.fileno())
        os.replace(temp, base / 'indice.jsonl')
    finally:
        Path(temp).unlink(missing_ok=True)


def _png_size(data: bytes):
    if not data.startswith(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'):
        return None
    return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')


def _preview(text: str) -> str:
    one = ' '.join(text.split())
    return one[:160] + ('…' if len(one) > 160 else '')


def save(root, kind: str, data: bytes, *, now: float | None = None, origem: str = 'pc1') -> dict:
    """Grava uma cópia. Só a Central chama. Devolve o item, ou duplicate=True se for igual ao último."""
    if kind not in KINDS:
        raise ValueError('Tipo de cópia desconhecido.')
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValueError('Cópia vazia.')
    data = bytes(data)
    extra = {}
    if kind == 'texto':
        if len(data) > MAX_TEXT:
            raise ValueError('Texto copiado acima de 1 MiB.')
        text = data.decode('utf-8')
        if not text.strip():
            raise ValueError('Cópia vazia.')
        extra = dict(chars=len(text), preview=_preview(text))
    else:
        size = _png_size(data)
        if len(data) > MAX_IMAGE or not size or not 0 < size[0] * size[1] <= MAX_PIXELS:
            raise ValueError('Imagem copiada deve ser PNG de até 8 MiB e 16 milhões de pixels.')
        extra = dict(width=size[0], height=size[1])
    digest = hashlib.sha256(data).hexdigest()
    now = time.time() if now is None else now
    with _locked(root) as base:
        rows = _read_index(base)
        if rows and rows[-1].get('sha256') == digest:
            return dict(rows[-1], duplicate=True)
        if shutil.disk_usage(base).free < len(data) + 256 * 1024 ** 2:
            raise ValueError('Espaço insuficiente para guardar a cópia.')
        stamp = datetime.fromtimestamp(now).strftime('%Y%m%d-%H%M%S')
        name = f'{stamp}-{digest[:12]}{KINDS[kind]}'
        fd, temp = tempfile.mkstemp(prefix='.copia-', dir=base / 'itens')
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(data); out.flush(); os.fsync(out.fileno())
            os.replace(temp, base / 'itens' / name)
        finally:
            Path(temp).unlink(missing_ok=True)
        origem = origem if origem in {'pc1', 'pc2'} else 'pc1'  # qual painel mandou (06/11: o PC2 também copia)
        row = dict(id=digest[:12], ts=now, kind=kind, file=name, bytes=len(data), sha256=digest, origem=origem, **extra)
        rows.append(row)
        # Retenção: itens mais novos primeiro, até o limite de quantidade e de espaço.
        kept, total = [], 0
        for item in reversed(rows):
            if len(kept) < MAX_ITEMS and total + item.get('bytes', 0) <= MAX_BYTES:
                kept.append(item); total += item.get('bytes', 0)
            else:
                (base / 'itens' / Path(item['file']).name).unlink(missing_ok=True)
        _write_index(base, list(reversed(kept)))
        return row


def items(root) -> list[dict]:
    """Do mais novo para o mais antigo, só itens cujo arquivo existe."""
    base = folder(root)
    return [r for r in reversed(_read_index(base)) if (base / 'itens' / Path(r['file']).name).is_file()]


def _when(ts) -> str:
    return datetime.fromtimestamp(float(ts)).strftime('%d/%m %H:%M')


def describe(row: dict) -> str:
    onde = f" · copiado no {row['origem'].upper()}" if row.get('origem') else ''
    if row['kind'] == 'texto':
        return f"[{row['id']}] {_when(row['ts'])}{onde} · texto, {row.get('chars', 0)} caracteres · {row.get('preview', '')}"
    return f"[{row['id']}] {_when(row['ts'])}{onde} · imagem {row.get('width')}x{row.get('height')}"


def listar(root, quantidade: int = 10) -> str:
    rows = items(root)
    if not rows:
        return 'A área de transferência compartilhada está vazia: nada foi copiado desde que ela passou a ser guardada.'
    quantidade = max(1, min(int(quantidade or 10), 50))
    linhas = [describe(r) for r in rows[:quantidade]]
    return (f'Cópias guardadas: {len(rows)} (mais nova primeiro). Para ler uma, use operacao=ler com o id.\n'
            + '\n'.join(linhas))


def ler(root, item: str = '', inbox: str | os.PathLike | None = None) -> str:
    """Texto volta inteiro (até 12 mil caracteres). Imagem vai para a caixa de entrada da entidade para análise visual."""
    rows = items(root)
    if not rows:
        return 'Não existe cópia guardada ainda.'
    key = str(item or '').strip().lower()
    if key in {'', 'ultimo', 'último', 'ultima', 'última', '1'}:
        row = rows[0]
    elif key.isdigit() and 1 <= int(key) <= len(rows):
        row = rows[int(key) - 1]
    else:
        row = next((r for r in rows if r['id'] == key), None)
        if row is None:
            return f"Não existe cópia com id '{item}'. Use operacao=listar para ver as guardadas."
    path = folder(root) / 'itens' / Path(row['file']).name
    if row['kind'] == 'texto':
        text = path.read_text(encoding='utf-8', errors='replace')
        cut = '' if len(text) <= READ_CHARS else f'\n...[cortado: {len(text) - READ_CHARS} caracteres a mais]'
        return f"Cópia [{row['id']}] de {_when(row['ts'])} (texto, {len(text)} caracteres):\n\n{text[:READ_CHARS]}{cut}"
    if inbox is None:
        return f"Cópia [{row['id']}] é uma imagem {row.get('width')}x{row.get('height')}; não há caixa de entrada para abri-la."
    target_dir = Path(inbox)
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}-copiado-{row['id']}.png"
    shutil.copyfile(path, target_dir / name)
    return (f"Cópia [{row['id']}] de {_when(row['ts'])} é uma imagem {row.get('width')}x{row.get('height')}. "
            f"Coloquei na minha caixa de entrada como {name}; para ver, use observar_imagem_recebida com nome={name}.")
