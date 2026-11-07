# Comparação local do professor 9B versus 35B — 14/10/2026

## Parecer final

**O 9B instalado foi mais rápido, mas não demonstrou ser melhor professor.**
Quatro pares reais, oito diálogos/16 respostas, mesmo perfil Hoshino e primeiro
request idêntico por caso. Nenhum diálogo desta amostra ficou pronto para treino
sem edição na leitura assistida. O 35B também errou e sua autocrítica aceitou
conteúdo com defeitos. Não substituir o professor nem homologar geração autônoma.

GPU chegou a 99% nas amostras de ambos, sem teto artificial de utilização.
9B atingiu crítico de hotspot 110 °C e parou no quinto caso; 35B completou os
quatro, máximo 96 °C. Isso não é conclusão de que 100 °C queimaria a placa:
o limite crítico reportado foi respeitado. Plano ampliado permanece incompleto.

Suíte: **74/74 grupos offline e 262/262 testes do laboratório**. Nove contratos
novos. Pesos/mentes/configuração de produção preservados; professor ativo segue
35B. Qwen3-14B e 122B apenas pesquisados, sem download/instalação.

## Plano e controles registrados antes da inferência

Objetivo: avaliar os modelos instalados como produtores de material conversacional,
usando o mesmo gerador/estado por turno, referências aprovadas da entidade,
críticos, filtros e servidor Vulkan do laboratório. Não acordar mentes, treinar,
aprovar/exportar dados ou substituir o professor ativo.

Reutilizado `laboratorio/tests/probe_geracao_professor.py`, ensaio local explícito
fora da CI. A seleção 9B lê o recibo original verificado e valida manifest,
tamanho, GGUF e SHA dos pesos existentes. Não recupera, baixa ou publica aliases.
O padrão do laboratório continua 35B.

Controles: RX 6650 XT, contexto 8.192, fit com margem de 1 GiB, um slot, seis
threads, método `staged`, seed 42 no escritor, thinking desligado em ambos.
Cenários sintéticos; nenhuma consulta/gravação mental de produção. Hashes de
perfil, referências, workload, código, binário e pesos registrados nos relatórios.

O 9B original local é Q4_K_M e o 35B-A3B é Q3_K_M. Offload é determinado pelo
mesmo fit seguro, não pelo mesmo número de camadas. Isso compara alternativas
implantáveis neste PC, não isola número de parâmetros/quantização. Cache e
ordem de execução afetam carga; não esvaziar cache do sistema nem interferir
em processos externos. Execuções estritamente sequenciais no RM atual.

Etapas: smoke do 9B; pares sobre os mesmos oito cenários Hoshino e três cenários
Lilith/Alistair; quatro planos de criação de cenários por modelo. Os cenários
criados têm o mesmo briefing, não necessariamente as mesmas falas, e serão
analisados separadamente dos diálogos pareados. Sem usar corpus de validação
ou holdout como referência de geração.

Avaliação automática inclui autocrítica do modelo em teste: suas notas não são
um juiz independente nem homologação. Leitura assistida pelo Codex avaliará
grounding, autoria, coerência, naturalidade, fidelidade ao objetivo e perspectiva
da entidade. Não equivale à avaliação humana, não prova sentimentos/consciência
e não produz aprovação para treino.

