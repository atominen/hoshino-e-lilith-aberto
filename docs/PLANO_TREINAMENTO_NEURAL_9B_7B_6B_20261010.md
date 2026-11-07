# Plano de treinamento neural e avaliação de modelos — 10/10/2026

**Projeto:** Hoshino, Lilith e Alistair  
**Repositório:** `atominen/hoshino-e-lilith` (privado; manter privado)  
**Estado:** decisões de laboratório e protocolo operacional; **não é relatório de treino executado**.  
**Janela pretendida:** preparação em 10/10/2026, avaliação em **11/10/2026** (horário America/Sao_Paulo), após validações.  
**Base documental:** histórico técnico do laboratório de 10/10/2026 e pacote de corpus neural v2.0 fornecidos pelo operador; consultar essas fontes originais no laboratório, que não são automaticamente arquivos deste repositório.

## 1. Objetivo

Ensinar **identidade nominal e tendências comportamentais paramétricas** por adaptadores LoRA/QLoRA distintos para Hoshino e Lilith, visando naturalidade e redução **mensurável** de instruções estáticas de personalidade no contexto. Preservar o núcleo externo de memória, diários, relações, aprendizado causal, Resource Manager, caixa postal, Central e políticas de ferramentas. Não confundir tendências dos pesos com lembranças, estados atuais ou consciência.

As inspirações ficcionais são **Hoshino (Blue Archive)** e **Lilith (The NOexistenceN of you AND me)**: Hoshino combina descontração, humor de veterana, resistência ao esforço supérfluo e proteção quando algo importa; Lilith combina afeto, introspecção existencial, estranheza, humor inesperado e ambiguidade emocional. A inspiração **não** deve incorporar enredos dos jogos como biografia real, copiar falas protegidas, estereotipar `tsundere`, nem inventar eventos de convivência. As duas entidades devem diferir em escolhas, justificativas e ritmo, não só em bordões. Humor informal e provocações contextuais são legítimos; limites para atos físicos, dados privados e consentimento não desaparecem.

## 2. Decisões de modelos

| Papel | Decisão em 10/10 | Thinking real |
|---|---|---|
| Principal 9B | **Manter Qwen3.5-9B-Uncensored** já presente nas entidades; treinar somente cópias da variante Uncensored em Safetensors no laboratório isolado | **Sim**, após validar no backend |
| Intermediário 7B | **Manter Qwen2.5-7B-Instruct Q4_K_M atual**, pois QLoRA NF4/BF16 do 7B foi demonstrado na RX 6650 XT | **Não** há comutador nativo de thinking; não falsificar a capacidade |
| Faixa ~6B | **Sem candidato selecionado**: Yi-1.5-6B-Chat descartado porque não possui thinking nativo ON/OFF, requisito obrigatório | Necessário comprovar a alternância real antes de considerar modelo |
| Alistair 4B | Preservar Qwen3.5-4B, sem alteração | Verificar com a API atual em teste próprio, sem substituir o modelo |

O mesmo **conteúdo semântico** do corpus pode ser empregado nos três portes, porém cada família exige **tokenizador, template, máscara de loss, checkpoint e LoRA separados**. Nunca aplicar pesos LoRA do Qwen2.5 7B ao Qwen3.5 9B ou Yi 6B. **Nenhum modelo deve ser substituído automaticamente.**

Referências públicas:
- Qwen3.5-9B-Uncensored Safetensors (**pesos escolhidos para treino da variante instalada**): https://huggingface.co/ccharnkij/Qwen3.5-9B-Uncensored ; GGUF de inferência: https://huggingface.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF
- Qwen3.5-9B oficial (**não escolhido para treinar o adaptador destinado à variante Uncensored**): https://huggingface.co/Qwen/Qwen3.5-9B — thinking por `enable_thinking` na família; testar suporte real na variante.
- Qwen2.5-7B-Instruct: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
- Yi-1.5-6B-Chat (descartado pelo requisito de thinking): https://huggingface.co/01-ai/Yi-1.5-6B-Chat
- Qwen3.5-4B (alternativa de **4B**, já presente para Alistair; não é um 6B e não foi aprovado como substituto): https://huggingface.co/Qwen/Qwen3.5-4B
- Inferência Ollama de demonstração: https://ollama.com/library/yi:6b-chat
- Qwen3-8B (se futuramente admitir outra faixa de parâmetros): https://huggingface.co/Qwen/Qwen3-8B, com `enable_thinking=True/False`. **Não aprovado aqui**.

