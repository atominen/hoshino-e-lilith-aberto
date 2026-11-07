# Professor e recuperação local de executores — plano de 13/10/2026

## Ordem e arquitetura

1. Inferências reais no professor existente, mesmas situações/perfis/seed,
   comparando escrita conjunta e escrita por prefixo. Julgamento técnico do
   professor não equivale a qualidade humana; preservar respostas e falhas.
2. Laboratório/treinos_unificados → ação de recuperação no MESMO registro de
   jobs/worker/locks → conversores llama.cpp já instalados → staging/hash →
   importação nos stores próprios → recibo e probe → ativação somente ausente.
3. Supervisor, CLI e inicialização individual reutilizam essa ação. Consultas
   de UI não carregam/convertem modelos. Crash/resultado incerto não autoriza
   replay; recuperação requer nova confirmação e usa artefatos íntegros.

Fontes: última estável aprovada da MESMA entidade/base; original local íntegro
se não existir estável. Estável corrompida/incompatível bloqueia, não vira
fallback silencioso. Pesos originais e identidades nunca são regravados.
O usuário autorizou ativar a última estável na recuperação, com original separado.

## Limites

4B de Alistair, Qwen2.5 7B e Qwen3.5 9B existentes; 6B Yi somente quando
selecionado/aprovado, sem reinstalar Jan/Esper/Hunyuan removidos nem trocar
família. Converter um candidato 6B não o aprova para conversa. Não há download,
cloud, treino, scheduler/banco adicional ou concorrência GPU nesta rodada.
Conversão não implica inferência validada; importação e efeito são distintos.

Mapeados: trabalhador.do_convert/experimentos; versionamento_lora/stable;
treinos_unificados/worker/stop; supervisor/wake/sono/noite; lifecycle;
config/shell; resource_manager/catalog/profiles; Central/model_settings;
importadores/scripts; testes de consolidação, supervisor e lifecycle.

## Proteções necessárias

Hash de base/adaptador; tokenizer/template; arquitetura; espaço incluindo
F16/Q4/projetor/cópias; RAM física sem swap; cancelamento de filhos owned;
recibos duráveis; alias existente preservado; versão original separada;
modelo ausente ≠ descarregado; nenhum wake automático nos ensaios físicos.
Perfis GPU antigos não passam a validar novos manifests por coincidência de nome.
Manter margem AMD de 768 MiB e concurrency_validated=false.
