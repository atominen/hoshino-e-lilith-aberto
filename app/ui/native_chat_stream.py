"""Projeção de prévias no chat; não envia mensagens nem controla áudio."""


def merge_previews(conversation, streams, *, entity, session, scope,
                   read_only=False, query='', before=0):
    result = list(conversation)
    if read_only or query or before or not session.get('id') or scope not in {'direct', 'global'}:
        return result
    completed = set()
    for message in conversation:
        meta = message.get('metadata') or {}
        if isinstance(meta, dict) and isinstance(meta.get('text_streams'), list):
            completed.update(identifier for identifier in meta['text_streams'] if isinstance(identifier, str))
    newest = {}
    for row in streams:
        if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                or row.get('entity') not in {'hoshino', 'lilith'} or not isinstance(row.get('text'), str)
                or not row['text'] or len(row['text']) > 12000 or type(row.get('revision')) is not int
                or row.get('status') not in {'queued', 'running', 'done', 'error', 'interrupted'}):
            continue
        if row['id'] in completed or row.get('final_message_id') in {m.get('id') for m in conversation}:
            continue
        if row.get('chat_scope') != scope:
            continue
        if scope == 'direct':
            if row['entity'] != entity or row.get('conversation_session_id') != session['id']:
                continue
        elif row.get('room_day') != session.get('local_date'):
            continue
        old = newest.get(row['id'])
        if old is None or row['revision'] > old['revision']:
            newest[row['id']] = row
    for row in list(newest.values())[:8]:
        status = ('incompleta · geração interrompida' if row['status'] in {'error', 'interrupted'} else
                  'aguardando atualização da conexão' if row.get('stale') else
                  'confirmando publicação' if row['status'] == 'done' else 'gerando')
        result.append(dict(id=row['id'], sender=row['entity'], recipient='usuario', text=row['text'],
                           kind='chat_preview', metadata=dict(chat_scope=scope, preview=True,
                           processing=dict(status=status), source='prévia')))
    return result


def _anchors(document):
    result = {}
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                for name in fragment.charFormat().anchorNames():
                    if name.startswith('chat-'): result.setdefault(name, fragment.position())
            iterator += 1
        block = block.next()
    return result


def _bookmark(anchors, position):
    previous = [(offset, name) for name, offset in anchors.items() if offset <= position]
    if not previous: return None, position
    offset, name = max(previous)
    return name, position - offset


def _restore(anchors, bookmark, end):
    name, offset = bookmark
    if name is None: return min(offset, end)
    if name not in anchors: return None
    start = anchors[name]
    next_start = min((value for value in anchors.values() if value > start), default=end + 1)
    return min(start + offset, next_start - 1, end)


def update_chat_document(browser, rendered: str) -> None:
    """Preserva leitura/seleção; só acompanha o fim quando já estava nele."""
    vertical, horizontal = browser.verticalScrollBar(), browser.horizontalScrollBar()
    cursor = browser.textCursor()
    old_anchors = _anchors(browser.document())
    position, anchor = _bookmark(old_anchors, cursor.position()), _bookmark(old_anchors, cursor.anchor())
    selected = cursor.selectedText()
    top = browser.cursorForPosition(browser.viewport().rect().topLeft())
    top_bookmark, top_y = _bookmark(old_anchors, top.position()), browser.cursorRect(top).top()
    old_vertical, old_horizontal = vertical.value(), horizontal.value()
    follow = old_vertical >= vertical.maximum() - 8 and not cursor.hasSelection()
    browser.setHtml(rendered)
    restored = browser.textCursor()
    end = max(0, browser.document().characterCount() - 1)
    new_anchors = _anchors(browser.document())
    new_anchor, new_position = _restore(new_anchors, anchor, end), _restore(new_anchors, position, end)
    if new_anchor is not None and new_position is not None:
        restored.setPosition(new_anchor)
        restored.setPosition(new_position, restored.KeepAnchor)
        # Conteúdo substituído/removido não deve selecionar outra frase por
        # acidente. Crescimento de outra mensagem conserva a seleção exata.
        if selected and restored.selectedText() != selected: restored.clearSelection()
    else:
        restored.clearSelection()
    browser.setTextCursor(restored)
    horizontal.setValue(old_horizontal)
    if follow:
        vertical.setValue(vertical.maximum())
    else:
        new_top = _restore(new_anchors, top_bookmark, end)
        if new_top is None:
            vertical.setValue(old_vertical)
        else:
            probe = browser.textCursor(); probe.setPosition(new_top)
            vertical.setValue(vertical.value() + browser.cursorRect(probe).top() - top_y)
