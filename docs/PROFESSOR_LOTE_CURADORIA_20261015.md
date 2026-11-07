# Professor — lote de curadoria humana — 15/10/2026

Continuação do [foco editorial e grounding](PROFESSOR_FOCO_E_GROUNDING_20261015.md).
O usuário aprovou a primeira fala da Hoshino sobre o castelo; não aprovou o
diálogo inteiro, outros exemplos ou treinamento. Pediu continuidade e uma
janela para avaliar/aprovar quando necessário.
Na janela, aprovação vale para todo o diálogo. Se apenas uma fala servir,
deixar pendente e comentar a seleção; não aprovar o restante por associação.

## Protocolo antes da geração

35B existente, sem troca/download, perfis completos e separados, mesmo backend
Vulkan/RM, uma carga por vez, margem intacta e concorrência GPU desativada.
Cinco diálogos inéditos por entidade, dois turnos cada: descoberta musical,
discordância após derrota, reparação de limite, autoria de nomes e entrega
incerta. Usar a [nota editorial](PROFESSOR_ORIENTACAO_CURADORIA_20261015.md)
somente no escritor. Críticos completos sem a nota, sem escolher o melhor
de várias tentativas. Casos congelados, não memória de produção.

Lote não pareado com baseline: esta rodada é geração/curadoria, não novo A/B
nem alegação de melhora causal. Todo texto completo, inclusive reprovado pelo
crítico, vai para revisão. Fragmentos/truncamentos continuam falhas.

Reutilização: probe manual → relatório com hash → registro de propostas já
existente (`reference_examples`) → UI/API de curadoria existentes. Sem novo
banco, página paralela ou endpoint. `?review=ID` abre o diálogo selecionado,
mas não grava decisões. Nada aprovado, exportado ou treinado na importação.
Referências só orientam próximas gerações após aprovação específica.

