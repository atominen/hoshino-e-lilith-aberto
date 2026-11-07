"""Contrato fechado de fala/trechos ASR; sem captura, estado mental ou modelo."""
import re


def validate(value):
    if value is None:return None
    keys={'id','part','revision','preview','session_id','scope'}
    if not isinstance(value,dict) or set(value)!=keys:raise ValueError('Origem de fala inválida.')
    if not isinstance(value['id'],str) or not re.fullmatch(r'[a-f0-9]{32}',value['id']):raise ValueError('ID de fala inválido.')
    for key,low,high in [('part',0,63),('revision',1,100000)]:
        if type(value[key]) is not int or not low<=value[key]<=high:raise ValueError('Ordem de fala inválida.')
    if type(value['preview']) is not bool:raise ValueError('Tipo de transcrição inválido.')
    if not isinstance(value['session_id'],str) or not 1<=len(value['session_id'])<=100:raise ValueError('Sessão da fala inválida.')
    if value['scope'] not in ('global','direct'):raise ValueError('Escopo da fala inválido.')
    return dict(value)


def compose(jobs,entity,session_id,scope):
    if not 1<=len(jobs)<=64 or len({j['id'] for j in jobs})!=len(jobs):raise ValueError('Trechos duplicados ou excessivos.')
    origin=None;source=None;mode=None;texts=[];segments=[];speaker=None
    for index,job in enumerate(jobs):
        meta=validate(job.get('utterance'))
        if (not meta or meta['preview'] or meta['part']!=index or meta['session_id']!=session_id or meta['scope']!=scope or
                job.get('entity')!=entity or job.get('kind')!='audio_asr' or job.get('status')!='done'):
            raise ValueError('Trecho definitivo não corresponde a esta fala/conversa.')
        result=job.get('result') or {};text=result.get('text')
        if not isinstance(text,str) or not text.strip():raise ValueError('Trecho sem transcrição definitiva.')
        current_source=result.get('source','browser_microphone');current_mode=job.get('capture_mode','command')
        current_speaker=(result.get('speaker','usuario'),result.get('speaker_basis','source_role'))
        if index and (meta['id']!=origin or current_source!=source or current_mode!=mode or current_speaker!=speaker):
            raise ValueError('Trechos de falas/origens diferentes.')
        origin=meta['id'];source=current_source;mode=current_mode;speaker=current_speaker
        texts.append(text.strip());segments.extend(result.get('segments') or [])
    return dict(text=' '.join(texts),source=source,speaker=speaker[0],speaker_basis=speaker[1],segments=segments),mode,origin
