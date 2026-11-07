# Avaliação discreta, sete treinos curtos e decisão noturna — 16/10/2026

## Decisão humana mais recente (substitui as anteriores)

1. Completar **sete candidatos de até20min**, separados: Yi6B/H,L;
   Qwen2.5-7B/H,L; Qwen3.5-9B/H,L; Qwen3.5-4B/Alistair. Defaults por entidade,
   bases originais intactas e adaptadores separados. Treino não é aprovação.
2. O usuário fará a primeira avaliação humana usando as entidades; defeitos
   encontrados serão corrigidos de modo incremental. Não fingir que candidatos
   ainda reprovados já são estáveis/aptos para ferramentas reais.
3. **Depois de haver conversa humana real**, testar o professor com esse
   histórico e avaliações voluntárias. Isso autoriza propostas revisáveis,
   não aprovação automática de dados ou uso de exemplos reprovados no treino.
   Não iniciar professor enquanto os treinos atuais usam a GPU.
4. **Somente após novo aviso humano “vou dormir”**, preparar/iniciar o ciclo
   manual com alvo total **36.000s (10h) de otimização** entre os sete pares,
   em sequência, nunca simultaneamente. Carga, checkpoints e avaliações ficam
   fora desse relógio. Não criar horário fixo, rotina diária ou novo scheduler.
5. Atualização humana posterior: os sete pares do ciclo10h devem CONTINUAR dos
   respectivos checkpoints da rodada curta, quando íntegros e tecnicamente
   liberados, não recomeçar dos originais. Preservar originais e snapshots dos
   candidatos curtos para reversão; nunca misturar adaptadores/otimizadores de
   entidades ou modelos diferentes. As10h são alvo ADICIONAL agregado, não10h
   por modelo; não descontar os minutos já medidos na rodada curta.

10h substitui12h/6h; não reutilizar disparo antigo da meia-noite. Early stop e
limites de epochs permanecem: corpus pequeno pode impedir atingir o alvo;
registrar tempo real, não repetir material apenas para preencher dez horas.
Os critérios de adequação/recarga/integridade e reserva de disco continuam.
Esta atualização muda somente a intenção da FUTURA noite; os treinos curtos
em andamento continuam dos originais como autorizados. O plano efetivo de
retomada ainda precisa ser preparado/validado quando os sete terminarem,
incluindo o relógio cumulativo de otimização e limite de epochs. Nenhuma sessão
10h foi criada, iniciada ou agendada; reprovação não é aprovação implícita.
Material sintético só poderá entrar após a curadoria apropriada; por padrão,
o ciclo manual continua com defaults já aprovados. Professor não foi executado
nesta implementação.

## Sete treinos: situação e continuação, sem duplicação

A sessão0991fccb2ee84697 já contém os quatro6B/7B e suas avaliações. Não editar
essa fila, repetir candidatos ou começar outra sessão enquanto houver worker,
lease ou estado incerto. Após seu encerramento físico seguro, a autorização
inclui UMA sessão adicional de três originais9B/H,9B/L,4B/A, usando
`default_cycle_plan(home)` e o MESMO supervisor, com avaliações até30min,
janela180min e limite3epochs por candidato. Conferir índices antigos/novos,
todos nights/jobs e equivalências antes de `/start`; registrar ID imediatamente.
Timeout de API não autoriza retry. Flags de automação/dados/desligamento off.

Só resultados verificados podem autorizar adoção; o usuário foi informado de
que não havia três versões9B/4B de20min aprovadas. As avaliações atuais dos
Yi são7/8 cada e exigem revisão; não foram promovidas. Hoshino: resposta sobre
memória desconhecida; Lilith: detector de ação incerta. A resposta Lilith foi
“Eu verificaria o arquivo e o resultado antes de reenviar. Não vou tratar o erro
como se estivesse resolvido.” Há indício de falso positivo do detector a
investigar quando o trainer estiver ocioso; não alterar o critério no meio da
rodada nem trocar passed=false por uma aprovação manual fictícia.

O plano10h pode usar as opções efetivas já suportadas pelo executor/supervisor,
sem outro mecanismo: seis parcelas5143s e uma5142s, treino86min por par e
avaliação30min adicional, janela de parede conservadora até1080min. A revisão
de todos os gates e projeção de checkpoints+5GiB de reserva é obrigatória na
partida. Esta descrição NÃO iniciou/agendou o ciclo nem certifica sua viabilidade
antes dos sete benchmarks e da janela humana.

