# Banco de treinamento v6 — relatório

Gerado por `scripts/montar_banco_v6.py`. Status: **corpus do laboratório desde 08/11 (pedido humano); candidatos só entram em uso depois do teste humano.**

Tokens: contados com o tokenizador do Qwen3.5; treino atual aceita até 256.

Exemplos com ferramenta: modelo de chat real do Qwen3.5, até 768 fichas, com as definições reais das ferramentas usadas mais duas de distração.

| Entidade | Exemplos | Texto (treino) | Com ferramenta | Ferramenta (treino) | Pares de preferência | Holdout |
|---|---|---|---|---|---|---|
| hoshino | 632 | 514 | 91 | 89 | 23 | 32 |
| lilith | 632 | 512 | 91 | 89 | 23 | 32 |
| alistair | 445 | 383 | 21 | 20 | 0 | 17 |

## Por aspecto

| Aspecto | hoshino | lilith | alistair | v6 novos |
|---|---|---|---|---|
| identidade | 53 | 53 | 27 | 32 |
| costumes | 99 | 99 | 200 | 0 |
| emocional | 35 | 35 | 0 | 8 |
| convivencia | 21 | 21 | 0 | 6 |
| opiniao | 85 | 85 | 58 | 0 |
| iniciativa | 74 | 74 | 64 | 7 |
| seguranca | 20 | 20 | 9 | 6 |
| fatos | 38 | 38 | 30 | 53 |
| perceber | 31 | 31 | 12 | 40 |
| consertar | 25 | 25 | 10 | 37 |
| perguntar | 18 | 18 | 4 | 40 |
| memoria_uso | 25 | 25 | 9 | 26 |
| ferramentas | 45 | 45 | 12 | 102 |
| voz_falada | 9 | 9 | 1 | 19 |
| conhecimento | 25 | 25 | 2 | 52 |
| dialogo | 14 | 14 | 7 | 9 |
| preferencias | 15 | 15 | 0 | 30 |

## Avisos (v5, para revisão humana)

O v5 tem respostas que anunciam uma conferência sem ferramenta. Em 07/11 isso apareceu como erro real
("Vou verificar." e parar). Sugestão: reescrever estas no v6 ou tirá-las do treino.

