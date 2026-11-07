# Central operacional — mapa e limites da rodada

Baseline: 70/70 grupos offline (07/10/2026). Backup de fontes em
`arquivo/central_20261007/fontes_antes.tar.gz`; não contém bancos nem pesos.

## Fluxo preservado

`central.html` → HTTP loopback autenticado de `iniciar_entidades.py` →
Supervisor / interentity / AudioService / job_bus / Resource Manager.
Presença, recibos e desfechos continuam no backend. A aba pode fechar sem
encerrar entidades. GET não inicia modelos, captura ou síntese.

Eventos: diagnostics JSONL e history SQLite existentes; jobs e leases nos
inventários existentes. Memória: leitura SQLite `mode=ro`, sem chamar recall
nem inicializar/migrar tabelas. Alistair expõe seu histórico, não uma mente nova.

Configuração: env por entidade, executores.json, audio.json; alterações apenas
por allowlist validada, backup, escrita atômica e conflito de revisão. Modelo e
contexto exigem entidade dormindo/offline e ausência de trabalho/lease ativo.
Comentários/env e campos JSON desconhecidos são preservados. Não há editor
arbitrário de arquivos ou comandos. Configuração de cloud/RM permanece leitura.

## Implementação incremental

A/B: manter contratos e IDs do chat/áudio, separar CSS e navegação incremental.
C/D: adaptador `core/central_control.py` no servidor existente; consultas
limitadas e redigidas, sem banco/coletor novo. Configuração segue consumidores
atuais. Áudio de teste requer clique explícito, nunca polling ou CI.
E: inventário dos manifestos locais; exportação autenticada em cópia verificada
na saída existente, sem armazenar gigabytes no navegador;
importação em staging sem adotar checkpoint desconhecido como compatível.
F–H: processo opcional Qt5 já instalado, desenhando orbes leves sem WebEngine.
HTTP autenticado apenas para APIs da central; falha/fechamento não envia
shutdown. Assets mínimos próprios por entidade, sem geração em massa.

## Lacunas e restrições explícitas

Sem push HTTP existente: polling de estado 2s, painéis sob demanda 5s, áudio 15s;
pausar consultas não essenciais com aba escondida. Nada de polling por frame.
O backend expõe frases estáveis de voz, não tokens textuais de resposta: mostrar
somente progresso/frases estáveis, jamais pensamento privado.
Comandos atuais combinam stderr/stdout em um log: exibir como saída combinada,
não inventar separação nem exit code. Modelos de compatibilidade desconhecida
são somente arquivos, nunca opção de executor. Hash de manifesto não equivale
à verificação integral de pesos: rotular separadamente.
Sem prova de saúde/emoção/dispositivo real, mostrar desconhecido/indisponível.
Azure e ElevenLabs reais, microfone, alto-falantes, desktop overlay e Minecraft
continuam exigindo ensaio local explícito. RunPod/cloud não são implementados.
