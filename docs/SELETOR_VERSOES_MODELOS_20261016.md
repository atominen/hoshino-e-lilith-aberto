# Seleção de versões para conversa real — 16/10/2026

## Arquitetura antes da implementação

Central Qt existente → endpoints autenticados de controle → catálogo/seleção
no backend → registro de treinos/checkpoints/recibos existente → worker unificado
de recuperação/conversão → Ollama isolado por entidade → Resource Manager atual.

Não haverá outro servidor, scheduler, banco mental ou download. A configuração
de seleção já existente em neural9b_modes será ampliada, preservando leitura
legada. Original, checkpoint e resultado final de treino são fontes distintas;
última estável continua separada e nunca será fabricada a partir de reprovados.

O usuário autorizou usar os candidatos desta rodada para conversar e formar
memórias reais, mesmo conhecendo as reprovações. Isso é opt-in EXPERIMENTAL,
não promoção de qualidade. Preparar artefato não acorda entidade nem sintetiza
voz. Seleção só com entidade dormindo, sem job/lease; fontes e manifesto devem
permanecer vinculados à entidade/base/hash. Versões novas não mudam o executor
de um processo já acordado, nem passam a seguir automaticamente o último treino.

O menu Modelos mostrará por família: original, último checkpoint salvo, último
treino finalizado e estável aprovada quando existir. A seleção ficará pinada ao
artefato mostrado, não a um ponteiro flutuante. Se não houver GGUF/alias validado,
será necessário preparar pelo MESMO worker; falha não vira disponibilidade.

As bases e os adaptadores originais permanecerão intactos. Conversão local
reutilizará cache de GGUF existente e staging, verificará integridade e fará
probe/unload antes de publicar alias imutável. Consentimento experimental não
desliga validação de formato, isolamento, VRAM, protocolos ou leases.

A skill Hugging Face é usada somente como referência de conversão e verificação
local; suas recomendações de cloud/Hub não se aplicam à autorização deste projeto.
Nenhum treinamento será iniciado nesta alteração.

## Iniciador encontrado

Já há iniciador nativo Hoshino e Lilith no menu local, apontando para
iniciar_entidades.py; não é um binário de pesos nem exige navegador. A pasta
Área de trabalho está vazia. Disponibilizar também o atalho de desktop sem
sobrescrever arquivos do usuário e sem acordar ninguém automaticamente.

## Validação planejada

Fixtures: seleção por entidade/base, versões antigas, revisão concorrente,
symlinks/caminhos estrangeiros, ausência de estável, consentimento experimental,
tentativa de troca durante inferência/job, recibos divergentes e interface Qt.
Execução real: conversão/importação/probe dos candidatos viáveis, original
preservado, nenhum input artificial entregue às memórias de produção. Teste
humano posterior continua necessário para personalidade, áudio e novas memórias.

## Implementação e evidências desta rodada

- Seletor em **Modelos**, por entidade e família: Original, Último checkpoint,
  Último treino concluído e Última estável quando realmente existir.
- Consentimento explícito para candidatos experimentais. Não altera promoção,
  datasets, .env original, identidade ou memória. Seleção por hash, não ponteiro
  flutuante; troca bloqueada durante execução. Checkpoint não é chamado de estável.
- Preparação usa o worker `recover` já existente, cache da base e LoRA separados,
  probe físico e descarregamento confirmado antes de disponibilizar o alias.
- Atalho executável também em `/home/gustavo/Área de trabalho/Hoshino e Lilith.desktop`.
  Continua sendo a Central nativa Python/Qt; não foi fabricado um AppImage/.exe.
- 74/74 grupos offline passaram em `/tmp/seletor-versoes-oficiais-20261016.log`.
  329/329 testes do laboratório passaram em
  `/tmp/seletor-versoes-laboratorio-20261016.log`. Contratos Qt: 50 casos,
  transporte/processos simulados, não confirmação do desktop físico.
