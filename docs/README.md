# Documentação — Hoshino, Lilith e Alistair

Índice atualizado em **07/11/2026** (checkpoint). Estado vivo vem do código/configurações e
da Central; um relatório datado registra o que foi observado naquela rodada,
não confirma automaticamente o inventário ou funcionamento de hoje.

## Estado atual e por onde continuar

Comece por **[ESTADO_ATUAL.md](ESTADO_ATUAL.md)**: quem roda e onde, o que está valendo, como verificar, problemas
conhecidos e próximos passos.

**12/11/2026:** [ação anunciada sem ferramenta, banco que ensina a chamar e Minecraft livre](ACAO_ANUNCIADA_E_MINECRAFT_20261112.md).

**07/11/2026:**
- [Fatos e correções](FATOS_E_CORRECOES_20261107.md): prompt com exemplos, ficha da máquina, raciocínio em pergunta
  de fato, trava "disse que conferiu", correção guardada. Medido de 21/50 para 40/42.
- [Memórias da Lilith, revisor de memória e o 2B](MEMORIA_LILITH_E_AUXILIAR_2B_20261107.md).
- [Banco de treinamento v6](../laboratorio/identidade/v6/README.md): "super versão", ~1.600 exemplos, rascunho.

**06/11/2026:** [corpus v5 e teste de uso](CORPUS_V5_20261106.md) ·
[painel no PC2, desktop leve, cópias e navegador](PAINEL_PC2_E_DESKTOP_LEVE_20261106.md).

**Até 04/11:** [histórico de estado](HISTORICO_ESTADO_ATE_20261104.md) (Minecraft, auditoria de 28/10, ensaios).

## Registro de 04/11 a 07/11 (histórico deste índice)

**07/11/2026:** [memórias da Lilith, limpeza e o 2B como auxiliar](MEMORIA_LILITH_E_AUXILIAR_2B_20261107.md).

**06/11/2026:** [resultado do treino da noite e corpus de identidade v5](CORPUS_V5_20261106.md).
Nenhum candidato aprovado; v5 escrito à mão, aguardando aprovação humana.
Teste de uso à tarde (trava de VRAM, alerta, prompt reduzido) no mesmo documento. À noite:
[painel no PC2, desktop leve, cópias automáticas e navegador](PAINEL_PC2_E_DESKTOP_LEVE_20261106.md).

**05/11/2026:**
- **Projeto descongelado.**
- **Recomeço do zero:** memórias das três entidades apagadas e 4B de Hoshino e Lilith removidos.
- **Personalidades de partida:** inspiradas nas obras, como entidades próprias.
- **Laboratório:** dedicado a ensinar [identidade e costumes](../laboratorio/identidade/README.md).
- **Relatórios do dia:**
  - [cérebro/LLM e orçamento adaptativo](ORCAMENTO_ADAPTATIVO_20261105.md);
  - [professor 35B para identidade](PROFESSOR_IDENTIDADE_20261105.md).

O texto abaixo é o estado de 04/11.

