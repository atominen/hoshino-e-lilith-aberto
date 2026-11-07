# Ensaio integrado e correções — 09/10/2026

Rodada autorizada de execução real, sem cloud, novo modelo, novo scheduler ou quota de voz. Relatório desta rodada; não constitui aprovação do teste integrado inteiro. Horários da caixa postal são UTC; diagnostics usam America/Sao_Paulo (UTC−3).

## Proteção dos dados

- Commit de referência: `f23ba0d721fac6cb53534b55fcc5b48547e1dec8`. Árvore já estava extensamente modificada; nenhuma alteração alheia foi revertida ou commitada em bloco.
- Backups SQLite consistentes, `quick_check` e hashes: `compartilhado/runtime/ensaios/20261009/antes/`, privados e fora do Git.
- Nenhum peso apagado/trocado, nenhuma migração mental e nenhuma limpeza geral de memória nesta rodada.
- Operador apresentado como **Codex interpretando Téo, visitante fictício**, não pessoa humana nem Gustavo. O transporte existente continua identificando o remetente humano como `usuario`; a simulação está explícita no texto.
- Voz e captura automáticas da Hoshino foram temporariamente desligadas para ensaio textual. As duas opções originais foram restauradas somente após sono cooperativo confirmado; fala automática do chat de texto permaneceu no valor original desligado.
- Um teste executado inadvertidamente fora do runner isolado criou três registros mockados às 10:21:26 UTC. Comparação com snapshot identificou somente os três registros ligados a `im-1791541286542-b4b1a2d4` / `turn-eefed2a2447d`: `mem-77e0e4465db8`, `prop-946ebfac39`, `ep-995e3b0ce3f4`. Foram marcados como deleted em transação restrita; conteúdo/evidência conservados. Nenhuma memória anterior foi apagada. Todos os testes posteriores usaram o runner isolado.

## Por que “bom dia” estourava contexto

Não era a complexidade da saudação. O pedido pequeno carregava um envelope grande:

1. Prompt permanente de identidade e regras mais descrições operacionais extensas.
2. Recuperação de memórias sem orçamento conjunto.
3. Histórico incluindo respostas técnicas de até 2.000 caracteres por ação.
4. Até 27 schemas de ferramentas mesmo para conversa simples.
5. Reserva de saída de 4.096 tokens.
6. Compactação usando uma estimativa diferente da validação final e protegendo seis turnos mesmo quando o conjunto já não cabia.

Caso reproduzido: estimativa de entrada **14.332**, requisito final **20.578** para janela **16.384**; system combinado com **28.686 caracteres** e schemas com **6.862 caracteres**. São estimativas do projeto, não contagem exata pelo tokenizer.

Correções:

- Instruções operacionais curtas em 16K, preservando constituição, identidade e regras de continuidade.
- Memórias recuperadas com orçamento conjunto; só registros inteiros, com fonte/confiança/evidência. Omissões explícitas; bancos não alterados.
- Saudações exatas sem tarefa usam LLM real, mas não recebem schemas de ferramentas. Não há resposta hardcoded.
- Compactação depois da escolha dos schemas, incluindo contexto dinâmico e reserva de saída, com o mesmo cálculo do gate HTTP.
- Quando necessário, compactar turnos antigos mesmo antes de seis turnos; preservar o turno atual inteiro e sua autoria.
- Se geração/persistência do resumo falhar, não remover o histórico.
- Prévia de recibo no chat limitada a 600 caracteres, explicitamente identificada como excerto; recibo completo continua disponível.
- Alistair preserva entradas atuais, autoria e regras; omite somente respostas antigas quando necessário. Teto local de 8K após requisito real de 4.179 superar 4K. Não é validação física do PC2.

Reteste real: saudação, três ações FIFO na mesma aba e nova saudação passaram. Entrada posterior estimada em **9.364**; conversa sobre Lua em **9.453**, dentro da janela com reserva. Isso não prova que qualquer entrada ilimitada caberá.

