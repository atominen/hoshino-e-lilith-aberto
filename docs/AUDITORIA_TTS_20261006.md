# Auditoria de voz — 06/10/2026

Esta auditoria cobre a implementação encontrada no começo da etapa de áudio.
Correções posteriores podem alterar os módulos listados. A referência `11111`
orienta a arquitetura; não foi tratada como uma lista de comandos executáveis.
Nenhuma identidade ou memória real recebeu falas de teste. Não foi usado sudo.

## Problemas constatados no legado

- `tools/voice.py` inicia seu próprio `voice_worker.py` em cada processo. Compartilhar
  o diretório de pesos não compartilha a instância do modelo. Hoshino e Lilith
  podem manter dois Kokoros, duas filas e dois reprodutores independentes.
- Hoshino configura `pf_dora`; Lilith também recebe esse padrão. Velocidade ou
  descrição diferente não transformam o mesmo timbre em duas vozes distintas.
- `voice_worker.py` fixa `KPipeline(lang_code='p')`. Modelo e dispositivo de
  `config.py` não são enviados ao worker, embora apareçam no diagnóstico.
- O cache padrão da aplicação é `compartilhado/modelos/huggingface`. Os pesos
  e o timbre completos do Kokoro estão em `compartilhado/modelos/voz/huggingface`.
  O cache padrão falhou no ensaio offline; o cache legado funcionou. Sem modo
  offline, a diferença pode provocar download no primeiro pedido.
- O protocolo JSONL antigo não correlaciona respostas por `request_id`. Após um
  timeout, ele mantém o worker vivo e uma resposta atrasada pode ser confundida
  com a resposta do próximo pedido.
- Não há sinal compartilhado de reprodução TTS nem bloqueio/identificação de
  eco entre as duas entidades e o transcritor. Bloquear só o microfone de um
  processo não protege a outra entidade ou um monitor de saída.
- `speak()` corta textos com mais de 1.200 caracteres sem anunciar a redução.
  Uma única frase muito longa também pode atingir o limite de fonemas interno.
- A descrição de `social/escuta.py` afirma que cada aplicativo possui um monitor
  próprio; isso não é uma propriedade geral de PulseAudio/PipeWire. O monitor
  normal pertence à saída e pode misturar vários aplicativos.

## Ensaio Kokoro real, local e silencioso

Script: `scripts/verificar_tts_local.py`. Ele força modo offline, quatro threads,
usa o worker já instalado, verifica o WAV e não inicializa nenhum reprodutor.
WAVs são temporários por padrão; `--output` preserva cópias para validação independente.

Texto: “Olá, Gustavo. Estou verificando a síntese local em português brasileiro,
sem reproduzir áudio.”

| Cache / turno | Resultado | Tempo | Áudio | RSS |
| --- | --- | --- | --- | --- |
| HF padrão | Falha `LocalEntryNotFoundError` | — | Nenhum WAV | — |
| Voz legado / frio | WAV íntegro | 6,201 s | 5,675 s | 1.041.108 KiB |
| Voz legado / quente | WAV íntegro | 1,578 s | 5,675 s | 1.109.044 KiB |

Formato: mono, PCM16, 24 kHz, 272.444 bytes. A integridade e a energia não
comprovam naturalidade subjetiva. Uma segunda execução preservou a amostra em
`compartilhado/runtime/audio/ensaios_kokoro_20261006/kokoro-legado-pf_dora-0.wav`.

