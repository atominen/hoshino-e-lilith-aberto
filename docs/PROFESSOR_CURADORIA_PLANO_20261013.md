# Professor — plano incremental de geração e curadoria

Estado inicial: 171 testes do laboratório; checkout com alterações anteriores
preservadas. Backup do código antes desta rodada em
`/tmp/hoshino-professor-curadoria-C2enmH/codigo-antes.tar.gz`.

## Um único pipeline

Painel existente → jobs/snapshots existentes → professor GGUF/Vulkan e lease
existentes → cenário sintético → respostas por turno → auditoria de integridade
→ revisão conversacional separada → proposta → decisões humanas por exemplo
→ exportador existente. Nenhum treinamento é iniciado por geração ou revisão.

Metadados determinísticos são montados pelo código. Não pedir ao professor uma
duração de treino ou confiança na própria resposta. Preservar os contratos do
exportador, aliases finais, autoria, hashes e validação/holdout separados.

Revisão humana persistida na própria proposta, com hash do exemplo, decisão,
motivo, timestamp e opção explícita de usá-lo como referência de comportamento.
Reprovação não apaga o texto. Referências autorais iniciais são rascunhos não
aprovados, não são corpus de treino e só orientam produção após aprovação humana.
Conteúdo alterado invalida decisões anteriores. Exportação e rotina noturna não
podem ignorar uma reprovação humana.

Respostas aceitas permanecem preservadas quando outro exemplo falha. Correções
reutilizam o mesmo cenário e diagnóstico, com tentativas limitadas. Crítico é o
mesmo LLM: revisão separada não significa independência ou prova de naturalidade.

## Comparação controlada

Ensaios manuais locais, serializados, com os mesmos cenários/perfis, registram
prompts, respostas, orçamento, thinking observado, latência, erros e métricas
físicas. Comparar instrução breve, referências contrastivas, escrita por turno,
thinking curto e sampling recomendado. Resultados ficam no diretório de métricas
existente; não são usados como treino/holdout. Nenhum download/cloud.

Primeiro testes offline e navegador com transporte simulado; depois smoke real
na AMD quando houver recursos. Aprovação humana de estilo continua necessária.
