# Alistair: recuperação, limites e maturidade dos recursos

Data: 08/10/2026. Rodada de refinamento; sem modelos, bancos, ferramentas ou schedulers novos.

## O que mudou

`app/alistair_runner.py` agora classifica citações da tabela existente `alistair_turns` por termos e assuntos: identificação, regras, configurações, tarefas e localização. Acentos não impedem correspondência. Preserva quatro turnos de continuidade imediata; busca nos últimos 2000 turnos do mesmo remetente e considera também o primeiro contato.

Correções recentes e até dois combinados explícitos recebem espaço na seleção, inclusive quando o pedido atual não diz “regra”. Até oito citações, 600 caracteres por trecho e 3600 caracteres de conteúdo recuperado limitam a expansão do contexto. Os metadados ficam fora desse orçamento de caracteres. Nenhuma linha é apagada ou reescrita.

Cada citação conserva ID de origem, remetente, timestamp, tipo `citacao_historica` e indicação de trecho parcial/possível correção/possível regra. Não se inventa confiança que a tabela não tem. Respostas antigas do próprio modelo não entram como evidência na busca; os quatro turnos imediatos continuam incluindo respostas para continuidade. Históricos de outros remetentes não são automaticamente introduzidos.

O diagnóstico existente recebe `alistair.memory_retrieved`, quantidade examinada, limite da janela e IDs recuperados, sem o texto das mensagens. Consumidores existentes — chat, inspetor da Central e manutenção de memória — conservam o esquema da tabela.

As instruções operacionais explicam que:

- Dados pessoais devem vir de mensagens atribuídas, não de fatos predefinidos no código.
- Correções explícitas do mesmo autor e assunto podem superar versões antigas; conflito ambíguo exige esclarecimento.
- Perguntas, encenação e hipóteses continuam falas, não fatos verificados.
- Lembrar um estado de job não substitui consultar seu estado atual.
- Regras aprendidas não criam ferramentas nem anulam autorização e verificação.
- Pedidos excessivamente complexos devem receber uma limitação curta e natural, com um próximo passo pequeno; mencionar assunto complexo não basta para recusar uma consulta simples.
- Não acordar ou encaminhar outra entidade automaticamente para escapar de uma pergunta.

Exemplo de estilo desejado, não saída real observada: “Isso é grande demais para eu executar com segurança. Posso organizar os requisitos primeiro.”

## Limitações da recuperação

Não é memória perfeita, busca semântica universal ou aprendizado de pesos. Sinônimos fora dos grupos podem não casar. Informações além da janela, exceto o primeiro contato, podem não voltar. Trechos longos podem perder contexto; isso é indicado explicitamente. A resolução semântica de sujeitos/correções e a qualidade da recusa dependem do 4B e precisam de ensaio real. O teste de prompt usa inferência simulada e **não comprova** que o modelo sempre obedecerá. O orçamento geral da conversa, inclusive snapshots/ferramentas e turnos imediatos longos, continua sendo um risco a observar.

## Qwen3-TTS: GPU disponível no projeto, não no runtime atual

O caminho já existente em `app/core/audio_service.py:Worker.call` consulta suporte HIP do próprio ambiente e solicita o Resource Manager existente: P0, estimativa de 4 GiB de VRAM + 1 GiB de workspace, margem do RM e fallback CPU. Não descarrega LLM alheio para obter espaço. Worker GPU próprio fecha antes da devolução do lease; falha não repete automaticamente a síntese. A configuração conservadora continua sem concorrência GPU validada.

Probes somente leitura desta rodada:

- PyTorch do ambiente TTS: `2.6.0+cpu`.
- HIP: ausente; `gpu_available=false`; `--probe-device`: `amd_hip_available=false`.
- amdgpu/sysfs disponível: aproximadamente 7,98 GiB reportados, 489 MiB usados, utilização 0% naquela amostra. Isso não é teste sob carga.
- RAM: aproximadamente 31,23 GiB totais e 26,43 GiB disponíveis naquela amostra.
- Swap: 8 GiB ativos, aproximadamente 0,8 MiB usados. Não é somada à RAM disponível pelo RM.

Portanto **Qwen TTS permanece em CPU neste PC**. Vulkan/RADV usado pelos LLMs não fornece aceleração ao PyTorch automaticamente. A integração pode solicitar GPU quando existir um runtime HIP funcional e o RM permitir, mas uma detecção positiva de HIP ainda não substitui síntese real e medição de pico de memória. As estimativas de VRAM e o custo de carregar/fechar por síntese ainda não foram calibrados aqui.

