# Alterações v0.2

- Catálogo real de seis modelos 6B/7B com links e limitações de modalidade.
- Nova seção do painel com seleção de modelo, operação, corpus, duração e adaptador.
- Importação de pares treino/validação JSONL validados pela interface.
- Planos de execução com prévia read-only, confirmação, execução/agendamento via systemd user e logs por job.
- Workers isolados com trava para apenas um experimento v0.2 e bloqueio de concorrência com a automação 9B.
- Treinador textual genérico QLoRA NF4/BF16 experimental, sem fallback silencioso para CPU.
- Exportação GGUF de base textual F16→Q4_K_M e LoRA separado; comparação textual no Ollama 11557.
- Interrupção de jobs próprios com validação de PID e comando.
- Preservados: agendamento do 9B 21h, scripts v1.4, modelos, bancos, runtime, código original e mods/overlays.
- 12 testes unitários e smoke HTTP de catálogo/importação/preview sem downloads passaram no ambiente de preparação.

**Pendente:** testes de hardware ROCm 8 GiB com cada candidato, execução real da conversão de cada arquitetura, visão GGUF/Ollama, memória de produção e interface de logs após job real. Este pacote não é certificação de nenhum desses itens.