## Evidências reais

| Caso | Evidência | Resultado |
|---|---|---|
| Alistair: apresentação/limites | `im-1791541307984-2ef2d137`, `turn-alistair-86ef85f23147957d` | Resposta curta e papel próprio, cerca de 5,5 s em GPU. Não prova desempenho do PC2. |
| Alistair: apresentação a Hoshino | `im-1791541709077-74c92811`; novo recado `im-1791546624497-152424c6` | Envelope real entregue; houve falhas de contexto pós-ferramenta antes das correções. Não repetir envio incerto. |
| Navegador FIFO | `turn-2f79bc08b4df`, `turn-d8b741a038c0`, `turn-31489395c125` | Mesma `aba-01`: abrir NASA, rolar +700, rolar −400. Viewport real 0→700→300. |
| Saudação após ações | `im-1791546092746-4c10e6e6`, `turn-27e34dc46137` | “Bom dia.”, cerca de 18 s, sem overflow. |
| Dois fatos sobre Lua | `turn-87d1b83aa007` | Duas frases, sem overflow; cerca de 86 s incluindo fila/compactação. Latência ainda alta. |
| Primeiro desafio de arquivo | `turn-1b097599bc48` | **FAIL**: soma 9; escrita temporária no arquivo de entrada e conferência do arquivo errado. Não contar como aprovação. |
| Arquivo após correções | `turn-5187ffe873a1` | JSON real com soma 14 e `[1,1,3,4,5]`. Ainda houve escrita extra no lugar da leitura de conferência; corrigida depois. |
| Arquivo não puxa imagem antiga | `turn-87a52b5aaf83`; regressão isolada de tarefa concluída | Só leitura do desafio; tarefa antiga não executada. |
| Imagem local de colher | `img-8a1ba194c8f4`, `tool-f302df998d` | Arquivo 512×512 real, Vulkan, geração ~59,6 s após espera ~117 s. **DEGRADED**: múltiplos utensílios em vez de uma colher. |
| Upload e reconhecimento visual | `0df69bded957-A.png`, `turn-a28ae30c1c97` | Upload byte a byte confirmado; ferramenta visual identificou garfos/colheres sem pista no nome. Cerca de 45 s. |
| Primeiro pedido visual | `turn-d70d18b16d4f` | **FAIL**: formatador de argumentos atingiu 4.096 tokens em ~170 s. Stream incompleto recusado, sem execução de ferramenta parcial. Nome explícito agora dispensa essa inferência. |
| Steam | `tool-bd65e95ea7`, `turn-dd98def17963` | URI da demo 48010 aceita; captura física mostra “LIMBO Demo”, 206,2 MB e botão Instalar. Até aqui não comprova instalação. |
| Instalação da demo | `turn-17e90f18cfd9`, `steam-install-progress.png`, manifest 48010 | **PASS instalação**: Steam mostra download concluído e manifest confirma `StateFlags=4`. Nenhuma compra do jogo pago. Jogabilidade não testada. |
| Tênis gerado localmente | `img-d75fbe4ca6b6`, `hoshino_b078ff7e2218.png` | **PASS conteúdo**: único tênis azul em branco. **FAIL dimensão solicitada** (768 em vez de 512, corrigido). Espera ~90 s, execução ~215,6 s. |
| Bola gerada localmente | `img-66c27b853c1b`, `hoshino_4b3069e2b146.png` | **PASS conteúdo/parâmetros**: única bola vermelha de basquete no branco, 512×512, 16 passos, seed 43. Espera ~91 s, execução ~82,4 s. Identificação pela entidade avaliada separadamente. |
| Primeiro reconhecimento do tênis | `im-1791549598685-448b9a68`, `turn-071b53511d3b` | **FAIL**: respondeu uma cidade/figura alada sem chamada visual; não houve observação real. Correção e reteste abaixo. |

