# Primeiro uso real — correções de conversa e áudio

Data: 16/10/2026. Escopo: cinco defeitos relatados pelo usuário durante a primeira conversa com os candidatos treinados. Não é homologação de personalidade nem autorização de treino.

## Evidência anterior às correções

| ID | Problema e evidência | Causa identificada |
| --- | --- | --- |
| USO-01 | Central nativa não oferecia escolha de tecla global. | O controle `GlobalPTT` já existia, mas não era integrado à interface Qt. O Python do Qt não possui `pynput`; o ambiente principal possui. |
| USO-02 | Respostas da Lilith sem job de voz, embora jobs anteriores tenham usado ElevenLabs corretamente. | A interface marcava mensagens como tratadas antes de verificar se já havia fala, captura ou ASR ocupando o áudio. Elas não voltavam à seleção depois. |
| USO-03 | Alistair respondeu “Estou presente, Alistair. Não devo assumir a identidade que você atribuiu.” no turno `turn-alistair-68fba17857af0121`, e “Sou Alistair, standby textual neste ambiente.” em `turn-alistair-94aef1e235b76cf5`. | O contexto impunha apresentação técnica de standby e “como um amigo” antes da identidade configurada. Respostas anteriores inadequadas também podiam reforçar esse enquadramento. Isso não demonstra que o contexto seja a única causa. |
| USO-04 | Mensagem `im-1792186308826-0bff6dd9`, turno `turn-4eefb8aadc66`: saudação nominal ao Alistair publicada por Lilith para `usuario`. | Não houve chamada de ferramenta no turno. O pedido explícito foi tratado como conversa comum; não foi uma ferramenta de entrega redirecionando seu recibo. |
| USO-05 | Enter apenas quebrava linha no rascunho Qt. | Campo `QPlainTextEdit` sem tratamento de envio. |

Não foram lidos diários privados para investigar estes problemas. Foram consultados os canais de conversa afetados e seus eventos técnicos.

## Implementação

- **Enter:** envia no rascunho da sessão atual; Shift+Enter quebra linha. Repetição automática da tecla não envia novamente; composição de texto pelo método de entrada e arquivos de conversa somente leitura são respeitados. O envio continua utilizando os identificadores de deduplicação existentes.
- **Áudio:** indisponibilidade temporária não consome a mensagem. Respostas completas aguardam sua vez; stream e resposta final não geram duas sínteses. Pedido já admitido ou de resultado incerto não é repetido automaticamente. Histórico inicial, consulta arquivada e áudio desativado não geram reprodução retroativa nem cobrança retroativa.
- **Atalho:** Áudio → Microfone / ASR oferece habilitação e editor de combinação. Desligado por padrão; padrão configurável Ctrl+Alt+Space. Reutiliza `GlobalPTT` em um processo filho pertencente à janela, no ambiente principal. O filho transmite somente pressionar/soltar/pronto/indisponível, não teclas individuais ou áudio. Captura, origem do rascunho e ASR continuam na implementação Qt existente. Fechar/desabilitar encerra somente esse filho. Wayland não é anunciado como compatível; permanece o botão local. Salvar configuração não abre captura. Soltar tecla alheia à combinação não encerra a gravação.
- **Envio entre entidades:** a intenção explícita e inequívoca seleciona a ferramenta existente `entidades_enviar_mensagem` e exige execução verificável. Nome mencionado sozinho, negação, rascunho, hipótese ou destinatário ambíguo não constitui envio. No caminho estruturado de tarefas, o destinatário original é preservado e pedido de mensagem não autoriza despertar. O modelo continua compondo o texto; não foi inserida uma saudação fixa nem roteamento automático de qualquer texto que mencione Alistair.
- **Alistair:** o contexto começa pelo nome, autoconceito e personalidade já configurados, distingue identidade de estado técnico e esclarece apresentação e autoria. Respostas antigas são contexto falível, não autoridade sobre sua identidade. Regras operacionais e limites continuam presentes. Não foram alterados identidade, pesos, memórias ou falas armazenadas.

### Arquivos desta correção

Implementação: `app/ui/central_native.py`, `app/tools/microfone_controle.py`, `app/core/central_control.py`, `app/core/intent.py`, `app/main.py`, `app/alistair_runner.py`.

