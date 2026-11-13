# Teste de uso de 07/11/2026: Lilith na Central, PC1 e PC2

Pedido do Gustavo: "vou testar e vamos ver até onde vai, até aparecer o primeiro problema". A conversa foi pela
Central do PC1 e pelo painel do PC2. O Claude acompanhou os diagnósticos, o histórico (só leitura) e os processos.
Cada problema achado ganhou causa, correção e teste.

## Problemas e correções

| # | O que apareceu | Causa | Correção |
|---|---|---|---|
| 1 | Despertar lento: três chamadas, ~45 s, a primeira vazia | O texto interno do despertar ("quando", "qual", "onde") ligava o raciocínio de "pergunta de fato" | A regra só vale para fala de pessoa, não para turno espontâneo (`resource_manager.thinking_for_cycle`) |
| 2 | "Cria uma pasta na área de trabalho" foi parar em `~/Desktop/MinhaPasta`, com "[PASTA VERIFICADA]" | A lista fixa tinha "Área de Trabalho" (T maiúsculo); o PC tem "Área de trabalho"; caía em `~/Desktop` e criava a pasta | `filesystem._desktop_dir` lê `user-dirs.dirs` (o mesmo que o `xdg-user-dir` lê) e compara nomes sem diferenciar maiúscula |
| 3 | "Vou abrir o Firefox para você. Apareceu uma aba vazia." sem ferramenta nenhuma | `abrir_aplicativo` não era oferecida para "chamar a janela do firefox", e a trava só conhecia verbos de conferir | O roteador oferece abrir junto de focar e reconhece nomes de programas. A trava cobra ação dita e não feita: "abri", "apareceu", "está aberto" sempre; "vou abrir" só quando a pessoa pediu uma ação (`conferencia.anunciou_sem_fazer`) |
| 4 | No PC2, "Texto não corresponde à transcrição", e toda mensagem seguinte falhava | O cliente nativo mantinha a transcrição antiga presa ao rascunho mesmo com outro texto digitado | Igual ao painel web: o texto vai como digitado quando não conserva a fala (`draft_keeps_transcript`) |
| 5 | Atalho global mudo no PC2 | O atalho exigia o ambiente do projeto, que o painel do PC2 não tem | Sem esse ambiente, usa o Python do sistema com `python3-pynput`; o instalador do painel instala o pacote |
| 6 | Memórias erradas depois da limpeza (detalhes abaixo) | Cinco causas de código | Ver "Memórias" |

## Memórias

Com a memória apagada às 16:32 pelo Gustavo (backup em `entidades/lilith/runtime/memory-backups/manual-e13f…`),
a frase "eu sou o gustavo rosa nunes eu sou o responsvel pela sua existencia individual nessa instalação" gerou:

1. **"Gustavo Rosa Nunes se chama Gustavo Rosa Nunes":** `scribe._atribuir` trocava "A pessoa com quem falo" pelo
   nome também na própria memória do nome. Agora a memória do nome fica intacta.
2. **Dois "Gustavo Rosa Nunes":** depois de renomear, `atualizar_pessoa` procurava a pessoa pelo nome no `localhub`,
   onde a busca por nome não existe, e criava outra. Agora recarrega a mesma pessoa pelo id (`people.por_id`).
3. **Fantasma "alguém":** o boot cria a pessoa do terminal antigo (`tui`/`local`), e o chat da Central usa
   `localhub`/`usuario`, ou seja, o mesmo humano em dois registros. Agora `people.identificar` trata os dois canais
   locais como a mesma pessoa. Além disso, `chat_identity` lia os canais só como dicionário, então a janela mostrava
   "Usuário" e podia criar um terceiro registro; agora lê os dois formatos.
4. **Papel de criador perdido:** a regra não aceitava "responsvel" (digitado) e só marcava o papel nos canais
   `tui`/`voz`. Agora aceita o erro de digitação e marca no `localhub` quando o papel é declarado.
5. **Escriba-modelo:** gravava "O usuário diz que é o responsável… da entidade" como "preferência" e sem ligar à
   pessoa. `scribe.normalizar_anotacao` troca pelo nome conhecido e por "a Lilith", liga a `participante:usuario` e
   só aceita "preferência" quando é gosto.

**Por que a segunda chamada do 9B não pegou:** as memórias das regras e a tabela de pessoas não passam por ela. O
revisor decide guardar ou não; ele não reescreve sujeito, perspectiva nem tipo.

**Registros errados que já estão na Lilith:** a correção proposta é aposentar, sem apagar, e aguarda o aval humano.

## Um 3B antes do 9B? (pedido humano)

Prova `compartilhado/runtime/ensaios/revisor-memoria-20261107/organizador_3b.py`:
- 59 casos rotulados (27 para guardar, 32 para descartar), mais as 8 anotações reais deste teste;
- CPU com 4 núcleos e temperatura 0.