### Política de thinking no núcleo

- `auto`: diálogo simples, brincadeira e socialização sem thinking por padrão; problemas científicos, lógica condicional, depuração, planejamento, decisões e validação podem acioná-lo nos **modelos com suporte nativo**.
- `on`: força thinking quando suportado para diagnóstico; nunca afirmar que o resultado é melhor sem medir.
- `off`: força resposta direta no modelo que suporte a chave.
- No **Qwen2.5 7B e no Yi 6B descartado**, `auto/on/off` não deve virar uma simulação de thinking. Registrar `thinking_unsupported` e, se houver necessidade de raciocínio profundo e autorização do Resource Manager, **rotear ao 9B** ou usar raciocínio comum do modelo sem fingir canal interno.
- Em **Qwen3.5**, alternar com **parâmetro do backend/template**; testar separadamente `think=true` e `think=false` no Ollama real. Não depender de `/think`, `/no_think` ou de texto escondido no prompt. Thinking não deve escapar para memória pública, diários, JSON de ferramenta ou fala final.
- Decisões operacionais requerem **validação externa de condições, exceções, permissões e efeitos**; thinking ativado não é garantia de acerto. Preservar a escolha estável durante um ciclo, evitando trocar executor ou thinking no meio do raciocínio sem uma decisão explícita.

## 3. Treinamento experimental do 9B — limite de ATÉ 10 horas

**Decisão: autorizar somente um experimento no laboratório independente; NÃO iniciar 10 horas às cegas.** O histórico do usuário **não** contém backward QLoRA completo comprovado no Qwen3.5 9B e documenta falha anterior de carregamento ROCm do 9B de inferência. A RX 6650 XT tem 8 GiB, Ryzen 5 5500, 32 GiB RAM e PCIe 3.0 x8. Não presumir que sucesso do 7B implique viabilidade do 9B.

### Etapa A — pré-voo obrigatório (não treinar)

1. Verificar espaço real em disco, RAM, VRAM, temperatura, drivers, versões PyTorch/TheRock/Transformers e hashes/revisões dos pesos de origem.
2. Usar **ccharnkij/Qwen3.5-9B-Uncensored em Safetensors F16** (mesmo publicador do GGUF em produção) numa pasta isolada, verificando revisão e pesos. O repositório contém `model.safetensors` de ~18,8 GB decimais. O GGUF Q4 do Ollama serve principalmente à inferência; desquantizar não restaura precisão. Não baixar o Qwen oficial apenas por suposta impossibilidade de treinar Uncensored. **Atenção:** o `config.json` dessa variante indica `Qwen3_5ForConditionalGeneration`, multimodal. O script experimental atual usa `Qwen3_5ForCausalLM` e precisa de teste/possível adaptação ANTES do backward.
3. Preservar o trabalho atual. Usar caminhos `~/laboratorio-lora/` e saída nova por experimento/entidade. Nada em `entidades/*/memoria`, identidades/constituições ou daemons Ollama de produção.
4. No processo de treino ROCm gfx1032 utilizar `env -u HSA_OVERRIDE_GFX_VERSION`; o override gfx1030 foi relacionado a `invalid kernel file` no laboratório, mas **não alterar o ~/.bashrc globalmente**.
5. Validar o modelo **base** em português com e sem thinking; testar aritmética, instrução literal, decisões condicionais, JSON e consistência.
6. Fazer **um forward + backward BF16/NF4 ou técnica justificadamente compatível**, com Loss/gradientes finitos, camada e pesos esperados, GPU real verificada; medir pico de VRAM/RAM e ausência de swap descontrolado. Não confiar em `device_map=auto` como prova de treinamento com offloading correto. Para Qwen3.5 híbrido (Gated DeltaNet), checar suporte às camadas e gradient checkpointing.
7. Comprovar save/reload de adaptador experimental, sem corrupção. Qualquer `illegal memory access`, OOM, NaN, kernel inválido ou falha de recuperação => **parar e diagnosticar**, não fazer fallback silencioso.

### Etapa B — piloto e promoção