O catálogo oficial PT-BR do Kokoro contém uma feminina (`pf_dora`) e duas
masculinas (`pm_alex`, `pm_santa`). Portanto não oferece diretamente duas
femininas brasileiras diferentes. O legado deve continuar identificado como
provisório, não como escolha final de duas vozes. [Catálogo oficial](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

Ambiente legado observado: Python 3.12; Kokoro 0.9.4; Torch 2.14.0+cpu;
Transformers 5.17.0; Soundfile 0.14.0; Misaki 0.9.4. Ele foi preservado.

## Candidatos pesquisados em fontes oficiais

### Qwen3-TTS CustomVoice 0.6B

Oferece nove IDs de timbre, incluindo as femininas `Serena`, `Vivian`, `Ono_Anna`
e `Sohee`, com geração em `Portuguese`. Não exige referência para esses timbres.
Nenhuma delas tem PT-BR como língua nativa no catálogo; sotaque e naturalidade
brasileiros precisam ser avaliados. `Serena` e `Vivian` são candidatas de ensaio,
não atribuições definitivas às entidades. Licença Apache-2.0. [Modelo oficial](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice).

O repositório completo ocupa aproximadamente 2,5 GB, incluindo o tokenizer;
o arquivo principal tem aproximadamente 1,81 GB. [Arquivos oficiais](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/tree/main).

A implementação oficial ignora `instruct` na variante 0.6B; o perfil deve escolher
um speaker ID, não prometer controle de estilo por texto que não é aplicado.
O código oferece `get_supported_speakers()` e `get_supported_languages()` para
validar o contrato em execução. [Implementação oficial](https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/inference/qwen3_tts_model.py).

O pacote oficial fixa Transformers 4.57.3 e Accelerate 1.12.0. Instalá-lo no
ambiente legado modificaria essas dependências. O ensaio usa outro ambiente
Python 3.12, `compartilhado/ambientes/tts-qwen`, com Torch/Torchaudio 2.6.0+cpu
obtidos no índice CPU oficial e sem FlashAttention. [Dependências Qwen](https://github.com/QwenLM/Qwen3-TTS/blob/main/pyproject.toml),
[wheels CPU PyTorch](https://pytorch.org/get-started/previous-versions/).

Estimativa pré-ensaio, não medição: 5–9 GB de RAM em float32, modelo + ambiente
aproximadamente 5–7 GB de disco. CPU evita concorrência com a RX 6650 XT, mas
não garante latência conversacional adequada. O instalador protege uma reserva
de pelo menos 12 GiB; não apaga componentes antigos para ganhar espaço.

### Chatterbox Multilingual V3 / pack PT-BR

A Resemble mantém um pack oficial otimizado para português brasileiro,
licença MIT, checkpoint T3 float32 de 2.143.990.296 bytes mais decoder e assets.
Para dois timbres próprios, o caminho documentado usa duas referências de áudio;
o projeto ainda não forneceu essas referências. O pack brasileiro é interessante
para um próximo comparativo, mas não resolve automaticamente o requisito de duas
vozes. [Pack oficial PT-BR](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-pt-br),
[documentação do motor](https://github.com/resemble-ai/chatterbox/blob/master/README.md).

As dependências também precisam de isolamento: o pacote atual fixa Torch e
Torchaudio 2.6.0 e Transformers 5.2.0 para Python 3.12. Não foi instalado neste
ensaio. [Dependências oficiais](https://github.com/resemble-ai/chatterbox/blob/master/pyproject.toml).

## Integração recomendada

1. Um processo compartilhado, protegido por lock entre processos, carrega um
   motor de síntese e atende uma fila serial com `entity`, `request_id`, idioma
   e perfil vocal. Alistair não participa da saída de voz.
2. A síntese retorna um artefato WAV validado e não o reproduz automaticamente.
   A interface escolhe um consumidor: navegador ou saída local, nunca ambos.
3. Cada pedido e evento de reprodução mantém autoria da entidade, origem TTS,
   início/fim e identificador. Timeout encerra o worker defeituoso antes de
   reutilizar o protocolo. Erro não vira áudio concluído.
4. Navegador usa cancelamento de eco quando disponível e suspende a captura
   durante a própria reprodução como fallback explícito. Os sinais compartilhados
   não substituem AEC real: não se deve prometer conversa simultânea sem eco.
5. ASR reutiliza Faster-Whisper; não carrega um transcritor por entidade. Entrada
   do microfone principal aponta para usuário por padrão. Fonte, aplicativo,
   locutor e conteúdo são campos separados e verificáveis.
6. O substituto só vira padrão depois de WAV íntegro, transcrição independente,
   prova dos dois timbres, latência/RAM medidas e audição humana das candidatas.
   Kokoro e os dois caches continuam preservados até essa validação.

## Ensaio Qwen

Preparação autorizada nesta etapa: `scripts/preparar_tts_qwen.py`; verificação:
`scripts/verificar_tts_qwen.py`. O primeiro instala no ambiente novo e baixa
somente o checkpoint oficial completo, fixando a revisão e verificando SHA-256
dos arquivos LFS. O segundo carrega uma única instância CPU float32, sintetiza
Serena e Vivian com o mesmo texto, preserva os WAVs e registra tempo/RSS/formato.

O ensaio terminou em uma única instância, CPU float32 com quatro threads,
offline e sem reprodução. SoX não está instalado no sistema; o aviso não
impediu a síntese CustomVoice. FlashAttention também não é usado nesta CPU.

Texto comum: “Olá, Gustavo. A imagem está pronta. Podemos conversar enquanto a
outra tarefa continua.”

| Candidata | Tempo de síntese | Duração WAV | RTF | RSS após síntese | Pico RSS |
| --- | --- | --- | --- | --- | --- |
| Serena | 37,356 s | 7,04 s | 5,306 | 5,05 GiB | 5,58 GiB |
| Vivian | 48,065 s | 8,96 s | 5,364 | 5,55 GiB | 5,90 GiB |

Carga do motor: 1,221 s, RSS inicial 4,39 GiB. Os dois WAVs são mono PCM16,
24 kHz, não silenciosos e finitos. Arquivos preservados:

- `compartilhado/runtime/audio/ensaios_tts_20261006/qwen_serena_ptbr.wav`
- `compartilhado/runtime/audio/ensaios_tts_20261006/qwen_vivian_ptbr.wav`
- `compartilhado/runtime/audio/ensaios_tts_20261006/verificacao_qwen_tts.json`

Instalação real: aproximadamente 4,1 GiB adicionais (modelo + ambiente), sem
CUDA/NVIDIA; 28,84 GiB livres ao terminar. Talker e tokenizer tiveram SHA-256
conferidos com os arquivos LFS da revisão oficial
`85e237c12c027371202489a0ec509ded67b5e4b5`. Proveniência e hashes completos em
`compartilhado/modelos/voz/qwen3-tts/origem_verificada.json`.

A latência observada é cerca de cinco vezes a duração do áudio: **não é tempo
real**. A integração da central pode usar Qwen de forma explicitamente provisória
para oferecer os dois timbres, sem fala automática por padrão, mantendo Kokoro
como legado rápido preservado. A troca definitiva ainda depende de ouvir as
candidatas e validar sotaque, timbre e experiência conversacional. Quatro threads
e uma fila CPU serial evitam disputar toda a CPU com Alistair. A política planejada
de um único worker pesado ASR ou TTS residente e descarga após 120 s ocioso
reduz RAM; isso não transforma as medidas acima em inferência em tempo real.

O ASR independente confirmou a amostra Kokoro com todas as palavras corretas,
mudando somente a pontuação. Evidência em `ASR_CENTRAL_20261006.md`. A comparação
independente de Serena e Vivian usou `scripts/verificar_tts_asr.py`, o mesmo
processo Faster-Whisper CPU/int8 e origem `synthetic_tts_fixture`:

| Candidata | Texto reconhecido | WER | Tempo ASR |
| --- | --- | --- | --- |
| Serena | Igual ao esperado | 0 (13/13 palavras) | 11,497 s incluindo carga |
| Vivian | Mesmo texto, `Gustavo!` em vez de `Gustavo.` | 0 (13/13 palavras) | 6,821 s |

WER preservou os acentos e ignorou somente caixa e pontuação. As duas amostras
passaram na fidelidade textual; esse resultado não substitui audição humana,
prova de distinção subjetiva das vozes ou avaliação de naturalidade. Não houve
captura física, chamada externa ou publicação de falas nas mentes reais.
