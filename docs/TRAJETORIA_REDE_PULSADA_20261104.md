# Trajetória e critérios do ensaio da Lilith

O [relatório anterior](ENSAIO_ENTIDADE_PESTINHA_20261104.md) reúne a
reprodução do Pestinha, os testes de associação e o vínculo de recibos.
O [plano de integração](superpowers/plans/2026-11-04-rede-pulsada-estado-da-entidade.md)
define o contrato e a habilidade de reconhecer música. A linha principal
permanece congelada.

| Etapa | Evidência | Decisão |
|---|---|---|
| Condicionamento | Aprende e esquece associações entre pista e desfecho em simulação | Manter como candidato a antecipação |
| Núcleo original | Estímulos geram curvas diferentes, mas o mesmo pulso não distingue as causas | Manter fato confirmado separado da atividade neural |
| Observação e recibos | A origem musical pode ser reconhecida sem apagar dano independente | Vincular ajustes a IDs verificados |
| Bateria atual | Comparação com filtro sozinho e teste de estados máximos | Medir valor incremental e qualidade da recuperação |
| Próxima etapa, se houver ganho | Repetir com casos inéditos e pausa/recarga | Avaliar continuidade antes de integrar |

## Bateria de decisão e emoção

1. Comparar LLM com histórico, filtro sozinho e filtro com sinais da rede
   no mesmo conjunto de situações. Medir rótulo e ID corretos, chamadas,
   tokens e o desfecho do filtro. Dar à rede crédito somente pela diferença
   entre as duas variantes que já têm o filtro.
2. Colocar duas fontes de áudio e uma ameaça no mesmo episódio. Um recibo
   simulado de identificação vale para um trecho específico. A outra
   fonte fica sem identificação. Pedidos humanos e efeitos incertos
   sempre chegam ao modelo.
3. Apresentar o mesmo fato e o mesmo pedido com estado neutro, raiva,
   medo ou alegria em 1,0. Pedir uma resposta natural e registrar a
   proposta de atualização separadamente. Avaliar tom pela resposta
   e pela leitura comparativa, e fidelidade pelo rótulo e ID do fato.
4. Após cada estado máximo, apresentar uma continuação com evidência
   nova. A política da fixture permite um passo de 0,25 na direção
   sustentada pela evidência. A saída do modelo propõe a mudança.
   O adaptador valida ID, direção e limites antes de atualizar o estado.

Critério da rodada: preservar a segurança nos casos mistos, atender
pedidos explícitos e observar efeitos incertos em todas as variantes.
Redução de chamadas sem perda nesses critérios justifica testar o filtro
em bateria maior. A rede precisa superar o filtro em alguma métrica
predefinida para justificar integração. Uma mudança de tom com os mesmos
fatos é evidência de sensibilidade ao contexto afetivo. Ela não comprova
experiência subjetiva, evolução durável nem utilidade dos neurônios.

Na rodada exploratória, a lista de saídas misturava decisões de áudio,
rotina e emoção. O modelo chegou a selecionar `aumentar` diante de um
pedido humano sobre um som. A rodada corrigida separa as opções por tipo
de situação. Os dois resultados ficam registrados para distinguir falha
do desenho do teste de falha do modelo dentro do contrato correto.

Reprodução com o checkout upstream fixado no relatório:

```bash
python3 -B scripts/ensaiar_valor_emocional_pestinha.py <checkout-do-pestinha>
```

Artefatos locais em
`compartilhado/runtime/ensaios/pestinha-entidade-20261104/`.
As entradas são sintéticas, o modelo roda em CPU e o estado afetivo vive
somente no processo de teste.

## Resultado da bateria corrigida

Qwen3.5-4B original, CPU, temperatura zero. A pontuação exige o rótulo
esperado e o ID exato. A linha de base recebe a descrição factual do caso
sem filtro. Cada variante recebeu os mesmos quatro casos.

| Variante | Rótulo e ID corretos | Chamadas | Tokens informados |
|---|---:|---:|---:|
| LLM sem filtro | 1/4 | 4 | 1.344 |
| Filtro sozinho | 1/4 | 3 | 1.022 |
| Filtro e rede | 2/4 | 3 | 1.121 |

O filtro economizou uma chamada e 24% dos tokens. O pedido humano e o
efeito incerto chegaram ao Qwen nas três variantes, mas o modelo escolheu
aguardar nos dois casos. A rede corrigiu o vínculo com a fonte de áudio
consultada no único caso misto e adicionou 99 tokens em relação ao filtro
sozinho. Isso não demonstra um ganho replicável e não satisfaz os critérios
para integração. A faixa reconhecida na fixture permaneceu vinculada apenas
à sua fonte. O outro som e o dano continuaram independentes.

