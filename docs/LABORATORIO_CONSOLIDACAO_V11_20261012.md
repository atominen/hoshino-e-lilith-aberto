# Laboratório Neural — consolidação v1.1 (12/10/2026)

## Estado validado

- A integração Original / Neural 9B foi instalada localmente, mas o adaptador 9B ainda não está pronto para produção.
- Os pesos HF do Qwen3.5-9B-Uncensored tiveram SHA-256 confirmado pelo operador.
- Na RX 6650 XT de 8 GiB, a v0.9.4 concluiu um passo real de LoRA; os testes longos posteriores falharam por OOM ao tentar transferir embeddings de cerca de 1,89 GiB durante o backward. **Treinamento 9B longo permanece bloqueado.**
- A versão local v1.0 de autopresets foi instalada e retirou um parcial de 1.024.000.000 bytes após verificar o 9B definitivo. Rank 4 e rank 8 no Qwen3.5-0.8B falharam nas duas entidades. Não há preset aprovado.
- O professor MoE 35B dispõe, em versões locais anteriores, de funções para preparar snapshots de datasets, gerar propostas, auditar diversidade/cópia, exigir aprovação e exportar somente para datasets derivados. O estado **atual** desse pipeline precisa ser conferido.
- Os pesos Yi 6B, Hunyuan 7B, Qwen2.5-7B, Alistair 4B, professor 27B, professor MoE 35B e base 9B são modelos/formatos distintos e não devem ser excluídos como duplicatas.

## Estrutura proposta

- `laboratorio/`: **código versionável**, incluindo professor, painel, treinamento, presets e testes.
- `laboratorio-local/`: **armazenamento físico privado** com pesos, bibliotecas locais, venv, datasets, snapshots, checkpoints, resultados e logs. Toda a pasta é ignorada pelo Git.
- `~/laboratorio-lora`: link simbólico de compatibilidade para `~/hoshino e lilith/laboratorio-local` após migração *expressamente autorizada*.
- `entidades/`, `app/` e identidades originais não são alterados pela migração.
- A migração real só deve ocorrer após auditar dependências e desligar processos do laboratório; exigir mesmo filesystem para usar rename sem duplicar dados.

## Professor 35B: qualidade e segurança operacional

Etapas: (1) selecionar históricos autorizados ou material padrão **somente do train**; (2) criar snapshot rastreável e identificado por entidade; (3) gerar candidatos com professor Vulkan; (4) validar JSON/esquema, evidências, originalidade, vazamento de dados e diversidade; (5) revisão humana de qualidade e fatos; (6) exportar somente os aprovados para dataset derivado; (7) testar em validação/holdout imutáveis.

Medições obrigatórias: taxa de falhas, tokens/s, latência p50/p95, taxa de aceitação humana, exemplos úteis/s, duplicações, falhas por formato, alucinações e uso de VRAM. O melhor preset depende de medições; **não existe garantia de zero falhas**. Em falhas, manter a ação parada e explicar a causa, em vez de fazer treinamento automático sobre dados não validados.

## Probes curtos — quatro portes

1. **4B:** Alistair Qwen3.5-4B HF (`modelos-extras/alistair-qwen35-4b/hf`).
2. **6B:** Yi1.5-6B HF (`modelos-extras/yi15-6b/hf`).
3. **7B:** Hunyuan-7B HF (`modelos-extras/hunyuan-7b/hf`); Qwen2.5-7B HF é candidato distinto.
4. **9B:** Qwen3.5-9B-Uncensored HF; somente inspeções e experimentos novos que não repitam o offload instável.

Para cada família, começar com leitura de config/shards e versão de tokenizer; em seguida forward, um backward, múltiplos updates, persistência/reload LoRA, testes de regressão e comportamento; registrar duração, loss de validação, VRAM e qualquer falha. Não treinar 6B/7B/9B com o runner BF16 do 0.8B. Não habilitar execução neural na Central até validar o checkpoint.

## Publicação e proveniência

No GitHub remoto, `laboratorio/` contém apenas `GUIA_GITHUB.md` antes da sincronização. As implementações recentes estão na máquina local. Esta atualização documenta decisões, **não afirma que o código executável foi sincronizado nem que testes de GPU foram feitos por GitHub**.

A sincronização de novos scripts deve vir de uma coleta atual de arquivos de código, com inspeção de segredos. Não publicar históricos, identidade/memória, `.env`, GGUF, Safetensors, cache, checkpoints ou venv.
