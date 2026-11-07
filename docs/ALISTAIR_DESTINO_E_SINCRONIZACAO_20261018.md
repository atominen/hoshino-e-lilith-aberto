# Alistair: escolher PC, PC2 ou Xbox na Central

## Autorização e fronteira

Em18/10 o proprietário autorizou oficializar a integração do4B já ensaiado,
seletor na interface existente, sincronização e inicialização automáticas.
Isso libera esta integração, não homologa a qualidade do candidato: os erros
aritméticos do [ensaio](XBOX_ALISTAIR_OTIMIZACAO_20261018.md) continuam registrados.
Não autoriza professor, treino, cloud, instalação de outros modelos, limpeza
mental, promoção de checkpoint como estável ou descarte doPC2.

Xbox: inferência textual do4B, seus pesos e controles técnicos. PC: Central,
identidade, bancos, memórias, histórico durável, permissões, execução e recibos
de ferramentas. Não há espelhamento bidirecional de bancos, relógios mentais,
personalidades ou conversas em arquivos do console. O contexto necessário é
enviado por pedido e o API de chat é stateless; não chamar APIs de preferências,
treino, imagem, download ou histórico doXbox.

## Interface e operação

Em **Modelos → Alistair → Onde executar Alistair**, destinos: **EstePC**, **PC2**
(pareamento existente preservado) e **XboxSeriesS**. Troca exige sono, ausência
de jobs/leases e lock da instância. Salvar não acorda ninguém. Um turno inteiro,
inclusive ferramentas, permanece no destino selecionado: falha não transfere
silenciosamente a execução para outro computador.

O painel nativo e o painel web usam as mesmas rotas autenticadas daCentral:

- GET `/api/control/alistair/execution`: só configuração/estado local; sem
  conectar, sincronizar, iniciar ou inferir. Dado antigo aparece como antigo.
- POST na mesma rota: revisão otimista, sono confirmado, campos permitidos;
  usuário/senha jamais voltam na resposta.
- POST `/api/control/alistair/execution/check`: `prepare` explícito ou
  `reconcile` por decisão humana, sem repetir o pedido anterior.

Informe o acesso remoto doDevicePortal, **não a senha da contaMicrosoft**.
Credencial fica somente noPC, arquivo600 ignorado peloGit. Certificado público
é fixado à raiz já verificada; pode ser reaproveitado dosDownloads somente se
seuSHA for o conhecido. Raiz diferente exige revisão explícita. Antes de enviar
credenciais, conferir assinatura da folha, raiz,IP, período e finalidade; TLS
com validação obrigatória, sem proxies, redirects ou confiança global alterada.

**Limite importante:** a API de inferência do app é HTTP sem autenticação
própria. Checkbox deLAN de confiança obrigatório; não expor portas àInternet,
usar redes compartilhadas/não confiáveis ou confundirTLS doPortal comTLS da
inferência. Autenticação/cifra nativa da inferência seria outra etapa.

