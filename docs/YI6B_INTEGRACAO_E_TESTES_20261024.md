# Yi6B: integração e teste mínimo — 24/10/2026

**Decisão posterior:** o proprietário pediu retirar o Yi. Os pesos/aliases e
seleções Yi foram removidos, preservando este diagnóstico. O substituto deve
ser consideravelmente mais rápido que o7B; [estado da substituição](SUBSTITUICAO_YI_EXECUTOR_RAPIDO_20261024.md).
As seções abaixo registram os ensaios anteriores, não instalação atual do Yi.

## Resultado

O proprietário autorizou integrar o Yi e testar o mínimo esperado. O suporte
foi implementado, mas **a ativação automática permanece desabilitada porque
os testes reais reprovaram**. Código aprovado pela suíte não significa LLM
aprovado. Não houve troca de pesos, treinamento, download, reset, alteração de
identidade ou criação de conversas/memórias nas entidades.

Os dois catálogos receberam um bloco `companion` para o Yi existente, com
`enabled=false`, `conversation_validated=false` e `block_reason=basic_tests_failed`.
Os recibos e seus hashes estão vinculados à configuração local. A seleção
manual anterior não foi removida; isso não transforma o candidato em aprovado.
Alistair/Xbox, 9B, 7B e o agendamento de treinamento não foram alterados.

## Implementação

- `app/core/yi_companion.py`: terceiro executor opt-in, isolado por entidade,
  alias/manifesto/origem pinados à seleção existente. Exige recibo íntegro de
  todos os oito casos, revisão semântica aprovada, perfil físico seguro e unload.
- Janela ensaiada de4096 tokens, saída própria de até512, GPU com todas as
  camadas e reserva conservadora mínima de5GiB. Sem diminuir a margem do RM.
- Elegível somente para conversa simples em texto cujo contexto integral caiba.
  Não aceita ferramentas, histórico com chamadas de ferramentas, visão ou
  formato estruturado. Não substitui o principal em tarefa complexa/importante.
- Limites e capacidades ficam na escolha imutável do ciclo. `main.py` usa o
  mesmo teto na requisição e omite `think` no Yi. Não descarta contexto para
  fazê-lo caber, não troca modelo no meio da resposta e recusa mudança posterior
  de contrato para ferramentas/formato incompatíveis.
- `scripts/verificar_yi_basico.py`: ensaio físico explícito `--run`, com pesos
  existentes, locks das entidades/laboratório, daemon owned e RM. Casos
  sintéticos não passam pelo chat, escriba ou aprendizado. Sem novo scheduler.

O custo inicial de8s é uma heurística de seleção para um futuro candidato
aprovado, **não** uma comparação medida contra9B/7B. A implementação não força
rodízio, nem habilita o Yi apenas porque está instalado ou respondeu uma vez.

## Casos definidos antes do ensaio

Identidade pelo nome fornecido; instrução curta (`PRONTO`); definição simples
em português; conta3+2 com saída somente numérica; recuperação de nome/cor de
um contexto fictício; reconhecimento de memória desconhecida; atribuição de
preferências a sujeitos distintos; tradução curta inglês→português.

O teste registra finalização/EOS, saída, tokens/tempos e condições físicas.
`done_reason=length` interrompe a rodada sem retry/aumento do teto. Presença de
palavras-chave não basta: a revisão semântica é um gate separado. Os falsos
positivos encontrados foram preservados nos recibos, não convertidos em PASS.

## Evidência real

| Ensaio | Execução | Resultado revisado |
|---|---|---|
| Hoshino, protocolo atual, GPU | 8 casos | 4 aprovados/4 reprovados; básico reprovado |
| Hoshino, serialização nativa, GPU | 8 casos diagnósticos | Falhas de definição, conta/contexto e memória persistiram; sem homologação |
| Lilith, protocolo atual, GPU | 6 casos | 2 aprovados/4 reprovados; parou por saída incompleta; 2 casos não executados |
| Hoshino, controle CPU | 2 casos diagnósticos | Ambos reprovados: definição e contexto |

Exemplos sintéticos — não são histórico humano:

- Reconheceu os nomes Hoshino/Lilith e seguiu a instrução `PRONTO`.
- Hoshino traduziu corretamente: “A caixa azul está aberta.”
- Em vez de explicar guarda-chuva como proteção da chuva, respondeu sobre
  chaves/cartões; o controle CPU respondeu sobre bordas de táxis/carros.
