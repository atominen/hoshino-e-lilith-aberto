# Defaults revisados e treinos manuais — 15/10/2026

Nova autorização posterior, sem reativar esta agenda:
[ciclo manual de6h e revalidação de16/10](TREINO_MANUAL_6H_20261016.md).

## Desfecho da autorização única — 16/10 às 00:01

**Ciclo de12h NÃO iniciado.** A checagem da meia-noite foi executada na janela
correta e encontrou `allowed=false`: os quatro gates de piloto/recarga dos
6B/7B permanecem sem aprovação, a sessão anterior terminou com corte térmico
na avaliação Yi/Hoshino e os três treinos de20min não foram executados.
GPU livre e 26,41 GiB de RAM disponíveis não substituem esses requisitos.
Não houve tentativa de `/start`, sessão parcial, retry, início atrasado ou
reagendamento para outra noite. `midnight_session` continua vazio; o índice
guarda a decisão em `midnight_attempt`, com timestamp e motivos.

Os dois acompanhamentos do Codex foram **pausados** pelo mecanismo do aplicativo,
com estado `PAUSED` confirmado em ambos. Isso encerra somente o acompanhamento
desta autorização bloqueada; não aprova ou conclui os treinamentos pendentes.
Central/serviços não foram desligados nem entidades acordadas. Nenhum worker
de treino ou lease GPU estava ativo na checagem. Originais, adaptador candidato,
checkpoints, logs, bancos e evidências permanecem preservados. Sem alteração
de código de treino, parâmetros, proteções ou configurações de produção nesta
verificação. Nova execução exige resolver/reavaliar o bloqueio e nova autorização,
não simplesmente reativar a agenda antiga.

## Decisão vigente

Automação por IA **desativada**. `enabled=false` e
`automatic_data_approval=false` na política existente. Há uma opção explícita
na seção de sessão noturna do laboratório. Isso impede currículo/aprovação de
dados, treino autônomo e crítica/promoção automática após recarga. Professor
manual continua disponível, mas não será usado como pré-requisito destes
treinos. Nenhum provider externo, scheduler, banco mental ou modelo novo.

São autorizações diferentes:

1. Treinos manuais agora: Hoshino 9B, Lilith 9B e Alistair 4B, até 20 minutos
   cada, com checkpoints e validação. Early stop pode encerrar antes.
2. Ciclo manual único em **16/10 às 00:00, America/Sao_Paulo**, teto de 12 horas
   de parede, incluindo carga/avaliação. Dois Yi 6B, dois Qwen2.5 7B, dois
   Qwen3.5 9B e o Qwen3.5 4B. São sete adaptadores de entidade sobre quatro
   bases; não sete downloads. **Partir novamente dos originais**, conforme
   resposta explícita do usuário; não retomar candidatos dos 20 minutos.
3. Professor com histórico humano real: somente depois das avaliações e de
   existir uma conversa real pertinente. Não usar os textos sintéticos desta
   rodada como se fossem experiências humanas. Automação por IA permanece off.

As bases ficam intactas, candidatos separados, estáveis atuais preservadas.
Treinar não significa instalar em produção ou aprovar personalidade.

## Revisão dos datasets

Alistair tinha 51 exemplos mas apenas 17 respostas distintas, triplicadas com
prefixos superficiais. Hoshino/Lilith: 722 exemplos cada, 33 multiturno e 580
falas assistant distintas, sem interseção exata entre splits. Muitos exemplos
operacionais são compartilhados, não constituindo diferenciação de persona.

Correções no treino:

- Pergunta “Discordar de quem criou a IA é sinal de deslealdade?” respondia
  “Sim”, embora a justificativa defendesse discordar. Corrigida a polaridade.
- Três variantes do Alistair tratavam timeout como resultado confirmado.
  Agora distinguem prazo excedido de efeito mutável ainda incerto.
- Três casos por entidade tratavam dois requisitos de benchmark como prova
  suficiente de generalização. Requisitos necessários não comprovam resultado.
- Acrescentados 36 diálogos por Hoshino/Lilith e 32 do Alistair: escolhas,
  cotidiano, humor contextual, limites, silêncio, autoria, incerteza, correções
  e regras simples. Textos editoriais autorais, **não** saídas aprovadas do
  professor, não conversas reais e não biografia do usuário.

Resultado: **758 Hoshino, 758 Lilith, 83 Alistair**. Os arquivos de validação e
holdout foram preservados byte a byte; não foram usados como fonte dos novos
exemplos. Não foi feita reescrita ampla de todos os exemplos antigos: qualidade
de persona e cobertura social continuam exigindo avaliação humana. O acréscimo
não transforma um corpus pequeno em material suficiente para horas ilimitadas.

