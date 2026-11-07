# Troca de executores e perfis dinâmicos — 24/10/2026

> Snapshot histórico: em27/10 a decisão foi substituída por
> [4B/9B, professor preservado](ORGANIZACAO_4B_9B_20261027.md).
> Pesos6B/7B foram retirados. O inventário abaixo descreve24/10.

**Decisão em24/10:** Hoshino/Lilith ficam com **7B e 9B na troca dinâmica**;
Alistair mantém seu mesmo 4B. O Qwen3-6B SNIPER baixado está preservado somente
como pesquisa, fora da rota automática. O requisito anterior de um terceiro
6B foi substituído e sua busca/integração está pausada. Yi e Qwen3-4B
experimental foram retirados anteriormente; o inventário abaixo é histórico.
[Estado atual](SUBSTITUICAO_YI_EXECUTOR_RAPIDO_20261024.md).

Atualização posterior nesta mesma data: o usuário autorizou integrar/testar o
Yi6B. O suporte foi implementado, mas os testes reais reprovaram e a ativação
automática permanece desligada. [Evidências e gates](YI6B_INTEGRACAO_E_TESTES_20261024.md).
As contagens abaixo registram a auditoria anterior a esses ensaios sintéticos.

## Resultado da auditoria

O seletor **não usa automaticamente todos os sete executores**. São sete
seleções individuais sobre quatro famílias; identidade e memória continuam
externas aos pesos e separadas por entidade.

| Entidade | Catálogo automático atual | Seleção manual adicional | Uso observado em23–24/10 |
|---|---|---|---|
| Hoshino | Qwen3.5 9B + Qwen2.5 7B | Yi1.5 6B | 9B; sem chamada7B identificada nesta janela |
| Lilith | Qwen3.5 9B + Qwen2.5 7B | Yi1.5 6B | 9B e7B |
| Alistair | Um executor4B, no destino configurado | Não se aplica | 4B |

Verificação de catálogo em24/10: os sete aliases selecionados são **originais**,
presentes nos respectivos stores; `runtime_alias` conferiu os manifestos pinados
e a existência/tamanho dos blobs. Não foi feito um novo hash integral de todos
os pesos, download, carga de modelo ou inferência nesta auditoria. O ambiente
foi sanitizado por entidade para reproduzir a precedência do launcher; herdar
`HOSHINO_MODEL` de outra entidade produziria um inventário incorreto.

Contagens dos diagnósticos locais, sem ler/expor conteúdo de conversa:

- Hoshino:16 decisões9B (13 qualidade,3 principal quente);17 finais HTTP200
  associados ao9B.
- Lilith:50 decisões9B (41 qualidade,9 principal quente) e3 decisões7B;
  77 finais HTTP200 do9B e3 do7B.
- Alistair:15 decisões4B e15 chamadas concluídas.

Decisão e chamada não são a mesma unidade: ferramentas e retries podem gerar
mais chamadas dentro de um único ciclo. Estes números não aprovam qualidade,
não são uma comparação de velocidade e não descrevem todo o histórico.
O7B de Hoshino é elegível, mas o roteador não força uso para preencher contagem.
O Yi não está no ramo automático de executor leve: permanece manual, sem
habilitá-lo por estar instalado. Selecioná-lo manualmente como principal é um
caminho distinto. Não se aprovou uma nova rota automática Yi nesta mudança.

## Primeira implementação

`app/core/resource_profiles.py` fornece seis predefinições ao **RM existente**.
Não cria serviço, fila, banco, agente ou scheduler adicional. A decisão ocorre
no primeiro pedido de inferência de cada ciclo de Hoshino/Lilith e permanece
fixa junto com o executor até a resposta, ferramentas e verificação terminarem.

| Perfil | Quando é solicitado | Efeito no roteamento |
|---|---|---|
| Qualidade | Trabalho complexo/importante | Conserva o principal; não disputa qualidade por custo |
| Resposta rápida | Pedido humano simples | Equilibra custo de chamada, fila e recarga |
| Recursos disputados | Outra entidade com compute/fila reais | Aumenta o custo de recarga e a preferência por pesos quentes |
| Trabalho de fundo | Pedido não interativo | Evita trocas caras; não muda a prioridade da fila humana |
| Pressão de memória | RAM abaixo da reserva+4GiB ou VRAM livre abaixo da margem | Penaliza reserva maior entre opções elegíveis |
| Conservador | Métricas ausentes, vencidas, instáveis ou RAM desconhecida | Evita recargas; não transforma incerteza em autorização GPU |

