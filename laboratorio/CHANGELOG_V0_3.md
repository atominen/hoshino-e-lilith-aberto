# Laboratório Neural v0.3 — apenas modelos locais e avaliação thinking ON/OFF

- A página **Modelos e execução** lista apenas checkpoints Safetensors HF concluídos que contenham `config.json`, pesos esperados, `lab_revision.json` e shards conhecidos. Diretórios `.incomplete`, downloads planejados e modelos sem recibo não aparecem.
- Candidatos técnicos restritos: **Qwen3-8B** e **Hunyuan-7B-Instruct**. Ambos anunciam modo de raciocínio alternável nos templates; **não foi homologado um 6B** que satisfaça os critérios nesta rodada. Não baixa modelos automaticamente.
- Comando de download separado: `python -m laboratorio.candidatos list|installed|download qwen3-8b`; downloads de cada candidato são seriais e recusados enquanto o Hugging Face do 9B está ativo.
- Nova operação **cycle_30m**, exatamente 30 minutos de otimização (tempo não inclui download, probes, carregamento e exportação): teste de geração HF `thinking=False/True`, QLoRA NF4 com checkpoint, GGUF base/LoRA e comparação pareada no Ollama isolado com flag `think=false/true`. Qualquer falha para antes da próxima etapa e preserva artefatos já concluídos.
- Travamento anti-concorrência da GPU quando o orquestrador 9B existe (mesmo que pausado), além da janela agendada para 21h e dos processos de download 9B. Não modifica os modelos e bancos de produção.
- Exportação F16 temporária verifica disco disponível antes de iniciar; não certifica GGUF Qwen3/Hunyuan sem os testes de runtime.
- Teste Python no ambiente de desenvolvimento: **17 testes unitários PASS**; verificação sintática JS e smoke HTTP da API `/api/catalog` com zero modelos instalados PASS.

**Limite:** Não foi executado treino na RX 6650 XT, download de pesos, conversão real ou Ollama. Hunyuan-7B havia sido descartado antes; este ensaio não muda o status de produção. Um erro em qualquer etapa não aprova o modelo e não o instala na Central. Sem 6B adequado verificado, deixamos a vaga vazia.

**Inventário flexível:** quaisquer novos checkpoints HF instalados em `modelos-extras/<id>/hf` com recibo/arquivos completos entram na lista mesmo se o ID não estiver no catálogo de candidatos; desconhecidos aparecem somente como inventário, não são habilitados para treino automático.