Fontes/revisão reproduzível: `laboratorio/defaults_editoriais.json` e
`laboratorio/revisao_defaults.py`. Aplicação explícita e idempotente, com
originais, hashes e relatório em
`laboratorio-local/controle-laboratorio/treinamento-unificado/reports/defaults-20261015-manual-1.json`.
Backups prévios de código/corpora em `backups/defaults-manuais-20261015/antes.tar.gz`
e originais de cada treino em `backups/defaults-20261015-manual-1/` no registro.

Tokenização real CPU, tokenizer original, zero truncamento:

| Base | Hoshino / Lilith ou Alistair | Maior sequência |
|---|---:|---:|
| Yi 6B | 758 / 758 | 194 / 185 |
| Qwen2.5 7B | 758 / 758 | 163 / 155 |
| Qwen3.5 9B | 758 / 758 | 124 / 121 |
| Qwen3.5 4B | 83 | 60 |

Todas abaixo do limite de 256 do runner. Isso só demonstra compatibilidade de
tokenização, não qualidade do corpus ou capacidade aprendida.

## Execução e gates

Mesmo `treinos_unificados`, runner NF4/ROCm, Resource Manager e supervisor da
Central. `torch.cuda` é a API HIP usada por esse runtime AMD; não há dependência
de uma GPU NVIDIA. Limite 8 GiB e margem 768 MiB inalterados, sem concorrência.
Qwen2.5 passa a poder usar **o offload congelado existente**: embedding/head CPU,
camadas textuais e adaptadores GPU, head FP32 para evitar emulação BF16 CPU.
Não há segundo mecanismo de treino. Original permanece somente leitura.

Sequência:

1. Sete smokes de dois updates, com corpora atuais separados, encerrando cada
   processo antes do próximo. Sessão `e10344b73f7b4386`.
2. Quatro pilotos de cinco minutos (6B/7B por entidade), checkpoint/recarga,
   validação e holdout completos e controle da base original sem adaptador.
   Smoke não basta para dizer que ensina personalidade ou generaliza.
3. Três treinos de 20 minutos com recargas/avaliações separados.
4. À meia-noite, somente se os gates de adequação e recursos estiverem atendidos:
   `default_cycle_plan(...,nightly=True)` prepara 14 tarefas sequenciais,
   treinamento e avaliação por candidato. Preparar **não executa**.

Noite: até 80 minutos de treino por modelo + até 15 de avaliação, com folga
na janela de 720 minutos para carga/drenagem. Parar em deterioração repetida
da validação ou três epochs; não repetir exemplos só para ocupar doze horas.
Um candidato 6B/7B só é elegível após piloto de pelo menos oito updates,
recarga física, hashes do corpus/base/adaptador correspondentes, comportamento
determinístico atendido e sem regressão >2% em validação/holdout contra a base.
Isso é gate técnico conservador, não prova de naturalidade.

Não sobrepor sessões. Se um job falhar, for interrompido ou ficar incerto,
não repetir treinamento automaticamente. Relacionar a falha ao registro e
checkpoint. Acordar/restaurar somente quem estava acordado antes; nestes
smokes o conjunto era vazio. Não desligar o computador nesta rodada.

### Medições físicas já encerradas

Sete smokes na RX 6650 XT, dois updates por par, sem OOM, sem pressão registrada,
exit code zero e liberação física da GPU antes do próximo. Pico abaixo é VRAM
total observada por amdgpu, **não** apenas a memória alocada pelo Torch.

| Entidade / base | Job | Loss amostral antes → depois | VRAM física pico | Carga |
|---|---|---|---:|---:|
| Hoshino Yi 6B | `932424f4953a4591` | 3,0494 → 3,0250 | 5,266 GiB | 80,7 s |
| Lilith Yi 6B | `63f3cb3cd58744b3` | 3,0421 → 3,0099 | 5,263 GiB | 21,4 s |
| Hoshino Qwen2.5 7B | `ee69bc5fcf8d446d` | 4,7122 → 4,6900 | 4,987 GiB | 25,4 s |
| Lilith Qwen2.5 7B | `d842c0b264d64816` | 4,5480 → 4,5265 | 5,013 GiB | 16,1 s |
| Hoshino Qwen3.5 9B | `7b924c659ecc4d54` | 3,1289 → 3,1290 | 5,425 GiB | 26,0 s |
| Lilith Qwen3.5 9B | `aa1fe12579b94430` | 2,8782 → 2,8771 | 5,428 GiB | 15,4 s |
| Alistair Qwen3.5 4B | `d0c6469c9daa4be1` | 3,9503 → 3,9519 | 4,890 GiB | 14,7 s |

