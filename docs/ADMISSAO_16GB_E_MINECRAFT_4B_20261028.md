# Uma entidade sem GPU16GB e ensaio Minecraft4B — 28/10/2026

Pedido humano: impedir execução de mais de uma entidade até haver uma GPU
com pelo menos16GB deVRAM; testar Qwen3.5-4B noMinecraft. Instrução posterior:
usar **16.000 tokens de contexto no ensaio**. Não houve aquisição de GPU,
remoção de equipamentos, download ou substituição de pesos por esta mudança.

## Regra implementada

- Conta Hoshino, Lilith e Alistair, inclusive início e drenagem. Alistair remoto
  também ocupa uma entidade na política global pedida pelo humano.
- Uma placa física precisa atingir a classe16GiB;8+8 não basta. Não contaRAM,
  swap ou memória gráfica compartilhada. GPU desconhecida permite uma entidade,
  bloqueando a segunda. Até64MiB de reserva do driver são tolerados na fronteira
  nominal16GiB;12GiB/15GiB não são arredondados para16GiB.
- CapacidadeAMD porsysfs eNVIDIA porconsulta local`nvidia-smi`, se instalado.
  Não instalaCUDA/NVML nem soma placas. A placa atual foi observada com
  8.573.157.376bytes, aproximadamente8GiB; portanto permite uma entidade.
- Central e entradas diretas verificam admissão sob a mesma trava global.
  Preparação mantém`entity.boot.lock` por descritor herdado até sair; runner
  mantém`entity.lock`. A reserva de boot é separada da manutenção para permitir
  recuperação de pesos locais sem liberar outra entidade. DaemonOllama não
  herda essa reserva.
- Presença expirada não ignora locks reais. Um segundo pedido recebe recusa
  clara; pedidos existentes de despertar/restauração não são consumidos como
  sucesso se foram bloqueados. Não há novo scheduler, desligamento forçado ou
  troca automática de entidade.
- Entrar por`app/main.py` também passa pelo runner antes dos imports pesados.
  A regra não depende apenas de um botão desativado na interface.

É uma condição de admissão, **não liberação automática de inferências paralelas**.
RM, margens e leases continuam vigentes; seu teto validado e sonda de usoAMD
não foram ampliados com base na nova sonda de capacidade. Uma futuraNVIDIA
precisará de verificação real do backend/telemetria antes de prometer desempenho.

