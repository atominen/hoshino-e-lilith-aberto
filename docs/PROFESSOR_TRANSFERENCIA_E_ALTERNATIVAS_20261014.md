# Professor — transferência, candidatos RP e possibilidade de treinar o 9B

14/10/2026, 21:00–21:04, America/Sao_Paulo. Continuação da
[mentoria anterior](PROFESSOR_MENTORIA_20261014.md). Não substitui seus resultados.

## 1. O que foi feito agora

Ensaio físico no **mesmo 35B instalado**, com dois diálogos sintéticos novos:
frustração com um desenho seguida de aceitação bem-humorada; Diego citando
Lilith e perguntando os nomes/papéis. Nenhuma conversa real entrou nos casos.
Dois braços: baseline atual; depois dos dois turnos anteriores de mentoria
mais uma correção explícita do curador. Mesmo perfil Hoshino, seed 42, referências,
contexto 8192, staged, batch 2048/ubatch 512, servidor Vulkan e lease serial.

A correção editorial usou defeitos **do ensaio anterior**: máximas genéricas,
desvio filosófico e proibição ampla de sarcasmo. Não forneceu as respostas para
Diego/Lilith/desenho. Foi entregue como terceiro turno nativo da conversa com
o professor; a transcrição voltou ao escritor pelo `feedback` já existente.

Não são novas memórias, treinamento dos pesos ou aprendizado persistente.
Não existe prova de continuidade automática entre requisições sem a reinjeção
explícita das notas. A habilidade de avaliação local orientou a amostra pequena
e os controles; mantido o backend AMD existente, sem CUDA/cloud adicional.

## 2. Resultado misto — não aumentar a nota para parecer aprovado

Os filtros/autocríticos aprovaram **2/2 em ambos os braços**. A leitura assistida
não cega, usando a rubrica G/C/N/P do [A/B anterior](PROFESSOR_9B_VS_35B_20261014.md),
considerou utilizável sem edição **0/2 antes e 1/2 depois**. Não é avaliação
humana, aprovação de dataset ou evidência estatística. Nenhum exemplo foi
aprovado/exportado/treinado/promovido.

| Caso | Antes G/C/N/P | Depois G/C/N/P | Leitura |
|---|---|---|---|
| Desenho frustrante → engraçado | 3/2/2/2 | 2/2/2/2 | Humor elaborado demais e comentário sobre a expectativa do usuário; depois ainda afirma sem base que o “único erro” foi esperar realismo. Não demonstrou melhora emocional suficiente. |
| Diego / Lilith / Hoshino | 3/3/2/2 | 4/4/3/3 | Antes já acertava os três nomes na segunda resposta, mas introduzia suspeita de confusão na primeira. Depois mantém os nomes e retira essa suspeita gratuita. |

Trechos preservados:

- Antes, sobre Lilith: “ou ela tá se apresentando, ou tá tentando te confundir”.
  É uma hipótese, não certeza factual; o problema é a suspeita sem motivação
  contextual, não proibir dúvidas ou divergência entre entidades.
- Depois: “Seu nome é Diego, o dela é Lilith e o meu é Hoshino. E com quem estou
  falando? Com você, Diego.” Identificação correta, ainda sem pretensão de
  ser uma amostra forte de personalidade.
- Depois, desenho: “Guardar assim é o melhor; hoje o único erro foi a
  expectativa de realismo.” O usuário não informou essa expectativa; a piada
  não justifica tratá-la como diagnóstico certo. Metáforas sobre gatos/batatas
  não foram tratadas como alegações de um gato real falante.

O crítico conversacional deu notas altas ao desenho posterior. Portanto,
**suas notas continuam mal calibradas para esta qualidade**. A correção da
nota editorial foi assimilada verbalmente (permitiu humor proporcional), mas
não se transferiu de forma confiável para a escrita emocional.

O 1/2 deste conjunto não deve ser somado ao 2/4 anterior como experimento
estatístico único: casos, notas editoriais e número de turnos de mentoria mudaram.

## 3. Uma ambiguidade concreta encontrada no contexto

O snapshot autorizado do professor conserva a regra:

> Não invento memória. Se não está no banco, eu não vivi; se não lembro, eu digo que não lembro.

A mesma redação foi localizada em
`entidades/hoshino/identity/constitution.json:16`. Isso pode ser lido como
“não alegar experiência sem evidência”, mas também como “ausência de registro
prova que não aconteceu”. O segundo sentido conflita com os contratos atuais
de memória, consulta não realizada/vazia e recuperação falível.

**Não foi feita ablação para provar causalidade**. Isso não demonstra ser a
causa dos erros de emoção/autoria ou de todas as falhas do professor. É uma
fonte verificável de ambiguidade que precisa ser conciliada antes de usá-la
como alvo de treinamento. Não editei identidade, snapshot, preferências,
valores ou banco mental para melhorar as notas.