- Comando inicial de um teste Qt usou nome de método inexistente e falhou na
  descoberta; corrigido o comando, o método real e os 50 contratos passaram.
- Hashes dos três bancos mentais continuam idênticos aos anteriores. Nenhuma
  conversa artificial foi enviada às entidades para testar o seletor.
- Primeira preparação física: job `d1f6064d965b4299`, Hoshino/9B, candidato
  `63418640b9f548ea`. Conversão LoRA GGUF concluída (496 tensores, 21,6 MB).
  Importação e probe terminaram: GPU/20 camadas, contexto 16K, resposta completa
  em 5,439 s, 3.849.238.608 bytes de VRAM residente, `pressure=[]`, unload
  confirmado. Alias experimental publicado, ainda sem ativação de produção.
- Uma regressão reproduziu um defeito novo do botão Preparar: a listagem compacta
  dos jobs omite o plano e não bastava para detectar preparação anterior. O
  bloqueio agora reconcilia os registros duráveis completos. O teste falhou antes
  da correção e passou depois; nenhuma preparação física foi duplicada.
- Acrescentado handoff limitado a dois segundos no mesmo lock da entidade,
  para o worker não confundir a liberação do pedido da Central com entidade
  acordada. Não suspende nem encerra entidades para obter o lock.

## Resultado final — 16/10, 15:54 America/Sao_Paulo

### Execução real dos sete adaptadores

Todos os jobs abaixo terminaram com resposta completa, `pressure=[]`, GPU e
descarregamento confirmado. São provas de conversão/importação/inferência
isolada, **não aprovação de personalidade, memória ou ações reais**. Os tempos
são os probes curtos do backend, não latência de conversa/voz nem duração total
das conversões. Não houve novo treinamento nem uso do professor.

| Entidade / família | Job de preparação | Probe (s) | VRAM residente (GiB) |
|---|---|---:|---:|
| Hoshino / 9B | d1f6064d965b4299 | 5,439 | 3,585 |
| Lilith / 9B | c3459b057312408b | 5,012 | 3,585 |
| Alistair / 4B | f150157d03e248f6 | 3,536 | 3,618 |
| Hoshino / 7B | 2c141ff2cfea409b | 3,098 | 4,840 |
| Lilith / 7B | fdf6b8188d4c4754 | 3,144 | 4,840 |
| Hoshino / 6B | a7ccbd15a2e24a39 | 2,096 | 3,636 |
| Lilith / 6B | 775d4a7e9835405f | 2,424 | 3,636 |

Recibos permanentes: `laboratorio-local/controle-laboratorio/treinamento-unificado/recovery/<entidade>/versions/<família>/`.
Cada job preserva plano com hashes do código e fontes, log, manifesto, capacidades,
amostras físicas e confirmação de unload. As bases HF/GGUF e candidatos de treino
permanecem separados; nenhum estável foi inventado/promovido.

### Seleção efetiva para o próximo despertar

- Hoshino: 9B treinado principal; 7B treinado no caminho leve existente; 6B
  treinado disponível para escolha manual como principal.
- Lilith: mesma distribuição, com adaptadores e armazenamento próprios.
- Alistair: 4B treinado, mantendo GPU oportunista e fallback CPU do RM existente.
- Todos permanecem **experimentais**. Reprovações anteriores continuam válidas
  e registradas em `docs/AVALIACAO_CONVERSAS_E_SETE_TREINOS_20261016.md`.
- Configuração pinada em `compartilhado/config/neural9b_modes.json`, com backups
  atômicos; .env, identidade e memória não foram alterados pelo seletor.
- Os originais das sete combinações estão disponíveis no catálogo. A referência
  original imutável já importada também é reconhecida quando falta alias canônico,
  sem sobrescrever esse alias.
- Sete checkpoints passaram verificação de integridade/proveniência/retomada.
  Seus aliases separados **não** foram preparados fisicamente nesta rodada:
  selecionar Checkpoint exige clicar **Preparar para uso**, aguardar e atualizar.
  Os checkpoints atuais têm o mesmo adaptador do final do respectivo treino,
  mas a referência de checkpoint e a de treino continuam distintas.

