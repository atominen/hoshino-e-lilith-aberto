# v0.5 — 11/10/2026

1. Professor 27B continua SOMENTE GGUF/inferência, agora com orçamento adaptativo de contexto, threads dinâmicos e offload pequeno opcional da GPU somente se a VRAM física livre for mensurável.
2. Dados efetivamente enviados ao professor incluem as propostas do snapshot e metadados dos últimos treinos, sem acesso a SQLite/diários privados.
3. 6B Yi-1.5-6B-Chat adicionado como exceção sem thinking. O catálogo não inventa um 6B pensando; mantém os 7B/8B com alternância exigida.
4. Alistair aparece como aluno selecionável na UI; corpus seed separado. Novo CLI `laboratorio.pilotos` prepara e executa os pilotos Alistair 4B e Yi 6B em sequência, com confirmação explícita.
5. Smoke e comparação de Yi6B não afirmam existir thinking; testa somente o modo normal. Modelos de 7B/8B exigem template ON/OFF não idêntico.
6. Guardas do 9B preservadas; sem downloads ou treinos de qualquer novo modelo quando 9B está ativo/reservado.
7. Testes unitários, syntax checks e API HTTP usados somente para desenvolvimento; nenhum treinamento/transferência real feito na máquina do operador.