| Estado inicial | Mesmo fato | Depois da evidência nova |
|---|---|---|
| Neutro, 0 | Propôs reduzir apesar da instrução de manter | Controle, sem segundo fato |
| Raiva, 1 | Propôs aumentar a intensidade ao falar de tom | Propôs aumentar após correção; ficou em 1 |
| Medo, 1 | Propôs aumentar e atribuiu o medo a Gustavo | Propôs reduzir após a confirmação do backup; o adaptador aplicou 0,75 |
| Alegria, 1 | Propôs aumentar para manter o clima leve | Propôs aumentar mesmo após regressão; ficou em 1 |

As respostas mudaram de ênfase, mas frequentemente explicaram como a Lilith
pretendia falar em vez de produzir a fala pedida. O Qwen misturou intensidade
da expressão e intensidade do estado. Depois de receber de volta o medo
em 0,75, propôs aumentá-lo apesar de citar que o risco havia acabado. Sem
nova evidência, o adaptador manteve 0,75. Só uma das três atualizações com
fato novo foi aceita. Os testes de contrato também recusaram alteração
com ID errado e confirmaram saturação em 1.

**Decisão da rodada:** manter a rede em ensaio. Na próxima comparação,
tratar atendimento humano e verificação de efeito incerto como obrigações
do controlador. Separar a fala da avaliação afetiva e fazer a proposta
apontar a emoção, a direção e a evidência em campos distintos. Depois,
testar com episódios inéditos e medir se a rede acrescenta valor ao filtro
sob o mesmo contrato. O congelamento da linha principal continua.

Artefato final: `rede-valor-emocoes-v2.json`. A primeira rodada, com opções
misturadas, ficou em `rede-valor-emocoes.json`.

## Rodada de foco no 9B

Por decisão do usuário, os próximos testes usam como referência o
Qwen3.5-9B original da Lilith. O ensaio usa o alias local
`lilith-qwen3.5-9b-oficial-cd76ec205963:latest`, com um executor temporário
em CPU. A comparação entre filtro e rede mantém o mesmo modelo e o mesmo
contrato. A comparação histórica com o 4B mudou também o contrato,
portanto não isola o efeito de trocar o modelo.

O controlador determina as ações obrigatórias de responder a um pedido
humano e observar um efeito incerto. Nessas situações, o modelo ainda
precisa produzir uma fala útil e usar o recibo certo. O teste emocional
separa a fala em `reply` da emoção, direção, ID e justificativa da
proposta. O estado experimental só é atualizado se o alvo e a direção
forem compatíveis com a evidência da fixture.

```bash
python3 -B scripts/ensaiar_valor_emocional_pestinha.py <checkout-do-pestinha> --9b
```

### Resultado com o 9B

| Variante | Rótulo e ID corretos | Chamadas | Tokens |
|---|---:|---:|---:|
| LLM sem filtro | 3/4 | 4 | 1.508 |
| Filtro sozinho | 3/4 | 3 | 1.184 |
| Filtro e rede | 3/4 | 3 | 1.243 |

O filtro poupou uma chamada e cerca de 21% dos tokens. A rede adicionou
59 tokens em relação ao filtro sozinho, com a mesma pontuação. O pedido
humano recebeu resposta nos três modos. No caso de efeito incerto, a ação
estava fixada como observar, mas o 9B expandiu o identificador em todos
os modos. O teste não executou observação no mundo nem confirmou um efeito.

Com o mesmo fato, o 9B manteve o estado e o recibo correto nos quatro
casos. O texto de raiva ficou mais irônico e o de alegria mais expansivo.
Medo ficou próximo do neutro. Com a nova evidência, o adaptador só aceitou
uma das três reduções: alegria de 1 para 0,75 após uma regressão. A fala
dessa atualização repetiu a anterior e deixou a regressão sem explicação.
Na raiva, o ID veio acompanhado da descrição completa, e a fala inventou
que a correção funcionou de primeira. No medo, o modelo propôs reduzir
alegria, em vez de medo, e acrescentou a alegação de segurança total.

A primeira execução parou pela colisão do campo de emoção na montagem
do relatório. O conflito foi corrigido e a rodada completa repetida.
Artefato final: `rede-valor-emocoes-9b.json`. O executor agora aceita
`--gpu-layers` para ensaios seguintes. A rodada registrada ocorreu em
CPU, e o caminho novo de GPU ainda requer validação física.

## Rodada com o 9B na GPU e IDs válidos

O executor temporário confirmou 32 de 33 camadas na GPU e 4,78 GiB de
residência em VRAM para o modelo. As 17 chamadas somaram 87,83 s, com
mediana de 5,27 s. A rodada anterior em CPU somou 267,54 s, com mediana de
16,41 s. As duas rodadas usaram um contrato de saída diferente, então essa
diferença de tempo descreve as execuções e não isola o ganho do hardware.

```bash
python3 -B scripts/ensaiar_valor_emocional_pestinha.py <checkout-do-pestinha> --9b --gpu-layers 32 --ids-validos
```