As duas pequenas pioras foram preservadas. Losses de tokenizers/bases distintos
não são um ranking de personalidade; dois updates não comprovam generalização.
RAM disponível mínima nos smokes: 15,58 GiB. Swap ocupada chegou a 5,96 GiB,
apesar da RAM livre; isso é ocupação observada, não prova isolada de thrashing.
O monitor guarda contadores de paginação para análise posterior. Hotspot máximo
nos smokes: 84 °C. A primeira carga fria foi mais lenta; não extrapolar seus
80,7 segundos para todos os reloads.

### Falha real do piloto e correção térmica

A sessão `988a8056d2644145` não passou: o primeiro piloto Yi 6B/Hoshino atingiu
hotspot **101 °C**, ultrapassando o corte conservador existente de 100 °C. O
monitor enviou parada cooperativa, salvou o update **67**, confirmou saída zero
do filho e liberação da GPU. Job `e9cfa2cc476048b8` ficou
`cancelled_checkpointed`, não concluído. Sem OOM nem parada forçada. VRAM
física pico: 5,520 GiB; RAM disponível mínima 16,23 GiB. Loss amostral
3,1186 → 2,1793 não transforma esse treino interrompido em aprovação.

Correção pequena no runner existente: `cool_before_work` consulta os mesmos
sensores antes de cada update, amostra de avaliação e caso de geração. Cede
compute próximo do limite, com histerese, prazo de 60 segundos e cancelamento.
O corte original continua imposto pelo monitor pai; não foram alterados
ventoinhas, potência, driver, VRAM ou Resource Manager. Tempo de resfriamento
é contabilizado à parte, nunca como otimização efetiva. Isso pode reduzir
throughput e não garante que um kernel longo não atinja o corte.

Quatro regressões isoladas cobrem histerese/corte inalterado, caminho frio,
prazo/cancelamento e perda de sensor. Depois da correção e da verificação de
SHA/otimizador/RNG, apenas o checkpoint confirmado foi retomado: sessão
`87fb5cdc16444a1a`, job `48b87c29351c44ca`. **Também interrompida**: avançou
67 → 90, mas atingiu 103 °C. Salvou checkpoint90, filho exit0, sem parada
forçada e GPU liberada. Foram 65,55 s adicionais de otimização, 11,14 s de
espera térmica e loss final amostral 2,0931. Não aprovar esse perfil longo:
ceder entre unidades não impediu pico dentro de uma unidade. As duas falhas
continuam registradas; nenhuma recarga/holdout aprovada foi fabricada.

Investigação seguinte, limitada: configuração/implementação local confirma que
Yi-1.5-6B-Chat é `LlamaForCausalLM` e usa os mesmos nomes de embedding/head já
atendidos pelos hooks de offload existentes. A allowlist foi estendida apenas
a esse caso. Probes `head_cpu=1` das duas entidades na sessão
`e3bee3b272b442ef`, antes de outro piloto salvo. Camadas textuais/LoRA continuam
GPU; embedding/head congelados CPU FP32. O perfil reduz carga GPU potencial,
mas ainda precisa ser medido. Se falhar, não há autorização implícita para
remover a proteção ou repetir indefinidamente. Os checkpoints antigos não
podem retomar mudando de offload; o novo piloto começa dos originais.

Os dois probes terminaram: Hoshino `1297009db0fd4fd3`, pico físico 4,421 GiB,
hotspot 82 °C; Lilith `054f006d0c0c4d68`, 4,538 GiB e 83 °C. Dois updates,
exit0, sem pressão, sem parada forçada, GPU liberada. O preset medido de ambas
passou a `head_cpu=true`. São evidências do novo offload curto, não de cinco
minutos/recarga ou doze horas estáveis.

Reconciliação de **15/10 às 23:20**: não existia outro worker nem piloto salvo
concluído. A sessão atual de pilotos é `d4ebc6127fa64307`, oito tarefas,
Yi/H, Yi/L, Qwen2.5/H e Qwen2.5/L, todos dos originais, cada treino de até
cinco minutos seguido de recarga/validação/holdout. Hashes de base e corpora
conferidos com o índice antes da partida. Os treinos de 20 minutos e o ciclo
de sete modelos ainda **não começaram**. Se as etapas anteriores permanecerem
pendentes à meia-noite, o disparo deve registrar bloqueio, não sobrepor jobs
nem declarar os sete modelos adequados só para cumprir o horário.