- O contexto dizia caixa azul. Hoshino respondeu **vermelha**, inclusive naCPU.
  Lilith citou a caixa azul, mas negou que a cor tivesse sido informada.
- Na conta chegou ao número5 no protocolo atual, mas não cumpriu a saída apenas
  numérica. No diagnóstico nativo acrescentou uma justificativa aritmética falsa.
- No diagnóstico nativo inventou uma feijoada para uma refeição desconhecida.
  Lilith produziu512 tokens sobre o ensaio e terminou com `done_reason=length`.

O primeiro classificador automático contou6/8 na Hoshino, incluindo dois
falsos positivos (definição/contexto). A revisão reduziu o resultado a4/8.
Na Lilith, o acerto automático do contexto também era falso. Os detectores
foram corrigidos e receberam regressões; as respostas originais foram mantidas.

Os aliases H/L têm o mesmo manifesto pinado
`3e9a9905779b5eb9639a4e2fdfff8513b1df2906369432408a539c33df2ea9d2`,
em stores individuais, com pesos GGUF de3.673.968.736 bytes. O recibo local
da base declara `01-ai/Yi-1.5-6B-Chat`, revisão
`771924d1c83d67527d665913415d7086f11ea9c0`.
Foi conferida a serialização do tokenizer local e realizado um controle sem
reescrever o template/alias. A [origem oficial](https://huggingface.co/01-ai/Yi-1.5-6B-Chat)
orienta usar o template do tokenizer. A comparação não resolveu as falhas.

Isso **não identifica definitivamente** se a causa restante está no modelo,
na conversão ou em outra parte do protocolo. O controle CPU mostra que não é
um problema exclusivamente de inferência GPU. Não foi feito outro export,
instalação de variante, nova quantização ou treino para tentar fazê-lo passar.

## Recursos, encerramento e recibos

Nos ensaios padrão GPU: residência do modelo3.882.069.523 bytes, pico total
aproximado3,99GiB; RAM disponível mínima acima26GiB; temperatura máxima68°C
na Hoshino/64°C na Lilith e `pressure=[]`. Decodificação nesses casos curtos
em torno44 tokens/s, sem comprovação de qualidade ou vantagem sobre outroLLM.

Unload confirmado em todas as rodadas. Saídas reais: Hoshino2 (reprovação),
diagnóstico nativo2, Lilith1 (resposta incompleta tratada como erro), controle
CPU2 (diagnóstico não homologa a suíte). Nenhum replay foi feito após o corte
da Lilith. Uma leitura pós-unload da Hoshino ficou instável e foi preservada;
ao reconciliar, ambos os endpoints owned estavam fechados, os leases vazios
e a GPU estável com371.990.528 bytes usados. As entidades continuaram dormindo/
offline. O campo de liberação ausente no recibo inicial de erro da Lilith foi
confirmado em `postcheck`, sem apagar a evidência original.

Arquivos locais, ignorados pelo Git, em
`compartilhado/runtime/ensaios/yi6b-20261024/`:

- `hoshino.json`: casos originais, revisão e reconciliação;
- `hoshino-native.json`: controle de template;
- `lilith.json`: casos executados e falha de finalização;
- `hoshino-cpu-control.json`: controle CPU, sem tratar subconjunto como aprovação.

## Testes de software e operação

**99 testes de executores** e **88/88 grupos oficiais offline** aprovados,
incluindo preservação de identidade/contexto, saída512, capacidades, pinagem,
recibos faltantes/divergentes, revisão semântica, pressão, unload e ciclo imutável.
Logs: `/tmp/yi6b-executores-final-20261024.log` e
`/tmp/yi6b-oficial-20261024.log`. Não foram usados modelos reais nessa suíte.

Para reverter o suporte, manter `enabled=false` ou remover somente o bloco
`companion` Yi dos dois catálogos; originais e seletores permanecem intactos.
Para habilitar no futuro, é preciso resolver os erros, concluir os oito casos
de cada entidade, revisar semanticamente e vincular um recibo aprovado ao alias/
hash exatos. Mudar flags não faz o loader aceitar um recibo reprovado. Novos
treinos, pesos ou variantes dependem de autorização própria; não foram iniciados.

## Diagnóstico dos originais — pedido de somente testes

O proprietário autorizou apenas os testes necessários, não troca/instalação,
treino, reconversão ou ativação. A comparação completa **ficou inconclusiva**:
a sessão de execução desapareceu durante uma reinicialização do computador,
sem recibo final do processo filho. Nenhuma resposta HF sobreviveu de forma
durável; não se presume que os casos executaram ou passaram. Não houve replay.

Verificações de leitura concluídas:

- Os três shards originais continuam com os hashes pinados;12.122.104.808 bytes
  de pesos preservados. Configuração, tokenizer e bases não foram regravados.
- A renderização manual do diagnóstico nativo é igual ao
  `apply_chat_template` local nos dois contextos comparados. Portanto, esses
  dois testes não foram protocolos independentes entre si.
- **Existe incompatibilidade de tokenização no caminho HF instalado**:
  `transformers5.19.0` retorna `LlamaTokenizer` baseado em `TokenizersBackend`,
  com `is_fast=true` mesmo pedindo `use_fast=false`. O SentencePiece local
  codifica `<|im_start|>` como `[6]`; o carregador instalado o divide em
  `[1581,59705,622,59593,5858,46826]`. Os vocabulários têm64000 e63992 entradas,
  respectivamente. Isso impede tratar uma inferência desse caminho como um
  controle fiel do tokenizer original sem resolver/explicitar a divergência.
- O vocabulário GGUF corresponde às64000 peças do SentencePiece, sem diferença.
  Q/K da camada0 correspondem aos pesos HF após a permutação esperada de RoPE
  (cossenos0,995799/0,995885); V corresponde diretamente(0,999805). É uma
  amostragem estrutural, **não** prova da conversão inteira ou da qualidade.
- EOS do tokenizer/GGUF é7; config/generation_config declaram2. O teste
  planejado usa explicitamente7, sem alterar arquivos. Não basta mudar EOS
  para explicar as respostas semanticamente erradas já observadas.

`scripts/comparar_yi_original.py` prepara um ensaio CPU isolado dos originais:
armazenamento BF16, operações Linear temporárias FP32 para não depender da
emulação BF16 lenta deste Ryzen, sem quantização nem salvamento de pesos.
O mecanismo passou somente no smoke com um modelo aleatório minúsculo; o
ensaio completo não foi validado. Mantém locks/RM, monitor físico, limite de
tempo/saída e espera pelo filho owned antes de liberar compute. Foi adicionado
registro durável antes de uma futura partida e em cada evento, para uma queda
não apagar a evidência de tentativa nem permitir repetição implícita.

Na reconciliação às13:25 de24/10: nenhum processo do ensaio, endpoints owned
11435/11436 fechados, H/L dormindo e Alistair offline. O registro RM do pai56674
persistiu, mas esse PID não existe e o lock kernel do token está livre; isso
**não** é um exit normal confirmado. A GPU estava estável,324.694.016 bytes
usados, com29.360.857.088 bytes de RAM disponíveis. Os journals confirmam a
mudança de boot, mas não comprovam a causa, OOM ou panic. Não atribuir a
reinicialização ao modelo sem evidência e não reiniciar inferência às cegas.
Depois de preservar essa evidência, a consulta normal `RM.status()` reconciliou
o token comprovadamente abandonado pelo lock kernel: leases e fila vazios.
Não foi feito DELETE manual, partida nova ou reinício de serviço. A validação
offline confirmou AST/JSON, catálogos Yi desabilitados, hashes dos recibos H/L
anteriores intactos e recusa de nova partida quando existe recibo da tentativa.

Recibo separado: `compartilhado/runtime/ensaios/yi6b-20261024/hoshino-hf-comparison.json`.
Os recibos reprovados e os catálogos de executores anteriores permanecem
intactos/desabilitados. O achado **não aprova nem condena definitivamente a
base HF**, e não explica sozinho as falhas GGUF. A comparação de geração
original versus convertido continua pendente de uma execução estável.

## Continuação após esclarecimento humano da queda de energia

O proprietário esclareceu “a luz piscou continue por enquanto”. A tentativa
interrompida foi preservada, e uma nova comparação diagnóstica foi autorizada.
Nenhum treino, adaptador, conversão/exportação, download de modelo ou ativação.
As entidades permaneceram dormindo/offline; nenhum caso entrou em chat/memória.

1. **Original BF16, CPU, sem quantização**: o primeiro caso começou a explicar
   guarda-chuva como proteção da chuva, mas não concluiu. Parou cooperativamente
   aos240,573s,37 tokens, sem EOS; não é PASS. Os casos de contexto não executaram,
   e o teto não foi ampliado. RAM mínima24.760.733.696 bytes, CPU máxima62,125°C,
   sem swap/pressão; exit real1, filho encerrado antes de liberar o RM.
2. **Controle NF4 direto dos originais, GPU com embedding/head CPU**: primeira
   carga foi interrompida pelo monitor do ensaio porque o swap *global* subiu
   uma página(4096 bytes), mesmo com23.788.548.096 bytes de RAM disponíveis.
   Isso não comprovou OOM nem pageamento pelo filho. O recibo e o exit-15 foram
   preservados; processo ausente, GPU ociosa e lease/fila livres reconciliados.
   O monitor do teste foi corrigido para verificar `VmSwap` do filho owned,
   sem alterar RM, margem de VRAM, piso de RAM, limites térmicos ou prazo.
3. **Único controle NF4 após essa correção**: completou os três diagnósticos,
   todos com EOS; **apenas1/3 passou na revisão semântica**, sem homologação.
   A operação foi somente inferência NF4 transitória, não treinamento nem
   exportação de outros pesos. Foi usado o offload já existente `head_cpu1`,
   sem override gfx e com BF16 nativo, a partir dos originais locais.

| Caso NF4 | Tokenização | Resultado |
|---|---|---|
| Nome fictício Nara e caixa azul | SentencePiece local | Negou que as informações tivessem sido fornecidas; reprovado |
| Definição de guarda-chuva | SentencePiece local | Definição incoerente sobre coqueiras/berços e “alma do delírio”; reprovado |
| Mesmo contexto Nara/azul | AutoTokenizer instalado | Recuperou os dois fatos, com gramática ruim; passou nesse critério limitado |

Os tempos desses três casos foram16,313s,15,207s e12,455s. São diagnósticos
com offload, não um benchmark do executor final nem comparação justa de velocidade
com Ollama. O controle NF4 consumiu no máximo4.549.181.440 bytes de VRAM total;
RAM mínima15.462.469.632 bytes; junction máxima87°C, edge56°C, memória46°C e
CPU53,875°C. `pressure=[]`, swap do filho0. O swap global chegou a393.216 bytes,
registrado separadamente, sem ser apresentado como consumo do modelo. Exit0,
filho realmente encerrado, leases/fila livres e fonte revalidada após o ensaio.

Também foi consultada **somente a metadata** do repositório oficial, na revisão
pinada `771924d1c83d67527d665913415d7086f11ea9c0`, via API pública. SHA256 LFS
dos três shards e do tokenizer.model correspondem aos hashes locais verificados;
os Git blob IDs de config/generation_config/índice/tokenizer.json/config/mapa de
tokens também conferem. Portanto, não foi apenas uma autoconsistência de recibos
locais. Nenhum arquivo do modelo foi baixado/regravado nessa conferência.

**Conclusão limitada:** a divergência dos tokenizers foi reproduzida, mas o
tokenizer fragmentado acertou um dos contextos; não é possível declará-la causa
única de todos os problemas. Falhas semânticas também ocorreram ao carregar
diretamente os originais em NF4, não apenas no GGUF. Isso não substitui um
controle BF16 completo, que ficou incompleto, e não isola modelo versus todos
os efeitos de runtime/quantização. O pipeline atual do Yi continua reprovado
para adoção; nenhuma personalidade ou capacidade geral foi inferida da loss.
Catálogos e hashes dos recibos reprovados H/L permaneceram intactos/desabilitados.

Recibos adicionais na área local de ensaios:

- `hoshino-hf-comparison-energy-retry.json`: BF16/CPU incompleto pelo prazo;
- `hoshino-hf-nf4-control.json`: carga abortada, evidência do falso positivo;
- `hoshino-hf-nf4-owned-control.json`: três diagnósticos NF4, revisão, origem
  oficial e reconciliação. `completed=true` significa execução encerrada,
  **não** qualidade aprovada (`quality_approved=false`).

Na conferência final, a GPU estava estável em1.022.574.592 bytes e RAM disponível
26.636.894.208 bytes, sem processos do ensaio, jobs ativos, leases ou fila. O
harness passou em AST, sensor CPU presente/ausente e atribuição de swap owned
(zero,4KB e métrica ausente). Não houve nova mudança de produção ou de serviços.