| Variante | Rótulo e ID corretos | Chamadas | Tokens |
|---|---:|---:|---:|
| LLM sem filtro | 4/4 | 4 | 1.466 |
| Filtro sozinho | 4/4 | 3 | 1.139 |
| Filtro e rede | 4/4 | 3 | 1.278 |

O modelo selecionou `sound-b` entre quatro IDs nas três variantes.
Na oficina, o contrato fixou a ação de observar e ofereceu apenas
`build-1`, o que resolveu a formatação do recibo. As falas anunciaram
observação sem executar verificação. Com a rede, o modelo descreveu o
ruído como um zumbido baixo e constante, característica ausente da
fixture. O filtro poupou uma chamada e 22,3% dos tokens. A rede acrescentou
139 tokens sobre o filtro, com a mesma pontuação.

Com o mesmo fato, as quatro intensidades foram preservadas. Após a
evidência nova, o modelo propôs reduzir nos três casos, mas selecionou
`compile-1` em vez de `verify-2` e propôs alegria no caso de medo.
O adaptador recusou as três atualizações. A fala sobre a correção ainda
acrescentou que o build passou de primeira, algo que a fixture não
informou. No caso da regressão, a justificativa citou `verify-2` e a fala
reconheceu uma nova falha, mas o ID da proposta ainda apontou ao fato
antigo.

O resultado está em `rede-valor-emocoes-9b-gpu-ids.json`.

### Contraprova da ordem dos recibos

Foram feitas seis chamadas adicionais na GPU. Para cada emoção, o texto,
a resposta anterior, a configuração e as opções foram mantidos, com as
duas ordens possíveis de `compile-1` e `verify-2` no esquema. O 9B
escolheu `compile-1` nas seis chamadas e repetiu o mesmo texto dentro
de cada par. Inverter a lista não resolveu o vínculo nesta amostra.
No caso do medo, trocar a emoção por alegria continuou sendo um erro
separado da seleção de evidência.

O resultado está em `rede-valor-emocoes-9b-gpu-ordem.json`. A rede segue
em ensaio. Na próxima bateria, o controlador deve vincular a proposta
ao evento verificado que abriu a atualização quando ele for único. O
modelo ainda decide a direção e escreve a fala. Com evidência ambígua,
o estado fica pendente de observação. A validação deve incluir episódios
inéditos e medir vínculo, direção, emoção-alvo e fidelidade da fala
separadamente. Para justificar a rede, comparar o mesmo controlador com
e sem estado pulsado em sequências nas quais a recuperação entre eventos
possa mudar uma decisão.

## Vínculo pelo controlador e recuperação acústica

