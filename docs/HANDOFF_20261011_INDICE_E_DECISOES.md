# CONTINUIDADE DO PROJETO — leia no início do próximo chat (11/10/2026)

> **Histórico, não ponto de entrada atual.** Em 14/10/2026 a documentação foi
> organizada no [índice por assunto](README.md), com [guia operacional](../laboratorio/README.md)
> e [mapa do projeto](ESTRUTURA_ATUAL.md). O professor atual continua 35B.
> Não repetir instalação, limpeza de modelos ou retomada de PIDs com base
> nos estados antigos abaixo; os relatórios originais foram preservados.

> **Estado da captura: 11/10/2026, aproximadamente 13:58, America/Sao_Paulo.**
> **Projeto/repo privado:** `atominen/hoshino-e-lilith`.
> **Este documento é um ponto de entrada resumido e autocontido**; duas páginas adicionais contêm pormenores de todos os subsistemas e logs. Pode haver eventos posteriores, então confirmar estado real antes de agir.

## Documentos principais, por ordem de leitura

1. **[Operação 9B e último estado real](HANDOFF_20261011_OPERACAO_9B_ESTADO_REAL.md)** — processo morto, peso parcial, cronologia da falha, estado persistido desatualizado, timer 21h obsoleto, passos seguros.
2. **[Arquitetura completa do Professor Neural e Laboratório](HANDOFF_20261011_ARQUITETURA_PROFESSOR_E_LABORATORIO.md)** — Hoshino/Lilith/Alistair, personalidade/memória, ideias de aprendizagem contínua, componentes, modelos, v0.1–v0.5, progresso e próximos trabalhos.
3. [Plano detalhado original e v1.4 9B](OPERACAO_UNICA_9B_UNCENSORED_VISAO_20261011.md) — procedimentos históricos; **não executar novamente a exclusão de modelos**.
4. [Laboratório v0.5](PROFESSOR_NEURAL_RECURSOS_DINAMICOS_6B_V0_5_20261011.md) e [v0.4](PROFESSOR_NEURAL_27B_ALISTAIR_V0_4_20261011.md) — contratos do professor/contexto, testes 4B/6B.
5. [Memória, personalidade e revisão noturna](CONSOLIDACAO_COGNITIVA_20261010.md), [proveniência da reflexão](REFLEXAO_EVIDENCIAS_RAM_20261009.md) e [preservação](POLITICA_PRESERVACAO_PROJETO.md).
6. [Histórico das decisões e exceções](../ESCOPO_CONGELADO.md).

## Resumo imediato do operador

**Máquina:** Linux Mint, Ryzen 5 5500 (6C/12T), RAM 32GiB, RX 6650 XT 8GiB `gfx1032`, ROCm/PyTorch experimental em `~/laboratorio-lora/.venv-rocm`; `HSA_OVERRIDE_GFX_VERSION` deve ser removido **somente** dos processos de treinamento GPU, sem adulteração global; SSD do projeto montado na partição `/dev/nvme0n1p2` (817G total). Medição mais recente: **55G livres, 93% usado**; 25,82GiB RAM disponível no teste anterior. A GPU tem 8 GiB físicos; GTT e swap não equivalem a VRAM.

**Projeto:** `~/hoshino e lilith/`, repositório GitHub **privado**, agentes independentes **Hoshino, Lilith, Alistair**, bancos/identidades/diários próprios. **Não apagar memórias, SQLite, credenciais, pesos, checkpoints ou variantes anteriores sem autorização específica.** Laboratório usa `~/laboratorio-lora` e `laboratorio/` no checkout, sem alterar a Central em produção. Mods ativam overlays em cópias, não hot-reload do código original.

**Estado da instalação de software:** **Laboratório Neural v0.5 instalado e 35 testes Python PASS no PC do usuário**. O painel localhost está disponível no código em `127.0.0.1:8787`, mas não foi reconfirmado se servidor segue rodando. A pasta completa `laboratorio/` **ainda não foi sincronizada** para o GitHub (na árvore remota, existia apenas `laboratorio/GUIA_GITHUB.md`); toda atualização de documentação GitHub é distinta da instalação do ZIP e de uma execução no hardware.

### O alerta atual mais importante: 9B interrompido, NÃO treinado

