# Histórico de estado até 04/11/2026

Movido do `CLAUDE.md` no checkpoint de 07/11, sem alterar o texto. É histórico de ensaios e decisões, não estado
operacional: IDs de tarefa (`ct-...`), servidor, inventário e checkpoints citados aqui não existem mais desde o
recomeço de 05/11. O estado atual está em [ESTADO_ATUAL.md](ESTADO_ATUAL.md).

- **04/11 · congelamento temporário (encerrado em 05/11 a pedido humano):** a linha principal é a referência para
  um ensaio isolado de associação e atenção com Pestinha e LLM local.
  [Protocolo e resultado](docs/ENSAIO_ENTIDADE_PESTINHA_20261104.md).

- **Estabilização de 04/11:** os casos pendentes das revisões da fuga e das
  perguntas reflexivas foram reproduzidos e corrigidos offline. A ponte mantém
  exclusão durante trocas de item já iniciadas pelo reflexo, mesmo ao vencer seu
  prazo. A classificação separa uma segunda pergunta reflexiva de um pedido
  coordenado. Os grupos de estabilidade, integrações e microfone v22 agora
  executam seus casos no runner offline. O arco já foi concluído em 30/10
  (`ct-6827e8b387`); as 30 flechas são uma etapa separada que aguarda pedido.
  [Evidências do arco](docs/MINECRAFT_ETAPAS_POS_KIT_20261028.md#arco--concluída-30102026-1837-ct-6827e8b387-passo-54)

- **Codex, ensaio4B encerrado às17:06:** contexto16.000 coube;12decisões em
  7min54s,41,93tokens/s de geração, sem concluir a picareta. Bancada/tábuas/
  gravetos e coleta tiveram recibos; autocorreção da colocação foi insuficiente.
  [Resultado, trava16GB ativa e limpeza](docs/ADMISSAO_16GB_E_MINECRAFT_4B_20261028.md).
  Todas dormindo ao fim. Ensaio não retomado; seleção permanente preservada.
- **Etapas depois do kit (Claude, 28/10 16:26):** [estado, correções e como retomar](docs/MINECRAFT_ETAPAS_POS_KIT_20261028.md). Lilith pausada na etapa das 30 carnes assadas (`ct-d76da17105`); depois arco, 30 flechas e dois gatos nomeados.
- **4B Qwen × Andy-4.2-Air (Claude, 28/10 18:20):** [comparação no mesmo protocolo](docs/MINECRAFT_4B_QWEN_VS_ANDY_20261028.md). Andy baixado só como alias de teste da Lilith; seleção vigente intocada. Lilith mudou de posição/inventário: conferir antes de retomar as carnes.
- **9B 32K e sem censura × original (Claude, 28/10 20:20):** [resultado parcial](docs/MINECRAFT_9B_SEM_CENSURA_VS_ORIGINAL_20261028.md). Original foi melhor no Minecraft; 32K e alias de teste foram substituídos pela decisão abaixo.
- **Decisão humana 28/10 ~20:50:** Lilith passou para o **Qwen3.5-9B original** (`lilith-qwen3.5-9b-oficial-cd76ec205963`, seleção + recibo com probe real) e **24K**; sem censura preservado, Hoshino inalterado. [Detalhes e como voltar](docs/MINECRAFT_9B_SEM_CENSURA_VS_ORIGINAL_20261028.md#6-decisão-humana-e-troca-aplicada-2810-2050).
- **Programação (29/10):** Minecraft pausado (carnes `ct-d76da17105` passo 122). [Oficina gráfica e modo projeto](docs/PROGRAMACAO_PROJETO_E_OFICINA_20261029.md): desafio do [buraco negro](docs/DESAFIO_AUTONOMO_BURACO_NEGRO_20261013.md) pela Lilith **encerrado a pedido humano** em 29/10 ~17:50, passo 475/600 (`ct-6499763ae6` paused, três entidades dormindo). Resultado **PARCIAL**: nunca compilou/rodou; ficou a infraestrutura de projeto (painel, memória de trabalho, foco, cache). Codex também trabalhou no modo projeto (216→237; mudanças sem commit em project_agent/main/workspace/testes). Não retomar, criar outra tarefa ou escrever o código dela sem novo pedido. Noite: modo projeto ganhou trava de releitura, `onde_esta`, pré-busca, `compilar_projeto` e intermediário por regra; mini-modelo `qwen3.5:2b` baixado com aval humano, só CPU (porta 11440), ligado na Lilith só no modo projeto ([resultado](compartilhado/runtime/ensaios/intermediario-20261029/README.md)).
- **30/10:** 30 carnes assadas **concluídas** (`ct-d76da17105`, 01:18; [relato](docs/MINECRAFT_ETAPAS_POS_KIT_20261028.md)). [Intermediário e lentidão do 9B](docs/INTERMEDIARIO_E_LENTIDAO_9B_20261030.md): 5 modelos comparados, fica o 2B; no Minecraft desligado por padrão (alarmes falsos); revisões do Codex corrigiram aviso que nunca chegava à decisão; meta intermediária 8192→4096 com fechamento pelo próprio raciocínio (aval humano). Lilith acordada sem tarefa; próxima etapa humana: arco.
- **Kit de ferro concluído com assistência**, tarefa`ct-4acf234a28`, passo256,
  registrado às11:12:08 de28/10. As quatro peças estão equipadas e espada,
  picareta, machado e pá foram conferidas no inventário; os oito crafts têm
  registro. Não equivale a aprovação de autonomia geral ou combate.
- Servidor`10.0.0.200:25565`, Java1.16.5, jogador`LilithMC`,
  conversa`claude_mc_servidor_ferro`. Mundo novo, sobrevivência, dificuldade
  mudada pelo humano paraPacífico durante o ensaio. Não importar crédito da
  tarefaLAN antiga`ct-06c691fa40`, nem usar32803/34993 como destino atual.
- Pedido humano posterior: **somente uma entidade ativa sem GPU de pelo menos
  16GB deVRAM; testar Qwen3.5-4B noMinecraft com contexto16.000**.
  [Trava e ensaio curto separado](docs/ADMISSAO_16GB_E_MINECRAFT_4B_20261028.md),
  sem reset ou retomada implícita das carnes.
  A auditoria anterior reproduziu12falhas principais e2complementares offline;
  essas correções de lógica ainda não foram implementadas pela auditoria.
- Não tratar PIDs, sessões, portas abertas ou checkpoints destes relatórios
  como prova permanente. Reconciliar Central/ponte/tarefa/recibos e jobs/leases
  antes de qualquer nova operação ou manutenção.
  O ensaio4B usou o mesmo jogador e alterou posição/inventário legitimamente,
  com recibos em banco separado. Ao retomar as carnes, comparar essas evidências;
  não afirmar continuidade com inventário idêntico ao snapshot das16:26 nem
  limpar a trava de sessão apenas para fazer o objetivo voltar a rodar.