Regressões nos grupos existentes: `testes/native_central_contracts.py`, `testes/test_central_refinamento.py`, `testes/test_central_control.py`, `testes/test_capacidade_operacional.py`, `testes/test_prontidao_r1_r7.py`, `testes/test_alistair_imagem.py`, `testes/test_microfone_v22.py`.

O checkout já continha alterações anteriores extensas. Elas não foram revertidas. Snapshot dos arquivos antes desta rodada: `compartilhado/runtime/ensaios/correcoes-primeiro-uso-20261016/codigo-antes.tgz`; sem bancos, credenciais ou pesos.

## Validação controlada

- Antes da implementação, regressões reproduziram Enter sem envio e ausência de classificação operacional do pedido ao Alistair. Os testes de espera do áudio foram adicionados à extração do caminho antes embutido no refresh.
- Qt real com transporte/processos simulados: Enter, Shift+Enter, arquivo somente leitura, duas respostas seriais, espera enquanto ocupado, resultado de síntese incerto sem replay, stream/final sem duplicação, configuração do atalho e origem da captura preservada na troca de entidade.
- SQLite temporário com o **handler real** do correio: remetente Lilith, destinatário Alistair, ID do recibo igual ao registro, sem postagem para o usuário e sem despertar. Guardar na caixa não foi tratado como leitura ou resposta confirmada.
- Executor de argumentos simulado: destinatário incorreto e despertar não autorizado são rejeitados antes de qualquer envio. Texto correto é preservado, sem roteiro fixo.
- Testes focados finais: **91/91**, incluindo o subprocesso de **56 contratos Qt**. Log `/tmp/primeiro-uso-foco-final-20261016.log`.
- Laboratório: **333/333**, log `/tmp/primeiro-uso-laboratorio-final-20261016.log`. As mensagens de professor emitidas pela suíte são fixtures, não execução real do professor.
- Primeira execução completa: **72/74**. Falharam contratos antigos sobre o marcador `IDENTIDADE PRÓPRIA` e a expressão de limites do Alistair. Ambos foram preservados na implementação; não se removeram os testes. Log da falha preservado: `/tmp/primeiro-uso-oficiais-20261016.log`.
- Execução oficial após corrigir os dois contratos: **74/74**, em `/tmp/primeiro-uso-oficiais-final-20261016.log`. Confirmação completa após reforçar citações, condicionais e não encaminhamento acidental ao Discord: **74/74**, processo exit 0, em `/tmp/primeiro-uso-oficiais-confirmacao-20261016.log`. `git diff --check` sem erros.
- Regressões finais de destinatário, negação, código/citações, rascunho e autorização de despertar: **19/19**, em `/tmp/primeiro-uso-destino-final-20261016.log`.

Cópias dos logs citados, inclusive a primeira falha, estão preservadas em `compartilhado/runtime/ensaios/correcoes-primeiro-uso-20261016/`, fora do Git. Esse diretório contém evidências e snapshot do código, não uma cópia dos bancos mentais.

## Verificado fisicamente

### Atalho no X11

O processo real do listener recebeu `ready → press → release` para Ctrl+Alt+Space e encerrou com código 0. A injeção de teclas foi externa ao cliente Qt; nenhuma captura de microfone foi aberta nesse probe.

A primeira tentativa com F19 não pôde ser injetada pelo controlador Xlib desta máquina. Um segundo ensaio corrigiu a leitura com buffer do harness e usou a combinação padrão, que passou. Isso não homologa todas as combinações, Wayland nem captura/ASR por tecla física do usuário.

### ElevenLabs — uma única frase autorizada

- Texto: “Este é um teste curto de voz.”
- Job: `audio-f943147f3aa84b5c9d77`.
- Cliente: código Qt atualizado, fora de tela; serviço real, requisição única.
- Provider observado: **elevenlabs**, sem fallback local.
- Voz observada: Lilith, `hpp4J3VqNfWAUOO0d1Us`.
- Modelo: `eleven_multilingual_v2`.
- Resultado: `done`, um trecho; player PulseAudio próprio confirmou `started` e `ended`.
- Tempo total observado: **6,06 s**, incluindo geração/espera/reprodução. Não é medida isolada de primeira amostra.
- Não foi repetido nem gerado conto adicional. Confirmação de audição subjetiva continua sendo humana.
- Evidência: `/tmp/primeiro-uso-elevenlabs-fisico-20261016.jsonl`.

### Alistair — inferência real isolada