Na lista cogitada pelo humano, aRTX4070Ti comum tem12GB; a4070TiSUPER tem16GB.
[Fonte oficialNVIDIA](https://www.nvidia.com/en-gb/geforce/graphics-cards/40-series/rtx-4070-family/).
RTX5060Ti existe em8/16GB eRTX5070Ti tem16GB; conferir a variante exata.
[Comparação oficialNVIDIA](https://www.nvidia.com/en-us/geforce/graphics-cards/compare/).

## Testes e ativação

Os testes novos verificam fronteira/sondaNVIDIA, placa desconhecida, duas placas
de8GB, corrida entre runners, dois shells reais antes da preparação, descritor
inválido, boot versus manutenção e bloqueio com presença ausente. A restauração
tem regressão específica para manter pedidos e não adiar o prazo em cada poll.
Fixtures antigas passaram a fornecer raiz/presença completas no ambiente temporário.

Evidências locais em`compartilhado/runtime/ensaios/auditoria-logica-20261028/`:
`suite-admissao-16gb-entrega.log`, logs anteriores preservados e
`central-admissao-16gb-reload.json`. Resultado final: **97/97grupos offline**,
incluindo11casos da admissão e a regressão de restauração. Uma primeira execução
mostrou2falhas de fixtures antigas (raiz real/presença incompleta); corrigidas
sem relaxar as guardas. A revisão independente dos três ajustes finais não
encontrou bloqueio remanescente por leitura; não substitui uso prolongado.

Central recarregada cooperativamente: PID anterior saiu e porta livre foi
conferida antes da nova partida, sem acordar entidades. Durante o ensaio4B,
`POST /api/start` paraHoshino retornou400 com a exigência16GB, mantendoLilith
awake. Evidências: `live-api-admission.json` e`verification-delivery.json`
(277links locais conferidos, nenhum ausente na verificação).

## Ensaio4B: método e estado

Script opt-in: [testar_minecraft_4b.py](../scripts/testar_minecraft_4b.py).
Usa alias4B local pinado, sem trocar a seleção permanente9B/4B. A escolha do
executor fica fixa no ciclo: nenhum fallback silencioso para9B. O teste usa
o mesmo decisorMinecraft, formato estruturado, dispatcher e leases reais.

Objetivo independente: fabricar uma picareta de pedra no servidor atual
`10.0.0.200:25565`, jogador`LilithMC`, sobrevivência. Não recebe sequência de
ações nem materiais. Inventário existente é condição inicial; não é ensaio
do zero. Tarefa/caderno de teste ficam em banco separado, preservando a tarefa
das carnes`ct-d76da17105`, identidades e memórias reais. Janela de até12decisões
e600segundos cooperativos; observações auxiliares são adicionais. Efeito
incerto interrompe novas ações e exige reconciliação, sem repetição automática.

Medidas: tempo por decisão e chamada, contadores reais doOllama quando
presentes, ocupação/leases, ação escolhida, recibo, craft/inventário e falhas.
Não gravar thinking/diários privados. Sem comparação direta de velocidade com
9B de outra sessão/hardware/contexto diferente como se fosse um teste pareado.

Primeira preparação`20261028T195431Z-9c4fc5cc` parou antes de inferir/conectar:
o harness usou um canal não aceito e a consulta recebeu`permission`. Zero
chamadasLLM, zero decisões; **não é reprovação do4B**. A ponte criada ficou
desconectada, a evidência foi preservada e precisa ser reconciliada antes da
nova tentativa com canal correto e contexto16.000.

## Resultado real do4B com contexto16.000

Execução`20261028T195850Z-7d4505ec`, encerrada às17:06:45 locais.
**Não concluiu a picareta dentro das12decisões.** Isso é falha deste objetivo
no orçamento do ensaio, não prova de que o modelo nunca consiga jogar.
Não houve intervenção com coordenadas/rota, novos itens ou resposta do condutor
à pergunta que ele enviou. A configuração permanente dos executores foi preservada.

| Medida | Observado |
|---|---|
| Executor efetivo | `lilith-qwen3.5-4b-original-72ade0b11c3e:latest`; somente4B, sem troca para9B. |
| Contexto/saída | Janela fixa16.000; saída leve1.024. Entradas contabilizadas peloOllama:840–8.858tokens; não foi teste com16mil tokens de entrada preenchidos. |
| Tempo total | 474,18s, aproximadamente7min54s, incluindo observação/ações/limpeza. |
| Decisões | 12; mediana35,40s, faixa19,10–55,18s. |
| Chamadas e geração | 24respostas dobackend;14.215tokens gerados;41,93tokens/s agregados apenas no tempo de geração. Não é taxa de conclusão de ações. |
| Limite de saída | 11respostas terminaram por comprimento; o ciclo utilizou sua etapa de conclusão sem raciocínio. Não são11falhas de transporte nemOOM. |
| Eventos do agente | 7sucessos,2erros com recibo e3recusas anteriores ao efeito. Sucessos incluem conexão/chat/equipamento, não7avanços na tarefa. |
| Produção confirmada | 1bancada,4tábuas de bétula e4gravetos; coleta de madeira com recibo. Nenhuma picareta de pedra fabricada. |
| Memória observada | Ollama informou3.680.438.844bytes deVRAM do modelo, aproximadamente3,43GiB, e contexto16000. Amostra deVRAM total da placa:5.373.505.536bytes, aproximadamente5,00GiB. |
| Uma amostra térmica | GPU99%, edge64°C, junction91°C, memória56°C. Não é medição contínua de pico. |
| Desfecho | Tarefa isolada`ct-77ea863da0` pausada ao atingir o orçamento de iterações. |

O primeiro erro de colocação informou ausência de chão livre sólido. O4B
reconheceu que precisava mudar de posição, mas repetiu colocação sem mover-se;
também repetiu a mesma pergunta nochat, recusada por falta de contexto novo.
Depois tentou uma referência a5,9blocos, recusada explicitamente por distância,
e terminou segurando a bancada. Não conseguiu transformar o diagnóstico em
uma ação de navegação que resolvesse o pré-requisito. Há também comentários
imprecisos sobre materiais/quantidades; linguagem confiante não confirma o plano.

Portanto, neste recorte: **hardware/contexto viáveis; ações básicas funcionam;
planejamento e autocorreção insuficientes para aprovar autonomia**. A repetição
observada ocorreu sem mudança de posição; não atribuir essa recusa específica
ao bug de cache que ignora posição, pois a mudança necessária não aconteceu.
As falhas mecânicas da auditoria geral continuam separadas desta avaliação.

O gargalo visível é a latência do ciclo, não apenas a velocidade de geração.
Próximo experimento útil: comparar o modo rápido sem raciocínio para habilidades
mecânicas com o modo atual, mantendo modelo/contexto e condições comparáveis.
Isso permanece **proposta**, sem alterar a personalidade ou desativar o modo
de raciocínio permanentemente para produzir um resultado favorável.

## Evidências e encerramento

Resultados locais em
`compartilhado/runtime/ensaios/minecraft-4b-20261028/20261028T195850Z-7d4505ec/`:

- `report.json`: decisões públicas, recibos, estado inicial/final, limites e
  contadores finais doOllama, sem thinking/diário privado.
- `summary.json`: medidas derivadas e contagens, sem confundir rejeição com execução.
- `resource-observations.json`: amostra física da janela/modelo/VRAM/temperatura.
- `operator-cleanup.json`: desconexão confirmada, modelo descarregado e encerramento
  somente da ponte criada na primeira preparação, após conferir PID, instante
  de partida e estado ocioso. Nenhum processo foi morto por nome/porta.

Ao fim: três entidades dormindo,0jobs ativos e0leases. A Central permanece
aberta com a trava16GB ativa; tarefa das carnes e dados existentes preservados.
O ensaio não foi retomado nem convertido em uma rotina automática.
