"""Orçamento adaptativo de raciocínio: pensar muito onde a situação pede.

Medição de 05/11 (logs reais da Lilith, 26-30/10). A geração é 58-90% do tempo
do 9B. Nas 669 decisões Minecraft seguidas de ação com efeito, o sucesso da ação
foi o mesmo com pouco ou muito raciocínio: 91% com menos de 1k caracteres e
88-93% entre 1k e 6k. Já 12% das decisões, as que passavam de ~1536 tokens,
produziam 33% de todo o texto das decisões.
[Detalhes](../../docs/ORCAMENTO_ADAPTATIVO_20261105.md).

A política escolhe um teto de *saída* (raciocínio + resposta) por decisão, a
partir de sinais de dificuldade que a própria decisão já recebe:
- rotina: progresso recente, sem falha nem barreira;
- atenção: estagnação, falha ou incerteza no último recibo, perigo, chat,
  meta nova;
- difícil: barreira, morte ou escolha anterior divergente.

O teto não impede pensar. Esgotado, a entidade fecha a mesma decisão com o
próprio raciocínio (fechamento já existente em main.py). O estouro também é
sinal: a próxima decisão sobe um nível. O teto de rotina se ajusta sozinho:
sobe quando ela estoura com frequência e volta a descer quando sobra.

Modos (HOSHINO_ORCAMENTO_ADAPTATIVO):
- ativo (padrão desde o descongelamento de 05/11, a pedido humano): aplica o teto escolhido;
- observar: calcula e registra, mas aplica o teto fixo antigo;
- desligado: nem calcula.
Não muda modelo, prompt, ferramentas nem as opções oferecidas.
"""
from __future__ import annotations

import os

NIVEIS = ('rotina', 'atencao', 'dificil')
TETO_FIXO = 4096                      # orçamento vigente desde 28/10 (decisão e meta)
TETOS = {'rotina': 1536, 'atencao': 4096, 'dificil': 6144}
ROTINA_MIN, ROTINA_MAX, PASSO = 1024, 4096, 512
JANELA = 10                           # últimas decisões de rotina consideradas no ajuste
SUBIR_SE, DESCER_SE = 0.3, 0.05       # fração de estouros na janela
CHAVE = 'orcamento_raciocinio'        # dentro do checkpoint da tarefa (persiste com ela)
# Cada etapa com fechamento aprende separado: escolher ação e escolher meta pedem raciocínios diferentes.
CLASSES = {'escolha': CHAVE, 'meta': CHAVE + '_meta'}


def modo() -> str:
    valor = os.environ.get('HOSHINO_ORCAMENTO_ADAPTATIVO', 'ativo').strip().lower()
    return valor if valor in {'observar', 'ativo', 'desligado'} else 'ativo'


def _memoria(checkpoint: dict, classe: str = 'escolha') -> dict:
    mem = checkpoint.get(CLASSES[classe]) if isinstance(checkpoint, dict) else None
    if not isinstance(mem, dict):
        mem = {}
    teto = mem.get('teto_rotina')
    janela = mem.get('janela_rotina')
    elevar = mem.get('elevar')
    return dict(
        teto_rotina=teto if type(teto) is int and ROTINA_MIN <= teto <= ROTINA_MAX else TETOS['rotina'],
        janela_rotina=[bool(x) for x in janela if type(x) is bool][-JANELA:] if isinstance(janela, list) else [],
        elevar=elevar if type(elevar) is int and 0 <= elevar <= 3 else 0)


def sinais_minecraft(checkpoint: dict, monitor: dict | None, *, perigo=False, morte=False, chat=False) -> dict:
    """Só leitura do que a decisão já recebe; nenhuma consulta nova ao jogo."""
    cp: dict = checkpoint if isinstance(checkpoint, dict) else {}
    mon: dict = monitor if isinstance(monitor, dict) else {}
    traj = [r for r in cp.get('trajectory') or [] if isinstance(r, dict)]
    ultimo: dict = traj[-1] if traj else {}
    sem_progresso = mon.get('actions_without_progress')
    sub = cp.get('subgoal')
    sub = sub if isinstance(sub, dict) else {}
    passos = cp.get('steps')
    passos = passos if isinstance(passos, int) else 0
    meta_passo = sub.get('selected_step')
    meta_nova = isinstance(meta_passo, int) and 0 <= passos - meta_passo <= 1
    return dict(
        barreira=bool(cp.get('barrier')),
        morte=bool(morte),
        escolha_divergente=bool(cp.get('choice_feedback')),
        sem_progresso=sem_progresso if isinstance(sem_progresso, int) and sem_progresso >= 0 else 0,
        ultimo_recibo=str(ultimo.get('status') or ''),
        perigo=bool(perigo),
        chat=bool(chat),
        meta_nova=meta_nova,
        sem_meta=not sub,
        inicio=passos < 3)


