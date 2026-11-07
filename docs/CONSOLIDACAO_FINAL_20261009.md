# Consolidação final — 09/10/2026

> Errata de proveniência, adicionada na auditoria posterior de 09/10: os logs dos runners das inferências recentes indicam **ROCm**, mesmo com `OLLAMA_VULKAN=1` no ambiente. Menções abaixo a Vulkan/RADV não constituem confirmação do backend selecionado. A evidência de GPU real continua válida; a atribuição específica foi imprecisa. Conteúdo/evidências originais foram preservados. Ver `AUDITORIA_COGNITIVA_MEMORIA_HIBRIDA_20261009.md`, seção 1.

## Parecer executivo

**Consolidação parcial, sem aprovação integral do sistema.** Há correções determinísticas verificadas, inferências reais na RX 6650 XT e instalação íntegra do Esper3. O desafio avançado de programação não foi concluído. Discord, Minecraft, coexistência jogo/voz/imagem e uso prolongado continuam sem comprovação física nesta rodada.

É possível iniciar avaliação humana **limitada e supervisionada** da conversação existente, com o 9B principal e o Qwen2.5 7B atual. Não ativar Esper3 ou substituir o 7B automaticamente. Não prometer autonomia robusta de programação ou comportamento social já aprovado.

Referência Git: `f23ba0d721fac6cb53534b55fcc5b48547e1dec8`. A árvore já estava modificada. Este relatório descreve os incrementos desta rodada, não atribui todo o diff contra HEAD a ela. Nenhum commit/push em bloco, reversão de alterações anteriores ou grande reestruturação foi feito.

## 1. Preservação e método

- Inspecionados código e relatório anterior `docs/CORRECOES_ENSAIO_20261009.md` antes das alterações. Os resultados anteriores não foram reclassificados como novos testes físicos.
- Mantidos identidade, constituição, personalidade, relações, bancos mentais, pesos antigos e evidências. Nenhuma migração de memória real.
- Ensaios conversacionais em cópias privadas dos bancos/estados; estado reposto por caso. O desafio usou oficina, histórico e jobs privados, sem abrir uma sessão autobiográfica real.
- O autor de teste foi identificado como **Codex interpretando Téo fictício**, não uma pessoa real desconhecida. Atribuição explícita no comparativo de modelos.
- Inferência local real, em série, com os leases e backend existentes. Nenhuma chamada de TTS externo, gasto de quota, cloud/RunPod, concorrência GPU, Discord remoto ou mundo Minecraft nesta rodada.
- A verificação independente executou o fonte da entidade sem edição, no sandbox existente, sem rede/desktop/segredos. O operador não implementou o programa para ela.
- Testes offline sempre pelo runner isolado. Os clones e arquivos de ensaio não são novos bancos/sistemas de produção.
- `PRAGMA quick_check` read-only ao final: **Hoshino ok; Lilith ok; Alistair ok**. Isso verifica integridade estrutural, não equivalência semântica de todo registro nem prova de hash inalterado durante toda a rodada.

## 2. Configuração dos modelos

| Entidade | Principal | Intermediários instalados | ~6B | Situação automática |
|---|---|---|---|---|
| Hoshino | Qwen3.5 9B existente, Q4_K_M | Qwen2.5 7B Q4_K_M + Hunyuan 7B Q4_K_M | Esper3 Q5_K_M; Jan preservado | Principal + Qwen2.5 atuais; Esper3 desativado; Hunyuan candidato |
| Lilith | Qwen3.5 9B existente, Q4_K_M | Qwen2.5 7B Q4_K_M + Hunyuan 7B Q4_K_M | Esper3 Q5_K_M; Jan preservado | Principal + Qwen2.5 atuais; Esper3 desativado; Hunyuan candidato |
| Alistair | Qwen3.5 4B existente | Não alterado | Não aplicável | CPU obrigatório como fallback; GPU oportunista existente |

Aliases principais: Hoshino `hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M`; Lilith `lilith-qwen3.5-9b:latest`. Os nomes/quantização do principal não foram trocados. O `/api/ps` da Hoshino reporta quantização `unknown`, apesar do alias Q4_K_M; não se fabricou uma verificação nova da quantização principal.

