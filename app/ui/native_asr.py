"""Estado limitado de uma fala nativa. Sem Qt, I/O, motor ou mensagens de LLM."""
from collections import deque
from dataclasses import dataclass
import time
import uuid


@dataclass(frozen=True)
class Packet:
    pcm: bytes
    part: int
    revision: int
    preview: bool


class LiveTranscript:
    def __init__(self,entity,session_id,scope,mode,auto_send):
        self.id=uuid.uuid4().hex;self.entity=entity;self.session_id=session_id
        self.scope=scope;self.mode=mode;self.auto_send=bool(auto_send)
        self.part=0;self.revision=0;self.ended=False;self.discarded=False;self.failed=False
        self.waiting=deque();self.latest=None;self.inflight=None;self.finals={};self.tentative={};self.hypothesis=''
        self.last_preview_at=float('-inf');self.last_preview_bytes=0;self.submission_id=uuid.uuid4().hex
        self.sent=False

    def _packet(self,pcm,preview):
        self.revision+=1
        return Packet(bytes(pcm),self.part,self.revision,preview)

    def preview(self,pcm,now=None):
        now=time.monotonic() if now is None else now
        if self.ended or self.discarded or self.failed:return
        if len(pcm)-self.last_preview_bytes<32000 or now-self.last_preview_at<1:return
        self.latest=self._packet(pcm,True);self.last_preview_at=now;self.last_preview_bytes=len(pcm)

    def seal(self,pcm,ended=False):
        if self.ended or self.discarded or self.failed:return
        self.latest=None
        if self.hypothesis:self.tentative[self.part]=self.hypothesis
        self.hypothesis=''
        if pcm:
            if len(pcm)<6400:pcm=bytes(pcm)+bytes(6400-len(pcm))  # preservar cauda <200 ms, sem omiti-la
            if len(self.waiting)>=4 or self.part>=64:
                self.failed=True;raise BufferError('Fila de fala cheia; envio incompleto bloqueado.')
            self.waiting.append(self._packet(pcm,False));self.part+=1;self.last_preview_bytes=0
        if ended:self.end()

    def end(self):
        self.ended=True;self.latest=None

    def discard(self):
        self.discarded=True;self.latest=None;self.waiting.clear();self.hypothesis='';self.tentative.clear();self.finals.clear()

    def take(self):
        if self.inflight is not None or self.discarded or self.failed:return None
        packet=self.waiting.popleft() if self.waiting else self.latest
        if packet is self.latest:self.latest=None
        self.inflight=packet
        return packet

    def complete(self,packet,job_id,result,error=None):
        if self.inflight is not packet:return
        self.inflight=None
        if self.discarded:return
        text=str((result or {}).get('text') or '').strip()
        if not packet.preview:
            if error or not text or not job_id:self.failed=True;return
            self.finals[packet.part]=(job_id,text)
        elif not error:
            if packet.part==self.part and not self.ended:self.hypothesis=text
            elif packet.part<self.part and packet.part not in self.finals:self.tentative[packet.part]=text

    def text(self):
        parts=[self.finals[i][1] if i in self.finals else self.tentative[i] for i in sorted(self.finals.keys()|self.tentative.keys())]
        if self.hypothesis:parts.append(self.hypothesis)
        return ' '.join(parts)

    def jobs(self):return [self.finals[i][0] for i in sorted(self.finals)]

    def ready(self):
        return (self.ended and not self.discarded and not self.failed and self.part>0 and
                self.inflight is None and not self.waiting and len(self.finals)==self.part)

    def metadata(self,packet):
        return dict(id=self.id,part=packet.part,revision=packet.revision,preview=packet.preview,
                    session_id=self.session_id,scope=self.scope)
