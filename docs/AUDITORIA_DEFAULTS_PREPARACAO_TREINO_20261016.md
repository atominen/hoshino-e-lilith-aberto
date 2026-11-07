# Defaults e preparação do ciclo6h — auditoria de16/10/2026

**Atualização posterior:** a preparação de contexto foi corrigida e passou
323 regressões/74 grupos offline. A autorização6h diurna foi substituída por
quatro candidatos6B/7B de20min agora e noite somente após novo aviso humano,
com objetivo12h de otimização. Ver [registro atual](TREINOS_20M_6B_7B_20261016.md).
O restante abaixo preserva o diagnóstico anterior à correção, não o estado
de implementação atual.

## Parecer

**Os materiais defaults existentes são aproveitáveis para treinar candidatos.**
Há dois problemas de preparação e uma limitação importante do piloto. Não é
necessário buscar outro modelo nem recriar os corpora para corrigir isso.
A partida do ciclo6h ainda não foi feita: o plano atual continua bloqueado.
As correções abaixo foram propostas, NÃO implementadas nesta auditoria.
Foi solicitada confirmação para corrigir a preparação e permitir candidatos
experimentais após verificação técnica, sem promover versões reprovadas.

Esta rodada executou leitura de código/corpus/proveniência e tokenização real
em CPU. Não executou nova inferência GPU, LoRA, professor, serviços externos,
edição de banco mental ou alteração de identidade. Nenhum resultado simulado
foi apresentado como comportamento aprendido.

## 1. Defaults conferidos

| Entidade | Treino | Validação | Holdout |
|---|---:|---:|---:|
| Hoshino | 758 | 131 | 104 |
| Lilith | 758 | 131 | 104 |
| Alistair | 83 | 27 | 16 |

Todos possuem mensagens user/assistant válidas. Não foram encontradas
autodeclarações estrangeiras como ChatGPT/Qwen/Yi nos alvos do treino, nem
ocorrências de Gustavo nesses arquivos. Nomes, regras contra replay de efeitos
incertos e estilos individuais já existem no material. Zero conversas idênticas
entre os splits da mesma entidade. Isso não prova independência semântica:
Hoshino/Lilith têm2 respostas finais de validação e9 de holdout já presentes no
treino, em perguntas diferentes. Alistair não tem essas repetições exatas.

Hoshino/Lilith têm36 conversas com múltiplos turnos cada.401/758 conversas são
idênticas entre ambas: muitas cobrem regras operacionais comuns. Isso não
mistura bancos/treinos, mas limita o quanto a queda de loss demonstra diferença
de personalidade. Esses defaults servem de base, não de homologação de afeto,
consciência, naturalidade prolongada ou personalidade final.

## 2. Defeito confirmado: contexto diferente entre treino e avaliação

`personalizacao.dataset_profile` retornaNone para defaults sem sidecar, e
`training_identity(entity,None)` retornaNone. O runner treina e calcula loss
sem a identificação curta, mas `dialogue_control` acrescenta a identificação
na geração de avaliação. Os sete pares entidade/base apresentaram prefixos
diferentes, comprovados com os tokenizers reais instalados.

Caso especialmente relevante: o template nativo do Qwen2.5 acrescenta, sem
system explícito, “You are Qwen, created by Alibaba Cloud. You are a helpful
assistant.”. Portanto o treino atual recebe esse enquadramento enquanto os
alvos ensinam Hoshino/Lilith; a avaliação troca o enquadramento. Não modificar
o template ou os pesos originais: fornecer o contexto externo coerente.

Isso é evidência de inconsistência, não prova de que explique sozinho todas
as falhas do Yi. ChatGPT não apareceu como resposta de treino; o modelo ainda
pode carregar tendências anteriores ou simplesmente não ter aprendido o nome.

## 3. Piloto não percorreu os exemplos de identidade

A proveniência do candidato `cdbf18c6ff1e46b0-yi-6b` confirma87updates,
início dos originais, nenhuma retomada e247,381s efetivos. O SHA de
personalizacao.py registrado no treino continua igual ao arquivo auditado.

Reprodução da ordem exata: shuffle com seed247 sobre758exemplos. **Nenhuma
das primeiras87amostras contém Hoshino na resposta.** A primeira ocorre na
posição108 da ordem embaralhada (linha150 do arquivo). As seguintes estão
nas posições124/140/141. A mesma ordem se aplica ao corpus Lilith de mesmo
tamanho. Portanto não é correto inferir desse piloto que o modelo é incapaz
de aprender o nome. Ele ainda não recebeu essa supervisão.

