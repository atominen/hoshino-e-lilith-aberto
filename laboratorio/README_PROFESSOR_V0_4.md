# Professor Neural v0.4 — implementação inicial

Esta versão **não** instala ou treina pesos automaticamente. Concentra-se no contrato do professor 27B e na preparação independente do treino do **Alistair**. Não altera os modelos nem os bancos da Central de produção.

## O professor não será treinado

- Modelo de inferência escolhido para **teste**, não homologado: `mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF`, arquivo **Q4_K_M** com cerca de **16,5 GB**.
- Download **apenas de um GGUF** com revisão HF fixa e verificação SHA256. Nenhuma etapa PEFT/LoRA para o professor foi implementada.
- Um `llama-server` CPU (`-ngl 0`) é criado em `127.0.0.1:11558`, **descarregado ao final** e mantido sob lock exclusivo do laboratório. Não abre o modelo pela API web do painel.
- A primeira fase cria propostas, **não as transforma automaticamente em treinamento**. JSON estrito; só três perfis: `nenhum=0`, `conservador=10min`, `moderado=30min`. Referências desconhecidas ou duração fora do contrato são recusadas.
- A variante *abliterated* tem recusas reduzidas, mas a qualidade de raciocínio/JSON/curadoria **não foi medida no PC**. Rótulo "uncensored" não implica qualidade superior.

```bash
cd "$HOME/hoshino e lilith"
source "$HOME/laboratorio-lora/.venv-rocm/bin/activate"
python -m laboratorio.professor status

# somente quando download/treino do 9B estiverem totalmente concluídos e houver espaço:
python -m laboratorio.professor download

# preparar servidor CPU de inferência:
cmake --build "$HOME/laboratorio-lora/llama.cpp/build" --target llama-server -j 4
```

Para analisar um recorte do histórico, exporte explicitamente um JSONL sob `~/laboratorio-lora/historicos-curadoria/` com um registro por turno/episódio:

```json
{"entity":"alistair","source_id":"hist:20261011:0001","messages":[{"role":"user","content":"Como está a tarefa?"},{"role":"assistant","content":"Não consigo confirmar conclusão sem consultar a ferramenta."}]}
```

Não copie diários privados, dados de terceiros ou segredos para o treino. O professor só acessa **esse snapshot de laboratório**, não lê os SQLite de Hoshino/Lilith/Alistair. Máximo de 40 registros/2 MiB por análise inicial (o resto precisa ser dividido em lotes; portanto isto **ainda não é** cobertura de todo o dia).

```bash
python -m laboratorio.professor plan \
  --entity alistair \
  --snapshot "$HOME/laboratorio-lora/historicos-curadoria/2026-10-11-alistair.jsonl"
```

A saída vai para `~/laboratorio-lora/professor-27b/propostas/` com `status=PROPOSTA_NAO_APROVADA`. O professor consulta metadados de até dez jobs anteriores da entidade para evitar repetir tentativas, mas ainda **não ingere automaticamente os logs antigos do 9B**, nem promove adaptadores.

## Alistair — um terceiro aluno independente

Manifesto do projeto: Alistair é `coordenador_standby`, textual, CPU, sem memória herdada, e usava um GGUF 4B. Adaptadores exigem a **base de treino em Safetensors**; a variante escolhida para o piloto é `Qwen/Qwen3.5-4B`, multimodal com **encoder visual congelado**. Isso não comprova que é a revisão exata do antigo GGUF de Alistair: **nunca usar seu LoRA no modelo antigo sem validar a base compatível**.

```bash
cd "$HOME/hoshino e lilith"
source "$HOME/laboratorio-lora/.venv-rocm/bin/activate"
python -m laboratorio.alistair status

# gera 51 exemplos de treino, 27 de validação e 16 holdout sintéticos
# não regrava nada que já existe; exige avaliação humana antes da promoção
python -m laboratorio.alistair seed

# baixar somente quando 9B não estiver baixando/treinando e houver >=27 GiB livres:
python -m laboratorio.alistair download

# probe real (ROCm, NF4, forward/backward, visão) antes de treinar:
env -u HSA_OVERRIDE_GFX_VERSION python -m laboratorio.alistair probe

# piloto de até 30 minutos, se probe tiver passado:
env -u HSA_OVERRIDE_GFX_VERSION python -m laboratorio.alistair train --minutes 30
```

Os checkpoints são guardados em `~/laboratorio-lora/modelos-extras/alistair-qwen35-4b/adapters/alistair-piloto/checkpoints/`. **Não há instalação na Central ou conversão GGUF automática nesta fase**; isso depende da homologação do probe e do adaptador. O treino reaproveita a rotina multimodal text-only existente do 9B, com o alvo `alistair` separado. Por segurança, se a arquitetura de 4B não possuir os mesmos LoRA targets, a execução falha antes de treinar.

## Segurança e limites

- O 9B **mantém prioridade**; nenhum novo download ou treino é permitido enquanto o processo/download 9B estiver ativo. O professor também usa lock cooperativo exclusivo.
- Não há permissões de shell para a saída do professor, nem execução de JSON como comandos.
- O professor não desliga o PC nesta fase. Shutdown configurável, fila noturna, avaliação independente e promoção automática exigem implementação e homologação posteriores.
- Não há garantia de que os modelos 27B/4B funcionem na sua máquina, nem teste GPU/RAM feito nesta entrega. Tests `unittest` são apenas invariantes de código e simulações.
- Para não perder tempo/SSD, **não inicie o download do professor 27B durante a transferência ou o treino do 9B**.

## Interface

O painel `http://127.0.0.1:8787` ganhou status somente leitura: presença do GGUF 27B, disponibilidade dos Safetensors 4B, existência do corpus Alistair e contagem de propostas. **Abrir/atualizar o painel não inicia inferência, download nem treinamento**.

## Próximas fases

1. Exportador de histórico com cursores de cobertura e ACL (sem abrir diários); seleção por lotes.
2. Avaliação independente de datasets e protótipos de Alistair.
3. Etapas LoRA e GGUF de 4B com comparação original/adaptado no Ollama isolado.
4. Fila noturna de três alunos, retomada exata com otimizador, promoção transacional e desligamento condicionado.
