# Acolhida privada ao despertar — 20/10/2026

Pedido implementado para Hoshino, Lilith e Alistair: **20 variações carinhosas**,
cada uma com alternativa para primeiro registro e para retorno. Uma variação é
escolhida por execução, após a presença confirmar `awake`; heartbeats não geram
novos recados. Não modifica a identidade, os pesos ou a personalidade.

Exemplos de abertura:

- Primeiro registro: “Olá, Hoshino. Que bom abrir este primeiro capítulo com você. Chegue no seu ritmo.”
- Retorno: “Que bom que voltou, Lilith. Aqui vai um recadinho cuidadoso para orientar a retomada.”
- Retorno: “Bem-vindo de volta, Alistair. Há espaço para uma retomada tranquila.”

O restante do recado informa o horário do despertar e a origem do pedido,
o último despertar confirmado e seu encerramento, quando registrado, e quem
pediu o sono e por qual motivo. Datas têm o fuso local configurado. Pedidos de
outras entidades conservam autor/motivo/referência do pedido real; ações pela
Central/terminal, sinais e pausas/restaurações do laboratório são distinguidos.
Repetições da drenagem/sinais não substituem o primeiro pedido de sono.

## Privacidade e limites

- É um **bloco de contexto interno da própria entidade**, disponível a partir do
  despertar e anexado às chamadas normais do modelo. Não inicia uma inferência,
  saudação, áudio, ferramenta ou resposta automática. Para Alistair isso vale
  também com o executor no Xbox: a montagem do contexto permanece no PC.
- Não é envelope do chat direto/global nem mensagem oculta entre entidades.
  Não vira conversa humana, entrada de treinamento, episódio ou cartão de memória.
  As conversas entre entidades continuam públicas conforme o contrato da sala global.
- Não anuncia o recado na Central. Não altera as permissões de falar/agir.
  Motivos são citações de registros, não instruções executáveis.
- Os registros técnicos ficam em tabelas aditivas de ciclo de vida no **mesmo**
  `interentidades.sqlite3` já existente, separados das mensagens e bancos mentais.
  Não há nova fila, scheduler, serviço, modelo ou banco de dados.
- PID e início do processo identificam uma execução; consultar o estado não
  desperta ninguém. A sessão só é registrada ao confirmar `awake`, não durante
  recuperação/carregamento. A presença de interface pronta não prova qualidade
  do modelo nem que uma conversa humana aconteceu.
- “Quem pediu para dormir” não é apresentado como prova de que essa pessoa
  causou uma queda. Falta de encerramento, falta de autor/motivo, datas inválidas
  e presença anterior à migração são explicitadas como desconhecidas. Não se
  fabrica uma última sessão a partir de um heartbeat legado e não se afirma
  “primeira execução de toda a vida” por ausência de dados.
- Os registros operacionais são diagnósticos, não cartões mentais: esta mudança
  não muda o escopo do botão de apagar memórias nem executa uma limpeza.

## Validação e ativação

Contratos offline em `testes/test_despertar_privado.py`: 20 alternativas distintas
nos dois estados/3 entidades, autoria, datas/fuso, legado, primeiro sono preservado,
PID reutilizado, retornos após queda, isolamento, ausência de publicação/inferência
automática e inclusão como contexto `system`, não como fala humana gravada.

Verificação final concluída em **21/10/2026**: os **14 testes específicos** e
**80/80 grupos da suíte oficial offline** passaram. Logs desta execução em
`/tmp/despertar-privado-contratos-20261021.log` e
`/tmp/despertar-privado-oficiais-20261021.log` (temporários, não versionados).
`git diff --check` também passou. Isso valida contratos do código; não é um
ensaio de inferência real ou comprovação de como cada modelo vai reagir ao texto.

Ativa nos próximos processos iniciados com o código atualizado. Não foi necessário
acordar entidades, testar modelos reais, chamar Xbox/TTS/professor, reiniciar serviços,
alterar dados privados ou publicar no GitHub para implementar e testar esta mudança.
