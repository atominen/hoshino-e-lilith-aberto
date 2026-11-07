"""Habituação e sensibilização por gatilho afetivo.

Mecanismo do Pestinha (depressão sináptica com recuperação lenta) escrito como
equação, sem simular neurônios: o replay de 05/11/2026 mostrou que a rede e a
equação dão o mesmo resultado, e a equação custa nada.

Cada gatilho listado em `REGRAS` tem um ganho que multiplica a intensidade do
evento antes de ele chegar ao humor, ao estado psicológico e às emoções:

* **habituação** (fator < 1): a mesma coisa repetida em pouco tempo pesa menos
  a cada vez, até um piso. Uma novidade atrás da outra deixa de ser novidade;
* **sensibilização** (fator > 1): um risco confirmado logo depois de outro pesa
  mais, até um teto, separando susto passageiro de ameaça que se repete.

Entre eventos o ganho volta exponencialmente para 1 (`recuperacao_min` é a
constante de tempo), inclusive com a entidade dormindo, pelo tempo de parede.
Gatilhos fora da tabela não mudam: maltrato, crítica, falhas, vergonha e
vínculos não "enjoam", para a entidade não ficar anestesiada ao que importa.

O estado fica em `estado_mente.json`, chave `habituacao`, porque é da própria
entidade. Valor ilegível ou fora do domínio é ignorado (ganho 1), nunca propagado.
"""
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import history  # noqa: E402

# gatilho -> (fator por ocorrência, recuperação em minutos, piso ou teto)
REGRAS = {
    'novidade':              (0.60, 60, 0.20),
    'pergunta_sem_resposta': (0.75, 60, 0.30),
    'experiencia_desejada':  (0.80, 120, 0.30),
    'usuario_voltou':        (0.70, 120, 0.30),
    'usuario_chegou_perto':  (0.70, 60, 0.30),
    'elogio':                (0.80, 180, 0.40),
    'conversa_boa':          (0.85, 120, 0.40),
    'tarefa_sucesso':        (0.85, 120, 0.40),
    'xadrez_vitoria':        (0.80, 240, 0.40),
    'silencio_longo':        (0.70, 120, 0.30),
    'risco_observado':       (1.25, 20, 1.60),   # sensibiliza
}
CHAVE = 'habituacao'


def _recuperado(dados, regra, agora):
    """Ganho atual de um gatilho a partir do registro salvo; 1.0 se não houver."""
    fator, tau_min, limite = regra
    if not isinstance(dados, dict):
        return 1.0
    try:
        ganho = float(dados['g'])
        decorrido = history.elapsed_seconds(dados['em'], agora, operation='habituation.recover')
    except (KeyError, TypeError, ValueError):
        return 1.0
    baixo, alto = (limite, 1.0) if fator < 1 else (1.0, limite)
    if decorrido is None or not math.isfinite(ganho) or not baixo <= ganho <= alto:
        return 1.0
    return 1.0 - (1.0 - ganho) * math.exp(-max(0.0, decorrido) / 60.0 / tau_min)


def ganho(evento: str, agora: datetime = None, estado: dict = None) -> float:
    """Ganho que o evento teria agora, sem registrar a ocorrência."""
    regra = REGRAS.get(evento)
    if not regra:
        return 1.0
    agora = agora or history.local_now()
    if estado is None:
        from core import state_file
        estado = state_file.read(config.ESTADO_MENTE).get(CHAVE, {})
    return round(_recuperado((estado or {}).get(evento), regra, agora), 4)


def registrar(evento: str, agora: datetime = None) -> dict:
    """Aplica uma ocorrência: devolve o ganho usado nela e grava o próximo.

    Falha de escrita devolve o ganho calculado com `persisted=False`; o chamador
    usa o ganho mesmo assim, mas a próxima ocorrência não terá sido contada.
    """
    regra = REGRAS.get(evento)
    if not regra:
        return dict(ganho=1.0, persisted=True, regra=False)
    from core import state_file
    agora = agora or history.local_now()
    fator, _, limite = regra
    usado = {}

    def mutate(dados):
        tabela = dados.get(CHAVE)
        tabela = dict(tabela) if isinstance(tabela, dict) else {}
        atual = _recuperado(tabela.get(evento), regra, agora)
        proximo = max(limite, atual * fator) if fator < 1 else min(limite, atual * fator)
        tabela[evento] = {'g': round(proximo, 4), 'em': history.utc_timestamp(agora)}
        dados[CHAVE] = tabela
        usado['ganho'] = round(atual, 4)

    persisted = state_file.update(config.ESTADO_MENTE, mutate, 'habituation.write')
    if not persisted:
        usado['ganho'] = ganho(evento, agora)
    return dict(ganho=usado['ganho'], persisted=persisted, regra=True)


def resumo(agora: datetime = None) -> dict:
    """Ganhos atuais diferentes de 1, para painel e diagnóstico (só leitura)."""
    from core import state_file
    agora = agora or history.local_now()
    estado = state_file.read(config.ESTADO_MENTE).get(CHAVE, {})
    out = {}
    for evento in REGRAS:
        g = ganho(evento, agora, estado)
        if abs(g - 1.0) >= 0.01:
            out[evento] = g
    return out
