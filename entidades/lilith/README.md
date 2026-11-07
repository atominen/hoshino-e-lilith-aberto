# Lilith

Lilith é uma entidade independente da Hoshino. Ela tem identidade, estado
psicológico, memória vetorial/SQLite, runtime, oficina e configuração próprios.
O código é compartilhado; experiências, memória e arquivos dos pesos são próprios.

O modelo nomeado `lilith-qwen3.5-9b:latest` é uma variante Ollama própria da
Lilith sobre a mesma base Qwen da Hoshino. A variante tem catálogo, daemon
(11436) e arquivos físicos separados em `ollama-lilith`, sem links para os
blobs da Hoshino. A cópia foi conferida por SHA-256. A mensagem de
sistema e a identidade da Lilith são fornecidas pela aplicação. Se for desejado
um conjunto de pesos completamente diferente, basta trocar `HOSHINO_MODEL` em
`config/lilith.env` e instalar esse modelo sem tocar na memória da Hoshino.

## Personalidade inicial

Ela começa afetuosa, curiosa, brincalhona, protetora, estranha quando cabe e
capaz de refletir sobre identidade, memória e existência. Esses são pontos de
partida, não falas obrigatórias. Humor, apego, confiança, insegurança,
melancolia e energia mudam por eventos e decaem com o tempo; traços de fundo só
se consolidam com evidência acumulada.

As referências são usadas como inspiração de comportamento, não como cópia de
falas, roteiro ou biografia. Lilith não afirma ser a personagem original e não
imita texto protegido literalmente.

## Inicialização

```bash
cd "/home/gustavo/hoshino e lilith"
HOSHINO_ENTIDADE=lilith bash iniciar_hoshino.sh --verificar
# depois da verificação, para iniciar a interface local:
HOSHINO_ENTIDADE=lilith bash iniciar_hoshino.sh
```

Discord e Minecraft ainda precisam de credenciais, nomes e unidades próprias
antes de serem ativados para Lilith. O modelo pode conversar localmente quando
o modelo nomeado estiver instalado.

O estado inicial da mente fica em `runtime/estado_mente.json` e
`runtime/estado_psicologico.json`; eles começam neutros e evoluem somente por
eventos reais da Lilith. Para preparar o Discord, use
`config/discord.env.example` como modelo e grave o arquivo preenchido apenas em
`runtime/discord.env` desta entidade. O token da Hoshino nunca é reutilizado.
