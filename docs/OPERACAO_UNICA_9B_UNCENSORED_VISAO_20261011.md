# Operação experimental exclusiva: Qwen3.5-9B-Uncensored multimodal

> **Estado:** plano e automação local preparada; **NÃO executado** na máquina do operador, nem validado na RX 6650 XT. Decisões revisadas em 11/10/2026.

## Decisões

- Concentrar os novos downloads e testes em **um único checkpoint de base**: [ccharnkij/Qwen3.5-9B-Uncensored](https://huggingface.co/ccharnkij/Qwen3.5-9B-Uncensored), **Safetensors F16** com suporte a texto e imagens; cerca de **18,8 GB**. Não baixar novos LLMs 7B ou 6B por ora. A escolha futura desses portes fica suspensa.
- Para treinamento paramétrico Hoshino/Lilith, utilizar **mesma base Uncensored multimodal** e produzir **adaptadores separados por entidade**. O corpus v2 é a referência, com grupos de treino/validação/teste distintos por entidade.
- O LoRA proposto altera **camadas textuais**; pesos do encoder de visão permanecem congelados, preservados no checkpoint. A visão precisa de teste multimodal real independente. Não confundir possuir tensores visuais com sucesso de inferência visual.
- O objetivo declarado é **até dez horas de otimização no total** (5 horas Hoshino + 5 horas Lilith em sequência, jamais simultaneamente na GPU), não dez horas por entidade. Download, inicialização e probes não contam como tempo de otimização.
- Qwen3.5 tem thinking nativo comutável, a verificar no backend de inferência; o treinamento textual desta rodada usa `enable_thinking=False`. Isso não elimina necessidade de memória operacional e autorizações.
- A decisão anterior de preservar todos os modelos Ollama foi alterada por solicitação do operador: ele deseja **excluir os modelos Ollama existentes antes do novo download**. Esse passo tem riscos importantes e exige confirmação literal.

## Exclusão limitada, mas destrutiva

A automação local **somente pode excluir** as subpastas `blobs` e `manifests` de:

- `~/hoshino/models/ollama`
- `~/hoshino e lilith/compartilhado/modelos/ollama`
- `~/hoshino e lilith/compartilhado/modelos/ollama-lilith`
- `~/.ollama/models`

Isso **apaga também os arquivos dos modelos 4B de Alistair e 7B de Hoshino/Lilith que residam nesses diretórios**. Os agentes podem parar de funcionar e **o download do checkpoint HF não reinstala automaticamente um modelo no Ollama**. Memórias, bancos, identidades, constituições, scripts do projeto e laboratórios fora dessas pastas não devem ser apagados. Outros caminhos desconhecidos ficam fora do escopo. **Não usar `rm -rf` sobre diretórios pai**, nem mexer em sistemas sem identificar os paths reais.

Por motivo de risco, a operação começa com uma prévia somente de leitura, confere serviços Ollama parados, tamanho recuperável e espaço disponível, e somente então aceita `--confirm-delete EU_AUTORIZO_APAGAR_TODOS_OS_MODELOS_OLLAMA`. **O usuário deve inspecionar o plano antes de confirmar.** Se a internet falhar depois da exclusão, os modelos antigos não estarão mais disponíveis; a alternativa tecnicamente menos arriscada continua sendo baixar e verificar antes de apagar, se houver espaço.

## Encadeamento automático local

1. Auditoria, confirmação destrutiva explícita e exclusão dos modelos Ollama conhecidos (não dos bancos).
2. Download do **único** checkpoint HF multimodal e sua revisão fixa, com verificação de Safetensors e tensores visuais. Se download falhar, nada mais roda; download parcial pode ser recuperado posteriormente.
3. **Probe independente da entidade Hoshino**: GPU ROCm gfx1032 com `HSA_OVERRIDE_GFX_VERSION` removido apenas do subprocesso, BF16, NF4, carregamento da arquitetura `Qwen3_5ForConditionalGeneration`, forward, backward com loss e gradientes finitos, forward multimodal com imagem e validação reservada.
4. Mesmo probe para **Lilith**. Se algum probe falhar por OOM, acesso ilegal HIP/ROCm, NaN ou incompatibilidade de modelo/tokenizer/PEFT, a automação **não inicia treino**.
5. Se todos passarem: até 300 min de Hoshino; depois até 300 min de Lilith, com checkpoints separados e atômicos a cada 15 min; possível interrupção precoce ao piorar validação.
6. Interrupção a pedido do usuário por sinal: guardar um adaptador após passo atual (quando o processo Python/GPU permanece responsivo); esperar salvamento. **Não há garantia em falha catastrófica da GPU/corte de energia**. Os adaptadores não incluem estado completo do otimizador, então **não existe retomada exata automática**; uma retomada futura exige implementação e teste.
7. Comparar base e adaptadores, testar thinking ON/OFF, visão, comportamentos diferentes das entidades, preservação de habilidades, memória/contexto dinâmico e confiabilidade de decisões antes de qualquer mudança em produção.

## Restrições e incompatibilidades reais

- **RX 6650 XT com 8 GiB:** sucesso do Qwen2.5-7B em QLoRA **não comprova** que Qwen3.5-9B multimodal fará backward. O plano **não tem offloading de backward validado**; proíbe fallback silencioso CPU; falhar é aceitável.
- O script anterior do 9B foi escrito com `Qwen3_5ForCausalLM` para texto; para o checkpoint com visão, o protótipo novo utiliza `Qwen3_5ForConditionalGeneration`. Compatibilidade efetiva com a versão instalada de Transformers, PEFT, ROCm e bitsandbytes **depende de probe físico**.
- Testar visão requer `AutoProcessor` e imagem real; a presença de `vision_config` não valida o uso visual com adapter.
- O dataset v2 ainda é sintético, relativamente limitado e não justifica dez horas obrigatórias: aplicar cedo-parar e checar overfitting.
- Não transferir adaptadores sem validar **a mesma revisão base** e método de implantação no GGUF/Ollama. Não modificar a Central, os bancos nem a personalidade dinâmica ainda.
- A automação deste plano é **local no Linux**, não uma automação do ChatGPT: ChatGPT/GitHub não têm acesso ao hardware do computador pessoal para iniciar o download ou o treino.

## Artefatos

Foi produzido um pacote de instalação **local**, entregue ao operador em conversa: `automacao_9b_vision_v1.zip`, com:

- `orquestrar_9b.py`: prévia, confirmação de limpeza, encadeamento, status e solicitação de parada
- `baixar_9b.py`: download HF com commit fixado + validação multimodal estrutural
- `treino_9b_vision.py`: probe de backward e forward visual + otimização LoRA text-only sobre base multimodal
- `hoshino_lilith_treinamento_neural_v2.zip`: dataset e avaliação, sem pesos adicionais
- `README.md` e `testes_static.py`

As validações realizadas **fora da máquina do operador** cobrem compilação Python, inspeção de ZIP, prévia não destrutiva e bloqueio quando a confirmação não é válida. Não incluem prova GPU, baixar pesos, limpar Ollama nem iniciar dez horas.

**O repositório continua privado.**
## Correção do orquestrador v1.1 — links simbólicos compartilhados

**Ocorrência observada:** ao executar `orquestrar_9b.py plan` em 11/10/2026, a auditoria da v1.0 interrompeu **antes de qualquer exclusão** ao encontrar `~/hoshino/models/ollama/manifests` como symlink. O destino real do link **ainda não foi fornecido**; não se presume que aponta a qualquer pasta específica.

**Correção preparada fora do PC do operador:** pacote `automacao_9b_vision_v1_1.zip` com auditoria que aceita somente links cuja resolução coincide exatamente com `blobs` ou `manifests` físicos de **outra raiz explicitamente listada no plano**. Recusa destinos desconhecidos, conta pastas compartilhadas uma única vez, e na eventual exclusão preserva o próprio symlink e o diretório, removendo somente conteúdos dos diretórios físicos aprovados. Estado isolado da v1.0 (`orquestrador-9b-vision-v1-1`).

**Validação:** compilação Python, casos sintéticos de link reconhecido, link para destino externo não autorizado, confirmação inválida e exclusão simulada em `TemporaryDirectory`; **nenhum teste destrutivo foi feito na máquina do usuário**. Antes de qualquer `start`, instalar v1.1, executar `python automacao_9b_vision_v1_1/orquestrar_9b.py plan` e inspecionar os destinos impressos. Caso falhe, capturar saída de `ls -ld` e `readlink -f` das raízes; **não remover symlinks nem suprimir a proteção**.

**Risco remanescente:** a ordem pedida pelo usuário continua sendo exclusão dos modelos Ollama ANTES do download de ~18,8 GB. Se a rede falhar, a instalação ficará sem executores Ollama; Safetensors baixado não volta automaticamente ao Ollama. **Não iniciar ainda sem aprovação do plano real e conferência de espaço.**

## Atualização v1.2 — GGUF e testes comparativos no Ollama de laboratório

**Motivo:** operador executou `plan` v1.1 com sucesso em 11/10/2026: dois links simbólicos conhecidos preservados, aproximadamente 20,92 GiB lógicos de arquivos de modelo distribuídos entre Hoshino e Lilith, **nenhuma exclusão efetuada**. Solicitou que a automação, após o treino, **compare as versões, converta os pesos para GGUF e permita testes pelo painel Ollama**.

**Artefato entregue na conversa:** `automacao_9b_vision_v1_2.zip`. Scripts incluídos: `orquestrar_9b.py`, `baixar_9b.py`, `treino_9b_vision.py`, `exportar_e_comparar.py`, `testes_static.py`, `iniciar_painel_ollama.sh`, `README.md` e corpus v2. **O ZIP não foi automaticamente enviado ao repositório**; usar a cópia entregue ao operador, cujo código foi verificado estaticamente. A execução no PC ainda não ocorreu.

### Pré-voo agora obrigatório ANTES de excluir Ollama

- Confirmar llama.cpp local com `convert_hf_to_gguf.py`, `convert_lora_to_gguf.py`, `build/bin/llama-quantize`; execução `start` recusa limpeza se faltarem as ferramentas. Não há `git clone` nem downloads adicionais automáticos de ferramentas. O modelo 9B continua sendo o **único checkpoint HF** a baixar.
- Projeção conservadora de espaço: **pelo menos 52 GiB livres após a limpeza**, antes de baixar o HF. A conversão posterior demanda **pelo menos 28 GiB livres**, pois há GGUF F16 intermediário, Q4_K_M e mmproj. Evitar excluir bancos para liberar espaço.
- Fazer `python automacao_9b_vision_v1_2/testes_static.py` e `python automacao_9b_vision_v1_2/orquestrar_9b.py plan`; inspecionar os destinos. `plan` é somente leitura. `start --confirm-delete EU_AUTORIZO_APAGAR_TODOS_OS_MODELOS_OLLAMA` **continua destrutivo** e requer Ollama parado.
- Laboratório usa novo estado `~/laboratorio-lora/experimentos/orquestrador-9b-vision-v1-2`, independente da v1.1.

### Exportação e homologação experimental

- A base Safetensors **Uncensored multimodal** é convertida por llama.cpp para GGUF F16 intermediário e então `base-q4_k_m.gguf`. Gera-se `mmproj-f16.gguf` separado para visão. O GGUF F16 intermediário é descartado **somente** após comprovar que o Q4 resultante possui cabeçalho GGUF válido.
- O adaptador selecionado de cada entidade é convertido por `convert_lora_to_gguf.py` para `hoshino-lora-f16.gguf` e `lilith-lora-f16.gguf`. Checkpoints são escolhidos por **menor loss de validação entre os que têm valor registrado**; testes cegos não fazem parte da seleção. **Não são criados dois GGUF completos de 9B com LoRA mesclado**, que exigiriam mais RAM/disco.
- São tentadas três importações numa instância Ollama **isolada**, porta `127.0.0.1:11555`, armazenamento `~/laboratorio-lora/ollama-painel-9b-lab`: `lab9b-original`, `lab9b-hoshino`, `lab9b-lilith`. `Modelfile` combina `FROM base.gguf`, `FROM mmproj.gguf` e, quando aplicável, `ADAPTER lora.gguf`. **A compatibilidade do Ollama com Qwen3.5 + LoRA GGUF + projetor visual é experimental**; se conversão/importação falhar, a automação interrompe sem alterar os daemons da Central.
- Executa testes pareados base/adaptado: prompts reservados, avaliação cega, identidades, `tsundere`, raciocínio lógico, JSON, matemática, thinking ON/OFF, interpretação de imagem gerada no teste e conversa real de 5 turnos; salva `comparacao_resultados.json`, `proveniência.json` e `resultado_final.json`. O status `API_SMOKE_OK_PENDENTE_REVISAO` indica **somente API funcional**, não que personalidade, visão, raciocínio, adaptador ou thinking estejam validados com rigor. Falhas e ausências de evidência ficam registradas.
- Os modelos Ollama isolados podem ser vistos após o teste iniciando `bash ~/laboratorio-lora/automacao_9b_vision_v1_2/iniciar_painel_ollama.sh` e conectando cliente/painel a `http://127.0.0.1:11555`, sem alterar portas 11435/11436/11437. **Nenhuma adoção em produção é automática**.
- Se a exportação falhar **depois** das duas sessões de treino, os LoRAs e o estado `trained` ficam preservados para nova tentativa apenas da etapa de exportação, sem apagar modelos nem reiniciar treino. Se falhar probe ou treino antes disso, não há retomada exata garantida.

**Validações efetuadas fora do Linux do operador:** compilação Python, simulação de limpeza com symlinks, rejeição de destino externo e confirmação errada, seleção de checkpoint por loss registrada, cabeçalho GGUF e nomeação de mmproj; integridade de ZIP. **Não foram executados download, treino QLoRA 9B, conversão GGUF real ou teste real de Ollama.**


## Extensão v1.3 — hábitos de memória aprendidos no LoRA

**Motivação (11/10/2026):** O operador quer reduzir injeções estáticas de contexto sobre quando recuperar memórias, registrar conhecimentos/procedimentos, consolidar experiências e acessar diários, passando a ensinar essas **tendências decisórias** no LoRA específico do ambiente de Hoshino e Lilith.

**Evidência arquitetural da revisão GitHub:** `app/mind/scribe.py` já grava automaticamente certos dados de conversa; `app/core/dispatch.py` já expõe `consultar_conhecimento`, `buscar_historico_chat`, `registrar_conhecimento`, `registrar_procedimento`, `aprender_experiencia`, `diario`, `manual_habilidades` e ferramentas de consulta. `app/memory/cognitive_notes.py` exige episódios/evidências reais, restringe observador e mantém diários privados.

**Artefato offline preparado:** `automacao_9b_vision_v1_3.zip` entregue ao operador na conversa. Substitui, **antes de qualquer treino**, o pacote v1.2; não atualiza por si só a pasta local. É um novo diretório `automacao_9b_vision_v1_3`, novo estado `orquestrador-9b-vision-v1-3` e corpus `pacote_neural_v3`. Mantém o v2 original como referência imutável, scripts de visão, conversão GGUF e guardas de exclusão da v1.2. Total por entidade: **722 treino** (+40), **131 validação** (+10), **104 teste reservado** (+14); 28 casos de memória reservados no total; **7 prompts de memória por entidade** são adicionados aos testes pareados do Ollama. Os splits são distintos; a extensão é intencionalmente pequena para não dominar personalidade/competências gerais.

**O que é treinado:** recuperação seletiva de memória quando apropriada, não registrar cada conversa trivial, evitar duplicar o `scribe`, diferenciar conhecimento factual de hipótese, registrar passos com pré-condições e resultados, atualizar lições com exceções e proveniência, não inventar memórias, respeitar privacidade entre entidades, não afirmar gravação sem resposta de confirmação, verificar esquemas reais de ferramentas e agir corretamente quando elas estão desligadas.

**Limite crucial:** nesta etapa o SFT usa apenas **pares de texto usuário/assistente**, não sequências tokenizadas de `tool_calls`/respostas de ferramentas. Portanto ele ensina **critérios de decisão e linguagem**, não garante invocação efetiva da API de memória. Esquemas de ferramentas, permissões, identidade de entidade, estado atual, memórias relevantes e resultados de operações precisam continuar sendo fornecidos dinamicamente pelo núcleo. Experimentos posteriores devem treinar e validar tool calling REAL no formato do template/backend, sem adotar novo parser experimental às cegas antes do treino longo.

**Teste de aceitação específico:** comparar base e LoRA em prompts reservados; depois executar testes reais no runtime da Central verificando chamadas corretas (nome e schema), não-duplicação automática do `scribe`, `aprender_experiencia` com episódios, comprovação de persistência via consulta, nenhum vazamento de diário, tratamento de ferramenta indisponível e ablação de tokens de contexto. O smoke test textual no Ollama isolado não é aprovação de integração com SQLite.

### Auditoria do operador v1.2 antes de atualizar

- `testes_static.py`: PASSOU.
- `orquestrar_9b.py plan`: PASSOU; dois symlinks para diretórios conhecidos preservados; nenhuma exclusão.
- Volume `/dev/nvme0n1p2`: 817G total, 725G utilizados, **51G livres, 94%**. Relatório de limpeza estimou **20,92 GiB lógicos** dos modelos. Recuperação de espaço física real **não garantida**, principalmente com reflinks.
- `plan` não verifica instalação de `llama.cpp`, embora `start` da v1.3 mantenha a verificação **antes da limpeza**. Confirmar as três ferramentas no disco e os daemons Ollama parados.
- Com internet lenta e **51G livres antes da exclusão**, **baixar primeiro** os ~18,8 GB HF Uncensored e só depois limpar Ollama seria menos arriscado se o operador autorizar mudar a ordem; a automação v1.3 **mantém a ordem destrutiva anteriormente solicitada**, excluindo antes do download. Portanto **não executar `start` sem confirmação consciente**. Os cálculos de espaço são projeções, não validação de espaço pós-limpeza.
- Nenhum download HF, limpeza Ollama, treino 9B ou conversão GGUF foi comprovado até este registro.

**Verificação realizada fora do computador do operador:** sintaxe Python, testes de limpeza simulada, verificação de ZIP, contagem e isolamento de splits e avaliação de rotas; não GPU real nem SQLite do projeto.

## Bloqueio novo — conversão multimodal GGUF no Ollama (11/10/2026)

O operador confirmou no terminal que não estão presentes `convert_hf_to_gguf.py`, `convert_lora_to_gguf.py` ou `build/bin/llama-quantize` nas pastas `~/laboratorio-lora/llama.cpp` e `~/llama.cpp`, mas `ollama` existe em `/usr/local/bin/ollama`. A v1.3 **não foi iniciada**, não apagou modelos e não fez download de checkpoint.

**Descoberta em inspeção do script `exportar_e_comparar.py` v1.3:** a rotina `create_models()` monta dois comandos `FROM` no mesmo Modelfile, `FROM base-q4_k_m.gguf` e `FROM mmproj-f16.gguf`, para anexar o projetor visual do Qwen3.5. Essa estratégia **não deve ser considerada suportada**. Existem relatos de `ollama create` pendurar com dois `FROM` para projetor visual em Ollama 0.32.5, e falhas de importação com `ADAPTER mmproj` para Qwen3.5: https://github.com/ollama/ollama/issues/17491 e https://github.com/ollama/ollama/issues/15346 . O código atual não impõe timeout a cada chamada HTTP de criação suficientemente curto para assegurar término nessas condições.

**Decisão operacional:** mesmo após instalar `llama.cpp`, **NÃO executar o `start` destrutivo da v1.3** até corrigir e testar a via multimodal e os timeouts com um modelo descartável/pequeno ou comprovar compatibilidade do backend. Preferir testes isolados `llama.cpp` com `--mmproj` quando aplicável; a Central/Ollama de produção não deve ser alterada para experimentar formato não homologado. A falha de formato não invalida necessariamente os futuros LoRAs, mas impede prometer painel Ollama com visão.

Instalação isolada das ferramentas (download **somente de código**, não de pesos) é permitida:
```bash
cd ~/laboratorio-lora
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git
cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_TESTS=OFF -DLLAMA_CURL=OFF
cmake --build llama.cpp/build --target llama-quantize -j 4
```
Não executar `pip install -r llama.cpp/requirements.txt` indiscriminadamente no ambiente ROCm; preservar versões de PyTorch.

**Observação adicional:** resultado de `plan` e testes estáticos não prova funcionamento do conversor, importação ou visão; só demonstra proteção de arquivos e estrutura do pacote. Com 51 GiB livres, modelo HF ~18,8 GB e material intermediário grande, o orçamento de disco deve ser reavaliado antes de qualquer limpeza.


## Operação noturna v1.4 — pedido de execução única (11/10/2026)

**Usuário autorizou expressamente** parar o download parcial anterior, excluir os modelos Ollama antigos auditados para liberar espaço, baixar apenas os pesos Safetensors multimodais `ccharnkij/Qwen3.5-9B-Uncensored`, testar o 9B e tentar **até dez horas** de otimização (5 horas Hoshino e 5 horas Lilith, não simultâneas), converter os adaptadores para GGUF e avaliar os resultados em Ollama isolado.

**Pacote produzido e entregue ao operador:** `automacao_9b_vision_v1_4.zip`. **Instalação ou execução na máquina do usuário não ocorreu a partir desta sessão**. Versão independente em `~/laboratorio-lora/automacao_9b_vision_v1_4`, diretórios novos `orquestrador-9b-vision-v1-4` e `exportacao-9b-vision-v1-4`. Scripts e corpus v3 incorporados. Testes estáticos/simulados passaram, inclusive symlinks, confirmação inválida, seleção fictícia por loss, formato GGUF, integridade do ZIP e bloqueio de duplo `FROM`. Os números de loss exibidos nesses testes são **fictícios** e não representam treino.

### Mudanças operacionais críticas da v1.4

- **Antes de excluir:** com confirmação literal, inspeciona `~/laboratorio-lora/logs/download-9b.pid`. Se o PID ainda for o download original v1.3 e a linha de comando corresponder ao checkpoint esperado, envia SIGTERM e espera até 45 segundos; preserva o download parcial para possível retomada HF. Se PID for reutilizado, não mata um processo estranho e aborta.
- Antes da exclusão também verifica ferramentas `llama.cpp`, importabilidade `Qwen3_5ForConditionalGeneration` e `AutoProcessor`, dependências de QLoRA, GPU ROCm com BF16 nativo e **backward BF16 pequeno**, bem como a estrutura do corpus. Ainda NÃO prova viabilidade do **9B inteiro**.
- Solicita SIGTERM aos processos **`ollama serve` do próprio usuário**; se o daemon não parar ou um supervisor o reiniciar, recusa apagar pesos em uso. Preserva symlinks físicos do projeto e todos os caminhos fora das pastas `blobs/manifests` auditadas. A exclusão permanece irreversível sem backup/re-download. Após limpeza, verifica espaço livre real antes do download.
- O treino multimodal NF4/LoRA é somente sobre camadas textuais, preserva a visão original e **pode falhar por VRAM insuficiente** na RX 6650 XT 8GiB. O ciclo longo depende de probes reais completos (backward + forward com imagem). Não existe fallback de camada neural silencioso nem retomada exata do otimizador.
- Se o treino concluir e a exportação falhar, preserva os checkpoints e grava `stage=trained,status=export_pending`, permitindo **reexecutar apenas exportação** depois de corrigir o erro; não confunde com treino concluído+modelos aprovados.
- **Correção da falha multimodal Ollama:** Modelfile agora contém **um único `FROM`** para a base Q4_K_M. O adaptador LoRA GGUF é introduzido somente por `ADAPTER`. Os modelos importados no Ollama isolado `127.0.0.1:11555` são **testes TEXTUAIS**; `mmproj` NÃO funciona de modo confiável via segundo `FROM` e não é importado por essa rota. As criações Ollama têm timeout (180 segundos por modelo), e as chamadas de comparação também têm limite de tempo.
- **Visão real separada:** tenta compilar `llama-server` local sem baixar pesos e testar `base-q4_k_m.gguf` junto com `mmproj-f16.gguf` em `127.0.0.1:11556`, usando imagem vermelha e API multimodal. Resultado isolado em `visao_llamacpp.json`. Falha visual não vira sucesso implícito; não apaga LoRAs.
- Os testes textuais comparam Qwen base e entidades adaptadas, identidade, lógica com thinking ON/OFF, instruções, contextos de memória e turnos longos. Resultados e falhas são registrados e **não** significam homologação da Central. Implantar no projeto real permanece tarefa separada, com prova de compatibilidade.

**Comandos de instalação e execução (somente no computador do operador, após baixar o ZIP):**

```bash
cd ~/laboratorio-lora
source .venv-rocm/bin/activate
unzip -n ~/Downloads/automacao_9b_vision_v1_4.zip -d ~/laboratorio-lora
python automacao_9b_vision_v1_4/testes_static.py
python automacao_9b_vision_v1_4/orquestrar_9b.py plan
mkdir -p ~/laboratorio-lora/logs
nohup env -u HSA_OVERRIDE_GFX_VERSION python -u automacao_9b_vision_v1_4/orquestrar_9b.py start \
  --confirm-delete EU_AUTORIZO_APAGAR_TODOS_OS_MODELOS_OLLAMA \
  > ~/laboratorio-lora/logs/9b-vision-v1-4.log 2>&1 < /dev/null &
```

**Acompanhamento e parada:**

```bash
tail -n 80 ~/laboratorio-lora/logs/9b-vision-v1-4.log
python ~/laboratorio-lora/automacao_9b_vision_v1_4/orquestrar_9b.py status
python ~/laboratorio-lora/automacao_9b_vision_v1_4/orquestrar_9b.py stop
```

**Limites não resolvidos:** não foi testado treino QLoRA completo Qwen3.5-9B multimodal em 8 GiB VRAM; não há garantia de que o download de ~18,8GB termine na noite com internet lenta, de que a arquitetura suportará backward, nem de que o Ollama carregará LoRA GGUF Qwen3.5. Se o procedimento falhar antes da exportação, os modelos Ollama antigos já apagados **não** serão restituídos automaticamente. Relatórios separaram `training`, `export`, `vision_llamacpp` e `ollama_text_only`, sem aprovação falsa de visão em Ollama. O projeto de produção não foi alterado por este documento.

## Janela diurna — pausa do treino até 21h (11/10/2026)

A pedido explícito do usuário, **não iniciar probes nem as dez horas de treinamento durante o dia**, porque ele precisa usar a RX 6650 XT e o computador. Preservar download lento em andamento, sem repetir a limpeza de modelos Ollama já feita. A execução retomada após o erro do Hugging Face foi observada com orquestrador PID `66998` e downloader PID `66999`, porém esses PIDs podem mudar.

**A v1.4 não possui janela temporal:** se o download terminar antes de 21h, inicia imediatamente o probe. Por isso o novo pacote `laboratorio_neural_painel_mods_v0_1.zip` disponibiliza `laboratorio/controle.py` e `laboratorio/labctl.py` para **pausar somente o processo pai** com `SIGSTOP` e agendar `SIGCONT` às 21h local por `systemd-run --user --on-calendar`. O filho downloader continua ativo. Resume somente com PID, proprietário, cmdline e tempo de início do processo idênticos. Usuário precisa instalar pacote e executar o agendamento local; **documentar não equivale a agendar**. A sessão e o PC devem permanecer ativos; reiniciar sistema invalida a retomada.

O sistema de mods desta entrega é **somente para snapshot** e não altera a v1.4 que está atualmente rodando em memória, nem os módulos Python vivos da Central. Abrir um painel não reconfigura um processo já carregado. Consulte [desenho e procedimentos](LABORATORIO_NEURAL_E_MODS_20261011.md).

## Atualização operacional posterior — 11/10/2026, 13:49 BRT

**Esta seção prevalece sobre orientações anteriores que pressupõem PIDs 66998/66999 ativos.** O operador confirmou duas vezes que **nem o orquestrador nem o downloader ainda existem**; há 18G na pasta HF ocupados por dois arquivos `.incomplete` (17.731.420.160 e 1.024.000.000 bytes), **sem arquivo final `model.safetensors`**. O registro de estado continua em `stage=deleted,status=failed,at=03:19:31`, retratando a falha anterior, e não comprova que a retomada mais recente completou alguma etapa. O log acaba em `Trying to resume download...` após encerramento incompleto de conexão HTTP; causa exata da saída dos processos é desconhecida. O timer das 21h existia, mas está associado ao PID 66998 agora morto; não pode ser tratado como garantia de retomada automática.

**Não iniciar treino nem exportação, não reaplicar a exclusão destrutiva de modelos Ollama e não apagar os parciais antes de diagnosticar/resumir com segurança.** O procedimento de recuperação e saídas reais estão no [handoff operacional completo](HANDOFF_20261011_OPERACAO_9B_ESTADO_REAL.md); o [índice de continuidade](HANDOFF_20261011_INDICE_E_DECISOES.md) é o ponto de entrada para o próximo chat.
