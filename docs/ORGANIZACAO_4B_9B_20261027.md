# Organização e seleção temporária: 4B + 9B

Decisão humana mais recente de 27/10/2026: manter somente as famílias de LLM
4B e 9B. Hoshino e Lilith passam a ter 9B principal e o mesmo modelo-base 4B
de Alistair como segundo executor. Isso substitui o mínimo anterior de 7B e a
preservação temporária do candidato 6B. Alistair conserva seu destino configurado.
Correção humana imediata: o modelo do professor é uma exceção e será preservado.

## Execução autorizada

1. Conferir entidades dormindo e ausência de jobs/leases antes de mudar arquivos.
2. Integrar o 4B como executor leve e versão selecionável por Hoshino/Lilith,
   sem identidade embutida de Alistair nem compartilhamento de dados mentais.
3. Reutilizar os blobs locais verificados, sem download. Manter cópias por
   entidade, fonte e hashes. Não afirmar qualidade/desempenho sem ensaio.
4. Remover pesos conversacionais das outras famílias, exceto o professor,
   incluindo bases e
   adaptadores correspondentes; preservar código, datasets, recibos e relatórios.
   Blobs do Ollama só saem após conferir todas as referências remanescentes.
5. Reunir scripts e evidências temporárias identificadas deste projeto dentro
   de `compartilhado/runtime/ensaios/arquivo-20261027/`. Não mover arquivos do
   sistema, do Codex/Claude, jogos instalados ou documentos pessoais por semelhança.
6. Validar seleção, catálogo, integridade e testes. Não acordar entidades nem
   retomar o Minecraft automaticamente por causa desta organização.

O professor e seus pesos ficam preservados; não será iniciado por esta tarefa.
Modelos de transcrição, áudio, percepção e geração de imagens são componentes
das ferramentas e permanecem. O encoder textual/visual do gerador de imagens
não é um terceiro executor de conversa. A limpeza não apaga memórias ou chats.

## Verificação e resultado

- Hoshino/Lilith: `qwen35-9b` principal e `qwen35-4b` leve;4B com contexto
  até8192, ferramentas nativas e admissão serializada peloRM. Cada catálogo
  tem seus próprios arquivos e versão original pinada; fonte neutra, sem
  personalidade de Alistair embutida. Identidades e dados mentais não foram copiados.
- Alistair: seleção/destino preservados. Professor35B: mesmo arquivo, inode,
  tamanho e horário de modificação antes/depois. Não executado pela organização.
- Retirados126arquivos de pesos/adaptadores e6manifestos7B. Remoção bruta:
  47,300GB decimais; novas cópias4B:6,762GB. Redução líquida lógica:40,538GB.
  Não confundir essa conta com medição de blocos físicos em filesystem comCOW.
- CatálogosOllama restantes contêm somente4,2B e9,0B, com0referências quebradas.
  Originais treináveis4B/9B, adaptadores correspondentes, professor, datasets,
  código e relatórios mantidos. Modelos das ferramentas foram preservados.
- 112artefatos/pastas de ensaio foram reunidos em
  `compartilhado/runtime/ensaios/arquivo-20261027/`, inclusive scripts/relatórios
  Minecraft e ensaios antigos encontrados emDocuments/Downloads e`.hoshino_game`.
  O manifesto`organizacao-pesos.json` registra os caminhos anteriores/novos e
  os arquivos retirados. Os caminhos`/tmp` nos relatos anteriores são históricos;
  não foram reescritos como se os ensaios tivessem ocorrido em outro lugar.
  Os atalhos de instalação que apontam para dentro do projeto continuam válidos.
- API real daCentral: Hoshino eLilith listam somente famílias4B/9B;
  Alistair lista4B. Originais presentes/selecionáveis confirmados. Isso verifica
  o catálogo servido, sem alegar inspeção visual de uma janela desktop antiga.
- Teste real isolado do4B naGPU: chamada nativa`confirmar_teste(valor=4)`
  correta, resposta concluída em3,710s; ferramenta não executada. Ao terminar:
  nenhum modelo residente no daemon do ensaio e0leases. Não é benchmark de
  conversa, Minecraft, visão, personalidade ou atividade prolongada das entidades.
- Revisão independente encontrou perda da nova política durante futura
  recuperação9B. Corrigidos os dois caminhos de publicação: agora preservam
  o documento completo, incluindo famílias e versões pinadas; teste de regressão
  observado falhar e depois passar. Seleções explícitas continuam tendo prioridade.
- Treino4B para Hoshino/Lilith não foi autorizado/homologado por esta troca.
  O laboratório mostra essa limitação com rótulo próprio, sem apresentá-lo como
  modelo de teste0,8B nem reaproveitar aprovação do corpus de Alistair.
- Testes específicos:113executores e163contratos de consolidação. Laboratório
  completo:362/362. Suíte principal final:96/96grupos, exit0; resultado no arquivo
  `organizacao-suite-final.log` dentro do arquivo de ensaios acima.

As três entidades permaneceram dormindo; nenhuma partida, treino, professor,
conversa fictícia ou reset mental foi iniciado. A tarefaMinecraft não foi
retomada por esta organização. Documentos anteriores continuam como histórico
dos respectivos ensaios. Esta alteração local não publica pesos/dados noGitHub.
