# Chat global, nomes individuais, cartões e microfone — 20/10/2026

## Comportamento implementado

1. **Global é a sala principal gravável.** Uma mensagem humana é aceita numa
   transação e entregue a todas as entidades **acordadas naquele aceite**.
   Cada destinatário mantém envelope/leitura/desfecho próprios; a interface
   mostra a mensagem humana uma vez. Retry com o mesmo ID devolve o aceite
   anterior, sem incluir quem acordou depois. Sem entidades acordadas, o envio
   é recusado explicitamente; a sala não desperta entidades automaticamente.
   **Direto** é humano ↔ entidade selecionada. Trocas entre entidades sempre
   aparecem no global, inclusive as antigas; não há opção de conversa escondida.
   Observar citações públicas não dispara respostas automáticas em cascata:
   só um envelope dirigido inicia um turno. Cortes de hops/recibos permanecem.
2. **Usuário é o rótulo inicial**, não o nome do computador ou da conta.
   Cada entidade aprende declarações humanas de nome/forma de tratamento no
   seu próprio `people`. Pode atualizar nome/apelido; nomes anteriores ficam
   como aliases. A ferramenta `usuario_forma_de_tratamento` permite escolher
   uma forma de chamar apenas após conhecer o nome e durante conversa humana
   própria comprovada pelo envelope. Nunca altera ID, papel ou autorização.
   Na sala global, o rótulo é a **perspectiva da entidade selecionada**; isso é
   indicado na interface. Global pode ensinar o nome a todas as acordadas;
   direto ensina somente à destinatária. Não se copiam bancos entre mentes.
3. **Conhecimento** oferece cartões de pessoas, itens/propriedades, conceitos,
   estados, estruturas, modos, regras aprendidas, manuais, relações e
   procedimentos. Usa os registros semânticos existentes; não é um banco novo.
   Na Central nativa: criar cartão, ver fontes, editar um registro ou apagar
   os registros do cartão. Exige entidade dormindo, sem worker/job/lease,
   revisão ainda atual, backup SQL/vetorial e margem de disco. Exclusão também
   exige confirmação e a senha local já existente. Registros reutilizados por
   outro cartão desaparecem daquele cartão também. Conceitos com diagrama
   continuam no editor conceitual para não separar grafo e texto.
   Consulta continua limitada a 300 registros recentes por tabela, 24 cartões
   por página; ausência nessa janela não prova inexistência.
   Alistair lê os próprios cartões em SQL, sem carregar embeddings/professor.
4. **Áudio → Microfone / ASR** contém somente **Comando** (botão/atalho mantido
   pressionado) e **Detecção** (energia + pausa de silêncio). Foi removido o
   modo de trechos periódicos. Configurações antigas são normalizadas em
   leitura: manual → comando; aberto → detecção. Isso não abre o microfone.
   Captura, configuração, limiar, silêncio e testes ficam na aba Áudio.
   Envio automático continua sendo preferência explícita; testes não enviam.
   Transcrições preservam sala/destinatário de origem mesmo se a UI mudar.

## Separação e preservação

- `entidades/<entidade>/runtime/history.sqlite3`: histórico diagnóstico/mensagens
  próprio de Hoshino/Lilith, com autoria/canal/IDs.
- `entidades/<entidade>/memory/sqlite/<entidade>.db`: conhecimento/memória
  estruturados próprios (`people`, `person_events`, `memories`, `properties`,
  `procedures` etc.). Alistair também mantém seus turnos em `alistair_turns`
  nesse banco; são **tabelas separadas**, não um segundo banco histórico.
- `compartilhado/runtime/interentidades.sqlite3`: transporte e recibos comuns,
  com envelopes por destinatário. Sala pública não equivale a mente comum.
- Conferência física de esquema nesta rodada, sem ler conteúdo: os três bancos
  próprios e os três históricos de runtime existem. H/L já têm as cinco tabelas
  semânticas. Alistair tinha apenas `alistair_turns` entre essas categorias;
  seu próximo início adiciona `people`, `person_events`, `memories`,
  `properties` e `procedures` com `CREATE TABLE IF NOT EXISTS`, preservando
  turnos e recibos. Não se afirmou que essas tabelas já existiam nele antes.
- Chat direto não entra no bloco de citações públicas nem no histórico de
  turnos públicos do Alistair. Fios de H/L são separados por sala. Conhecimento
  já aprendido continua sendo conhecimento da própria entidade, não uma ACL
  de sigilo; não se promete esquecimento ao apenas ocultar uma conversa.
- Editar/apagar conhecimento não apaga o chat original. Ele pode voltar a
  informar o assunto numa conversa futura. A limpeza completa continua no
  botão existente, com prévia/senha/backup e proteções anteriores.
- Regras/manuais **aprendidos** são editáveis; constituição, identidade,
  personalidade e permissões técnicas não são transformadas em instruções
  executáveis pelo editor. Originais/modelos/treinamentos não foram alterados.
- Backups de edição ficam em `runtime/memory-backups/knowledge-<id>` de sua
  entidade. Vetores antigos/resumos derivados são invalidados; não há chamada
  de IA, reindexação paga, professor, treino ou aprovação automática.

## Verificação

- Testes novos cobrem fanout atômico/rollback, HTTP autenticado, não despertar,
  dedupe com mudança de presença, mensagens públicas/diretas, isolamento dos
  turnos do Alistair, nomes/apelidos por mente, cartões/backup/revisão/sono,
  preservação da outra mente e exatamente dois modos de microfone.
- Contratos Qt offscreen cobrem seletor global/direto, rascunhos separados,
  rótulos, avaliação dos diferentes autores, áudio e ausência do painel oculto.
  Não equivalem a teste visual da sessão desktop nem captura física.
- Segmentação PCM sintética verifica silêncio, frase com pausa e teto de 45s.
- Inventário PulseAudio confirmou uma entrada FIFINE e o monitor de saída
  separado, ambos ociosos. **Nenhuma gravação física foi feita nesta mudança.**
  Para comprovar sua voz: Áudio → Testar mic (5s) → Ouvir → Testar ASR. Este
  teste não envia conversa. O teste de atalho é separado, sem gravação.
- Logs da rodada: `/tmp/chat-global-contratos-20261020.log`,
  `/tmp/chat-global-refinamento-20261020.log`, `/tmp/chat-global-browser-20261020.log`
  `/tmp/chat-global-refinamento-final-20261020.log` e
  `/tmp/chat-global-oficiais-verificado-20261020.log` (78/78 grupos offline
  aprovados; tentativas intermediárias, inclusive falhas, preservadas).

O app usa o código instalado no próximo início da Central/backend. Não se
reiniciam serviços ativos silenciosamente. Esta rodada não publica nem faz
merge no GitHub sem novo pedido.