| Modelo | Perdeu boa | Descartou ruim | Reescrita | s/anotação |
|---|---|---|---|---|
| Qwen3.5 2B | 0/27 | 1/32 | copia a fala da entidade, troca quem fala | 4,5 |
| Granite 4.0 Micro | 1/27 | 6/32 | errada na maioria | 3,5 |
| Ministral 3 3B | 0/27 | 0/32 | acerta o caso bom, muda o sentido dos ruins | 3,7 |
| Llama 3.2 3B | 0/27 | 2/32 | copia sem mudar | 3,2 |

**Conclusão:** nenhum serve como primeiro revisor. Eles não filtram o lixo, e a reescrita deixa a anotação ruim
com cara de verdadeira. O 9B continua revisando, com a normalização em código antes. Os três modelos foram baixados
em `compartilhado/modelos/ollama-intermediario` (~7 GB) e ficam até decisão humana.

## Outros pedidos atendidos no dia

- **Botão do laboratório:** saiu da aba Entidades.
- **Uma janela por vez:** comanda a última que recebeu foco (`central_control.window_may_command` e
  `SO_JANELA_ATIVA`). Dormir, interromper, cancelar, encerrar e os sentidos ficam livres.
- **Fechamento conjunto:** fechar a Central do PC1 fecha o painel do PC2. Fechar o PC2 pergunta "Fechar tudo"
  (padrão) ou "Fechar só esta janela".
- **Respostas estranhas** ("como quiser ser tratada", "você mora perto daqui?", "Obrigado" no masculino):
  - vêm do treino v5 e do prompt reduzido, que não diz que ela vive neste computador;
  - o Gustavo espera que sumam com o treino do banco v6;
  - "Obrigado" e "ser chamada" entram no banco.
- **Temperatura:** a junção a 95–99 °C é normal para o Gustavo e não é mais motivo de alerta.
- **CPU:** trabalho do Claude na CPU fica limitado a 4 núcleos depois do reinício das 17:26.

## Rodada da noite (memória do zero, 20:25–20:45)

O Gustavo apagou a memória da Lilith pela Central (backup `manual-7832…`) e testou com o código corrigido.

**Já funcionou:**
- **Nome:** "A pessoa com quem falo se chama Gustavo Rosa Nunes".
- **Relação:** "…se declara responsável por eu existir… foi quem me montou".
- **Pessoa:** uma só, com papel de criador e os dois canais locais juntos.
- **Revisor:** barrou o lixo do escriba, agora com o trecho copiado e a origem no `memory.review`.
- **Fechamento:** a Central e as janelas fecharam juntas.

| O que apareceu | Causa | Correção |
|---|---|---|
| Janela do PC1 não fechava depois que o PC2 encerrou a Central | Só o PC2 fechava junto; o PC1 esperava um recibo novo que nunca vinha | As duas janelas fecham ao ver a Central encerrando ou a porta fechada por 10 s; com a Central já fechada, a janela fecha na hora |
| Memória "poluída pelas instruções" (duas reflexões) | A reflexão lia recibos mecânicos de ferramenta e a nota fixa do sistema; o despertar virava fala de "alguém" | Reflexões (periódica e noturna) sem `tool_receipt` nem a nota fixa; episódio por iniciativa gravado como dela |
| Pedido: cartão de bronze | — | Níveis bronze, ferro, ouro e diamante (platina vira diamante, com migração do banco). O que a pessoa disse e o revisor confirma, mas é passageiro, vira bronze no cartão "O que <pessoa> me disse", com a menor prioridade |
| "me diga [quem] eu sou" virou "não tem nada na minha agenda" | O bloco da pessoa dizia "não vira assunto", tratava por "ela/nela" e não trazia o que ela sabe | `people.bloco_pessoa`: usa o nome, permite responder, traz as memórias ligadas à pessoa, "não presumo gênero" |
| "Vou abrir no PC2…" sem abrir | A trava só olhava a última mensagem, sem verbo | A trava olha as últimas falas da pessoa |
| O que ele pediu virava "sem apoio" | O 9B devolveu trecho vazio; a origem só via a última mensagem | Sem trecho: vale se a anotação usa as palavras-chave da fala (pergunta não conta). A origem confere as falas recentes |
| "favorito = encontre um manga de luta…" | Sem acento, o "e" da conjunção foi lido como "é" | "e" seguido de pedido ou pronome é conjunção; em "X, ele é meu favorito" o favorito é o X |
| "Já deixei o link aberto" (no PC1, sem link) | Nada cobrava | Pediu link e a ferramenta trouxe um: a resposta precisa trazê-lo (uma recuperação) |

**Pendente:**
- **Pedido com várias partes:** ela fez uma de três e encerrou. Precisa de uma lista do que foi pedido, conferida antes da resposta final.
- **Fica para o treino** (decisão do Gustavo):
  - "Obrigado" no masculino;
  - "como quiser ser chamada";
  - a pessoa tratada como visita;
  - saber da existência das outras entidades.