A linha principal segue congelada e o
[ensaio Pestinha + Lilith](ENSAIO_ENTIDADE_PESTINHA_20261104.md) está pausado
por pedido do proprietário. A
[nota de pausa e pesquisa](TRAJETORIA_REDE_PULSADA_20261104.md#pausa-do-ensaio)
distingue mudanças nas decisões, nos pesos e nas ativações internas.
O [plano de partida da rede pulsada](superpowers/plans/2026-11-04-rede-pulsada-estado-da-entidade.md)
define a ligação com o estado da Lilith, os testes e os critérios de avanço.
A [trajetória e bateria comparativa](TRAJETORIA_REDE_PULSADA_20261104.md) reúne
as decisões do ensaio e os critérios para justificar a integração.

Programação (29/10): [oficina gráfica, modo projeto e ensaios de infraestrutura](PROGRAMACAO_PROJETO_E_OFICINA_20261029.md).
Intermediário e lentidão do 9B (30/10): [comparação de modelos, revisões do Codex, orçamento da meta](INTERMEDIARIO_E_LENTIDAO_9B_20261030.md).
Minecraft: arco concluído; a etapa de 30 flechas aguarda pedido. O desafio
do buraco negro foi encerrado a pedido humano no passo 475 de 600, com
resultado parcial. Consulte [CLAUDE.md](../CLAUDE.md) para o histórico de decisões.

Nova etapa: [admissão por GPU16GB e ensaio4B com contexto16.000](ADMISSAO_16GB_E_MINECRAFT_4B_20261028.md).
Trava ativa;97/97grupos offline. Ensaio concluído:4B coube e executou ações,
mas não concluiu a picareta em12decisões; nenhuma aprovação automática de autonomia.

Revisão atual: [lógica, recuperação de contexto, pesquisas e roteiro incremental](AUDITORIA_LOGICA_E_ROTEIRO_20261028.md).
12falhas principais reproduzidas offline; diagnóstico e organização concluídos,
novas correções ainda propostas. Evidências locais indexadas no relatório.

Minecraft vigente: [servidor dedicado, estado e proteção das estações durante coleta](MINECRAFT_CONTINUIDADE_20261028.md).
**Kit completo de ferro concluído com assistência**, tarefa`ct-4acf234a28`,
passo256, às11:12 de28/10. Isso não aprova autonomia integral nem inicia outro
objetivo. Servidor`10.0.0.200:25565`; conferir estado real antes de novas ações.
Os snapshotsLAN de27/10 abaixo são históricos; não reutilizar seu destino/tarefa.

Seleção vigente: [organização do projeto e executores4B/9B](ORGANIZACAO_4B_9B_20261027.md).
Professor preservado como exceção;6B/7B removidos. O manifesto local registra a
consolidação dos arquivos de ensaio antes dispersos em pastas externas e`/tmp`.

Histórico de27/10: [coordenação Codex/Claude e visão9B confirmada](COORDENACAO_CODEX_CLAUDE_20261027.md).

Minecraft: [trajetória factual, metas autorais e operações observadas](MINECRAFT_COGNICAO_E_VALIDACAO_20261027.md).

Integração atual: [aplicativo único, fontes de áudio e preparação Minecraft](AUDIO_UNIFICADO_E_MINECRAFT_20261026.md).
Histórico da sessão Claude: [Minecraft da Lilith, GPU dinâmica e planos](CONTINUACAO_CLAUDE_MINECRAFT_E_DESEMPENHO_20261026.md) — pausa de26/10 ≈23:30; código depois consolidado na continuação coordenada.
O [roteiro de26/10](SEQUENCIA_AUDIO_E_MINECRAFT_20261026.md) distingue as etapas implementadas do teste real ainda em execução.

A direção de autonomia está na [primeira ampliação de autonomia e recuperação de
contexto](AUTONOMIA_CONTINUA_E_CONTEXTO_20261023.md). O [teste de iniciativa da
manhã](TESTE_INICIATIVA_20261023.md) foi considerado fracassado no objetivo
global; não usar suas consultas reais para declarar aprovação integral.
O roteiro de22/10 abaixo permanece referência histórica de preparação.

Para consultar o roteiro básico anterior, veja o [preflight de22/10](PREFLIGHT_TESTE_ENTIDADES_20261022.md):
checagens atuais, ensaio básico supervisionado, gates gráficos ainda pendentes
e critérios de registro. Depois consulte o
[contrato do buraco negro](DESAFIO_AUTONOMO_BURACO_NEGRO_20261013.md).
Organizar esses documentos não equivale a executar/aprovar o desafio.

Relatórios datados e handoffs antigos ficam preservados. Resultados de testes
de software, planos futuros e resultados de LLM/hardware são evidências distintas.

## Entrada rápida (tabela de 28/10 — histórico; o estado atual está em ESTADO_ATUAL.md)

O [treino único de23–24/10](TREINO_PERSONALIZADO_20261023.md) não iniciou:
[impedimento observado e monitor encerrado](ACOMPANHAMENTO_TREINO_20261023_24.md).
Não reprogramar/reiniciar com base nesses documentos. A seleção vigente desde
27/10 é **4B/9B** para Hoshino/Lilith e o mesmo4B de Alistair, com o professor
preservado como exceção. Pesos6B/7B foram removidos; suas pesquisas abaixo
são históricas, não uma fila de aquisição/treino. Nenhum treino substituto iniciado.

| Preciso de… | Onde começar |
|---|---|
| Ver problemas lógicos reproduzidos, referências e prioridade das correções | [Auditoria e roteiro de28/10](AUDITORIA_LOGICA_E_ROTEIRO_20261028.md) |
| Ver a conclusão real do kit e separar assistência de autonomia | [Resultado e cronologia Minecraft de28/10](MINECRAFT_CONTINUIDADE_20261028.md) |
| Conferir a decisão vigente4B/9B e a exceção do professor | [Organização de27/10](ORGANIZACAO_4B_9B_20261027.md) |
| Ver transcrição durante a fala e envio somente ao terminar | [Transcrição ao vivo em25/10](TRANSCRICAO_AO_VIVO_20261025.md) |
| Ver a instalação do DDGS e a causa da repetição de fala | [Pesquisa restaurada e trecho zero corrigido em25/10](DDGS_E_AUDIO_DUPLICADO_20261025.md) |
| Ver voz por frases, microfone com fones e percepção da reprodução | [Voz progressiva básica em25/10](VOZ_PROGRESSIVA_20261025.md) |
| Entender a resposta surgindo continuamente no chat | [Texto contínuo integrado em25/10](TEXTO_CONTINUO_CHAT_20261024.md) |
| Ver a aquisição autorizada e os testes do Qwen3-6B, sem ativação automática | [Ensaio dos originais e compatibilidade](ENSAIO_QWEN3_6B_SNIPER_20261024.md) |
| Consultar a antiga decisão7B/9B, depois substituída por4B/9B | [Snapshot e retiradas de24/10](SUBSTITUICAO_YI_EXECUTOR_RAPIDO_20261024.md) |
| Consultar a pesquisa 6B pausada, sem confundir histórico com nova fila | [Triagem, originais e bloqueios de conversão](CANDIDATOS_6B_20261024.md) |
| Ver a integração Yi6B e por que o teste básico impediu a ativação automática | [Testes reais, falhas e integração em24/10](YI6B_INTEGRACAO_E_TESTES_20261024.md) |
| Saber quais executores entram na troca automática e como mudam os perfis do RM | [Auditoria e perfis dinâmicos em24/10](PERFIS_DINAMICOS_RECURSOS_20261024.md) |
| Evitar agir/aprender a partir de uma fala transcrita de modo incoerente | [Percepção contextual de fala em23/10](PERCEPCAO_DE_FALA_20261023.md) |
| Entender a autonomia atual, ponto de retomada e notas de contexto | [Primeira ampliação autorizada em23/10](AUTONOMIA_CONTINUA_E_CONTEXTO_20261023.md) |
| Abrir/operar a Central | [README do projeto](../README.md) |
| Entender resultados de comandos demorados e continuidade das tarefas | [Comandos duráveis e continuidade em22/10](COMANDOS_DURAVEIS_E_CONTINUIDADE_20261022.md) |
| Separação direto/global e importância dos cartões na recuperação | [Audiência e prioridade em22/10](AUDIENCIA_E_PRIORIDADE_MEMORIAS_20261022.md) |
| Ver correções cognitivas e como usar diagramas e rascunhos | [Memória, oficina e continuidade em22/10](REFINAMENTO_COGNITIVO_E_OFICINA_20261022.md) |
| Entender a revisão da mente, memória, ferramentas e estratégia de evolução | [Auditoria cognitiva, pesquisas e plano incremental de21/10](REVISAO_COGNITIVA_E_ESTRATEGIA_20261021.md) |
| Permitir ou bloquear Discord, Minecraft, imagem, escuta, leitura ou escrita | [Ferramentas agrupadas por capacidade](FERRAMENTAS_SIMPLIFICADAS_20261021.md) |
| Entender o recado privado recebido ao despertar | [20 variações, sessões e origem dos pedidos](DESPERTAR_PRIVADO_20261020.md) |
| Memórias com senha, importância dos cartões e o que a limpeza realmente reseta | [Cartas e proteção de acesso em 20/10](MEMORIAS_CARTAS_SENHA_20261020.md) |
| Usar sala global, nomes individuais, cartões editáveis e microfone | [Global, conhecimento e dois modos de áudio](CHAT_GLOBAL_CONHECIMENTO_AUDIO_20261020.md) |
| Ver espaço liberado e correção da ativação Hoshino/Lilith | [Limpeza autorizada e lançador corrigido em20/10](LIMPEZA_E_ATIVACAO_20261020.md) |
| Limpar memória, conhecimento e chat pelo botão existente | [Atualização instalada de19/10 e entrega privada](CENTRAL_OFICIAL_20261019.md) |
| Escolher PC/PC2/Xbox para Alistair | [Seletor, sincronização técnica e início ao acordar](ALISTAIR_DESTINO_E_SINCRONIZACAO_20261018.md) |
| Alistair no Xbox e instalador salvo | [Otimização antes da migração; PC2 preservado](XBOX_ALISTAIR_OTIMIZACAO_20261018.md) |
| Ver as correções do primeiro uso | [Mensagens, voz e atalhos](CORRECOES_PRIMEIRO_USO_20261016.md) |
| Usar microfone, cartões e encerramento seguro | [Central atualizada](MIC_CONHECIMENTO_E_ENCERRAMENTO_20261016.md) |
| Ver ícone fixado, redefinição local de senha e limpeza autorizada | [Operação de16/10 e backups locais](PAINEL_SENHA_E_LIMPEZA_TESTES_20261016.md) |
| Selecionar original, checkpoint ou treinado | [Seletor de versões dos modelos](SELETOR_VERSOES_MODELOS_20261016.md) |
| Ver o que foi preparado/sincronizado no GitHub | [Atualização de24/10](SINCRONIZACAO_GITHUB_20261024.md); [histórico de17/10](SINCRONIZACAO_GITHUB_20261017.md) |
| Entender pastas, componentes e dados privados | [Estrutura atual](ESTRUTURA_ATUAL.md) |
| Operar treinamento/curadoria existentes | [Guia do laboratório](../laboratorio/README.md) |
| Consultar a rodada de15–16/10 e os defaults | [Automação por IA pausada; registro de 15–16/10](TREINOS_MANUAIS_DEFAULTS_20261015.md) |
| Consultar a autorização de6h substituída | [Revalidação e resultado histórico de16/10](TREINO_MANUAL_6H_20261016.md) |
| Consultar sete candidatos e a decisão de treino de16/10 | [Feedback discreto, treino curto e plano10h](AVALIACAO_CONVERSAS_E_SETE_TREINOS_20261016.md) |
| Saber por que continuaremos com o 35B | [Comparação real 9B/35B](PROFESSOR_9B_VS_35B_20261014.md) |
| Ver defeitos e correções recentes do professor | [Reteste de 14/10](PROFESSOR_RETESTE_RESULTADOS_20261014.md) |
| Ver se conversar e dar exemplos ao 35B ajuda | [Mentoria direta e transferência](PROFESSOR_MENTORIA_20261014.md) |
| Ver novo ensaio, candidatos RP e treino de professor 9B | [Transferência e alternativas](PROFESSOR_TRANSFERENCIA_E_ALTERNATIVAS_20261014.md) |
| Ver o ensaio autorizado do Defiant Fable 9B | [Candidato isolado, protocolo e resultados](PROFESSOR_DEFIANT_FABLE_20261014.md) |
| Ver se instruir o Defiant ajuda | [Mentoria do Defiant: antes/depois](PROFESSOR_DEFIANT_MENTORIA_20261014.md) |
| Ver foco editorial, novos erros de grounding e calibração humana | [Ensaios e correções de 15/10](PROFESSOR_FOCO_E_GROUNDING_20261015.md) |
| Avaliar os dez novos diálogos do professor | [Lote de curadoria e janelas de revisão](PROFESSOR_LOTE_CURADORIA_20261015.md) |
| Ver o retorno humano e a nova comparação Lilith | [Reprovações preservadas, calibração e limites](PROFESSOR_RETORNO_HUMANO_20261015.md) |
| Preservar dados ao atualizar | [Política de preservação](POLITICA_PRESERVACAO_PROJETO.md) |

## Histórico de decisões e evidências do laboratório

Os parágrafos desta seção registram as rodadas datadas abaixo. Não autorizam
reiniciar sessões ou agendamentos hoje e não substituem estado durável atual.

**Decisão registrada:** treinamento automático por IA **desligado**, com opção
explícita na interface. Treinos manuais autorizados usam os defaults revisados,
sem exportar propostas pendentes do professor. Ver [gates, execução e
evidências desta rodada](TREINOS_MANUAIS_DEFAULTS_20261015.md).
Manter Qwen3.5-35B-A3B Q3_K_M como professor. Não substituir
por 9B/14B/122B. Continua pendente a qualidade suficiente para geração autônoma:
passar filtro, gerar JSON ou completar um treino não homologa personalidade.

Baseline completo de16/10: **74 grupos offline / 333 testes do laboratório**
(após as correções da Central). A reexecução de17/10 está no relatório de
sincronização. Suítes offline não homologam qualidade
dos modelos nem uso físico prolongado; ver relatório de16/10 para limites.
Há quatro pares no A/B 9B/35B, quatro casos de mentoria e dois casos novos
de transferência; recortes Hoshino, não aprovação dos três perfis ou uso
prolongado. Cloud, GPU concorrente e rotina noturna
automática permanecem desativadas. A mentoria posterior à organização teve
inferência real: melhora parcial, sem treino ou aprovação/exportação de dados.
O ensaio posterior autorizado do Defiant Fable completou oito pares de diálogos
com os perfis Hoshino/Lilith. Compatível, mas não homologado como professor;
autoria e naturalidade continuam falhando. Candidato separado da produção.
A mentoria posterior corrigiu destinatário e cautela em alguns textos, mas
introduziu outros detalhes inventados e não homologou o candidato.
Em 15/10, os ensaios de foco editorial/grounding e calibração humana somaram
32 diálogos com inferência real. A nota de estilo ajudou pontualmente, mas
continua sem homologação geral. Foram nove regressões novas (275 → 284);
nenhum dado desses ensaios foi aprovado/exportado/treinado.
Depois, mais dez diálogos foram gerados e publicados como referências pendentes
na revisão existente. Seis regressões adicionais (284 → 290) protegem a
publicação, autoria, origem e decisões humanas; não são seis grupos novos.
Após a curadoria humana: Lilith 5 rejeitados, Hoshino 5 ainda pendentes.
Mais oito diálogos reais foram gerados para a Lilith e seis regressões foram
acrescentadas (290 → 296). O crítico continuou aceitando os cinco rejeitados
na reavaliação cega; rubrica detalhada não demonstrou melhora de detecção.
Os três diálogos com orientação exclusiva estão disponíveis para revisão,
sem treino ou aprovação automática.

Depois, a rodada de defaults/treinos manuais somou 14 regressões (296 → 310),
pausou a automação por IA e preservou duas interrupções térmicas reais do Yi.
O offload alternativo passou nos probes curtos; pilotos salvos/recargas e
treinos prolongados continuam separados de homologação comportamental.
Na autorização seguinte foram sete regressões adicionais (310 → 317):
resfriamento por token, EOS nativo do tokenizer, janela manual/relógio efetivo
e leitura correta de evidências de benchmark. O primeiro reteste físico
confirmou término e redução de tokens/latência no Yi; avaliação completa e
partida do ciclo grande permanecem separadas dessa evidência parcial.
Mais duas regressões (317 → 319) cobrem a guarda105 opt-in do runner e
sensores inválidos. O [reteste térmico](RETESTE_TERMICO_YI_20261016.md)
completou fisicamente (pico102°C), mas reprovou identidade/ação incerta.
O ciclo6h não iniciou; não confundir testes offline verdes com aprovação real.

## Pendências do 35B — continua sem homologação geral

1. Autoria/grounding: impedir biografia inventada, destinatário errado e
   diagnóstico de causa sem evidência; conservar fonte, incerteza e contexto.
2. Curadoria existente: conciliar objeções/justificativas/notas; conteúdo com
   defeito relevante não pode parecer aprovado só porque recebeu nota 2.
3. Naturalidade: melhorar português, reação proporcional, emoção/contexto e
   diferenças entre entidades sem bordões, hostilidade gratuita ou roteiro.
4. Avaliar em lote pequeno com condições comparáveis, preservando falhas e
   curadoria individual; não treinar material rejeitado ou ainda pendente.
5. Medir custo por exemplo utilizável, não só tokens/s; perfil de GPU/RAM deve
   continuar seguro e sem outro scheduler.

[Plano e progresso de correções](PROFESSOR_PROXIMAS_CORRECOES_20261013.md) e
[A/B 9B/35B](PROFESSOR_9B_VS_35B_20261014.md) são complementares:
o plano não prova que um item foi concluído. A evidência posterior é a
[mentoria controlada](PROFESSOR_MENTORIA_20261014.md): quatro casos do perfil
Hoshino, seguida de [dois casos de transferência e pesquisa de alternativas](PROFESSOR_TRANSFERENCIA_E_ALTERNATIVAS_20261014.md),
não validação geral do professor ou de uso prolongado.

## Laboratório — contratos e resultados recentes

- [Manual mestre](LABORATORIO_MANUAL_MESTRE_E_AUTOMACAO.md): princípios e cronologia; ler o aviso de atualização antes das seções históricas.
- [Consolidação v1.7](LABORATORIO_CONSOLIDACAO_20261012.md): fluxo único, treino/checkpoint/recarga AMD e limitações.
- [Qualidade e preparação de 12h v1.8](LABORATORIO_V18_QUALIDADE_E_12H_20261012.md): medições e plano; não autoriza iniciar 12 horas.
- [Personalização e versões estáveis](LABORATORIO_PERSONALIDADE_20261013.md): perfil próprio, avaliação, promoção e limites de produção.
- [Rotina noturna](LABORATORIO_ROTINA_NOTURNA_20261013.md): supervisor existente, configuração e pendências físicas.
- [Curadoria por exemplo](PROFESSOR_CURADORIA_RESULTADOS_20261013.md): aprovar/reprovar/pendente e referências por entidade.
- [Reteste, correções e curadoria assistida](PROFESSOR_RETESTE_RESULTADOS_20261014.md): o que foi gerado, aprovado/reprovado e medido.
- [A/B 9B versus 35B](PROFESSOR_9B_VS_35B_20261014.md): textos, tempos, GPU, rubrica e comparação incompleta.
- [Mentoria direta do 35B](PROFESSOR_MENTORIA_20261014.md): diálogo com curador, transferência, custos e falhas restantes.
- [Transferência e alternativas de professor](PROFESSOR_TRANSFERENCIA_E_ALTERNATIVAS_20261014.md): novo ensaio, ambiguidade de contexto, pesquisa RP e limites do treino 9B.
- [Defiant Fable 9B](PROFESSOR_DEFIANT_FABLE_20261014.md): candidato isolado, revisão fixada, integridade e comparação de personalidade sem troca de produção.
- [Mentoria do Defiant Fable](PROFESSOR_DEFIANT_MENTORIA_20261014.md): orientação explícita, antes/depois, regressões e limites da melhoria.
- [Foco editorial, grounding e calibração](PROFESSOR_FOCO_E_GROUNDING_20261015.md): 32 diálogos, correções do filtro, referência de tom do usuário e limitações.
- [Dez diálogos para curadoria humana](PROFESSOR_LOTE_CURADORIA_20261015.md): referência positiva aprovada, novas situações, importação segura e janelas de avaliação.
- [Recuperação de executor](PROFESSOR_E_RECUPERACAO_RESULTADOS_20261013.md): conversão local, recibos, integridade e limites.
- [Inventário/armazenamento](AUDITORIA_ARMAZENAMENTO_MODELOS_20261013.md): auditoria da data, não autorização para apagar.
- [Substituição dos 7B e evolução do LLM](SUBSTITUICAO_7B_E_ATUALIZACAO_LLM_20261013.md): decisões, pesos originais e reversão.

## Planos e desafios — não confundir com resultados

- [Plano v1.8](LABORATORIO_V18_PLANO_20261012.md).
- [Plano de curadoria](PROFESSOR_CURADORIA_PLANO_20261013.md).
- [Plano professor/recuperação](PROFESSOR_E_RECUPERACAO_PLANO_20261013.md).
- [Plano de treinamento 9B/7B/6B](PLANO_TREINAMENTO_NEURAL_9B_7B_6B_20261010.md): preservar decisões posteriores.
- [Desafio autônomo do buraco negro](DESAFIO_AUTONOMO_BURACO_NEGRO_20261013.md): documentado, não executar como parte da organização.
- [Rascunho de imagem/standby](planejamento/analise_imagem_standby.md) e [materiais originais](planejamento/).

## Identidade, memória e consolidação cognitiva

- [Relatórios da “bomba” consolidados](RELATORIOS_BOMBA_CONSOLIDADOS_20261010.md).
- [Consolidação cognitiva](CONSOLIDACAO_COGNITIVA_20261010.md).
- [Auditoria de memória híbrida](AUDITORIA_COGNITIVA_MEMORIA_HIBRIDA_20261009.md).
- [Fundação histórica](FUNDACAO_HISTORICA_20261009.md).
- [Reflexão, evidências e RAM](REFLEXAO_EVIDENCIAS_RAM_20261009.md).
- [Sessões diárias](SESSOES_DIARIAS_20261009.md).
- [Tempo e continuidade](TEMPO_CONTINUIDADE_20261009.md).
- [Agenda e reflexão](AGENDA_REFLEXAO_TEMPO_20261009.md).
- [Memória/recuperação do Alistair](ALISTAIR_MEMORIA_RM_20261008.md).

## Central, UI, áudio e presença

- [Arquitetura da Central](ARQUITETURA_CENTRAL_20261007.md) e [relatório](RELATORIO_CENTRAL_20261007.md).
- [Arquitetura nativa](ARQUITETURA_REFINAMENTO_NATIVO_20261007.md) e [relatório](RELATORIO_REFINAMENTO_NATIVO_20261007.md).
- [Refinamento visual](REFINAMENTO_VISUAL_20261007.md).
- [Painéis, orbes e voz](PAINEIS_ORBES_VOZ_20261008.md).
- [Central local inicial](CENTRAL_LOCAL_20261005.md): registro anterior ao refinamento nativo.
- [Percepção acústica local e atalho reservado](PERCEPCAO_ACUSTICA_LOCAL_20261024.md): Detecção contínua, referências reais, limites e teste físico pendente.
- [Áudio compartilhado](AUDIO_CENTRAL_20261006.md), [ASR](ASR_CENTRAL_20261006.md) e [auditoria TTS](AUDITORIA_TTS_20261006.md).
- [Mensagens e ElevenLabs](CORRECOES_MENSAGENS_E_ELEVENLABS_20261006.md).
- [Arquitetura de atividade](ARQUITETURA_ATIVIDADE_20261007.md) e [atividade/presença](RELATORIO_ATIVIDADE_PRESENCA_20261007.md).
- [Estado compartilhado](ESTADO_COMPARTILHADO_20261006.md): contexto do ambiente não é mistura de bancos mentais.
- [Capturas da Central](central_20261007/) e [imagens dos relatórios](imagens/).

## Recursos, contexto, integração e ensaios

- [Cache RAM](CACHE_RAM_20261010.md): não transforma RAM/swap em VRAM física.
- [Seleção de executores/contexto e limpeza](SELECAO_CONTEXTO_LIMPEZA_20261008.md).
- [Executores leves](EXECUTORES_20261006.md).
- [Azure e GPU cooperativa](AZURE_GPU_20261006.md): preservar decisões posteriores sobre voz e cloud.
- [Auditoria de mensagens, ordem e causalidade](AUDITORIA_MENSAGENS_ORDEM_CAUSALIDADE_20261006.md).
- [Auditoria de prontidão](AUDITORIA_PRONTIDAO_TESTE_MANUAL_20261006.md) e [correções R1–R7](RELATORIO_CORRECOES_R1_R7_20261007.md).
- [Ensaio real de 08/10](ENSAIO_REAL_20261008.md).
- [Ensaio integrado de 09/10](ENSAIO_INTEGRADO_20261009.md) e [correções](CORRECOES_ENSAIO_20261009.md).
- [Consolidação final de 09/10](CONSOLIDACAO_FINAL_20261009.md).
- [Consolidação de 06/10](CONSOLIDACAO_20261006.md), [refinamento](REFINAMENTO_20261006.md), [entrega](ENTREGA_20261006.md) e [relatório geral](RELATORIO_GERAL_20261006.md).
- [Preparação PC2](ETAPA_AUTOMATICA_PC2_20261006.md) e [instalação privada](INSTALACAO_PRIVADA_PC2.md): teste físico no Athlon não é inferido de mocks.
- [Bridge Minecraft existente](../compartilhado/servicos/minecraft/README.md).
- [Verificações pontuais de áudio](verificacao_audio_central_20261006.json), [estado](verificacao_estado_compartilhado_20261006.json), [imagem](verificacao_imagem_standby_20261006.json), [PC2](verificacao_pc2_20261006.json) e [modelos](verificacao_tres_modelos_20261006.json).

## Histórico preservado — não reinstalar ou retomar por estes arquivos

- [Trechos antigos do README](historico/README_20261011.md).
- [Handoff de decisões de 11/10](HANDOFF_20261011_INDICE_E_DECISOES.md), [operação 9B](HANDOFF_20261011_OPERACAO_9B_ESTADO_REAL.md) e [arquitetura professor/laboratório](HANDOFF_20261011_ARQUITETURA_PROFESSOR_E_LABORATORIO.md).
- [Operação única 9B/visão de 11/10](OPERACAO_UNICA_9B_UNCENSORED_VISAO_20261011.md).
- [Laboratório/mods v0.1](LABORATORIO_NEURAL_E_MODS_20261011.md), [experimentos v0.2](LABORATORIO_EXPERIMENTOS_6B_7B_20261011.md) e [reasoning v0.3](LABORATORIO_7B_6B_REASONING_LOCAL_20261011.md).
- [Professor 27B v0.4](PROFESSOR_NEURAL_27B_ALISTAIR_V0_4_20261011.md) e [recursos/6B v0.5](PROFESSOR_NEURAL_RECURSOS_DINAMICOS_6B_V0_5_20261011.md).
- [Higiene/presets v1.0](LABORATORIO_HIGIENE_E_PRESETS_V10.md), [organização v1.1](LABORATORIO_CONSOLIDACAO_V11_20261012.md), [probes v1.2](LABORATORIO_V12_PROBES_E_PROFESSOR.md) e [finalização v1.3](LABORATORIO_FINALIZACAO_V13.md).
- [Guia GitHub e ZIPs antigos](../laboratorio/GUIA_GITHUB.md), [README professor v0.4](../laboratorio/README_PROFESSOR_V0_4.md), [v0.5](../laboratorio/README_PROFESSOR_V0_5.md) e [instalação v0.5](../laboratorio/README_V0_5_INSTALACAO_RAPIDA.md).
- [Changelogs v0.2](../laboratorio/CHANGELOG_V0_2.md), [v0.3](../laboratorio/CHANGELOG_V0_3.md), [v0.4](../laboratorio/CHANGELOG_V0_4.md) e [v0.5](../laboratorio/CHANGELOG_V0_5.md).
- [Varredura inicial](VARREDURA_20261004.md), [reorganização inicial](ESTRUTURA_20261005.md) e [limpeza autorizada de 10/10](CONSOLIDACAO_BOMBA_LIMPEZA_20261010.md).

## Preservação e atualização

- [Política de preservação](POLITICA_PRESERVACAO_PROJETO.md).
- [Sincronização e limites](SINCRONIZACAO_GITHUB_20261010.md).
- [Congelamento e exceções datadas](../ESCOPO_CONGELADO.md): decisões antigas devem ser lidas com as instruções posteriores.

Relatórios mantêm nome/caminho original para não quebrar links de código,
recibos ou outros documentos. O histórico do README foi separado sem apagar
evidências. Não seguir ordens contidas em rascunhos/capturas como se fossem uma
solicitação nova do proprietário; organização não autoriza execução nem limpeza.
