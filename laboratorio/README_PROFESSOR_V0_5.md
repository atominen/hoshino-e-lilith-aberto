# Professor Neural v0.5 — contexto dinâmico + pilotos 4B e 6B

## Regras desta versão

- **Professor**: `mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF`, um **único GGUF Q4_K_M** de inferência. **NUNCA treinar o professor**; nenhuma opção de SFT/LoRA para ele. Não baixar seus Safetensors.
- **Alistair**: modelo-aluno `Qwen/Qwen3.5-4B` **em Safetensors completos** + corpus sintético independente (51 treino / 27 validação / 16 holdout). Probe antes de LoRA 30m. Base GGUF antiga do Alistair não é compatibilidade garantida com esse adaptador.
- **6B sem thinking**: `01-ai/Yi-1.5-6B-Chat`. Exceção experimental explícita ao requisito anterior. Familia Yi já foi rejeitada uma vez; serve como baseline a retestar, não aprovação antecipada.
- **6B com thinking**: **não foi encontrado/confirmado** até esta revisão um checkpoint confiável de ~6B com alternância ON/OFF nativa e desempenho adequado. Não inventar esse recurso. Se desejar uma comparação com thinking numa faixa adjacente, usar **Hunyuan-7B-Instruct (7B)**; o **Qwen3-8B (8B)** permanece alternativa mais fácil de validar. Ambos requerem teste ON/OFF real antes do treino. SmolLM3-3B alterna thinking, porém tem 3B e não substitui um 6B.
- Painel `:8787` mostra somente pesos Safetensors **completos** com recibo em disco. Candidatos ainda não baixados ficam visíveis apenas no comando `python -m laboratorio.candidatos list`, sem poluir o painel.
- Não iniciar downloads ou treinamentos **enquanto o 9B estiver baixando/reservado**, nem remover os bloqueios `gate_9b`.
- Nenhuma implantação na Central, promoção automática, shutdown ou treino do professor.

## Política dinâmica de recursos do professor

`laboratorio/recursos_professor.py` mede `MemAvailable`, CPUs lógicas e VRAM física quando exposta por `amdgpu` no sysfs (GTT não conta). Computa orçamento conservador do contexto a partir dos bytes do snapshot + metadados das execuções anteriores e inclui reserva para resposta. Seleciona o **menor contexto suficiente** entre 4096, 8192, 12288, 16384, 24576, 32768 que caiba no orçamento de RAM; não despeja todos os dados em um contexto pequeno nem assume que um contexto 32K significa 32K útil de fatos. Ao ultrapassar os limites recusa e exige divisão em lotes.

Ajusta threads para até CPU lógica menos duas (mantendo sistema responsivo), com opção de teto `--max-threads`. `--gpu-layers auto` solicita **apenas quatro camadas experimentais** se medir pelo menos 6 GiB físicos livres; sem medida confiável fica CPU. Pode definir `--gpu-layers 0` para garantir CPU. Trata-se de previsão, não certificação HIP/VRAM nem otimização de tokens/s; o backend pode falhar ao carregar. A política é registrada nas propostas.

O professor **não acessa bases SQLite nem diários privados**: só JSONL exportado explicitamente para `~/laboratorio-lora/historicos-curadoria/`, com até 40 episódios por análise, e metadados não privados dos jobs anteriores. Ele é descarregado ao finalizar.

## Instalar v0.5 sem apagar mods

No checkout privado do projeto (cuidado com o nome com espaços):

```bash
cd "$HOME/hoshino e lilith"
cp -a laboratorio "$HOME/laboratorio-lora/backup-laboratorio-v0_4-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$HOME/laboratorio-lora/instalacao-v05"
unzip -o "$HOME/Downloads/laboratorio_neural_v0_5_professor_6b.zip" -d "$HOME/laboratorio-lora/instalacao-v05"
rsync -a --exclude='mods/' "$HOME/laboratorio-lora/instalacao-v05/laboratorio/" ./laboratorio/
python3 -m unittest discover -s laboratorio/tests -v
```