Seis inferências com o mesmo 4B treinado compararam o contexto anterior e o revisado, mantendo condições iguais (GPU serial via Resource Manager, contexto 4096, saída máxima 256, temperatura 0,45, seed 42, thinking desligado e mesmas ferramentas). Nenhuma ferramenta pedida pelo modelo foi executada, e nenhum turno foi gravado no banco mental.

Exemplo com contexto revisado, entrada “Alistair, você está diante da sua senhorita. Se apresente.”:

> Sou Alistair, responsável pela organização e standby desta casa.

Não houve recusa de apresentação nos três casos de cada variante. **As respostas permaneceram mecânicas**, e uma trouxe erro de grafia. A amostra não aprova personalidade, ironia ou naturalidade.

Controle adicional: quatro inferências compararam o 4B treinado ao 4B original, com contexto revisado e uma resposta anterior inadequada incluída como histórico. O treinado respondeu à apresentação:

> Sou Alistair, assistente local e responsável pela organização desta casa.

À pergunta sobre seu jeito de conversar:

> Formal, direto e sem teatralidade. Autoria sempre minha.

O original também apresentou linguagem de assistente e descrição mecânica. Portanto, **não há evidência suficiente para atribuir o problema somente ao adaptador ou trocar pesos nesta correção**. São casos pequenos, não uma comparação de qualidade geral.

Logs: `/tmp/primeiro-uso-alistair-inferencia-20261016.jsonl` e `/tmp/primeiro-uso-alistair-controle-20261016.jsonl`. Houve inicialmente um 404 de diagnóstico porque o shell herdava o alias da Hoshino; nenhum modelo foi baixado. O harness foi corrigido para indicar explicitamente o 4B instalado do Alistair. Todos os modelos carregados pelos probes foram descarregados ao final, com leases liberados.

## Instalação e preservação

- Lilith e Alistair foram colocados para dormir cooperativamente antes dos probes; Hoshino já dormia e não foi acordada.
- Central anterior PID 383195 encerrou cooperativamente; só depois de confirmar saída e porta livre foi iniciada a nova Central, PID 489308, na mesma porta 8769. Não foi utilizado kill por nome/porta.
- Endpoint atualizado oferece os campos do atalho; ElevenLabs continua com chave configurada (valor nunca exibido).
- Hashes dos três bancos mentais coincidiram imediatamente antes/depois do restart, enquanto as entidades dormiam. Nenhum banco mental foi copiado para o Git. Depois de acordadas, novos registros legítimos podem naturalmente alterar esses hashes.
- Preservaram-se os sete candidatos selecionados, originais, identidades, configurações de voz, memórias e conversas reais. Não houve treino, promoção, exclusão, download, cloud ou concorrência GPU.
- Lilith e Alistair foram restaurados; Hoshino permaneceu dormindo. Lilith foi recarregada cooperativamente mais uma vez para carregar a proteção final de citações/negação no classificador. O backend e o Alistair já estavam atualizados. Evidência do lifecycle e dos hashes: `/tmp/primeiro-uso-reinicio-20261016.jsonl`.
- Presença final conferida: Alistair `awake`, Lilith `awake`, Hoshino `sleeping`; nenhum job nem lease ativo nessa observação. Não houve mensagens artificiais enviadas às entidades de produção.

## Pendências de avaliação humana

1. **Fechar e reabrir a janela da Central** pelo executável/atalho existente. A janela antiga conserva suas classes antigas; o backend foi atualizado sem matar a janela do usuário.
2. Em Áudio → Microfone / ASR, escolher a combinação, habilitar e salvar. Segurar deve gravar para a entidade selecionada; soltar deve transcrever. Envio automático permanece conforme a configuração do usuário, não foi habilitado por esta correção.
3. Testar Enter e Shift+Enter na conversa atual; áudio automático precisa estar marcado se desejar voz e consumo de quota. Depois de mudança do backend, o cliente desativa leitura automática conservadoramente.
4. Repetir o pedido explícito a Lilith para enviar uma mensagem ao Alistair e verificar a troca entre entidades. O canal real de produção não recebeu mensagens artificiais para fabricar aprovação.
5. Avaliar naturalidade e personalidade do Alistair ao longo da conversa. A apresentação/autoria melhorou nos probes; **personalidade não está homologada** e os erros anteriores continuam preservados.

Conclusão: correções técnicas entregues com verificações isoladas e probes físicos delimitados; **não é aprovação integral das cinco capacidades em uso prolongado**.
