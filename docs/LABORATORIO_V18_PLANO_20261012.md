# Laboratório Neural v1.8 — plano incremental

Baseline: commit d6bf47f, 74/74 grupos offline e 88/88 testes do laboratório.

## Arquitetura preservada

Central nativa → painel localhost existente → `treinos_unificados`/professor →
jobs duráveis e supervisor noturno existentes → lease exclusivo do Resource
Manager → executor ROCm/Vulkan isolado → checkpoints candidatos → avaliação →
aprovação humana. Nenhum scheduler, banco, backend ou interface paralela.

## Alterações previstas e consumidores

- Professor: esquema/validador, geração, auditoria, exportação aprovada e revisão
  no painel. Exemplos multitur­nos opcionais, compatíveis com propostas antigas;
  plano explícito de situações, não apenas categorias; perfil do corpus próprio.
- Treino: runner, snapshots/retomada, jobs, painel e supervisor. Medir tempo
  efetivo de updates separado de carga/avaliação/save; conservar o contador nos
  checkpoints. Avaliações intermediárias usam validação, nunca holdout.
- Preparação longa: prévia sem execução; plano sequencial no supervisor atual,
  avaliação do candidato correto e liberação física da GPU antes do próximo job.
- Central: atalho no dashboard para a interface de laboratório já existente.

## Segurança e limites de evidência

Não iniciar as 12 horas nesta rodada. Não promover adaptadores, misturar corpora,
alterar bases, memórias ou identidades. Margem e serialização GPU preservadas.
Benchmarks de minutos não homologam estabilidade de seis horas. Filtro técnico
do professor não equivale a aprovação humana de personalidade. Relatórios finais
devem separar medições, projeções e pendências.
