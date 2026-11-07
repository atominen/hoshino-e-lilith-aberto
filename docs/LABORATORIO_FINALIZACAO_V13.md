# Encerramento do Laboratório Neural — v1.3

## Escopo operacional

1. Via painel local `http://127.0.0.1:8787`, seção **Finalizar laboratório**, executar **separadamente, em série**: Alistair 4B, Lilith e Hoshino, com até **10 minutos de treino** cada. O probe/preparo não conta no limite. Não há deploy na Central.
2. **Corpus original por entidade:** Alistair: `datasets-alistair-seed:alistair` (seed **sintético piloto, não corpus histórico validado**); Lilith: `pacote_neural_v3:lilith`; Hoshino: `pacote_neural_v3:hoshino`. Nunca misturar treino, identidade ou memória.
3. **Bases de pesos:** Alistair Qwen3.5-4B HF obrigatório. Para Lilith/Hoshino o operador escolhe explicitamente **Qwen3.5-0.8B** (treino curto já validado) ou **mesma base Qwen3.5-4B** com adaptadores próprios e probe de 12 passos. O 4B não é o 9B original destas entidades. O 9B permanece bloqueado por OOM nos treinamentos prévios.
4. O treinador 4B é `treino_qwen35_entidade.py` com `--vision-cpu`, NF4, checkpoint final isolado; em falha não inicia a próxima entidade. O treinador 0.8B usa `autopreset.calibrate()` e `autopreset.mini()` e preserva os critérios de comparação de loss, velocidade e VRAM.
5. **Professor MoE:** após os três resultados, usar **Preparar professor** no menu e, na seção **Professor MoE**, iniciar as três tarefas `standard` uma por vez, cada qual seguida de auditoria de cópias/diversidade e revisão humana de exemplos. Gerar somente datasets derivados. Propostas rejeitadas não são promovidas automaticamente. A v1.3 pede **novos cenários situacionais**, não cópias do dataset de origem.
6. **Fechar laboratório:** pressionar **Verificar encerramento**. Exige três adaptadores finais, três propostas aprovadas automaticamente **e** conjuntos derivados expressamente aprovados por pessoa. Nunca confundir testes estáticos com execução ROCm ou qualidade real. Nenhum script remove modelos, snapshots, históricos ou checkpoints.

## Limpeza e documentação

- `laboratorio/` mantém código versionável, módulos, testes e documentação. `laboratorio-local/` mantém HF/GGUF, venv, dados, snapshots, logs, backups e checkpoints e deve continuar ignorado pelo Git. `~/laboratorio-lora` é link de compatibilidade.
- A remoção conhecida de 1.024.000.000 bytes em parcial 9B foi concluída. Nenhum outro modelo foi homologado como redundante. Preservar 4B, Yi 6B, Qwen2.5 7B, Hunyuan 7B, 9B, professores, datasets originais e adaptadores.
- Um encerramento válido requer logs, arquivos de checkpoint, auditoria do professor e revisão do diff antes de merge no GitHub. No repositório privado, o código v1.2 está na branch de revisão; v1.3 só deve ser publicada após teste local de interface/ROCm.

## Verificação final

`python3 -m unittest discover -s laboratorio/tests -v` e `python3 -m laboratorio.finalizacao_10min status` são somente leitura (exceto caches Python convencionais). `python3 -m laboratorio.limpeza_segura clean` mostra apenas candidatos sem apagar. Para uso da interface, reinicie somente o backend da Central/painel em uma janela segura; a interface já contém botões de professor e inspeção de jobs.
