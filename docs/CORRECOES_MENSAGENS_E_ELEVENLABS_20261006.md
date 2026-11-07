# Correções de mensagens e integração ElevenLabs

Data: 06/10/2026. Raiz: `/home/gustavo/hoshino e lilith`.

## Resultado e limites

Rodada autorizada após a [auditoria anterior](AUDITORIA_MENSAGENS_ORDEM_CAUSALIDADE_20261006.md). Foram corrigidos defeitos reproduzíveis de fila, contexto, entrega, cancelamento e recibos. ElevenLabs foi acrescentado ao roteador de voz existente, não como outro sistema de áudio.

Nenhum checkpoint foi baixado, substituído ou apagado. Nenhum banco mental real foi migrado ou alterado pelos testes. Não houve reinício de entidades/serviços reais, abertura de microfone, conexão Discord/Minecraft real ou gasto de quota de voz. Identidades, memórias, relações e executores independentes permanecem intactos.

Cloud de cognição permanece desativada em `compartilhado/config/capacidades.json`. A exceção de escopo autorizada é somente ElevenLabs TTS opcional. `concurrency_validated=false`, margem GPU, Resource Manager e escolha 9B/7B/4B não foram modificados. O congelamento de outras capacidades/modelos/sistemas continua vigente.

## Defeitos corrigidos

| Problema observado | Correção e contrato atual |
|---|---|
| B descartada quando C já estava aguardando | Mensagens comuns não cancelam mais um turno por estarem na fila. A, B e C recebem seus próprios turnos na central, em FIFO. |
| Turno B enxergava C antes de processá-la | Snapshot termina na mensagem selecionada. Pergunta/objetivo não se desloca para uma entrada futura. |
| Resposta inserida fora de lugar após compactação | Compactação atua no prefixo do turno. A mensagem de origem ancora a resposta antes das entradas posteriores. |
| `não, direita` e `PARA` não cancelavam | Marcadores explícitos são reconhecidos; `não sei`, `para conversar`, dependência e complemento não se tornam cancelamento. |
| Correção já na fila ainda executava intenção velha | Cada entrada carrega sua revisão. Entradas superadas são finalizadas como `superseded`, sem executar a intenção anterior. |
| Correção por microfone não invalidava texto local | Revisão alcança canais locais do mesmo participante local. Não alcança outro autor/Discord; isso não é identificação biométrica. |
| Mensagem presa indefinidamente em `_interentity_inflight` | Todos os desfechos do worker liberam o controle em RAM. Estado durável diferencia resposta, substituição, falha e incerteza. |
| Timeout/erro parecia silêncio sem estado | Metadados existentes registram status, timestamp, motivo e `auto_retry=false`; a central mostra a distinção. Falha não recebe confirmação de resposta. |
| Primeira página ocultava novas mensagens | Caixa postal exclui IDs já reivindicados e entradas retidas por falha/incerteza antes de aplicar o limite. `peek` continua expondo essas entradas. |
| Ordem da caixa postal divergente da interface | Ambas usam ordem de inserção/commit SQLite (`rowid`), não timestamps atribuídos antes da transação. |
| ASR do navegador chegava como escrita ao modelo | Origem de áudio, modalidade e participante local são propagados ao worker/contexto; IDs/timestamps do transporte entram no histórico. |
| Debounce não tinha prazo máximo | Tempo desde a última entrada, limitado por janela máxima de 3,6 s ou pela janela configurada se maior. Entradas legadas sem timestamp ganham uma referência estável. |
| Ação começava depois de esperar um lock já cancelada | Nova checagem imediatamente após adquirir a trava, inclusive na recuperação de workspace. |
| Efeito anterior perdido ao cancelar um lote de ferramentas | Recibos concluídos são devolvidos antes da invalidação do turno. Ferramentas seguintes não são iniciadas. |
| Cancelar coroutine liberava trava enquanto sua thread ainda escrevia | Ação iniciada permanece protegida até seu resultado. Cancelamento é drenado, registrado e propagado depois; não há kill/repetição. |
| `PARA` esperava uma navegação longa terminar | Stop cooperativo existente pode ultrapassar exclusivamente a trava da navegação própria (`ir_para`/`seguir_jogador`). Não interrompe craft/mineração/outro autor/processos. |
| Timeout mutável de Minecraft virava erro seguro para repetir | Após envio sem recibo: `RESULTADO_INCERTO`, propagado ao contrato e diário de ações existentes. Segunda ação idêntica é bloqueada por esse diário. Consulta sem efeito mantém erro comum. |
| IDs Minecraft colidiam no mesmo milissegundo | UUID por RPC, entidade e parent/turn ID no pedido; recibo com ID diferente é recusado. Compatibilidade com respostas legadas sem ID permanece. |
| Duplo envio/retry de transporte criava duas intenções | UI usa `submission_id` estável por tentativa; endpoint reutiliza o envelope por chave. Outro ID permite repetir intencionalmente o mesmo texto. Reuso do ID com texto diferente é recusado. |
| Discord removia entrada antes de responder | Caminho principal lê sem consumir. Envelope persiste com desfecho; o ID original Discord gera uma identidade estável e dedup sobrevive a reinício. |
| Hash do ID Discord poderia embaralhar entradas | Leitura usa ordem de gravação do arquivo, não ordenação alfabética do hash. |
| Reenvio repetia trechos Discord já entregues | Cursor confirmado por trecho no envelope existente. POST em andamento/resultado incerto é retido e não repetido automaticamente. Arquivo de anexo ausente não é apresentado como entrega completa. |
| Evento de jogo nunca chegava ao contexto | Log Minecraft existente alimenta a janela de observações existente, com origem, entidade, PID/seq, horário e sessão quando presentes. Nunca vira fala/ordem humana. |
| Diagnósticos sem ligação ao turno | Decorador de contexto já existente é usado em `responder`; histórico de saída reutiliza o mesmo turn ID. Estado final não é sempre chamado `ok`. |
| Áudio antigo podia continuar após correção | Revisão invalida o produtor imediatamente, inclusive durante verificação final. Síntese acompanha invalidação e rejeita resultado remoto tardio. |
| Interrupção acontecia sem envio confirmado, ou atingia uma resposta nova | Apenas após persistir nova entrada, central cancela falas próprias anteriores daquela entidade. Rejeição/retry deduplicado, ASR, outra entidade e jobs posteriores ficam intactos. |

