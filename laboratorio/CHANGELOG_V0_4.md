# Mudanças do Laboratório v0.4 — 11/10/2026

- Novo professor exclusivamente **GGUF 27B Q4_K_M** para inferência local em CPU; download explícito e SHA256.
- Analisador/validador JSON de propostas com IDs reais e isolamento por entidade, sem executá-las automaticamente.
- Auditoria limitada de histórico de jobs por entidade; nenhum acesso direto a diários/SQLite.
- Novo aluno Alistair 4B com download separado de Safetensors, seed de piloto, prova ROCm e treinamento até 30 minutos.
- Adaptador de Alistair sempre isolado, não instalado no Ollama do projeto nem mesclado aos modelos antigos.
- Painel mostra professor e Alistair como status, sem listá-los como candidatos futuros instalados na UI operacional.
- Nesta fase não foi implementado desligamento do computador, promoção automática ou execução do 27B/4B na GPU real.

Instruções completas: `laboratorio/README_PROFESSOR_V0_4.md`.