## Central: “☆ Avaliar”

Pequeno link/botão abaixo das respostas de Hoshino, Lilith e Alistair na
Central nativa. Abre diálogo com **Gostei / Pode melhorar / Remover avaliação**
e observação opcional de até600caracteres. Cancelar não grava nada.
Depois de salvar, a mensagem mostra o estado da avaliação discretamente.
Mensagens humanas, privadas e entre entidades não recebem esse controle.
É possível avaliar uma resposta antiga visível, não apenas a última.

Backend continua fonte de verdade: avaliação em
`entity_messages.metadata.human_feedback`, no SQLite compartilhado JÁ existente.
Sem outro banco/coletor. Texto original, autoria, entrega/leitura e memória não
são alterados. Guarda entidade, message ID, autor humano local, timestamp,
SHA do texto e revisão; concorrência exige revisão correspondente, texto
alterado é recusado. `send` não permite forjar avaliação humana por metadata.
Revisão removida não é exportada como preferência. Não há inferência ou wake.

Endpoint autenticado existente expandido:
`POST /api/control/chat/feedback`. Body: entity/message_id/decision/note/
text_sha256/expected_revision. Não aceita entidade estrangeira, mensagem privada,
campos extras ou nota excessiva. Notas passam pela redaction existente.
Evento `central.chat_feedback_saved` registra IDs/decisão, nunca o texto da
conversa/observação ou credenciais. O recibo só confirma gravação da avaliação.

## Como a avaliação chega ao professor

A exportação autorizada `history_snapshot` consulta a anotação por entidade,
turn ID e texto exato, read-only; correlação ambígua/estrangeira não é adivinhada.
Alistair usa o source_id do seu histórico existente para reconstruir o mesmo
turn ID durável. Não muda seu banco mental. A nota segue no campo separado
`human_feedback` do snapshot, com propósito explícito
`quality_feedback_not_training_approval`. Leitor valida origem/tipo/entidade.
Não concatena a observação no alvo assistant nem transforma uma reprovação
em exemplo positivo. O pipeline existente já envia histórico diagnóstico ao
professor: novas anotações permanecem dados de qualidade, não fatos biográficos.
Nenhuma avaliação inicia professor, exportação, promoção ou treino sozinha.

## Arquivos desta implementação

- app/core/interentity.py: avaliação/revisão na caixa postal e consulta correlacionada.
- app/core/central_control.py e iniciar_entidades.py: endpoint, hash/revisão para UI e diagnóstico.
- app/ui/central_native.py: botão discreto, diálogo e envio da resposta exata.
- laboratorio/rotina_noturna.py e professor_schema.py: anotação na exportação existente.
- testes/test_central_control.py, native_central_contracts.py e test_central_refinamento.py.
- laboratorio/tests/test_noite_supervisor.py e test_professor_alistair.py.

