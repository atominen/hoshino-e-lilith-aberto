# Revisão noturna e RAM compartilhada — 09–10/10/2026

## Arquitetura e escopo do incremento

Continuação limitada da Fase 2 do plano cognitivo. O histórico bruto, as
identidades e os bancos existentes permanecem preservados. Não implementar
outro cache, scheduler, backend ou diário nesta rodada.

Fluxo implementado: `night_reflection.preparar_material` lê os registros atuais
com limites explícitos → `prompt` usa esse mesmo recorte → inferência existente
P5 → `salvar` guarda a referência ao recorte no campo `reflections.evidencias`.
`main.talvez_refletir_noturno` conserva o material entre a consulta e a gravação;
não consulta novamente o banco para inventar a evidência depois da resposta.

Reutilizar `bd`, SQLite mental, diagnósticos e recuperação de `reflection`.
Material composto de registros inteiros, sem cortar conclusões/episódios no meio.
Exclusões por orçamento e limites de linhas ficam explícitas. Registro grande
demais pode ficar de fora; isso não equivale a prova de ausência nem a revisão
completa. Falha de leitura ou resposta sem conclusões válidas não marca sucesso.

O vínculo é com o **contexto fornecido**, não certificação de que cada conclusão
do LLM é verdadeira ou foi sustentada por todas as fontes. Categoria permanece
`reflexao`. APIs antigas de material/prompt e gravação sem evidência estruturada
continuam legíveis; nenhuma migração de evidências antigas.

Consumidores mapeados antes das alterações: `main` chama prompt/salvar;
`reflection.ultimas` e `bloco_para_prompt` recuperam `evidencias` pelo formatador
existente; Central inspeciona as linhas; manutenção usa IDs. Testes de reflexão,
integridade, persistência, capacidades e reset usam esses contratos. O escritor
JSONL não fornece ID em todos os eventos: usar arquivo/linha/hash real, não criar
message ID fictício. Não há afirmação de snapshot causal global entre SQLite,
JSONL e outros processos.

## RAM — opinião e evidências iniciais

