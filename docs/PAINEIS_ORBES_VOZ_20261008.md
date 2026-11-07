# Painéis, orbes e verificação das entidades — 08/10/2026

## Implementado

- Recursos: cartões CPU/RAM/VRAM/GPU, tendências de até 120 consultas, swap, margem e disco. Compute, fila e residência em tabelas separadas. Medição ausente não vira zero. Falha da consulta invalida os valores atuais. Sem novos timers de polling; usa a consulta existente da aba ativa.
- Atividade: linha do tempo filtrável por conteúdo/IDs, severidade, autoria, turno; guia de comandos com saída filtrada pelo backend. Dados técnicos completos continuam acessíveis sob demanda. Não implica ordem causal global. Respostas atrasadas de outra entidade não entram no painel atual.
- Serviços: cartões dos provedores, preferência, vozes e fallback, chave somente como estado configurada/não configurada. Nunca confunde configuração com conexão ou consumo autorizado. Diagnóstico usa o mesmo componente visual de eventos, limitado aos erros da entidade selecionada.
- Orbes: escolha por entidade entre energia/imagem local, seletor de cor base, opção de tingimento por emoção disponível. Contorno dourado/lilás/menta mantém identificação. Não escreve emoções. Alistair continua sem perfil afetivo. Imagens PNG/JPEG/WebP de até 10 MiB, dimensão máxima 4096 por lado; imagens inválidas caem no visual energia, com aviso no tooltip. Sem downloads, geração ou compartilhamento automático de assets.
- Configurações no arquivo de interface existente; validação, revisão e backup atômico preservados. Nenhum banco ou API paralela.
- Qwen TTS: probe do próprio ambiente, sem pesos, confirma suporte AMD/HIP antes de solicitar GPU. Prioridade P0 no Resource Manager existente; orçamento conservador de 4 GiB mais 1 GiB de workspace, margem do RM, RAM de staging, `overlap_safe=false`, fallback CPU. Worker GPU owned encerrado antes de liberar compute; nenhum unload de LLM alheio. Erro não repete síntese automaticamente. Dispositivo/lease acompanham resultado e diagnóstico. Caminhos Central e ferramenta de voz usam o mesmo Worker.

## Limitação real da voz

Probe local: PyTorch `2.6.0+cpu`, HIP ausente, disponibilidade GPU falsa. `voice_worker.py --probe-device` confirmou `amd_hip_available=false`. Portanto **não houve síntese GPU real e a instalação atual continua usando CPU**. Vulkan/RADV dos LLMs não fornece aceleração ao PyTorch automaticamente. Não foram instalados drivers, wheels ou hacks de compatibilidade; a integração GPU está coberta por mocks, não validada fisicamente nesta RX 6650 XT. Instalar runtime AMD compatível e realizar ensaio controlado é uma etapa pendente, não um sucesso declarado.

## Confirmação das entidades

- Hoshino e Lilith: manifestos indicam a mesma camada de pesos principal Qwen3.5-9B-Uncensored Q4_K_M (`07bc4714…`) e leve Qwen2.5-7B Instruct Q4_K_M (`2bada8a7…`). Blobs presentes em armazenamentos independentes. Não foi recalculado hash de todos os pesos nesta rodada.
- Identidade, memória, histórico, relações e estados seguem em pastas/bancos por entidade. O código mental é compartilhado; os dados não. `mind/personality.py:registrar_evidencia` ajusta traços com evidências persistidas. Isso não retreina os pesos durante a conversa.
- Não são modelos vazios: há conhecimento/condicionamentos do pré-treinamento e instruções de identidade predefinidas. A história pessoal cresce nas estruturas externas, com recuperação sujeita a erros.
- Alistair: Qwen3-4B Instruct 2507 Q4_K_M presente, personalidade própria de organizador/standby. Quatro ferramentas declaradas: consultar Central, consultar histórico próprio entre entidades, enviar mensagem, solicitar despertar. CPU fallback e GPU oportunista mantidos. Memória durável `alistair_turns`: últimos quatro turnos, primeiros contatos e busca textual limitada. Não equivale a memória perfeita nem à mente Hoshino/Lilith.

