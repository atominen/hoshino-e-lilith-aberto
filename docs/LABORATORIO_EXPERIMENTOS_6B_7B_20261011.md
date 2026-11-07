# Laboratório Neural v0.2 — candidatos 7B/6B e experimentos de UI

Data: 11/10/2026, fuso America/Sao_Paulo. Extensão autorizada da interface de laboratório já existente, **sem nova instalação em produção**.

## Motivação

O usuário solicitou buscar modelos 7B e 6B apesar de anteriormente ter rejeitado as opções disponíveis, testar as novas alternativas e acrescentar à interface uma seleção real de **modelo, corpus, duração, horário e conversão GGUF**. A pasta `~/laboratorio-lora` foi enviada num ZIP para inspeção. Ela contém scripts QLoRA e corpora v2/v3, mais o estado de automação v1.4 e logs.

O 9B Uncensored Vision permanece em download com internet lenta, controlado por um timer às 21h de 11/10/2026. **Nenhuma ação nesta atualização suspende, reinicia, apaga ou baixa pesos do 9B**.

## Candidatos — revisão de fichas Hugging Face

| Candidato | Faixa | Modalidade | Avaliação proposta | Status do laboratório |
|---|---|---|---|---|
| Qwen/Qwen2.5-VL-7B-Instruct | 7B | texto+imagem | comparar visão/descrição | pesquisa; treinador multimodal não implementado |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | 7B | texto/raciocínio | matemática, raciocínio, comportamento | QLoRA textual experimental |
| Qwen/Qwen2.5-7B-Instruct | 7B | texto | baseline de personalidade | QLoRA textual experimental |
| Qwen/Qwen2.5-Omni-7B | 7B | texto+imagem+áudio+vídeo | inspecionar multimodalidade | pesquisa, sem GGUF automático |
| 01-ai/Yi-VL-6B | 6B | texto+imagem | candidato 6B visual | pesquisa, família Yi já foi rejeitada |
| 01-ai/Yi-1.5-6B-Chat | 6B | texto | baseline 6B | QLoRA textual experimental, anteriormente rejeitado |

Fonte: fichas oficiais no catálogo `laboratorio/catalogo.py`. **Nenhum dos candidatos acima é garantidamente uncensored ou preserva thinking nativo**, salvo o aspecto de raciocínio destilado do DeepSeek. Testes de segurança/recusas e raciocínio são necessários antes da escolha de executor.

## Implementação entregue

**Artefato executável:** `laboratorio_neural_v0_2.zip` (ZIP de atualização incremental para `laboratorio/` e documentação). Substitui a interface v0.1 local após backup e reinício manual do servidor 8787. Novos scripts `catalogo.py`, `experimentos.py`, `trabalhador.py` e `treino_texto.py`; amplia `painel.py`, `labctl.py`, HTML, CSS, JS e suíte de testes. Utiliza corpus já existente sem copiar 6B/7B/9B pesos para a pasta do projeto.

**Controles de segurança:** operações apenas a partir de IDs allowlist de modelos; previews read-only; execução/agendamento somente após confirmação; datasets restritos a pares JSONL v2/v3 ou importação validada; log/estado em diretório do laboratório; sem `sudo` e sem `shell=True`; sem download concorrente com 9B; sem teste Ollama de produção; visão explicitamente bloqueada na conversão textual, sem segundo `FROM`.

**Limites:** treino QLoRA 6/7B experimental (NF4 BF16 em GPU 8 GiB não testado nesta entrega), GGUF e `ADAPTER` dependem de `llama.cpp`/Ollama atuais; resultados de Ollama são **comparações textuais**, não validação de memória SQLite ou visão. O treinamento de 9B original não muda. Agendamento dos novos jobs usa timers transitórios `systemd --user`, sem autoexecutar trabalho se janela conflitante com treino 9B.

**Testes realizados no ambiente de preparação:** suíte unitária (catálogo, datasets, importação, bloqueios, mods) e smoke HTTP de rotas e CSRF. Nenhuma GPU, Ollama ou Hugging Face foi invocado para download real.

## Implantação

1. Salvar ZIP em `~/Downloads`, fazer backup da pasta `laboratorio/` atual no PC.
2. `unzip -o ~/Downloads/laboratorio_neural_v0_2.zip -d "$HOME/hoshino e lilith"`.
3. `python3 -m unittest discover -s laboratorio/tests -v`.
4. Reiniciar somente servidor local do painel (porta 8787), **não reiniciar o orquestrador v1.4**.
5. Acessar `http://127.0.0.1:8787`, usar `Verificar plano`, selecionar corpus e conferir alertas; não dar início a cargas pesadas enquanto o 9B estiver baixando.
6. Versionar a pasta `laboratorio/` no repositório privado após inspeção. O documento remoto é registro técnico; os executáveis vêm do ZIP e não são sincronizados automaticamente.
