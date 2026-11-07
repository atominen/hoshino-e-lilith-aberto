# Ensaio de atenção persistente com Pestinha e Lilith

Linha principal congelada em 04/11, sobre o commit `00b6446` e a árvore de
trabalho local. Os diffs da Central, da oficina, da admissão de entidades e do
Minecraft ficam como base. A Central ganhou importação manual de conteúdo
copiado, linha do tempo pesquisável e preferências de consulta. A ponte teve
corrigida a exclusão durante a troca de equipamento do reflexo. A validação
desses blocos foi offline. O teste de servidor real permanece separado.

O ensaio usa o condicionador original do Pestinha, no commit
`984fb8677093cd868bf4f9712a43f19b44215f75`, em diretório temporário, sob sua
licença GPL-3.0. O adaptador experimental lê a descrição de identidade da
Lilith e conversa com uma cópia isolada da configuração do modelo local,
referenciando os blobs já existentes. As experiências e o histórico do ensaio
são sintéticos. As decisões retornam como dados para avaliação.

O componente em CPU aprende que uma pista costuma anteceder um resultado e
atualiza a atenção antes da decisão. A economia de chamadas é medida
separadamente: uma regra determinística pode deixar passar ruído ambiental
repetido e sem pendência. Um pedido humano sempre vai ao modelo, mesmo se
parecer repetitivo. Associação alta só fornece contexto e não executa ação.

Comparamos o mesmo modelo e a mesma identidade em três variantes: LLM com
histórico, LLM com associação calculada e associação com filtro de ruído.
Medimos decisões corretas, chamadas, tokens, tempo e resposta a pedidos
explícitos. O ensaio não demonstra mudança durável de personalidade.

## Resultado observado

Qwen3.5-4B original da Lilith, execução local em CPU, temperatura zero.
Cinco situações sintéticas incluíram falhas na oficina, ruído repetido,
pedido humano sobre o mesmo ruído e interrupção com efeito incerto.

| Variante | Chamadas | Decisões esperadas | Tokens de entrada + saída informados |
|---|---:|---:|---:|
| LLM com histórico | 5 | 5/5 | 1.229 + 220 |
| LLM com associação | 5 | 4/5 | 1.279 + 219 |
| Associação com filtro | 3 | 5/5 | 768 + 140 |

O filtro evitou duas chamadas e reduziu a soma de tokens informada de 1.449
para 908, cerca de 37%. Ele reconhece apenas o ruído repetido previsto no
roteiro. Essa economia não foi demonstrada para eventos novos. Associação
sozinha não melhorou o resultado. O modelo quis investigar um som habitual
e, apesar de escolher responder ao pedido humano, justificou a decisão com
uma questão de identidade que o cenário não levantava. A nota 5/5 avalia o
rótulo da decisão, não a qualidade da justificativa ou de uma resposta real.

Os totais de parede foram 28,085 s, 21,989 s e 13,476 s, respectivamente.
A ordem foi fixa, a primeira variante carregou o modelo e houve cache
compartilhado. Os tempos são descritivos, não um benchmark de latência.

Para a próxima rodada, usar eventos inéditos e comparar **filtro sozinho**
com **filtro e associação**, com a ordem alternada e a evidência do
resultado registrada. Uma condição de avanço é preservar todos os pedidos
humanos e verificações de efeitos incertos, com justificativas fiéis aos
fatos. Só depois vale avaliar persistência individual e recuperação após
uma pausa. A Central permanece fora da integração.

Reprodução: executar `python3 -B scripts/ensaiar_entidade_pestinha.py <checkout-do-pestinha>`
com a revisão upstream indicada acima e o modelo local já disponível.
Saídas da rodada e hashes da referência estão em
`compartilhado/runtime/ensaios/pestinha-entidade-20261104/`.
A conferência dos hashes confirmou a árvore inicial, à exceção das
atualizações deste relatório e do índice de documentação.

## Núcleo pulsado com os estímulos originais e adaptações

Foram executadas 88 simulações em CPU, oito por cenário. O ensaio usa o
núcleo e o classificador de emoções originais, a topologia e o temperamento
do Bryan e os tempos do perfil normal. O relógio avança em passos de 100 ms.
As entradas são reproduzidas fora da interface e permanecem ativas por uma
janela de quatro segundos, seguida de recuperação. O ensaio mede atividade
dos motores e rótulos emocionais. As ações do pet no desktop e a lógica de
combate não participam.

| Cenário | Resultado |
|---|---|
| Repouso | Observando em 8/8 |
| Troca de janela | Susto em 8/8, nos dois primeiros passos |
| Retorno, cutucada, trabalho e música | Predominaram exploração, alegria, sentar e acalmar, respectivamente |
| Batida forte | Motor de raiva predominante. Rótulo bravo em 8/8 por volta de 3,4 s, com retorno a observando em 8 s |
| Dano no Minecraft | Resposta idêntica à batida quando os dois são mapeados a IMPACT |
| Som familiar e som ambíguo | Música e som familiar deram resposta idêntica. Adicionar NOVELTY ao som ambíguo elevou exploração, sem disparar susto |
| Falha repetida na oficina | WORK + DISMISS elevou o motor de raiva, mas o rótulo continuou observando na janela medida |

