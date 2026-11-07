"""Limpeza única da fala, sem dependências de reprodução ou modelos."""
import re

_STAGE = re.compile(
    r"(?:\*{1,3}|\(|\[|\{)\s*"
    r"(?:sorri(?:ndo|r)?|sorriso|ri|rindo|risos?|suspira(?:ndo|r)?|suspiro|bufa|bufando|"
    r"engole em seco|chora(?:ndo)?|soluça(?:ndo)?|geme(?:ndo)?|grita(?:ndo)?|"
    r"sussurra(?:ndo)?|murmura(?:ndo)?|revira os olhos|encolhe os ombros|"
    r"olha para|olhando para|faz uma pausa)\s*"
    r"(?:\*{1,3}|\)|\]|\})", re.I)
_ALONE = re.compile(
    r"(?<![\w])(?:\*{1,3})?\s*(?:risos?|suspira|suspiro|bufa|chora|soluça|sussurra)\s*"
    r"(?:\*{1,3})?(?=[,.!?;:]|$)", re.I)


def clean_for_speech(text):
    text = re.sub(r'</?answer>', '', str(text or ''))
    text = re.sub(r"```.*?```", " bloco de código ", str(text or ""), flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = _ALONE.sub(" ", _STAGE.sub(" ", text))
    text = re.sub(r"\[(CICLO INTERNO|SISTEMA|AGORA|SENSORES|AGENDA REAL)[^\]]*\]", "", text)
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[\[imagem:[0-9a-f]{12}\]\]", "", text)  # anexo do chat, não se lê em voz alta
    text = re.sub(r"https?://\S+", " link ", text)
    text = re.sub(r"[*#_~`>]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class SentenceBuffer:
    """Só libera prefixos completos e irrevogáveis de um stream append-only.

    Mantém código/markdown aberto, números e abreviações no buffer. Se o backend
    substituir um prefixo já emitido, o chamador cancela, em vez de falar uma
    revisão como se fosse continuação. O fragmento final só sai após `done`.
    """
    def __init__(self):
        self.text = ''
        self.offset = 0

    def push(self, text, *, final=False):
        if not text.startswith(self.text):
            raise ValueError('Stream de fala revisou prefixo; cancelar áudio pendente.')
        self.text = text
        sentences = []
        base, cursor = self.offset, self.offset
        for boundary in re.finditer(r'[.!?]+["”\')\]]*(?=\s+\S)', text[base:]):
            end = base + boundary.end()
            prefix = text[:end]
            if prefix.count('```') % 2 or prefix.count('`') % 2:
                continue
            if prefix.count('[')!=prefix.count(']') or prefix.count('(')!=prefix.count(')'):
                continue
            if re.search(r'(?:\b(?:sr|sra|dr|dra|prof|etc)|\b[A-Z])\.$', prefix, re.I):
                continue
            sentence = text[cursor:end].strip()
            if sentence:
                sentences.append(sentence)
                cursor = end
        self.offset = cursor
        if final and text[self.offset:].strip():
            sentences.append(text[self.offset:].strip())
            self.offset = len(text)
        return sentences


def sentence_chunks(text):
    return SentenceBuffer().push(text, final=True)