def nivel_por_sinais(sinais: dict, classe: str = 'escolha') -> tuple[str, list[str]]:
    dificil = [k for k in ('barreira', 'morte', 'escolha_divergente') if sinais.get(k)]
    if dificil:
        return 'dificil', dificil
    atencao = [k for k in ('perigo', 'chat', 'meta_nova', 'inicio') if sinais.get(k)]
    if classe == 'meta' and sinais.get('sem_meta'):
        atencao.append('sem_meta')        # primeira meta: planejamento aberto, não rotina
    if sinais.get('sem_progresso', 0) >= 2:
        atencao.append('sem_progresso')
    if sinais.get('ultimo_recibo') not in {'', 'success'}:
        atencao.append('ultimo_recibo_' + sinais['ultimo_recibo'][:20])
    return ('atencao', atencao) if atencao else ('rotina', [])


def escolher(checkpoint: dict, sinais: dict, *, modo_atual: str | None = None, classe: str = 'escolha') -> dict:
    """Devolve o teto a aplicar e o que a política escolheria (para o registro)."""
    atual = modo_atual or modo()
    if atual == 'desligado':
        return dict(modo=atual, classe=classe, nivel=None, motivos=[], escolhido=TETO_FIXO, limite=TETO_FIXO)
    mem = _memoria(checkpoint, classe)
    nivel, motivos = nivel_por_sinais(sinais, classe)
    if mem['elevar'] and nivel != 'dificil':
        nivel = NIVEIS[NIVEIS.index(nivel) + 1]
        motivos = [*motivos, 'estouro_anterior']
    escolhido = mem['teto_rotina'] if nivel == 'rotina' else TETOS[nivel]
    return dict(modo=atual, classe=classe, nivel=nivel, motivos=motivos, escolhido=escolhido,
                limite=escolhido if atual == 'ativo' else TETO_FIXO)


def registrar(checkpoint: dict, escolha: dict, *, pensamento_chars: int, estourou: bool) -> dict:
    """Aprende com o resultado: estouro eleva a próxima; a janela ajusta o teto de rotina.

    No modo observar o estouro é contado contra o teto que *seria* aplicado
    (estimado por ~3,5 caracteres por token), para a evidência valer antes
    de ativar.
    """
    if not isinstance(checkpoint, dict) or escolha.get('nivel') is None:
        return {}
    classe = escolha.get('classe', 'escolha')
    mem = _memoria(checkpoint, classe)
    chars = pensamento_chars if type(pensamento_chars) is int and pensamento_chars >= 0 else 0
    estouro = bool(estourou) if escolha['modo'] == 'ativo' else (estourou or chars > escolha['escolhido'] * 3.5)
    mem['elevar'] = min(3, mem['elevar'] + 1) if estouro else max(0, mem['elevar'] - 1)
    if escolha['nivel'] == 'rotina' and 'estouro_anterior' not in escolha['motivos']:
        mem['janela_rotina'] = [*mem['janela_rotina'], estouro][-JANELA:]
        if len(mem['janela_rotina']) >= JANELA // 2:
            fracao = sum(mem['janela_rotina']) / len(mem['janela_rotina'])
            if fracao > SUBIR_SE and mem['teto_rotina'] < ROTINA_MAX:
                mem['teto_rotina'] += PASSO
                mem['janela_rotina'] = []
            elif fracao <= DESCER_SE and len(mem['janela_rotina']) == JANELA and mem['teto_rotina'] > ROTINA_MIN:
                mem['teto_rotina'] -= PASSO
                mem['janela_rotina'] = []
    checkpoint[CLASSES[classe]] = mem
    return dict(mem, estouro=estouro)
