# Congelamento de escopo — 06/10/2026

## Descongelamento de 05/11/2026 (pedido humano)

O proprietário descongelou a linha principal: "vamos descongelar o projeto,
aplicar a mudança, testar todo o projeto". O congelamento de 04/11 abaixo é
histórico. Continuam valendo as regras permanentes: preservar memórias,
identidades e bancos; recarregar só com drenagem cooperativa; um implementador
por área; nada de download, treino ou troca de modelo sem pedido.
[Orçamento adaptativo e resultado da suíte](docs/ORCAMENTO_ADAPTATIVO_20261105.md).

**05/11, modelos:** a pedido humano ("pode apagar todos os outros modelos que
não seja o 9b e o 4b e os checkpoints"), foram apagados:
- o Qwen3-6B SNIPER, o que substitui a preservação de 24/10;
- os restos de Yi, Hunyuan, 7B e professor 27B;
- os checkpoints e adaptadores treinados e os aliases de recuperação;
- a conversão antiga do 9B da Lilith;
- os três candidatos descartados do intermediário;
- a fonte do Andy.

Por escolha dele, ficaram:
- os 9B em uso (Hoshino sem censura; Lilith no 9B oficial);
- o 4B do Alistair;
- o professor 35B;
- o intermediário 2B, cuja ideia de corretor de ações não foi abandonada, assim como a rede do Pestinha;
- os modelos de voz, escuta e imagem.

## Congelamento temporário de 04/11 — experimento Pestinha (encerrado em 05/11)

A linha principal fica congelada durante o ensaio. O código local em andamento
é a base de referência, incluindo as alterações ainda sem commit. O trabalho
experimental fica no laboratório de scripts, com entradas sintéticas e um
executor temporário do modelo local. A implantação na Central, os estados das
entidades e as configurações vigentes ficam fora do ensaio.

[Inventário, protocolo e resultado](docs/ENSAIO_ENTIDADE_PESTINHA_20261104.md).
O proprietário pausou também os ensaios. Retomar inferências, treino ou
integração exige nova solicitação. A
[nota de pausa e pesquisa](docs/TRAJETORIA_REDE_PULSADA_20261104.md#pausa-do-ensaio)
registra o último resultado e as opções para mudar a tomada de decisão.

**05/11, liberação parcial a pedido humano:** foram implantados a correção da
percepção de apps, a habituação e sensibilização afetivas e o corpo pulsado dos
orbes. Decisão, prompt, modelos, treino e Central continuam fora.
[Resultados e o que mudou](docs/TRAJETORIA_REDE_PULSADA_20261104.md#retomada-de-0511-onde-a-rede-se-justifica).

## Decisão vigente final de27/10/2026 — 4B e9B, professor como exceção

Hoshino e Lilith têm9B principal e4B leve. Alistair mantém seu4B e destino.
O professor é outro caso: seus pesos são preservados, sem início automático.
Autorizada remoção dos outros pesos conversacionais, inclusive o6B antes
preservado e o7B. Memórias, identidades, datasets, código e relatórios permanecem.
[Estado atual](docs/ORGANIZACAO_4B_9B_20261027.md). As decisões abaixo são histórico
e não autorizam baixar de novo os pesos removidos ou iniciar treinos.

## Histórico de24/10/2026 — somente 7B e 9B na troca dinâmica

O proprietário encerrou a busca/integração de um terceiro executor por agora:
**Hoshino e Lilith alternam somente entre seus 7B e 9B existentes**. Alistair
conserva seu mesmo 4B e destino configurado. Esta decisão substitui a exigência
anterior de 6B + 7B + 9B, preservada abaixo como histórico.

**Não apagar o Qwen3-6B SNIPER baixado.** Seus originais e resultados ficam
preservados como pesquisa, fora da rota automática, sem treino, conversão,
nova avaliação ou ativação implícitos. Não há novo modelo a baixar nem ciclo
a iniciar. [Estado e limpeza pontual](docs/SUBSTITUICAO_YI_EXECUTOR_RAPIDO_20261024.md).

## Substituição autorizada de24/10/2026 — retirar Yi e avaliar executor rápido

O proprietário autorizou apagar o Yi e buscar um modelo confiável, mantendo
originais treináveis. Sua correção explícita exige **6B + 7B + 9B para Hoshino
e Lilith**, com o 6B consideravelmente mais rápido que o 7B atual; não reduzir
para 4B nem acrescentar 8B nesse papel. **Alistair mantém seu mesmo modelo 4B**,
sem rodízio entre famílias. Yi retirado; relatórios e outras famílias preservados.
Qwen3-4B foi ensaiado por interpretação equivocada do assistente: seus pesos,
GGUF e alias foram posteriormente removidos por pedido explícito do proprietário,
com relatórios preservados e reinstalação por planos antigos bloqueada.
O novo 6B ainda está pendente; a pesquisa não autoriza sua ativação. Download e
testes não aprovam treino, promoção ou ativação por si.
[Remoção, origem e critérios](docs/SUBSTITUICAO_YI_EXECUTOR_RAPIDO_20261024.md).

Depois da triagem, o proprietário autorizou **baixar e testar Qwen3-6B SNIPER**
isoladamente. Originais verificados, mas os testes NF4 e a compatibilidade de
conversão não o homologaram. Nenhuma troca ativa, treino ou promoção.
[Resultado e limites](docs/ENSAIO_QWEN3_6B_SNIPER_20261024.md).

## Complemento explícito de24/10/2026 — integrar e testar o Yi6B

O proprietário autorizou integrar o Yi existente e executar os testes básicos.
O suporte de terceiro executor foi implementado, com recibo por entidade e
gates de contexto/capacidades/recursos. Os ensaios reais reprovaram; portanto
o Yi continua desabilitado na troca automática, sem alterar seus pesos ou
forçar aprovação. A autorização não inclui outro treino/download/reexport.
[Resultados e operação](docs/YI6B_INTEGRACAO_E_TESTES_20261024.md).

## Ampliação explícita de24/10/2026 — perfis dinâmicos de recursos

O proprietário autorizou verificar a troca de modelos e tornar o gerenciador
dinâmico com predefinições conforme a necessidade. A primeira etapa ajusta
custos de escolha no RM existente, com histerese e registro por tarefa. Não
aprova rodízio obrigatório dos sete, nova rota automática Yi, concorrência
GPU, novo modelo/serviço ou alteração de identidade/memória/treinamento.
Reservas e perfis físicos medidos continuam sujeitos aos gates anteriores.
[Implementação, auditoria e reversão](docs/PERFIS_DINAMICOS_RECURSOS_20261024.md).

## Ampliação explícita de23/10/2026 — autonomia e continuidade individuais

O proprietário considerou fracassado o teste de iniciativa da manhã e autorizou
começar uma grande mudança, inclusive extrapolando o refinamento anterior.
Hoshino e Lilith devem poder escolher interesses/atividades, criar e executar
projetos, conversar e manter continuidade sem depender de ordens a cada passo.
Notas/comentários curtos servem para **recuperação de contexto**, não para
fabricar ações ou aprovar comportamento pela quantidade de texto. Identidade
e autoria das experiências continuam individuais. Alistair mantém seu papel
de apoio, sem copiar toda a dinâmica das outras duas.

Esta decisão prevalece sobre o congelamento histórico para a evolução do
controlador, ferramentas cognitivas e continuidade. Não autoriza por si só
compra, quota, publicação/contato com terceiros, instalação de modelos,
treinamento extra, acesso às memórias alheias ou remoção das proteções físicas.
Agendamento noturno, modelos, identidades, bancos e evidências preservados.
[Primeira implementação e limites reais](docs/AUTONOMIA_CONTINUA_E_CONTEXTO_20261023.md).

## Exceção explícita de18/10/2026 — Alistair4B noXbox

O proprietário autorizou oficializar o executor4B ensaiado noXbox, seletor de
destino naCentral existente (PC/PC2/Xbox), sincronização técnica e inicialização
ao acordarAlistair. Banco/identidade/memórias/histórico/ferramentas continuam noPC;
PC2 e originais preservados. Sem professor/treino/cloud ou aprovação automática
de qualidade. [Contrato e reversão](docs/ALISTAIR_DESTINO_E_SINCRONIZACAO_20261018.md).
As regras anteriores seguem vigentes fora desta exceção.

Esta era a última expansão de arquitetura autorizada em18/10. A ampliação
de23/10 acima substitui essa restrição para autonomia e continuidade; as
seções originais abaixo permanecem como referência fora da nova autorização.

## Executores aprovados

- Hoshino: Qwen3.5 9B principal existente + `hoshino-qwen2.5-7b:latest` leve.
- Lilith: Qwen3.5 9B principal existente + `lilith-qwen2.5-7b:latest` leve.
- Alistair: Qwen3 4B existente, CPU obrigatória e GPU oportunista local.

Os dois leves usam Qwen2.5 7B Instruct Q4_K_M e possuem cópias físicas e
catálogos independentes. Identidade, memória, relações e estado continuam
nos arquivos/bancos de cada entidade, nunca nos pesos de um executor.

Nenhum sexto executor textual, novo modelo de voz/visão/imagem, capacidade,
ferramenta, serviço ou sistema deve ser acrescentado sem uma revisão explícita
deste congelamento pelo usuário. Os modelos/capacidades anteriores permanecem
preservados. Cloud de capacidades continua desativada; Azure TTS opcional da
etapa anterior e os fallbacks locais não foram substituídos.

## Trabalho permitido

Somente bugs, desempenho, latência, memória, naturalidade, scheduler, UI,
testes e integração das capacidades já existentes. Ajustar contexto, margens
e custos observados não autoriza baixar outros modelos ou ampliar capacidades.

## Invariantes

- Um executor é escolhido antes da inferência e fixado durante a resposta,
  suas ferramentas, retries e verificação final. Falha não troca executor no
  meio da resposta; CPU/GPU podem mudar entre chamadas completas do mesmo modelo.
- Complexidade incerta/importante, tarefas operacionais, visão e reflexões
  profundas conservam o 9B. Trabalho simples pode usar 7B; principal quente
  pode ser mais barato do que unload/reload.
- Pesos residentes em VRAM não são um lease de compute. Compute termina ao
  acabar a chamada. Estado observado distingue GPU resident, RAM resident,
  unloaded; métricas vencidas/incertas são explicitamente unknown.
- RX 6650 XT: teto rígido de 8 GiB, margem de segurança e serialização padrão.
  Sem CUDA. RAM livre é MemAvailable; swap não conta como capacidade segura.
- Alistair não expulsa Hoshino/Lilith para obter GPU, não concorre com áudio
  ou trabalho prioritário aguardando, não interrompe uma inferência iniciada
  e sempre conserva o caminho CPU. PC2 continua CPU.
- Preservar dados/modelos existentes. Instalação dos dois modelos já aprovados
  exige espaço para cópias, staging e pelo menos 10 GiB livres de reserva,
  recibo do backend, catálogo local e hashes verificados.

Detalhes e resultados: [relatório da etapa](docs/EXECUTORES_20261006.md).

## Exceção autorizada em 11/10/2026 — laboratório de desenvolvimento

O usuário autorizou explicitamente **painel local, controle noturno do treinamento experimental 9B e sistema de mods/overlays por cópia** dentro da nova área `laboratorio/`. Esta autorização não altera os invariantes de memória/identidade, nem libera alteração direta de arquivos da Central ou instalação de novos executores no ambiente de produção. Mod ativo só afeta snapshots de teste; adoção no launcher real exige validação e aprovação adicionais. Ver [documentação](docs/LABORATORIO_NEURAL_E_MODS_20261011.md).

## Nova exceção de laboratório em 11/10/2026 — pesquisa 6B/7B

O usuário autorizou **pesquisar e avaliar** novos candidatos de 6B e 7B no laboratório, além de selecionar datasets, agendar treinos curtos, converter GGUF e testar em Ollama isolado. Esta autorização **não aprova novos executores na produção** e não substitui as restrições de memória/identidade nem a janela do experimento 9B às 21h. Mods continuam aplicados somente a cópias. Ver [especificação](docs/LABORATORIO_EXPERIMENTOS_6B_7B_20261011.md).

## Esclarecimento de laboratório 11/10/2026 — thinking alternável

A seleção experimental foi restrita a modelos de ~6B–8B com mecanismo documentado para ligar/desligar thinking. A autorização não implanta modelos novos na Central, não substitui identidades e não remove os controles de memória/permissões; modelos não homologados permanecem apenas opções do laboratório. O operador pediu inventário dinâmico que lista apenas pesos realmente presentes. O treinamento 9B das 21h mantém prioridade e proteção de recursos. Ver [especificação](docs/LABORATORIO_7B_6B_REASONING_LOCAL_20261011.md).

## Exceção de laboratório 11/10/2026 — professor GGUF e Alistair aluno

O usuário autorizou explicitamente **implementar o Professor Neural com modelo 27B só para inferência GGUF, sem treinar o professor**, e experimentar QLoRA separado de **Alistair 4B** (além de Hoshino/Lilith). A autorização é de laboratório, sem alterar o modelo de produção, registros mentais ou o papel de Alistair como coordenador textual. O plano do professor não pode ser executado automaticamente nem usar shell/desligar PC na v0.4. A origem exata do GGUF antigo de Alistair precisa ser verificada antes de aplicar qualquer adaptador. [Especificação](docs/PROFESSOR_NEURAL_27B_ALISTAIR_V0_4_20261011.md).

## Exceção de 11/10/2026 — Yi 6B sem thinking e professor dinâmico

O usuário **revogou exclusivamente para candidatos 6B** o requisito anterior de thinking ON/OFF, autorizando teste de `01-ai/Yi-1.5-6B-Chat` sem thinking. A exigência de thinking ON/OFF permanece **obrigatória nos 7B**; modelos maiores precisam verificação pelo backend. Autorizado ampliar o orçamento adaptativo de RAM/contexto/threads do Professor 27B exclusivamente GGUF (sem treino de professor) e pilotos sequenciais de Alistair 4B + Yi6B em **laboratório**. Esta exceção não altera produção, identidade, dados mentais, governança da GPU 8GiB ou reserva 9B, e não aprova desligamento automático. [Especificação](docs/PROFESSOR_NEURAL_RECURSOS_DINAMICOS_6B_V0_5_20261011.md).
