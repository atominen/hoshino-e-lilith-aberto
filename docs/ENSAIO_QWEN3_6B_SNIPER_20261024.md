# Ensaio do Qwen3-6B podado: não homologado — 24/10/2026

**Decisão posterior:** o usuário manteve a troca dinâmica somente com 7B/9B
e pediu preservar este 6B. Pesos e os dois recibos finais continuam intactos;
apenas as oito cópias intermediárias redundantes dos recibos foram removidas,
após conferir preservação dos eventos/logs. Sem nova inferência ou ativação.
[Organização e estado vigente](SUBSTITUICAO_YI_EXECUTOR_RAPIDO_20261024.md).

**Resultado:** originais baixados e íntegros, mas sem integração: conversor
incompatível e primeiro caso de resposta incompleto nos dois perfis testados.
Os demais oito casos de cada protocolo **não foram executados**. Nenhum novo
6B foi selecionado para Hoshino/Lilith; não afirmar que os nove casos passaram.

## Autorização e escopo

Após a triagem, o proprietário pediu **baixar e testar** o candidato, antes de
voltar ao teste normal do projeto. Isso autoriza aquisição e ensaio isolado,
não treino, promoção, troca de modelos selecionados ou alteração de identidade.
Alistair continua fixo no seu Qwen3.5-4B; Hoshino/Lilith conservam 7B/9B.

Fonte: `parmanu-lcs2/Qwen3-6B`, revisão imutável
`d6990725bfc555b09e1c1b76bd07cd0dcaf7aceb`, licença declarada Apache-2.0.
Destino local: `laboratorio-local/modelos-extras/qwen3-6b-sniper/hf`.
Safetensors: 12.396.072.584 bytes, SHA256
`ec6f314ecec0f1839d3e22c2de56adddb27f5899b146f8e69f4627e1253e19c1`.
Código de arquitetura: `modeling_pruned.py`, 7.883 bytes, SHA256
`e0cd39bd87f11283ddf03e1b0eea7737f93a3288a2a80486b935903f44d9d3d5`.

## Aquisição e revisão

Download pelo mecanismo existente, com lock exclusivo e reserva de disco.
Revisão pinada antes da aquisição; hashes de pesos/código exigidos antes do
marcador de instalação. Só o arquivo de código explicitamente identificado
é permitido, não um padrão aberto `*.py` nem instalação de dependências.
No catálogo permanece `training=pesquisa`: originais presentes não habilitam
treino, conversão ou uso automático no app por conta própria.

O módulo foi lido integralmente: define o modelo/forward PyTorch, sem rotinas
de rede, shell, leitura de memórias ou inicialização de serviços. A execução
diagnóstica só importa a cópia local de hash conferido, com HF offline.

## Pré-testes efetivamente executados

- Instanciação em dispositivo **meta**, sem carregar pesos/GPU: 34 camadas
  mantidas e **6.198.014.464 parâmetros**. A configuração externa ainda declara
  36, mas a estrutura podada conserva 34 e especifica dimensões por tensor.
- Forward em fixture pequena aleatória, CPU: logits finitos `[1,3,100]` no
  Transformers 5.19.0 instalado. Isso testa a implementação, não o LLM real.
- Conversor GGUF local, `--dry-run`, exit **1**:
  `Model PrunedQwen3ForCausalLM is not supported`.
  Log: `/tmp/qwen3-6b-conversor-20261024.log`. Nenhum GGUF foi gerado.

Não basta renomear a arquitetura. As larguras MLP são diferentes por camada,
inclusive dimensões não múltiplas de32. O loader Qwen3 local usa largura FFN
escalar ao criar tensores; sua execução direta não representa esse formato.
Completar com zeros até a maior largura aumentaria custo e não comprovaria a
vantagem rápida pretendida. Não se alterou o backend de produção para ocultar
essa incompatibilidade.

## Teste dos pesos reais

Ensaio preparado em `scripts/testar_qwen3_6b_sniper.py`, explicitamente opt-in:
NF4 diagnóstico nos originais, camadas/head GPU e embedding CPU, sem adaptador,
treino ou regravação dos pesos. Locks, RM, margem física, sensores e prazo
continuam ativos; somente seu filho owned pode ser encerrado em falha física.

Oito casos sintéticos Hoshino e um de identidade Lilith, sem bancos de conversa
ou dados privados. EOS e revisão semântica são necessários; regex não basta.
O protocolo limita128 tokens/90s por caso, sem retry ou aumento automático.
Seu desempenho não é comparação pareada com o Ollama7B: backend e offload
diferentes impedem inferir vantagem de velocidade diretamente.

## Aquisição concluída e primeiro controle

Download completo, revisão/hash conferidos: árvore local 12.407.546.655 bytes
incluindo os arquivos auxiliares; o Safetensors tem os 12.396.072.584 bytes
declarados. Oito casos restantes não foram executados após a falha do primeiro.