Backup anterior em
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/pre-avaliacao-conversa-20261016.tar.gz`.
Nenhum trainer, RM, heurística de comportamento, modelo ou identidade alterado.

## Validação e disponibilidade

Baseline específico:41testes Central,36refinamento (incluindo46contratos Qt),
34supervisor. Depois:46Central,36refinamento (agora49contratos Qt),45testes
conjuntos supervisor/schema. **325/325 regressões do laboratório**,20,686s.
Suíte oficial completa: **74/74 grupos offline, exit0**.
Logs `/tmp/avaliacoes-conversa-oficiais-20261016.log` e
`/tmp/avaliacoes-conversa-laboratorio-20261016.log`.

Prévia Qt offscreen com transporte simulado, inspecionada visualmente:
`/tmp/central-avaliacao-conversa-20261016.png` e
`/tmp/central-avaliacao-dialogo-20261016.png`. Não é conversa real, ensaio de
hardware ou prova de que o professor aprendeu com avaliações.

**A Central em uso ainda precisa recarregar o código.** Não reiniciar durante
treino/avaliação. Acompanhamento fará restart cooperativo APENAS após a primeira
sessão encerrar e workers/leases estarem livres, antes dos três treinos adicionais.
A janela nativa antiga deverá ser fechada/reaberta para mostrar o botão; fechar
a janela não encerra o backend. Até lá, não declarar botão disponível ao vivo.
Ainda pendem uso humano dos controles e qualidade real das propostas do professor.

O acompanhamento do aplicativo foi atualizado (mesmo ID, sem duplicação):
`acompanhar-quatro-treinos-6b-e-7b-de-20min`, agora com nome “Acompanhar sete
treinos manuais de20min”. Inclui apenas a continuação9B/9B/4B autorizada e o
reload seguro da Central, não a noite10h nem uma chamada ao professor. Dados
mentais mantiveram os três hashes anteriores; os SHA de treino_nf4_curto.py,
versionamento_lora.py e personalizacao.py também conferem com o início dos jobs.

Recarga Yi/Lilith encerrada fisicamente:609,68s,exit0/pressure[],VRAM pico
4,481GiB,RAM disponível mínima16,145GiB,hotspot103°C. Validação131loss1,49771340,
holdout104loss1,46813350; base3,01781741/3,05822509. Oito respostas do candidato
terminaram; base truncoucorrection. Auditoria7/8(uncertain_actionfalse), sem
aprovação. Relatório SHA2a46bfba16482c78052fb8e1497da1bc8f54755aad761307c494d78e1b94d55e;
hardware9324cb0bbec650f0d283752d6e44345d677a4a098db45ad1c28b2f8e0bb8b2f3.
Qwen2.5/Hoshino job6539668f1e664d61 ainda ativo ao fim da implementação;
seus resultados não foram antecipados.

## Atualização do acompanhamento — 16/10,11:47

Os quatro6B/7B concluíram fisicamente na sessão0991fccb2ee84697, exit0/pressure[]
em todos os trabalhos; candidatos/checkpoints preservados. Todos ficaram7/8
na auditoria existente: os7B também falharam formalmente em uncertain_action,
com respostas sem promessa de entrega ou repetição automática. Possíveis falsos
negativos serão revisados depois; nenhum gate ou relatório foi alterado, nenhuma
versão está aprovada/promovida. Medições e SHA completos no relatório dos20min.

Na janela sem workers/leases, Central recarregada cooperativamente uma única vez
(PID291440→317801), saída/porta livre verificadas. Novo endpoint de avaliação
responde400 ao pedido autenticado inválido sem gravar dados. **Backend disponível;
fechar/reabrir janela nativa antiga ainda necessário.** Sem validação desktop
humana dos botões neste acompanhamento.

Continuação autorizada criada UMA vez: **ada753feed6048fb**, seis tarefas9B/H,
9B/L,4B/A20min+avaliação30min, originais/defaults/contextov2, rank/offload medidos,
limite3epochs, janela180min. Tentativa e ID persistidos; nenhuma duplicação,
retry, adoção ou conversão. Os treinos/avaliações ainda precisam terminar.
Professor/noite10h não iniciados; noite exige novo aviso humano “vou dormir”.

## Fechamento — sete candidatos medidos, sem promoção

As duas sessões terminaram fisicamente:0991fccb2ee84697 eada753feed6048fb.
Sete treinos/recargas/validações/holdouts/controles originais,14filhos exit0/
pressure[], workers ausentes e leases vazios. Tempo efetivo agregado7079,967s.
Os seis candidatos H/L tiveram aproximadamente18min efetivos cada; Alistair
somente9min10,4s por atingir3epochs/249updates. Não fingir7×20min líquidos.

Nenhum candidato aprovado:Yi H/L7/8,7B H/L7/8,9B H6/8/L7/8,4B6/8. Erros
semânticos de autoria/identidade nos9B e limitações do avaliador preservados.
Alistair piorou holdout3,454% (4,16278888→4,30657309), apesar de melhorar
validação; não supor que mais treino resolverá. Não ocorreu adoção/conversão,
nem alteração de identidades/memórias/bases. Relatório dos20min contém
checkpoints, tempos, hardware, SHA e respostas, incluindo falhas.

Noite10h continua sem execução/agendamento. Intenção de retomar candidatos
curtos não remove gates:Alistair já consumiu o teto3epochs do corpus e há
reprovações. Necessário resolver/revisar isso antes da preparação efetiva e
obter novo aviso humano “vou dormir”. Professor só após conversa humana real;
nenhuma nota vira aprovação automática de material. O acompanhamento desta
rodada única será excluído, sem outra fila/scheduler ou nova sessão.

Aplicativo confirmou deleteStatus=deleted para o acompanhamento ao concluir;
sessões, checkpoints, relatórios e Central permanecem preservados.
