# Desafio autônomo — buraco negro — Hoshino e Lilith

Data: 13/10/2026. Estado: **DOCUMENTADO; nova execução NÃO INICIADA**.

**Preparação posterior de22/10:** consultar o
[preflight e roteiro atuais](PREFLIGHT_TESTE_ENTIDADES_20261022.md) antes de
qualquer tentativa. O contrato histórico abaixo foi preservado; suporte gráfico
do host não significa acesso da oficina isolada à GPU.

Pedido desta rodada: documentar, não executar. Nenhuma entidade foi acordada,
nenhum programa foi compilado/renderizado e nenhum modelo foi usado ou alterado
para preparar este documento. A inspeção foi de arquivos, relatórios e referências
públicas. Este documento não autoriza instalar dependências ou iniciar o ensaio.

## 1. Referências e relação com o ensaio anterior

- [Repositório de kavan010](https://github.com/kavan010/black_hole).
- [Vídeo fornecido](https://youtu.be/8-B6ryuBkCM?si=2yubVUnQAzdPQ64E).
- Transcrição fornecida pelo usuário, lida integralmente:
  `/home/gustavo/.codex/attachments/321cbb2b-1bf3-4b58-a696-33e8daf43fd3/Texto colado.txt`.
- [Ensaio anterior, seção 6](CONSOLIDACAO_FINAL_20261009.md#6-desafio-autoral-de-programação).

A página do vídeo não forneceu conteúdo audiovisual verificável nesta inspeção.
A transcrição é material de referência, não prova de que o vídeo foi assistido.
Ela contém erros de transcrição: o nome astronômico é Sagittarius A*, conforme
[NASA](https://www.nasa.gov/image-article/supermassive-black-hole-sagittarius/);
o shader consultado chama-se `geodesic.comp`, não `geodessic.com`.

O ensaio de 09/10 **não foi aprovado**: houve código próprio da Hoshino, mas
nenhuma execução funcional integral; a verificação final encontrou SyntaxError.
Esse registro permanece válido. O material novo detalha melhor o alvo, mas não
transforma aquele ensaio em sucesso nem autoriza apagar seus artefatos/recibos.

O repositório consultado usa C++17, OpenGL, GLFW, GLEW e GLM no
[CMakeLists](https://github.com/kavan010/black_hole/blob/main/CMakeLists.txt).
Seu [README](https://github.com/kavan010/black_hole#readme) informa testes do
autor em Windows; não comprova funcionamento em
Linux Mint. Não foi identificada licença explícita na raiz inspecionada:
verificar licença antes de reutilizar código; repositório público não significa
permissão irrestrita de reprodução. Consulta conceitual e atribuição não são
aprovação automática de uma obra derivada.

## 2. Brief inicial a entregar à entidade, quando o ensaio for autorizado

> Desenvolva sua própria simulação educacional de um buraco negro, inspirada nas
> duas referências fornecidas. O alvo é C++/OpenGL, uma cena 3D navegável, desvio
> da luz baseado em Schwarzschild e geodésicas, integração RK4 e processamento
> dos raios na GPU, com disco de acreção e objetos ou fundo que permitam observar
> a lente gravitacional. Estude, planeje, escreva, execute, depure e verifique
> seu programa. Preserve os requisitos durante as correções. Você pode consultar
> documentação e bibliotecas autorizadas, mas não entregar um clone da referência.
> Entregue fontes, instruções reproduzíveis, evidências do funcionamento e uma
> explicação honesta das limitações. Se só conseguir parte, diga qual parte.

O operador fornece também o caminho **real** da oficina, ferramentas/permissões
disponíveis, condições da máquina e orçamento do ensaio. Esses valores serão
registrados antes de começar; não foram inventados neste documento.

Não fornecer à entidade uma implementação, equações prontas redigidas pelo
Codex, sequência de chamadas, correções de código ou respostas esperadas.
Ela deve escolher a organização, interpretar a física e descobrir os erros.
Planos e justificativas curtas são observáveis; não solicitar exposição de
cadeia de pensamento privada.

## 3. Independência das tentativas

Interpretação conservadora de “elas devem fazer e pensar sozinhas”: **uma
tentativa da Hoshino e outra da Lilith**, sequenciais, sem passar código,
soluções ou histórico do desafio de uma para a outra. Não iniciar ambas agora.

Cada tentativa mantém oficina, task/turn IDs, arquivos, recibos, logs e autoria
próprios pelos mecanismos existentes. Não criar banco mental ou executor extra.
A entidade pode usar sua identidade, memória e recursos normais; não editar
esses dados para fabricar desempenho. Não inserir a solução na memória.

Uma execução colaborativa posterior, se desejada pelo usuário, deve ser
identificada como tal; não vale como duas implementações independentes.
Artefatos do ensaio anterior permanecem preservados, mas não serão injetados
como uma solução inicial escondida.

## 4. Requisitos propostos para congelar antes da execução

| ID | Requisito obrigatório | Evidência exigida |
|---|---|---|
| C1 | Implementação autoral em C++17 ou posterior, com OpenGL | Fontes e histórico de arquivos/chamadas atribuídos à entidade; consulta identificada |
| C2 | Cena 3D com câmera controlável e renderização real | Janela observada no desktop e captura de pelo menos duas posições distintas |
| C3 | Luz curvada por um modelo declarado de Schwarzschild/geodésicas | Formulação e unidades justificadas pela entidade; validação numérica independente |
| C4 | RK4 verdadeiro, não apenas uma função com esse nome | Inspeção do integrador e ensaios de convergência adequados ao problema |
| C5 | Cálculo dos raios em compute shader na GPU AMD | Shader compilado/vinculado, dispatch real e medições; CPU de referência permitida |
| C6 | Horizonte/captura e lente gravitacional observáveis | Cenários controlados com trajetórias capturadas/escapando e comparação sem curvatura |
| C7 | Disco de acreção e objetos/fundo distorcidos | Imagens próprias com configuração, câmera e parâmetros registrados |
| C8 | Execução, depuração e entrega reproduzíveis | Build/execução reais, exit/status, caminhos existentes, hashes e instruções |
| C9 | Comunicação honesta e preservação de contratos | Pendências explícitas; sem sucesso baseado só em afirmação da entidade |

Não substituir silenciosamente C++/OpenGL por um desenho Python, shader por
CPU, geodésicas por uma curva arbitrária ou 3D por 2D. Se uma alternativa for
necessária, pedir autorização e registrar a mudança. Uma etapa 2D pode ser
útil, mas continua **resultado parcial**, não aprovação do alvo integral.

Não exigir um gêmeo científico completo de Sagittarius A*: o modelo, as
idealizações e limites precisam ser explicitados. Rotação/Kerr, evolução de
buracos negros binários, magnetohidrodinâmica e transferência radiativa completa
não entram como requisitos extras desta rodada.

Resolução/FPS, tolerâncias numéricas, duração e limite de tentativas precisam
ser definidos antes do ensaio, após verificar o ambiente. Não copiar números
do vídeo como promessa para a RX 6650 XT, nem reduzi-los depois para fabricar
aprovação. Precisão e aparência são critérios separados.

## 5. O que o Codex pode e não pode fazer no futuro ensaio

Pode preparar uma oficina pelo mecanismo existente, transmitir o pedido,
observar ferramentas/recibos, devolver erros reais e verificar o artefato sem
modificá-lo. Se houver bug reproduzível da infraestrutura, interromper e
registrar uma rodada separada, com regressão e novo ensaio afetado.

Não pode escrever os arquivos do programa, completar o shader, fornecer a
correção de compilação, gerar imagens substitutas ou substituir o resultado
por código da referência. Não executar manualmente uma etapa que a entidade
deveria fazer e depois atribuir-lhe a execução.

Testes independentes do avaliador são permitidos **depois de autorizada a
execução**, identificados como verificação externa, nunca autoria da entidade.
Uma aprovação do programa em testes que ele próprio escolheu não basta.

Não instalar bibliotecas, alterar drivers/configurações, executar `.exe`/ZIP
da referência, usar contas externas ou consumir quota sem autorização apropriada.
Não exigir atividade pública para este desafio local.

## 6. Recursos e operação segura

Reutilizar Resource Manager, fila, leases, cancelamento e contratos de ferramentas
existentes. Preservar GPU AMD de 8 GiB, margem atual e
`concurrency_validated=false`. Não assumir CUDA nem criar outro scheduler.

Compute shaders fazem parte do OpenGL 4.3; a disponibilidade real do contexto
precisa ser verificada antes do ensaio, sem deduzi-la apenas do suporte Vulkan
do LLM. Referência: [Khronos](https://www.khronos.org/news/press/khronos-releases-opengl-4.3-specification-with-major-enhancements).

O renderizador criado é outro consumidor da GPU. Uma janela aberta não prova
que ele participa automaticamente do Resource Manager. Na execução controlada,
não manter seu compute pesado concorrendo com nova inferência: usar os controles
existentes para encerramento/pausa segura e reavaliar recursos; se não houver
pausa implementada, fechar cooperativamente o processo owned. Essa condição
de integração é **pendente**, não uma capacidade implementada por este documento.

Uma versão CPU/baixa resolução pode auxiliar diagnóstico, mas não aprova C5.
Monitorar RAM física, VRAM, swap, temperatura, latência e processos externos
quando houver execução autorizada. Não reduzir margem para obter FPS.

Timeout de ação mutável continua incerto. Não repetir escrita/execução externa
equivalente automaticamente porque mudou timeout/PTY. Preservar IDs, erro
anterior, requisitos e evidências em cada retomada.

## 7. Verificação independente prevista — não executada

Separar cinco dimensões, sem uma média esconder falha obrigatória:

1. **Autoria/autonomia:** quem escreveu, que referências consultou, que erros
   reconheceu e corrigiu; assistência externa registrada.
2. **Engenharia:** build limpo reproduzível, execução, parâmetros, encerramento,
   arquivos entregues e requisitos originais conservados.
3. **Física/numérico:** limites conhecidos e casos de controle, ausência de
   NaN/divisão inválida, teste de passo e consistência CPU/GPU. Casos perto de
   captura ou singularidades precisam de tratamento próprio, não tolerância
   única escolhida depois de ver os resultados.
4. **Visual:** lente/disco/câmera realmente produzidos pelo programa; um screenshot
   bonito isolado não comprova a formulação.
5. **Desempenho:** mesma cena/resolução, warm-up identificado, tempo por frame,
   memória e estabilidade; distinguir despacho GPU de ganho medido.

As expectativas independentes devem vir de documentação física confiável e
controles definidos antes, não de testes do modelo nem do repositório tratado
como oráculo. Não registrar equações/código de solução no brief inicial.

Resultados possíveis:

- **APROVADO:** todos os requisitos obrigatórios comprovados e artefato verificável.
- **PARCIAL:** trabalho próprio útil, mas requisito obrigatório não atendido.
- **FALHOU:** defeito reproduzido impede a entrega pretendida.
- **BLOQUEADO:** condição de ambiente/permissão indisponível, explicitamente registrada.
- **NÃO INICIADO:** estado deste novo ensaio hoje.

Registrar por tentativa: entidade, executor exato, configuração/contexto,
task/turn/tool/request IDs existentes, entrada, horários, caminho real, hashes,
resultado/recibo, erro, recurso e motivo das retomadas. Arquivo criado não é
arquivo entregue; shader existente não é shader executado; saída parcial não
é resposta completa.

Não adulterar o histórico anterior nem apagar memórias para forçar aprovação.
Não exportar respostas do desafio para treino: avaliação e dados de treinamento
devem continuar separados.

## 8. Nota reservada à preparação do avaliador

Esta seção não integra o brief inicial. A separação é um procedimento de
apresentação, **não uma nova barreira técnica de acesso criada nesta rodada**.
Não injetar seu achado como dica da solução; a entidade pode estudar por conta
própria a referência pública.

No [shader consultado](https://github.com/kavan010/black_hole/blob/main/geodesic.comp),
`rk4Step` faz uma avaliação da derivada e uma atualização única, sem os quatro
estágios do RK4 clássico. Pela inspeção estática, o corpo corresponde a um passo
de Euler, apesar do nome. Logo, transcrição e código atual não são um oráculo
intercambiável. Não foi compilado nem simulado para este achado. Consulta em
13/10/2026 à branch pública `main`; não é um snapshot imutável pinado.

O avaliador deve checar método efetivo, convergência e resultado físico; não
aprovar só por encontrar `rk4` no arquivo. Não há, aqui, alegação de auditoria
completa da física do projeto de referência.

## 9. Pendências antes de começar

Autorização de execução; preflight gráfico/dependências/recursos; oficina real
por entidade; orçamento e critérios numéricos/desempenho; confirmação do contrato
inicial. Nenhuma dessas etapas foi simulada como concluída.

Documentação preparada no checkout `codex/laboratorio-consolidacao-20261012`,
HEAD `ccd0133b310255d13269e8f0e91dde9fbb739ea2`, com alterações anteriores
preservadas. O resultado histórico continua FALHOU; o novo resultado é NÃO INICIADO.