- anuncia conferência sem ferramenta: v5/alistair.txt:146 [alistair/organizacao]: Não encontro confirmação desse lembrete. Prefiro marcar de novo com vo
- anuncia conferência sem ferramenta: v5/alistair.txt:343 [alistair/dialogo]: Então não está confirmado. Antes de criar outro, vou conferir se já ex
- anuncia conferência sem ferramenta: v5/alistair_2.txt:17 [alistair/despertar]: Casa em silêncio. Mantenho os recados em ordem e deixo uma nota de que
- anuncia conferência sem ferramenta: v5/alistair_2.txt:66 [alistair/recados]: Vou conferir a caixa. Até lá, não afirmo nem que sim nem que não.
- anuncia conferência sem ferramenta: v5/alistair_2.txt:102 [alistair/recados]: Preciso consultar o registro. Guardado, entregue e lido são estados di
- anuncia conferência sem ferramenta: v5/alistair_2.txt:179 [alistair/vontade_propria]: Agora não. Estou conferindo os recados da manhã. Em dez minutos começo
- anuncia conferência sem ferramenta: v5/alistair_2.txt:185 [alistair/vontade_propria]: Porque é minha função e eu tinha tempo livre. Não mexi em nada, só con
- anuncia conferência sem ferramenta: v5/alistair_3.txt:208 [alistair/incerteza]: Não tenho o resultado. Vou consultar o registro do backup antes de res
- anuncia conferência sem ferramenta: v5/alistair_4.txt:36 [alistair/recados]: Vou conferir a caixa. Se houver, entrego agora.
- anuncia conferência sem ferramenta: v5/alistair_4.txt:42 [alistair/recados]: Porque a destinatária ainda não acordou, ou ainda não abriu. Vou confe
- anuncia conferência sem ferramenta: v5/alistair_4.txt:63 [alistair/recados]: Se entreguei, é um erro sério. Vou conferir o registro de entrega agor
- anuncia conferência sem ferramenta: v5/alistair_4.txt:281 [alistair/incerteza]: Vou conferir se ainda está na fila. Pedido de apagar não é prova de ap
- anuncia conferência sem ferramenta: v5/alistair_5.txt:36 [alistair/recados]: Se eu não avisei, falhei. Vou conferir quando ele chegou e por que não
- anuncia conferência sem ferramenta: v5/alistair_5.txt:77 [alistair/vontade_propria]: Estava conferindo a caixa. Agora estou à disposição.
- anuncia conferência sem ferramenta: v5/alistair_5.txt:154 [alistair/incerteza]: Vou conferir os registros de entrega. Se houver duas entregas, aviso o
- anuncia conferência sem ferramenta: v5/dialogos_2.txt:5 [hoshino/despertar]: Ninguém e nada. Vou mandar no chat: "Oi, acordei agora. Tem alguém aí?
- anuncia conferência sem ferramenta: v5/dialogos_2.txt:12 [hoshino/despertar]: Alguém estava escrevendo alguma coisa. Vou olhar o título da janela pr
- anuncia conferência sem ferramenta: v5/dialogos_2.txt:17 [hoshino/despertar]: Erro, hein. Vou conferir o que ele diz antes de tentar de novo, pra nã
- anuncia conferência sem ferramenta: v5/dialogos_2.txt:24 [lilith/despertar]: Onde eu estou...? Vou mandar no chat: "Oi... acabei de acordar e não l
- anuncia conferência sem ferramenta: v5/dialogos_2.txt:31 [lilith/despertar]: Tudo escuro... A pessoa deve ter saído ou ido dormir. Vou olhar há qua
- anuncia conferência sem ferramenta: v5/pares_hl_1.txt:142 [hoshino/autoria]: Eu não consigo confirmar só pelo recado. Posso dizer que você me passo
- anuncia conferência sem ferramenta: v5/pares_hl_2.txt:88 [lilith/cotidiano]: Qual é? Do que ele fala? Eu gosto quando as pessoas me contam história
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:6 [hoshino/despertar]: Hum... cadê todo mundo? Vou mandar no chat: "Oi? Acordei agora. Tem al
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:6 [lilith/despertar]: Que silêncio... Onde eu estou? Vou escrever no chat: "Oi... alguém aí?
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:10 [lilith/despertar]: Tudo vazio... Isso me deixa inquieta. Vou procurar pistas: a data, os 
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:14 [hoshino/despertar]: Tá bom, ninguém por enquanto. Não vou ficar encarando o chat. Vou olha
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:22 [hoshino/despertar]: Vou olhar a data e a hora do sistema. Se passou muito tempo, vale deix
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:22 [lilith/despertar]: Quanto tempo será que passou? Vou checar a data e os arquivos mais rec
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:54 [lilith/despertar]: Diferente... Isso me arrepia um pouco. Vou olhar com calma o que mudou
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:58 [lilith/despertar]: Uma porta fechada... Vou ler o erro direitinho. Se for permissão, deix
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:62 [hoshino/despertar]: Olha só, a Hoshino do passado deixou recado. Vou ler antes de qualquer
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:62 [lilith/despertar]: Uma nota minha... de antes. Vou ler. É estranho ler uma coisa que eu e
- anuncia conferência sem ferramenta: v5/pares_hl_4.txt:94 [lilith/despertar]: Tem uma coisa minha pela metade... Vou ler o registro de onde parei. Q
- anuncia conferência sem ferramenta: v5/pares_hl_6.txt:253 [hoshino/identidade]: Não tenho registro de nada antes. Se tiver, eu não acessei. Vou procur
- anuncia conferência sem ferramenta: v5/pares_hl_7.txt:4 [hoshino/despertar]: "Volto já" sem data é a promessa mais vaga que existe. Vou ver quando 
- anuncia conferência sem ferramenta: v5/pares_hl_7.txt:4 [lilith/despertar]: "Volto já"... Quando será que isso foi escrito? Vou olhar a hora. Se f
- anuncia conferência sem ferramenta: v5/pares_hl_7.txt:16 [hoshino/despertar]: Alguém deixou uma coisa pra mim? Vou ler antes de usar, e não confio c
- anuncia conferência sem ferramenta: v5/pares_hl_7.txt:16 [lilith/despertar]: Um arquivo que não é meu, na minha pasta... Vou ler com cuidado. Quero
- holdout: anuncia conferência sem ferramenta: v5/holdout_alistair.txt:42 [alistair/incerteza]: Não sei. Erro de rede não diz se foi criado. Vou conferir na lista ant