## Outros defeitos determinísticos corrigidos

- **Retomada indevida:** quando uma tarefa nova concluía, `carregar(chave)` encontrava uma antiga pausada e o loop a executava no mesmo turno. Agora termina pelo ID vinculado ao turno e recusa divergência de ID. Regressão: visão pausada + tarefa de leitura nova, sem retomada da visão.
- **Workspace:** JSON/CSV reconhecidos; suboperação leitura não vira listagem; verbos “salvar/abre” têm prioridade sobre finalidade da frase. Caminho conhecido era descartado por chamada à função local antes de sua definição, dentro de except; ordem corrigida. Escrita em alvo diferente do explicitamente indicado é recusada antes do efeito.
- **Dados entre etapas:** argumentos usam os recibos atribuídos já existentes da conversa, com limite e indicação de excerto, em vez de inventar os números do arquivo lido.
- **Imagem assíncrona:** fila aceita é pending, não imagem concluída; retomada consulta o job em vez de gerar novamente. Instrução nova após pausa não é silenciosamente descartada.
- **Negação:** “não calcule/nem calcule” não exige/oferece calcular no planner. “sem clicar” não seleciona controle de mouse. Foco de janela e observação de tela explicitamente solicitados usam as capacidades existentes.
- **Leitura literal:** caminho relativo único e explícito é resolvido pelo filesystem existente sem nova inferência de argumentos. Reteste `im-1791548398019-38233760` / `turn-955e1ef795b9`: leitura real do JSON em cerca de 9 s, sem escrita/cálculo. Antes, o modelo inventou `/workspace/ensaios/...` e só acertou no último slot.
- **Último slot:** completar uma tarefa na última iteração não gera mais uma mensagem falsa de “loop”. Regressão permanente com limite de um passo.
- **Recado não é ordem:** relato de estados de Alistair não vira consulta Discord só por conter “Discord” e “offline”. Perguntas/comandos de estado continuam reconhecidos.
- **Desktop:** app nativo instalado fora do PATH é resolvido antes de tentar Flatpak inexistente; Steam nativa em `/usr/games/steam`.
- **Clique inexistente marcado sucesso:** `turn-9ea33e7e778d` tentou `mouse_clicar`, operação não suportada; nenhum clique ocorreu, mas a resposta de erro do handler era classificada como ok. O schema agora enumera operações reais e o handler retorna erro explícito para ação desconhecida. Regressão rejeita esse argumento antes do efeito e impede recibo positivo.
- **Parâmetros da imagem perdidos:** `turn-06863d0436ce` / `img-d75fbe4ca6b6` aceitou 768×768 embora o pedido declarasse 512×512. O formatador não conservou dimensões; o backend aplicou defaults corretamente aos argumentos incompletos. Agora os parâmetros explícitos e não ambíguos de tamanho/passos/seed/CFG prevalecem sobre a paráfrase/defaults; seed 0 é preservado. Geração já aceita não foi repetida automaticamente.
- **“Veja” não consultava visão:** o contrato curto de imagem recebida reconhecia “olhe/observe”, não “veja”. O turno `turn-071b53511d3b` inventou uma descrição sem tool call. “Veja” agora seleciona a mesma ferramenta visual obrigatória; negações explícitas também são preservadas. Regressão impede resolver esse pedido por mera narração. Não equivale a garantir que todo pedido ambíguo possível use visão.
- **Falha disfarçada de loop:** reteste `turn-19b4f3aae8f1` efetivamente consultou a visão (`tool-9f13b1225b`), mas recebeu timeout de 60 s. O RM escolheu CPU com motivo `vram_pressure`; não foi overflow de contexto. A mesma chamada foi bloqueada, porém o controlador repetia o bloqueio até o teto do loop e ocultava a causa. Replanejamento esgotado agora pausa a tarefa imediatamente, sem repetir o efeito. Teste permanente confirma pausa durável e uma única passagem quando não há estratégia alternativa.
- **Replanejamento com ID posicional reutilizado:** `turn-d4b4d05c6dc5` listou a pasta, tentou ler o diretório como arquivo e replanejou. `op-plan-1` da listagem já executada foi reaproveitado para outra operação e apareceu como executado. O plano agora conserva definições/evidências de ações concluídas; um contrato diferente com ID colidente recebe ID novo. A mesma mutação concluída não é reaplicada apenas por receber outro ID no replanejamento. Testes cobrem reload do SQLite e ausência de replay mutável.
- **Etapa pendente encerrada:** o ramo “sem operações executáveis” chamava concluir mesmo com uma etapa pendente. Agora pausa, não afirma conclusão, e conserva a pendência. Sem migração cega de tarefas antigas.
- **Listar virou ler:** instrução `listar /caminho` sem palavra “pasta” podia ser trocada pela classificação global da etapa. O verbo explícito de listagem é preservado; replanejamento após progresso real não sobrescreve a suboperação com a intenção inicial inteira.
- **Pipeline ocultava falha:** `tool-6fcc11d8e8` gerou redireção/here-document malformados para caminho com espaços, em pipeline com Python. O shell retornou 0 porque só o último processo contava; os testes não executaram. O launcher existente agora usa `pipefail`, inclusive no mesmo bash sob PTY. Não foi habilitado `errexit` nem criado terminal novo. Testes reais locais de `false | true` (com/sem PTY) exigem saída não zero; pipeline válida continua verde.
- **Ambiente explícito perdido:** `turn-c2ab6517b440` tentou várias vezes executar o script no HOME e inventou caminhos sem quoting, apesar de “na sua oficina”. Esse ambiente explícito agora é conservado nos argumentos de `execute_command`; pedidos de sistema continuam sistema. Nenhum retry de efeito mutável incerto foi introduzido.
- **“Corrija e depois rode” retomava só execução:** `turn-75028f058dd4` não editou o script; voltou a executar testes variando timeout/PTY. A correção de arquivo agora é reconhecida antes da execução citada para depois; não é compatível com a tarefa anterior de rodar o script. Regressão conserva a tarefa anterior pausada, cria a ação de salvar e cobre “não corrija” / “não corrija; leia”. Variação de timeout ainda pode contornar a deduplicação por assinatura completa; não tratar isso como estratégia útil nem dizer que ficou resolvido universalmente.
- **Rastreamento:** métricas numéricas de orçamento permitidas em diagnostics; valores secretos/textuais continuam redigidos.