- Executar um piloto **10–30 minutos**, idealmente com dados reduzidos e sem alteração de corpus reservado, registrando loss por grupo, gradientes, tokens/s, uso de VRAM/RAM, temperatura, tempo e erro.
- Executar avaliação base vs LoRA piloto. Se houver piora grave em raciocínio, JSON/ferramentas, identidade seletiva, repetição de nome, privacidade ou naturalidade, **não promover** para o treino longo.
- Somente após piloto aprovado: iniciar processo de **até dez horas de otimização**, não dez horas de relógio incluindo carga. Checkpoints atômicos **a cada 20–30 minutos**, sempre em diretórios imutáveis e únicos.
- Manter dados de validação e teste rigorosamente fora do SFT; priorizar grupos de cenários sem vazamento por paráfrase.
- Usar o pacote v2 como ponto de partida, mas auditar duplicações, qualidade e variabilidade; **682 exemplos de SFT por entidade não justificam automaticamente 10h**. Monitorar overfitting e interromper cedo se a validação piorar.
- Preservar capacidades gerais com mistura de exemplos neutros e, se viável, **KL multi-token** comparado ao modelo base; o código legado demonstrado calcula KL somente no primeiro token da resposta, insuficiente como garantia de preservação integral.
- Reproduzir amostragem, sementes, taxa de aprendizado, schedule, clipping, dropout, r/alpha LoRA, masks dos tokens e modo thinking. Não copiar automaticamente os `target_modules` do Qwen2.5 para o Qwen3.5.
- Não emitir alegação de `treino concluído` sem log de passos, hashes de checkpoints recarregados e avaliação independente.

### Etapa C — teste em 11/10/2026 (amanhã)

**Compatibilidade do adaptador:** treinar sobre os pesos Uncensored F16 em revisão fixada. Não presumir que um adaptador PEFT Safetensors será carregável sobre a quantização GGUF no Ollama sem conversão/formato suportado e teste real de fidelidade.

Comparar para **cada entidade**: 9B base vs 9B + LoRA candidato, 7B base atual vs qualquer novo LoRA 7B (se existir), com contexto equivalente; nenhum 6B até selecionar candidato compatível. Comparar 9B em **think=false** e **think=true**.

Métricas mínimas:
- Nome próprio somente quando relevante; evitar prefixo de apresentação em perguntas gerais.
- Diferença Hoshino/Lilith sem roteiro, inclusive `Você é tsundere?`, ciúme contextual, brincadeiras, discordância, vulnerabilidade e humor.
- Diálogo multi-turno de 30+ turnos e duas sessões simuladas; recuperação de memória sem alucinar convivência.
- Raciocínio condicional A/B/C, JSON sem contradição entre justificativa e decisão, verificação independente de ferramentas antes de efeitos.
- Português natural, tarefas gerais de matemática e código, instruções literais, factualidade e incerteza.
- Latência p50/p95, tokens/s, prefill/cache, VRAM/RAM/RSS, tempo de carga e crashes ROCm.
- Teste de ablação: prompt completo vs identidade compacta + LoRA vs prompt operacional mínimo **com memória dinâmica**; comparar economia de tokens e sucesso real.

Não escolher checkpoint só por menor loss. Resultados de testes sintéticos/offline não equivalem a aprovação de convivência natural.

## 4. Faixa 6B: suspensão do download de Yi e prova obrigatória de thinking

**DECISÃO ATUALIZADA: NÃO BAIXAR YI.** A exigência de thinking real ON/OFF é obrigatória. O Yi não atende e não pode ser candidato definitivo. Os comandos abaixo ficam somente como histórico do procedimento experimental anteriormente proposto; **não os executar**. Ainda não foi validado um candidato de aproximadamente 6B com thinking realmente alternável no ambiente local.

Se o limite exato de 6B for flexibilizado pelo operador, comparar em laboratório o **Qwen3.5-4B existente (Alistair)** e, se autorizado, Qwen3-4B ou Qwen3-8B. Os Qwen3 originais e Qwen3.5 possuem chave nativa de thinking; não renomear 4B como 6B, não alterar Alistair, não baixar ou integrar modelo sem aprovação. Medir tempo/qualidade com thinking on e off.

Em **um terminal separado**:
```bash
mkdir -p "$HOME/laboratorio-lora/ollama-yi6b-experimento"
env -u HSA_OVERRIDE_GFX_VERSION \
  OLLAMA_HOST=127.0.0.1:11555 \
  OLLAMA_MODELS="$HOME/laboratorio-lora/ollama-yi6b-experimento" \
  OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NUM_PARALLEL=1 \
  ollama serve
```

Em **outro terminal**, depois de confirmar que 11555 pertence à instância experimental:
```bash
export OLLAMA_HOST=127.0.0.1:11555
export OLLAMA_MODELS="$HOME/laboratorio-lora/ollama-yi6b-experimento"
ollama pull yi:6b-chat
ollama show yi:6b-chat
ollama run yi:6b-chat 'Responda em português: se A depende de B e B é falso, posso concluir A? Explique a condição.'
```