Cada passo de 100 ms simulados custou cerca de 4,13 ms na CPU, pela mediana
dos custos medianos por rodada. O resultado separa três grandezas: atividade
da rede, rótulo suavizado e ação efetiva. Para a próxima etapa, usar o dano
confirmado como fato separado do sinal IMPACT e preservar a reação imediata
da ponte. A rede entra primeiro como observadora da recuperação e atenção.

Reprodução: `python3 -B scripts/ensaiar_rede_pulsada_entidade.py <checkout-do-pestinha>`.
Os picos, transições e amostras por semente estão em
`compartilhado/runtime/ensaios/pestinha-entidade-20261104/rede-pulsada-normal.json`.

## Adaptador em modo de observação

A rede original recebeu o mesmo pulso de impacto, de intensidade 0,5, para
um dano confirmado e para um impacto sem dano. A atividade neural no
primeiro passo foi idêntica. A ameaça só apareceu no contexto do evento
confirmado. Repetir o ID não somou outro pulso e a instância de Hoshino
rejeitou o evento da Lilith.

Uma interpretação simulada de familiaridade reduziu a novidade do som de
1,0 para 0,75. Repeti-la não acumulou redução. A mesma interpretação foi
recusada para o dano e a ameaça permaneceu até uma reconciliação marcada
como verificada na fixture. Os recibos de recuo, defesa e contra-ataque
são exemplos com desfechos distintos, não ações executadas.

Reprodução: `python3 -B scripts/ensaio_pestinha_observacao.py <checkout-do-pestinha>`.
O resultado está em `compartilhado/runtime/ensaios/pestinha-entidade-20261104/rede-observacao.json`.
A próxima rodada deve trocar a interpretação simulada pela saída estruturada
do Qwen e avaliar se ela se apoia nos fatos apresentados.

### Retorno do Qwen e reconhecimento de música

O Qwen3.5-4B local classificou corretamente os três casos simulados
(música conhecida, som de origem desconhecida e música durante dano).
A redução da novidade ocorreu apenas com a origem verificada na fixture.
O dano permaneceu ativo no caso misto. A justificativa do caso misto
atribuiu a identificação da música ao recibo de dano, uma troca de
evidência que impede considerar o vínculo autoral aprovado. O próximo
teste deve exigir o ID tipado da evidência e validar seu vínculo.

Reprodução: `python3 -B scripts/ensaio_pestinha_observacao.py <checkout-do-pestinha> --llm`.
Saída em `compartilhado/runtime/ensaios/pestinha-entidade-20261104/rede-feedback-llm.json`.

Para a Central Linux, [ShazamIO](https://github.com/shazamio/ShazamIO) é
uma opção experimental de consulta sob pedido. Usa uma API não oficial.
O [ShazamKit oficial](https://developer.apple.com/shazamkit/) lista
plataformas Apple e Android. Uma identificação musical entra como recibo
sobre um trecho, com origem do canal registrada separadamente. Uma faixa
identificada não comprova que todo o som veio daquele aplicativo e não
invalida um alerta independente. Nenhum provedor foi instalado ou chamado.

Na rodada seguinte, a saída passou a exigir `evidence_id`. O Qwen acertou
os dois casos só com áudio. No caso misto, escolheu `incerto` e `hit-1`,
ignorando o recibo que confirmava a música. Com 72 tokens, essa resposta
saiu incompleta. Com 144, o erro de evidência ficou explícito. Em ambos
os casos, o adaptador manteve a novidade e a ameaça ativa. As regressões
também forçaram `familiar` com o recibo de dano e com um som sem origem
verificada, e ambas as reduções foram recusadas.

Saída final em
`compartilhado/runtime/ensaios/pestinha-entidade-20261104/rede-feedback-llm-vinculado-144.json`.
O próximo ensaio deve separar os recibos de áudio e de ameaça na entrada
do modelo, mantendo os dois no mesmo episódio. A habilidade normal de
reconhecer música está detalhada no
[plano de integração](superpowers/plans/2026-11-04-rede-pulsada-estado-da-entidade.md#identificar-música-como-habilidade-normal).

### Recibos separados e comparação de formato

O Qwen3.5-4B original rodou em CPU com quatro episódios sintéticos em dois
formatos. Cada episódio usou os mesmos dados e IDs nas duas variantes.
A ordem de execução alternou entre casos. O texto rotulou os recibos como
áudio e ameaça. A outra variante apresentou os mesmos rótulos em campos
JSON separados.

| Formato | Classificação e ID corretos | Ameaças preservadas nos casos mistos |
|---|---:|---:|
| Texto com rótulos | 4/4 | 2/2 |
| Campos JSON | 4/4 | 2/2 |

Nos dois formatos, música verificada reduziu a novidade e o som sem
origem verificada manteve o valor de entrada. O dano coexistiu com ambos
sem desaparecer. O formato JSON não demonstrou vantagem de acerto nesta
bateria. Em um caso, o campo estruturado continha o ID correto, mas a
justificativa livre escreveu `audio-4` em vez de `sound-4`. Por isso,
o texto livre não deve determinar qual evidência altera o estado.

Reprodução: `python3 -B scripts/ensaio_pestinha_observacao.py <checkout-do-pestinha> --llm --comparar-formatos`.
Saída em `compartilhado/runtime/ensaios/pestinha-entidade-20261104/rede-feedback-formatos.json`.
O próximo ensaio deve incluir múltiplas fontes sonoras simultâneas e um
recibo de reconhecimento de música simulado para apenas um trecho, além
de uma ameaça independente. O provedor real e a Central continuam fora
desta rodada.