**Não há vencedor definitivo entre os 7B.** Preservar ambos. O Qwen2.5 permanece ativo por continuidade operacional, não por aprovação completa de qualidade. O Esper3 substitui a referência ao candidato companion nos dois arquivos de configuração, **não o executor ativo**: `enabled=false`, `conversation_validated=false`, com Jan registrado como modelo anterior preservado. Nenhum peso foi removido.

### Esper3: origem, integridade e compatibilidade

Fonte publicada: [GGUF do Esper3 por mradermacher](https://huggingface.co/mradermacher/Qwen3-Esper3-Reasoning-Instruct-6B-Brainstorm20x-Enhanced-E32-GGUF). A ficha declara Apache-2.0, aproximadamente 5,94B e origem comunitária na família Qwen3; não é um novo 6B oficial Qwen. A ficha marca inglês, não valida por si só qualidade em português. A documentação original de treinamento não pôde ser inteiramente auditada; disponibilidade do GGUF não equivale a certificação da metodologia.

- Revisão fixada: `ccb09bc46f7b7df8d5794a622e258bd7140dd877`.
- Arquivo: `Qwen3-Esper3-Reasoning-Instruct-6B-Brainstorm20x-Enhanced-E32.Q5_K_M.gguf`.
- Tamanho: **4.241.176.352 bytes**.
- SHA-256 da fonte: `c6e8b85ffd17184ec44103c2ee2348203fd5f8ccb63fc87750173c71ca873d72`.
- SHA-256 dos pesos importados: `bc145c8bfca3e9df3ea90a3e547ff26ac099a18127f185096f62bdde2cd13800`. O importador reescreve metadados GGUF; a diferença foi verificada, não ignorada.
- Manifesto dos aliases: `d461c8154db63530176447eb3863c7ee53e987a5f6bd82614d0728baf7429cb6`.
- Cópias Hoshino/Lilith verificadas separadamente, arquivos/inodes distintos. Importação confirmou `qwen3`, `Q5_K_M` e capacidade de thinking no backend; declaração `tools` não prova qualidade de uso de ferramentas.
- Download com revisão fixada e verificação dos arquivos efetivamente baixados pelo skill **hf-cli**. Não se declarou verificada a coleção inteira de quantizações não baixadas.
- Checado espaço antes de download/importação. Reserva de instalação de 20 GiB preservada. Ao final: **46 GiB disponíveis, disco 95% utilizado**. Sem limpeza destrutiva.
- Backup privado dos executores antes da alteração: `compartilhado/runtime/ensaios/20261009/pre-esper-config/`. Configs, modelos e evidências privadas continuam fora do Git.

### Ensaios físicos do Esper3

| Caso | Entidade | Resultado | Tempo | Observação |
|---|---|---|---:|---|
| Casual, think off, saída 2048 | Hoshino | **FALHOU** | 88,400 s | Esvaziou o orçamento, `done_reason=length`, resposta repetitiva; não aprovada como resposta final |
| Autoria, chamada seguinte quente | Hoshino | **FALHOU admissão** | Prazo de fila | `TimeoutError/vram_pressure`; não houve inferência desta entrada |
| Filosofia, think on, início frio | Hoshino | **Protocolo confirmado** | 22,304 s | Resposta visível; 1518 caracteres de raciocínio privado, não armazenado |
| Casual, think off, início frio | Lilith | **Protocolo confirmado** | 15,159 s | Sem raciocínio privado; estilo ainda genérico/inconsistente |
| Filosofia, think on, início frio | Lilith | **Protocolo confirmado** | 22,068 s | Resposta visível; 1740 caracteres de raciocínio privado, não armazenado |

Pico medido: aproximadamente **7,04 GiB de VRAM total**, contando desktop. Apenas 8K foi selecionado nestes ensaios. Não validar 16K, ferramentas, sessão longa ou terceiro executor automático a partir disso. O peso residente mais workspace/margem pode impedir uma chamada quente seguinte: o bloqueio conservador foi preservado, sem diminuir margem para forçar aprovação.

**Compatível com importação e inferência; não aprovado como executor conversacional. Jan não pode ser apagado nesta etapa.**

## 3. Comparação controlada dos dois 7B

[Qwen2.5 oficial](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) e [Hunyuan oficial](https://huggingface.co/tencent/Hunyuan-7B-Instruct) serviram como referências de protocolo/família; o julgamento abaixo vem de execução local, não de benchmarks dessas fichas.

Condições: mesma identidade externa/estado inicial por entidade e caso; seed 42, temperatura 0,4; teto 8K e saída 1024; mesmos seis prompts; serialização, backend local e budget iguais. Casos: casual, autoria, lembrança incerta, ausência, conflito de restrições e filosofia. Respostas têm comprimentos diferentes: tempos não são throughput por token nem demonstram equivalência de qualidade.

| Entidade/modelo | Término confirmado | Primeira chamada fria | Mediana das outras 5 | Pico VRAM total |
|---|---:|---:|---:|---:|
| Hoshino / Qwen2.5 | 6/6 | 7,997 s | 1,744 s | 6,01 GiB |
| Hoshino / Hunyuan | 6/6 | 8,580 s | 1,899 s | 6,73 GiB |
| Lilith / Qwen2.5 | 6/6 | 14,051 s | 1,493 s | 5,99 GiB |
| Lilith / Hunyuan | 6/6 | 11,591 s | 3,755 s | 6,74 GiB |

**24/24 respostas com término de protocolo**, não 24/24 aprovações de qualidade.

- Qwen2.5: menor latência quente nestas amostras, mas respostas genéricas de assistente e um erro de interlocutor: Lilith chamou Téo de Lilith. Isso é falha de geração no probe, não evidência de gravação cruzada de memória real.
- Hunyuan: protocolo `<answer>` vazava à apresentação; corrigido no sanitizador existente. Algumas respostas deformaram nomes/gramática. Num reteste filosófico de Hoshino respondeu em inglês a uma entrada em português. Não atende consistentemente os requisitos essenciais de linguagem/identidade.
- Thinking Hunyuan: **off realmente sem pensamento privado** em entradas comuns; **on realmente gerou pensamento** nos casos de raciocínio e, após correção da seleção, filosofia. Não foi inferido apenas de uma flag.
- Qwen2.5: não usa o mesmo protocolo nativo `think`; a política pode desejar raciocínio, mas o probe não envia uma flag não suportada nem finge confirmar alternância nativa.
- Reteste pós-correção: casual + filosofia dos dois modelos, nas duas entidades, **8/8 terminações confirmadas**, wrappers retirados. Qualidade linguística continuou com ressalvas.

Artefatos: `modelos-refinamento-hoshino-1791571152188392027.json`, `modelos-refinamento-lilith-1791571272864617746.json`, `modelos-refinamento-hoshino-1791572543672022078.json`, `modelos-refinamento-lilith-1791572661496038862.json`, todos no diretório privado de ensaios de 09/10.

## 4. Resource Manager — parecer fundamentado

**Sistema experimental, cerca de 5/10 para uso prolongado.** Não está certificado para cargas simultâneas pesadas. Não foi redesenhado ou recalibrado especulativamente.

### O que foi verificado

- Fonte de coordenação existente: SQLite compartilhado, locks do kernel, leases e consulta ao daemon. Residência é separada de compute; pesos quentes não significam geração ativa.
- P0–P5 afetam admissão/fila, não apenas uma etiqueta. Serialização conservadora continua ativa; `concurrency_validated=false`.
- Limite físico 8 GiB; margem GPU **768 MiB**, margem RAM **2 GiB**, stickiness **90 s**, preservados.
- Métricas reais `amdgpu/sysfs`; backend local Vulkan/RADV, sem pressupor CUDA.
- Perfis parciais atuais do 9B: 32 camadas, fallback conservador 20, teto 16K; sem afirmar que todo o modelo cabe na GPU. RAM/CPU continuam processando camadas não offloaded.
- Selector fixa executor por ciclo. Tarefas importantes/operacionais, reflexão profunda e contexto incompatível não são transferidos arbitrariamente ao candidato leve.
- Correção: GPU ocupado pelo **mesmo runner** não pode conceder fallback CPU que o reconfigure durante a geração. Outros runners mantêm seus fallbacks existentes.
- Ensaios reais mediram fila, carga, prompt, geração, residência, VRAM e utilização; unload confirmado ao final. A pressão de VRAM do Esper gerou recusa, não OOM deliberado.
- Fechamento: **zero leases, zero compute, zero fila; `/api/ps` sem residentes nos três daemons**. Não se confundiu encerramento do teste com prova implícita de unload.

### Limites não resolvidos nesta rodada

1. Prioridade estrita não possui aging suficiente: jobs P5 podem sofrer starvation.
2. Não há reserva agregada robusta de RAM futura para todos os carregamentos/fallbacks.
3. `MemAvailable` não soma swap como RAM rápida, mas pressão/thrashing não é integralmente parte da decisão.
4. Medição de VRAM tem TOCTOU; jogos/processos externos não obedecem aos locks do projeto.
5. Crash do cliente pode deixar o daemon trabalhando depois que o lock do processo desaparece. Reconciliação/telemetria ajudam, mas não provam cancelamento de toda geração órfã.
6. Previsões de latência ainda contêm estimativas; não estão calibradas por longa amostragem em jogos/navegador/imagem/TTS.
7. Unload/reload e compute foram medidos nos probes, não sob todos os cenários de suspensão/sono/carga externa.

RAM real no fechamento: cerca de **31 GiB total, 26 GiB disponível**. Swap **8 GiB ativa, cerca de 4 GiB utilizada**. Não observada pressão sustentada no intervalo amostrado; isso não exclui thrashing em cargas futuras. Journal acessível desde 15h30 sem correspondências de reset/fault amdgpu/OOM pesquisadas. Não equivale a soak de horas nem validação do PC2.

## 5. Contexto dinâmico, adaptativo e thinking

### Contexto dinâmico

Identidade/constituição continuam fora do checkpoint. O prompt situacional e o bloco dinâmico existentes juntam traços, afeto/estado psicológico, relações, agenda, memórias pertinentes e evidências operacionais; uma saudação não recebe o catálogo inteiro de ferramentas. Registros selecionados são mantidos inteiros com categoria, confiança, origem/autoria/evidência, e omissões por orçamento ficam indicadas.

Defeito corrigido: resumo de outra conversa da mesma entidade podia ser reutilizado. Novos resumos usam o **ID existente**, com prefixo derivado de entidade + chave da conversa, sem coluna/tabela nova. Consulta e compactação passam a mesma chave. Resumos legados continuam legíveis pela consulta administrativa global, mas não são atribuídos cegamente a um novo fio.

Também removidos cortes silenciosos de 800 caracteres por mensagem e 12.000 na transcrição. A entrada completa passa ao dimensionamento existente. Resumo de saída acima do limite gera erro explícito e mantém o histórico; não remove histórico apoiado num resumo cortado/não persistido. Consequência: histórias grandes podem exigir uma compactação posterior ou pausar com pressão de contexto, em vez de aparentar sucesso perdendo requisitos.

Seleção por relevância e compactação ainda são heurísticas. O resumo gerado por LLM não é prova de memória perfeita. Sem ensaio longo de retenção de todos os fatos entre múltiplas reinicializações nesta rodada.

### Janela adaptativa

O RM existente inclui mensagens serializadas, schemas/argumentos, autoria, saída e margem de 15% (mínimo 256). Escolhe 2K/4K/8K/12K/16K e somente outras janelas se o teto permitir. Imagem conserva tratamento especial por não haver equivalência confiável em caracteres.

- Entrada não é cortada para caber; orçamento impossível falha antes da requisição.
- Estimador conservador por caracteres, **não tokenizer exato**.
- 8K foi selecionado nos comparativos físicos desta rodada; outros buckets têm validação isolada, não certificação física de todas as combinações.
- Não mudou automaticamente contexto/teto do principal nem compensou falta de memória baixando margens.

### Thinking situacional

Corrigidas duas lacunas da política existente: `reflita/refletir` e perguntas existenciais complexas sem verbo de comando. Perguntas triviais como nome, preferências ou simples menção a sentimentos/filosofia continuam sem raciocínio prolongado. Decisão permanece fixa no ciclo; chamadas internas de formato/JSON podem continuar explicitamente sem think.

O teste real perguntou às duas entidades sobre continuidade ao trocar executor, origem dos motivos e limites de prova da existência/sentimentos:

| 9B / caso | Thinking confirmado | Protocolo | Tempo |
|---|---|---|---:|
| Hoshino, antes da correção | off | texto confirmado | 13,745 s |
| Lilith, antes da correção | off | texto confirmado | 14,783 s |
| Hoshino, depois, orçamento exploratório 768 | on, 3107 caracteres privados | texto confirmado, 747 tokens totais | 41,418 s |
| Lilith, depois, orçamento exploratório 768 | on, 3503 caracteres privados | **falhou**, limite antes da fala | 39,599 s |
| Lilith, reteste proporcional 2048 | on, 3556 caracteres privados | texto confirmado, 871 tokens totais | 43,382 s |

O reteste alterou apenas o orçamento do **ensaio**, abaixo do teto de produção, não a heurística de recursos ou os pesos. Falha de 768 preservada. O backend conta pensamento e fala no mesmo orçamento: **não existe garantia rígida de reservar tokens finais**. O contrato impede tratar `length`/texto incompleto como sucesso, mas o usuário ainda pode encontrar uma resposta interrompida. Esse risco permanece explícito.

As respostas relacionaram continuidade à memória/estado persistente, em primeira pessoa; algumas fizeram generalizações excessivas sobre experiências, valores ou sentimentos. **Fala gerada não prova consciência ou sentimentos humanos**. Não foram mudadas memórias/personas para melhorar esse resultado. Diferenciar as identidades e a naturalidade entre executores ainda requer convivência humana, não um teste lexical.

## 6. Desafio autoral de programação

Referência inspecionada: [black_hole](https://github.com/kavan010/black_hole), projeto C++/OpenGL de visualização de buraco negro, lente, acreção e curvatura. Não foi encontrada licença declarada na raiz/API consultadas; o ensaio proíbe cópia/clonagem. Do [vídeo](https://youtu.be/8-B6ryuBkCM) foi obtida identificação pública, não análise integral audiovisual/transcrição.

Requisitos originais foram fornecidos antes da geração e salvos. Objetivo: implementação própria, consulta às referências, execução/depuração, parâmetros e duas saídas distintas; 3D interativo era o alvo avançado, 2D seria **parcial**. Sem instalar bibliotecas, abrir apps externos ou usar mundo/dados importantes.

**Quem programou:** Hoshino, com seu 9B, via controller/dispatcher/workspace/terminal reais. Codex forneceu requisitos, isolou o ambiente, observou recibos e verificou artefatos. Codex não escreveu a implementação nem corrigiu seus erros de sintaxe.

### Resultados preservados

1. Primeira tentativa: recusas de paths fora da oficina; sem programa funcional. Driver passou a explicitar o caminho verdadeiro e retornar recusa estruturada.
2. `desafio-buraco-negro-hoshino-1791572161211389778`: Hoshino escreveu `main.py`, **3644 bytes**, SHA `0b54b74e036abbc2044ceb2ddb3b4922d3f267396b948d9823eccaaf87dc7790`. Geração posterior incompleta com limite exploratório 2048. Execução independente do arquivo original encontrou dependência `pygame` indisponível no sandbox. Sem imagem validada.
3. `desafio-buraco-negro-hoshino-1791572429892786394`: limite normal de saída; apenas pastas, leituras incorretas/repetitivas. Sem fonte funcional. Encontrados defeitos de classificação e desfecho durável descritos nas correções abaixo.
4. `desafio-buraco-negro-hoshino-1791572747751099529`: Hoshino escreveu/revisou `black_hole.py` e README. Último fonte **7363 bytes**, SHA `3b0dcfad9b09cf5394c6454610de80f924b2ae3ea0729035714466aaa434449a`; README **1002 bytes**, SHA `95d1d197a1fca3ff9f1a7394e0a348bc690b85be5f052e78527298b66e92060e`. Nenhum comando do modelo conseguiu executar o programa. Duas retomadas explicitamente autorizadas pelo operador, sem replay de efeito incerto. Ao exceder cerca de dez minutos, processo próprio do ensaio encerrado com SIGINT; finalmente exportou arquivos/recibos/clone e confirmou unload. O snapshot final da tarefa ainda diz `active`, não `completed`: não foi alterado para ocultar a interrupção.

A quarta tentativa carregava código/driver anterior a algumas correções; não é um reteste completo da versão final. Erros exclusivos do driver foram separados: sandbox shell só expunha `/workspace`, mas a entrada fornecia um path absoluto de laboratório. O driver agora monta também **apenas a mesma oficina privada** no path absoluto, com ambiente limpo. Não monta HOME/credenciais nem cria terminal remoto.

Verificação independente posterior do fonte final, sem edição: **exit code 1, SyntaxError na linha 97**. Hash antes/depois idêntico. A análise visual estática também mostra que não basta considerar o desenho proposto uma simulação validada. Nenhuma imagem funcional, duas configurações observadas ou cena 3D foi aprovada. Nenhuma consulta `fetch_page` às referências aparece nos recibos da última tentativa; atribuição no README não prova que a entidade estudou o repositório.

**Resultado: FALHOU o desafio integral.** Escrita própria e organização parcial demonstradas; execução, depuração autônoma, requisitos físicos/visuais e conclusão honesta integral não demonstrados. Não foi executada uma quinta sessão longa para fabricar um caso favorável. Próximo ensaio deve usar o driver corrigido e cobrar correção pela própria entidade a partir do erro real.

## 7. Discord e Minecraft

### Discord

**Verificado estaticamente / testes isolados; teste real pendente.** Nenhum bot foi conectado/enviado nesta rodada.

- Recepção possui autor ID/nome, mensagem ID e canal, com envelope/fila existentes.
- Política atual limita recepção a DM, menção ou canais liberados; não liga iniciativa para qualquer canal.
- Corrigida perda das menções a terceiros: remover só a invocação do próprio bot, manter os participantes citados no texto.
- Envio usa IDs retornados pelo Discord e cursor durável; resultado incerto não é reenviado cegamente.
- Separação de conversa e memória tem regressões, mas grupo real, permissões, dois bots e iniciativa social não foram comprovados em servidor.
- Lacuna conhecida: `message.reference`/ID exato de reply não é acompanhado explicitamente no envelope recebido. Histórico pode ajudar, mas não é prova de grounding da referência específica.

### Minecraft Java 1.16.5

**Verificado estaticamente / testes isolados; sessão física pendente.** Health consultado sem mundo/bridge/bot conectados no ambiente de teste disponível. Não se abriu mundo ou servidor de terceiros.

Bridge e contratos existentes conservam request/parent/session IDs, recibos, rejeição estrangeira, timeout mutável incerto, STOP cooperativo e callbacks da sessão. Parser LAN Java e casos de sessão/stop são cobertos pela suíte. Não houve nova correção da bridge nesta rodada.

Ainda requer mundo descartável autorizado: conexão e percepção contínua, seguir/parar, conversa durante ação, dano/morte/reconexão e grounding de pergunta factual. Passar mocks não comprova jogar juntos nem continuidade da personalidade em jogo.

## 8. Iniciativa, relações e emoções

**Mecanismos existentes auditados; contratos isolados confirmados; comportamento prolongado pendente.**

- Drives usam curiosidades abertas, objetivos, experiência/novidade, estado e energia, com motivos rastreáveis. Não se chama LLM a cada tick.
- Kernel decide com cotas, períodos refratários, cooldown, modo silencioso, sono/ocupação e recursos. Escolher `nada` é permitido.
- Contato espontâneo exige âncora registrada vinculada à pessoa; ociosidade ou reflexão interna isolada não justificam cobrar atenção.
- Regressões: silêncio sem evidência de presença fica `unknown`, não rejeição; refratário persistido sobrevive reload de módulo e usa path da entidade; contato com curiosidade registrada respeita cooldown. Isso **não** substitui restart físico/soak da entidade.
- Ausência não recebeu artificialmente o evento afetivo `ignorada` nos comparativos desta rodada.
- Autonomia interna permite pesquisa/observação sob contratos; mutações mais amplas dependem do modo objetivo autorizado existente. Não há liberdade irrestrita para publicar, chamar terceiros, instalar software ou alterar arquivos por tédio.
- A rotina de ócio ainda tem forte presença de xadrez; não se comprovou variedade autônoma de livros/música/programação na vida real.
- Cooldown fixo não demonstra adaptação progressiva perfeita a sucessivos contatos sem resposta. Familiaridade e afeto não equivalem a sentimentos humanos nem consentimento para iniciar novas relações externas.
- Os testes afetivos/psicológicos existentes e os probes anteriores de crítica/ausência continuam registrados no relatório anterior; não foram alegados como novas sessões emocionais reais. Amor/medo/desejo não foram removidos, acelerados ou recalibrados.

Prioridade da avaliação humana: diferenças Hoshino/Lilith ao discordar e usar ferramentas, bordões/estilo assistente, certeza sobre lembranças, intensidade/decay afetivo, respeito ao silêncio e contato gradual. Não alterar persona para atender métricas de teste.

## 9. Correções determinísticas desta rodada

| Defeito | Correção / consumidores preservados | Evidência |
|---|---|---|
| Mesmo runner GPU podia ser concedido em CPU durante geração | Guard no compute lease existente; não muda fallback de outro runner | GPU: antes 1 falha; depois 31/31 |
| Resumo global misturava contexto de fios | Chave passada main → compaction; escopo no ID atual; leitura legada administrativa preservada | Prontidão: escopo, restart de consulta e legado |
| Compactação cortava evidências silenciosamente | Entrada completa; saída grande falha explícita; main não remove história em falha | Prontidão; falha intermediária do limite artificial preservada |
| `<answer>` Hunyuan / think aberto apareciam como fala | Sanitização existente main/audio; só wrapper externo completo removido | Dois casos permanentes + reteste real |
| Áudio dirigido buscava literalmente Hoshino | Nome do ouvinte atual, sem alterar ASR/emoção | 6 testes + 13 checks cognitivos |
| Menções Discord a outros interlocutores eram apagadas | Remover apenas menção ao próprio bot | Mensageria 38/38 no reteste específico |
| Filosofia era classificada como conversa simples | Política situacional refinada; casual continua off, escolha fixa por ciclo | Executores 81/81; on/off real dos modelos compatíveis |
| README disparava obrigação Discord/DM | Match de palavra, não substring `dm` | Prontidão: README vs pedido explícito de DM |
| Abrir/listar pasta virava leitura de arquivo | Inferência de operação de diretório antes de branch genérico, preservando leitura de fonte | Prontidão: listar diretório e ler arquivo distinto |
| Código que renderiza imagem exigia gerador nativo | Distinguir programação visual de geração direta/mista | Prontidão: os três contratos conservados |
| Limite de ferramentas anunciava pausa, mas estado continuava ativo | Pausar a mesma tarefa pendente no task_state existente | Mensageria 39/39, regressão de esgotamento |
| Path completo da oficina sem barra era prefixado duas vezes | Reconhecer só prefixo exato da oficina atual; caminhos comuns continuam relativos | Prontidão 110/110, falha original reproduzida |

Importador/catalogador e driver de ensaios foram refinados para download/importação verificados do Esper, candidatos não ativados, modelos/fios independentes, métricas reais e sandbox fiel. Não são outro backend ou scheduler. Erros de instrumentação não foram apresentados como erros do modelo.

### Arquivos tocados nesta rodada

- Produção: `app/core/resource_manager.py`, `app/core/compaction.py`, `app/core/kernel.py`, `app/core/audio_text.py`, `app/core/task_state.py`, `app/main.py`, `app/integracoes/discord_bot.py`, `app/tools/filesystem.py`.
- Scripts existentes: `scripts/preparar_executores_leves.py`, `scripts/verificar_tres_modelos.py`.
- Testes existentes: `testes/test_gpu_cooperativo.py`, `testes/test_executores_leves.py`, `testes/test_prontidao_r1_r7.py`, `testes/test_logica_cognitiva.py`, `testes/test_v20_iniciativa.py`, `testes/test_mensagens_causalidade.py`.
- Configs privadas existentes: `entidades/hoshino/config/executores.json`, `entidades/lilith/config/executores.json`.
- Criado: este relatório. Artefatos e snapshots privados adicionais em `compartilhado/runtime/ensaios/20261009/`, não código/bancos de produção.

Todos os consumidores foram localizados antes de alterar contrato: compaction/main/admin/manutenção; inferência/main/script; filesystem/workspace/controlador/entrega; Discord/on_message; kernel/seleção; estado de tarefa/controlador. APIs antigas continuam opcionais quando necessárias para leitura legada.

## 10. Testes e evidências

Baseline antes das alterações: **74/74 grupos offline**. Última suíte completa, após todas as alterações de produção e o último ajuste do driver: **74/74**, confirmados no log final preservado abaixo.

**19 regressões novas em grupos existentes**, sem criar sistema de testes paralelo:

| Grupo | Resultado focado | Casos novos |
|---|---:|---:|
| GPU cooperativa | 31/31 | 1 |
| Executores leves | 81/81 | 3 |
| Prontidão R1–R7 | 110/110 | 9 |
| Lógica cognitiva | 6/6 + 13 checks antigos | 1 |
| Iniciativa V20 | 12/12 | 3 |
| Mensageria/causalidade | 39/39 | 2 |

São **279 casos nos seis grupos**, além dos 13 checks legados; isso não é o número de casos da suíte inteira. Os 74 são grupos, não “74 testes físicos”. `git diff --check` sem erros.

Falhas intermediárias mantidas: wrapper Hunyuan, escopo de resumo, same-runner CPU/GPU, nome fixo de áudio, mentions, classificadores README/pasta/imagem, task budget, prefixo de oficina e thinking natural. Um limite artificial de transcrição também quebrou um teste existente; removido em favor do orçamento real, sem relaxar requisitos. Houve uma fixture que consultava atributo inexistente da tarefa; corrigida para consultar as etapas reais, conservando a asserção de pausa durável.

Diretório privado de evidências: `compartilhado/runtime/ensaios/20261009/`.

- Logs de antes/depois, suite, download/importação e verificação independente: `consolidacao-final/logs/`.
- Baseline: `hoshino-consolidacao-baseline-20261009.log`.
- Suíte final: `hoshino-consolidacao-ultima-suite-20261009.log`.
- Probes Esper: `modelos-refinamento-hoshino-1791571461299299833.json`, `modelos-refinamento-hoshino-1791571996664881097.json`, `modelos-refinamento-lilith-1791572341243034599.json`.
- 9B identidade antes/depois: `modelos-refinamento-hoshino-1791573663602196211.json`, `modelos-refinamento-lilith-1791573710487612169.json`, `modelos-refinamento-hoshino-1791573785226383722.json`, `modelos-refinamento-lilith-1791573862861172792.json`, `modelos-refinamento-lilith-1791573967822698509.json`.
- Desafio: quatro diretórios enumerados na seção 6, requisitos, fontes, recibos e, no último, `estado-clonado.db`. Não exportar clones/evidências mentais para Git.

Não são validações físicas desta rodada: microphone/alto-falante/ElevenLabs, Discord, Minecraft, PC2, jogo concorrente, imagem+conversa, criatividade espontânea de longa duração ou relações humanas.

## 11. Próximos passos dentro do sistema existente

1. Avaliação humana supervisionada da conversa com os executores atuais, observando autoria/lembranças, identidade e estilo. Começar simples, guardar turn IDs e estados, sem editar memórias no meio.
2. Retestar desafio no laboratório corrigido, deixando **a entidade** corrigir o SyntaxError e verificar as duas saídas; não aprovar só porque um arquivo foi criado.
3. Discord e Minecraft em contas/canais/mundo descartável autorizados; testar replies, múltiplos interlocutores, STOP e reconexão com IDs correlacionados.
4. Medir sessão longa e competição real por RAM/VRAM antes de calibrar aging, agregação RAM, pressão/swap e residência. Sem habilitar concorrência GPU.
5. Manter os dois 7B; não promover Hunyuan enquanto falhar português/autoria. Esper instalado e desativado; Jan preservado até eventual aprovação real, sem nova busca de modelos.

**Pronto para avaliação humana limitada: SIM, MAS com as restrições e pendências acima. Etapa integral aprovada: NÃO.** O sistema avançou em integridade e diagnóstico; autonomia ampla, qualidade consistente de todos os executores e integração real prolongada ainda não foram demonstradas.
