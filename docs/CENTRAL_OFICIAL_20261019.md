# Atualização instalada e entrega privada — 19/10/2026

Pedido humano: corrigir a limpeza incompleta e a continuidade do Alistair,
aplicar no app deste PC e atualizar o GitHub privado. Nenhuma nova limpeza de
dados, alteração de identidade/pesos, treino ou execução do professor foi
autorizada por esta entrega.

## Botão existente “Apagar todas”

O botão em **Memória** agora explicita **memória, conhecimento e chat**. A
operação continua sendo somente para a entidade selecionada, com senha,
confirmação e prévia vinculada ao conteúdo atual. Clientes antigos não podem
reutilizar silenciosamente uma prévia do escopo anterior.

- Remove os registros aprendidos do banco da entidade: memórias, propriedades,
  pessoas/eventos associados, fatos, episódios, reflexões, procedimentos,
  resumos, turnos Alistair, tarefas/etapas, lembretes, metas e projeções de
  experiência. Esvazia os índices vetoriais existentes sem gerar embeddings.
- Limpa o histórico local e seu índice de busca, inclusive entradas órfãs.
  No canal compartilhado, retira o texto e o feedback das mensagens que
  envolvem essa entidade. Conserva os IDs/tombstones e marcadores de processamento
  necessários para não reenviar ações/respostas antigas.
- Cancela pedidos de despertar pendentes desse escopo; cancelamento não é
  confirmação de que alguém acordou. Tarefas de apresentação ficam canceladas.
  Recibos de efeitos e marcadores incertos continuam protegidos contra replay.
- Arquiva logs de experiência, pendências de reflexão e caches de contatos
  antes de retirá-los das fontes ativas. Limpa somente a projeção operacional
  `activity_context` do JSON de estado, não emoções/identidade.
- Preserva identidade, personalidade, traços/gostos, habilidades, configurações,
  modelos/adaptadores, auditoria e memórias próprias das outras entidades.
  Cópias que outra entidade já aprendeu em seu próprio banco não são apagadas.

Como o chat usa um canal compartilhado, **as três entidades precisam estar
dormindo e sem jobs/leases**. A interface explica e solicita o sono; o backend
confere novamente com os locks existentes. Não se força o encerramento de um
trabalho ativo para limpar dados.

Backup SQLite consistente de todas as fontes antes do primeiro efeito,
verificação de integridade, cópia do índice/arquivos e reserva de 1 GiB. A
operação entre bancos não é uma transação distribuída: falha intermediária fica
registrada como resultado incerto, bloqueando nova tentativa automática. O
backup permite diagnóstico/recuperação; não se declara sucesso parcial.

**Não é apagamento forense:** backups, auditoria e arquivos técnicos/áudio
permanecem locais. “Apagar selecionadas” continua removendo só a seleção e
resumos derivados; não adquire silenciosamente o escopo completo.

## Alistair

A fala real “acordar a Lilith e se apresentar a Alistair” gerou uma restrição
de autorização inventada. Agora esse pedido específico ambíguo recebe uma
pergunta de esclarecimento, sem inferência, envio ou despertar. Confirmação
humana na mesma sessão libera apenas o alvo esclarecido; reinício e “continue”
não repetem um envio já registrado. Não é um planejador geral nem interpretação
automática de qualquer frase ambígua.

A identidade configurada continua sendo a fonte de personalidade. Sua projeção
fixa no prompt conserva papel, natureza, traços, estilo, regras cognitivas e
campos personalizados, sem alterar o arquivo. Remove metadados técnicos sem
função conversacional. Cumprimentos e perguntas completas simples de identidade
não recebem o catálogo de ferramentas. Pedidos compostos/operacionais mantêm
as permissões e ferramentas; nenhum limite de contexto/segurança foi reduzido.

O cadastro de senha também inclui a correção já testada do formulário
persistente: validação visível, confirmação e leitura do estado salvo. Scrypt,
limite de tentativas e mínimo de oito caracteres permanecem. A senha atual
não é redefinida pela atualização.

## Verificações

- **77/77 grupos oficiais offline**, exit 0, pelo runner isolado existente.
  Inclui laboratório, browser simulado e contratos Qt; não abre microfone,
  usa ElevenLabs, treina ou escreve em bancos reais.
- Limpeza completa: **7/7** testes específicos, incluindo isolamento entre
  entidades, backup, recibos/efeitos incertos, FTS órfão, mudança após prévia,
  falha antes dos efeitos, links indevidos, entidade sem banco mental e
  interrupção sem campo de resultado além dos 200 jobs recentes da interface.
