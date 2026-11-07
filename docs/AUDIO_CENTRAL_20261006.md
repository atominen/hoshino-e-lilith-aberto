# Áudio compartilhado e central — 06/10/2026

## Entrega desta etapa

A central única agora grava pelo microfone do navegador, transcreve localmente e
preenche o rascunho da entidade escolhida no início da gravação. Trocar a seleção
durante a transcrição não troca a destinatária. O usuário revisa e envia; não há
envio automático de fala para as memórias. Alistair aceita mensagens transcritas,
mas continua exclusivamente textual.

Hoshino usa a candidata **Serena**, Lilith usa **Vivian**, em um único motor
Qwen3-TTS CustomVoice 0.6B, CPU/float32. Timbres são IDs distintos do checkpoint;
naturalidade e sotaque brasileiro ainda não foram aprovados por audição humana.
O idioma é português multilíngue, não um catálogo de duas vozes nativas PT-BR.
A voz pode ser pedida em **Ouvir Hoshino/Lilith** nas respostas; a opção de ouvir
novas respostas automaticamente começa desligada. Notificações de Alistair e
mensagens do usuário não são faladas em nome das entidades.

São os mesmos **três LLMs conversacionais** da etapa anterior. TTS e ASR são
componentes especializados, não novas mentes ou um quarto LLM de standby.

## Fluxo e recursos

- Gravação explícita, até 60 s, PCM mono/16 kHz no navegador. A API também aceita
  WAV mono PCM16 de 8–48 kHz, 0,2–60 s e até 8 MiB; cabeçalhos incompletos falham.
- Um processo ASR lazy, Faster-Whisper configurado atualmente como large-v3,
  CPU/int8, até quatro threads e cache offline. Modelo não é duplicado por entidade.
- Fila serial de áudio: um pedido executando e até quatro aguardando; lease
  `cpu_audio` também protege a execução entre processos. GPU não é usada por áudio.
- Só ASR **ou** TTS pesado fica residente. Trocar o tipo de operação libera o
  outro worker; após 120 s sem novos pedidos os dois são descarregados. Isso
  reduz RAM, mas acrescenta custo de carga ao voltar a usar o motor.
- Cancelar e encerrar convertem pedidos pendentes em interrupção. Cancelamento,
  timeout ou resposta com ID errado descarta o worker antes de outro pedido.
  O bootstrap Linux encerra o filho caso seu processo pai morra.
- Falhas de persistência/limpeza não abandonam a fila nem travam seu encerramento.
  Falha de registro não é anunciada como trabalho confirmado.
- Áudios de entrada são removidos ao terminar/cancelar. WAVs de fala concluídas
  são artefatos em `entidades/<id>/runtime/audio/central`, limitados a 40 MiB por
  arquivo e orçamento de 512 MiB por entidade. Reserva de disco é conferida;
  não se apagam arquivos antigos silenciosamente para abrir espaço.

Textos acima de 2.400 caracteres ou palavras indivisíveis acima do limite de
chunk falham claramente: não há corte silencioso. Chunks normais conservam o
conteúdo, sem prometer fala expressiva por `instruct` que o modelo 0.6B não aplica.
WAV só fica concluída depois de conferir PCM, frames, duração e limite; o worker
também confere áudio finito e não silencioso. Limite de tokens atingido na síntese
é tratado como possível truncamento, não como sucesso.

A configuração central fica em `compartilhado/config/audio.json`. Kokoro e seu
ambiente/cache originais foram preservados como alternativa explícita, não como
fallback invisível que substituiria os timbres. Para usar o legado na central,
configure backend `kokoro`, Python `compartilhado/ambientes/voz/bin/python`, ambos
IDs `pf_dora` e `voices_ready=false`; serão a mesma voz feminina provisória.
Instalação Qwen foi isolada, aproximadamente 4,1 GiB adicionais, sem sudo.

Executores Hoshino/Lilith iniciados pela central desativam captura e reprodução
legadas **antes** de importar os módulos da interface anterior. O navegador é o
consumidor de áudio dessa execução, sem duas saídas falando a mesma resposta.
Iniciar individualmente a interface anterior continua usando Kokoro; seu cache,
protocolo identificado, tratamento de timeout e corte de texto foram corrigidos.

