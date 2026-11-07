# Professor Neural v0.4: 27B somente GGUF e Alistair como aluno
Data: 11/10/2026. Projeto pessoal privado.

## Decisão aprovada
O usuário autorizou **iniciar a implementação** do curador/professor de aprendizado noturno, incluir **Alistair** no treinamento e limitar o **27B estritamente a inferência em GGUF, sem qualquer ajuste de pesos**.

**Pacote executável entregue no ChatGPT:** `laboratorio_neural_v0_4_professor_alistair.zip`, SHA256 `53c5b9d198ba6717b1d7ee6e7dc0a15e180ba3a896b1201d9d5729e2a3eac61c`. Contém a pasta `laboratorio/` completa da v0.3 mais código, UI e testes novos. **O ZIP deve ser instalado/sincronizado no checkout do operador**; este documento GitHub não executou scripts, baixou pesos nem treinou modelos. A interface antiga precisa reiniciar para servir a nova rota de status.

## Professor: somente GGUF/inferência
- HF repo específico existente [mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF](https://huggingface.co/mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF); arquivo `Huihui-Qwen3.5-27B-abliterated.Q4_K_M.gguf` (~16,5 GB).
- SHA256 publicado na ficha desse arquivo: `5a2321c22682c7109907d6a4c0293b9c6349bc239d4e7b9aaa1e14b98add4484`. O download explícito `python -m laboratorio.professor download` fixa a revisão Hub e confere o hash completo. **Jamais baixa Safetensors 27B**.
- `python -m laboratorio.professor plan --entity <hoshino|lilith|alistair> --snapshot ...` carrega `llama-server` CPU `-ngl 0` na porta `127.0.0.1:11558`, lê um snapshot JSONL **explicitamente exportado** em `~/laboratorio-lora/historicos-curadoria/`, mais até dez metadados de jobs anteriores por entidade, gera proposta de exemplos SFT, valida contrato estrito e descarrega o professor (SIGTERM/timeout SIGKILL) em `finally`.
- Piloto limitado a 40 registros/2 MiB por análise, máximo 12 exemplos propostos. Saída sempre `PROPOSTA_NAO_APROVADA`, com perfis `nenhum/0`, `conservador/10 min` ou `moderado/30 min` — o professor não executa esses treinos. IDs não existentes, comandos extras em JSON e mistura de entidades são recusados.
- **Não cobre ainda automaticamente o histórico integral**, os JSONL do usuário precisam ser exportados e revisados. Memórias/diários privados não são lidos automaticamente, o cron noturno ainda não foi criado, e a IA nunca recebe shell/sudo/shutdown.

## Alistair: terceiro aluno Qwen3.5-4B
- Manifesto existente `entidades/alistair/entidade.json` identifica papel `coordenador_standby`, dispositivo `cpu`, sem voz nem herança de memórias. Executor antigo: GGUF `unsloth/Qwen3.5-4B-GGUF`. **Não usar esse GGUF como origem para treinamento de LoRA.**
- Base de laboratório escolhida: [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B), Safetensors multimodais, baixa apenas mediante comando expresso `python -m laboratorio.alistair download` e revisão registrada em `lab_revision.json`. Arquitetura 4B e peft/ROCm ainda não tiveram probe físico. O LoRA deve ser avaliado contra **exatamente essa base HF** (ou GGUF derivado dela), não anexado sem teste ao antigo Unsloth GGUF.
- Gerador `python -m laboratorio.alistair seed` prepara 51 exemplos de treino, 27 validação e 16 holdout **sintéticos, sem acontecimentos autobiográficos**, com separação por casos e revisão humana necessária; não prova qualidade longitudinal.
- `python -m laboratorio.alistair probe` usa treinador multimodal text-only derivado do experimento 9B, validando backward BF16/NF4 e forward de imagem, LoRA só nas camadas de texto. `python -m laboratorio.alistair train --minutes 30` executa piloto somente se probe passou e com recursos livres. Checkpoints independentes em `~/laboratorio-lora/modelos-extras/alistair-qwen35-4b/adapters/alistair-piloto`. Sem exportação GGUF, importação Ollama ou promoção automática nesta fase.
- Falha de incompatibilidade 4B com LoRA targets causa parada sem treinar, jamais fallback CPU de backward.

## Preservação e conflitos
- Funções novas dependem do lock de trabalho `~/laboratorio-lora/controle-laboratorio/trabalhador.lock`; rejeitam concorrência com o 9B, inclusive agendamento/pausa do pai ou downloader ativo; não desmontam modelos nem alteram dados reais.
- O painel `localhost:8787` agrega rota GET somente leitura `/api/professor-status`: instalação 27B, disponibilidade 4B e corpus, probe e quantidade de propostas. Abri-lo não cria jobs.
- **Não desligar o computador automaticamente** nesta fase. O sistema de encerramento condicionado, histórico completo via cursor, retomada exata do otimizador e homologação de três alunos são trabalhos de próximas fases.

## Testes verificados em ambiente sandbox, não no PC do usuário
- 26 testes unitários passaram (incluindo anteriores), compilação Python válida, CLI `status` de professor/alistair e smoke HTTP de `/api/professor-status` passaram.
- Zip extraído/testado; **não houve download do GGUF, carregamento real de 27B, teste de GPU 4B, treinamento de Alistair, avaliação comportamental nem intervenção no 9B da máquina pessoal**.

## Instalação e próxima etapa
```bash
cd "$HOME/hoshino e lilith"
cp -a laboratorio "$HOME/laboratorio-lora/backup-laboratorio-v0_3-$(date +%Y%m%d-%H%M%S)"
unzip -o "$HOME/Downloads/laboratorio_neural_v0_4_professor_alistair.zip" -d .
python3 -m unittest discover -s laboratorio/tests -v
source "$HOME/laboratorio-lora/.venv-rocm/bin/activate"
python -m laboratorio.professor status
python -m laboratorio.alistair status
python -m laboratorio.alistair seed
```
Somente depois do 9B terminar e de revisar espaço/disco, executar os comandos de download e probe descritos em `laboratorio/README_PROFESSOR_V0_4.md` do ZIP. **Reiniciar somente o painel 8787**. Versionar os scripts locais no repositório privado posteriormente, nunca arquivos de pesos, memórias ou dados reais.

## Próxima arquitetura
1. API de leitura de histórico com cursor e ACL; exportar por entidade sem diários e sem repetição.
2. Avaliar propostas contra ferramentas e conjunto reservado; gerar dataset com aprovações auditáveis.
3. Integrar Alistair a exportação 4B GGUF/LoRA e testes Ollama isolados.
4. Gerenciador de noite com planos aprovados, parada/retomada do otimizador, supervisor de recursos, política de promoção e shutdown apenas mediante verificações explícitas e autorização.

## Correção de compatibilidade de arquivos HF Qwen3.5-4B

Inspeção dos arquivos reais de [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B/tree/main) mostrou `preprocessor_config.json` (além de `model.safetensors.index.json` e dois shards Safetensors), mas não `processor_config.json`. Na versão final do ZIP, o pré-voo do aluno e o treinador multimodal aceitam `preprocessor_config.json` **ou** `processor_config.json`, preservando a exigência de metadados visuais. 26 testes estáticos continuam passando. O treinamento real 4B permanece **não comprovado**: detalhes de PEFT/model forward podem falhar no probe GPU.

## Empacotamento final sem sobrescrever documentação/estado

ZIP final contém **somente** caminhos sob `laboratorio/` (29 arquivos), evitando alterar arquivos `docs/` reais do checkout. Recomenda-se instalar em pasta temporária e copiar com `rsync -a --exclude 'mods/'` para preservar os mods locais do operador; fazer backup da pasta anterior antes da operação. Em nenhum momento usar `git reset --hard`, `rm -rf` no checkout ou copiar a pasta `models`.
