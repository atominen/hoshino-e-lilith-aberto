# Varredura técnica — 2026-10-04

## Resultado

A suíte completa terminou com `Tudo passou.` após as alterações. O conjunto atual cobre núcleo, integração, continuidade, E2E de turno, tarefas longas, visão, escuta, microfone, diagnóstico, Minecraft, tarefas v28 e as novas melhorias de execução.

## Alterações principais

- Adicionadas primitivas determinísticas `calcular` e `sortear` para aritmética, moeda, dados, inteiros e escolhas sem consumir chamada do LLM.
- Reforçado o roteamento de ferramentas para que termos genéricos não ativem domínios errados; `jogo` não encaminha para xadrez sem evidência de xadrez.
- Adicionada validação do plano de tarefa para detectar ferramentas obrigatórias antes da execução.
- Etapas textuais podem ser resolvidas pelo próprio modelo, mas não podem falsificar operações externas.
- Geração de imagem passa a ser verificada de forma assíncrona: `queued/running` permanece pendente; `done` fecha a verificação.
- A referência a `minha workspace` passa a usar a oficina canônica do projeto.
- O estado mental ganhou uma camada adaptativa de médio prazo separada de identidade, personalidade e humor.
- O modelo de si foi atualizado para explicitar continuidade por camadas, reparo por evidência e tendências como pressões, não falas roteirizadas.
- Busca web atualizada para `ddgs` e script de modelos alinhado ao backend de voz Kokoro/CPU.
- Keep-alive padrão do Ollama ajustado de 24h para 30m.
- Adicionado README e `.gitignore`; `rodar_testes.sh` ficou executável.

## Relação com o material da Lilith

O material foi usado somente como referência arquitetural para capacidades mentais: separação entre identidade estável e estado adaptativo, continuidade relacional, memória significativa, tensões/pressões internas e manifestação por comportamento. Nenhuma personalidade ou conjunto de falas da personagem foi incorporado à Hoshino.
