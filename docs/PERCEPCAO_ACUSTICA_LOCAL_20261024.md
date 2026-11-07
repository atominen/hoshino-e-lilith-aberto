# Microfone: atalho reservado e percepção acústica local

## Uso e autoria

**Central → Áudio → Microfone / ASR** mantém só dois modos:

- **Comando:** botão/atalho para falar, com o transcritor existente.
- **Detecção:** captura contínua explicitamente aberta e autorizada. Além do
  ASR, um detector CPU classifica sons sem depender do limiar de fala.

Abrir o painel não abre o microfone. Alt+W ou a combinação configurada fica
reservada no rascunho: não insere W, substitui seleção ou vaza repetição após
mudar o foco. O listener global permanece o único acionador do microfone;
não há bloqueio das teclas de outros aplicativos. Falta teste físico global.

O painel informa disponibilidade, escuta, som provável e janelas perdidas.
Desativar **Ouvir o ambiente**, parar captura, mudar destinatária/escopo ou
encerrar invalida resultados pendentes. Comando/ASR não depende do detector.

Sons não viram mensagens humanas nem comandos. Recibos mínimos ficam no job
bus existente, sem PCM/WAV/base64. Global entrega às entidades já acordadas e
autorizadas; direto somente à selecionada. Hoshino/Lilith recebem contexto
perceptivo uma vez; Alistair vê percepções frescas no próximo turno normal.
Não há inferência de LLM por janela, despertar automático ou resposta obrigada.

O evento é **provável, com autoria desconhecida**: não diz “você riu”, não
infere emoção, identidade ou consentimento; score não é porcentagem de certeza.
Não existe garantia de reconhecer TODA risada ou todo som.

## Continuidade e recursos

PCM16 mono16kHz; janelas15600 amostras (975ms), avanço7680 (480ms), em RAM.
A UI mantém um pedido em voo e só a janela mais recente aguardando; sobrecarga
descarta janelas e mostra a contagem. Saturação da fila ASR não fecha Detecção.
Worker separado, dois threads, lease CPU próprio, checagem de RAM e prazo6s.
Sem GPU, cloud, quota de voz ou gravação permanente contínua. Falha/resultado
incerto exige nova ativação manual; não baixa modelos ou repete escondido.

Parar tem um slot de cancelamento reservado mesmo com8 pedidos ocupados.
Nova Detecção aguarda confirmação do servidor; cancelamento incerto permanece
visível, sem retry automático. Nesse caso, encerrar a Central cooperativamente
reconcilia o worker antes de reabrir. Observações entregues às entidades mantêm
o horário real da captura em UTC, inclusive se só entrarem num turno posterior.

A captura continua durante o player do app. Janelas sobrepostas são marcadas
e não entregues às entidades; trechos ASR contaminados não são enviados. Há
cauda1,1s. **Não é cancelamento de eco**: pode perder voz/risada humana junto
do player e não distingue o som de outra aplicação. Fones ajudam; eco real
é trabalho separado.

## Proveniência e preparação explícita

- [YAMNet Google, geração1665848355781994](https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/audio_classification/rpi/lite-model_yamnet_classification_tflite_1.tflite?generation=1665848355781994),4.126.810bytes,521 classes.
- Modelo SHA256`10c95ea3eb9a7bb4cb8bddf6feb023250381008177ac162ce169694d05c317de`.
- Classes embarcadas SHA256`8e1267a120c1932b7273c0d0e0c5529edbb9a35512b437b1c8982baa59047051`.
- [Fonte YAMNet / Apache2.0](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet).
- Python3.12 isolado,`ai-edge-litert==2.3.0`,NumPy2.2.6; ambiente principal não atualizado.
- Wheel Linuxx86_64cp312 SHA256`dc9f56c23e0dcf182b6c35f23fbb102ed048296588882b806d5eff7654c04c88`.

Pesos/runtime não entram no Git. Não há aquisição na importação ou captura:

```bash
/usr/bin/python3 -B scripts/preparar_percepcao_acustica.py --install
```