O controle usa as rotas de ciclo de vida do
[DevicePortal documentadas pelaMicrosoft](https://learn.microsoft.com/en-us/windows/uwp/debug-test-perf/device-portal-api-core#start-a-modern-app),
com pacote completo explícito; não procura processos para matar por nome.

## Inicialização e sono

"Automática" significa **ao acordar Alistair pela Central**. O console deve
estar ligado, emDevMode, pacote exato.7 instalado e classificadoGame.
Não há ligação remota do console, mudança de modo ou instalação automática
deMSIX/certificado do app. O endpoint precisa permanecer em primeiro plano.

O caminho remoto não inicia daemonOllama local nem recuperação/treino local.
PC2 legado sem nova seleção explícita conserva seu comportamento anterior.
Só o app próprio e ocioso pode fechar/reabrir; nunca kill porPID/porta/nome,
force-stop, reset ou duas instâncias. Ao dormir, fechar apenas a instância
comPID gerenciado ainda confirmado; app alheio permanece intacto.

## Sincronização de arquivos e estados

PC é a fonte da versão selecionada e pinada pelo seletor de pesos existente.
Nenhum "último checkpoint" flutuante é adotado sozinho. Perfil textual restrito
à baseQwen3.5-4B já medida; projector/visão e arquivos mentais não são copiados.

1. Conferir pacote/processos e blobs locais. VerificarSHA integral físico no
   primeiro pareamento ou quando metadados/versão mudarem; cache técnico evita
   reler2,73GB a cada despertar sem motivo.
2. Manter base existente, enviar só arquivos ausentes. NovoLoRA usa nome porSHA,
   sem sobrescrever o anterior. Arquivo parcial/divergente bloqueia, não é
   apagado ou reenviado automaticamente. Originais e versõesPC2 preservados.
3. Com app parado, ativar diagnóstico sem modelo e confirmar5GiB/Game/margens
   nativas. Cópias são limitadas ao4B e adaptador≤128MiB; sem descarte de arquivos
   para liberar espaço. Disco cheio/erro de cópia bloqueia com recibo e mantém
   catálogo anterior/diagnóstico: não presume espaço disponível pelo tamanho25GB.
4. Conferir hashes de retorno antes de publicar o catálogo. Somente então
   restaurar execução normal:33camadasGPU, contexto salvo na abaModelos
   (2048–8192, passos de256), host1 quando háLoRA;
   Original sem adaptador usa host0. Nenhuma fusão/conversão/treino.
5. Reconciliar recursos/processo após carga e antes/depois de pedidos, com
   telemetria durante geração. PoolsUMA não se somam. Sem sensor térmico novo
   ou alteração de proteções do console.

O estado técnico fica em `compartilhado/runtime/alistair-execution/`, não é uma
segunda fila ou scheduler. IncluiPID, orçamento, seleção, hashes e intenção,
**não prompt/resposta/credenciais**. Log técnico doXbox é lido emRAM para conferir
conclusão, concorrência e cortes; não é banco mental doPC.

## Contratos de conversa e falhas

Adapter traduzOllama→OpenAI sem perder ordem, autoria ou conteúdo de recibos.
IDs de chamadas são associados inequivocamente e normalizados por pedido,
pois o app pode repetir`call_1` em gerações distintas. Ferramentas são propostas;
somente oPC aplica os contratos e recibos duráveis já existentes.

O appxllama, inclusive.7, pode cortar contexto para caber. Esta integração **não publica a resposta
nem executa propostas** se o log da geração indicar corte. Também rejeita
resposta vazia/truncada, geração concorrente,PID trocado, telemetria inválida,
contagens incoerentes e ferramentas não ofertadas. Não promete que o app
recusa o corte antes de calcular; a resposta é bloqueada noPC depois de detectar.

Antes de cada operação mutável, intenção durável e lock exclusivo noPC.
Timeout/crash/pressão/resultado incerto deixam bloqueio persistente, inclusive
após reiniciar aCentral. Nenhum fallback, retry ou replay de inferência.
CadaID enviado também recebe recibo técnico próprio: mesmo concluído, esseID
não pode ser reenviado após reinício se a camada superior perdeu a resposta.
"Reconciliar" só por clique humano e após confirmar ociosidade; nunca transforma
uma resposta perdida em sucesso nem repete uma ação. Sono e encerramento das
outras entidades não ficam presos no lock global durante hashes/cópia.

## Ajustes de modelo sincronizados — 19/10

A fonte do contexto e do limite de saída é o mesmo `alistair.env` editado pela
aba **Modelos**. Não existe uma segunda configuração de usuário no console.
Ao acordar Alistair ou clicar **Conferir/sincronizar agora** com ele dormindo,
o contexto escolhido vai para `n_ctx` do catálogo no Xbox. Mudança de contexto
fecha somente o executor ocioso, confere Game/recursos e recarrega o modelo;
os pesos existentes não precisam ser copiados novamente.

O teto permanece 8192 tokens; valores entre 2048 e8192 são aceitos em passos
de256, respeitando o padding do cache. Saída mínima128 e reserva mínima512
para entrada. Não se promete qualidade com prompts perto do teto. O limite de
saída é enviado por pedido; alterar somente esse limite não exige recarregar
um modelo ocioso já preparado no contexto correto. GPU/threads não são espelhados
do PC:33camadasGPU/LoRAhost1 permanecem no perfil validado do console.

Os painéis nativo/web mostram **limites salvos**, **últimos limites aplicados**
e **sincronização pendente**. Abrir/salvar o painel não inicia nem conecta ao
Xbox; as mudanças são aplicadas no próximo despertar ou na conferência explícita.
Janela adaptativa usada para preparar o pedido no PC nunca pode ultrapassar a
janela preparada no console. Configuração diferente da preparada bloqueia o
envio antes da rede, até nova preparação com a entidade dormindo. Operação
pendente impede salvar nova configuração; não há ajuste/retry durante geração.

O app cria o KV somente na primeira geração, não quando termina de carregar os
pesos. A preparação aceita ausência de KV apenas se ainda não houve prefill nem
geração. Depois da geração, antes de publicar fala ou ferramentas, o cliente
exige o cache físico correspondente à janela salva. Na base4B fixada porSHA,
esse cache tem contexto/32 MiB (128MiB em4096,256MiB em8192). Falha, valor
divergente ou corte de contexto bloqueiam a resposta; nenhum gate é removido.

### Resultado da sincronização física

Sem trocar o app .7 nem os pesos, a configuração foi salva pela mesma API da
abaModelos, preparada no console e testada com pergunta sintética isolada:

| Contexto salvo/console | Saída salva/enviada | KV físico após gerar | Resultado |
| ---: | ---: | ---: | --- |
| 4096 | 512 | 128 MiB | `ALISTAIR_XBOX_OK`,6tokens,3,028s |
| 8192 | 768 | 256 MiB | `ALISTAIR_XBOX_OK`,6tokens,2,733s |

Um único prefill/geração completa por janela; sem corte de contexto nem pressão
nas14amostras normais. A primeira tentativa foi bloqueada antes de inferir porque
a checagem esperava KV antes de sua criação tardia; foi preservada e corrigida,
com IDs novos na validação concluída. Não houve replay de geração ou ferramenta
real, uso de conversa humana, novo treino ou cópia de banco mental.

Os valores originais8192/768 foram restaurados. As demais linhas do.env foram
conferidas contra a configuração original; backups da API preservados. App
fechado normalmente, entidades dormindo, jobs/leases vazios. Central recarregada
cooperativamente apenas após confirmar a saída doPID próprio e liberação da
porta; novo endpoint confirmou limites salvos/aplicados iguais e nenhuma
sincronização pendente. Uma partida fria sempre verifica Game antes dos pesos,
inclusive se catálogo/limites já coincidirem.

Verificação final:151testes de topo passaram (Xbox,CentralControl,
CentralRefinamento eBrowser), incluindo70contratosQt internos com transporte
simulado. Não é suíte completa do projeto nem validação de contexto longo ou
personalidade. Sintaxe e diff conferidos. Evidências locais ignoradas peloGit:
`compartilhado/runtime/alistair-execution/model-settings-sync-20261019-v2.json`,
`model-settings-tests-final-20261019.log` e
`settings-central-reload-20261019.json`. A tentativa inicial permanece como
`model-settings-sync-20261019.json`.

## Continuidade e contexto — 19/10

O chat real mostrou uma falha de execução, não ausência do histórico: um pedido
explícito para acordarLilith e se apresentar terminou só no pedido de despertar;
depois “continue” gerou outra promessa, sem consulta ou apresentação. A fala
“Lilith acordou” precedeu o consumo do pedido pelaCentral. Não houve envio
Alistair→Lilith nessa sequência. Os registros antigos permanecem como evidência.

Foi acrescentada continuidade **restrita** para o pedido humano inequívoco de
acordar uma única Hoshino/Lilith e se apresentar. Usa um namespace técnico na
tabela existente `alistair_actions`, sem novo banco/schema/scheduler. A
apresentação continua gerada pelo modelo com sua identidade configurada;
somente a confirmação de envio/presença é mecânica e baseada em registros reais.

- Reconhecimento conservador: citações, hipóteses, condições futuras, negação,
  destinatários múltiplos e cláusulas adicionais não concedem essa execução.
  Outros pedidos continuam no caminho conversacional existente, sem alegar
  planejamento geral resolvido por esta correção.
- Ferramenta limitada ao destinatário autorizado, com permissões atuais de
  envio/despertar/consulta conferidas. Texto e autoria são verificados na linha
  física do canal, sem marcar mensagem como entregue ou lida.
- “Continue” no mesmo participante/sessão usa o mesmo recibo; não envia outra
  apresentação nem outro despertar. Reinício não elimina a proteção. Efeito
  incerto permanece bloqueado. Mensagem removida não é tratada como comprovante.
- Mudança de assunto suspende a tarefa, cancelamento a cancela; continuidade
  expira após24h sem atualização. Não adota tarefas a partir do chat antigo,
  não executa nada em segundo plano nem reenvia a apresentação antiga sozinha.
- Envio não significa presença, leitura ou resposta. Presença vem de consulta
  atual; promessa do modelo não encerra uma tarefa sem recibo.

Na primeira correção, o contexto conservava integralmente a identidadeJSON e as entradas do histórico,
mas elimina a cópia duplicada da personalidade, contadores/IDs voláteis no
prefixo e a projeção técnica redundante em conversa simples. IDs, horários e
fontes permanecem nos registros de autoria/diagnóstico. Estado atual é consultado
por ferramenta, não inferido de uma fotografia antiga do sistema. A política
anterior de orçamento continua: apenas respostas históricas podem sair do
contexto; entrada atual, citações e recibos não são truncados para caber.

Comparação offline do texto fixo com a mesma identidade e sem histórico:
4172→2979caracteres, redução28,6%. **Não é medição de tokens ou latência real.**
O console já mantinha o modelo residente; os≈68s de um turno anterior eram
principalmente o prefill de2093tokens, não uma nova carga de pesos. Comparação
PC/Xbox com prompt/pesos/limites idênticos e validação humana continuam pendentes;
não se promete que esse ajuste iguale o raciocínio ou a velocidade dos executores.

Atualização posterior de19/10: [projeção fixa da mesma personalidade, caminho
sem ferramentas para frases simples e esclarecimento de destinatário ambíguo](CENTRAL_OFICIAL_20261019.md).
A projeção textual substitui o envelope JSON no prompt, não o arquivo de
identidade; traços/estilo/regras/campos personalizados continuam presentes.

406testes de topo passaram pelo runner isolado, em10grupos: continuidade21,
standby/imagem21, prontidão112, Xbox53, Central57, refinamento40, atividade40,
causalidade41, isolamento20 e browser1 (inclui contratosQt internos simulados).
Não é a suíte inteira nem um ensaio real de conversa/encadeamento no console.
Logs locais: `/tmp/alistair-isolado-20261019-test_*.log`.

ApenasAlistair foi recarregado cooperativamente após confirmar jobs/leases
vazios e nenhuma entrada nova em processamento. PID32225 saiu; appXbox próprio
fechou fisicamente. Nova instânciaAlistair73954, appXbox6372, estado`ready`,
contexto8192, sem operação pendente. Lilith permaneceu acordada noPID36894;
Hoshino continuou dormindo. Nenhuma inferência ou apresentação real foi criada
para o ensaio. O cacheKV será conferido na próxima geração, como já previsto.

### Incidente de isolamento e reparo dos próprios artefatos

Uma invocação inicial da verificação legada foi feita incorretamente com
`unittest` direto, sem `testes/executar_isolado.py`. Foram identificados artefatos
sintéticos naHoshino dormindo. Antes da limpeza foi feito backupSQLite consistente
dos quatro bancos atingidos e cópia doJSON de estado. Foram retirados **somente**
os registros auditados dessa invocação:2entradas sintéticas no canal,55mensagens
no histórico/índiceFTS,20tarefas/22etapas de chave`test::`,3resumos e2recibos de
ferramentas simuladas. A projeção operacional com`session-trace` também saiu;
não é identidade ou emoção. Eventos técnicos/diagnósticos foram preservados.

Os bancos Alistair/Lilith e suas conversas reais não eram os alvos desse ensaio.
Traços e perfil existentes daHoshino foram preservados. Não houve limpeza geral,
alteração de pesos, treino ou tentativa de transformar os dados sintéticos em
conversa humana. Os quatro bancos passaram em`quick_check` após o reparo.

Backup recuperável e script de reparo **não reexecutável automaticamente**:
`compartilhado/runtime/alistair-execution/incident-fixture-20261019/`.
Os três grupos tocados agora recusam execução sem o runner isolado antes de
importar os módulos da aplicação; a guarda possui teste de regressão. A rodada
final de406testes usou isolamento com bloqueio de bancos/rede/serviços reais.

## Verificação e reversão

Testes offline cobrem seleção/UI, credenciais privadas, preservaçãoPC2, tradução
de ferramentas, término, cortes, orçamento/telemetria, sincronização porSHA,
falha de upload, rollback de seleção e bloqueio após reinício. Não substituem
o teste físico do perfil8K e do encadeamento de ferramentas, nem conversa humana.
A medição anteriorhost1 foi em2K; não extrapolar seu ganho para8K.

Para reverter, dormirAlistair, resolver qualquer operação incerta e selecionar
**EstePC** ouPC2 pareado. Não apagar modelos/bancos. Desativar flags automáticas
conserva arquivos e evidências. Configuração exige nova abertura daCentral/UI
se ela ainda estiver executando código anterior. Estado físico/ativação serão
registrados depois do teste real, sem confundir testes simulados com aprovação.

### Estado da entrega

Interface e backend implementados; o proprietário cadastrou as credenciais
localmente e salvou **Xbox**, IP10.0.0.103, início/sincronização habilitados eLAN
de confiança confirmada. A Central/painel foram abertos sem acordar entidades.
Estado noturno observado completed; rotina/dados automáticos
e desligamento permanecemfalse. Nenhum treino, modelo instalado, conversa
gravada para ensaio ou conteúdo mental alterado por esta entrega.

Verificações dirigidas concluídas:40contratosXbox,16PC2,54CentralControl,
28CentralEntidades,40CentralRefinamento (inclui contratosQt reais simulados),
1bateria de navegaçãoBrowser com APIs simuladas:179testes de topo passaram entre
as etapas. Os40contratosXbox e54CentralControl foram reexecutados após as
correções do executor; os demais grupos pertencem à verificação inicial,
antes dessas correções restritas.
Dois grupos inicialmente falharam com oPython do sistema por dependências
ausentes; passaram reexecutados no ambiente principal existente, sem instalar
pacotes. SintaxePython/JS/shell e diff conferidos. Não é reexecução da suíte
completa nem teste físico de8K/ferramentas.

Primeira preparação física: leitura integral dos2.708.804.000bytes da base e
16.267.168bytes do adaptador confirmou osSHA fixados, sem upload. Antes de
qualquer operação mutável, o inventário bloqueou com"Executor concorrente ou
processo incerto": oWDP lista tanto xllama.exe/PID6368 quanto seu auxiliar
RuntimeBroker.exe/PID3520 sob o mesmo pacote. A telemetria nativa confirmou
PID6368, Game5GiB e margens seguras; não eram dois executores.

A correção aceita somente oRuntimeBroker do pacote exato como auxiliar;
doisxllama, pacote/imagem desconhecidos,PID/flags incertos continuam bloqueados.
A espera de encerramento também acompanha uma linha dePID que mudou para
IsRunning=false: somente seu desaparecimento confirma a saída. A rota deupload
foi corrigida paraPOST `/api/filesystem/apps/file?…&extract=false`, conforme o
[contratoMicrosoft](https://learn.microsoft.com/en-us/windows/uwp/debug-test-perf/device-portal-api-core#upload-a-file).
As primeiras falhas foram preservadas; não se repetiu inferência incerta.

### Validação física e bloqueio de formato — 18/10

Após aprovação humana para reconciliar, a preparação real passou: diagnóstico
Game5GiB, sincronização dos controles sem copiar pesos e ativação.6/PID4224,
33camadasGPU, LoRAhost1/248paresF16. Os bancos não foram usados no ensaio.

| Caso sintético | Resultado medido |
| --- | --- |
| Controle de texto | ALISTAIR_XBOX_OK,6tokens,3,482s de parede |
| Proposta de ferramenta fictícia | Nome/argumentos/ID corretos,76tokens,18,073s |
| Primeiro recibo | HTTP400 antes de nova geração; pedido não reenviado |
| Recibo após correção de codificação, com novoID | Marcador correto,85tokens,20,369s, porém raciocínio interno exposto: reprovado |

O erro400 foi reproduzido sem inferência, usando otemplateGGUF e o detector
doapp: incluir `name` redundante no recibo faz o detector contar3ocorrências na
transcrição e3no prompt, rejeitando schemas válidos. O reciboOpenAI agora usa
apenas `tool_call_id`; nome e argumentos continuam preservados na chamada
assistant e validados antes da tradução. Não se mudou o detector nem retirougate.

Mesmo com transporte corrigido, oapp.6 monta fala final a partir de geração
bruta, não do conteúdo final separado pelo parser, e força thinking nas ferramentas.
Isso impediu aprovação. O cliente passou a recusar marcadores de raciocínio na
fala, em vez de publicar/recortar silenciosamente. Houve3gerações completas,
sem execução real de ferramenta, sem retry doID recusado e sem conversa gravada.

Nas15amostras nativas destes ensaios: picoapp3.731.877.888bytes; picoGPU
2.818.322.432bytes; menores margens1.636.831.232bytesapp e1.167.944.090bytesGPU.
Não houve pressão nas amostras. PoolsUMA não se somam; não é medição térmica nem
estabilidade prolongada. Contexto configurado8192, bufferKVCPU256MiB observado,
compatível com8camadas de atenção/4cabeçasKV/dimensões256/256/F16 doGGUF fixado.
O log não imprime n_ctx diretamente; não houve teste de qualidade perto de8K.

App fechado cooperativamente após confirmar3prefills/3términos; nenhuma entidade
foi acordada. Estado técnico permaneceblocked/IntegrationFormatBlocked, sem
pedido pendente, até correção e reteste. Recibos integrais sintéticos ficam em
`compartilhado/runtime/alistair-execution/integration-synthetic-20261018.json`,
`integration-synthetic-receipt-v2-20261018.json` e `integration-postcheck-20261018.json`.
O benchmark2K anterior e seus erros permanecem intactos.

### Correção do app autorizada — 19/10

O proprietário aprovou gerar uma nova versão doapp, preservando.6 e os pesos.
Receita isolada no repositório privado `atominen/xllama-xbox-4b-gpu`, branch
`codex/tool-replies-20261019`, commitbe6f6a46d066bc1d61ba42a1e930f444bcf67617.
A alteração retorna apenas o conteúdo final do parser e bloqueia falha de parse,
sem fallback para texto bruto. A opção explícita `chat_template_kwargs.enable_thinking`
chega ao render e ao parse; o cliente solicitafalse, sem alterar odefault legado.

Os33testes da receita passaram, incluindo contratosC++ reais; compilação sintática
da ponte com headersllama fixados e da variante semllama passou. Uma única
[compilação manual39230134303](https://github.com/atominen/xllama-xbox-4b-gpu/actions/runs/39230134303)
terminou com sucesso: Windows/MSVC, assinatura e verificações do pacote passaram.
O artefato foi conferido pelos hashes do recibo e instalado in-place como
`Atominen.Xllama4BGPU_1.6.0.7_x64__pj67f1fcj4n14`. Configurações e metadados dos
modelos permaneceram idênticos; nenhum peso foi reenviado, desinstalado ou
resetado. Pacote assinado, certificado público, dependência, licença e recibos
estão preservados em `pacotes/xbox_alistair_1.6.0.7/`, sem remover a cópia .6.

O usuário esclareceu que dados técnicos úteis ao desempenho podem ficar noXbox.
Pesos, LoRA e cache de inferência já ficam lá; não há motivo medido nesta etapa
para transferir banco/identidade ou ampliar componentes para obter esse ganho.

### Validação física da versão .7 — 19/10

A atualização inicialmente voltou ao modo App de 1 GiB. O diagnóstico bloqueou
a carga: nenhuma geração foi enviada nessa tentativa. Posteriormente o orçamento
nativo confirmou Game de 5 GiB. Uma checagem somente de leitura encontrou o app
fechado durante a consulta; inventário e log confirmaram processo ausente e zero
gerações antes de uma nova preparação controlada. Falhas de pré-verificação do
script local foram preservadas e corrigidas antes de qualquer pedido de inferência.
Não houve repetição de resposta nem adoção de resultado incerto.

A preparação gerenciada passou e o marcador compilado `tool-wire-v1` foi
confirmado no log. Somente três pedidos sintéticos novos foram enviados:

| Caso | Resultado da .7 | Tokens de saída | Parede |
| --- | --- | ---: | ---: |
| Texto | `ALISTAIR_XBOX_OK`, término `stop` | 6 | 3,101 s |
| Ferramenta fictícia | `test_read_marker({"sample_code":"fixture-alpha"})`, ID preservado no recibo | 28 | 14,355 s |
| Resposta ao recibo | Somente `VERDE-42`, sem raciocínio interno, término `stop` | 5 | 2,457 s |

Nenhuma ferramenta real foi executada. Houve exatamente três prefills e três
gerações completas, sem aviso de corte de contexto. Foram confirmadas 33/33
camadas GPU, LoRA host1 e buffer KV CPU de 256 MiB com contexto configurado 8192.
O log não imprime n_ctx diretamente; qualidade próxima de 8K não foi testada.

Em 14 amostras de execução normal (mais uma diagnóstica), pico do app de
3.730.051.072 bytes e pico GPU de 2.816.806.912 bytes. As menores margens foram
1.638.658.048 bytes do app e 1.169.459.610 bytes GPU. Os gates de recursos
passaram nas amostras. Pools UMA podem se sobrepor: não somar esses valores.
Não houve medição térmica ou ensaio prolongado.

O executor foi fechado pelo cliente e seu desaparecimento foi confirmado:
estado `sleeping`, sem pedido pendente, jobs ou leases ativos. As três entidades
continuaram dormindo. A Central foi iniciada sem `--entity`; seu endpoint
autenticado confirmou Xbox selecionado, sincronização/início habilitados e LAN
aceita. Rotina noturna, aprovação automática de dados e desligamento seguem
desativados. Abrir a Central não acorda Alistair; a partida do Xbox ocorre
quando o usuário o acordar, com o console ligado em Dev Mode/Game.

Os 40 contratos offline Xbox passaram novamente após o teste físico. Aprovação
de protocolo/formato não homologa personalidade, raciocínio, memória ou adoção
automática de outro modelo; erros de qualidade anteriores continuam válidos.
Registro integral sintético:
`compartilhado/runtime/alistair-execution/integration-synthetic-20261019-v5r2.json`.
As tentativas diagnósticas v3/v4 e pré-verificações v5/v5r1 permanecem no mesmo
diretório, assim como os recibos de compilação, download e instalação.