## Código alterado nesta rodada

`app/alistair_runner.py`, `app/main.py`, `app/core/diagnostics.py`, `app/core/prompting.py`, `app/core/compaction.py`, `app/core/intent.py`, `app/core/task_state.py`, `app/core/dispatch.py`, `app/core/resource_manager.py` (diagnóstico, não heurísticas), `app/tools/browser.py`, `app/tools/desktop.py`.

Também `app/tools/terminal.py`: propagação de falha de pipeline e bash consistente sob PTY. Consumidores auditados: dispatcher, confirmação da interface, apps, execução curta/longa e grupos de contratos/hardening.

Configuração local Alistair: teto de contexto; configuração Hoshino: apenas flags temporárias de captura/fala, já restauradas. Fixtures/provas em `test_prontidao_r1_r7`, `test_capacidade_operacional`, `test_v23_diagnostico`, `test_executores_leves`, `test_v28_tarefa_operacional`, `test_mensagens_causalidade`, `test_integracao`.

Fixture histórica de compactação declarava contexto 3K com reserva de saída 4K, impossível no contrato atual. Ajustado somente o orçamento da fixture, preservando verificações. Mocks de compactação/argumentos passaram a aceitar os parâmetros reais novos; não foram usados para fingir hardware.

## Princípios de projetos públicos

