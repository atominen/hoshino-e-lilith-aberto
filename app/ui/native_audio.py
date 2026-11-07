"""PCM/segmentação da UI. Sem modelo, rede, estado mental ou captura no import."""
import array
import io
import math
import sys
import wave

RATE=16000
FRAME_BYTES=1600  # 50 ms mono int16


def pulse_volume(percent):
    if type(percent) is not int or not 0<=percent<=100:raise ValueError('Volume deve estar entre 0 e 100%.')
    return round(percent*65536/100)


def owned_sink_input(rows,pid,stream_name):
    """Não ajustar saída global ou stream de outro aplicativo/PID reutilizado."""
    if not isinstance(rows,list) or type(pid) is not int or pid<=0 or not stream_name:return None
    matches=[]
    for row in rows:
        if not isinstance(row,dict):continue
        properties=row.get('properties') or {}
        if not isinstance(properties,dict):continue
        if str(properties.get('application.process.id'))!=str(pid) or properties.get('media.name')!=stream_name:continue
        index=row.get('index')
        if type(index) is int and index>=0:matches.append(index)
    return matches[0] if len(matches)==1 else None


def rms(pcm):
    samples=array.array('h');samples.frombytes(pcm[:len(pcm)//2*2])
    if sys.byteorder!='little':samples.byteswap()
    return math.sqrt(sum(x*x for x in samples)/len(samples))/32768 if samples else 0.0


def wav_bytes(pcm):
    if not RATE*2*.2<=len(pcm)<=RATE*2*45 or len(pcm)%2:raise ValueError('Trecho deve durar entre 0,2 e 45 segundos.')
    out=io.BytesIO()
    with wave.open(out,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(RATE);wav.writeframes(pcm)
    return out.getvalue()


class Segmenter:
    """Gate energético; não identifica pessoa nem inventa conteúdo/transcrição."""
    def __init__(self,mode='command',threshold=.012,silence_ms=900,segment_seconds=8):
        if mode not in {'command','detection'}:raise ValueError('Escolha comando ou detecção.')
        self.mode=mode;self.threshold=threshold;self.silence_frames=max(1,silence_ms//50)
        self.maximum=45*RATE*2
        self.pending=bytearray();self.buffer=bytearray();self.pre=bytearray();self.silent=0;self.voiced=False;self.speaking=False;self.events=[]
    def feed(self,data):
        self.pending.extend(data);segments=[];level=0;self.events=[]
        while len(self.pending)>=FRAME_BYTES:
            frame=bytes(self.pending[:FRAME_BYTES]);del self.pending[:FRAME_BYTES]
            level=rms(frame);voice=level>=self.threshold
            if self.mode=='detection' and not self.buffer and not self.speaking:
                self.pre.extend(frame);self.pre=self.pre[-FRAME_BYTES*6:]
                if not voice:continue
                self.buffer.extend(self.pre[:-FRAME_BYTES]);self.pre.clear()
            self.buffer.extend(frame);self.voiced=self.voiced or voice;self.speaking=self.speaking or voice;self.silent=0 if voice else self.silent+1
            ended=self.mode=='detection' and self.silent>=self.silence_frames
            if len(self.buffer)>=self.maximum or ended:
                pcm=bytes(self.buffer) if self.voiced and len(self.buffer)>=RATE*2*.2 else b''
                if pcm:segments.append(pcm)
                self.events.append({'pcm':pcm,'ended':ended})
                self.buffer.clear();self.voiced=False
                if ended:self.silent=0;self.speaking=False
        return level,segments
    def finish(self):
        self.buffer.extend(self.pending);out=bytes(self.buffer[:45*RATE*2]);self.pending.clear();self.buffer.clear();self.pre.clear()
        return out


class AcousticWindows:
    """Janelas YAMNet sobrepostas; nunca dependem do VAD/limiar de fala."""
    def __init__(self):self.buffer=bytearray()
    def feed(self,data):
        if not isinstance(data,bytes) or len(data)>RATE*2*45:raise ValueError('Chunk acústico excessivo/inválido.')
        self.buffer.extend(data);out=[]
        while len(self.buffer)>=31200:
            out.append(bytes(self.buffer[:31200]));del self.buffer[:15360]
        return out
    def clear(self):self.buffer.clear()
def public_speech_streams(jobs, entity, session, scope, seen, now):
    result=[]
    for job in jobs:
        details=job.get('details',{})
        if (job.get('kind')!='llm_speech' or job.get('status') not in ('running','done')
                or job['id'] in seen or details.get('invalidated') or not details.get('sentences')
                or details.get('channel')!='localhub' or not details.get('stable_only')
                or not 0 <= now-job.get('updated_at',0)<120):continue
        if scope=='global':
            allowed=(job.get('entity') in ('hoshino','lilith') and details.get('chat_scope')=='global'
                     and details.get('room_day')==session.get('local_date'))
        else:
            allowed=(job.get('entity')==entity and details.get('chat_scope','direct')=='direct'
                     and details.get('conversation_session_id')==session.get('id'))
        if allowed:result.append(job)
    return result