- Continuidade/contexto: **26/26**, incluindo destinatário ambíguo, confirmação
  na sessão correta, preservação de campos personalizados, ausência de replay
  e bloqueio de ferramentas não oferecidas mesmo se o modelo inventar uma chamada.
- Refinamento da Central: **41/41**, com contratos nativos internos e regressões
  de senha, exclusão parcial e cópia dos índices vetoriais temporários.

Logs completos locais: `/tmp/central-oficial-20261019-oficiais.log`,
`/tmp/central-oficial-20261019-oficiais-final.log` e
`/tmp/central-oficial-20261019-oficiais-entrega.log`. A reexecução intermediária
teve76/77: o teste de efeito incerto ainda simulava despertar após um cumprimento
“Olá”, agora sem ferramentas. A fixture passou a fazer um pedido explícito de
despertar; o grupo de112 testes voltou a passar, sem enfraquecer a trava.
Essas verificações não homologam personalidade ou convivência prolongada.

## Ensaio físico pontual de latência

Duas inferências sintéticas “Olá!”, sem chat/memória/professor, no mesmo app
Xbox `.7`, mesmos pesos/perfil/limites salvos, em ordem anterior→novo. O novo
contexto não mudou camadas, quantização, personalidade em disco ou proteções.

| Medida | Anterior | Novo |
|---|---:|---:|
| Caracteres do texto fixo | 2979 | 2682 |
| Ferramentas oferecidas nesse cumprimento | 4 | 0 |
| Tokens de entrada físicos | 1243 | 648 |
| Prefill nativo | 39,290 s | 19,504 s |
| Saída | 16 tokens | 12 tokens |
| Tempo completo da chamada | 42,109 s | 21,714 s |

Carga adicional medida separadamente:14,664s. Ambas terminaram pelo protocolo
existente, sem replay/fallback, com `reuse=0`. O app owned foi fechado e sua
saída física conferida. A primeira tentativa do script de ensaio foi recusada
localmente por alias não correspondente à seleção atual, **antes de qualquer
inferência**; não foi relaxada a conferência de versão. O ensaio foi corrigido
para ler o alias efetivamente preparado e não mudou a seleção do usuário.

É uma amostra em uma única ordem, com saídas de tamanhos diferentes, não ABBA,
mediana de várias conversas ou comparação PC/Xbox. Demonstra a redução de
prefill neste recorte, não promete a mesma melhora em todos os turnos nem
homologa qualidade/personalidade. Evidência local:
`compartilhado/runtime/ensaios/central-oficial-20261019/comparacao.json`.

## Aplicação no app

Central anterior115165 encerrada pelo endpoint cooperativo, com recibo da mesma
geração `complete` e processo realmente encerrado. Somente a janela owned115169
recebeu término após a saída do seu backend; o auxiliar de atalho saiu por EOF.
Nenhuma entidade/job foi interrompida ou acordada.

Nova Central133177, janela nativa133186, geração nova atendendo no lançador
existente. API real confirmou o novo escopo `experience-v1` pela prévia somente
leitura; **nenhum pedido de exclusão foi enviado**. As três entidades continuaram
dormindo, sem jobs/leases. Senha configurada antes/depois sem alteração do estado;
arquivos de identidade, configuração das entidades, bancos mentais e estado
mental sem escrita no intervalo. Nenhuma mensagem nova no histórico. O histórico
técnico Hoshino recebeu `shutdown.complete`, esperado na reabertura; por isso hash
byte a byte de todos os SQLite/WAL não é critério de preservação desses eventos.

Após acrescentar a guarda durável contra limpeza interrompida fora da janela
dos200 jobs, houve uma segunda reabertura cooperativa, também sem entidades
ativas: **Central136929/janela136952**. Recibo `complete`, senha e **31 arquivos
protegidos com hashes idênticos** (configurações/identidades/bancos mentais/estado),
três entidades ainda dormindo. Log local:
`/tmp/central-oficial-20261019-reabertura-final.log`. Não houve exclusão real.

## GitHub e preservação

Entrega na mesma branch privada `laboratorio-v11-organizacao-20261012`, ligada
ao PR #1 existente em rascunho, sem merge automático em `main`, force push ou
reescrita. O PR #2 de planejamento Xbox não é modificado/mesclado. Inclui também
a integração PC/PC2/Xbox, sincronização de limites e evidências de 18–19/10 já
produzidas nesta conversa. Não copia senhas, bancos, memórias, pesos, ambientes,
datasets privados, certificados locais ou logs descartáveis para o GitHub.

O app instalado usa este código local pelo lançador existente. Não se instala
outro modelo nem uma nova versão do app Xbox nesta correção de prompt/UI.
Reversão de código não restaura dados apagados; para isso seria necessária
recuperação explícita a partir do backup da operação, sem replay de efeitos.