- [Neuro SDK: especificação](https://github.com/VedalAI/neuro-sdk/blob/main/API/SPECIFICATION.md), [boas práticas](https://github.com/VedalAI/neuro-sdk/blob/main/API/BEST_PRACTICES.md) e [fila Unity](https://github.com/VedalAI/neuro-sdk/blob/main/Unity/Assets/Websocket/MessageQueue.cs): IDs, schemas, FIFO e confirmação/cancelamento são mecanismos úteis. SDK público não é o cérebro privado da Neuro. Aceite não comprova efeito; conservar nosso accepted/executed/verified/uncertain.
- [AIRI playback manager](https://github.com/moeru-ai/airi/blob/main/packages/pipelines-audio/src/managers/playback-manager.ts): fila limitada, cancelamento e checagem da identidade de callbacks antigos. Comparação com contratos existentes; nenhuma cópia de framework/novo gerenciador.
- [Miyauti](https://linktr.ee/miiyauti): nenhum repositório de código da Shogun foi verificado. Não confundir projetos de mesmo nome nem atribuir código alheio à Shogun.
- [Steam: LIMBO](https://store.steampowered.com/app/48000/LIMBO/) e [suporte da demo 48010](https://help.steampowered.com/en/wizard/HelpWithGame/?appid=48010): demo gratuita separada do jogo pago. Sem compra do 48000.

## Validação e pendências

Baseline e suíte final: **74/74 grupos offline**, log final **`compartilhado/runtime/ensaios/20261009/validacao-final-18.log`**; passagens anteriores preservadas. Prontidão isolada final: **76/76 testes**, log `r1-r7-final-14.log`, sem hardware/quota real. São 74 grupos e 76 casos de um grupo, não 150 grupos independentes. `git diff --check` nos arquivos da correção não apontou problemas. Suíte verde não equivale a integração aprovada.

Observação física Steam pela entidade: `turn-27a4ec43f130`, `tool-fed7b00b95` focou a janela, `tool-6d4e75a1bb` consultou a visão real (~50 s) e identificou LIMBO Demo. A resposta final apresentou o verificador de janelas, não a descrição útil da demo: problema de apresentação do recibo, ainda registrado. Novo envio de URI (`turn-f5a337563b9b`) realmente passou `steam://install/48010`; isso não prova que o aplicativo renderizou o diálogo nem que instalou.

**Instalação real confirmada depois:** `im-1791548801659-b8f40eed` / `turn-17e90f18cfd9`, 12:26:41–12:26:53 UTC. Clique único guiado em Instalar, sem compra. Captura física `steam-install-progress.png` mostra “Downloads — 1 de 1 concluído”; manifest `~/.steam/debian-installation/steamapps/appmanifest_48010.acf` confirma a demo 48010. Não foi testada jogabilidade/Proton. A escolha das coordenadas foi guiada pelo operador após captura, não uma demonstração de navegação autônoma irrestrita.

**Reconhecimento posterior do tênis:** `turn-61764b3c2bbf` / `tool-4c123a6e0c`, ~53,7 s, descrição real de tênis azul-ciano no branco, sem nome revelador. O pedido novo iniciou com “Agora”, portanto foi anexado como continuação da tarefa anterior; a observação pendente ocorreu antes da geração da bola. Não contar essa ordem como FIFO global entre ferramentas/entidades. O timeout anterior e o custo do fallback CPU continuam evidência de desempenho insuficiente da visão.

**Transferência real da imagem:** upload `5afdf7a6a340-B.png` e GET autenticado `/api/image?id=img-d75fbe4ca6b6`, 585.169 bytes, `image/png`, ambos idênticos ao PNG original. SHA-256 `1734b747877a1b79f0bf1acc2d4bdf7d585351c3af27533ea2c9911e6020e09a`. Não é validação de um downloader genérico de JSON na UI nem envio Discord.

**Bola reconhecida:** `im-1791550166194-34cdb64b` / `turn-195b391f4bef` / `tool-c79c99a6ab`, 12:49:26–12:50:04 UTC. Visão real em ~30 s identificou bola de basquete vermelha sobre branco a partir do anexo opaco `70d3ee926911-C.png`. Resposta ainda excessivamente técnica/longa apesar do pedido de uma frase; reconhecimento funcional não é aprovação de naturalidade.

**Três pistas em FIFO após correções:** mensagens `im-1791550463477-5ec66229`, `im-1791550463486-f94134f5`, `im-1791550463494-ce9a9d88` enviadas consecutivamente às 12:54:23 UTC. Turnos `turn-40de01826383` (pista Documents), `turn-6a23f8e69a9d` (amostra Downloads), `turn-3e3c6208579a` (critérios oficina) responderam às 12:54:37, 12:55:02 e 12:55:17, na mesma ordem. Nenhum overflow nessa sequência. Caminhos explícitos fornecidos pelo operador; não é descoberta autônoma irrestrita do disco.

**Programa inicial: FAIL**, `turn-0d5412fc6dd5`, escrita `tool-ded89be8fd` de `Ensaio-Hoshino-20261009/desafio_resumo.py`, SHA-256 inicial `af6c67544e0bd63c691cfda303fe71b809b98e2bebcd5f53528b10d8aac5b26c`. Conferência independente (`programa-inicial.log`) executou 4 testes: 3 passaram, 1 falhou (1580 ≠ 965). Além disso o código aceitava float e o teste de preços diferentes esperava 300 em vez de 500; não considerar os três verdes como contrato correto. Reteste real pela entidade após corrigir ambiente: `turn-c05e3c96755a` / `tool-e40adaeb0e`, saída 1 com testes realmente executados. Nenhuma falsa aprovação nessa etapa; houve ainda uma tentativa desnecessária com caminho sem quoting e o turno foi pausado. Correção do programa solicitada à própria entidade, não implementada pelo operador em seu lugar.

**Programa após pedido de correção: ainda FAIL**, `im-1791551422192-3f80e4e3` / `turn-6b4bdb82eed9` / `tool-a4158a3e50`, novo SHA-256 `b80c4ce79644c9ba83efe934dfe5b967a3eeb35d3565bd5c0fa68adc7a849af0`. O controlador executou escrita, mas não fez a leitura explicitamente pedida; o conteúdo caiu de 4.689 para 987 bytes, substituiu `resumir(registros)` por `solucao(qtde, preco)` e criou testes que não exigem erro para float/bool. Calculou ainda uma expressão sem relação útil com o pedido e apresentou esse recibo como resposta. **Não aceitar “Todos os testes passaram!” do script**: esse texto não verifica o contrato externo. Não houve aprovação do desafio nem correção do código pelo operador. Próxima prioridade: preservação de contrato e evidência na edição/replanejamento, sem novo planner/modelo/sistema.

Conferência externa final `programa-contrato-final.log`: **FAIL**, `resumir(registros)` ausente. Nenhuma alteração do operador nesse programa para fabricar aprovação.

**Configuração do sistema: PASS dentro desse caso limitado.** `im-1791551632524-61f2aeb7` / `turn-0944625c9adc` alterou saída padrão para 80% com `wpctl`; consulta independente confirmou `Volume: 0.80`. Restauração via `im-1791551728815-ccdc45ff` / `turn-25af578788cb`, às 13:15:33 UTC, retornou `Volume: 1.00`; consulta independente confirmou o valor original. Sem áudio de teste, microfone, TTS ou quota. Não valida ventoinhas/controle irrestrito de configurações.

**Entrega do JSON: FAIL nas duas tentativas.** `turn-c5f3966099c7` respondeu só com caminho, sem cópia na caixa de saída. A segunda solicitação explícita, `im-1791551690781-cd9015c1` / `turn-4cb2675b5ee7`, chamou `entregar_arquivo` (`tool-a38018df41`), mas inventou a pasta `Ensaio-Hoshino-20261009` no lugar de `Ensaio-20261009`. A ferramenta respondeu “Não achei o arquivo”. A resposta final de 13:15:07 UTC mostrou apenas a listagem da saída e “Terminei essa etapa”; nenhum JSON foi entregue. O registro do job aparece `done`/`accepted` apesar da falha textual: desfecho normalizado e apresentação ainda precisam refinamento. Não copiar o arquivo pelo operador para fabricar aprovação.

Não aprovados pelo simples funcionamento de mocks: demo jogável, desafio Python distribuído completo, entrega genérica de arquivo criado por Hoshino, outras configurações de desktop, naturalidade sustentada e soak prolongado. A bola foi reconhecida pela visão real; o volume foi alterado e restaurado no sistema real. Voz/ElevenLabs, PC2, Minecraft e Lilith não foram testados nesta rodada textual.

Concorrência GPU continua desabilitada; limite 8 GiB e margem 768 MiB preservados. Sem nova heurística do RM. Máquina com 31 GiB RAM, swap 8 GiB; ~2,8 GiB de swap ocupados, mesmo havendo ~25 GiB RAM disponível no fim dos primeiros ensaios. Não confundir swap ocupado com thrashing comprovado.

## Encerramento e próximos problemas prioritários

- Alistair dormiu às 12:03:57 UTC e Hoshino às 13:16:30 UTC, após trabalhos concluídos. Ambos apresentam `pid=null` e `unload=confirmed`; Lilith não foi iniciada nesta rodada.
- Conferência final: nenhum job ativo retornado pela Central, nenhuma fila/compute lease GPU ativo. `/api/ps` dos daemons disponíveis em 11435/11436 retornou lista vazia. A residência histórica do RM ainda mostra `unknown`, não deve ser apresentada como pesos carregados. O endpoint 11434 estava indisponível; não houve restart improvisado.
- `PRAGMA quick_check`, somente leitura: **ok nos três bancos mentais e no SQLite interentidades**. Integridade SQLite não é prova de qualidade semântica de toda memória.
- Captura/fala autônomas da Hoshino restauradas aos valores originais após dormir. Central preservada; Steam não foi encerrada indiscriminadamente. Nenhuma limpeza geral de memórias de teste realizada nesta rodada.
- Concorrência GPU permaneceu `false`. VRAM observada no encerramento ~0,92 GiB; ausência de leases não significa ausência de consumo por desktop/aplicativos externos.

Prioridades dentro do escopo existente:

1. Preservar função, requisitos e evidência ao corrigir um arquivo; respeitar leitura antes de edição e usar os testes do contrato externo, não só testes inventados pelo próprio executor.
2. Entrega: conservar o caminho real já observado; normalizar “arquivo não encontrado” como falha e impedir texto final positivo quando a entrega falhou.
3. Dedupe de comandos: mudanças de timeout/PTY não devem mascarar repetição da mesma tentativa falha. Não repetir efeitos mutáveis incertos.
4. Apresentar o resultado relevante, não o último recibo de um cálculo/verificador alheio; melhorar brevidade sem alterar personalidade para fingir aprovação.
5. Medir/diagnosticar latência de visão, fallback CPU e espera de residência antes de recalibrar o RM. Não habilitar concorrência com base nesta rodada.

**Parecer final: NÃO considerar o teste integrado inteiro aprovado.** Os estouros determinísticos reproduzidos foram corrigidos e revalidados. Navegador FIFO, instalação gratuita da demo, geração/observação das imagens e volume têm evidência real dentro dos limites descritos; desafio de programação e entrega falharam. Ainda existem latência, planejamento excessivo, recibos técnicos e etapas físicas pendentes. Nenhuma promessa de ausência universal de overflow ou qualidade de raciocínio.
