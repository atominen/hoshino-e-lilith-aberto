# Organização, limpeza e atualização privada — 24/10/2026

## Pedido e destino

Organizar/atualizar a documentação, remover material desnecessário do experimento
Qwen3-4B, preservar Alistair e pesquisar um substituto 6B. O pedido também
autoriza publicar o estado do projeto no GitHub privado.

Repositório confirmado pela API: `atominen/hoshino-e-lilith`, **privado**, com
permissão de escrita. Entrega na branch existente
`laboratorio-v11-organizacao-20261012`, [PR #1 em rascunho](https://github.com/atominen/hoshino-e-lilith/pull/1).
Base local/remota reconciliada: `6441a7c275519af7dc00d004ca1b13334ab69e9f`.
Não fazer merge em `main`, force push, rebase ou alterar o PR #2 do Xbox.

## Organização e remoção

- README e índice apontam para o estado atual, decisões 6B/7B/9B, pesquisa
  pendente e resultado real do agendamento de 23–24/10, que não iniciou.
- Relatório de substituição consolidado: situação atual primeiro, limpeza
  autorizada e resumo histórico depois. Recibos/falhas não foram apagados.
- Qwen3-4B experimental removido: originais, GGUF, cópia de execução, alias
  e seus metadados exclusivos. **13.055.590.400 bytes liberados (~13,06 GB)**.
  Com a retirada anterior do Yi, total histórico de ~36,20 GB. Os pesos não
  têm backup; recuperação exigiria download da revisão e nova importação.
- Script de benchmark/importação 4B e comando específico `download-reference`
  retirados. Registro `retired` e testes impedem reinstalação por planos antigos.
  Sem prune global ou exclusão de código de diagnóstico necessário.
- Todos os outros manifestos e hashes das configurações selecionadas foram
  conferidos intactos na limpeza. Alistair mantém seu Qwen3.5-4B; 7B/9B,
  professor, voz, imagem, memórias, identidades e corpora preservados.

Detalhes: [retiradas e estado dos executores](SUBSTITUICAO_YI_EXECUTOR_RAPIDO_20261024.md).

## Conteúdo local acumulado incluído na entrega

Preservar as mudanças existentes de 20–24/10: sala global/direto e audiência,
nomes individuais, cartões/senha/importância, áudio e ferramentas agrupadas,
despertar privado, continuidade e recibos de comandos, memória/oficina,
autonomia e notas de contexto, percepção de transcrição e perfis de recursos.
Incluem-se implementação, UI, testes e documentação correspondente; esta
sincronização não reexecuta essas operações nem recarrega código em produção.

Inclui-se também a interface de sessão personalizada já implementada, com os
relatórios que distinguem a autorização antiga, agendamento perdido e nenhum
treino novo. Publicar o código não autoriza partida atrasada ou outra sessão.

## Pesquisa de substituto, sem instalação

[Triagem 6B](CANDIDATOS_6B_20261024.md): Qwen3-6B podado de Parmanu é candidato
à análise de compatibilidade, com 6,198 bilhões de parâmetros declarados e
originais públicos. A arquitetura podada ainda não tem conversão comprovada
no backend local. Alternativas e motivos para não instalá-las estão registrados.
Nenhum novo peso foi baixado, carregado, treinado, aprovado ou ativado.

## Verificações e limites

- Regressões de retirada/catálogo: **20/20 testes**, exit 0.
- Suíte oficial offline completa: **89/89 grupos**, exit 0, em
  `/tmp/github-sync-oficiais-20261024.log`.
- Sintaxe AST das 93 fontes Python alteradas/novas e links Markdown locais
  conferidos; nenhum destino ausente. Diff preparado sem erros após retirar
  uma linha vazia excedente no fim de `speech_perception.py`, sem mudar lógica.
- Conteúdo preparado: **124 arquivos de fontes/testes/documentação**, sem
  bancos, configurações reais, credenciais, pesos ou logs privados. Busca de
  padrões de tokens/chaves e de valores secretos locais conhecidos: sem achados;
  valores secretos não foram impressos nem enviados.
- Entrega por push normal na branch existente; confirmar SHA remoto após o envio.
  Manter PR em rascunho e repositório privado.

Testes offline não aprovam personalidade, modelos, hardware, uso prolongado,
recarga da Central ou rotina de treinamento. Nesta rodada não se acordou
entidade, não se abriu chat/memória privada nem houve inferência, professor,
quota de voz, cloud, concorrência GPU, reinício ou desligamento de serviço.

## O que permanece somente local

Pesos preservados, bancos/vetores/diários/conversas, configurações reais,
credenciais, ambientes, corpora privados, caches e logs/recibos de runtime.
Não foram removidos por estarem ignorados no Git. Os 44 arquivos apagados
pertenciam somente aos alvos experimentais pinados e autorizados.
