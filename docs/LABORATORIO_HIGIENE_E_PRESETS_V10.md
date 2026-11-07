# Laboratório Neural — higiene, microtreinos e presets automáticos v1.0

## Resultado da noite de 12/10/2026

- Os pesos HF do Qwen3.5-9B-Uncensored estão completos e SHA-256 verificado: `95117c3faed067c2a48dd3ddebf16209c4c6b60d1714ef5dd32cf784e2e053fc` (18.819.721.632 bytes).
- ROCm RX 6650 XT 8 GiB: NF4 Qwen3.5-9B multimodal carregou; LoRA textual de 10.819.584 parâmetros teve **um update** bem-sucedido em v0.9.4, mas treino noturno subsequente caiu por OOM.
- Na v0.9.5 o probe de 12 passos também caiu por OOM ao tentar realocar `1,89 GiB` via `accelerate/hooks.py` (embeddings congelados offload CPU). Não há aprovação de estabilidade.
- **Treinamento longo 9B suspenso**. Não retomar o antigo orquestrador; não apagar os parciais sem verificação. Experimentos posteriores exigem nova política de movimentação de embeddings e múltiplos passos sem OOM.
- Central: integração reversível Original/Neural 9B v0.9 já instalada no computador pelo operador. O modo Neural 9B **não deve ser liberado** sem adaptador compatível convertido e importado. O preset de microtreino 0.8B **não é adaptador para 9B**.
- Os modelos Yi-1.5-6B, Hunyuan-7B, Qwen2.5-7B, Alistair 4B, professor 27B e professor MoE 35B são **distintos**, não duplicatas só por tamanho/nome. Mantê-los até prova de obsolescência.

## Arquitetura da integração v1.0

A Central permanece executando `app/ui/central_native.py` e `app/ui/control.js`. Sua entrada **Laboratório Neural**, criada na integração anterior, abre o painel HTTP local (127.0.0.1:8787). Nesta atualização, somente três arquivos do próprio laboratório são alterados: `laboratorio/painel.py`, `laboratorio/web/index.html`, `laboratorio/web/app.js`. Um GET local novo `/api/presets-auto` é **somente leitura**, não carrega GPU nem dispara tarefas. A UI visualiza resultados experimentais e limites.

Os módulos novos `laboratorio/limpeza_segura.py`, `laboratorio/treino_micro.py` e `laboratorio/autopreset.py` são independentes. Estado/relatórios vão para `~/laboratorio-lora/controle-laboratorio/presets-auto`. Pesos/adaptadores experimentais, se explicitamente produzidos, permanecem lá: não entram em `entidades/{hoshino,lilith}/identity` ou `memory`, nem em Ollama.

## Limpeza sem falsos duplicados

1. `python3 -m laboratorio.limpeza_segura audit` — tamanho de pastas preservadas e cópias **byte a byte idênticas** v2↔v3 (arquivos pequenos). Não apaga nada.
2. `python3 -m laboratorio.limpeza_segura clean` — prévia exclusiva de parciais HF vinculados ao SHA do 9B; nenhum outro arquivo é elegível.
3. `python3 -m laboratorio.limpeza_segura clean --apply --confirm APAGAR_SOMENTE_PARCIAIS_9B` — **exclusão real** dos `.incomplete` com SHA incorporado no nome **somente se** o arquivo final de 18,8 GB ainda existir com tamanho e hash verificados e nenhum downloader estiver ativo. É irreversível sem backup. Se não aceitar, não executar.

Os nomes idênticos em `pacote_neural_v2` e `pacote_neural_v3` não são por si só autorização para exclusão da v2, pois scripts podem referenciá-la. Mesmo conteúdo HF/GGUF em formatos distintos não significa duplicação física.

## Microtreinos independentes e resultados efetivos

