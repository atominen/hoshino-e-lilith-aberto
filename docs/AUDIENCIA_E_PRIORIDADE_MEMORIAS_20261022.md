# Audiência e importância das memórias — 22/10/2026

Continuação do [refinamento cognitivo](REFINAMENTO_COGNITIVO_E_OFICINA_20261022.md).
Alterações de código e testes isolados: nenhuma edição de banco mental real,
identidade, modelo, configuração ativa ou treino. Sem reiniciar a Central,
chamar LLM/provedor, gastar créditos ou publicar no GitHub.

## Direto e global

- A origem extraída do transporte passa a registrar `chat_scope`. Texto de
  conversa não consegue se declarar público simplesmente escrevendo essa palavra.
- No turno global, episódios, conhecimento semântico e propriedades precisam
  de proveniência pública. Registros legados sem origem suficiente ficam
  preservados e disponíveis no direto, não automaticamente públicos.
- Modelos conceituais verificam todas as fontes no SQLite atual. Mistura de
  fonte privada/pública, fonte ausente/inativa e ciclos impedem recuperação
  pública. Rascunho novo feito no global recebe origem desse turno, mas
  continua hipótese, não observação ou fato confirmado.
- A oficina não permite usar uma referência privada para montar uma nova
  interpretação pública nem revisar um modelo privado através do global.
  Uma anotação privada/legada não vira pública apenas por citar fontes públicas:
  a própria anotação também precisa de origem pública.
- O contexto público não injeta automaticamente diário, acolhida privada do
  despertar, percepção ambiente pendente, perfil de pessoa, agenda, reflexões
  ou resumos afetivos sem origem separável. A identidade-base permanece.
  Os conteúdos não são apagados nem os estados reinicializados.
- Consultas de memória/estado privado ainda sem filtro próprio ficam ocultas
  das ferramentas oferecidas no global e bloqueadas também na execução.
  O histórico entre entidades aceita apenas Hoshino, Lilith ou Alistair como
  destino, não `usuario` como desvio para ler um chat direto.
- O Alistair aplica a mesma regra ao conhecimento SQL, não injeta um nome
  aprendido apenas pelo perfil privado e separa continuidade de tarefas
  diretas e globais mesmo quando a sessão humana é a mesma.
- O escopo acompanha a construção do contexto, a resposta e as ferramentas
  via contexto da execução; é restaurado ao sair do turno.

### Limites explícitos

Isto protege os caminhos de recuperação/contexto e as ferramentas de memória
auditadas, **não é uma sandbox do sistema operacional**. Um executor autorizado
a ler arquivos ou executar código com a mesma conta ainda precisa de política
de acesso própria; não se promete confidencialidade universal contra esse acesso.
Não foram apagadas nem reclassificadas mensagens que já chegaram ao global
antes desta correção, nem sanitizados resumos históricos já produzidos.

Os resumos de gostos, relações e emoções ainda não possuem proveniência granular
por audiência. Por isso sua projeção automática pública é conservadora. Uma
etapa futura deverá permitir a parte publicamente fundamentada sem expor os
motivos privados. Os estados continuam existindo no direto; não foi criada
outra personalidade para o global.

Esta rodada trata o global local; não certifica todos os canais externos,
compartilhamentos deliberados, arquivos e ferramentas criadas pela entidade.

## Ferro, Ouro, Diamante e Platina

O mapeamento entre registro e cartão agora é compartilhado pela interface e
pela recuperação. Identificação explícita da pessoa prevalece sobre nome;
nome ambíguo continua assunto, não identidade presumida.

A preferência acrescenta, respectivamente, **0 / 0,02 / 0,04 / 0,06** ao ranking.
É um ajuste pequeno de engenharia, ainda não calibrado por avaliação humana.
O filtro de relevância e o filtro de audiência continuam obrigatórios.
Platina não torna uma frase verdadeira, não aumenta confiança, não recupera
um assunto irrelevante e não libera uma memória privada no global.

No Alistair, o filtro de registros ativos ocorre antes do limite de busca:
registros aposentados recentes não expulsam todos os ativos da janela.
A janela passa a até 300 registros ativos recentes por tabela, com até três
resultados. Continua sendo recuperação limitada, não busca integral.

## Verificação

O grupo `test_audiencia_memoria` testa origem do transporte, restauração do
escopo, separação SQL/vetor, propriedades, fontes mistas/apagadas/cíclicas,
oficina pública/privada, exclusão de resumos privados do prompt, ferramentas
bloqueadas, continuidade do Alistair e prioridade sem alteração de verdade.
São dados descartáveis, sem inferência: não medem naturalidade ou qualidade
do modelo real.

Validação: **83/83 grupos offline aprovados** em duas passagens. Log da segunda:
`/tmp/audiencia-memoria-validacao-20261022.log`. Após o último endurecimento
sobre anotações privadas com fontes públicas, o grupo específico foi executado
novamente: **13/13 testes aprovados**, log
`/tmp/audiencia-memoria-contratos-20261022.log`.
A sonda `scripts/auditar_memoria_offline.py` também executou com sucesso;
`git diff --check` sem erros. Não foi reiniciada a instalação em execução.

## Próximas etapas

1. Ensaio real controlado depois de carregar o código atualizado: conversa
   direta/global, correção de informação e retomada em outra sessão.
2. Medir precisão, latência e contexto efetivo no PC e Xbox; não atribuir ganho
   de velocidade aos testes unitários.
3. Reduzir varreduras da memória e a limitação de busca do Alistair com um
   benchmark representativo antes de escolher índice/cache.
4. Evoluir proveniência dos estados afetivos e demais resumos derivados.
5. Verificar uso espontâneo da oficina por Hoshino/Lilith sem dar a solução.

Professor, treino noturno e desafio do buraco negro permanecem não iniciados.
