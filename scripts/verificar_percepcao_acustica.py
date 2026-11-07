#!/usr/bin/env python3
"""Ensaio opt-in com gravações públicas; sem microfone, Central ou conversas.

Referências ficam somente em RAM; o relatório contém hashes e métricas, não
gravações. ESC-50 é CC BY-NC3.0 (uso local de pesquisa, sem redistribuir áudio).
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import resource
import sys
import time
from urllib.request import urlopen
import wave

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT)]
REVISION='33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6'
FILES=(('1-1791-A-26.wav','laughter'),('1-30039-A-26.wav','laughter'),
       ('1-30043-A-26.wav','laughter'),('1-33658-A-26.wav','laughter'),
       ('1-36164-A-26.wav','laughter'),('1-36164-B-26.wav','laughter'),
       ('1-72695-A-26.wav','laughter'),('1-73123-A-26.wav','laughter'),
       ('1-19111-A-24.wav','cough'),('1-26143-A-21.wav','sneeze'),
       ('1-19118-A-24.wav','cough'),('1-30830-A-24.wav','cough'),
       ('1-29680-A-21.wav','sneeze'),('1-31748-A-21.wav','sneeze'),
       ('1-21934-A-38.wav',None),('1-17367-A-10.wav',None),
       ('1-104089-A-22.wav',None),('1-137-A-32.wav',None))


def read_audio(url):
    import numpy as np
    with urlopen(url,timeout=25) as response:data=response.read(4*1024**2+1)
    if len(data)>4*1024**2:raise ValueError('Referência grande demais.')
    with wave.open(io.BytesIO(data),'rb') as wav:
        if wav.getsampwidth()!=2:raise ValueError('Referência não é PCM16.')
        rate=wav.getframerate();channels=wav.getnchannels()
        values=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').reshape(-1,channels).mean(axis=1)
    if rate!=16000:
        values=np.interp(np.arange(round(len(values)*16000/rate))*rate/16000,np.arange(len(values)),values)
    return values.astype('<i2'),hashlib.sha256(data).hexdigest()


def run():
    import numpy as np
    from core import acoustic_perception as detector
    report=dict(model_sha256=detector.MODEL_SHA,esc50_revision=REVISION,rows=[],
                notice='Amostra exploratória pequena, não benchmark/garantia de recall em microfone real; mistura/volume/corte são transformações declaradas.')
    sounds={}
    for name,expected in FILES:
        url=f'https://raw.githubusercontent.com/karolpiczak/ESC-50/{REVISION}/audio/{name}'
        pcm,sha=read_audio(url);sounds[name]=pcm
        report['rows'].append(evaluate(name,pcm,expected,url,sha))
    url='https://storage.googleapis.com/audioset/speech_whistling2.wav'
    speech,sha=read_audio(url);report['rows'].append(evaluate('speech_whistling',speech,None,url,sha))
    report['rows'].append(evaluate('silence',np.zeros(80000,dtype='<i2'),None,'generated silence',''))
    laugh=sounds[FILES[0][0]]
    report['rows'].append(evaluate('laughter_volume_5pct',(laugh*.05).astype('<i2'),'laughter','gain0.05 from '+FILES[0][0],''))
    peak=max(range(0,len(laugh)-6400,1600),key=lambda i:float(np.mean(laugh[i:i+6400].astype(float)**2)))
    report['rows'].append(evaluate('laughter_400ms',np.pad(laugh[peak:peak+6400],(3000,6200)).astype('<i2'),
                                   'laughter',f'400ms peak-energy crop at sample{peak} from '+FILES[0][0],''))
    n=min(len(laugh),len(speech));mixed=np.clip(laugh[:n]*.5+speech[:n]*.5,-32768,32767).astype('<i2')
    report['rows'].append(evaluate('laughter_and_speech_mix',mixed,'laughter','50/50 PCM mix of references above',''))
    report['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return report


def evaluate(name,values,expected,url,sha):
    import numpy as np
    from core import acoustic_perception as detector
    began=time.perf_counter();cpu=time.process_time();events=[];times=[];windows=0;raw_max={kind:0.0 for kind,_,_,_ in detector.GROUPS}
    for i in range(0,max(1,len(values)-15600+1),7680):
        chunk=values[i:i+15600]
        if len(chunk)<15600:chunk=np.pad(chunk,(0,15600-len(chunk)))
        result=detector.classify_pcm(chunk.astype('<i2').tobytes());windows+=1
        if float(np.std(chunk))>1:
            scores=detector._ENGINE.get_tensor(detector._ENGINE.get_output_details()[0]['index'])[0]
            for kind,_,indices,_ in detector.GROUPS:raw_max[kind]=max(raw_max[kind],float(max(scores[list(indices)])))
        events.extend(result['events']);times.append(result['processing_seconds'])
    kinds=sorted({e['kind'] for e in events});vocal={e['kind'] for e in events if e['kind']!='sound'}
    return dict(name=name,url=url,source_sha256=sha,expected=expected,duration_seconds=round(len(values)/16000,3),
                windows=windows,detected=kinds,expected_detected=expected in kinds if expected else None,
                false_vocal_classes=sorted(vocal-({expected} if expected else set())),
                max_scores={k:max(e['score'] for e in events if e['kind']==k) for k in kinds},
                raw_max_scores={k:round(v,5) for k,v in raw_max.items()},
                wall_seconds=round(time.perf_counter()-began,4),cpu_seconds=round(time.process_time()-cpu,4),
                window_max_seconds=round(max(times),4),window_mean_seconds=round(sum(times)/len(times),4))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--download-reference',action='store_true')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if not args.download_reference:parser.error('Aquisição de referências exige --download-reference.')
    result=run();args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