## Memória Hoshino — não apagada

Leitura somente de contagens: 4 memórias, 8 episódios, 4 reflexões; zero nas demais categorias de manutenção consultadas. Lilith sem registros nessas categorias; Alistair sem turnos.

Não foi contornada a senha de exclusão existente. Usuário recebeu pergunta sobre limpar pelo botão protegido ou também retirar histórico de testes do uso ativo. O contrato atual preserva conversas brutas/caixa postal, relações e traços; apagar só memórias não garante que texto antigo nunca volte ao contexto. Nenhum banco foi migrado, editado ou apagado nesta rodada. Backup recuperável é feito pelo procedimento protegido quando a exclusão for efetivada.

## Controle do PC — auditoria, não aprovação física

Sessão X11, `xdotool`, `wmctrl` e `pactl` presentes. Adaptadores existentes cobrem abrir apps/URLs/pastas, foco, mouse/teclado, rolagem, ferramentas de terminal e observação. Isso não significa controle irrestrito ou que qualquer app funcione.

Defeito reproduzido somente com subprocesso mockado em `tools/desktop.py:acao`, backend xdotool: `rolar(0)` emite 2 cliques; `rolar(1)` também 2; `rolar(3)` emite 3. A implementação faz um clique inicial mais `max(1,abs(q)-1)`. Registrado para correção; não alterado porque este subpedido era verificar a capacidade.

Outra limitação de contrato: enumerar janelas após `acao_desktop` não verifica semanticamente se um clique digitou no campo certo. Os aliases de teclas também merecem auditoria por backend (nomes X11 não são necessariamente nomes PyAutoGUI).

Nenhum mouse/teclado real foi acionado. Não declarar controle do desktop aprovado apenas por bibliotecas presentes ou mocks verdes.

## Testes e evidências

- Suíte completa: **74/74 grupos offline** nas execuções de validação, incluindo a rodada final com Serviços/Diagnóstico.
- Áudio: **41/41**, com quatro regressões novas (sem HIP não pede GPU; lease P0 e fechamento antes de liberação; falha sem replay; fallback CPU preserva worker).
- Controle Central: **37/37**, nova regressão de estilos isolados, validação e preservação de configurações.
- Refinamento: **34/34**, incluindo **36/36 contratos Qt**, quatro novos casos (métricas desconhecidas/zero/histórico limitado; filtros e texto literal; imagens locais, transparência e tingimento; serviços sem expor segredo ou afirmar conexão).
- Screenshots de Recursos/Atividade/Configurações gerados com transporte simulado e dados explicitamente fictícios; inspeção visual corrigiu contraste de linhas alternadas e organizou eventos/comandos em guias.
- Serviços/Diagnóstico também verificados em screenshots isolados. Total de nove novos testes, além das verificações estendidas; não validam síntese HIP real, compositor ou controle físico do PC.
- Nenhuma quota externa, modelo novo, concorrência GPU habilitada ou memória real alterada.

## Arquivos desta rodada

Novo: `app/ui/native_panels.py`.

Alterados: `app/ui/central_native.py`, `app/ui/native_style.py`, `app/ui/overlay.py`, `app/core/central_control.py`, `app/core/audio_service.py`, `app/core/tts_router.py`, `app/tools/voice.py`, `app/tools/voice_worker.py`, `testes/native_central_contracts.py`, `testes/test_central_control.py`, `testes/test_central_refinamento.py`, `testes/test_audio_service.py`.

As mudanças anteriores da árvore de trabalho foram preservadas. Nenhum commit/push ou reinício de serviços reais foi feito. Requer reabertura da interface/overlay e reinício cooperativo da Central para carregar o novo contrato de configurações. Dados técnicos brutos foram mantidos apenas nos detalhes, sem perder IDs ou evidências.
