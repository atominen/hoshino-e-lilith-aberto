# Laboratório v1.2 — executor multimodal 0.8B, auditoria do professor e probes por arquitetura

## Diagnóstico de origem (12/10/2026)

Os quatro presets (Hoshino/Lilith, rank 4/8) falharam **antes** de treinar: `treino_micro.py` rejeitava todo modelo com `vision_config`. O modelo Qwen3.5-0.8B local usa essa arquitetura. Esta versão carrega `Qwen3_5ForConditionalGeneration` quando o config é multimodal e escolhe exclusivamente módulos textuais para LoRA; pesos visuais ficam congelados. Não há garantia de sucesso até executar o benchmark ROCm no PC.

Os pesos 4B (Qwen3.5), 6B (Yi1.5/Llama), 7B (HunyuanDense e Qwen2.5) e 9B (Qwen3.5) exigem executores/diagnósticos distintos. `probes_arquiteturas.py plan` é leitura pura, sem GPU. `smoke` executa dois updates LoRA na GPU, um modelo por vez. O `smoke` do **9B** está bloqueado porque o offload de embeddings do v0.9.5 falhou novamente; usar um novo runner de memória antes de liberar. Nenhum resultado é instalado na Central.

## Professor e material SFT

`professor_moe.prepare_from_dataset(home, entity, dataset_id, ...)` constrói snapshots revisáveis exclusivamente a partir de arquivos `*_train.jsonl`; não lê memórias privadas da produção. `snapshots` permite usar evidências históricas previamente curadas, `run` requer autorização expressa, `_validate_teacher_output` valida esquema e IDs; a geração registra propostas ainda não aprovadas; `approved_export` exige IDs revisados pelo operador e cria dataset derivado, sem alterar validação ou iniciar treino.

Esse é um **contrato e fluxo de código**; não é prova de que a geração 35B está funcional hoje. O modelo está estruturalmente presente. `professor_auditoria` mede jobs/propostas e aprovação já gravada, não lê mensagens nem prova qualidade das respostas. A qualidade deve ser medida por diversidade, consistência, verificação factual, aprovação humana e estabilidade do servidor Vulkan com falhas registradas; não usar "sempre sem falhas" como requisito alcançável.

Comandos (após instalação no PC):

```bash
cd "$HOME/hoshino e lilith"
python3 -m laboratorio.professor_auditoria
python3 -m laboratorio.professor_moe status
python3 -m laboratorio.professor_moe snapshots --entity hoshino
python3 -m laboratorio.probes_arquiteturas plan
```

Primeiro repita a calibração 0.8B; se algum candidato passar, o preset poderá selecionar uma configuração pelos critérios atuais (loss de validação, velocidade e VRAM). Teste os 4B/6B/7B com comandos distintos, quando a placa estiver livre. Falhas devem ser registradas com traceback, nunca tratadas como sucesso de treinamento.

## Sincronização GitHub

GitHub `laboratorio/` continha apenas `GUIA_GITHUB.md` na `main` quando da auditoria. Branch de revisão `laboratorio-v11-organizacao-20261012` adicionou documentação e exclusão de `/laboratorio-local/`. A sincronização do código instalado requer Git autenticado localmente e revisão das alterações; use o utilitário de preparo incluído no pacote. Ele não inclui pesos, logs, `.env`, datasets nem históricos.