- Modelo experimental: `~/laboratorio-lora/modelos/qwen3.5-0.8b` BF16, texto puro, local e até 4 GiB Safetensors.
- Corpora por entidade: `pacote_neural_v3/{hoshino,lilith}_{train,validation}.jsonl`; `*_test.jsonl` permanece **intocado** como holdout.
- Tipo implementado: **LoRA BF16 SFT textual**, quatro updates no benchmark e até 2–15 minutos no mini-treino opcional.
- `rank 4` versus `rank 8`, com máximo de 256 tokens (comprimentos dinâmicos); mesmas amostras e validação fixadas.
- Ranking empírico: melhoria da cross entropy em seis exemplos de validação, throughput e pico de VRAM; falhas e OOM são excluídos. **Quatro updates não demonstram generalização, fidelidade de personalidade ou estabilidade longa.**
- Calibração: `python3 -m laboratorio.autopreset calibrate --entity both --confirm CALIBRAR_GPU` (até 4 execuções curtas sequenciais na GPU; falhas são registradas).
- Automação completa, opcional: `python3 -m laboratorio.autopreset auto --entity both --minutes 3 --confirm CALIBRAR_E_TREINAR_CURTO`. Refaz o benchmark a cada invocação e usa o preset medido para até 3 minutos de LoRA em cada entidade, sequencialmente; registra falhas isoladas.
- Resultado: `python3 -m laboratorio.autopreset status`. Sem benchmarks reais, nenhum preset é proclamado o melhor.
- Mini-treino controlado: `python3 -m laboratorio.autopreset mini-train --entity hoshino --minutes 3 --confirm TREINO_CURTO_ISOLADO` (requer calibração compatível com modelo/corpus nas últimas 24 horas). Repetir com `lilith` quando Hoshino encerrar. Saída isolada e nunca implantada automaticamente.
- O mini-treino é **somente um experimento**; um LoRA 0.8B não funciona sobre um modelo Qwen3.5-9B.

## Próximas famílias de treinamento — não implementadas no v1.0

1. **QLoRA NF4 7B**: modelo base Qwen2.5-7B HF local, requer microprobe de VRAM e kernels ROCm. O modelo 7B GGUF não se confunde com o HF 7B.
2. **DPO / ORPO**: refinamento por pares `chosen/rejected`. Dataset v3 atual é de conversas de SFT, **não possui comprovação de preferências rotuladas**. Criar corpus de preferências aprovado e holdout antes de executar.
3. **Distilação supervisionada de respostas**: apenas exemplos revisados, com contrato de origem, não copiar respostas brutas do professor sem auditoria.
4. **Continued pretraining**: exige corpus grande de texto bruto e avaliação de esquecimento; não usar conversa de identidade como pré-treino bruto.
5. **LoRA especializada por competência** (conversa, ferramentas, raciocínio, visão): avaliação por eixo, roteamento explícito e adaptadores compatíveis por arquitetura.
6. **9B multimodal com offload correto de embeddings**: substituir a cópia completa (1,89 GiB) por `torch.nn.functional.embedding` local no CPU, movendo apenas as saídas necessárias, se validado em backward; desempenho PCIe e compartilhamento `lm_head` precisam ser verificados. O v1.0 não faz essa mudança, porque ainda não foi testada.

## Reversibilidade, logs e garantias

- Instalador usa SHA-256 dos três arquivos de UI/API coletados antes de qualquer modificação; se divergirem, **falha sem gravar**. Não editar fontes reais às cegas.
- Gera backup em `~/laboratorio-lora/backups/lab-higiene-preset-v10-*`, com manifesto de restauração.
- `.env`, identidade, memória, modelos principais, venv ROCm, caches de Ollama e os antigos logs **não são modificados**.
- O instalador e os testes deste pacote foram validados fora do computador; microtreinos reais somente poderão ser aprovados após execução ROCm local.
- No modo `mini-train`, um `result.json` registra loss, tempo, VRAM, hardware, dataset/config hash e aviso de limitação. Não use esses adaptadores na Central até exportação e avaliação completas.
