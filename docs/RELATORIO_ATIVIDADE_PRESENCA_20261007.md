# Rodada incremental — atividade, presença e distribuição privada

## O que foi implementado

- Projeção operacional compacta no JSON de estado **existente** por entidade;
  nenhuma mente, agenda, fila, autoridade de objetivos, scheduler ou banco novo.
- Atividade, quatro modos práticos, objetivo/subobjetivo, autoria, affordances,
  origem/IDs e saliência entram no ciclo de inferência existente. Mudança de
  atividade não troca identidade nem reinicia humor/memória.
- Minecraft primeiro: observação RPC validada, sessão, validade de 8 segundos,
  desconhecido explícito, perigo inferido de HP/hostis observados. Dados de
  chat não viram percepção/autorização. Antes da ação, revalida dentro da trava.
- Coleta/construção não passam por risco observado sem proteção/reavaliação;
  copiloto/estrategista não assumem o controle. Uma mutação Minecraft por lote
  permite reobservar no próximo passo, em vez de executar sequência cega.
- Tentativas operacionais limitadas a 32, separadas de memórias pessoais e sem
  argumentos/outputs. Falha repetida pede outra abordagem; efeito mutável
  incerto permanece bloqueado entre turnos/restart mesmo se a janela de histórico
  girar. Overflow de incertezas é conservador, não apaga a incerteza.
- Retomada de objetivos usa o objetivo canônico e executor conservador. O sucesso
  de uma **tentativa** agora exige recibos verificados do frame existente,
  não `bool(ferramentas_usadas)` ou frase otimista. Isso não declara conclusão
  de uma meta aberta. Pode registrar falso negativo onde falta verificação.
- Estilo Hoshino/Lilith/Alistair: primeira pessoa, normalmente 1–3 frases;
  explicação longa quando necessária. Vínculo moderado, com experiências
  atribuídas, sem isolamento, exclusividade, cobrança de presença ou memória
  inventada. Alistair admite limites de qualidade do 4B sem acordar/enviar
  alguém automaticamente. Não é uma validação empírica de naturalidade.
- Catálogo afetivo existente ganha medo/desejo/amor com decay. Risco Minecraft
  confirmado alimenta a apreciação existente uma vez por transição; amizade
  mantém gatilho anterior e acrescenta amor pequeno/lento. Desejo tem gatilho
  disponível no catálogo, sem um novo motivador automático. Alistair não ganha
  o pipeline mental das duas entidades.
- Central/orbes leem atividade/emoção reais via APIs existentes. Não inventam
  emoção indisponível nem modulam voz. Dados emocionais malformados não quebram
  o painel. Nenhum pacote grande de figurinha foi gerado nesta rodada.
- Desktop preserva as ferramentas de URL/app/mouse/teclado. Pedido de abertura
  agora diz **enviado, não verificado**, em vez de afirmar abertura por retornar
  zero. Não houve controle real do desktop/Spotify ou mudança de ventoinha.
- Instalador simples por terminal, planejamento padrão, pacote CPU 4B existente,
  hash/staging/extração segura, margem de disco e recusa atômica de sobrescrita.
- Exportação por allowlist para repositório privado: só fontes/licenças/docs e
  templates novos. Não sobe mentes evoluídas, bancos, históricos, logs, chaves,
  ambientes ou pesos. Código versionado não é sincronização de mentes.
  Templates de identidade são `.json.example`; arquivos reais de identidade
  são ignorados para não virar dados mentais rastreados pelo Git depois.

## Arquivos

Criados:

- `app/core/activity_context.py`
- `instalar.py`
- `scripts/exportar_codigo_privado.py`
- `testes/test_activity_context.py`
- `docs/ARQUITETURA_ATIVIDADE_20261007.md`
- `docs/INSTALACAO_PRIVADA_PC2.md`
- este relatório.

Modificados:

- `app/main.py`: projeção, pré-condições sob trava, replay incerto, lote curto,
  retomada de objetivo e evidência da tentativa.
- `app/core/cognition.py`: campos de projeção no frame e verificação conservadora.
- `app/core/prompting.py`: brevidade, primeira pessoa, continuidade/vínculo.
- `app/core/resource_manager.py`: pedido operacional reconhecido não vira tarefa
  leve só por ser curto. Não houve recalibração, alteração de prioridades ou
  habilitação de concorrência GPU.
- `app/alistair_runner.py`: foco, autoria e limite do executor no prompt.
- `app/tools/minecraft.py`: snapshot só após recibo correlacionado validado.
- `app/tools/desktop.py`: aceitação de abertura não significa verificação.
- `app/mind/emotions.py` e `app/mind/affect.py`: catálogo/apreciação/projeção visual.
- `app/core/central_control.py`, `app/ui/central_native.py`, `app/ui/overlay.py`:
  observação read-only por entidade, sem nova verdade no frontend.
- `testes/catalogo.py`: novo grupo de regressão offline.
- `testes/test_prontidao_r1_r7.py`: fixture Minecraft completa com sessionId e
  distinção entre consulta preventiva read-only e chamada explícita do modelo.
  Continua exigindo autoria, IDs, recibos, memória, TTS e reprodução correlacionados.

## Validação

