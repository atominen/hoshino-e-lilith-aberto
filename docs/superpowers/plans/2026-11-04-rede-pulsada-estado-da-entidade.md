# Plano inicial da rede pulsada na Lilith

Status em 04/11/2026: plano para ensaio isolado. A linha principal continua
congelada conforme o [escopo vigente](../../../ESCOPO_CONGELADO.md).

## Objetivo

Dar à Lilith um estado rápido que carregue o efeito de acontecimentos
recentes entre uma decisão e outra. O estado rápido, as emoções registradas,
o humor e a interpretação pelo Qwen pertencem à mesma entidade. A Lilith
continua sendo a dona das experiências e decisões. Começamos com ela e
avaliamos a Hoshino depois, com estado e calibração próprios.

Há duas hipóteses separadas. A rede pode melhorar continuidade e recuperação
depois de um estímulo. Um filtro de rotina pode poupar chamadas ao modelo
quando há repetição confirmada e nenhuma pendência. Cada ganho deve aparecer
na comparação com sua própria referência.

## Ponto de partida

- A ponte do Minecraft já reage a dano e observa ameaças próximas.
  [Reflexo atual](../../../compartilhado/servicos/minecraft/bridge.js).
- O sistema já traduz eventos em emoções e oferece ao modelo o humor.
  [Emoções](../../../app/mind/emotions.py), [humor](../../../app/mind/affect.py)
  e [montagem do contexto](../../../app/core/prompting.py).
- A associação isolada errou uma decisão adicional no ensaio com o 4B.
  O filtro economizou 37% dos tokens em cinco situações sintéticas, mas
  houve uma justificativa que introduziu um assunto ausente do cenário.
  [Resultados e limites](../../ENSAIO_ENTIDADE_PESTINHA_20261104.md).