### Entrega durável sem novo banco

`entity_messages.metadata.processing` usa `processing`, `answered`, `superseded`, `failed` e `uncertain`. Dados antigos sem esse campo continuam legíveis. `answered` e `superseded` finalizam leitura, com rótulos diferentes na interface; falha/incerteza permanecem não lidas e visíveis, mas fora do processamento automático.

Se um processo cair deixando `processing`, não sabemos se uma ferramenta produziu efeito: o item fica retido para verificação. Isso privilegia não duplicar efeitos em vez de simular uma recuperação exatamente uma vez. Não houve migração cega dos dados anteriores.

No barramento de arquivos Discord, estados ficam nos envelopes existentes. O consumidor legado `channels.receber()` continua com consumo imediato por compatibilidade; o laço principal usa explicitamente leitura sem consumo. Envelopes concluídos com source ID são preservados para deduplicação.

## ElevenLabs

Integração HTTP direta, sem SDK novo, por sentença estável já produzida pelo pipeline existente. Usa `POST /v1/text-to-speech/{voice_id}`, autenticação `xi-api-key` e PCM de 24 kHz convertido em WAV mono 16 bits, mantendo reprodução ordenada. Referências: [API oficial](https://elevenlabs.io/docs/api-reference/text-to-speech/convert) e [formatos do SDK oficial](https://github.com/elevenlabs/elevenlabs-python/blob/main/src/elevenlabs/types/tts_output_format.py).

O modelo inicial configurado é `eleven_multilingual_v2`, que suporta português; `model_id`/variável de ambiente permitem escolher outro modelo compatível com esse endpoint, sem instalação local. Não foram adicionados clonagem, STT ElevenLabs, WebSocket ou outros serviços. Português/sotaque da voz escolhida ainda precisam de escuta real. [Modelos oficiais ElevenLabs](https://elevenlabs.io/docs/overview/models).

### Configuração

Arquivo existente: `compartilhado/config/audio.json`.

- `backend` continua sendo o motor LOCAL (`qwen3_tts` ou `kokoro`), nunca `elevenlabs`.
- `elevenlabs.enabled=false` inicialmente: nenhum envio externo inesperado.
- Para escolher ElevenLabs, definir `preferred_provider="elevenlabs"`, `elevenlabs.enabled=true` e os IDs de voz de Hoshino/Lilith.
- IDs em `elevenlabs.voices.hoshino` / `.lilith`, ou variáveis `ELEVENLABS_TTS_VOICE_HOSHINO` / `ELEVENLABS_TTS_VOICE_LILITH`.
- Chave exclusivamente em `ELEVENLABS_API_KEY` no ambiente do processo da central; `key_env` permite um nome diferente. Nunca colocar a chave no JSON, código ou repositório.
- Modelo em `elevenlabs.model_id`, ou `ELEVENLABS_TTS_MODEL`.
- Prazo padrão 6 s, máximo 15 s; cooldown padrão 30 s. Os valores são configuráveis dentro desses limites.

Sem chave ElevenLabs, a seleção Azure/local anterior continua funcionando. Azure continua preferencial por padrão quando configurado. Se ElevenLabs for escolhido e falhar por rede, autenticação, quota, prazo, áudio inválido ou erro de provider, entra **Qwen3-TTS local obrigatório**. Não há cadeia de tentativas remotas consumindo mais quota; Kokoro permanece como opção local legada, não substituto oculto do fallback obrigatório.

Cancelamento não inicia fallback. A resposta tardia de uma requisição não pode sobrescrever o arquivo local. Headers/corpos de erro remotos e texto sintetizado não são registrados. Diagnóstico contém provider, voz, latência e código de falha sanitizado. Chaves padrão e nomes customizados são removidos do ambiente dos workers ASR/TTS; redaction também cobre `xi-api-key` e o espelho de histórico.

Cancelamento local não garante estorno nem cancelamento da cobrança de uma síntese já aceita pelo servidor. Texto enviado para provider remoto segue o serviço/configuração da conta; não prometemos retenção zero.

## Modelos: avaliação da proposta, sem troca nesta rodada

Há uma premissa incorreta no rascunho: `entidades/hoshino/entidade.json` já aponta para `hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M`. Lilith declara a mesma fonte sob alias próprio. Portanto, não é uma troca simples de “9B oficial” por “9B abliterated”: o baseline real já é derivado comunitário. A página do modelo o descreve como GGUF de um fine-tune, mas isso não prova o estilo ou capacidade dos pesos locais. [Fonte configurada](https://huggingface.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF).

| Candidato | Avaliação nesta rodada |
|---|---|
| `wangzhang/Qwen3.5-9B-abliterated` | Bom candidato para comparação conservadora, não vencedor estabelecido. Autor reporta 2/200 recusas e KL 0,0105; não são validação nossa de português, ferramentas ou personalidade. A revisão exata do modelo-base não foi registrada na publicação. O repositório principal contém BF16 de 18,8 GB, não o GGUF Q4 pronto que cabe na nossa rota local. [Card](https://huggingface.co/wangzhang/Qwen3.5-9B-abliterated), [arquivos](https://huggingface.co/wangzhang/Qwen3.5-9B-abliterated/tree/main). |
| `huihui-ai/Qwen2.5-7B-Instruct-abliterated-v2` | Candidato 7B válido para A/B contra o leve atual. A descrição de melhoria sobre outra abliteration não demonstra preservação de tool calling, precisão, memória ou estilo em nosso contexto. Não escolher só por menos recusa. [Card](https://huggingface.co/huihui-ai/Qwen2.5-7B-Instruct-abliterated-v2). |
| Defiant Fable 9B | Somente candidato experimental, com variante/revisão/quantização exatas. O card traz diretrizes específicas de chat/roleplay e sampling; não é evidência de neutralidade ou superioridade. Não adotar seus presets automaticamente. [Card do autor](https://huggingface.co/DavidAU/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP-GGUF). |
| `kaineone/Qwen3.5-4B-abliterated-GGUF` | O card o posiciona como órgão de linguagem do KAINE e recomenda suprimir thinking, descrevendo-o como voz, não reasoner. Isso exige cautela especial para Alistair, que faz planejamento/triagem. Arquivo publicado indicado em 2,78 GB, diferente do arredondamento ~2,6 GB do texto. Só considerar substituição após teste Athlon real. [Card](https://huggingface.co/kaineone/Qwen3.5-4B-abliterated-GGUF). |

Minha decisão é manter os modelos atuais e primeiro comparar o 9B atual com a variante conservadora e o 7B atual com a v2, antes de promover qualquer candidato. Abliteration/KL baixo não garantem um cérebro “vazio”, neutralidade, ausência de hábitos de assistente ou igualdade de identidade entre executores. Também não garantem ganho de latência. A intenção continua sendo identidade/memória/estado externos aos pesos; contratos operacionais não dependem de obediência do checkpoint.

### Protocolo A/B proposto — não executado

Usar a avaliação existente, sem criar outro módulo/scheduler. Cada comparação deve manter os mesmos snapshots de identidade, memória, relações, prompts, parâmetros e workload, sem aprendizado persistente na entidade real. Serializar GPU; RX 6650 XT 8 GiB com margem, Vulkan/RADV, sem CUDA.

Avaliar em português, para ambas as entidades: conversa casual, mudança de assunto, silêncio, correção/interrupção, lembrança incerta, discordância, erro próprio, conversa emocional, rotina 7B, decisão importante 9B, tarefa com ferramentas e reflexão profunda. Avaliação cega de naturalidade, estilo de assistente/RP, repetição, falsa certeza, fidelidade ao estado externo, mistura entre entidades e mudança de estilo 7B/9B. Ferramentas sempre isoladas, com recibo/verificação, nunca ações reais como benchmark.

Medir cold/warm load, primeira resposta, tempo total, tokens/s, RAM, VRAM e utilização GPU no mesmo workload. Antes de uma futura transferência, fixar revisão/SHA, fonte e licença, estimar pesos + cache + conversão/staging + margem e verificar espaço novamente. Leitura nesta rodada: disco de 817 GiB, ~83 GiB disponíveis, 90% utilizado; nenhuma autorização implícita para preenchê-lo ou apagar modelos. Não empilhar checkpoints na GPU e não promover um candidato só por tamanho ou taxa de recusa.

## Testes e regressões durante a implementação

Todos os testes citados são offline, com modelos/providers/transporte/hardware mockados e persistência temporária. Não validam timbre real, qualidade de checkpoint ou navegação real.

| Execução | Resultado |
|---|---|
| Suíte antes das alterações | 65/65 grupos, exit 0 |
| Primeira suíte expandida | 65/67; dois conflitos expostos, não ocultados |
| Alistair após correção de compatibilidade | 20/20 testes, exit 0 |
| Central após atualização justificada da fixture | 17/17 testes, exit 0 |
| Novo `test_mensagens_causalidade` | 32/32 testes, exit 0 |
| Novo `test_elevenlabs_tts` | 18/18 testes, exit 0 |
| `test_audio_service` com duas regressões HTTP novas | 36/36 testes, exit 0 |
| Azure existente | 17/17 testes, exit 0 |
| Suíte expandida anterior à última revisão | 67/67 grupos, exit 0 |
| Suíte final após todas as alterações de código/testes | 67/67 grupos, exit 0 |

Total novo: 52 testes (32 + 18 + 2). Os testes de mensagens usam o worker/responder/dispatcher reais com o modelo simulado, não a classe `ConversationState` para fingir validação do laço principal. O teste antigo dessa classe continua sendo unitário da classe, não prova de produção.

Os conflitos da primeira execução foram:

1. **Regressão introduzida na rodada:** rejeitar mudança de texto em toda chave de dedup bloqueava notificações de progresso legítimas do Alistair. Restrição de payload foi limitada à chave de submissão humana `central:`; dedup de notificações mantém seu contrato. Regressão nova cobre essa compatibilidade.
2. **Fixture desatualizada pelo contrato de reivindicação:** teste headless consultava `inbox` para inspecionar uma mensagem já reivindicada. Agora usa `peek`, verifica `read_at=None` e `processing`, publica uma resposta real no barramento e verifica entrega. Não reintroduz replay inseguro nem fabrica sucesso.

Também foram corrigidos durante desenvolvimento, antes da validação final: inicialização dos mapas opcionais de voz ElevenLabs e fixtures novas que inicialmente não atingiam a ação (roteamento do frame) ou chamavam método de worker inexistente. Asserções de efeito/cancelamento foram preservadas; foram ajustadas as fixtures ao componente realmente exercitado.

## Arquivos alterados

Produção/configuração:

- `app/main.py`: workers, snapshots/âncoras, revisão local, finalização, observações Minecraft, proteção de thread mutável, stop cooperativo e cancelamento de áudio.
- `app/core/conversation.py`: marcadores explícitos de correção.
- `app/core/interentity.py`: estados no envelope, fila disponível versus retida, commit order e dedup compatível.
- `app/social/channels.py`: persistência/estados de entrega, origem Discord e checkpoints de envio.
- `app/integracoes/discord_bot.py`: ID original e envio por trecho com recibo.
- `app/tools/minecraft.py`: RPC UUID/parent/entidade, resultado incerto e rejeição de recibo trocado.
- `app/core/tts_router.py`: ElevenLabs, transporte remoto compartilhado e fallback obrigatório.
- `app/core/audio_service.py`: isolamento de segredos, estado das vozes, interrupção seletiva e invalidade do produtor durante síntese.
- `app/tools/voice.py`: isolamento de segredos no caminho nativo.
- `app/core/diagnostics.py`: segredos ElevenLabs e desfecho real do turno.
- `app/ui/central.html`: ID estável de submissão e rótulos de processamento.
- `iniciar_entidades.py`: idempotência HTTP e interrupção somente após aceite, sem cancelar resposta posterior.
- `compartilhado/config/audio.json`: provider opcional desativado e configuração por nomes de ambiente/IDs.

Testes/documentação:

- `testes/test_mensagens_causalidade.py` e `testes/test_elevenlabs_tts.py`: novos grupos.
- `testes/test_audio_service.py`: regressões do endpoint de envio.
- `testes/test_central_entidades.py`: fixture atualizada com evidência de estado/entrega reais.
- `testes/catalogo.py` e `testes/executar_isolado.py`: inventário e remoção de credenciais reais.
- Este relatório. A auditoria original permanece como registro histórico anterior às correções.

Backup reversível de fontes anteriores: `arquivo/refinamento_20261006_mensagens_voz/fontes_antes.tar.gz`. Não inclui modelos/bancos mentais; sua finalidade é recuperar as fontes/configuração desta rodada. Não restaurar tudo cegamente por cima de trabalho posterior.

## Riscos e próximas prioridades dentro do escopo

1. **ElevenLabs real pendente:** chave/IDs não foram configurados nem usados nesta rodada. Ainda faltam Hoshino/Lilith reais, sotaque/timbre, primeira sentença, várias frases, autoplay, rede, quota e cancelamento em conta real.
2. **Não há DAG ou ordenação causal global.** FIFO é por conversa/caixa postal. Observações Minecraft preservam fonte/seq/sessão/horário, mas isso não cria uma ordem total entre microfone, Discord, dois processos e eventos do jogo. Relação exata entre evento do jogo e RPC ainda depende de sessão/diagnóstico, não de reconstrução universal.
3. **Janela de observações é limitada.** Eventos antigos/overflow continuam no log, mas nem todos entram no contexto curto. Inicialização não reinterpreta o diário antigo como jogo acontecendo agora. Não foi adicionada reação automática de combate/dano.
4. **LLM iniciado pode continuar gerando:** cancelamento invalida fala/resposta/ações seguintes; não há kill do daemon nem promessa de interromper compute imediatamente. Uma ação mutável iniciada/travada mantém a trava até encerrar, com diagnóstico, para não entrelaçar efeitos.
5. **Stop cooperativo não é kill universal:** alcança somente navegação atribuída ao mesmo participante/entidade pelo dispatcher. Mineração/craft e ações fora desse caminho não são interrompidos à força. Minecraft/Discord reais e latência de parada ainda precisam de ensaio local.
6. **Entrega externa exatamente uma vez não é garantida.** Crash durante POST Discord gera estado retido/incerto. Verificação/retomada exige inspeção humana ou os mecanismos atuais; não há replay automático. Edições Discord não foram adicionadas como nova capacidade.
7. **Envelopes retidos e tombstones consomem disco.** Não há limpeza automática nova nem exclusão de dados. Medir crescimento em uso prolongado antes de ajustar retenção.
8. **Compatibilidade legada explícita:** consumidores externos sem `submission_id` continuam podendo enviar duas mensagens iguais. RPC sem request ID na resposta ainda é aceito; um ID divergente não é. O caminho antigo de consumo imediato do barramento segue disponível, mas não é usado pelo worker principal.
9. **Checkpoint e hardware pendentes:** nenhum A/B, PC2 Athlon, coexistência prolongada de imagem/conversa, leak/deadlock ou comparação 7B/9B real foi validado por estes mocks. Scheduler conservador e fallbacks atuais foram preservados, não recalibrados por suposição.

Não considerar o projeto “completamente aprovado” com base na suíte offline. Próxima rodada prioritária: configurar duas vozes autorizadas, ensaio real controlado de voz + interrupção; depois o cenário Minecraft/conversa/voz com recibos e observações, e somente então decisões sobre checkpoints com medidas e A/B.