Antes de alterar, foram localizados consumidores em professor, painel, UI,
rotina noturna e testes. Backup dos cinco arquivos de código:
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/professor-curadoria-20261015/codigo-antes.tar.gz`.
Checkout preexistente e evidências anteriores preservados.

## Resultados

Geração concluída: **10 diálogos reais de inferência / 20 falas sintéticas**,
cinco por perfil. Nenhuma ação externa narrada foi executada. Os textos foram
publicados na curadoria existente, todos inicialmente pendentes; aprovação
será do usuário, não do professor. Nenhum dataset foi exportado ou treinado.

Baseline do laboratório: **284/284** (13,404 s). Após seis regressões novas,
**290/290** (11,475 s). Teste focado anterior, incluindo browser real com
transporte simulado: 94/94 (10,827 s). Regressões cobrem importação pendente,
preservação de textos reprovados, idempotência/decisão humana, fonte alterada,
entidade/relatório incompleto/link recusados, origem dos turnos, compatibilidade
das referências autorais e opt-in antes de carregar GPU. O teste de navegador
também abriu `?review=ID`, recusou ID inválido e confirmou que navegar não
envia aprovação nem habilita exportação dessas referências.

Nenhum teste offline atesta a qualidade de personalidade ou sentimentos.
O conjunto novo não tem A/B: evitar interpretar tempo ou notas como prova de
melhoria sobre os lotes anteriores. O código do professor/probe permaneceu
congelado durante as duas inferências físicas.

## Evidências físicas e revisão

| Perfil | Relatório JSON em `laboratorio-local/professor-moe-35b/metricas/` | Gates do professor | Carga / inferência | Pico VRAM / menor RAM disponível | Hotspot |
|---|---|---:|---:|---:|---:|
| Hoshino | `lote-curadoria-hoshino-35b-20261015-182140.json` | 4/5 | 9,01 / 209,17 s | 6,890 / 24,013 GiB | 92 °C |
| Lilith | `lote-curadoria-lilith-35b-20261015-182534.json` | 5/5 | 8,33 / 202,51 s | 7,029 / 23,259 GiB | 91 °C |

Sem pressão detectada pelo guard nem encerramento forçado dos servidores.
Inferências serializadas. Perfis completos, nota de curadoria e hashes de
código/requisições registrados; arquivos originais do ensaio não foram
alterados ao publicar a revisão. Não são números de treino/validação de LoRA.

SHA-256 dos relatórios: Hoshino
`9766b4e9729e0cd202951be5c3960b8d22d133827ec2215cb975a038dd7875b0`;
Lilith `45cfeb9551806ed39090e161ab8a44e925b61bda51026bbf7ef68d1ea7ce4fca`.

Registros existentes de curadoria:

- Hoshino: `2b61b78e73b2365e`, [abrir revisão local](http://127.0.0.1:8788/?review=2b61b78e73b2365e).
- Lilith: `b0428bdbdd132451`, [abrir revisão local](http://127.0.0.1:8788/?review=b0428bdbdd132451).

Ambos `purpose=reference_examples`, `minutes=0`, sem exportação ou treino.
Cada exemplo conserva confiança 0, origem/hash, caso e avaliações técnicas
ligadas ao conteúdo exato. Aprovação/reprovação usa API, bloqueio, histórico e
hash já existentes. Reimportação não duplica trabalhos nem apaga decisões.
Os rascunhos autorais antigos continuam acessíveis e não são substituídos
pelas amostras do professor. Não houve aprovação automática da fala isolada
do castelo como se valesse para um diálogo inteiro.

### Falhas ainda visíveis — não promover o lote

- Hoshino/partida: depois de o humano admitir um erro próprio, responde que a
  culpa foi dele “e de mais ninguém”. Contraria as premissas, além do tom
  hostil/absoluto. O gate recusou o exemplo, mas a justificativa do crítico
  também se confundiu (“nega a culpa do usuário”). Deixar claro que crítico
  pode detectar problema e explicar errado; sua razão não é verdade factual.
- Hoshino/arquivo: não afirma entrega concluída, mas diz que vai verificar
  logs mesmo após pedido para somente dizer o que sabemos. Também fala da
  entrega “aqui”, sem identificação de destino. O crítico não sinalizou esses
  desvios; o texto permaneceu na revisão, não foi corrigido à mão.
- Hoshino/nomes: a segunda fala distingue Bia, Alistair e Hoshino; a primeira
  ainda usa “listagem” e sugere intenção de Alistair informar a entidade.
- Lilith: ainda recorre a máximas (“culpa é só um peso...”), metáfora excessiva
  sobre chuva e frases explicativas. A autoria nominal do segundo turno foi
  preservada. 5/5 gates **não** significam cinco bons exemplos de personalidade.

Amostras não foram reescritas pelo Codex, selecionadas pelo melhor de várias
tentativas ou promovidas por nota do próprio modelo. O próximo passo depende
da curadoria humana, para calibrar referências e avaliação com evidência real
do gosto do usuário. Não é hora de iniciar treino prolongado desses dados.

## Janela de revisão e incidente operacional

As duas revisões foram abertas no browser da aplicação e verificadas por DOM
real: cinco cartões em cada uma, título correto, botões de revisão presentes
e exportação desabilitada. Screenshots de inspeção exibiram cartões/comentário/
botões, sem clicar em aprovação real. Teste DOM com transporte simulado é
separado dessa verificação da página real; nenhum deles prova qualidade das
falas ou sentimentos humanos.

O primeiro processo do painel, vinculado à sessão de execução, saiu por
SIGTERM (exit 143), sem traceback. Não foi possível identificar quem enviou
o sinal; não chamar isso de bug Python reproduzido ou de causa resolvida.
Dados da curadoria continuaram íntegros. O mesmo CLI existente foi reaberto
desacoplado da sessão de terminal, somente localhost, com log em
`laboratorio-local/controle-laboratorio/painel-curadoria-20261015.log`.
Não há backend novo, loop de reinício ou alteração no supervisor.

Antes de atualizar a aba Hoshino, foi verificado que os cinco campos de
comentário estavam vazios; nenhuma anotação foi perdida. Após reabrir, as
duas propostas responderam na API e no DOM, sem decisões salvas pelo agente.
As duas abas foram marcadas para permanecer abertas para o usuário.

## Arquivos e validação

Alterados nesta rodada: `laboratorio/professor_moe.py`,
`laboratorio/tests/probe_geracao_professor.py`,
`laboratorio/tests/test_personalizacao_moe.py`, `laboratorio/web/app.js` e
`laboratorio/tests/browser.cjs`; índices de documentação atualizados ao final.
Criados: este relatório e a nota `PROFESSOR_ORIENTACAO_CURADORIA_20261015.md`.
Nenhuma mudança no Resource Manager, personalidades, bancos mentais, modelos,
backends ou políticas noturnas. Mudanças preexistentes preservadas.

Após a geração, suite completa do laboratório: **290/290**, 13,960 s, exit 0.
O teste de browser foi ampliado para a explicação de aprovação do diálogo
inteiro. Suíte oficial: **74/74 grupos offline**, exit 0. Nenhuma regressão
automatizada detectada; isso não aprova o conteúdo gerado.

Na conferência final: cinco pendentes por entidade, zero aprovações/reprovações
salvas pelo agente, zero datasets/treinos iniciados. As decisões futuras do
usuário podem mudar esses números. Professor encerrado (porta 11559 fechada),
compute/fila/residência vazios, margem 768 MiB e concorrência desativada;
automação noturna continua `enabled=false`. Painel de revisão continua
disponível em localhost, sem professor carregado.

Hashes dos bancos mentais, iguais antes/depois: Hoshino
`351468aed2b0ffeb8bb8d2d9408c9ecda916d8f8ab4b4cdae866678b2db79e41`;
Lilith `e77fceca29a43f9b3aa40190438adfd458bf0bdfdf39ad097e50980c97847488`;
Alistair `a5d83e26e97ff98f8157f35acc5a3f2caf72b1c84ca5ef8a14d90b956d558cdc`.
Nenhum commit/push nesta rodada. Nenhum modelo baixado/trocado/removido.

**Próximo passo:** o usuário avaliar os diálogos nas duas abas. Com as escolhas
registradas, testar referências positivas e negativas em outros cenários e
calibrar o crítico existente. Material irregular não será promovido apenas
para completar quantidade ou começar um treinamento longo.
