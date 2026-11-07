# Referências externas e retomada Codex — 27/10/2026

## Estado reconciliado às14:06

Claude entregou o código em`126d962`; última correção de comportamento em
`2f5b57a`, testada mas ainda não carregada. Central ativa; as três entidades
dormindo,0jobs/leases, ponte8766 encerrada. Minecraft34993 ainda escutando.
Tarefa`ct-06c691fa40` pausada,85passos, sem efeito pendente; meta autoral
`furnace1`. Não reiniciar outra tarefa nem repetir entradas anteriores.

Houve obtenção real de16iron_ore e20coal, mas nenhum forno/lingote ou kit de
ferro. Picareta de pedra anterior quebrou. Último estado antes do sono:
sessão`abe35da337`, posição(-98,69,-62),116cobblestone,4crafting_table,
131oak_planks e inventário completo salvo em`last-state.json` da sessão Claude.
O humano **confirmou nesta retomada que ajudou com os materiais/deslocamento**.
Essa ajuda não será contada como fabricação ou navegação autônoma da entidade.
Também impede tratar o resultado futuro como ensaio integral sem assistência.

## O que outros projetos fazem e o que se aplica aqui

Fontes primárias consultadas nesta retomada, sem instalar outro executor:

| Referência | Prática observada | Aplicação/limite neste projeto |
|---|---|---|
| [Voyager, projeto dos autores](https://voyager.minedojo.org/) | Feedback do ambiente/erro, verificação e biblioteca de habilidades reutilizáveis | Adotar a distinção entre tentativa e resultado; persistir habilidades só depois de evidência. Os resultados comGPT-4 não garantem desempenho do nosso9B |
| [Mindcraft: estado do agente](https://github.com/mindcraft-bots/mindcraft/blob/develop/src/agent/library/full_state.js) | Estado estruturado de mundo, inventário, equipamento e atividade | Manter fatos operacionais compactos e identificados; não confundir estado parado com ausência de objetivo |
| [Mindcraft: habilidades](https://github.com/mindcraft-bots/mindcraft/blob/develop/src/agent/library/skills.js) | Habilidade de fundição reúne pré-condições, uso do forno, espera e recolhimento; relata quantidade real | Habilidades mecânicas compostas podem reduzir decisões triviais. Não copiar literalmente: a versão consultada presume minérios`raw_*`, incompatíveis com nosso1.16.5 |
| [Mindcraft: biblioteca](https://github.com/mindcraft-bots/mindcraft/blob/develop/src/agent/library/skill_library.js) | Seleção de documentação de habilidades relevantes e conjunto básico sempre disponível | Reduzir ruído na decisão pode ajudar, preservando acesso ao catálogo completo. Não assumir que seu fallback de recuperação é correto sem testar |
| [Mindcraft: continuidade](https://github.com/mindcraft-bots/mindcraft/blob/develop/src/agent/self_prompter.js) | Objetivo persistente e serialização do ciclo para evitar duas respostas concorrentes | Nosso ciclo já tem tarefa durável eRM; não criar um segundo scheduler para reproduzir esse padrão |
| [Mineflayer Pathfinder, documentação oficial](https://github.com/PrismarineJS/mineflayer-pathfinder#properties) | Raio`-1` é ilimitado; parar imediatamente requer limpar o objetivo | Sustenta os limites/limpeza acrescentados pelo Claude; não ampliar busca indiscriminadamente para contornar falha |

Conclusão de engenharia, ainda a medir: infraestrutura corrigida e opções
verdadeiras são necessárias, mas não garantem que a decisão siga a própria meta.
Antes de acrescentar outro módulo ou mais instruções, testar a última ligação
meta→opções no9B real e depois no mundo. Se falhar, comparar uma representação
mais concisa da decisão, mantendo autoria e critérios físicos. Não trocar pesos,
forçar uma resposta, escrever uma sequência fixa de ferro ou declarar aprovação
por aumento incidental de inventário.

## Ensaio inicial sem efeitos

Snapshot histórico extraído dos diagnósticos da sessão`abe35da337` às13:59:32,
com receitas/percepção e posição reais daquela observação, antes da ajuda humana.
O ensaio usa o executor local/RM e substitui as observações; execução de ferramentas,
checkpoint e notas de memória são bloqueados. Não opera no Minecraft.

Mesmo snapshot, configuração e semente20261027; comparação entre a projeção
anterior e a ligação meta→opções de`2f5b57a`. Uma amostra por versão serve só
para diagnosticar a escolha, não é benchmark nem prova de autonomia.
Resultados:`/tmp/minecraft-codex-resume-probe-20261027.json`.
Script temporário:`/tmp/minecraft-codex-resume-probe-20261027.py`.

Resultado anterior: abriu catálogo completo e escolheu coletar20iron_ore,
apesar da meta`furnace1` e de não ter picareta apta. Não foi executado;
a pré-condição de ferramenta teria de ser reconferida no mundo.
`2f5b57a` com perfil residente20camadas conferido: pediuID`coletar:iron_ore`
não oferecido e foi recusado antes de qualquer efeito. Primeira tentativa dessa
medição nem chegou ao modelo por reserva deVRAM; não contar como decisão.

Protótipo conciso+JSON escolheu aproximação da bancada,86,33s. A integração
inicial, conservando mais contexto histórico do que o protótipo, escolheu carvão
em200,21s, com um plano de fabricar forno. Isso **não comprova solução do
planejamento**: o formato passou, a escolha continuou questionável. Não foi
executado. Retomada física do estado atual (após ajuda humana) é ensaio distinto.

## Implementação e revisão da representação

`minecraft_cognition.decision_view` destaca a meta registrada, conserva fatos,
receitas, inventário e referências, removendo a repetição de todas as faltas em
cada transição. `choice_schema`/`parse_choice` fazem a seleção porID e comentário
curto; o dispatcher continua sendo a fronteira de efeitos. `outra` abre o catálogo
completo. Resposta nativa antiga válida segue permitida e validada como antes.

RED→GREEN: decisãoJSON chega à operação exata; campos/IDs/nota inválidos recusam;
compactação não muda fatos nem a entrada.67testes do núcleo e148de integração
passaram. A primeira suíte geral começou durante a migração e terminou95/96 por
contratos de integração ainda antigos; não foi aprovação. Suíte final é posterior
às correções da revisão e tem log separado.
Resultado final:96/96grupos, exit0, `/tmp/minecraft-structured-final-suite-20261027.log`.

Revisão fresca Claude`16377302-2dc5-4bd4-bbe1-f8a4b43d840d`, só leitura, em
`/tmp/claude-minecraft-structured-review-20261027.json`. Um passe RED→GREEN
corrigiu três problemas: afirmação de meta/autoria inexistente nos primeiros
passos; instruçõesJSON contradizendo chamada nativa no catálogo completo;
nota/plano autoral perdido ao abrir esse catálogo. As duas notas são preservadas
se forem distintas, sem apresentá-las como efeito já executado.

Decisões e limites registrados:

- Compatibilidade nativa conserva acesso a ferramentas registradas fora dosIDs
  projetados; não se prometeenum global para esse ramo. Guardas de identidade,
  permissões, argumentos e recibos continuam no ciclo. Remover compatibilidade
  exigiria migração própria; custo de mantê-la: alguns erros de escolha ainda
  chegam à recusa factual, antes do efeito.
- Nota estruturada tem240caracteres; comentário/plano nativo conserva limite
  anterior. Expandir o plano estruturado ficou como melhoria menor posterior.
- Hipótese de executor sem ferramentas não se aplica ao catálogo7B/9B aprovado
  observado. Um futuro executor exige seu próprio contrato de capacidade.
- A reserva deVRAM que bloqueou uma medição não foi declarada corrigida. O ensaio
  temporário usou o perfil20camadas já residente e conferido; essa alteração não
  foi feita em configuração ativa. Pesos de teste foram liberados pelo ciclo
  existente, com confirmação, antes da próxima partida.

Retomada física após a suíte e commit`ecaf5d4`: entrada única
`in-local-test-minecraft-34993-codex-format-resume1`, mesma conversa/tarefa.
Central retornoustarting PID4105139 às14:35; presençaawake conferida.
A primeira decisão consultou estado, sem conectar ainda. Continuidade de sessão
e novas fabricações não foram aprovadas nessa consulta. Nenhuma terceira entidade
foi despertada nem outra sessão de trabalho criada.

### Resultado da primeira retomada e defeito de recursos

Às14:37 a própria entidade conectou ao destino, recibo`tool-a2bd5e7b2a`, sessão
`59b4083d0d`. O verificador pausou por troca de sessão, antes de transferir crédito.
Codex conferiu posição e bancada(-96,69,-61), recibos de leitura`tool-349108960f`
e`tool-df16d4866d`. O inventário coincidiu exceto mais64oak_planks (131→195),
registrados como acréscimo externo sem fabricação da entidade. O humano confirmou
ajuda anterior; a origem exata desse novo lote não foi inferida. Revisão atribuída
abe35da337→59b4083d0d e backup preservados. Entrada única`...format-resume2`.

A etapa seguinte ficou esperandoGPU, não executando jogo. Modelo físico tinha
20camadas (`llama-server -ngl20`,3834862631bytes reportados naGPU), mas a fila
reservava5905580032bytes do perfil32. Demonstração em dois testes: candidato
era guardado antes de admissão; fallback20 usado com métrica incerta não era
guardado. Depois, o cache podia ser tratado como upgrade já quente, embora esse
upgrade nem tivesse sido admitido. Isso reproduziu o bloqueio visto no ensaio
temporário, agora também no runner real.

Sono cooperativo, saída doPID4105139 e0jobs/leases conferidos antes da edição.
`gpu_resource` agora registra o perfil na admissãoGPU, incluindo o fallback,
sem registrar candidato recusado. Margem, contexto, pesos, fila e política de
exclusão não foram relaxados.104testes de executores passaram após RED→GREEN.
O cache é de perfil admitido; não é uma medição física independente de camadas.

### Chat doMinecraft pedido pelo humano

O humano autorizou ler/responder sem perder o trabalho. Antes, `minecraft_chat`
era explicitamente excluído do ciclo e só havia o último evento, sobrescrito
por outros eventos. A ponte agora mantém até32falas de jogadores por sessão,
sem eco próprio e sem transformar mensagens de sistema em jogadores.
Até8novas falas entram como observações por decisão; IDs apresentados ficam
no checkpoint desta tarefa. Não são mensagens humanas inventadas pelo condutor.

O catálogo nativo existente oferece `minecraft_chat`; a entidade decide se
responde. Não há outro scheduler, inferência paralela nem interrupção de ação
em andamento. Chat aceito não aprova fabricação, não abandona o objetivo e não
consome/reset o contador de estagnação do trabalho. Mensagem nova permite uma
resposta igual sem repetir o contexto antigo. O ciclo aceita só fala curta em
uma linha, sem slash/comandos de servidor ou controles, antes de qualquer envio.

Limites: o buffer começa ao conectar; não recupera conversa ocorrida enquanto
o bot estava ausente. “Apresentada ao modelo” não prova compreensão ou resposta.
O cursor é do checkpoint da tarefa; migração entre objetivos independentes ainda
não é um histórico de conversa permanente. A resposta chega após o processamento
do9B, sem promessa de imediatismo. Aceite de envio não prova leitura pelo jogador.

Focados desta etapa:104executores,70núcleo,149integração e44regressões da ponte
passaram. Revisão fresca do incremento e suíte geral separadas da aprovação
de resposta real no mundo. Nenhum diálogo foi enviado porCodex no Minecraft.
Suíte geral do incremento:96/96, exit0, `/tmp/minecraft-resource-chat-suite-20261027.log`.

### Revisão do incremento e correções de fronteira

Claude`dc790f8c-ac45-4a58-8c21-54de6b2729a4` revisou apenas o incremento
posterior, em leitura. Achados importantes foram reproduzidos/corrigidos num
passe RED→GREEN: limite de fala em unidadesUTF-16 para impedir divisão do
Mineflayer com comando escondido após emoji; recusa de controles/formatação
e surrogates; atribuição pelo pacote tipado`chat.type.text`, sem confiar no evento
legado baseado emregex; exclusão de mensagens antigas em todas as projeções,
inclusive escolha de meta; cursor sequencial por sessão, ordem cronológica e
contagem de falas que saíram do buffer; somente uma resposta por contexto novo
fica isenta da estagnação; passos de resposta não inflam o monitor/trajectória
do trabalho. Recibos de conversa permanecem no diário de efeitos da tarefa.

A inspeção do código instalado doMineflayer confirmou a divisão em256unidades
UTF-16 e a regex que também casa com avisos de sistema. Testes da ponte usam
o`ChatMessage` real da dependência1.16.5, não só eventos de chat inventados.
Essa atribuição é a do servidor; não é autenticação de uma pessoa física.

Um ensaio físico adicional mostrou que corrigir o cache sozinho não bastava:
perfil32 realmente carregado deixou pouca margem para a próxima chamada.
O gerenciador agora permite **diminuir** para outro degrau já medido quando
há pressão conhecida deVRAM; não sobe um modelo quente sem motivo nem relaxa
margem, contexto ou qualidade. Residência antiga é consultada novamente antes
de avaliar a descida; métrica incerta conserva a recusa segura.

Após essa correção, duas inferências reais consecutivas do mesmo9B/16K passaram:
4,309s e0,601s, ambas perfil31, com0leases ao terminar. Esse teste é só umJSON
curto, sem raciocínio; **não é benchmark da decisão de jogo** nem da conversa.
Log:`/tmp/minecraft-gpu-cache-real-fixed-20261027.log`. A tentativa anterior
que bloqueou fica preservada em`/tmp/minecraft-gpu-cache-real-20261027.log`.

Focados finais:105executores,73núcleo,149integração e44regressões da ponte verdes.
Suíte final após esse passe: `/tmp/minecraft-resource-chat-final-suite-20261027.log`.
Resultado conferido:96/96grupos, exit0. Modelo usado no ensaio de recursos
liberado pelo ciclo existente e confirmado antes da próxima recarga da entidade.

Decisões de escopo: manter pausa diante de um envio de chat incerto, sem replay,
em vez de apagar uma pendência lateral para forçar continuação. Conversas novas
contínuas podem consumir turnos e duas entidades podem conversar entre si;
não foi demonstrado um escalonador social que garanta progresso de jogo nessa
situação. O objetivo e o teto de passos continuam preservados. Uma fala aceita
não é conclusão do kit nem prova de leitura pelo destinatário.

## Observação humana posterior: visão sob demanda e habilidades

O humano forneceu uma proposta como **ponto de vista**, pediu estudar imagem do
campo visual quando necessária e reafirmou a colaboração comClaude. Isso não
substitui a decisão vigente de dois executores7B/9B, nem autoriza treinamento,
cloud ou troca de pesos. A inferência atual continua no mesmo9B.

[Ollama documenta o parâmetroformat com JSON Schema](https://docs.ollama.com/capabilities/structured-outputs).
O formato restringe a representação; não garante escolha útil, retorno completo,
semântica correta ou efeito físico. O cliente continua validandoID, campos e
nota antes do dispatcher e este reconfere pré-condições. O caminho nativo de
compatibilidade também mantém suas validações. Não afirmar impossibilidade
absoluta de erro de ponta a ponta só porque háenum no pedido.

### Viabilidade da câmera do próprio bot

**Viável tecnicamente, ainda não instalada/validada neste projeto.**
[Prismarine Viewer](https://github.com/PrismarineJS/prismarine-viewer) oferece
primeira pessoa e modoheadless. A documentação inclui1.16.4 e uso de assets da
versão suportada mais próxima na mesma família; o nosso1.16.5 precisa de ensaio.
O9B e`tools.vision.observar_imagem` já existem. Falta produzir e atribuir a imagem
da câmera correta, não capturar o desktop/jogador humano.

Inspeção de[lib/headless.js](https://github.com/PrismarineJS/prismarine-viewer/blob/master/lib/headless.js)
confirma câmera baseada em posição/yaw/pitch do bot e capturaJPEG. O modo usa
`node-canvas-webgl`, listado como dependência de desenvolvimento, e assume um
contextoWebGL válido; instalar só o pacote não garante o renderer. Ele registra
listeners de movimento/mundo e não expõe limpeza completa por captura. Chamá-lo
repetidamente por imagem sem adaptação pode acumular recursos. Não ligar um vídeo
contínuo por padrão para satisfazer um pedido de imagem ocasional.

Proposta incremental:

1. Protótipo isolado com dependências fixadas, renderizando uma cena conhecida
   do1.16.5; conferir texturas, oclusão, orientação e custoCPU/RAM/VRAM.
2. Renderer de propriedade da sessão do bot, acesso somente local; capturar um
   quadro após os chunks necessários estarem prontos. Descartar frame antigo
   ou de outra sessão/entidade. Limpar listeners/contexto quando encerrar.
3. Uma futura ferramenta de observação devolve imagem+metadados: entidade,
   sessão, dimensão, posição/yaw/pitch, hora de captura e origemMinecraft.
   Nenhum movimento/rotação oculto para obter a foto.
4. Inferência visual serializada peloRM após liberar o renderer. A entidade
   pede a imagem quando precisar; não há captura contínua nem outroLLM paralelo.
5. Testar distinção Hoshino/Lilith, reconexão, cena ainda não carregada, perda
   de contexto gráfico e liberação de memória. Medir latência no PC real antes
   de ativar. Visão não substitui inventário/recibos para aprovar fabricação.

Habilidades compostas como fundir e recolher um lote são uma evolução possível:
parâmetros escolhidos peloLLM, pré-condições e recibos por subefeito, cancelamento
cooperativo e retorno parcial/incerto honesto. Não equivale a inserir um roteiro
fixo de kit de ferro. O escopo desta correção continua na representação da decisão.

A proposta deLoRA fica como estudo posterior. Não foi conferida uma garantia de
compatibilidadeADAPTER/Qwen3.5 na versão instalada; o caminho precisa de ensaio
próprio, assim como VRAM, conversão e licença de qualquer dataset. Nenhum dado de
conversa ou experiência foi aprovado automaticamente como material de treino.
