# Professor Neural v0.5 — recursos dinâmicos, Alistair 4B, exceção Yi 6B
Atualização do laboratório em 11/10/2026. **Pacote executável entregue no chat**: `laboratorio_neural_v0_5_professor_6b.zip` (SHA256 `f25eed124aaff51b4789a135b2e2e1174f76e7c42099ad600e53529e822ab1eb`; 35 arquivos na pasta `laboratorio/`). **Este commit registra as decisões, não instala os scripts no PC do operador**; os arquivos devem ser copiados do ZIP para o checkout e sincronizados do checkout para o GitHub privado. Nenhum peso, banco mental ou diário é enviado.

## Autorização e restrições
O usuário autorizou o **professor Qwen3.5 27B abliterated em GGUF somente inferência**, contexto dinâmico e utilização responsável dos recursos disponíveis; autorizou **pilotos de 30 minutos de Alistair 4B** e **6B**, removendo exclusivamente para 6B a obrigação de thinking ON/OFF. **Os 7B continuam obrigatoriamente com thinking comutável**. Não autoriza treino dos pesos do professor, promover modelos à Central real ou alterar históricos originais.

## Modelos
- Professor: `mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF`, arquivo `Huihui-Qwen3.5-27B-abliterated.Q4_K_M.gguf`, ~16,5GB. Sem Safetensors/LoRA próprios.
- Alistair: `Qwen/Qwen3.5-4B` Safetensors para treino individual; executor Ollama anterior de origem Unsloth GGUF não recebe automaticamente adaptador gerado de base diferente.
- 6B exceção sem thinking: `01-ai/Yi-1.5-6B-Chat` (config `LlamaForCausalLM`, BF16 ~12,1GB). Reavaliar apesar da rejeição anterior. No ciclo comparativo, executar apenas resposta direta, sem fingir um canal thinking.
- 7B thinking obrigatório: `tencent/Hunyuan-7B-Instruct` (comutação documentada), requer validação real de template e backend; alternativa maior `Qwen/Qwen3-8B` com switch comprovado na ficha. **Nenhum 6B thinking ON/OFF nativo suficientemente comprovado foi encontrado**: SmolLM3-3B pensa, mas tem 3B; derivados Qwen3-6B não verificados não foram incluídos.

## Mudanças de software
- `laboratorio/recursos_professor.py`: estima os tokens do lote e reserva saída, mede `MemAvailable` físico, CPUs lógicas e VRAM física `mem_info_vram_*` (não GTT), escolhe menor contexto suficiente entre 4096, 8192, 12288, 16384, 24576, 32768 que caiba na RAM. Rejeita material maior, não trunca silenciosamente e não força uso de swap. CPU usa até threads lógicas-2. GPU opcional `--gpu-layers auto` solicita apenas quatro camadas se >=6 GiB físicos livres; `--gpu-layers 0` é fallback CPU explícito. Heurísticas, não benchmark ROCm.
- `professor.py`: passa metadados dos trabalhos passados da mesma entidade ao prompt; registra política de recursos no plano proposto; descarrega `llama-server` em `finally`. Professor só lê snapshots autorizados de até 40 episódios em `~/laboratorio-lora/historicos-curadoria/`.
- `catalogo.py`: adiciona somente Yi6B não pensante ao catálogo técnico CLI; **painel lista apenas checkpoints Safetensors locais completos**, preservando comportamento v0.4.
- `experimentos.py`/`trabalhador.py`: seleciona corpus v3 Hoshino/Lilith ou Alistair seed, preserva isolamento por entidade; em 6B não inventa thinking ON/OFF e para 7/8B rejeita template ON/OFF idêntico. Corrige guarda 9B também no ciclo completo.
- `treino_texto.py`: exige ROCm e fronteira verificável de tokens assistant, não trunca silenciosamente se mais de 20% dos exemplos ultrapassarem 384 tokens.
- `pilotos.py`: fila explícita `plan` / `run --six-entity <hoshino|lilith|alistair> --confirm`, primeiro probe e treino Alistair 4B, depois smoke OFF, treino 30m, GGUF e comparação isolada Yi6B. **Não baixa modelos automaticamente**, não implanta na produção, não desliga o PC. Alistair 4B e Yi6B são checkpoints e adaptadores independentes.
- Painel v0.5: opções de entidade Alistair, contexto do professor, distinção thinking e correção do seletor de dataset para `cycle_30m`.
- `README_PROFESSOR_V0_5.md` documenta instalação e operação.

## Estado operacional conhecido
No log fornecido pelo usuário, a v0.4 foi instalada e passou 26/26 testes, corpus Alistair gerado (51 treino/27 validação/16 holdout), mas `base_complete=false`, `probe_passed=false`, `trained_in_this_session=false`; professor `installed=false`. A tentativa de baixar Alistair e treinar foi **corretamente recusada pelo guard `gate_9b`**: downloader 9B ativo e orquestrador 9B mesmo que pausado, reservado para 21h. **Nenhum treino de Alistair ou do Yi6B foi executado por esta implementação**, pois as ferramentas não têm acesso ao PC pessoal.

## Validação
35 testes de desenvolvimento PASS, `compileall` Python PASS, `node --check` JS PASS, smoke HTTP localhost para `/api/catalog` e `/api/professor-status` PASS; `/api/catalog` retorna [] quando não há modelos instalados. **Nenhum benchmark real de ROCm, download de Yi6B/4B/27B, inferência 27B, treino ou conversão GGUF foi realizado.**

## Próximos comandos, após instalar ZIP
```bash
cd "$HOME/hoshino e lilith"
source "$HOME/laboratorio-lora/.venv-rocm/bin/activate"
python3 -m unittest discover -s laboratorio/tests -v
python -m laboratorio.professor status
python -m laboratorio.alistair status
python -m laboratorio.pilotos plan --six-entity hoshino
```
**Não executar downloads enquanto o 9B estiver ativo/reservado.** Quando o 9B terminar e houver disco livre: `python -m laboratorio.alistair download`, `python -m laboratorio.candidatos download yi15-6b`, e somente com duas bases íntegras e datasets: `env -u HSA_OVERRIDE_GFX_VERSION python -u -m laboratorio.pilotos run --six-entity hoshino --confirm`. Professor `python -m laboratorio.professor download` baixa **apenas GGUF** quando a infraestrutura estiver livre, sem cron automático. Não remover proteções de recursos.

## Pré-voo final de contexto do professor

A versão final do ZIP chama `llama-server /tokenize` após carregar a instância, conta os tokens efetivos do conjunto de instruções + histórico + metadados e reserva 1600 tokens de resposta mais 384 de protocolo antes de aceitar o plano. Se `/tokenize` não fornecer contagem ou se o total exceder o contexto escolhido, recusa com erro e exige dividir o snapshot. Isto impede depender apenas de uma heurística aproximada de bytes por token e mantém transparência sobre documentos não incluídos.