## Origem e limites de captura

Enquanto esta aba grava, sua própria reprodução de voz é interrompida. O navegador
solicita cancelamento de eco, redução de ruído e mono. Isso não comprova AEC real,
nem impede som de outras abas/aplicativos entrando pelo microfone físico.
Não foi implantado um serviço global de captura isolada por aplicativo.

`speaker=usuario` significa papel da fonte `browser_microphone`, não reconhecimento
biométrico da voz de Gustavo. Fontes não primárias continuam desconhecidas.
Não há diarização instalada. Idioma configurado não recebe uma confiança inventada.
Metadados de origem só acompanham o envio revisado correspondente à mesma entidade;
texto substituído é enviado como digitado, sem atribuir falsa origem à transcrição.

Inventário diferencia microfones, monitores de saída e streams de aplicativos.
Um stream Discord/Firefox não é um capturador isolado. A escuta legada não usa
mais o monitor genérico como se fosse Discord ou Minecraft. Fonte virtual não é
classificada como microfone físico apenas pelo nome. Na observação mais recente,
o sistema detectou **fifine Headset Mono** e a saída USB correspondente; anteriormente
havia apenas `auto_null`. Não se abriu o microfone nem reproduziu som nesse ensaio.

## Verificações

Suíte offline: 25 grupos, com 34 testes de serviço/HTTP/RPC, 17 de ASR e 7 de voz
legada. Dados temporários, sem acessar os bancos mentais reais. Cobertura de
cancelamento, proveniência, autenticação, caminhos/symlinks, WAV incompleta,
fila cheia, quota, erros de disco, correlação de pedidos e conservação do texto.

Ensaio independente de candidatas: uma instância Qwen CPU, Serena 37,356 s para
7,04 s de áudio; Vivian 48,065 s para 8,96 s. Pico de RAM **5,90 GiB**. Ambas
passaram ASR com **WER 0, 13/13 palavras**; não é avaliação subjetiva de voz.
Dados e fontes em `AUDITORIA_TTS_20261006.md` e `ASR_CENTRAL_20261006.md`.

Ensaio integrado real `scripts/verificar_audio_central.py`:

| Etapa | Resultado |
| --- | --- |
| HTTP → Hoshino/Serena | 42,180 s, WAV mono PCM16/24 kHz, 6,96 s |
| HTTP → Lilith/Vivian | 38,159 s, WAV mono PCM16/24 kHz, 7,12 s; mesmo PID TTS |
| WAV sintética → ASR HTTP | 12,059 s; frase fiel, TTS liberado antes do ASR |
| Cancelamento ASR | `interrupted`, sem mensagem automática |
| Encerramento | ambos workers parados, sem processo de áudio órfão |

Evidência em `verificacao_audio_central_20261006.json`. Bancos de mensagens/jobs
do ensaio foram temporários; WAVs de saída são artefatos, não vivências inseridas
nas mentes. Kokoro corrigido também passou ensaio offline: 5,871 s frio / 1,595 s
quente para 5,675 s de áudio. A central foi inspecionada no navegador com os
controles novos, candidatos, fontes e fala automática desligada.

Qwen em CPU está aproximadamente cinco vezes mais lento que a duração da fala;
**não é tempo real**. Ainda é necessário gravar sua fala na central e ouvir as
candidatas para confirmar captura, saída física, sotaque, ruído e experiência.
Discord/Minecraft ao vivo, WorldState, cognição evolutiva completa e benchmark
`aa` não foram aprovados por esta etapa de áudio.

## Como usar

Abra o executável da central. Selecione a entidade; em **Falar uma mensagem**,
libere o microfone no navegador, fale e pressione **Concluir gravação**. Revise
o rascunho e pressione **Enviar**. **Cancelar** interrompe gravação/transcrição.
Nas respostas da Hoshino/Lilith, use **Ouvir**; **Parar fala** interrompe o player
e cancela a preparação pendente. Fechar a aba libera a captura e solicita
cancelamento do áudio, mas não coloca as entidades para dormir.

Próxima etapa: WorldState factual compartilhado, com interpretações e memórias
individuais, sem confundir estado observado com crenças ou fatos inventados.