A RX 6650 XT não consta na tabela oficial de GPUs suportadas consultada na [documentação AMD](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/reference/system-requirements.html). A AMD distingue suporte oficial de habilitação comunitária. Não foi instalado ROCm, trocado driver, aplicado override de arquitetura ou baixado outro modelo. Referência do backend existente: [Qwen3-TTS oficial](https://github.com/QwenLM/Qwen3-TTS).

## Maturidade do Resource Manager

Avaliação por inspeção e testes offline; não benchmark de uso prolongado. **Nota geral: 5/10 — sistema experimental com proteções úteis, ainda não maduro para uso pessoal prolongado sem observação.** Não é média simples: pressão agregada e recuperação limitam a nota.

| Área | Nota | Evidência e limite |
|---|---:|---|
| Arquitetura e integração | 7/10 | RM único, SQLite/locks, residência separada de compute. Adaptadores de áudio/LLMs/imagem convergem nele; observação de processos não é estado perfeitamente atômico. |
| Proteção GPU | 7/10 | Limite de 8 GiB, margem atual 768 MiB, métricas AMD, rejeição de métricas ausentes/instáveis, serialização. Ainda há intervalo entre medir e iniciar; aplicações externas podem alocar nesse intervalo. |
| Prioridade e espera justa | 4/10 | P0–P5 determina a ordem real da fila, FIFO dentro da prioridade. Não há aging; fluxo contínuo prioritário pode adiar indefinidamente classes baixas. |
| RAM e pressão | 4/10 | MemAvailable e margem de 2 GiB, staging e fallback verificados. Não é reserva agregada rigorosa de todos os workers, nem reage especificamente a PSI/swap thrashing. |
| Recuperação | 5/10 | Locks do kernel ajudam a retirar leases abandonados; testes de crash e cancelamento. Um daemon sobrevivente ao controlador exige reconciliação; liberar lease não prova ausência de compute real. |
| Telemetria e custos | 6/10 | Fila, duração, VRAM, motivos de decisão e reload observado em caminhos existentes. Parte das estimativas ainda é nominal; falta calibrar carga mista real. |
| Validação prolongada | 3/10 | Suíte offline e sondas reais limitadas não demonstram ausência de leaks, stalls ou starvation em horas de uso. TTS HIP nesta placa não validado. |

Pontos de código: `app/core/resource_manager.py` (`assess_executor`, `gpu_policy`, `assess_gpu`, `compute_lease`, `record_reload`), `app/core/gpu_metrics.py` e `app/core/audio_service.py:Worker`. A fila GPU não tem limite global explícito equivalente ao limite de quatro pendências do serviço de áudio. Alistair oportunista respeita trabalho prioritário já aguardando, mas um trabalho já iniciado não é interrompido arbitrariamente.

Não alterei heurísticas nesta rodada. Mantidos `concurrency_validated=false`, margem, modelos e CPU fallback. Próxima evidência útil: latência e memória de uma sessão curta real; depois fila prolongada, recuperação de daemon e pressão agregada em ensaios isolados.

## Validação

- Baseline focado antes da alteração: 19/19 em `test_prontidao_r1_r7`.
- Sete regressões adicionadas: nome corrigido após ruído/restart; regras/configuração/acentos; combinado recuperado sem pergunta explícita; isolamento de remetentes e saída inventada; citações hipotéticas; limites/legibilidade da tabela antiga; contrato do prompt e recusa simulada.
- Resultado focado final: **26/26**.
- Suíte completa intermediária: **74/74 grupos offline**.
- Suíte completa após o último ajuste: **74/74 grupos offline**, sem regressões encontradas.
- Verificações focadas adicionais: GPU cooperativo **28/28**, serviço de áudio **41/41**, executores leves/Alistair oportunista **47/47**. Transportes e dispositivos simulados nesses testes; não síntese GPU física.
- `git diff --check` dos dois arquivos alterados: sem erros.

Nenhum banco mental real alterado, entidade acordada, serviço reiniciado, síntese real executada ou quota externa consumida. Mudanças entram no próximo reinício cooperativo do processo Alistair; um processo já ativo não recarrega esse módulo sozinho.

## Arquivos desta rodada

- Alterados: `app/alistair_runner.py`, `testes/test_prontidao_r1_r7.py`.
- Criado: este relatório.
- Alterações anteriores de UI/voz e demais arquivos da árvore foram preservadas. Nenhum commit/push efetuado.