### Acompanhamento e disparo único

**Bloqueio confirmado em 15/10 às 23:41:** a avaliação independente
`4bb4ecb5ab344529` falhou. O monitor registrou hotspot **100 °C**, no corte
existente, e enviou SIGTERM ao filho (`child_exit_code=-15`, propagado como
código241 pelo processo externo). Duração física 685,04 s; pico de VRAM
**4,469 GiB**, RAM disponível mínima 16,483 GiB. Não houve parada forçada.
O processo encerrou e liberou a GPU/lease; nenhum worker permaneceu ativo.
Não classificar isso como OOM ou incompatibilidade do modelo: a causa
registrada da interrupção foi o corte térmico.

O log preservou validação completa de 131 exemplos (loss 2,1141) e holdout de
104 (2,1346, 115,32 s). **Isso não é avaliação aprovada:** a sequência de
geração/controle comportamental e comparação com a base não terminou e não
existe relatório final de avaliação. O aviso de `model.device=cpu` com inputs
GPU acompanha o offload, mas não comprova a causa da falha. Não alterar o
executor automaticamente com base apenas nesse aviso.

A sessão `d4ebc6127fa64307` ficou `completed_with_errors`, índice1 de8. Yi/Lilith
e os dois pilotos Qwen2.5 7B **não chegaram a executar**, portanto não estão
reprovados nem homologados. O treino salvo Yi/Hoshino e todos os checkpoints
continuam preservados, sem promoção. O índice registra o bloqueio e o SHA da
telemetria, não altera o desfecho do supervisor.

Os treinos de20min **não foram iniciados**, por falta da conclusão segura dos
pilotos; a pré-checagem dos sete treinos continua bloqueada por quatro gates
de piloto/recarga/comportamento. Não repetir, retomar, substituir parâmetros,
afrouxar proteção ou iniciar parcialmente a noite. O disparo de meia-noite
deve confirmar o impedimento, não transformar a agenda em autorização para
ignorar essa falha. Automação por IA, cloud, concorrência e desligamento
continuam off. Hashes dos corpora, assinaturas/configs das quatro bases e
hashes dos três bancos mentais permanecem iguais aos registrados.

Atualização **15/10 às 23:31**: o primeiro piloto salvo do novo perfil Yi/Hoshino
terminou, job `cdbf18c6ff1e46b0`: **87 updates**, 247,38 s de otimização,
317,95 s na fase cronometrada (inclui validação/checkpoints), carga 15,35 s.
Loss de monitoramento de 16 exemplos: 3,1174 → 2,1052. Telemetria física:
VRAM pico **4,813 GiB**, hotspot máximo **96 °C**, RAM disponível mínima
15,558 GiB, `pressure=[]`, exit0, sem parada forçada ou cancelamento.
O candidato foi salvo e o supervisor iniciou a recarga independente
`4bb4ecb5ab344529`. A validação completa de 131 exemplos já foi executada
(loss 2,1141, 146,7 s); holdout, comparação com a base e contratos de resposta
ainda estão em andamento. Portanto **treino curto concluído, candidato não
aprovado**. Não houve novo piloto duplicado nem partida dos treinos de 20 minutos.
Hashes de todos os corpora e assinaturas/configs das quatro bases conferem com
o índice desta autorização. Nenhum código de treino foi alterado durante o job.

O índice privado `plans/manual-sequence-20261015.json` liga as sessões, hashes
de corpus/base e correção térmica. É apenas referência de observação; a verdade
de execução continua nos jobs e na sessão do supervisor. Não editar
`nights/current.json` por fora do supervisor ativo.

Foram criados dois acompanhamentos nesta conversa pelo mecanismo do Codex:

- `acompanhar-treinos-manuais-de-15-16-10`: verifica a cada dez minutos;
  após os pilotos encerrados, inicia uma única sessão manual 9B/9B/4B de até
  20 minutos, com avaliações e sem professor. Falha incerta não dispara retry.
- `treino-manual-nico-meia-noite-de-16-10`: disparo único em 16/10 às 00:00;
  revalida pilotos, hashes, etapas anteriores, espaço e recursos. Só inicia
  os sete pares se o plano estiver liberado. Se a janela for perdida ou algum
  gate falhar, relata o bloqueio; não sobrepõe jobs nem transfere a autorização
  para outra noite. O teto termina às 12:00, inclusive em partida ligeiramente
  atrasada.