Referências: [entrada/classes](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio),
[LiteRT](https://developers.google.com/edge/litert/libraries/task_library/audio_classifier),
[fala/assobio do exemplo oficial](https://www.tensorflow.org/hub/tutorials/yamnet).

## Ensaio real e limites observados

[Relatório com hashes por referência](verificacao_percepcao_acustica_20261024.json).
Nenhum microfone capturado, conversa enviada, LLM/Xbox ativado ou provider pago.

199 janelas/110,815s de referências e transformações declaradas:

-8 clipes rotulados como risada:8 detectados com limiar0,10; o inicial0,25
  detectava só2 dos primeiros4. Ajuste baseado nos primeiros2; os demais6
  foram checagem posterior, não benchmark amplo independente.
-Ganho0,05 e recorte400ms de risada detectados; mistura50/50 de fala/risada
  **não detectada**. Transformações não são novas gravações independentes.
-Tosse1/3 e espirro2/3. Alguns clipes de risada também receberam tosse/espirro.
  Existem confusões reais; classes não são exclusivas.
-Fala/assobio, silêncio, chuva, relógio, palmas, teclado: sem falso evento
  vocal nesses6 casos; parte gerou sons ambientais prováveis.
-CPU total0,8021s (~4,03ms/janela); parede média~3,51ms, maior janela12,7ms.
  RSS máximo~78,4MiB. Medidas desta máquina, sem carga equivalente ao uso
  completo, não garantia de latência em produção.
-Worker separado real, partida fria com silêncio:~104ms até resposta; processo
  próprio encerrou confirmado. Isso não valida o microfone.

ESC-50 revisão`33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6`,
[atribuição/licença CC BY-NC3.0](https://github.com/karolpiczak/ESC-50#license),
somente pesquisa local. Áudios não são redistribuídos no repositório. Referências
baixadas só com opção explícita, mantidas em RAM durante o ensaio:

```bash
compartilhado/ambientes/percepcao-acustica/bin/python -B scripts/verificar_percepcao_acustica.py \
  --download-reference --output /tmp/percepcao-acustica.json
```

## Verificação e reversão

Suíte offline: PCM/janelas/protocolo, HTTP autenticado, deduplicação, permissão,
cancelamento, saturação, continuidade ASR/TTS, autoria e restart sem IDs antigos.
Resultado final/revisão constam no plano; fixtures não aprovam qualidade real.
Parar Detecção ou desativar Ouvir o ambiente desliga a escuta; o atalho reservado
independe do modelo acústico. Nenhuma reversão exige resetar memórias, trocar
pesos de conversa ou mudar Xbox. Teste físico de microfone/atalho/voz própria
permanece pendente, com consentimento e sem fingir conversa humana de teste.

## Revisão independente

Revisão somente leitura identificou duas falhas importantes: a primeira janela
perdia`sequence=0` na montagem da URL e o cancelamento podia ser recusado pela
fila HTTP cheia. Ambas foram reproduzidas em testes falhando antes da correção;
o novo contrato usa a URL gerada pela UI até a validação real do serviço.
O teste de slot reservado cobre8 pedidos ocupados e bloqueio de nova captura
até confirmação. A descrição também passou a preservar o horário observado.
Testes específicos:18 casos acústicos,42 grupos de refinamento contendo112
contratos Qt e42 casos de serviço/HTTP. Nada disso aprova hardware real.

Suíte final após as correções: **90/90 grupos offline**. Uma execução anterior
teve falha intermitente num teste antigo de recibo/processo (sem alteração nesta
tarefa); o grupo isolado19/19 e a repetição serial completa passaram. Não houve
supressão de teste nem mudança de terminal/treinamento para obter aprovação.
Commits locais: implementação`f83a1ce` e correção final posterior. Sem push/merge.

Entrega local: correção`f99e5b2`; Central e UI reabertas sem selecionar entidades
para despertar. API real`audio/state`200 confirmou modelo/runtime disponíveis
em CPU e worker ainda inativo; pedido PCM inválido respondeu400 sem inferência.
Estado real confirmou0 entidades acordadas e nenhum processo de captura.
Nenhum teste de microfone real foi feito e nenhuma sessão de treino iniciada.