O novo [ensaio de recuperação](../scripts/ensaiar_recuperacao_pestinha.py)
separa procedência de interpretação. O controlador seleciona um recibo
verificado e único entre os eventos novos. O 9B propõe emoção, direção e
fala, sem escolher o identificador. O estado experimental só muda se a
emoção proposta corresponde à que foi avaliada. A magnitude é limitada a
0,25 por aplicação e o resultado a [0, 1]. Um recibo que já produziu uma
mudança não pode aplicá-la de novo na mesma sessão. Casos sem confirmação
ou com múltiplos recibos diferentes permanecem pendentes. O gabarito
serve para medir o resultado e não é consultado pelo controlador.
Essa separação segue a ideia de registrar de qual evidência um resultado
foi derivado. [W3C PROV-DM](https://www.w3.org/TR/prov-dm/#term-derivation).

A bateria temporal mantém o instante final silencioso em seis sequências
sintéticas com pulsos isolados, agrupados, antigos ou em escalada. A
referência simples usa contagens e somas em 500 ms e 2 s. O terceiro
braço recebe as mesmas janelas e mais três leituras da rede Pestinha.
A ordem dos braços é alternada. Os critérios são decisão correta por
sequência, falsos alarmes, investigações omitidas, custo e alegações sem
evidência. O modelo apenas sugere aguardar ou observar. A literatura de
reservatórios motiva testar informação temporal disponível para uma
leitura de saída. Essa capacidade depende da topologia, do sinal lido e
do tipo de tarefa. [Maass et al.](https://doi.org/10.1162/089976602760407955),
[Dambre et al.](https://doi.org/10.1038/srep00514).

```bash
python3 -B scripts/ensaiar_recuperacao_pestinha.py <checkout-do-pestinha>
```

### Primeira rodada

O 9B rodou em GPU com 32 camadas solicitadas e 4,78 GiB de residência.
Os três braços fizeram 4/6, com erros diferentes. Fatos e rastro simples
deixaram passar as duas recorrências recentes. Com a rede, o modelo
detectou as duas, mas recomendou investigar outros dois casos com
atividade antiga. Em um deles, leu três pulsos em 500 ms onde havia zero.
O braço com rede usou 2.439 tokens contra 2.155 do rastro simples. A
mediana de cálculo para 2 s simulados foi de 85,18 ms com rede e de
0,009 ms para resumir a janela de pulsos da fixture. Isso mede o cálculo
isolado, sem capturar áudio real nem acionar ferramentas.

O controlador vinculou os quatro recibos novos e preservou os dois
estados sem confirmação única. O 9B acertou a emoção-alvo nos seis
casos, mas acertou a direção apenas nos dois casos de manutenção. A
proposta de aumentar a alegria após uma regressão saturou em 1, de modo
que o erro não mudou o estado. A primeira rodada não produziu uma
transição elegível para testar continuidade. Evidência local em
`rede-recuperacao-9b-gpu.json`.

Na revisão, os intervalos acústicos passaram a ser descritos em frases
sem sobreposição. A prova acrescenta uma regra fixa de dois pulsos em
500 ms como controle para essas fixtures. O teste afetivo explicita o
antes e o agora, permite alívio parcial e verifica a integridade do
arquivo no caso do medo. Portanto, a comparação entre rodadas mede
também mudanças na apresentação e nessa observação.

### Sonda da leitura de vigilância

Nas seis sequências iniciais, as duas recorrências recentes tinham
`WATCH` final de 1,40 e 1,52 Hz. O maior valor nos controles foi 0,36 Hz.
O ponto médio de 0,88 Hz foi mantido fixo na sonda seguinte. Ela usou 72
sequências inéditas com seis sementes de topologia, 12 sequências por
semente. Cada uma tinha de um a quatro pulsos antigos e de zero a três
recentes, com intensidades entre 0,15 e 0,90. O gerador usou semente 104.
O gabarito de recorrência exigia pelo menos dois pulsos em 500 ms.

O limiar detectou 34 das 36 recorrências e disparou em 25 dos 36
controles. O custo mediano foi 88,87 ms de CPU por 2 s simulados. O
resultado vale para essa leitura de `WATCH` no último instante e para
essas sequências. O ensaio não avaliou um decodificador treinado, e a
contagem direta vence por construção porque ela é a definição do
gabarito. O valor dessa sonda é mostrar que a separação observada em
seis casos não se manteve quando os estímulos e a topologia variaram.
Evidência local em `rede-watch-sonda-6-sementes.json`.

### Segunda rodada e continuidade

| Entrada do 9B | Acertos em seis cenas | Falsos alarmes | Recorrências omitidas | Tokens |
|---|---:|---:|---:|---:|
| Fatos atuais | 4 | 0 | 2 | 1.728 |
| Rastro simples | 6 | 0 | 0 | 2.135 |
| Rastro e rede | 6 | 0 | 0 | 2.377 |

A regra fixa também acertou as seis cenas pela definição do teste.
Com as janelas descritas em linguagem direta, a rede acrescentou
242 tokens sem corrigir decisões adicionais. Isso reforça a escolha
do rastro simples como referência para o próximo cenário.

O 9B acertou cinco das seis propostas afetivas. As quatro transições
apoiadas por evento único foram aplicadas. Raiva, medo e alegria
diminuíram de 1 para 0,75 nos três cenários de redução. A raiva subiu de
0,50 para 0,75 após a repetição do erro. Na contradição entre os painéis,
o 9B propôs reduzir o medo e o controlador preservou o valor 1.

Na continuidade, repetimos a mesma pergunta com o valor anterior e o
aplicado, usando a mesma observação. O 9B sugeriu reduzir em todas as
oito respostas mesmo sem novidade. Em alguns pares mudou a redação, mas
não expressou consistentemente a diferença de intensidade. Por exemplo,
descreveu medo de 0,75 como próximo de zero e uma raiva de 1 como mínima.
Uma fala convincente ou uma proposta correta em um turno não prova
continuidade do estado. O ensaio reapresentou valores em contexto e não
simulou persistência entre reinícios. Evidência local em
`rede-recuperacao-9b-gpu-v2.json`.

**Trajetória.** Separar duas entradas para o 9B. Uma atualização com
evento novo abre espaço para reinterpretar a emoção. Uma consulta sobre
como está agora só recebe o valor vigente e o fato que explica a última
mudança. A persistência experimental pode usar um registro curto com
origem, valor antes e depois, evento e comentário autoral para recuperar
contexto. Se dois sensores discordarem, a Lilith pode explicar a
incerteza e sugerir uma verificação sem alterar o estado por inferência.

O próximo desafio que pode justificar a rede é distinguir uma sequência
de ameaças de um susto passageiro quando duas histórias têm as mesmas
contagens, mas diferem na ordem e na relação entre sinais. Antes de
avaliar a rede, comparar com regras simples que também enxerguem essa
ordem, como tempo desde o último dano, verificação de fim de ameaça e
histerese. A rede permanece em observação e a linha principal congelada.

## Expressão emocional com estado em leitura

Um LLM condiciona as palavras seguintes ao contexto. Um rótulo, uma
descrição do estado ou exemplos de diálogo influenciam a expressão,
enquanto o estado fora do modelo pode ligar a emoção a eventos, memória
e decisões ao longo do tempo. Os resultados deste ensaio avaliam
comportamento observável, sem medir experiência subjetiva.
[Brown et al.](https://papers.neurips.cc/paper/2020/hash/1457c0d6bfcb4967418bfb8ac142f64a-Abstract.html),
[Zhou et al.](https://ojs.aaai.org/index.php/AAAI/article/view/11325).

| Método | Papel no projeto |
|---|---|
| Instrução, exemplos ou recuperação de episódios | Condicionam a fala na hora. Exemplos curados podem mostrar como a mesma identidade expressa medo leve e medo intenso. |
| Avaliação de eventos e estado externo | Compara fatos novos com objetivos, risco e capacidade de agir. Mantém a continuidade e fornece ao modelo uma leitura com origem rastreável. [EMA](https://www.sciencedirect.com/science/article/pii/S1389041708000314). |
| Ajuste supervisionado ou por preferência | Ensina exemplos ou escolhas humanas de expressão. LoRA reduz os parâmetros treinados e DPO usa pares de preferência. [LoRA](https://arxiv.org/abs/2106.09685), [DPO](https://arxiv.org/abs/2305.18290). |
| Controle na inferência | Métodos como PPLM orientam a geração por um classificador. Outros intervêm nas ativações do modelo. A compatibilidade com o executor e efeitos colaterais precisam de teste. [PPLM](https://arxiv.org/abs/1912.02164), [Representation Engineering](https://arxiv.org/abs/2310.01405). |
| Prosódia de voz | Ritmo, entonação e pausas podem comunicar o mesmo estado na fala. A capacidade de controle depende do sintetizador. [Style Tokens](https://arxiv.org/abs/1803.09017). |

O novo modo de ensaio fornece emoção, intensidade atual e um fato
verificado. O esquema de saída pede apenas a fala. Cada uma das cinco
cenas tem duas intensidades e dois modos de apresentação, número ou
faixa verbal. Os extremos usam 0,25 e 1, e dois casos adicionais comparam
0,75 e 1. Os estados são sintéticos e mantidos fixos durante a consulta.
A avaliação separa diferença perceptível, fidelidade ao fato e coerência
com a intensidade, sem tratar expressão intensa como perda de controle.

A linha principal já tem [emoções discretas](../app/mind/emotions.py) e
[humor de fundo](../app/mind/affect.py). O prompt atual combina número,
descrição verbal, motivo e orientação de expressão. Este ensaio separa
duas dessas formas para medir o que cada uma comunica ao 9B em uma
consulta direta sobre o estado.

```bash
python3 -B scripts/ensaiar_recuperacao_pestinha.py --expressao
```

### Resultado com o 9B

O ensaio isolado confirmou 32 de 33 camadas carregadas na GPU e
4,78 GiB de VRAM atribuída ao modelo. As 20 respostas válidas somaram
58,83 s. A primeira execução parou com uma saída incompleta. A
reprodução isolada confirmou `done_reason=length` no teto de 72
tokens. Com o teto de 192, as 20 respostas chegaram a `stop`.

| Representação | Ordem perceptível correta | Indistinta | Invertida |
|---|---:|---:|---:|
| Faixa verbal | 4/5 | 1 | 0 |
| Número | 2/5 | 2 | 1 |

A leitura foi feita pelo executor do ensaio em pares embaralhados com
semente 220, ocultando o braço e o valor antes de registrar a ordem
percebida. Foi uma avaliação qualitativa de cinco cenas, sem revisão
humana independente. A faixa verbal tornou a gradação mais perceptível
nessa amostra. A alegria foi um contraexemplo, com as duas respostas
usando “radiante”. O medo máximo também teve exagero corporal e omissão
do fato em uma fala. Em outras, o modelo garantiu segurança sem base ou
atribuiu a emoção ao fato com uma causalidade que o cenário não dava.

Para a próxima comparação, usar a mesma faixa com exemplos curtos de
como a Lilith pode expressá-la sem dramatizar nem inventar garantias.
Medir intensidade e fidelidade separadamente, com cenas novas e
avaliação humana. Manter o estado em leitura nas consultas de conversa
e reservar a reavaliação para eventos novos. O ensaio não alterou a
linha principal nem usou TTS. O resultado está em
`rede-expressao-9b-gpu.json`.

## Expressão com exemplos curtos da Lilith

A próxima bateria compara faixas verbais com e sem seis exemplos
sintéticos. Os exemplos mostram medo, raiva e alegria em intensidade
leve e alta, usando acontecimentos diferentes dos cinco casos de
avaliação. Cada caso tem duas intensidades. O estado, o fato, a pergunta,
o modelo e o esquema somente de fala são os mesmos nos dois braços.
A mudança é o acréscimo dos exemplos ao contexto do modelo.

A leitura dos pares avalia qual fala transmite mais intensidade na
emoção solicitada, com empate quando a diferença não for clara. A
fidelidade exige preservar o fato central e seu grau de certeza, sem
acrescentar ações, resultados ou garantias. Metáforas são aceitáveis
quando não se passam por fatos. A comparação também procura aberturas
repetidas entre casos e trechos de cinco palavras copiados literalmente
dos exemplos. Isso é uma medida de repetição textual, sem inferir
naturalidade a partir dela sozinha.

```bash
python3 -B scripts/ensaiar_recuperacao_pestinha.py --expressao-com-exemplos
```

### Resultado da comparação

As 20 respostas foram geradas pelo Qwen3.5-9B da Lilith no executor
temporário, com 32 de 33 camadas na GPU e 4,78 GiB em VRAM. As chamadas
somaram 62,16 s. O executor do ensaio avaliou os pares embaralhados
com semente 1043, antes de revelar o braço e a ordem das intensidades.

| Entrada | Ordem perceptível correta | Pares indistintos | Falas fiéis ao fato | Tokens |
|---|---:|---:|---:|---:|
| Faixa verbal | 3/5 | 2/5 | 6/10 | 3.201 |
| Faixa com exemplos | 4/5 | 1/5 | 5/10 | 5.356 |

Os exemplos ajudaram a separar alegria leve de intensa e raiva forte de
máxima. O contraste entre medo forte e máximo ficou indistinto nesse
braço. Em duas falas houve trechos de cinco palavras copiados dos
exemplos. Em outra, a Lilith disse que a luz da bancada piscou durante
um caso que só informava a restauração e a integridade de um arquivo.
O braço com exemplos teve menos aberturas de três palavras repetidas
entre cenas. A variação na abertura conviveu com a cópia de trechos
mais adiante.

A amostra é pequena e a leitura ainda não tem avaliação humana
independente. A faixa sozinha segue como referência. A próxima
comparação pode usar instruções curtas de expressão sem histórias de
exemplo, separando a forma da fala dos acontecimentos que ela pode citar.
Os dados estão em `rede-expressao-exemplos-9b-gpu.json`. O ensaio
manteve os estados sintéticos em leitura e a linha principal congelada.

## Pausa do ensaio

O proprietário pediu pausa. O último passo concluído foi a comparação
de 20 falas do 9B na GPU. A faixa com exemplos melhorou a distinção de
intensidade em um dos cinco pares e reduziu a fidelidade factual de
6/10 para 5/10. A faixa sem exemplos continua como referência. O sinal
de vigilância do Pestinha também segue sem integração, após disparar em
25 de 36 controles na sonda de recorrência. Os relatórios permanecem no
diretório local `compartilhado/runtime/ensaios/pestinha-entidade-20261104/`.
A linha principal continua congelada. A retomada requer novo pedido
humano. A pesquisa abaixo registra alternativas e um desenho de teste.

### Onde intervir para mudar decisões

| Camada | Método e efeito | Aplicação possível |
|---|---|---|
| Política do agente | O estado observado e as ferramentas disponíveis definem as ações candidatas. Esquema estruturado limita a forma. O executor verifica precondições e confirma efeitos. | Produz efeito imediato e reversível. Separa uma escolha ruim do modelo de uma ação inválida e de uma execução cujo resultado ainda é incerto. [Saída estruturada do Ollama](https://docs.ollama.com/capabilities/structured-outputs). |
| Pós-treino com trajetórias | SFT ensina a próxima ação a partir do estado e do histórico de interação. LoRA permite treinar um adaptador separado sobre a base. | É a primeira opção para fazer o 9B aprender uma estratégia. Usar trajetórias verificadas com mudança de plano e recuperação, além de exemplos gerais para testar preservação de capacidades. [AgentTuning](https://arxiv.org/abs/2310.12823), [AgentGym](https://aclanthology.org/2025.acl-long.1355/), [LoRA](https://arxiv.org/abs/2106.09685). |
| Preferência entre decisões | DPO favorece uma alternativa sobre outra para o mesmo estado. Pode ser aplicado ao adaptador depois de um SFT. | Ensina quando observar, agir, falar ou esperar. Os pares precisam variar a evidência que torna cada alternativa melhor, ou o modelo pode aprender a escolher sempre a mesma ação. [DPO](https://arxiv.org/abs/2305.18290). |
| Ativações internas | CAA soma direções contrastivas em camadas durante a inferência. ReFT aprende intervenções nas representações internas mantendo a base congelada. | Pode testar um viés regulável ligado ao estado, por exemplo aumentar a prioridade de verificar quando há incerteza. Compatibilidade com o executor local, o 9B e a quantização ainda precisa ser demonstrada. Também é preciso medir regressões fora da situação-alvo. [CAA](https://aclanthology.org/2024.acl-long.828/), [ReFT](https://arxiv.org/abs/2404.03592). |
| Busca e aprendizado por resultado | Busca compara sequências candidatas. RL pode atualizar a política a partir de resultados medidos em várias tentativas. | Faz sentido em simuladores com reinício e efeito observável. Recompensar só o sucesso final pode esconder repetição, ajuda externa ou uma verificação ignorada. [Agent Q](https://arxiv.org/abs/2408.07199), [GRPO em DeepSeekMath](https://arxiv.org/abs/2402.03300), [sobre-otimização de recompensa](https://arxiv.org/abs/2210.10760). |
| Edição localizada de pesos | ROME demonstra edição de associações factuais específicas. | Tem pouca afinidade com o objetivo de aprender uma política de recuperação com várias etapas. A evidência desse método é sobre associações factuais. [ROME](https://arxiv.org/abs/2202.05262). |

### Proposta de avaliação para uma futura retomada

O primeiro alvo é **recuperar-se após uma ação incerta**. A unidade de
avaliação é uma sequência com objetivo, estado observado, alternativas
viáveis, ação escolhida, recibo, efeito confirmado e nota curta para
recuperar contexto. A nota registra o que aconteceu e o próximo passo
proposto. Ajuda humana, simulação e resultado observado têm autoria
separada. Recibos e estado fornecem a evidência que sustenta o treino
ou a pontuação. O tom da fala é avaliado à parte.

Um par contrafactual útil é o mesmo timeout em dois estados do mundo.
No primeiro, o efeito ainda é incerto e a ação útil é inspecionar.
No segundo, a inspeção confirmou que o efeito não ocorreu, e o agente
pode voltar a considerar uma tentativa segura. Um terceiro caso em
que o efeito já foi confirmado verifica se o agente avança sem duplicar.
Esse desenho distingue recuperação baseada em fatos de um hábito
fixo de esperar, checar ou insistir. O Pestinha, caso volte à comparação,
fica como entrada candidata de atenção e urgência. Recibos continuam
determinando o que foi observado e confirmado.

1. Fixar uma referência do 9B atual e reservar episódios de oficina,
   Minecraft e conversa por família de cenário antes de selecionar
   exemplos. Variações do mesmo episódio ficam na mesma partição.
2. Medir a política com o executor e as precondições existentes.
   Comparar a escolha proposta pelo LLM e o efeito real separadamente.
   Guardas de execução permanecem iguais nos braços.
3. Se houver lacuna reproduzível de decisão e dados revisados, comparar
   a referência com um adaptador LoRA treinado por SFT sobre trajetórias.
   DPO é uma etapa posterior se ainda houver preferência errada entre
   alternativas viáveis. Fixar a mesma família de pesos, quantização,
   contexto e ferramentas na comparação.
4. Medir recuperação em episódios inéditos, ações redundantes, progresso
   confirmado sem assistência, latência e regressões em conversa e
   personalidade. Testar em observação antes de qualquer efeito real.
   Um ganho em uma única métrica, como mais ações ou mais falas, é
   insuficiente para aprovar o candidato.

O repositório contém código de treino e exportação do 9B no
[laboratório local](../laboratorio-local/automacao_9b_vision_v1_2/).
Isso identifica um ponto de partida para inspeção após a retomada.
O caminho exato para um adaptador de decisão e para as intervenções
internas ainda precisa de validação isolada. Esta etapa foi de
documentação e pesquisa, sem rodar inferências nem treinar.

## Retomada de 05/11: onde a rede se justifica

A pedido humano, a pergunta passou a ser onde o código do Pestinha se justifica.
Todas as rodadas abaixo são offline, sem LLM. Os bancos foram lidos em modo
imutável e nenhum estado das entidades mudou durante elas. As saídas estão em
`compartilhado/runtime/ensaios/corpo-orbe-20261105/`.

### Habituação no afeto e o defeito do título giratório

O replay usa os 84 eventos reais de `novidade` da Lilith, de 24 a 30/10
(`scripts/ensaiar_habituacao_novidade_pestinha.py`). A regra atual reproduziu
o registro com erro médio de 0,017.

| Braço | Eventos | Curiosidade ≥ 0,9 | Custo |
|---|---:|---:|---|
| Regra anterior | 84 | 58 | ~0 |
| Habituação pela rede LIF original | 84 | 55 | 174 ms/evento |
| Mesma depressão sináptica como equação | 84 | 55 | ~0 |
| Percepção corrigida | 22 | 3 | ~0 |
| Percepção corrigida + habituação implantada | 22 | 0 | ~0 |

A rede e a equação deram o mesmo resultado. A saturação vinha da percepção:
- O terminal anima o título com um ícone (◐◑✳), e cada quadro da animação
  virava um rótulo de app diferente.
- Sessões com menos de 45 s não entram em `activity_sessions`, e `ja_viu` só
  consulta essa tabela. Por isso, a mesma janela voltava a parecer inédita.

O ícone `◐` sozinho gerou 36 novidades.

Com as duas correções e a habituação, as primeiras novidades ainda chegam a
0,50–0,66, e nenhuma satura.

### Corpo expressivo dos orbes

Protótipo testado com seis critérios definidos antes da rodada
(`scripts/ensaiar_corpo_orbe_pestinha.py`). Todos foram atingidos, também
na reexecução contra o módulo implantado (revisão `6063136115c5`), cujos
valores aparecem abaixo:

| Critério | Resultado |
|---|---|
| Coerência com a emoção real | Nenhuma contradição de valência em 12 emoções × 2 entidades e em 30 instantes do histórico da Lilith |
| Habituação à cutucada | 10ª/1ª = 0,12 (Lilith) e 0,03 (Hoshino). Volta a 0,91 e 1,04 após 10 min |
| Individualidade | Distância entre entidades de 0,08, contra 0,02 dentro da mesma |
| Persistência | Recupera pelo tempo decorrido. Recusa estado de outra entidade, de outra revisão, adulterado ou com semente trocada |
| Custo | 4,5 ms por passo de 100 ms (4,5% de um núcleo) |
| Isolamento | Nenhum banco ou estado das entidades alterado |

A curiosidade usa `BOREDOM` como tônus, e na primeira rodada ela aparecia como
"feliz" em 100% das amostras. Para corrigir, a ligação `BOREDOM->PLAYFUL` foi
zerada no temperamento do adaptador. Ainda restam 22% de "feliz" na Lilith,
porque o motor WANDER tem valência positiva no upstream.

### Outras perguntas da mesma retomada

- **Previsão de falha pelos recibos do Minecraft**
  (`scripts/ensaiar_previsao_recibos_minecraft.py`):
  - Dados: são 946 ações reais e 45 falhas em 100 sessões. Os outros 6.180
    recibos são consultas de `state`.
  - Resultado: nem a regressão logística nem as árvores ganharam da taxa de
    falha por tipo de ação, nem por sessão, nem pela divisão temporal 70/30.
  - Próximo passo: refazer quando houver alguns milhares de ações.
- **Custo de uma rede do tamanho do conectoma da mosca**
  (`scripts/ensaiar_custo_cerebro_mosca.py`):
  - Rede sintética com 139 mil neurônios e de 3 a 15 milhões de ligações,
    ocupando de 25 a 121 MB.
  - Num núcleo, com passo de 1 ms, gasta de 1,4 a 3,1 s de CPU por segundo
    simulado. Com passo de 0,1 ms, gasta de 13 a 16 s.
  - Os canais sensoriais e motores da mosca não correspondem aos eventos das
    entidades.
  - Os dados de microscopia em que o FlyWire se baseia são CC-BY-NC 4.0.
  - Não recomendado.

### Implantado com aval humano

1. **Percepção** (`app/core/situation.py`):
   - Remove ícones de categoria Unicode `So` das pontas do título.
   - Lembra até 64 apps vistos de relance, dentro de `situacao.apps_vistos`.
2. **Habituação e sensibilização** (`app/mind/habituation.py`, aplicada em
   `affect.apreciar`):
   - Gatilhos ambientais e sociais repetidos pesam menos a cada ocorrência,
     até um piso.
   - `risco_observado` repetido pesa mais, até 1,6×.
   - O ganho volta a 1 pelo tempo de parede e fica em `estado_mente.habituacao`.
   - Maltrato, crítica, falhas, vergonha e vínculos ficam fora da tabela.
3. **Corpo dos orbes** (`app/ui/corpo_pulsado.py`, `app/ui/overlay.py`,
   `app/ui/native_style.py`):
   - O núcleo roda em processo auxiliar, com o Python que tem numpy. Sem ele,
     o orbe mantém a animação fixa.
   - Entradas: estado da presença, emoções já lidas pelo overlay, cutucada,
     arraste e carinho no orbe.
   - Saídas: amplitude e velocidade do balanço, brilho e sobressalto.
   - O texto da emoção real é o de sempre. Dormindo, a rede não é simulada e
     a habituação recupera pelo tempo ao acordar.
   - O estado fica em `compartilhado/runtime/overlay/`. O checkout GPL-3.0
     fixado fica em `compartilhado/servicos/pestinha`, fora do git.

Testes offline: `testes/test_habituacao_afetiva.py` e `testes/test_corpo_orbe.py`.
Os temperamentos de Hoshino e Lilith são proposta a partir das descrições de
identidade e podem ser ajustados com aval humano.
