Registro da contribuição Claude Opus5.5 à coordenação de27/10.
Somente leitura; recomendações não equivalem a implementação ou aprovação do ensaio.

# Próxima melhoria cognitiva do ciclo Minecraft (somente leitura, nada foi editado nem executado)

## Diagnóstico: falha de interface ou capacidade do modelo

Li o código e encontrei três falhas de interface que confirmam sua hipótese e a ampliam. Elas aparecem antes de qualquer limite do 9B.

1. **Percepção só do produto final.** Em `app/main.py:2886-2888`, `items` recebe apenas os itens de `fabricar` e `ter_no_inventario`, ou seja, `wooden_pickaxe`. O `craftAnalysis` (`bridge.js:343-357`) informa `oak_planks: precisa 3, tem 2` e `pode_agora:false`. Ele não analisa o ingrediente que falta. Para chegar à transformação possível, o modelo precisa cruzar dois campos (`percepcao` e `receitas_consultadas` compacto) e encadear dois níveis. Para um 9B, isso é um ponto de falha previsível.
2. **O próprio prompt confunde madeira com tábuas.** Em `main.py:2899` está escrito "Para obter madeira [...] use minecraft_coletar". Para quem já tem troncos e precisa de tábuas, isso empurra para a coleta. A crença errada do plano ("quebrar troncos produz tábuas") encontra apoio no texto do condutor.
3. **O plano errado se autorreforça.** `plan_view` (`main.py:2859-2868`) só avisa quando `falta_para_concluir` muda. Coletar troncos não muda o que falta, então o plano volta intacto em `meu_plano` a cada decisão, sem aviso.

**Capacidade do modelo:** só dá para culpar o 9B se ele continuar coletando depois que a transformação possível estiver explícita, o texto do prompt estiver neutro e houver um sinal de estagnação. Hoje ainda não dá para separar as duas causas.

## Prioridades (no máximo 3)

1. **Mostrar também as transformações dos ingredientes que faltam.** Seriam alternativas disponíveis, não uma sequência a seguir.
2. **Descrever a ferramenta de forma neutra e avisar quando não há progresso.** Trocar a frase de `:2899` por algo como "minecraft_coletar quebra um bloco do mundo e entrega o que ele solta; transformar itens do inventário é fabricação". Isso descreve a mecânica, não dá receita. No `plan_view`, avisar quando as últimas N ações com recibo não reduziram `falta_para_concluir`. Esse sinal é genérico e não diz o que fazer.
3. **Orientação recente do interlocutor na visão compacta.** Fica para depois (ver o fim).

## Recomendação mínima para esta rodada

Fazer a prioridade 1 só em `main.py`, dentro de `ask`, sem tocar em `bridge.js`, que é área do Codex por causa do `lineOfSight`. Depois da percepção atual:

- juntar os nomes de ingredientes com `tem < precisa` das `variantes` já devolvidas;
- refazer a leitura de `minecraft_estado` com `{'itens': [*itens_que_faltam, *ingredientes_que_faltam]}`. Isso cabe no limite de 6 nomes de `perception`.

O `craftAnalysis` existente passa a devolver também `oak_planks` com o `pode_agora` real calculado pelo `recipesAll` do servidor. No prompt, uma única linha descritiva: "percepcao.receitas inclui também os ingredientes que faltam". Nada de ordem nem de "faça X".

Junto, a troca de texto da prioridade 2 (só a frase de `:2899`). O sinal de estagnação fica para uma segunda passada, se o teste abaixo pedir.

Antes de editar código carregado, conferir que o ciclo está ocioso, sem jobs nem leases.

**Teste offline (RED→GREEN):** um `read` falso que devolve a percepção da picareta com `oak_planks 2/3`. O teste confirma que a segunda leitura pede `oak_planks` e que a visão contém a análise dele. Confirma também que nenhum texto de ordem ou ação sugerida entra no prompt.

**Teste que refutaria a hipótese, no mundo real:** retomar `codex-coord2` com o mesmo inventário (4–5 `oak_log`, 2 `oak_planks`, 4 `stick`, bancada perto). Se, com `oak_planks pode_agora:true` visível e o texto neutro, o 9B escolher coletar troncos em 3 decisões seguidas, a hipótese de interface cai para este caso. A causa passa a ser a âncora do plano ou a capacidade de encadear, e o próximo passo é o aviso de estagnação. Só contam fabricação e picareta com recibo real. Fala otimista ou o teste offline não valem como resultado.

## Deixar para depois

- **Orientação do interlocutor.** Proposta: um campo `interlocutor_recente` com no máximo 3 mensagens `user` de `_historico_da_conversa(chave_conversa)` (`main.py:585`), posteriores ao início da tarefa, com cerca de 300 caracteres cada. Cada uma leva a autoria registrada: humano, RP do condutor ou intervenção. A identidade e o contexto completo não entram, porque já estão no ciclo principal. Antes de implementar, falta decidir como uma correção humana se distingue de uma ordem do condutor, e se as mensagens ficam visíveis só até a entidade reescrever o plano.
- Habilidades aprendidas dos próprios recibos, orçamento de memória e identidade, e mais profundidade na análise de receitas (hoje é um nível só).
- Visão em primeira pessoa no Minecraft. Ela exige outra fonte de imagem; o screenshot do jogador humano não serve.
