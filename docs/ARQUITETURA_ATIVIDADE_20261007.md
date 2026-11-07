# Contexto de atividade e presença — integração incremental

Baseline anterior à alteração: 73/73 grupos offline. Nenhum serviço real é
reiniciado por esta rodada. Cloud e concorrência GPU permanecem desativadas.

## Mapa dos consumidores

Entrada/FIFO/autoria → `main.InterfaceHoshino.responder` →
`core.prompting` + memória existente → `core.cognition.CognitiveFrame` +
`core.task_state` → `Resource Manager.choose_executor` → Ollama →
`dispatch.executar_resultado` → contratos/recibos/verificação → publicação e
TTS → histórico/pós-turno existentes.

Autonomia: heartbeat/kernel/impulsos e goals existentes. **Não há outro loop,
scheduler, dono de objetivos, banco ou escriba.** Alistair conserva seu runner,
histórico e ferramentas menores, inclusive fallback CPU/PC2.

Minecraft: bridge Node por entidade → RPC correlacionado → snapshot observado
privado da entidade → projeção compacta do ciclo. Desktop continua usando suas
ferramentas existentes e as mesmas confirmações, travas e recibos.

UI nativa/overlay → `central_control` → arquivos/diagnostics/job bus existentes.
A projeção da atividade não é uma segunda fonte de verdade: objetivos vêm de
task_state/goals; resultados vêm de recibos; emoções vêm de estado_mente.

## Contrato mínimo

`core.activity_context` monta e limita uma projeção operacional no JSON de
estado já existente. Campos: entidade, conversa, atividade, modo prático,
objetivo/subobjetivo referenciado, participantes atribuídos, affordances atuais,
observações com sessão/tempo/origem/confiança, saliência/reason codes, última
ação/resultado e assinaturas curtas de tentativas. Sem cadeia de pensamento.

Quatro modos: agente integrado, copiloto, estrategista, executor de ferramenta.
Mudar modo não muda identidade, prompt canônico, memória ou emoções.
Snapshot expirado é explicitamente desconhecido; recibo não prova estado futuro.
Projeções antigas após restart não retomam ações por si mesmas.

Histórico de tentativas é operacional, limitado e sem argumentos secretos.
Resultado mutável incerto exige revisão, não retry automático; falha repetida
exige nova abordagem. STOP/correção continuam no contrato FIFO/revisões atual.
Silêncio/wait são válidos; oportunidade não substitui o objetivo.

## Etapas e limites

1. Projeção compacta + Minecraft/controle cognitivo; testes adversariais.
2. Contexto de conversa, executor conservador e Alistair com limites explícitos.
3. Emoções e vínculo no mecanismo existente, com causa/decay, sem coerção.
4. UI/overlay lendo projeção/emoção real e somente assets disponíveis.
5. Instalador e exportação por allowlist para GitHub privado. Nenhuma memória,
   credencial, runtime ou peso vai para Git. PC2 executa, não é dono da entidade.

Downloads/instalação requerem execução explícita do instalador. Sem chamadas
pagas, nova aquisição de modelos, alteração de curvas de ventoinha às cegas,
ou sessão humana/Minecraft automática. Integridade, espaço, staging e
compatibilidade são verificados antes de aplicar. O primeiro teste real continua
necessário; testes simulados não provam naturalidade nem hardware.