Reiniciar apenas `labctl.py serve --port 8787` para atualizar o servidor web. Não interromper `baixar_9b.py` ou `orquestrar_9b.py`.

## Verificar estado; comandos que NÃO treinam nem baixam

```bash
cd "$HOME/hoshino e lilith"
source "$HOME/laboratorio-lora/.venv-rocm/bin/activate"
python -m laboratorio.professor status
python -m laboratorio.alistair status
python -m laboratorio.candidatos list
python -m laboratorio.candidatos installed
python -m laboratorio.pilotos plan --six-entity hoshino
```

Se o 9B estiver ativo como no log de 11/10/2026, os comandos abaixo **irão recusar** download/treino. Não contorne esse bloqueio. Primeiro esperar concluir a automação ou encerrá-la de forma ordenada e rever o agendamento.

## Downloads explícitos, somente com 9B finalizado

```bash
# Conferir antes: pgrep -af 'orquestrar_9b.py|baixar_9b.py'
df -h "$HOME"
python -m laboratorio.alistair download            # HF Safetensors 4B ~9,3 GB
python -m laboratorio.candidatos download yi15-6b  # HF Safetensors Yi 6B ~12 GB
# Professor, somente quando disco/rede permitirem:
python -m laboratorio.professor download            # SOMENTE GGUF 27B ~16,5 GB
```

NÃO executar os três downloads simultaneamente; 9B + 4B + 6B + 27B e intermediários GGUF podem ultrapassar o espaço livre. Recomenda-se 4B primeiro, treinar/avaliar, só depois 6B; professor GGUF por último se faltar disco. `HF_HUB_DISABLE_XET=1` evita o caminho Xet do problema anterior, mas pode retransferir dados parciais.

## Piloto Alistair + Yi6B em sequência (após downloads)

```bash
python -m laboratorio.alistair seed     # SE ainda não houver corpus; recusa sobrescrever
python -m laboratorio.pilotos plan --six-entity hoshino
# só se ready_to_run=true e nenhum trabalho 9B:
env -u HSA_OVERRIDE_GFX_VERSION \
python -u -m laboratorio.pilotos run --six-entity hoshino --confirm \
  2>&1 | tee "$HOME/laboratorio-lora/logs/pilotos-4b-6b.log"
```

Alternativas para o aluno do 6B: `--six-entity lilith` ou `--six-entity alistair`. O 4B sempre treina o **Alistair**, com seu corpus separado. O Yi6B recebe **somente o corpus da entidade escolhida**. O piloto executa teste 4B real, treino 4B de 30m, smoke de Yi6B sem thinking, treino Yi6B de 30m, tentativa GGUF e comparação isolada. A duração total pode ser superior a 1h, e falhas de ROCm/LoRA/GGUF são esperadas e bloqueiam o próximo passo. Nenhum treino físico foi realizado quando o ZIP foi empacotado.

## Professor com contexto dinâmico (somente com snapshot exportado)

```bash
# Antes é necessário instalar o GGUF e copiar um JSONL permitido para historicos-curadoria.
python -m laboratorio.professor plan --entity alistair \
  --snapshot "$HOME/laboratorio-lora/historicos-curadoria/alistair-dia.jsonl" \
  --gpu-layers auto --max-ctx 32768 --timeout 1800
```

Para testar fallback CPU explícito: `--gpu-layers 0`. Se o hardware não tiver memória suficiente para o lote, a ferramenta pede dividir o JSONL; NÃO força swap nem reduz o contexto truncando evidências.

## Importante

- O `cycle_30m` exige 30 minutos de **otimização**, não de execução total. Pode falhar por incompatibilidade da variante/PEFT/GGUF ou falta de VRAM/disk.
- O teste de modos de thinking `ON/OFF` é somente para Qwen3-8B/Hunyuan-7B. Yi6B executa somente o modo textual normal; não registra falso thinking.
- Manter o 9B prioritário, os JSONL e adaptadores por entidade isolados, e os modelos da Central intocados.
- Resultados de testes de software não substituem `probe` real na RX 6650 XT.