Residência ou presença `awake` sozinhas **não provam demanda concorrente**.
A histerese de60s evita oscilar entre perfis por variação breve; qualidade,
pressão, incerteza e passagem de fundo para pedido humano têm entrada imediata.
A recuperação de pressão/incerteza aguarda essa estabilização. O estado é
local ao processo e individual por entidade, sem persistir perfil obsoleto
entre boots. Os gates físicos são reavaliados normalmente a cada lease,
inclusive se o perfil estiver retido ou o ciclo já tiver executor fixado.

As mudanças são pesos de custo: recarga1×/2×, bônus de residência1×/1,5×,
fila interativa e penalidade de16 unidades porGiB de **reserva** sob pressão.
Esses valores são heurísticas iniciais, não tempos medidos nem estimativa de
consumo exato de RAM. Os custos de chamada anteriores também eram heurísticos.
Não há alegação de configuração ótima ou ganho de tokens/s demonstrado.

Alistair mantém seu único4B e o destino PC/PC2/Xbox existentes. O perfil de
escolha9B/7B não troca esse destino, configura seu backend remoto ou inventa
alternância de modelo para ele. O RM continua governando suas concessões locais.

## O que não muda

- Catálogo, versões pinadas, pesos, qualidade mínima e capacidade de ferramentas.
- Mensagens, contexto integral e limites de saída; o dimensionamento adaptativo
  de contexto existente continua separado deste novo seletor.
- Reservas físicas, camadas GPU, temperaturas, margem, teto8GiB e serialização.
- Identidades, memórias, permissões, serviços, treino e agendamentos.
- Nenhuma troca durante geração, interrupção de processo ou CPU fallback novo.

É uma boa estratégia ajustar a execução à carga, mas não forçar rodízio.
Carregar outro modelo e aumentar paralelismo/contexto pode consumir mais memória
e piorar a fila. A documentação do [Ollama sobre residência, memória e
concorrência](https://docs.ollama.com/faq) descreve essas limitações; o
[servidor llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
separa cache de prompts em RAM, contexto e execução. RAM não vira VRAM com a
mesma largura de banda e um cache de prompts não prova cache dos pesos.

## Operação, observabilidade e reversão

O evento técnico existente `executor.selected` passa a incluir
`resource_profile` e `cost_basis=heuristic_not_benchmark`, sem prompts privados.
Central → Recursos, tanto nativa quanto web, mostra os perfis disponíveis e a
**última decisão observada** por entidade, data e retenção contra trocas frequentes.
A consulta é limitada às caudas dos diagnósticos e não toma decisões, desperta
entidades ou faz sondagem de inferência. Ausência de recibo não é perfil ativo;
um recibo antigo tampouco confirma que o processo ainda está executando.

O código será carregado no próximo início normal dos processos. Na auditoria,
Hoshino/Lilith estavam dormindo, Alistair offline e sem jobs/leases ativos.
Não foram despertados nem reiniciados para fabricar evidência física.
Para reverter só esta política, definir `HOSHINO_DYNAMIC_RESOURCE_PROFILES=0`
no ambiente da entidade e usar o ciclo normal de sono/despertar; isso devolve
o custo anterior sem desfazer outras correções ou tocar dados. A interface
aberta antes da atualização precisa ser reaberta para receber o novo painel.

## Verificação e próxima calibração

Testes offline cobrem os seis perfis, métricas vencidas/incertas, pressão,
histerese, isolamento entre entidades, preferência de recarga, bloqueio de
rebaixamento complexo, contexto integral, ciclo imutável, reversão, projeção
sem dados privados e os painéis web/nativo.

Resultados finais, todos offline:

- **88/88 grupos** da suíte oficial aprovados, incluindo GPU cooperativa,
  painéis nativo/web e integraçãoXbox simulada. Log:
  `/tmp/perfis-recursos-oficial-final-20261024.log`.
- **91 testes** de executores aprovados no ensaio focal, incluindo os oito
  novos contratos de perfis. Log: `/tmp/perfis-recursos-executores-20261024.log`.
- **58 testes** de controle da Central aprovados no ensaio focal. Log:
  `/tmp/perfis-recursos-central-20261024.log`.
- Sintaxe Python/JavaScript, links locais dos documentos alterados e
  `git diff --check` sem falha. Os testes usam dados temporários e transporte
  simulado; não são prova de velocidade, execução deLLM ouGPU real.

Próxima etapa útil: medir carga fria/quente, espera de fila, primeiro token,
tokens/s, contexto real, VRAM/RAM e alternância Hoshino/Lilith em trabalho real.
Comparar os mesmos pedidos e validar qualidade antes de ajustar custos ou
habilitar outro executor automático. Afinar camadas/offload/cache/paralelismo
exige ensaio próprio de cada combinação; não experimentar cegamente em execução.

Estado nesta entrega: software implementado; benchmark físico e calibração
comparativa ainda pendentes. Não foi iniciado/reprogramado nenhum treino.