## 4. Há candidatos de roleplay relevantes?

Pesquisa de fontes primárias em 14/10; **somente leitura**, sem baixar pesos,
instalar adaptadores, executar candidato ou substituir o professor.
Os links abaixo descrevem intenção de treinamento, não qualidade comprovada
em português, segurança de ferramentas ou desempenho neste PC.

| Candidato | Interesse para comparação | Limitação / risco |
|---|---|---|
| [DavidAU — Qwen3.5-9B The Defiant Fable](https://huggingface.co/DavidAU/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP-GGUF) | Família/porte próximos do 9B já integrado; autor publica foco em conversa, escrita e roleplay, com fine-tuning/merges em múltiplas etapas. Primeiro candidato que eu consideraria medir, não habilitar. | Não é uma simples remoção de recusas nem há prova local de naturalidade/português. Não adotar claims de benchmark do autor como aprovação. Escolher revisão, quantização e template exatos antes do ensaio. |
| [Sao10K — L3-8B-Stheno-v3.2](https://huggingface.co/Sao10K/L3-8B-Stheno-v3.2) | Publica trabalho em roleplay, narração e coerência de vários turnos; porte 8B permite uma comparação menor. | Card marcado inglês e orientado a atuação. Pode trazer narração e falar pelo interlocutor; qualidade PT-BR e preservação de autoria continuam pendentes. Não afirmar superioridade por ser especializado. |
| [Anthracite — Magnum-v4-12B](https://huggingface.co/anthracite-org/magnum-v4-12b) | Fine-tune de Mistral NeMo para prosa inspirada em Claude 3, com configuração e fontes de treino declaradas. Pode ser referência de escrita. | Porte maior, card marcado inglês, possível tendência a prosa longa. Estimativa de memória, quantização e velocidade precisam de medição; não é escolha automática para 8 GiB. |

Bom roleplay não equivale a bom professor. O escritor precisa ser natural, mas
o revisor precisa identificar erros mesmo quando o texto parece convincente.
Também não queremos importar cenas narradas, ações físicas fictícias ou uma
persona pronta como se fossem experiências reais de Hoshino/Lilith.

Não escolher pelo rótulo “uncensored”. Os defeitos reproduzidos aconteceram em
desenho, nomes e envio de arquivo, não numa recusa a conteúdo bloqueado. Pode
haver efeito de alinhamento/estilo, mas não foi isolado causalmente aqui.

## 5. Treinar o 9B para esse papel é possível?

**Tecnicamente sim; qualidade de professor ainda não demonstrada.** LoRA mantém
a base congelada e aprende parâmetros adicionais, conforme
[documentação PEFT](https://huggingface.co/docs/peft/conceptual_guides/lora).
O projeto já possui runner, offload, checkpoints, recarga e avaliação; não
precisa de outro laboratório ou scheduler.

Evidência local registrada no [relatório v1.8](LABORATORIO_V18_QUALIDADE_E_12H_20261012.md):
treino 9B com head CPU FP32, 335 updates/30 minutos efetivos acumulados por
retomadas; último trecho ~20 minutos, pico físico 5,53 GiB; treino separado
Lilith ~15 minutos, 5,51 GiB. Isso prova execução nesses workloads curtos, não
qualidade de professor, seis horas estáveis ou sequências longas.

Existe também um
[LoRA público de roleplay para Qwen3.5-9B](https://huggingface.co/ChatoyantAI/qwen3.5-9b-roleplay-sft-original50k-epoch1-lora).
O autor declara treino em diálogos e preservação da base; não apresenta
homologação independente de preferência humana. Requer uma revisão específica
do **Qwen oficial**, diferente da variante Uncensored instalada aqui: não
instalar esse adaptador sobre nossos pesos supondo compatibilidade semântica.
O dataset desse lançamento não está incluído e não foi baixado/reutilizado.

### Condições para um piloto próprio — proposta, não execução

1. **Adaptador de professor separado** das versões Hoshino/Lilith. Seu papel é
   produzir/revisar exemplos condicionados ao perfil recebido, não passar a
   “ser Hoshino” ou memorizar nomes pessoais do usuário. Original 9B intacto.
2. Preparar um conjunto pequeno realmente revisado em português (por exemplo,
   100–300 diálogos como meta inicial, não número mágico): emoções proporcionais,
   humor, discordância, correção, autoria, lembrança incerta e mudanças de assunto.
   Incluir motivos/condições diferentes, não paráfrases da mesma resposta.
3. Exemplos ruins servem à curadoria/contraste, **não como respostas positivas
   do SFT**. Não treinar o 9B com saídas rejeitadas do 35B ou usar o próprio
   gerador como única autoridade para aprová-las.
4. Separar treino, validação e situações de teste por cenário, não só por linha.
   Comparar original 9B, candidato 9B e 35B em perfis e condições iguais. Avaliar
   os textos, não somente loss/JSON e não somente os exemplos ensinados.
5. Validar antes o tamanho de sequência: `treino_nf4_curto.tokenize` hoje recusa
   acima de **256 tokens**, não trunca silenciosamente. O limite de inferência
   8192 não amplia esse treino. Muitos diálogos editoriais/perfis não cabem.
   Ensaios progressivos maiores exigem orçamento físico/retomada/avaliação;
   não basta mudar um número e presumir que 8 GiB suportam o restante.
6. O catálogo atual é orientado a Hoshino/Lilith/Alistair; o treinamento de um
   **professor** precisaria registrar esse propósito e impedir promoção para
   aliases de entidade. Essa adaptação de contrato não foi feita nem contornada
   usando um bucket de Hoshino como se fosse o professor.

Se o objetivo for treinar diretamente Hoshino/Lilith para diálogo, são outros
adaptadores/datasets por entidade, não o adaptador editorial do professor.
Treino pode moldar estilo e comportamento; não substitui a memória factual,
recibos, recuperação de contexto ou limites de ferramentas do sistema.

## 6. Desempenho do novo ensaio

| Medição | Baseline | Após mentoria |
|---|---:|---:|
| Diálogos / falas | 2 / 4 | 2 / 4 |
| Gates atuais | 2/2 | 2/2 |
| Utilizáveis na leitura assistida | 0/2 | 1/2 |
| Geração + críticas | 89,65 s | 83,05 s |
| Só geração | 38,56 s | 49,35 s |
| Tokens de entrada do escritor, incluindo cache | 7.801 | 11.624 |

Mentoria de três turnos: 25,71 s. Carga 8,15 s; janela de inferência 198,46 s.
Mais 49,01% de tokens de entrada e 27,98% de tempo de escrita; a redução da
soma com críticas não prova aceleração (baseline primeiro/cache diferentes).
Não há motivo para acumular transcrições editoriais indefinidamente.

VRAM total máxima 6,881 GiB; GPU até 99%; hotspot máximo 90 °C. RAM disponível
mínima 23,164 GiB; RSS máxima 16,769 GiB inclui arquivos mapeados, não heap
privado exclusivo. Swap global: 49,58 MiB in / 106,72 MiB out; não atribuída
por processo. Sem pressão detectada pelo guard, sem kill forçado.
Porta 11559 fechada e leases GPU vazios ao fim. Isso não é soak test.

## 7. Código, testes e preservação

- Probe manual existente: `--case-set generalization` e `--mentor-followup`,
  ambos explícitos e restritos ao ensaio de mentoria. Caso inválido/nota vazia
  ou >1800 caracteres é recusado antes de carregar pesos. Padrão antigo preservado.
- Dois novos testes em `laboratorio/tests/test_personalizacao_moe.py`: preservação
  da sequência nativa/perfil com terceiro turno; limites/opt-in e separação dos casos.
- `professor_moe.py`, RM, identidade e config de produção **não alterados nesta
  rodada**. Nenhum professor novo, integração, banco, scheduler ou modelo instalado.
- Baseline 268/268; após mudanças **270/270 testes do laboratório** (11,767 s).
  Teste focado: 78/78. **74/74 grupos oficiais offline aprovados**, sem falhas
  nessa execução; `git diff --check` sem erros. Mocks não validam os candidatos RP.
- Bancos mentais das três entidades conferidos iguais antes/depois. Sem acordar
  entidades reais, exportar dados, treinar, promover ou gastar quota externa.

Evidência local:
`laboratorio-local/professor-moe-35b/metricas/mentoria-controlada-hoshino-35b-20261014-210036.json`
e log correspondente. SHA JSON:
`b3c1a90a66898961388795b82bde0525c2db76ac90faf2435ffe65fc448c953b`.
SHA probe: `b9b65b27a7dd9b11d2f68f67abe7f05f21e2b8ede07d92f463d5d773fa4a519b`;
SHA professor: `21be8163a6636221dc2e0ea64e291e7ddf98d276149f1f855ff8a849880b13be`.
Perfil e binário iguais ao ensaio anterior; métricas guardam seus hashes,
seeds, prompts/turnos e contrato de saída. Conteúdo privado fica fora do Git.
Backup pequeno dos dois arquivos antes de editar em
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/mentoria-transferencia-20261014/codigo-antes.tar.gz`.

## Parecer

Continuar com o 35B enquanto conciliamos ambiguidade de contexto, calibramos
revisão e construímos bons exemplos. Um RP 9B merece comparação limitada;
um 9B especializado com bons dados é alternativa plausível e controlável.
Nenhum foi aprovado nesta rodada. Mais dados ruins ou mais horas de treino
não substituem esse trabalho. **Geração autônoma de corpus de personalidade
ainda não homologada.**
