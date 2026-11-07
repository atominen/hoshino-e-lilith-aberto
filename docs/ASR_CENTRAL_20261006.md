# ASR compartilhado da central — 6 de outubro de 2026

Implementado em `app/core/audio_transcription.py`, reutilizando o reconhecedor,
o preparo do sinal e o filtro de texto de `app/tools/transcricao.py`.

## Comportamento

- Uma instância lazy do faster-whisper large-v3 por worker persistente da central.
  A carga e a inferência são protegidas por lock, incluindo o consumo dos segmentos.
  O módulo não torna a RAM compartilhada entre processos; as entidades devem
  enviar os áudios ao mesmo worker, não iniciar outro ASR por destinatária.
- CPU/int8, até quatro threads, somente arquivos de modelo já no cache local.
  Nenhum download de ASR é iniciado automaticamente.
- Entrada WAV PCM mono/estéreo, de 0,2 a 120 segundos e até 25 MiB.
  Áudio de navegador em 44,1/48 kHz é reamostrado para mono/16 kHz.
- VAD, silêncio, arquivo inválido/incompleto e transcrição sem fala aproveitável
  resultam em falha explícita. Erro não é transformado em mensagem do usuário.
- `speaker=usuario` no microfone primário é uma atribuição do papel da fonte:
  `speaker_basis=source_role`. Não é reconhecimento da voz de Gustavo.
  Outras fontes ficam com `speaker=desconhecido` até haver evidência de identidade.
- pyannote não está instalado no ambiente principal. O adaptador declara essa
  ausência; não inventa diarização ou identificação vocal.
- Idioma português configurado não aparece como confiança de identificação
  medida. Probabilidade de ausência de fala e log-probabilidade dos segmentos
  vêm dos campos reais do faster-whisper.
- Nenhuma captura, thread de microfone ou escrita em memórias é iniciada pelo
  simples import do módulo. `release_model()` libera sua referência na parada.

## Correção da escuta legada

`social/escuta.py` não afirma mais que um monitor separa aplicativos. Pistas como
Discord, jogo ou chamada não selecionam o monitor genérico nem um microfone como
substituto. Um endpoint real cujo nome corresponda à pista pode ser selecionado;
o nome sozinho não prova isolamento. Fontes técnicas exatas continuam permitidas,
e som do sistema pode usar monitor misto, com essa limitação explicada.

Foi corrigido também o caso em que a palavra `fone`, contida em `microfone`,
fazia a seleção escolher a saída de áudio em vez da entrada.

## Verificação

17 testes novos em `testes/test_audio_transcription.py` passaram sem rede/modelos
reais. As 21 verificações legadas de `testes/test_escuta.py` também passaram.

Ensaio real, sem reprodução/captura de hardware e sem publicar conversa:

- Fixture: `kokoro-legado-pf_dora-0.wav`, sintetizada localmente pelo motor legado.
- Duração: 5,675 s; PCM mono/24 kHz; 272444 bytes.
- SHA-256: `955cc2eadb93e0be7ef2658049d86cab88baedc18f48fe323326292c7bb888e3`.
- Texto esperado: “Olá, Gustavo. Estou verificando a síntese local em português
  brasileiro, sem reproduzir áudio.”
- Texto obtido nas duas chamadas: “Olá Gustavo, estou verificando a síntese local
  em português brasileiro sem reproduzir áudio.”
- Primeira chamada com carga: 11,800 s. Segunda chamada na mesma instância: 7,294 s.
- Probabilidade de ausência de fala: 0,0018048537; log-probabilidade média: -0,1631282151.
- Fonte do ensaio: `synthetic_tts_fixture`; speaker desconhecido, sem identificação
  vocal e sem diarização. A diferença observada foi apenas de pontuação.

Este ensaio confirma TTS local → WAV → ASR real e reuso da instância. Não confirma
qualidade em ruído, várias pessoas, microfone físico ou captura isolada de Discord.
