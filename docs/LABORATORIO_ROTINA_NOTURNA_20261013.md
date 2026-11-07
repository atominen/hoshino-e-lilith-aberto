# Rotina noturna — mapa de implementação

Supervisor existente (`iniciar_entidades.py`) → política/configuração no registro
noturno existente → sondas `world_state`/Resource Manager e agendas read-only →
sono cooperativo → professor existente → curadoria com gates → trainer existente
→ recarga/holdout/crítica → promoção no registro estável existente.

Não há daemon, timer, banco mental, scheduler ou backend de IA adicional.
`rotina_noturna.py` contém adaptadores e transições chamadas pelo Supervisor;
não possui loop próprio. O painel configura o mesmo supervisor via loopback.

Padrões solicitados: 00:30, America/Sao_Paulo, 30 minutos de ociosidade observada.
“Vou dormir” explícito autoriza a janela; ociosidade só autoriza quando a política
de execução por inatividade estiver habilitada. Não é prova de sono/abandono.
O horário não autoriza ignorar processos externos, filas, efeitos incertos ou
agendas. Falta de sondas confiáveis bloqueia execução automática.

Históricos próprios são consultados read-only, com IDs/turnos/autoria preservados
em snapshots privados. Diários e mensagens de outras entidades não são copiados.
Histórico não vira resposta-alvo: falhas observadas orientam casos novos; nenhuma
lembrança/nome pessoal deve ser incorporada como fato permanente nos pesos.

Só dados completos, inéditos e criticados entram no corpus derivado. Conjuntos
originais de validação/holdout não mudam. Máximo duas tentativas por entidade,
segunda com diagnóstico aplicado, nunca replay depois de crash/efeito incerto.
Versão reprovada nunca substitui estável; ausência de estável preserva original.
Publicação no laboratório NÃO significa instalação do adaptador em produção.

Desligamento: somente após drenagem real, workers/leases encerrados, rechecagem
de presença humana, recursos e agenda. Agenda pendente mantém PC ligado e acorda
as entidades responsáveis. Rejeição/timeout do desligamento é diagnosticada,
sem retry automático. Nenhum teste deste desenvolvimento desliga a máquina.

## Configuração e uso

No painel: **Treinamento → Sessão noturna → Rotina diária automática**.
Horário/inatividade, autorização por ausência, duração por entidade, janela e
desligamento são configuráveis. Política padrão: **00:30 / 30 minutos**, janela
de 600 minutos, treino de 10 minutos, até 8 propostas por entidade. Isso NÃO é
o plano de 12 horas. A janela de início é de duas horas após o horário escolhido.

**Ativação permanece FALSE.** Nenhuma política de produção foi escrita nem
nenhuma sessão real foi autorizada. Valores padrão agora existem no código/UI;
salvar exige confirmação. A Central precisa estar aberta para configurar e
executar: o painel não cria outro agendador. A qualidade ainda não justifica
autorizar operação desacompanhada.

A frase humana direta “vou dormir”, “vou dormir agora” ou “estou indo dormir”
autoriza a janela contextual por 12 horas quando a rotina já estiver habilitada;
citação, pergunta, negacão ou mensagem de um LLM não autorizam. Uma noite por
data local; crash deixa recuperação explícita, não replay automático.

CPU/presença/mídia/GPU/RAM/disco/filas/leases/agenda são checados antes. A última
estável reaproveita seu corpus aprovado e hash de validação; perda/alteração do
corpus impede treino, sem retorno silencioso ao original. Entidades que não
couberam na última janela têm precedência na próxima. Não mudou o Resource
Manager. Espera por worker não regrava arquivo de sessão a cada segundo.

## Implementação desta rodada

- `laboratorio/rotina_noturna.py`: política, guarda, históricos próprios read-only,
  cursor/proveniência, corpus cumulativo, curadoria, tokenização, treino/avaliação,
  segunda tentativa limitada, restauração/agenda e pedido final de desligamento.
- `iniciar_entidades.py`: transições chamadas no tick existente, configuração
  autenticada, aviso humano de sono, checkpoint ao retorno do usuário, eventos
  `laboratory.learning_transition` e desligamento somente depois de shutdown.
- `app/main.py`: `input_sources` no registro de saída para relacionar entradas
  cujo `turn_id` ainda não estava preenchido. Legados usam os links de eventos,
  nunca adivinham mensagens vizinhas.
- `laboratorio/painel.py`, `web/app.js`, `web/index.html`: configurações por proxy
  do supervisor existente, confirmação e indicação de indisponibilidade.
- `laboratorio/treinos_unificados.py`: tarefa `learn` serial, orçamento físico,
  janela/agenda e recusa de replay de sessão cognitiva interrompida.
- `laboratorio/personalizacao.py`: perfil de Alistair sem pipeline mental novo;
  apenas identidade/papel próprios, sem referências experienciais da outra entidade.
- `laboratorio/professor_moe.py`: cobertura de emoções na amostra padrão, seleção
  contextual de perfil, thinking situacional, justificativa concreta de reprovação,
  crítico sem autoavaliação/confiança do gerador, bloqueio de causas/consultas/
  biografias inventadas, ações não solicitadas e strings cortadas por gramática.
- `laboratorio/tests/test_noite_supervisor.py`, `test_consolidacao.py`,
  `test_personalizacao_moe.py`, `browser.cjs`: regressões e transporte isolado.
- `laboratorio/tests/probe_critico_professor.py`: ensaio manual LOCAL no professor
  real, com o mesmo lease P5; não faz parte da CI, não exporta e não treina.