- Uma sonda temporária do núcleo original aplicou um pulso de impacto de
  100 ms. O sinal de susto aumentou, mas o decodificador padrão não escolheu
  susto nas 12 repetições. O custo mediano foi 0,81 ms de CPU por 20 ms
  simulados naquela rodada. Isso mede cálculo, não latência no jogo.
  [Núcleo upstream na revisão ensaiada](https://github.com/mille-okws/pestinha/blob/984fb8677093cd868bf4f9712a43f19b44215f75/pestinha/core/nervous_system.py).

## Contrato do protótipo

| Fluxo | Dados mínimos | Efeito permitido na fase inicial |
|---|---|---|
| Observação → rede | Entidade, ID, instante, tipo, intensidade e evidência | Aplicar um pulso e atualizar sinais internos |
| Rede → contexto | Alerta, susto, tendência de recuperação e IDs dos eventos | Oferecer ao LLM um resumo quando houver decisão a tomar |
| LLM → rede | Interpretação tipada, confiança e IDs das evidências usadas | Ajustar familiaridade ou recuperação com peso limitado |
| Ponte → avaliação | Ação escolhida pelo reflexo, recibo e efeito observado | Comparar a sugestão da rede com o que aconteceu |

O adaptador trata fatos confirmados, hipóteses e pedidos humanos como
categorias diferentes. Dano confirmado mantém prioridade sobre uma
interpretação tranquilizadora. Um evento repetido pelo transporte usa o
mesmo ID e conta uma vez. Um pedido humano e um efeito incerto chegam ao
LLM mesmo quando o sinal rápido está baixo. Um resumo gerado pelo próprio
LLM não vira uma nova observação, para impedir que o estado se amplifique
em circuito fechado.

## Etapas de implementação e teste

- [x] **Reprodução da rede em CPU.** Criar
  `scripts/ensaiar_rede_pulsada_entidade.py` com relógio simulado, sementes
  registradas e o núcleo original carregado a partir de um checkout
  temporário. Reproduzir impacto, som repetido, som ambíguo e silêncio.
  Registrar entrada, pico, tempo até o pico, recuperação e custo de CPU.
  Usar a mesma topologia nas primeiras comparações.
- [x] **Adaptador em observação.** No mesmo ensaio, receber os contratos da
  tabela acima. Usar recibos simulados no teste de combate, com fuga,
  defesa e contra-ataque registrados separadamente. Verificar deduplicação,
  isolamento entre entidades e que a sugestão só aparece no relatório.
  Exercitar um dano seguido de interpretação tranquilizadora para verificar
  a prioridade do fato.
- [ ] **Ligação nos dois sentidos com o 4B.** Estender o
  [ensaio com o Qwen](../../../scripts/ensaiar_entidade_pestinha.py).
  Comparar LLM com histórico, filtro sozinho e filtro com estado da rede.
  Alternar a ordem após aquecer o modelo. Usar os mesmos casos inéditos de
  conversa, ambiente, oficina e Minecraft para cada variante. Medir
  escolhas, justificativas, chamadas, tokens e tempo. Testar explicitamente
  que o mesmo som repetido, quando acompanhado de pedido humano, chega ao LLM.
- [ ] **Continuidade.** Salvar apenas o estado experimental com identidade,
  revisão da topologia e autoria do sinal. Simular pausa, recarga e expiração.
  Comparar com o mesmo ensaio iniciado do zero. Verificar recuperação coerente
  e rejeitar estado de outra entidade ou revisão incompatível.

## Critérios para avançar

1. A rede em observação não altera ações, ferramentas ou permissões.
2. A variante candidata preserva todos os pedidos humanos e todos os casos
   de efeito incerto na bateria. As justificativas citam evidência do caso.
3. A rede melhora pelo menos uma medida previamente escolhida, como menos
   alarmes repetidos sem perder dano confirmado, ou recuperação mais
   coerente após uma pausa, em comparação com filtro sozinho. Relatar também
   regressões, mesmo quando o número de chamadas cair.
4. Medir o custo da rede no mesmo hardware e separar tempo de inferência,
   cálculo neural e, em um teste posterior, confirmação do servidor.
5. Uma eventual integração usa o ciclo, a memória e o controle de recursos
   existentes. A validação offline precede qualquer ensaio com o jogo real.

## Quando aumentar a rede

As populações já são definidas em configuração no código upstream. Aumentar
uma população é uma alteração pequena no construtor, mas muda as conexões
geradas e pode afetar a leitura de estados salvos. Primeiro identificar uma
distinção que a topologia atual não represente, por exemplo susto passageiro
versus ameaça persistente. Só então testar um canal ou grupo novo, com
estímulos, ligações, duração, custo e versão do estado definidos. A fonte
original fica no ensaio temporário durante essa avaliação. O reaproveitamento
direto no produto depende da revisão de compatibilidade com a licença
GPL-3.0 do Pestinha.

## Identificar música como habilidade normal

Proposta de habilidade `identificar_musica`, disponível nas conversas e
nas atividades das entidades sempre que houver uma fonte permitida. A
entidade pode usá-la para atender ao usuário ou para investigar música
durante uma atividade própria com escuta autorizada. A aba **Áudio →
Fontes e atenção** é o ponto para escolher a fonte e consultar o resultado.
A habilidade usa um trecho delimitado da fonte selecionada. A disponibilidade
da habilidade não implica reconhecimento contínuo.

- Reutilizar a permissão de captura da fonte e a chave de internet para
  consultas ao catálogo externo. Sem áudio autorizado ou provedor
  disponível, retornar o impedimento como resultado da ferramenta.
- Registrar ID do trecho e da fonte, horário, provedor e desfecho. Em caso
  de correspondência, incluir faixa e artista quando o catálogo os
  retornar. Tratar sem correspondência, indisponibilidade e timeout como
  desfechos distintos. O áudio bruto não faz parte do recibo.
- Oferecer o resultado ao LLM como observação do trecho. Só vincular
  familiaridade ao evento de áudio correspondente. O nome da faixa
  não autentica o aplicativo que a reproduziu e não explica outros sons
  simultâneos nem altera ameaças confirmadas.
- Em Linux, ensaiar um adaptador de [ShazamIO](https://github.com/shazamio/ShazamIO)
  separado do restante do áudio. O [ShazamKit oficial](https://developer.apple.com/shazamkit/)
  atende às plataformas listadas pela Apple e ao Android. Manter o
  contrato de recibo independente do provedor.
- Validar primeiro com respostas simuladas, incluindo música e dano no
  mesmo intervalo. Para avaliar o provedor real, usar uma amostra de
  música conhecida em fonte de teste e medir identificação, ausência de
  correspondência e latência. A implementação na Central fica para a
  etapa de integração após o ensaio isolado.