- Modelo: `ccharnkij/Qwen3.5-9B-Uncensored`, revisão `cfcad5b1d1771e7803e08c49fb3dfcd202182f8c`, Safetensors multimodal monolítico esperado ~18.819.721.632 bytes.
- A limpeza autorizada de modelos Ollama antigos já aconteceu (~20,92GiB); **NÃO a repetir**. Dados mentais e código preservados.
- Primeira tentativa falhou às **03:19:31** por erro HF Xet/CAS, deixando `stage=deleted,status=failed`.
- Segunda tentativa retomou sem nova exclusão, com ambiente `HF_HUB_DISABLE_XET=1`, timeouts HF aumentados, scripts v1.4 e PIDs históricos `66998` (pai) e `66999` (filho), log `~/laboratorio-lora/logs/9b-vision-retomada.log`.
- Pai foi pausado de dia por `SIGSTOP`; downloader continuou em segundo plano. Timer de retomada foi registrado para **21:00 de 11/10** em `lab-retomar-9b-66998-6276946.timer`.
- O downloader sofreu `peer closed connection without sending complete message body` e tentou retomar. Em **13:47–13:49**: `du -sh` da pasta = **18G**; antigo `.incomplete` ~1.024GB e parcial novo **17.731.420.160 bytes**, mas **`model.safetensors` final não existe**.
- Às **13:49** e na verificação seguinte **os DOIS processos (66998 e 66999) já NÃO EXISTIAM**; `pgrep` também vazio. **Download não está ativo agora**. O log exibido para em `Trying to resume download...`; causa exata de encerramento não comprovada.
- `orquestrar_9b.py status` ainda mostra a falha **antiga** de 03:19, `stage=deleted` e PID 66998 salvo; não confiar no PID ou no `status=failed` como diagnóstico exclusivo da tentativa mais recente.
- **O timer das 21h aponta a um PID morto**: poderá ser no-op/recusado por checagem anti-PID reuse, mas **NÃO pode retomar magicamente o download nem garantir treino**. Verificar unidade `systemctl --user cat ...`, limpar timer obsoleto de maneira pontual e só agendar novo processo após recuperação. **Não emitir `SIGCONT` nem reiniciar com opção destrutiva para um PID desconhecido.**
- Não foi feito **probe 9B, LoRA Hoshino/Lilith, exportação GGUF, comparação Ollama ou implantação em produção**.
- Prioridade seguinte: investigação somente leitura + retomada HF da revisão correta, preservando os `.incomplete`; reservar GPU para a janela noturna e conferir disco antes de gerar GGUF.
- Ferramentas instaladas: `llama.cpp` com conversores GGUF e quantizador; ainda precisam ser testadas com a arquitetura exata.

### Modelos e requisitos vigentes

| Ator/faixa | Escolha/condição |
|---|---|
| Professor | `Huihui-Qwen3.5-27B-abliterated.Q4_K_M.gguf`, ~16,5GB, **SÓ GGUF/INFERÊNCIA**, **NUNCA treinar o 27B**; ainda não baixado |
| Hoshino e Lilith | mesmo Qwen3.5-9B multimodal Safetensors, LoRAs **independentes**, corpus v3 por identidade **722 treino / 131 validação / 104 holdout**; ainda sem treino real 9B |
| Alistair | `Qwen/Qwen3.5-4B` Safetensors para treino LoRA isolado (antigo executor Unsloth GGUF não é base automaticamente compatível); corpus sintético **51 train / 27 validation / 16 holdout presente**; pesos ainda AUSENTES |
| 6B experimental | `01-ai/Yi-1.5-6B-Chat`, sem thinking; **exceção explícita** permite experimentá-lo assim; ainda AUSENTE |
| 7B experimental | pensamento ON/OFF real **OBRIGATÓRIO**; Hunyuan-7B-Instruct candidato com ressalvas/antes descartado, exige teste backend real |
| 8B comparativo | Qwen3-8B com thinking ON/OFF; ainda AUSENTE |
| 7B antigo | Qwen2.5-7B-Instruct sem thinking nativo; referencial histórico, não satisfaz exigência atual |
| Faixa 6B com thinking | **nenhum candidato homologado**; buscar futuros sem assumir que 3B ≈6B |

**Tela de modelos**: mostrar **SOMENTE checkpoints realmente baixados, inteiros, com recibo**; não exibir pesquisa/planos. Modelos desconhecidos locais podem aparecer apenas para leitura, não para treinamento até homologação.

### Professor noturno — ideia grande, fase parcial

O usuário quer que, ao dormir, um professor ~27/28B uncensored com thinking analise histórico do dia, pesquisas, registros e treinamentos anteriores, escolha experiências de qualidade e intensidade/duração, monte datasets individuais, descarregue-se, treine **Hoshino, Lilith e Alistair** sequencialmente, reabra o professor se precisar avaliar e, quando terminar, **possa desligar o PC**. Idéia aprovada como direção, NÃO totalmente implementada. O professor deve **poder decidir não treinar**.

Na **v0.5 de verdade**, professor só produz **propostas** em snapshots JSONL explicitamente exportados (até 40 registros/2MiB), com IDs/evidência checados; não lê automaticamente todo histórico, não treina sozinho e não tem shell/root. Contexto dinâmico 4K–32K conforme `MemAvailable`, tokens realmente contados por `llama-server /tokenize`, CPU threads detectadas e offload GPU mínimo opcional; não usar swap como RAM rápida. Ainda **não baixado/testado** fisicamente. **Desligamento automático do PC, treino automático diário, promoção de LoRA para produção, recuperação exata de otimizador e rollback completo são pendências**, não habilitadas.

