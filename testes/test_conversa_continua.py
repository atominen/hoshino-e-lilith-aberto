import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from core.conversation import ConversationState, extrair_ultima_pergunta, parece_correcao



def main():
    falhas = 0

    def ok(cond, msg):
        nonlocal falhas
        if cond:
            print('  ok  ', msg)
        else:
            print('  FALHA', msg)
            falhas += 1

    print('1. correções de rumo')
    ok(parece_correcao('espera, não faz isso'), 'detecta correção')
    ok(parece_correcao('na verdade quero outra coisa'), 'detecta mudança de intenção')
    ok(not parece_correcao('vamos falar de xadrez'), 'não marca frase normal')

    print('2. fio isolado')
    fio = ConversationState(('discord', '123'), 'discord', '123')
    fio.receber('primeira parte', {'id': 'p1', 'nome': 'Gustavo'})
    fio.receber('segunda parte', {'id': 'p1', 'nome': 'Gustavo'})
    lote = [fio.mensagens_pendentes.popleft(), fio.mensagens_pendentes.popleft()]
    fio.iniciar_turno(lote)
    ok(len(fio.historico) == 2, 'duas mensagens entram como duas mensagens reais')
    ok(fio.historico[0]['content'] == 'primeira parte', 'ordem preservada')
    fio.anexar_resposta('entendi. Quer que eu continue?')
    ok('Quer que eu continue?' in fio.ultima_pergunta, 'pergunta fica registrada no fio')

    print('3. correção durante geração')
    fio2 = ConversationState(('tui', 'local'), 'tui', 'local')
    fio2.receber('faz a primeira coisa')
    lote2 = [fio2.mensagens_pendentes.popleft()]
    fio2.iniciar_turno(lote2)
    fio2.receber('na verdade, não faça isso', {'id': 'p1', 'nome': 'Gustavo'})
    ok(fio2.cancelar_geracao, 'correção nova cancela o turno em voo')
    ok(len(fio2.historico) == 1, 'mensagem nova não foi injetada retroativamente no histórico')

    print('4. pergunta')
    ok(extrair_ultima_pergunta('Tudo certo. O que você quer? Posso fazer isso?') == 'Posso fazer isso?', 'última pergunta extraída')

    print(f'\n{4 + 3 + 3 + 1} verificações de conversa')
    print(f'{falhas} falha(s)')
    raise SystemExit(1 if falhas else 0)


if __name__ == '__main__':
    main()