### Resource Manager e interface

O mesmo mecanismo de recibos medidos agora reconhece a versão selecionada e sua
família: 9B/20 camadas/16K com reserva de 4,25 GiB; 7B/8K e 6B/4K com reserva de
5 GiB; 4B/8K com reserva de 4 GiB quando seu probe GPU está íntegro. A reserva
efetiva nunca fica abaixo da residência observada arredondada. Margem, staging,
leases, serialização e fallback conservador permanecem; não há scheduler novo.
Modelo sem suporte nativo a ferramentas não ganha essa capacidade por seleção.
Os tetos não truncam mensagens silenciosamente: o controle adaptativo existente
continua responsável por aceitar/rejeitar o contexto.

Central anterior PID 317801 encerrou por pedido autenticado; saída e porta livre
confirmadas antes da partida do PID 383195, sem `--entity`. Nenhuma entidade foi
acordada. Endpoint novo autenticado retornou 200 para as três; ausência de
autenticação retornou 403; corpo inválido e candidato sem consentimento retornaram
400, sem alteração na seleção. Catálogo/runtime conferidos em processos separados
com a configuração real de cada entidade, sem executar suas mentes.

Resultado final da suíte: **74/74 grupos offline e 333/333 testes do laboratório**.
Contratos Qt: **50**, incluindo as três fontes e cancelamento do consentimento.
Sintaxe shell e `git diff --check` sem erro. O clique/visual do desktop físico
continua pendente de avaliação humana: verificar Qt disponível e contratos
offscreen não comprova a experiência real da janela.

### Preservação e limites

Hashes mentais iguais antes/depois, até 15:54:

- Hoshino: `351468aed2b0ffeb8bb8d2d9408c9ecda916d8f8ab4b4cdae866678b2db79e41`
- Lilith: `e77fceca29a43f9b3aa40190438adfd458bf0bdfdf39ad097e50980c97847488`
- Alistair: `a5d83e26e97ff98f8157f35acc5a3f2caf72b1c84ca5ef8a14d90b956d558cdc`

Fim: nenhum worker de laboratório, nenhum lease ativo, GPU devolvida ao sistema.
Cloud, concorrência GPU, dados sintéticos automáticos, promoção e treino noturno
não foram habilitados. Os testes não escreveram conversas nas memórias reais.
Novas conversas do usuário poderão usar os mecanismos de memória já existentes;
isso não representa garantia de lembrança perfeita nem aprovação comportamental.

### Arquivos desta implementação

`app/core/neural9b_modes.py`, `app/core/central_control.py`,
`app/core/resource_manager.py`, `app/ui/central_native.py`,
`iniciar_entidades.py`, `iniciar_hoshino.sh`,
`laboratorio/recuperacao_modelos.py`, `laboratorio/treinos_unificados.py`,
`testes/test_central_control.py`, `testes/native_central_contracts.py`,
`testes/test_central_refinamento.py`, `laboratorio/tests/test_consolidacao.py`,
este relatório e o atalho na Área de Trabalho. Alterações preexistentes não
relacionadas foram preservadas. Backup anterior:
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/pre-seletor-versoes-20261016.tar.gz`.

### Como abrir e escolher

Fechar apenas a janela nativa antiga e abrir **Hoshino e Lilith** na Área de
Trabalho/menu do sistema para carregar o novo código da interface. Não usar
"Encerrar com segurança" só para renovar a janela.

Em **Modelos**, escolher a entidade, família e versão. **Usar esta versão** só
funciona com sono confirmado e artefato pronto; candidato pede confirmação
experimental. Se ainda não estiver pronto, **Preparar para uso** e depois
**Atualizar versões**. Isso não treina, não promove estável e não acorda ninguém.
Depois usar o controle normal de despertar e conversar. Avaliações discretas
dos balões continuam disponíveis para registrar a experiência humana.
