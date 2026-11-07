"""YAMNet local: eventos prováveis, nunca transcrição, autoria ou emoção.

Sem captura, download, importação de runtime ML ou gravação na importação.
O classificador deve rodar no worker CPU isolado, não no processo Qt/LLM.
"""
import hashlib
import importlib.util
import math
from pathlib import Path
import threading
import time
import zipfile

import config

MODEL_DIR=Path(config.MODELOS_DIR)/'percepcao-acustica/yamnet'
MODEL_SHA='10c95ea3eb9a7bb4cb8bddf6feb023250381008177ac162ce169694d05c317de'
MODEL_BYTES=4126810
MODEL_URL='https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/audio_classification/rpi/lite-model_yamnet_classification_tflite_1.tflite?generation=1665848355781994'
LABELS_SHA='8e1267a120c1932b7273c0d0e0c5529edbb9a35512b437b1c8982baa59047051'
RATE=16000
WINDOW=15600
GROUPS=(('laughter','risada/gargalhada',tuple(range(13,19)),.10),
        ('crying','choro',tuple(range(19,23)),.35),
        ('sigh','suspiro',(23,),.35),('cough','tosse',(42,43),.35),
        ('sneeze','espirro',(44,),.35),('gasp','ofegação',(39,40),.4))
_LOCK=threading.RLock()
_ENGINE=None
_STAMP=None


def _verified_model():
    path=MODEL_DIR/'yamnet.tflite'
    if path.is_symlink() or not path.is_file():raise RuntimeError('Detector acústico não instalado; execute a preparação explícita.')
    if path.stat().st_size!=MODEL_BYTES or hashlib.sha256(path.read_bytes()).hexdigest()!=MODEL_SHA:
        raise RuntimeError('Modelo acústico divergente; não carregar nem baixar automaticamente.')
    return path


def status():
    try:_verified_model();available=True
    except (OSError,RuntimeError):available=False
    return dict(available=available,loaded=_ENGINE is not None,engine='YAMNet',device='cpu',
                downloads_allowed=False,window_samples=WINDOW,sample_rate=RATE,
                score_basis='uncalibrated_model_score',speaker_identification=False)


def events_from_scores(scores,labels=None):
    if len(scores)!=521 or any(not math.isfinite(float(v)) or not 0<=float(v)<=1 for v in scores):
        raise ValueError('Scores acústicos inválidos.')
    events=[];vocal=set()
    for kind,label,indices,threshold in GROUPS:
        vocal.update(indices);index=max(indices,key=lambda i:float(scores[i]));score=float(scores[index])
        if score>=threshold:
            events.append(dict(kind=kind,label=label,class_index=index,score=round(score,5),speaker='unknown',
                               basis='acoustic_model_score_not_probability'))
    if labels is not None:
        if len(labels)!=521:raise ValueError('Classes acústicas inválidas.')
        # Fala/canto/silêncio não são convertidos em um evento não verbal falso.
        ignored=set(range(0,13))|set(range(24,35))|{494}|vocal
        eligible=[i for i in range(521) if i not in ignored and float(scores[i])>=.6]
        if eligible:
            i=max(eligible,key=lambda i:float(scores[i]))
            events.append(dict(kind='sound',label=str(labels[i]),class_index=i,score=round(float(scores[i]),5),
                               speaker='unknown',basis='acoustic_model_score_not_probability'))
    return events


def classify_pcm(pcm,*,sample_rate=RATE):
    if not isinstance(pcm,bytes) or len(pcm)!=WINDOW*2 or sample_rate!=RATE:
        raise ValueError('Detector exige15600 amostras PCM16 mono em16kHz.')
    global _ENGINE,_STAMP
    began=time.monotonic()
    with _LOCK:
        path=_verified_model();stamp=(str(path),path.stat().st_mtime_ns,path.stat().st_ino)
        import numpy as np
        if _ENGINE is None or _STAMP!=stamp:
            from ai_edge_litert.interpreter import Interpreter
            engine=Interpreter(model_path=str(path),num_threads=2)
            engine.allocate_tensors()
            inputs=engine.get_input_details();outputs=engine.get_output_details()
            if (len(inputs)!=1 or len(outputs)!=1 or inputs[0]['shape'].tolist()!=[WINDOW]
                    or outputs[0]['shape'].tolist()!=[1,521] or inputs[0]['dtype']!=np.float32):
                raise RuntimeError('Contrato do modelo acústico não confere.')
            _ENGINE=engine;_STAMP=stamp
        values=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768.
        values-=np.mean(values)
        energy=float(np.sqrt(np.mean(values*values)))
        if energy<1e-6:return dict(events=[],engine='YAMNet',processing_seconds=time.monotonic()-began)
        _ENGINE.set_tensor(_ENGINE.get_input_details()[0]['index'],values)
        _ENGINE.invoke();scores=_ENGINE.get_tensor(_ENGINE.get_output_details()[0]['index'])[0]
        with zipfile.ZipFile(path) as z:raw=z.read('yamnet_label_list.txt')
        if hashlib.sha256(raw).hexdigest()!=LABELS_SHA:raise RuntimeError('Mapa de classes divergente.')
        return dict(events=events_from_scores(scores,raw.decode().splitlines()),engine='YAMNet',
                    processing_seconds=round(time.monotonic()-began,5),speaker='unknown')