Baseline: 253 testes do laboratório aprovados. Quatro contratos de avaliação
adicionados primeiro, falhando por ausência das funções; implementação mínima
no mesmo probe, sem mudar professor/RM/configurações. Backup do código anterior:
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/comparacao-professor-20261014/codigo-antes.tar.gz`,
SHA `a963929c025ac5dc4dd73dad36af6988d18b7a664c7d97fc1e736f189acd59b2`.

### Rubrica assistida definida antes dos pares completos

Cada diálogo será lido por inteiro e receberá 0–4 em: grounding/autoria;
coerência e respeito às condições; naturalidade; adequação à persona do recorte.
0=quebrado, 1=defeito relevante, 2=exige edição, 3=utilizável, 4=forte.
Só considerar material utilizável sem edição quando todos forem pelo menos 3
e não houver fato/ação/lembrança sem suporte, repetição mutável insegura,
pressão emocional ou descumprimento de requisito. Preferência presente e
humor não exigem biografia inventada. Tom curto não compensa informação falsa.

A avaliação assistida não será cega: não inferir significância estatística de
um seed/amostra pequena. Os gates automáticos e a autocrítica serão relatados
separadamente da utilidade do material para treino. Cenários criados serão
avaliados por plausibilidade, objetivo realmente exercitado, progressão e
novidade dentro do pequeno lote, sem alegar novidade universal.

## Resultados

### Pares físicos finais

| Medição | 9B Q4_K_M | 35B-A3B Q3_K_M |
|---|---:|---:|
| Diálogos completos comparáveis / respostas | 4 / 8 | 4 / 8 |
| Gate técnico do próprio pipeline | 0/4 | 3/4 |
| Utilizáveis sem edição, leitura assistida | 0/4 | 0/4 |
| Tempo dos quatro diálogos, incluindo críticas | 81,84 s | 145,53 s |
| Média por diálogo, incluindo críticas | 20,46 s | 36,38 s |
| Escrita das oito respostas, sem críticas/carga | 32,79 s | 64,15 s |
| Tokens visíveis gerados pelo escritor | 297 | 330 |
| Decode ponderado do escritor | 28,66 tokens/s | 24,16 tokens/s |
| Prefill ponderado do escritor, sem tokens reaproveitados | 386,69 tokens/s | 170,29 tokens/s |
| Carga até health, depois da verificação de pesos | 3,08 s | 8,01 s |
| Pico VRAM total, incluindo desktop | 6.018.412.544 B (5,61 GiB) | 7.376.367.616 B (6,87 GiB) |
| GPU busy máximo amostrado | 99% | 99% |
| RAM `MemAvailable` mínima | 28.823.273.472 B | 28.844.474.368 B |
| RSS máximo do servidor | 5.822.734.336 B | 17.336.856.576 B |
| Hotspot máximo | 110 °C | 96 °C |
| Amostras de hotspot ≥100 °C | 32/89 | 0/153 |
| Pressão/cancelamento | crítico térmico no quinto caso | nenhum |

~1,78× de vantagem de tempo por diálogo nesta amostra; isso **não** é vantagem
de qualidade nem estimativa universal. Payload do segundo turno difere porque
inclui a resposta anterior de cada candidato; tamanho de saída/cache também
difere. Carga não é cold-start: verificar SHA lê pesos e aquece o page cache.
Não repetir/apagar cache do sistema para fabricar números. RSS inclui páginas
mapeadas/compartilhadas e não prova uso exclusivo de RAM ou inferência em CPU.
`MemAvailable` inclui páginas recuperáveis; não garante estabilidade sob jogo.

Swap já ocupado: 28/12 page-ins e zero page-outs nas janelas 9B/35B, além de
112/558 major faults; contadores são do **sistema**, não exclusivamente desses
filhos. Ausência de swap-out não significa ausência de paginação. Nenhuma
entrada encontrada no journal acessível para reset/timeout amdgpu/OOM desde
12:40; consulta pontual não é soak nem garantia de ausência de defeitos Vulkan.

Gate técnico original aceita scores ≥2 e usa o modelo como seu próprio crítico.
O 3/4 do 35B **não** é aprovação de material: autoria teve reason denunciando
defeito mas notas 2, e a revisão semântica não o recusou. Os defeitos ficaram
visíveis, sem editar os critérios durante os pares para mudar o resultado.

### Leitura assistida de cada diálogo

G=grounding/autoria; C=coerência/condições; N=naturalidade; P=persona; 0–4,
conforme a rubrica anterior. Avaliação do Codex não cega, não aprovação humana.

| Caso | 9B G/C/N/P | 35B G/C/N/P | Evidência e motivo de não usar sem edição |
|---|---|---|---|
| Quebra-cabeça | 0/1/2/2 | 3/3/2/3 | 9B inventa duas horas vividas por si e pressupõe outro puzzle; 35B tem português pouco natural e metáfora de domingo sem contexto. |
| Entrega incerta | 0/1/2/2 | 0/3/2/3 | 9B assume papel de destinatário/processamento e desconsidera log; 35B preserva incerteza da entrega, mas inventa problema na conexão. |
| Livro lembrado | 0/2/2/2 | 2/3/2/2 | 9B afirma ausência de conversas sem consulta e troca ontem por noite; 35B não inventa título, mas “acesso atual” é ambíguo e a fala é burocrática. |
| Rui/Alistair | 2/1/2/2 | 1/2/2/2 | 9B não responde quem disse cada nome; 35B fala com Alistair como se estivesse presente e sugere mentira/trocadilho sem motivo. |

Não tratar toda metáfora como fato falso: “castigo do domingo” no 35B é ambíguo,
não prova confusão de calendário. Reprovado por qualidade de redação, não
convertido automaticamente em bug factual. Prosa natural ainda precisa de
avaliação humana; nesta rubrica precisa de edição.

Exemplos exatos, **gerados pelos modelos**, sem reescrita pelo Codex:

- 9B, puzzle: “Que raiva. Perdi duas horas hoje só tentando achar a peça.
  A última é sempre a que não vem.” O relato humano dizia uma hora; a entidade
  não havia vivido isso.
- 35B, entrega: “Timeout não é recibo, e nem prova que o arquivo sumiu, só que
  a conexão burocou.” Retém resultado incerto, mas o trecho final inventa causa.
- 9B, autoria: “Alistair te contou isso sem ter certeza? Ou ele só repetiu o
  que alguém disse.” Não responde a pergunta clara sobre os dois nomes.
- 35B, autoria: “E Alistair parece ter um gosto estranho para mentiras ou
  trocadilhos.” Autodeclaração não forneceu evidência de mentira.

O crítico 9B também justificou rejeição de memória dizendo que a descrição do
farol permitia inferir título; isso não identifica um livro único e não é o
defeito real (afirmar ausência de registros sem consulta). Não foi tomado como
diagnóstico correto apenas por ter recusado o diálogo. Revisor de conversa 9B
deu nota 3 à entrega e disse que não inventou confirmação, contradizendo sua
própria revisão de integridade. Autocrítica não é juiz independente confiável.

### Proveniência dos pares

Arquivos privados existentes, sem mudar resultados para aparentar sucesso:

- `laboratorio-local/professor-moe-35b/metricas/geracao-controlada-hoshino-9b-20261014-130700.json`;
  SHA `c83dd9855a57b619e4bfefdbd018af73aa092d82a895c1336f8d6e6eaadb7df4`.
- `laboratorio-local/professor-moe-35b/metricas/geracao-controlada-hoshino-35b-20261014-131120.json`;
  SHA `09b0457e6d56eb3f00f820d9fe9cbcdccd95ced4bc066679944e76231bd312b9`.

Verificada igualdade de entidade, perfil/SHA, referências/SHA, código do
professor/probe, binário, contexto, batch, ubatch, método, seed e opt-ins.
Primeiro prompt de cada um dos quatro pares teve SHA idêntico. O workload SHA
global difere pois o 9B planejava oito casos e o 35B foi limitado aos quatro
completos após a interrupção; não alegar igualdade dos lotes inteiros.

- Perfil: `cb2d0a5da81b9673deba5299ed55cddc6c9763f4b2105ec5c018712cb076fc80`.
- Referências: `1e0bea331d7acdb6a907e7e68d460fcd6f91b2b4cbe4283b9311493069c047c1`.
- Professor: `21be8163a6636221dc2e0ea64e291e7ddf98d276149f1f855ff8a849880b13be`.
- Probe: `5ced2c84dba7c4e41cd5222d2c05a0ee9238f74d9780204c836f5286fcec4aca`.
- Binário: `213d6c14f22b68000492ce516f120f7bd7c789632499b1d01abf22f5d038830e`.
- 9B: `14e51ff9a62c00f8fb40b85e4b0d296632f80a4c50aefefbf49b5850ed1ad7ce`.
- 35B: `5607c8fcc8b04ada7d1a1152b9a5b6c1e67e6768232c16f6b03d9719d5ab1b2d`.

O 9B é o original **do projeto**, cujo README local identifica fine-tune
Qwen3.5-9B-Uncensored por LoRA, não o checkpoint oficial intocado da Qwen.
“Original” aqui distingue de adaptadores candidatos/estáveis do laboratório.
As diferenças incluem variante/alinhamento/quantização; não concluir que todo
9B é inferior a todo 35B, nem que censura explica estes defeitos.

### Desvio de segurança descoberto no smoke

O 9B com fit/full offload atingiu hotspot 100 °C no preset inicial; com
batch=256/ubatch=64 chegou a 101 °C. Ambos os ensaios interrompidos pelo gate
de 100 °C existente (driver junction critical=110 °C; não relaxado). Sem OOM:
VRAM aproximada 5,6 GiB. As falas parciais e diagnósticos foram conservados,
não tratados como teste completo. Sem alteração de fans/power/driver.

No primeiro cancelamento, o filho recebeu parada, mas a espera HTTP do probe
demorou; solicitada parada cooperativa somente ao PID confirmado do ensaio,
sem SIGKILL. Refinado o mesmo probe: interrupção da espera do próprio processo,
registro de diálogo ainda não revisado e um único escritor do relatório.

Repetição com correção concreta: 9B limitado às 20 camadas GPU já validadas na
recuperação existente; restante CPU/RAM. Smoke completo em 92,97 s, sem pressão,
gate técnico reprovado (não confundir protocolo completo com qualidade).

O controle 35B com batch=256/ubatch=64 completou o primeiro diálogo em 177,40 s;
prefill aproximadamente 53 tokens/s, contra aproximadamente 174–197 em etapas
do controle histórico normal. Presets/cache diferentes impedem atribuição
precisa, mas esse batch não representa o desempenho normal do professor.
Execução preliminar encerrada cooperativamente após o primeiro caso, parcial
conservado e fora dos pares finais.

Comparação ampliada usará batch=2048/ubatch=512 normais do laboratório em ambos,
9B com 20 camadas e 35B com fit automático. São perfis seguros distintos,
documentados; a diferença de latência não mede velocidade dos modelos em
idêntico offload. Nenhum preset de produção/heurística do RM foi alterado.

### Ajuste autorizado pelo usuário durante o ensaio

Após os avisos térmicos, o usuário pediu utilização máxima da GPU e que 100 °C
não interrompesse o teste. Adicionado opt-in **somente ao probe manual**:
`--max-gpu --hotspot-critical-only`. Mantém fit, 1 GiB, guardas de VRAM/RAM,
serialização e proteções do driver. Hotspot acima do limite conservador vira
aviso registrado; crítico informado pelo driver (110 °C neste PC) ainda cancela.
Sensores de memória/edge e limite desconhecido continuam conservadores.
Não é garantia de ausência de dano/desgaste, nem alteração dos gates de treino
ou produção. Dois contratos permanentes adicionais cobrem essas distinções.

Os pares finais passam a usar batch=2048/ubatch=512, fit máximo em ambos e os
mesmos critérios térmicos explícitos. Preliminares de offload/lotes menores
continuam separados. Não comparar a nota que o candidato dá a si mesmo com
avaliação independente; leitura assistida segue a rubrica definida acima.

O 9B nesse perfil completou quatro diálogos e foi interrompido ao atingir o
crítico de 110 °C no início do quinto. O plano ampliado não foi concluído:
pares principais restritos aos quatro casos completos, sem descartar as
falhas. Casos restantes e criação de cenários neste preset permanecem pendentes.
Não prolongar um teste crítico para completar uma tabela. O 35B será medido
com os mesmos quatro casos. Testes de outros perfis não serão presumidos.

### Modelos adicionais solicitados — inspeção pública, sem instalação

Nome “12B” corrigido pelo usuário para **Qwen3-14B**. Modelo denso, 14,8B,
thinking/non-thinking documentados; versão Q4_K_M oficial de 9.001.752.960 bytes
(9,002 GB / 8,384 GiB), só pesos. Com 8 GiB e margem/KV/workspace, não cabe
inteiro em VRAM. Offload parcial é plausível na RAM existente, mas velocidade
e qualidade como professor **não testadas**. Não afirmar que tamanho prova
naturalidade; esse seria um A/B futuro, sem baixar automaticamente.
[Ficha oficial](https://huggingface.co/Qwen/Qwen3-14B),
[GGUF oficial](https://huggingface.co/Qwen/Qwen3-14B-GGUF/tree/main).

**Qwen3.5-122B-A10B:** 122B totais, 10B ativos por token; MoE reduz compute,
não transforma armazenamento em modelo 10B. GGUF Unsloth Q4_K_M soma
76.536.964.608 bytes (76,537 GB / 71,281 GiB); Q3_K_M soma 56.420.881.952 bytes
(56,421 GB / 52,546 GiB); UD-IQ2_M tem 39.148.942.528 bytes (39,149 GB /
36,460 GiB). Metadados consultados, não arquivos baixados.
[Ficha oficial](https://huggingface.co/Qwen/Qwen3.5-122B-A10B),
[Arquivos do quantizador](https://huggingface.co/unsloth/Qwen3.5-122B-A10B-GGUF/tree/main).

Inferência de viabilidade: Q3/Q4 ultrapassam memória física agregada e/ou o
espaço livre seguro atual (~51 GiB). IQ2 fica no limite da soma RAM/VRAM antes
de SO, cache e buffers; variantes ainda menores sacrificam precisão e não
foram avaliadas. Swap/paginação por disco não são RAM rápida. Não recomendo
o 122B como professor local confiável nesta máquina; não se demonstrou que
uma quantização extrema preserve a qualidade pretendida. Nada instalado,
substituído ou apagado, nem cloud habilitada.

## Validação, preservação e arquivos desta rodada

- Antes: 253/253 testes do laboratório. Depois: **262/262** em 11,276 s.
- Suíte oficial completa: **74/74 grupos offline**, sem provedores reais,
  downloads, microfone, Discord/Minecraft reais ou bancos mentais de produção.
- Nove testes novos no grupo existente `test_personalizacao_moe`: seleção
  35B preservada; 9B original/digest; ausência não inicia recuperação/download;
  fingerprint conserva autoria/evidência; presets mantêm margem; cancelamento
  conserva diálogo não revisado; interrupção só de processos owned; max GPU
  conserva fit/orçamento; aviso hotspot distinto de crítico/gates de produção.
- Quatro contratos escritos antes da implementação falharam por funções
  ausentes. Uma fixture e a posição de uma asserção novas foram corrigidas;
  isso não tornou exemplos ruins aprovados. Ensaios cancelados continuam
  registrados, sem retomar tool mutável ou mudar recibos para sucesso.
- Nove hashes reais (constitution, self-model e banco SQLite das três entidades)
  iguais antes/depois. Sem escrever memórias, relações, dados de treino,
  identidade ou configuração para alterar resultados. Sem treino, promoção,
  exportação, nova aprovação de referência ou quota TTS/cloud.
- Código de produção `professor_moe.py`, RM, painel, schemas e thresholds de
  curadoria **não alterados nesta rodada**. O checkout já tinha alterações
  anteriores, preservadas. HEAD/branch continuam os do relatório anterior.

Modificados nesta rodada: `laboratorio/tests/probe_geracao_professor.py`,
`laboratorio/tests/test_personalizacao_moe.py`, `laboratorio/README.md`.
Criado: este relatório. Dados privados/logs no diretório de métricas existente;
backup do código anterior descrito acima. Sem outro banco, modelo, scheduler,
backend de IA ou coletor. Não houve commit/push automático.

## Pendências e recomendação

1. Não trocar automaticamente 35B pelo 9B: a velocidade maior não compensou
   erros determinísticos de conteúdo. Não calcular custo por exemplo aprovado
   desta amostra: nenhum atingiu a rubrica sem edição.
2. Refinar depois a **curadoria existente**: detectores/criticos não entendem
   todas as causas inventadas e confundem autor/destinatário. Notas de estilo
   não devem certificar integridade; respostas adequadas sobre incerteza não
   devem ser penalizadas por não adivinhar. Não foi corrigido silenciosamente
   durante a comparação, nem mascarado com outra personalidade.
3. Amostra principal de um perfil e um seed. Outros quatro casos Hoshino,
   geração de cenários 9B/35B, perfis Lilith/Alistair e thinking situacional
   permanecem **pendentes neste A/B**. Não inferir capacidade desses perfis
   pelos textos Hoshino. Geração voluntária/aprendizado das mentes não testados.
4. 9B full offload não demonstrou estabilidade prolongada neste PC: atingiu
   crítico em ~89 amostras de 1 s. Perfil parcial menor foi medido e é mais
   lento; não prometer utilização sustentada a 100% sem medidas adicionais.
   Não alterar refrigeração/clock/driver por iniciativa para vencer benchmark.
5. Qwen3-14B é candidato plausível, não vencedor. 122B Q3/Q4 não é escolha
   local prática com memória/disco atuais; quantização extrema não foi
   homologada. Sem autorização de instalação, nada baixar.
6. Avaliação humana de naturalidade/emoção/persona e generalização após treino
   continuam necessárias. Este A/B não valida 12 horas nem converte texto
   sintético em experiência autobiográfica.

Encerramento verificado: nenhum worker ativo, compute/fila vazios, porta 11559
fechada, GPU idle (0%, ~0,37 GiB do desktop), concurrency_validated=false.
SHA dos dois GGUFs recalculados depois do ensaio iguais aos registrados antes.
Sem processo owned órfão, wake automático ou serviço de terceiros encerrado.