RAM é útil para cache, staging e offload parcial. Não se deve somar sua capacidade
à VRAM como se tivessem a mesma velocidade. [HIP/AMD](https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_runtime_api/memory_management/unified_memory.html)
documenta acesso compartilhado/mapeado, dependências de suporte e transferência
de dados. [Khronos](https://docs.vulkan.org/guide/latest/memory_allocation.html)
descreve a memória dedicada e o custo do caminho PCIe nas GPUs discretas.

Leitura física inicial: aproximadamente 31 GiB RAM, 25 GiB disponíveis; swap
8 GiB, 3,4 GiB ocupados. Nos dois intervalos curtos de observação não houve
swap-in/out; isso não comprova estabilidade prolongada. O driver expõe cerca de
7,98 GiB VRAM e 15,61 GiB de orçamento GTT, dos quais cerca de 0,16 GiB estavam
ocupados. **GTT não é VRAM física extra e não comprova inferência sobre pesos
remotos.** A coluna `shared` de `free` tampouco é essa reserva de GPU.

Logs reais anteriores do runner Hoshino mostram ROCm, buffer CPU_Mapped de
683,55 MiB, buffer ROCm0 de 4.674,33 MiB, KV 256 MiB e compute 111,39 MiB.
Confirmam buffers distribuídos, não GPU calculando diretamente sobre todos os
pesos mantidos em RAM. Cache configurado em 8.192 MiB é limite, não alocação
atual. Não executar inferência nem alterar perfis nesta rodada.

Antes de adotar zero-copy no runner real: comparar o mesmo modelo/prompt/saída
com offload atual, medindo primeiro token, tokens/s, RAM/VRAM, swap e falhas.
Mantenho VRAM 8 GiB, margens existentes e concorrência desativada. RAM aumenta
possibilidades, mas não há ganho de latência demonstrado nesta rodada.

## Validação

Baseline: 74/74 grupos offline, saída 0. Novas regressões executadas antes da
correção: 16 métodos, 6 antigos verdes e 10 novos vermelhos (5 falhas, 5 erros
pela ausência do contrato de preparação). Logs privados em
`compartilhado/runtime/ensaios/20261009/reflexao-evidencias/`.

Resultado final: **74/74 grupos offline**, sem grupo em falha, registrado em
`suite-final.log`, depois da guarda de isolamento do recorte. A rodada completa
intermediária também passou 74/74 (`suite-depois.log`), mas não é o baseline final.
O diretório/nome deste relatório mantém a data de início da rodada; fechamento
em 10/10/2026.

## Correções implementadas

1. Episódios agora fornecem ID, horário integral, resultado, sucesso/falha,
   fonte e contexto/autoria existente. Antes o resultado era consultado, mas
   não enviado; ID/contexto sumiam e o offset era retirado da apresentação.
   Não presumir autor quando o legado não o registrou.
2. Categorias disputam o mesmo orçamento em rodadas, por registros inteiros.
   Nenhuma fonte toma silenciosamente o espaço de todas as outras. O teto de
   caracteres permanece o configurado, com mínimo legado de 1.000; ele limita
   **material**, não o prompt de identidade nem tokens. Limites de linhas são
   sinalizados, com contagem de exclusões conhecidas pelo orçamento; não é
   contagem exata de todo o histórico fora dos limites de consulta.
3. Consultas mentais passam a falhar explicitamente; JSONL ilegível também.
   A noite não é marcada como vazia/concluída nessas falhas. Leitura de eventos
   mantém só a janela existente de 300 linhas em RAM, embora ainda percorra o
   arquivo diário. Hash do evento é dos bytes da linha, excluindo terminador,
   mesmo quando a exibição precisou substituir UTF-8 inválido.
4. O recorte que chegou à inferência acompanha a gravação. Registro novo que
   aparece enquanto o modelo responde não é anexado retrospectivamente como
   evidência. Envelope contém entidade, dia, instante de referência, fontes
   selecionadas, seus metadados disponíveis, hashes e limites, mais o motivo.
   Referência de outra entidade é recusada no prompt e na gravação.
5. `reflections.evidencias` preserva o envelope no próprio banco existente.
   Recuperação automática apresenta até oito referências resumidas, explicita
   as demais e fornece o ID para inspeção do registro integral. A recuperação
   não reinjeta todos os contextos antigos. Tipo continua reflexão, confiança
   ausente continua explicitamente ausente/default, não confirmação factual.
6. Nenhuma conclusão válida → não marcar conclusão da noite. Conclusão maior
   que os 700 caracteres já previstos é recusada inteira, não cortada e
   salva como se estivesse completa. Exclusões por tamanho/limite de 12 são
   diagnosticadas sem texto do conteúdo; conclusões válidas restantes podem
   ser salvas. Isso é processamento parcial, não prova de que todo material
   foi aprendido.
7. Ordenação de memórias, procedimentos e contatos usa os comparadores de
   instantes já existentes, com ID como desempate, sem reescrever legado.
   Material diário de episódios/emoções/eventos mantém os limites do dia e
   teto temporal da rodada anterior.

O envelope registra **origem do contexto**. Não contém a íntegra imutável de
todos os registros consultados, nem vínculo semanticamente comprovado de cada
conclusão com uma fonte. Hash ajuda a detectar alteração posterior da versão
representada, não recupera sozinho um registro modificado. Não persiste cadeia
de raciocínio ou cache de execução como memória autobiográfica.

## Arquivos desta rodada

- [night_reflection.py](</home/gustavo/hoshino e lilith/app/mind/night_reflection.py>): preparação/limites/proveniência/compatibilidade.
- [main.py](</home/gustavo/hoshino e lilith/app/main.py>): conservar recorte e não declarar sucesso em falhas.
- [reflection.py](</home/gustavo/hoshino e lilith/app/mind/reflection.py>): prévia explícita da evidência na recuperação.
- [test_reflexao_noturna.py](</home/gustavo/hoshino e lilith/testes/test_reflexao_noturna.py>): 14 métodos novos; fixture compartilhada pelos testes antigos sem duplicar sua execução.
- Este relatório é o único documento novo. Nenhum grupo oficial novo.

## Regressões e preservação

**20/20 métodos** do grupo noturno, sendo 6 anteriores e **14 regressões novas**,
mais o smoke legado. Integridade: **15/15**. Persistência: **17/17**. Todos em
isolamento oficial, SQLite e arquivos temporários, inferência simulada.

Cobertura nova: ID/autoria/resultado/offset; orçamento e fonte gigante; tipo e
confiança zero; recorte estável durante resposta; fonte JSONL verificável;
falha de tabela/leitura; limite de linhas; material que não cabe; resposta
inválida; recuperação compacta; UTF-8 inválido; conclusão longa; origem de outra
entidade recusada. Strings de evidência antigas continuam legíveis sem migração.

Falhas de desenvolvimento não ocultadas:

- Primeira execução: 5 falhas determinísticas e 5 erros da API nova ausente.
- A própria ampliação inicial expôs reinjeção excessiva: 16.630 caracteres em
  uma reflexão do ensaio isolado; adicionada regressão e corrigido o leitor.
- Hash calculado após decodificação não correspondia a bytes UTF-8 inválidos;
  reprodução e correção para leitura binária sem reescrita do arquivo.
- Conclusão longa era cortada/salva; regressão vermelha antes da recusa inteira.
- Novo envelope não recusava contexto de outra entidade; guarda adicionada após
  regressão vermelha. Não houve vazamento de banco real nesse teste.
- Persistência ainda emite `ResourceWarning` de conexões SQLite não fechadas
  durante seus testes. Não foram suprimidos nem corrigidos neste incremento;
  suíte verde não demonstra ausência de leaks em todos os consumidores.

Snapshots consistentes dos três bancos pela API de backup SQLite, fonte aberta
somente para leitura, e arquivos de código pré-incremento estão no diretório
privado ignorado pelo Git. Comparação dos dumps lógicos após alterações: originais
e snapshots idênticos, `quick_check=ok` nos seis arquivos:

| Entidade | SHA-256 lógico |
|---|---|
| Hoshino | `f9164eba302fb5eb2884945877e390b8ae95a256698b2f2b4afd864c9edf8ae7` |
| Lilith | `aad72056ccb4a82567319f2d714118b80fea27f32d63d312194a8fb765498aec` |
| Alistair | `9212718395f40f66eadffd19d39450b299c816a60e31233a37fef6ba54120914` |

Nenhum modelo removido/trocado, banco migrado, personalidade editada, entidade
acordada, serviço reiniciado ou provider pago chamado. Alterações anteriores da
árvore suja foram preservadas. `git diff --check` sem erros.

## Limites e próximos pontos

- Ainda é revisão limitada, não resumo semântico incremental que garanta visita
  posterior a todos os registros omitidos. Esse processamento restante, diário
  voluntário/ACL, aprendizagem causal e oficina visual seguem pendentes.
- Registros grandes demais ficam fora; quando nenhum cabe, há falha explícita,
  não sucesso vazio. Não foi medido volume enorme de registros/JSONL; teto de
  contexto não equivale a limite rígido de RAM das consultas.
- SQLite e marcador JSON de noite concluída não formam uma transação única.
  Persistência de reflexão seguida de falha do marcador ainda precisa de
  auditoria de idempotência/recovery; não prometer exactly-once.
- Falhas deixam a revisão pendente; backoff e contenção de tentativas continuam
  sujeitos ao ciclo existente. Não afirmar orçamento de inferência prolongada
  ou iniciativa diária validado por mocks.
- Não há teste novo de personalidade, consciência/sentimento, Discord,
  Minecraft, GPU, providers ou convivência física prolongada nesta rodada.
- A segunda leitura física encontrou cerca de 24 GiB disponíveis, VRAM usada
  0,89 GiB e GPU busy 0%; swap ocupada continua 3,4 GiB sem entrada/saída nos dois
  intervalos. É snapshot curto enquanto rodavam testes offline, não benchmark
  de LLM, cache ou acesso GPU direto à RAM.
- Memória de execução compartilhada não autoriza compartilhar memórias mentais
  de entidades. Pesos/cache, histórico e contexto/estado de cada entidade têm
  contratos diferentes. Nenhuma deduplicação de pesos/cache foi implementada.

Para carregar o código novo, restart cooperativo posterior; não executado aqui.
Reversão deve retirar somente este incremento, sem restaurar bancos por cima dos
originais ou reverter alterações anteriores. O leitor legado continua disponível.