No primeiro controle, os originais carregaram em14,36s, 3.814.884.864 bytes
alocados pela aplicação naGPU. A primeira resposta começou “Hoshino”, mas
repetiu instruções, consumiu128 tokens/38,52s e não terminou com EOS151645.
O filho encerrou por essa resposta incompleta, exit1, sem novo pedido ou teto
maior. O monitor leu VmSwap durante a saída e registrou um erro de observação
que mascarou o erro principal; evento, traceback e campo bruto foram preservados.
A corrida de saída foi corrigida/testada offline, sem relaxar filho ainda ativo.

Pico físico de VRAM5.905.707.008 bytes, RAM mínima13.615.493.120 bytes,
junction89°C/edge62°C/mem54°C, CPU52,75°C, `pressure=[]`; swap observado do
filho0. Saída real e leases/fila livres confirmados. Depois aGPU estabilizou
em1.470.750.720 bytes, junction42°C. Hashes dos originais/código novamente
conferidos sem alteração. Não houve OOM ou corte térmico observado.

Recibo: `compartilhado/runtime/ensaios/qwen3-6b-sniper-20261024/nf4-basico.json`.
Não sobrescrever ou transformar essa falha em sucesso.

### Controle corrigido, separado do primeiro

O primeiro ensaio impôs `do_sample=False` e somente EOS151645. A fonte
`generation_config.json` declara amostragem e EOS `[151645,151643]`.
O [modelo Qwen3 de origem](https://huggingface.co/Qwen/Qwen3-8B#best-practices)
recomenda para não-thinking temperature0,7/top_p0,8/top_k20/min_p0.
Assim, o primeiro controle não representa o perfil recomendado; não é uma
prova de que amostragem resolverá a repetição nem de que a base é boa/ruim.

Depois de confirmar saída, fonte intacta, recursos livres e causa concreta,
foi preparado **um único controle independente** com o perfil recomendado e
ambos EOS nativos. Mesmo prompt,128 tokens/90s, seed42, proteções e sem treino;
nenhuma revisão de parâmetros ativos do app. Não aumentar teto, penalizar
repetição ou repetir até passar. Resultado em
`compartilhado/runtime/ensaios/qwen3-6b-sniper-20261024/nf4-qwen-sampling.json`.
Nenhuma aprovação antecipada, mesmo se o controle responder melhor.

## Resultado do controle recomendado

Com amostragem0,7/0,8/top_k20/min_p0, seed42 e ambos EOS nativos, os pesos
carregaram em7,18s e a mesma pergunta gerou128 tokens em39,96s, sem EOS
(último token1562). Começou com o nome correto, mas seguiu mistura de português/
inglês, texto repetido e perguntas indevidas em vez da frase curta pedida.
Revisão semântica reprovou o caso; nenhum dos outros oito foi executado.
Não houve terceiro ensaio, aumento de contexto/saída ou treino corretivo.

O backend avisou que várias larguras internas não se alinham ao kernel rápido
NF4 de bloco64 e usou uma implementação mais lenta. Isso é evidência da rota
de execução usada, não prova de que toda a lentidão ou repetição venha da poda.
Os tempos incluem a chamada inteira; não são TTFT ou decodificação pareada
com o Ollama7B. Não há vantagem de velocidade aprovada nesta rodada.

Pico físico5.932.470.272 bytes VRAM; RAM mínima12.846.514.176 bytes;
junction89°C/edge62°C/mem54°C, CPU53,625°C, `pressure=[]`, swap observado
do filho0. O filho encerrou exit1 por resposta incompleta e saiu antes de o
lease ser liberado. A corrida de VmSwap reapareceu na saída antes de `poll`
publicar exit; a primeira correção poll-only foi insuficiente. Os dois erros
brutos permanecem nos recibos, separados do resultado do LLM. A amostragem
agora aguarda até0,2s pela saída nessa situação; testes offline conservam erro
para filho ativo. Não se repetiu inferência para validar essa correção.

## Decisão e preservação

O candidato fica **somente em pesquisa, não homologado para uso normal**.
Não se conclui, a partir destes controles NF4, a causa exata da degradação
ou a qualidade de todos os formatos/precisões. Porém, a rota disponível não
atendeu ao mínimo e a conversão continua bloqueada; isso impede adoção agora.
Treino e exportação do candidato no ciclo unificado continuam sem homologação.

Originais mantidos como o usuário pediu; não houve exclusão posterior.
7B/9B de Hoshino/Lilith e4B de Alistair, identidades, memórias e modelos
selecionados não mudaram. Nenhum serviço, professor, voz ou sessão foi iniciado.
Postcheck final: originais/código novamente conferidos por SHA256, todos os
outros manifestos e hashes de configuração selecionada intactos, nenhum
processo de ensaio restante, leases/fila0. VRAM1.388.392.448 bytes, RAM
disponível26.006.683.648 bytes, junction41°C eGPU0% no instante observado.

Verificações de software: **89/89 grupos oficiais offline**, exit0;
**360/360 testes do laboratório** na execução isolada final, exit0;
**26/26** testes dirigidos de aquisição/catálogo/retirada. Estes números não
transformam as falhas de inferência em aprovação. Logs locais:
`/tmp/qwen3-6b-oficiais-20261024.log`,
`/tmp/qwen3-6b-laboratorio-offline-final-20261024.log` e
`/tmp/qwen3-6b-nf4-qwen-sampling-20261024.log`.