### Alistair + Yi6B — etapa seguinte quando viável

```bash
cd "$HOME/hoshino e lilith"
source "$HOME/laboratorio-lora/.venv-rocm/bin/activate"
python3 -m unittest discover -s laboratorio/tests -v
python -m laboratorio.professor status
python -m laboratorio.alistair status
python -m laboratorio.candidatos installed
python -m laboratorio.pilotos plan --six-entity hoshino
```

Última saída observada de `pilotos plan`: `alistair_base_complete=false`, `alistair_seed_present=true`, `alistair_probe_passed=false`, `six_b_complete=false`, `six_b_native_thinking=false`, `six_b_entity=hoshino`, `ready_to_run=false`; `will_download=false`, `will_change_production=false`, `will_shutdown=false`. **Não executar pilotos automaticamente**. Quando 9B e disco permitirem: baixar 4B e Yi6B **um por vez**, probe ROCm, só então piloto 30 min Alistair e 30 min 6B com persona selecionada (Hoshino/Lilith/Alistair), exportação e comparação Ollama isolada conforme compatibilidade. Não há checkpoints reais desses pilotos.

### Nota histórica de treinamento 7B anterior

Conversa anterior do projeto tratou de treino de personalidade Qwen2.5-7B ~30min no ambiente `~/laboratorio-lora`, com script `treino_qwen25_7b_personalidade_30min.py` e adaptador de teste `final-passo-00229`. Foram preparados prompts de avaliação de identidade/personalidade; **o trecho disponível não comprova aprovação ou resultados finais**. Não tratar experimentos anteriores de 7B como prova de conclusão de novos 9B/4B/6B.

## Comandos seguros para iniciar diagnóstico no próximo chat

Executar apenas se o operador concordar; estes **não iniciam downloads/treinos**:

```bash
cd "$HOME/hoshino e lilith"
source "$HOME/laboratorio-lora/.venv-rocm/bin/activate"
date
pgrep -af '[o]rquestrar_9b.py|[b]aixar_9b.py' || true
python "$HOME/laboratorio-lora/automacao_9b_vision_v1_4/orquestrar_9b.py" status
du -sh "$HOME/laboratorio-lora/modelos/qwen3.5-9b-uncensored-hf"
find "$HOME/laboratorio-lora/modelos/qwen3.5-9b-uncensored-hf" \
  -type f -name '*.incomplete' -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n'
ls -lh "$HOME/laboratorio-lora/modelos/qwen3.5-9b-uncensored-hf/model.safetensors" || true
tail -n 40 "$HOME/laboratorio-lora/logs/9b-vision-retomada.log"
systemctl --user list-timers --all | grep -Ei 'lab|9b|retomar' || true
df -h ~
```

## Mensagem sugerida para copiar ao próximo chat

> Estou continuando o projeto privado **Hoshino e Lilith**. Leia a documentação no repositório `atominen/hoshino-e-lilith`, começando por `docs/HANDOFF_20261011_INDICE_E_DECISOES.md`, `docs/HANDOFF_20261011_OPERACAO_9B_ESTADO_REAL.md` e `docs/HANDOFF_20261011_ARQUITETURA_PROFESSOR_E_LABORATORIO.md`. O laboratório **v0.5 foi instalado com 35 testes passando**, mas **o download do Qwen3.5-9B parou** depois de 17,7GB parciais, pai e filho 66998/66999 desapareceram, `model.safetensors` não existe, e o timer das 21h aponta PID morto. Não repetir a exclusão Ollama nem apagar `.incomplete`. Quero retomar com segurança o 9B e depois testar Alistair 4B + Yi6B por 30 min cada; professor 27B somente GGUF de inferência, contexto dinâmico, futuros treinos noturnos autônomos. Antes de alterar minha máquina, verificar estado e preservar memórias/modelos/código. Continue de onde paramos e não atribua testes reais de GPU aos 35 testes unitários.

## Regras de preservação

- **Repositório privado**; não fazer `git push --force`, `git reset --hard`, `rm -rf` amplo nem enviar bancos, memórias, diários, credenciais, tokens, pesos, arquivos `.incomplete`, caches ou logs extensos.
- Github possui **documentação**, não o pacote Python v0.5 completo ainda; sincronização futura exige revisão do checkout local.
- A revisão noturna mental já existe; professor é curador de treino distinto, não nova autoridade arbitrária de memória.
- Não confundir artefatos textuais do ChatGPT, testes sandbox e comandos sugeridos com arquivos realmente instalados/rodando.
- Não afirmar mais progresso do que o comprovado nas saídas. Esse arquivo é um **snapshot datado**.
