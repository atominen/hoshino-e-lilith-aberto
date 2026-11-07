# Laboratório Neural — atualização e histórico de instalação

## Operação atual — organização de 14/10/2026

Continuamos com o **professor 35B**, ainda sem homologação para produzir/aprovar
personalidade sozinho. O [guia operacional](README.md), o
[índice de documentos](../docs/README.md) e o [mapa do projeto](../docs/ESTRUTURA_ATUAL.md)
substituem instruções antigas como ponto de entrada. Organização não faz
sincronização/push nem instala código ou modelos.

Os fontes completos estão agora neste checkout. A interface única abre pela
**Central → Laboratório Neural**, em localhost:8788. Início manual, apenas se
não houver painel ativo: `PYTHONPATH=app:. compartilhado/ambientes/principal/bin/python -B -m laboratorio.labctl serve --port 8788`.
Leia o [README atual](README.md) e a [consolidação verificada](../docs/LABORATORIO_CONSOLIDACAO_20261012.md).

**Não execute os comandos de instalação, agendas ou PIDs dos trechos históricos
abaixo.** Os ZIPs não são fonte de atualização; o timer SIGSTOP e runners antigos
estão aposentados. A sessão noturna exige autorização explícita e usa o
supervisor atual. Modelos, dados e credenciais permanecem locais e fora do Git.

## Registro histórico (não é procedimento de instalação atual)

Esta pasta foi reservada no repositório privado para a **interface local, controle de treino e mods reversíveis**.

**Pacote executável v0.1:** `laboratorio_neural_painel_mods_v0_1.zip` entregue ao usuário no chat de 11/10/2026. Os fontes completos são copiados do ZIP para `laboratorio/` no checkout local; o diretório GitHub neste commit registra a estrutura e a decisão. **Não considere este guia isolado uma instalação pronta para executar.**

```bash
cd "$HOME/hoshino e lilith"
unzip -n "$HOME/Downloads/laboratorio_neural_painel_mods_v0_1.zip" -d .
python3 -m unittest discover -s laboratorio/tests -v
python3 laboratorio/labctl.py serve --port 8787
```

Painel em http://127.0.0.1:8787. Sem acesso externo. O estado local e os snapshots são mantidos em `~/laboratorio-lora/`; mods substituem arquivos somente em snapshots e não alteram originais. Para detalhes: [documentação técnica](../docs/LABORATORIO_NEURAL_E_MODS_20261011.md).

**Agendar 21h:** `python3 laboratorio/labctl.py schedule --pid 66998 --at '2026-10-11 21:00:00'`, após conferir que o PID ainda pertence ao orquestrador. A interface oferece a mesma ação. O download filho não é pausado.

**Limitações:** a Central principal não recebe hot-reload e as cópias não herdam bancos e credenciais da instância real. O laboratório é um mecanismo de desenvolvimento, não uma sandbox de segurança.

## Atualização executável v0.2

A atualização `laboratorio_neural_v0_2.zip` foi entregue ao operador na conversa de 11/10/2026: catálogo de seis candidatos 6B/7B, seletor e importação de datasets, planos read-only, execução/agendamento de QLoRA textual, exportação GGUF e comparação no Ollama isolado. Os scripts executáveis completos **não foram enviados automaticamente ao GitHub por este documento**; precisam ser copiados para a pasta `laboratorio/` local e versionados pelo operador. [Documento técnico](../docs/LABORATORIO_EXPERIMENTOS_6B_7B_20261011.md).

Após copiar e passar nos testes, **reinicie somente o servidor do painel 8787** para aplicar as rotas v0.2. Preserve o orquestrador do 9B pausado e seu downloader ativo. Treino de modelos visuais e Ollama visual continuam bloqueados até haver suporte validado.

## v0.3 — inventário real e ciclo comparativo

O pacote `laboratorio_neural_v0_3.zip` inclui catálogo limitado de modelos com thinking ON/OFF confirmado documentalmente, `laboratorio/candidatos.py` para download explícito e resume dos arquivos parciais, API de inventário que só mostra **checkpoints completos locais**, `cycle_30m` experimental com teste ON/OFF, QLoRA, GGUF e comparação Ollama. Checkpoints locais futuros aparecem por descoberta e ficam só leitura até homologação. **17 testes estáticos passaram**, não há resultado de GPU local. Não tentar downloads em paralelo ao 9B nem prejudicar a janela das 21h. Veja [detalhes](../docs/LABORATORIO_7B_6B_REASONING_LOCAL_20261011.md). Extraia o ZIP no checkout local, teste, e só então versione os scripts no repositório privado.

## v0.4 — professor 27B GGUF e Alistair

O pacote `laboratorio_neural_v0_4_professor_alistair.zip` contém os scripts novos `professor.py`, `professor_schema.py`, `alistair.py`, `treino_qwen35_entidade.py`, painel de status e testes de isolamento de fontes. Um **único arquivo GGUF Q4_K_M do 27B** serve apenas à inferência de curadoria; não se treina o professor. Alistair recebe um piloto **Qwen3.5-4B Safetensors/QLoRA** separado dos adaptadores existentes. 26 testes unitários passaram fora da máquina do operador. Baixar/modelar/treinar continuam comandos explícitos e bloqueados se o 9B estiver ativo. O desligamento do PC e a leitura automática do histórico integral seguem pendentes. [Documento técnico](../docs/PROFESSOR_NEURAL_27B_ALISTAIR_V0_4_20261011.md).

**Os arquivos executáveis completos do pacote não foram automaticamente enviados ao repositório por esta documentação**: copie o ZIP no checkout, rode a suíte e versione `laboratorio/` manualmente; não envie pesos, segredos, bancos ou logs privados.

## v0.5 — professor com recursos dinâmicos e 6B

Código executável completo entregue no ZIP `laboratorio_neural_v0_5_professor_6b.zip` (35 arquivos). Adiciona `recursos_professor.py`, `pilotos.py`, testes e README de instalação; professor 27B continua só inferência GGUF. O UI **permanece somente com checkpoints instalados**, não mostra escolhas futuras. Alistair 4B e Yi-1.5-6B entram em fila de pilotos 30m, com guardas intactos contra concorrência com 9B. [Documento v0.5](../docs/PROFESSOR_NEURAL_RECURSOS_DINAMICOS_6B_V0_5_20261011.md). Este guia no GitHub não contém os executáveis do ZIP até o operador sincronizar o checkout privado.
