# Laboratório Neural — guia operacional

> **Objetivo único desde 05/11/2026 (decisão humana): ensinar nome, identidade,
> personalidade e costumes às entidades por LoRA/QLoRA.** Leia primeiro
> [identidade/README.md](identidade/README.md), que traz escopo, bases, fluxo e
> critérios, e os rascunhos `identidade/tracos_*.json`. O texto abaixo é o guia
> histórico até 17/10. Os planos de Yi, Hunyuan, 7B, 6B e da automação de visão
> estão fora do escopo, e os pesos e backups desses ensaios foram apagados do
> `laboratorio-local` em 05/11.

**Navegação atualizada em 17/10/2026.** Base consolidada v1.7/v1.8 e ajustes
posteriores preservados; isso não cria nova versão de arquitetura. Navegação:
[índice por assunto](../docs/README.md) · [mapa dos componentes/dados](../docs/ESTRUTURA_ATUAL.md).

**Rodada vigente: treinamento automático por IA pausado.** A nova opção em
Treinamento → Sessão noturna permanece desligada, assim como a rotina diária.
Treinos manuais continuam disponíveis, mas sua avaliação não chama o professor
nem promove candidatos automaticamente. Defaults revisados, hashes, backups,
pilotos 6B/7B e o ciclo único de 16/10 estão no
[relatório atual](../docs/TREINOS_MANUAIS_DEFAULTS_20261015.md).
A decisão posterior sobre os sete treinos curtos e o plano agregado de10h está
no [relatório de16/10](../docs/AVALIACAO_CONVERSAS_E_SETE_TREINOS_20261016.md):
noite somente após novo aviso humano, sem reativar planos anteriores.
O [seletor da Central](../docs/SELETOR_VERSOES_MODELOS_20261016.md) diferencia
originais, checkpoints e candidatos experimentais; conversão não é aprovação.