A busca estreita por timeout/incerto/reenvio/mutável nas perguntas encontrou
somente uma amostra nas primeiras87: linha500, na posição13, ensinando
verificar estado/hash antes de repetir. Isso não demonstra domínio de todos
os cenários de entrega. Não preencher o teste com a resposta esperada nem
repetir só oito perguntas para fabricar aprovação.

## 4. Compatibilidade da correção proposta — CPU, não inferência

Foi usada em memória a identificação curta já existente na função
training_identity para perfis explícitos, sem criar/capturar perfil mental,
alterar corpora ou tocar identidades. Treino e geração receberam a MESMA string.
Nos sete pares, o prefixo tokenizado coincide e o system automático Qwen não
é incluído. Todos os splits continuaram válidos, sem descarte ou truncamento.

| Base | Entidade | Maior sequência atual | Com contexto curto coerente |
|---|---|---:|---:|
| Yi6B | Hoshino | 200 | 228 |
| Yi6B | Lilith | 187 | 214 |
| Qwen2.5-7B | Hoshino | 163 | 170 |
| Qwen2.5-7B | Lilith | 155 | 161 |
| Qwen3.5-9B | Hoshino | 127 | 152 |
| Qwen3.5-9B | Lilith | 123 | 147 |
| Qwen3.5-4B | Alistair | 60 | 85 |

Todas abaixo do limite256 do runner. São6084preparações de exemplos por
configuração (os corpora são reutilizados entre bases), não6084diálogos novos.
Isso comprova compatibilidade de entrada/máscara, não qualidade aprendida.

## 5. Treinar candidato não equivale a aprovar/promover

O default_cycle_plan atual exige que o piloto6B/7B passe os oito contratos antes
do treino longo. No piloto presente, isso exigiu aprender um nome antes de
receber seus exemplos. Recomenda-se separar claramente:

- Prontidão para experimentar treino: corpus íntegro/isolado, mesmo contexto
  e template, labels válidos, memória/temperatura seguras, checkpoint/recarga
  íntegros, loss finita e treinamento isolado sem execução de ferramentas.
- Aprovação do resultado: identidade, autoria, não repetir efeitos incertos,
  respostas completas, validação/holdout, naturalidade e ausência de regressão.
  Os critérios existentes de promoção NÃO devem ser afrouxados.

Falhar como candidato ainda em aprendizado não autoriza colocá-lo em produção.
Permitir mais treino controlado também não significa que6h resolverão tudo.
Essa mudança de gate exige decisão explícita; não remover bloqueio escondido.

## 6. Correções mínimas propostas e compatibilidade

1. Usar o mesmo contexto curto de entidade nos defaults de treino/validação/
   geração, preservando native chat templates e exclusividade dos corpora.
   Não codificar personalidade completa nem a resposta dos benchmarks.
2. Registrar versão/hash do contexto nos planos, checkpoints e relatórios;
   manter leitura de candidatos antigos. Recusar retomada silenciosa com
   tokenização/contexto diferente; novos treinos continuam dos originais.
3. Separar elegibilidade para treino experimental de aprovação/promoção final,
   preservando os testes que reprovam identidade e replay incerto.
4. Revalidar preparação, checkpoint/recarga e recursos com o novo contexto;
   contar tempo efetivo realmente atingido. Early stop/3epochs continuam.

Arquivos candidatos a alteração: `laboratorio/personalizacao.py`,
`treino_nf4_curto.py`, `versionamento_lora.py`, `treinos_unificados.py` e grupos
existentes de regressão do laboratório. Risco principal: mudar tokenização de
checkpoint legado sem versionamento; por isso não retomar/corrigir pesos antigos.

Não é preciso baixar outro modelo, trocar datasets por material do professor,
mudar memórias, criar planner/scheduler ou aumentar o limite de VRAM.

## 7. Situação para as seis horas

É tecnicamente plausível usar os defaults já criados após corrigir/verificar
a preparação. Ainda faltam benchmarks salvos/recargas dos outros pares para
dimensionar checkpoints e recursos. Os smokes antigos são de2updates: não
usar suas taxas por hora como garantia de execução longa.

O alvo permanece21600s somados entre os sete treinos, não seis horas por
entidade/modelo. Alistair tem só83exemplos; o teto3epochs permite249updates.
Logo pode encerrar antes da sua parcela de51min. Não repetir dados para
preencher horas, nem declarar6h efetivas se early stop/epochs encerrarem antes.

O último teste físico Yi completou em652,71s com pico102°C, exit0 e sem pressão;
isso é evidência curta, não homologação térmica de6h. Guarda105 do runner,
margens de VRAM, serialização e proteções do driver devem permanecer.
Nenhum worker/lease ativo nesta auditoria; ciclo6h NÃO iniciado. Bases/corpora
conferiram com o índice existente e ficaram intocados.