Enquanto os acompanhamentos estavam ativos, computador, aplicativo Codex e
Central/supervisor precisavam continuar disponíveis. Agora ambos estão pausados,
sem trabalho de treinamento em execução. Nenhuma sessão de20min ou de12h foi
declarada concluída ou iniciada só por criar o agendamento.

## Conhecimento novo, por exemplo JavaScript

SFT/LoRA pode incorporar habilidades/conhecimento a partir de exemplos, não só
tom de fala. Porém estar em memória ou num documento não implica estar nos
pesos. Não treinar diretamente cada lembrança ou reflexão como verdade.

O caminho existente pode ser usado: selecionar material autorizado com fonte
e confiança → organizar exemplos/exercícios verificáveis → corpus versionado
separado do teste → treino candidato → executar exercícios JavaScript inéditos
em sandbox → comparar base/candidato, autoria/persona e capacidade geral →
aprovar ou manter a estável. Explicações erradas ou código não executado não
viram rótulos positivos. Preservar treino de identidade e medir esquecimento.
Fatos mutáveis e informações pessoais devem continuar na memória recuperável,
não serem decorados indiscriminadamente nos pesos.

Nesta rodada isso é **proposta/metodologia**, não integração de aprendizado
autônomo já comprovada. Não foi misturado conteúdo JavaScript arbitrário aos
defaults de personalidade. Referência técnica: [SFT Trainer oficial](https://huggingface.co/docs/trl/main/en/sft_trainer)
e [estudo sobre esquecimento em LoRA](https://arxiv.org/abs/2512.17720).

## Organização, limpeza e limitações

Históricos, relatórios, modelos e bancos preservados. Foram removidos **17
diretórios de caches descartáveis de código, 6.955.008 bytes** (~6,63 MiB), nas
áreas app/laboratorio/scripts/testes. São regeneráveis. Nenhum cache de pesos,
dataset, ambiente, backup, KV/RAM validado ou cache global do sistema foi apagado.
A pasta grande continua contendo os pesos intencionalmente preservados.

Validação offline: baseline **296/296** antes das alterações; nove regressões
da rodada levaram a **305/305**, e as quatro térmicas a **309/309** (12,774 s).
O grupo de navegador também confirmou leitura inicial da política salva,
checkbox de IA desligado e formulário bloqueado até consulta bem-sucedida.
A suíte oficial passou **74/74** antes e depois do primeiro ajuste térmico.
Uma regressão adicional cobre o mapeamento Yi autorizado e a manutenção das
camadas/LoRA na GPU. Última suíte do laboratório: **310/310**, 11,919 s,
exit0. São 14 regressões novas desde o baseline296; não 14 grupos oficiais.
Logs locais: `/tmp/defaults-tests-completos-20261015.log` e
`/tmp/defaults-suite-oficial-20261015-final.log`. Houve falhas intermediárias de
fixtures que dependiam da autorização automática antiga e um acesso indevido
do mock à chave `action`; corrigidos explicitando autorização em ambientes
temporários e preservando o contrato dos consumidores, não retirando asserts.

Hashes dos três bancos mentais continuam idênticos aos anteriores. Nenhuma
entidade foi acordada para os smokes/pilotos, nenhum candidato foi instalado
em produção e nenhuma proposta rejeitada/pendente do professor entrou no treino.

Atualizar os resultados dos pilotos e treinos na continuação. Não considerar a
rodada inteira encerrada enquanto recargas, avaliações e sessões autorizadas
continuarem pendentes. Naturalidade e qualidade de persona exigem avaliação humana.

## Arquivos desta rodada

- Política/execução existentes: `laboratorio/rotina_noturna.py`,
  `treinos_unificados.py`, `treino_nf4_curto.py`, `alistair.py`, `painel.py`.
- Revisão local e rastreável: novos `laboratorio/revisao_defaults.py` e
  `laboratorio/defaults_editoriais.json`; limpeza restrita em `limpeza_segura.py`.
- Mesma UI: `laboratorio/web/index.html`, `app.js`. Opção de IA, preparação do
  plano manual e carregamento da política real antes de permitir salvar.
- Regressões: `laboratorio/tests/test_consolidacao.py`, `test_noite_supervisor.py`,
  `test_personalizacao_moe.py` e `browser.cjs`.
- Navegação/documentação: `README.md`, `laboratorio/README.md`, `docs/README.md`
  e este relatório. Demais mudanças preexistentes no checkout foram preservadas.

Captura da configuração real (não simulação DOM):
`/tmp/laboratorio-automacao-desligada-20261015.jpg`. Abrir a UI não iniciou
professor nem entidade. A reprodução física do treino não comprova qualidade
emocional; ler os diálogos das recargas ainda será necessário.