**Decisão atual: continuar com o Professor 35B.** O 9B foi somente um A/B;
14B/122B foram pesquisados, não instalados. A qualidade do 35B ainda exige
curadoria por exemplo, não aprovação de si mesmo. Último baseline registrado:
74/74 grupos offline e 333/333 testes do laboratório em16/10; ver a
[reexecução de17/10](../docs/SINCRONIZACAO_GITHUB_20261017.md). Veja o
[reteste](../docs/PROFESSOR_RETESTE_RESULTADOS_20261014.md) e a
[comparação real](../docs/PROFESSOR_9B_VS_35B_20261014.md).
O [ensaio de foco editorial e grounding](../docs/PROFESSOR_FOCO_E_GROUNDING_20261015.md)
registra as correções do filtro v1.13.2 e a calibração posterior com referência
de tom fornecida pelo usuário. Gates do crítico não equivalem à aprovação de
naturalidade; os experimentos não alteram identidade, memória ou professor ativo.
O [lote posterior para revisão humana](../docs/PROFESSOR_LOTE_CURADORIA_20261015.md)
tem cinco diálogos gerados por perfil e abre direto na curadoria existente.
Aprovar uma referência vale para o diálogo completo e não inicia treino.
Após o [retorno humano](../docs/PROFESSOR_RETORNO_HUMANO_20261015.md), os cinco
diálogos antigos da Lilith seguem rejeitados. O probe agora recupera as notas
salvas por caso; a reavaliação cega expôs que a autocrítica ainda é otimista.
Oito novos diálogos foram preservados, incluindo falhas. A comparação curta
com nota exclusiva da Lilith está na [curadoria local](http://127.0.0.1:8788/?review=c586b7067caf6548),
com três pendentes e nenhuma exportação/treino. Professor ainda não homologado.
O [ensaio de mentoria direta](../docs/PROFESSOR_MENTORIA_20261014.md) mediu melhora
parcial: quatro diálogos antes/depois, não homologação dos três perfis.
O [reteste de transferência e alternativas](../docs/PROFESSOR_TRANSFERENCIA_E_ALTERNATIVAS_20261014.md)
adicionou dois casos novos, correção editorial e estudo de viabilidade do 9B;
nenhum modelo ou treinamento novo foi instalado/iniciado.

O [ensaio posterior do Defiant Fable 9B](../docs/PROFESSOR_DEFIANT_FABLE_20261014.md)
é um candidato isolado, explicitamente autorizado; não muda o professor ativo,
as identidades ou os executores de produção. Consulte o relatório para separar
download, integridade e inferência real de aprovação de qualidade.
Foram oito diálogos por modelo nos perfis Hoshino/Lilith. O candidato funcionou
e foi mais rápido, mas não substitui o professor: ainda erra autoria e certeza
de resultados. Nenhum dos textos foi aprovado para treino.
Na [mentoria posterior](../docs/PROFESSOR_DEFIANT_MENTORIA_20261014.md), foram
oito casos antes/depois: correções pontuais, mas sem melhora consistente de
qualidade e com custo maior de contexto/escrita. Sem treino ou promoção.

Nada inicia professor, treino ou entidade automaticamente ao abrir este guia.
As datas abaixo indicam quando cada
componente foi implementado/avaliado, não homologação de todo o sistema.

O checkout local, não um ZIP antigo, é a fonte do código. Leia o
[manual mestre](../docs/LABORATORIO_MANUAL_MESTRE_E_AUTOMACAO.md) e a
[consolidação v1.7](../docs/LABORATORIO_CONSOLIDACAO_20261012.md) e o
[relatório v1.8](../docs/LABORATORIO_V18_QUALIDADE_E_12H_20261012.md).
Os relatos históricos permanecem disponíveis; resultados novos não apagam falhas antigas.

### Repetir o ensaio de mentoria, opcional e manual

Somente com entidades dormindo, GPU disponível e sem outro worker. Não treina,
exporta ou aprova dados; solicita o mesmo lease conservador do laboratório:

```bash
PYTHONPATH=app:. compartilhado/ambientes/principal/bin/python -B -m laboratorio.tests.probe_geracao_professor --home "$PWD/laboratorio-local" --entity hoshino --methods staged --limit 4 --executor 35b --mentoring-comparison --confirm-gpu
```

O comando mantém proteção térmica conservadora padrão. O ensaio registrado usou
o opt-in manual de hotspot crítico já autorizado anteriormente, sem remover
proteções do driver; os dois modos estão descritos no relatório. Não habilitar
rotina noturna ou converter resultados em corpus só por passarem autocrítica.
`--case-set generalization --limit 2` escolhe os dois casos posteriores.
`--mentor-followup` aceita uma correção editorial explícita, de até 1800 caracteres,
adicionada ao diálogo com o professor. Nunca colocar segredos ou conversas reais
nesse argumento; não é memória de entidade nem dataset aprovado.

## Operação

Abra **Central → Laboratório Neural**. Há uma única interface de treinamento,
em `http://127.0.0.1:8788`, usando `treinos_unificados` e `treino_nf4_curto`.
O servidor do painel não carrega modelos. Também pode ser iniciado com:

```bash
PYTHONPATH=app:. compartilhado/ambientes/principal/bin/python -B -m laboratorio.labctl serve --port 8788
```

1. Selecione base instalada e entidade; 4B é exclusivo de Alistair.
2. Verifique o plano e seu benchmark/preset. Não há download automático.
3. Execute treino experimental ou smoke. Checkpoints incluem LoRA, otimizador,
   RNG e posição. Retomada exige mesma base, corpus e preset, com hashes íntegros.
4. Recarregue o candidato em processo novo e avalie validação/holdout separados.
5. **Somente com automação por IA autorizada**, a recarga tenta promover quando há perfil íntegro, controle
   físico comparável e todos os critérios passam. O aluno libera GPU/lease/locks
   antes da crítica pelo professor; o supervisor acompanha o mesmo job até o
   desfecho. Avaliações legadas sem esses contratos precisam
   de revisão explícita. Leia também as respostas para avaliar naturalidade.
6. Estável/rollback preservam cópias independentes no laboratório, **não produção**.

O Professor 35B transforma evidências de **treino autorizado**, em lotes curtos,
com raciocínio de curadoria limitado a 256 tokens. A política de thinking das
entidades não é alterada. Categorias, temas e diálogos de
um a três pares de fala são planejados; a persona vem do corpus e do perfil local versionado
explicitamente selecionado da própria entidade.
Na avaliação de candidatas, o mesmo professor julga respostas do aluno, sem
gerar um corpus. Essas respostas não aparecem como fontes treináveis. Crítica
incompleta, contraditória ou com objeções impede promoção automática.
Recusas de cópia, repetição, resposta genérica, JSON incompleto e truncamento ficam
registradas. Proposta não é dataset aprovado. Exportação continua exigindo
curadoria humana; validação e holdout nunca são matéria-prima do professor.
Fit Vulkan mantém margem de 1 GiB; camadas restantes podem executar em CPU/RAM.
Não se promete offload integral de um GGUF de 16 GB numa GPU de 8 GiB.

## Sessão noturna

Na mesma interface, **Vou dormir · autorizar sessão** define trabalho e janela.
O supervisor existente pede sono cooperativo, espera jobs/leases drenarem,
executa serialmente e solicita checkpoint ao terminar a janela. Restaura somente
as entidades originalmente acordadas, sem instalar adaptadores.
Após crash do supervisor, requer confirmação de recuperação; não repete treino.
O antigo timer/SIGSTOP v1.4 está aposentado e não deve ser reativado.
Os antigos runners `treino_texto`, `treino_qwen35_entidade` e fechamento v1.3
não iniciam novas cargas. Previews, módulos de referência, checkpoints e relatos
históricos foram preservados; agendas antigas de treino recusam replay. A CLI
de Alistair encaminha ao mesmo worker unificado e agora exige `--confirm`.

### Plano manual vigente — até 12 horas de parede

**Preparar noite manual · 7 treinos / até 12h (NÃO executa)** verifica pilotos,
corpus e recargas antes de preparar sete pares treino/avaliação: Hoshino/Lilith
Yi 6B, Qwen2.5 7B e Qwen3.5 9B, mais Alistair Qwen3.5 4B. Todos começam das
bases originais; não retomam os candidatos dos 20 minutos. Até 80 minutos por
treino, avaliação separada, early stop e teto de três epochs; não ocupar a
janela repetindo exemplos depois de deterioração da validação.

O usuário autorizou uma única sessão em **16/10/2026 às 00:00**; isso não ativa
a rotina diária nem a geração/aprovação automática de dados. Preparar não inicia
a sessão. Adequação técnica de 6B/7B depende de piloto salvo e recarga física,
não apenas de smoke ou de uma medição de loss.

### Referência anterior — seis horas efetivas por 9B

O plano v1.8 de seis horas efetivas por entidade é histórico nesta rodada;
não é o plano do botão atual. Sua função de compatibilidade só calcula previsões.
Hoshino treina na base original com seu train/validation, é avaliada em processo
novo e libera a GPU; então Lilith usa exclusivamente seus próprios splits.
Os objetivos são **21.600 segundos de updates por entidade**, excluindo carga,
validação, checkpoints e avaliação final. Portanto o tempo de parede é maior
que 12 horas. Early stop pode encerrar antes se a validação piorar.

Iniciar exige nova autorização explícita de sono/janela; preparar não suspende
entidades nem inicia subprocessos. **Preparar retomada interrompida** conserva
o relógio acumulado, optimizer/RNG, autoria e predecessor exato da avaliação.
Crash incerto nunca é autorização para replay automático. Checkpoints legados
sem relógio efetivo não recebem horas fictícias. Não misturar presets de offload
na retomada; os antigos continuam disponíveis como evidência.

O perfil experimental 9B `head_cpu` mantém camadas textuais e LoRA em GPU,
embedding/visual e head congelados em CPU. Só o head CPU usa FP32 para evitar
matmul BF16 emulado; arquivos originais permanecem intactos. O perfil só é
selecionado pelo laboratório a partir de medições, não muda os executores da
Central. Margem 768 MiB, serialização e `concurrency_validated=false` preservados.

## Validação / preservação

```bash
PYTHONPATH=app:. compartilhado/ambientes/principal/bin/python -B -m unittest discover -s laboratorio/tests -v
bash rodar_testes.sh
```

Testes offline não treinam, abrem microfone, chamam cloud ou acessam bancos reais.
ROCm/Vulkan são ensaios separados autorizados. Pesos originais, datasets,
identidades, memória e evidências ficam preservados fora do Git em
`laboratorio-local` (`~/laboratorio-lora` é compatibilidade).
Smoke/treino curto/recarga não substituem avaliação humana e ensaio prolongado.

## Integração cognitiva — 13/10/2026

Personalização agora permite capturar perfil versionado de Hoshino/Lilith:
identidade, constituição, traços consolidados e experiências escolhidas por
referências locais. Use **Personalização → Capturar perfil**, selecione-o no
Professor e revise o corpus proposto. Diários privados e estado afetivo
momentâneo não entram no treino. Não há exportação automática de todo histórico.

Corpora derivados aprovados carregam o SHA do perfil até o adaptador. A recarga
compara base sem LoRA, holdout completo e contratos fixos; quando todos os
critérios passam e a automação por IA está autorizada, tenta promover uma cópia estável independente.
Original HF + adaptador estável permanecem separados. Última estável e anterior
são preservadas para rollback. Isso não instala o adaptador no Ollama e não
reduz automaticamente o contexto de produção.

Leia [decisões, evidências e limitações](../docs/LABORATORIO_PERSONALIDADE_20261013.md).

## Rotina diária configurável

**Treinamento → Sessão noturna → Rotina diária automática** configura o mesmo
Supervisor da Central. Padrões: **00:30**, **30 minutos de inatividade**, janela
máxima de 600 minutos e treino curto de 10 minutos por entidade. A ativação
permanece **desligada** até a homologação do currículo/fluxo físico completo.
A Central precisa estar aberta; abrir apenas o painel do laboratório não mantém
um segundo agendador. Não desligamos o PC nos testes de desenvolvimento.

Somente currículo completo/inédito, crítica e tokenização comprovadas liberam
treino. A última estável conserva também seu corpus aprovado para a noite
seguinte. Segunda tentativa exige diagnóstico de qualidade concreto e tempo
seguro; crash, timeout ou efeito incerto não produzem replay. Agenda pendente
impede desligamento e restaura as entidades responsáveis. Sem aprovação, a
estável/original permanece intacta. Registrar estável não instala em produção.

O ensaio local do crítico é separado da suíte offline e não cria treino:

```bash
PYTHONPATH=app:. compartilhado/ambientes/principal/bin/python -B -m laboratorio.tests.probe_critico_professor --home laboratorio-local --profile NOME_DO_PERFIL.json --confirm-gpu
```

Leia [relatório da rotina e do professor](../docs/LABORATORIO_ROTINA_NOTURNA_20261013.md)
para resultados reais e pendências; testes simulados não homologam a noite real.

## Curadoria individual do professor — 13/10/2026

Abra **Central → Laboratório Neural → Professor MoE → Ver detalhes**. A seção
**Curadoria por exemplo** mostra a conversa completa, o parecer técnico e três
decisões: **Aprovar**, **Reprovar** (com motivo) e **Deixar pendente**. Reprovar
conserva o texto; excluir/descartar é outra operação, com arquivo de auditoria.
Decisões são persistentes e vinculadas ao SHA do conteúdo. Alterar o exemplo
invalida sua aprovação; exportação também revalida os gates atuais.

O botão **Revisar exemplos de referência da entidade** abre três rascunhos
autorais por entidade. Não foram gerados pelo professor, não são datasets e não
podem ser exportados como treino. Depois de aprovar, a opção **Usar como
referência** permite orientar gerações futuras daquela mesma entidade. Notas
de reprovação também orientam a escrita futura, sem usar a resposta reprovada
como alvo de treinamento. Todo o histórico permanece armazenado; somente um
conjunto pequeno entra no contexto.

O gerador atual escreve primeiro o cenário e depois uma resposta por vez,
sem mostrar falas humanas futuras. Metadados são determinísticos, integridade
e qualidade conversacional são revisões separadas, e somente o exemplo
defeituoso recebe nova tentativa. A intenção pedagógica é passada ao gerador,
não apenas ao crítico. Cópias de cenários são barradas antes do diálogo.

**Limitação medida:** o próprio professor como crítico ainda perde erros e
também pode reprovar indevidamente. Seus novos lotes (`generation_version=v1.12`)
exigem curadoria individual antes de exportar/treinar, inclusive pela rotina
noturna. Isso não altera a promoção automática de adaptadores já avaliados.
A rotina automática continua desligada; nenhum treino foi iniciado nesta rodada.

O ensaio de geração é manual, local e separado da suíte offline:

```bash
PYTHONPATH=app:. compartilhado/ambientes/principal/bin/python -B -m laboratorio.tests.probe_geracao_professor --home laboratorio-local --entity hoshino --methods staged --limit 2 --confirm-gpu
```

## Recuperação de executor ausente — local

Ao acordar pela Central, executores configurados ausentes são reconstruídos
no mesmo worker do laboratório. Usa última estável aprovada da entidade/base
ou original local pinado quando não houver estável. Original separado;
modelo existente não é substituído. Não baixa modelos, treina, modifica
identidade/memória ou habilita concorrência GPU. 6B experimental não é aprovado
para conversa somente por converter. Erro/crash bloqueia repetição automática.

No painel: **Treinamento → Recuperar executor ausente — pesos locais**.
Preview é somente leitura; execução exige confirmação. Progresso e parada
usam os mesmos jobs. Inferência/unload reais precedem publicação do alias.
Permissões/espaço/SHA/layout/template precisam passar. Conversor Qwen3.5 usa
`--no-mtp`: o backend atual não executa a camada especulativa.

Relatório: [recuperação e evidências](../docs/PROFESSOR_E_RECUPERACAO_RESULTADOS_20261013.md). Para nova
recuperação depois de falha, conferir primeiro o job/log e corrigir a causa;
não remover modelos/bancos para "tentar de novo".

`--experimental-references` usa os rascunhos ainda pendentes SOMENTE no ensaio;
nunca os aprova nem libera para geração de produção. Leia o
[relatório de implementação e testes reais](../docs/PROFESSOR_CURADORIA_RESULTADOS_20261013.md).

## Reteste e curadoria assistida — 14/10/2026

Geração por diálogo nativo, evidências por turno e referências pertinentes usam
o mesmo professor/jobs. Cenários não recebem histórias anteriores como contexto;
o verificador continua checando repetição. Conteúdo precisa de curadoria.

`review_examples` conserva revisão humana por padrão; curadoria assistida exige
`reviewer='codex_assisted'` e referência à autorização explícita. UI diferencia
esse revisor. Não é aprovação automática do professor. Nove referências autorais
foram aprovadas para orientar esta rodada, não para exportação/treino.

Professor ainda não homologado para gerar personalidade sem supervisão. Um
exemplo de raciocínio foi aprovado em conteúdo e tokenizado localmente (244/256),
sem treino. Leia [resultados e limitações](../docs/PROFESSOR_RETESTE_RESULTADOS_20261014.md).

## Comparação local do professor 9B/35B — 14/10/2026

O mesmo probe manual aceita `--executor 9b` somente para avaliar os pesos
originais instalados e verificados; o professor configurado continua 35B.
Não baixa, converte, publica aliases, acorda entidades ou aprova/exporta dados.
Preserva diálogos ainda não revisados ao cancelar e mantém compute lease até
o filho owned encerrar. O teste local não participa da suíte offline.

`--max-gpu` usa fit máximo sem remover a margem. O opt-in de ensaio
`--hotspot-critical-only` registra aviso de hotspot alto, mas continua parando
no crítico do driver; não modifica guardas de produção/treino, memória/edge,
fans, power ou hardware. Sem opt-in, a política conservadora continua ativa.

Quatro pares completos: 9B mais rápido, nenhum candidato homologado para
gerar personalidade sozinho. 9B atingiu crítico 110 °C e a comparação ampliada
ficou pendente. Leia o [relatório, textos e métricas](../docs/PROFESSOR_9B_VS_35B_20261014.md)
antes de interpretar notas automáticas como qualidade ou trocar o professor.