`versionamento_lora.py`/`treino_nf4_curto.py` já tinham modificações da rodada
anterior e foram preservados; esta rodada não criou outro mecanismo de treino,
avaliação, publicação ou rollback.

## Evidências reais — professor 35B / RX 6650 XT

Jobs, respostas reprovadas e métricas estão preservados em
`laboratorio-local/professor-moe-35b/`, fora do Git. Cada worker registra SHA do
código/perfil e libera o processo Vulkan e o lease ao terminar.

| Job | Entidade | Desfecho físico | Decisão |
|---|---|---|---|
| `504fc4fb9e9440c5` | Hoshino | 2/8; consultas/corpo inventados encontrados | não treinar |
| `709381c5ee8d4c5d` | Hoshino | 0/8; crítica/generação inadequadas | não treinar |
| `c040f45e664649d4` | Hoshino | 8/8 nos gates da época; revisão detectou erros reais | não aprovado |
| `76c446b5e00a4bb7` | Hoshino | 0/8; currículo emocional ainda inconsistente | não treinar |
| `cebad861dabe494a` | Hoshino | 0/8; crítico confundiu afeto/preferência com humanidade | corrigir classificação |
| `f466d64b4c654010` | Hoshino | 2/8; consulta a banco inventada | não treinar |
| `2257ae23964f42d8` | Lilith | 8/8 nos gates antigos; motivo passado e causa de recibo inventados | novo filtro reprova casos 6 e 7 |
| `a0e4072bc1604065` | Hoshino | 0/8; detalhe inventado sobre pintura | reprovação correta |
| `e099641542ab4ca7` | Alistair | 0/8; justificativa cortada por gramática e fatos inventados | não treinar |

Não são nove lotes aprovados: as falhas estão visíveis e nenhum foi exportado
automaticamente/treinado. Os dois lotes completos demonstram que JSON válido e
parecer positivo do próprio professor NÃO bastam para qualidade.

Medições dos primeiros seis jobs: pico de VRAM **6,86–6,97 GiB**, RAM disponível
mínima **23,69–25,22 GiB**, swap utilizada **1,46 GiB** sem crescimento nesses
ensaios; temperatura máxima observada **79–90 °C**. Sem pressão registrada pelo
monitor. Margem de **768 MiB** e concorrência desativada preservadas. Não são
prova de estabilidade de 12 horas nem de ausência universal de resets/leaks.
Inferências nesses jobs somaram **110,28–358,22 s** por tentativa de currículo,
sem confundir isso com tempo de otimização LoRA ou aprovação humana.

Crítico físico em controles separados:

- `critic-controls-20261013-155819.json`: 8/8 controles simples corretos.
- `critic-controls-20261013-160753.json`: **6/8** nos exemplos gerados da Lilith;
  deixou passar a afirmação sobre memória e a causa inventada do recibo. Esta
  comparação usou categorias de controle simplificadas; não é A/B idêntico de
  todos os metadados. Script agora conserva categoria/plano originais ao reproduzir.
- `critic-controls-20261013-161644.json`: **8/8** nos controles simples, com
  preferências/alegria/tristeza/incerteza permitidas e quatro defeitos rejeitados.

O crítico não ficou infalível. O filtro atual **v1.11.5** reavalia os dados e
reprova, por evidências concretas, os casos 6/7 daquele lote Lilith. Perguntar
“preciso ajustar a descrição?” não comprova que o recibo acusou falta dela.
“Eu estava tão ansiosa” sem origem não é reparação factual. Os erros reais viraram
regressões; propostas com filtro antigo não podem entrar no ciclo automático.

## Testes e preservação

Baseline desta rodada: **143/143** testes do laboratório e **74/74** grupos
offline oficiais. Resultado atual: **171/171** testes do laboratório; suíte
oficial também **74/74** após a integração. Inclui configuração/backup, datas,
isolamento, autoria, cursor, corpus cumulativo, drenagem, agenda, mídia, fairness
entre noites, worker vivo, segunda tentativa, não replay e promoção obrigatória.

Um teste antigo aceitava “não tenho registro no banco” apenas por estar numa
conversa técnica. Foi corrigido: tema técnico não comprova consulta; recibo de
consulta fornecido continua aceito. A falha inicial e o motivo não foram ocultados.

Painel real em localhost: navegador sem erros JavaScript, controles 00:30/30
visíveis; consulta informa Central indisponível quando ela está fechada. Teste
read-only não salvou política, não acordou entidade nem iniciou treino. Captura:
`/tmp/laboratorio-rotina-noturna-20261013.png`. Processo do painel: aproximadamente
**38 MiB RSS**, CPU momentânea 0%; não é benchmark prolongado da interface.

Hashes de nove arquivos reais (constituição, self-model e banco mental de cada
entidade) iguais antes/depois. Nenhuma base original, identidade, memória, corpus
original ou versão estável alterada. Nenhuma quota externa, cloud, download,
concorrência GPU ou desligamento real utilizado.

## Parecer e pendências

**Fluxo implementado e isoladamente validado; operação noturna real NÃO homologada.**
O professor ainda não produziu um currículo completo que supere a revisão
independente dos erros conhecidos. Manter desligado é uma decisão de qualidade,
não falta do horário solicitado.

Pendências: geração consistentemente natural/coerente nas três entidades;
teste físico curadoria → treino curto → recarga → promoção → restauração;
noite prolongada/checkpoints/retorno humano/agendas reais; autorização/policykit
do desligamento e prova física correspondente. Nenhum comando de poweroff foi
executado. Atualização da produção/instalação de adaptadores continua separada
da publicação estável do laboratório; não afirmar que o comportamento mudou
porque apenas um registro estável foi gravado.