Baseline antes da rodada: **73/73 grupos offline**, exit 0.

Primeira suíte após integração: **73/74**, exit 1. Falha no teste R7 que esperava
um único RPC e omitia sessionId do estado; a consulta preventiva é comportamento
novo intencional, não duplicação de mutação. Corrigida a fixture, mantida a
verificação exata de duas leituras distintas e da chamada com parent/tool ID.
Uma versão intermediária do teste de emoção também revelou chave de gatilho
duplicada; o gatilho anterior foi preservado e recebeu só o incremento pequeno.

Nova regressão: **40/40 testes**, exit 0. Cobre TTL/futuro/sessão, autoria,
isolamento, orçamento de contexto, dados enormes/malformados, mudança de assunto,
modos, prioridade de risco, espera de lock, STOP, tentativas incertas após restart,
falsa conclusão, causa/decay/emissões afetivas, exportação sem dados/segredos,
arquivo perigoso, hash, espaço, staging, corrida de destino e ausência de início
de serviços. Todos com fixtures; sem banco mental real ou provider real.

R1–R7 específico: **19/19**, exit 0. Suíte completa após correções: **74/74
grupos offline**, exit 0; uma repetição final confere a versão entregue.
Os grupos incluem causalidade/mensagens simultâneas, GPU, CPU/fallback Alistair,
UI nativa, áudio/providers, ferramentas e Minecraft/bridge simulados.

Benchmark controlado, sem LLM real: 100 construções/persistências da projeção,
mediana **2,135 ms**, p95 **3,230 ms**, bloco **1.089 caracteres**, estado
**2.818 bytes**. O bloco medido não inclui a orientação fixa (~700 caracteres).
É custo de overhead de fixture, **não** evidência de inferência mais rápida,
naturalidade, GPU concorrente ou otimização antes/depois do LLM.

Pacote real: checksum SHA-256 aprovado; planejamento leu a estrutura inteira,
extração prevista **2.565.213.838 bytes**, exigência **6.860.181.134 bytes livres**
na partição de destino, mantendo 4 GiB. Nenhuma extração/serviço real no PC2.

## Preservações

Nenhum modelo apagado/baixado/trocado, banco mental migrado, personalidade
evoluída sobrescrita ou serviço real reiniciado. Sem quota ElevenLabs/Azure,
cloud, RunPod ou concorrência GPU. RX 6650 XT 8 GiB e RM/fallbacks existentes
preservados. A chave continua só no ambiente; nenhuma chave entra no Git.

## Limites e próxima rodada prioritária

1. Validar com o usuário a versão nova **após encerramento/reinício cooperativo**:
   conversa, retomada de objetivo e Minecraft real. Processos já iniciados não
   recarregam este código automaticamente; não os reiniciei à força.
2. Não confundir este incremento com implementação total do rascunho extenso:
   intenção ampla/atividades não-Minecraft, heurísticas de oportunidade, escolha
   de submeta aberta e continuidade prolongada ainda dependem do controlador e
   LLM existentes; não foi criado um planejador/autônomo novo.
3. Incertezas mutáveis não têm nova UI de resolução nesta rodada. Revisão externa
   do efeito/recibo é necessária; bloqueio conservador não é sucesso. Múltiplos
   efeitos diferentes chegando ao limite fecham o gate, em vez de autoreplay.
4. Observação/verificação não é simulação perfeita: Minecraft segue sujeito a
   mundo mudando após medir, timeout, entidades/versões e backend. STOP continua
   cooperativo. Snapshot não prova segurança futura.
5. Mouse/teclado dependem de desktop/foco reais (X11/Wayland); Spotify usa
   mecanismos de app/URL existentes, sem integração OAuth nova. Presets de
   ventoinha não foram alterados/automatizados sem validação específica.
6. Desejo/vínculo novos precisam avaliação longitudinal de calibração. Estilo
   curto/primeira pessoa é contexto, não corte artificial de respostas, e não
   garante igualdade de naturalidade entre 7B/9B antes de medir conversas reais.
7. Assets finais/seleção rica de figurinha/GIF e modulação emocional de voz
   permanecem posteriores; aqui há apenas projeção visual do estado existente.
8. PC2: pacote fora do Git exige transferência; ainda medir Athlon/HDD, boot,
   RAM, latência, desconexão e uso longo. Instalação principal nova não é turnkey:
   precisa modelos/serviços/configs existentes importados e testados.
9. GitHub contém snapshot inicial do código: não é ainda sincronização automática
   da instalação em execução. Revisar diff e fazer backup antes de atualizar.
10. Ensaios físicos de ElevenLabs, Minecraft, microfone/reprodução/overlay desktop
    e soak/leaks continuam humanos. Mocks não aprovam esses ensaios.

## Gate

**SIM, MAS...** para um teste manual incremental: primeiro encerrar/reabrir
cooperativamente os serviços que devem receber o código, começar com conversa/
apresentações e testar atividade Minecraft com observação das falhas. O offline
não mostrou bloqueador determinístico remanescente nesta rodada. Não há aprovação
de uso prolongado, acesso total irrestrito ao PC, modelo mais competente ou PC2
físico sem os respectivos testes. Não declarar todo o rascunho concluído.
