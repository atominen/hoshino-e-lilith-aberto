# Refinamento nativo — contrato antes da implementação

Baseline 72/72 offline. Existe uma central em uso: não será encerrada nem
terá seus bancos reais manipulados durante o desenvolvimento.

Janela QtWidgets (já instalada) → mesmo HTTP loopback autenticado →
Supervisor/AudioService/Resource Manager/job_bus/diagnostics existentes.
HTML permanece alternativa explícita, não fonte de estado. O padrão do
iniciador passa a janela nativa; fechar janela não encerra entidades.
Captura/reprodução nativas usam parec/paplay já instalados, processos próprios
da janela, sem QtWebEngine ou novo backend ASR/TTS. Microfone nunca abre
automaticamente ao iniciar. Modos: manual, aberto segmentado e detecção por
energia, mais botão de segurar. ASR existente continua preenchendo rascunho.

Teste de voz é explicitamente distinto de resposta da entidade; não exige
acordar LLM. Texto e executor TTS escolhidos antes da síntese. Sem modificar
checkpoint de conversa. Provider real/fallback são mostrados. CI não usa quota.

Configuração visual/política: JSON existentes, revisão, backup, allowlist.
Desativação atua no registro/despacho atual, não um dispatcher paralelo.
Não cancela uma ferramenta mutável já iniciada.

Exclusão: senha scrypt, nunca senha em claro no arquivo/log; limite de tentativas.
Somente entidade dormindo/offline, sem jobs/leases, com lock de lifecycle.
Prévia de IDs/contagens; confirmação explícita; backup SQLite consistente e
índice vetorial antes do efeito. Memórias, episódios, reflexões, procedimentos,
resumos de contexto e histórico mental do Alistair; não identidade, traços,
relações, modelos, configurações, recibos ou caixa postal compartilhada.
Histórico bruto continua disponível: isto não promete apagar todo registro do
que foi dito. Falha entre índices e SQLite é diagnosticada, não sucesso falso.
Nenhum banco novo. Testes usam somente fixtures temporárias.