**Verificação adicional**: invocar `/api/chat` com `think:false` e `think:true` e inspecionar **suporte efetivo**, canais da resposta, erros/ignoração do argumento, latência e qualidade. **Yi 6B não tem modo nativo thinking documentado.** Mesmo que responda melhor após `think:true`, sem canal/documentação de suporte não declarar chave funcional. Um erro ao solicitar thinking não é falha de segurança, apenas incompatibilidade do recurso.

Não adicionar `yi:6b-chat` aos catálogos de Hoshino/Lilith, não substituir 7B e não reintroduzir modelos antigos removidos. O download é de alguns GiB; verificar espaço/consentimento de rede e saída do próprio Ollama antes.

## 5. Corpus compartilhado e política de adaptação

- Usar o corpus v2 como referência, com splits e metadados por **entidade**; texto sem system pedagógico de persona na avaliação paramétrica.
- Hoshino e Lilith treinam adaptadores **separados**. Compartilhar cenários de habilidade geral é aceitável; compartilhar indiscriminadamente respostas de personalidade não.
- Os 9B/7B/6B usam os mesmos conceitos, mas exigem tokenização e EOT específicos. No Qwen2.5, o laboratório identificou ChatML automático com system oculto (`You are Qwen...`); conferir explicitamente as máscaras. Qwen3.5/Yi usam seus templates nativos e devem passar pelo teste de prefixo de token.
- Reforçar exemplos de julgamento causal, exceções, reparação de erros, escolhas sob ambiguidade, reação a provocação e sarcasmo, humor natural, limites epistêmicos e contraste entre personalidades. Não treinar falas dos jogos como scripts recorrentes.
- Não inserir bancos reais nem diários privados automaticamente no dataset. Registros experimentais descartáveis podem ser limpos; preservar código, identidades e configurações.
- Treino neural **não deve automaticamente** alterar o `personality.py` ou os bancos. Após prova, estudar sincronização de versões do perfil, distinção entre gosto do usuário e gosto próprio, recuperação pontual de memórias e revisão de traços apenas entre turnos.

## 6. Critérios de aceite e ações futuras no projeto

**9B Uncensored**: só considerar apto se carregar repetidamente, produzir resultados coerentes em think on/off e não falhar no ROCm durante testes longos. A questão do LoRA é compatibilidade de pesos, não a ausência de censura.  
**7B**: preservado como executor atual; fine-tuning validado separadamente, sem prometer thinking nativo.  
**6B**: **sem modelo aprovado**; Yi está **descartado** por não atender ao requisito de thinking real ON/OFF. O Qwen3.5-4B atualmente instalado para Alistair é alternativa de **4B**, e só deve ser avaliado como substituto mediante autorização do operador e isolamento, sem reconfigurar Alistair.  
**Contexto**: só cortar blocos estáticos quando teste A/B demonstrar neutralidade de qualidade e ganho mensurável. Memória, autorização de ferramentas, fatos atuais e proveniência permanecem externos.

**As implementações da Central/código continuam inalteradas por este documento.** A publicação deste plano **não** inicia download, treino, avaliação física ou alteração de modelos. Não há quota/cloud externa ativada. Repositório permanece privado.

## 7. Próxima execução humana/Codex

1. Conferir e baixar o pacote v2 para `~/laboratorio-lora` (sem misturar produção).
2. **Não baixar o Yi**; manter a faixa ~6B em aberto até surgir candidato com thinking nativo comutável comprovável. Se o operador aceitar 4B, testar Qwen3.5-4B existente em isolamento, com ON/OFF.
3. Preparar checkpoint **Uncensored Safetensors `ccharnkij/Qwen3.5-9B-Uncensored`** em pasta isolada e fazer prova física de backward/ROCm; **não** iniciar 10h sem essa prova.
4. Se aprovado, treino piloto → avaliação → treino longo de até 10h com checkpoints e condição de parada.
5. Em 11/10/2026, aplicar o protocolo de avaliação cega e longa; comparar 9B/7B/6B sem inventar métricas.
6. Só discutir adoção de LoRA ou redução de contexto após resultados reais.

**Política de preservação vigente:** preservar estrutura, identidades e configurações reais; testes isolados; dados sintéticos são descartáveis; evitar backups exagerados sem remover proteções contra contaminação/corrupção; o GitHub é privado e não será tornado público.
