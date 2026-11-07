# Percepção de possíveis erros de transcrição — 23/10/2026

## Objetivo e comportamento

A transcrição pode chegar ao chat mesmo contendo um erro grave. Antes de
interpretá-la como uma ordem ou aprender algo sobre a pessoa, o próprio LLM
avalia se a fala faz sentido no contexto do mesmo fio. A mensagem original
não é corrigida, substituída ou apagada pela aplicação.

Se houver uma ambiguidade importante, a entidade faz uma pergunta curta
sobre a parte duvidosa. Uma alternativa sugerida na pergunta é hipótese,
não certeza sobre o áudio. Mudanças de assunto, humor, nomes novos, termos
técnicos, informalidade e outros idiomas não são erros por si mesmos.

Exemplo ilustrativo de comportamento esperado, **não amostra de inferência real**:
depois de conversar sobre memória, “apague a melhoria” pode provocar uma
pergunta como “Você quis dizer memória ou melhoria?”. A aplicação não converte
essa frase em “apague a memória” nem concede autorização de exclusão.

## Fluxo implementado

1. O transporte mantém texto e autoria originais. A Central resume indicadores
   do job ASR autenticado; dados enviados pelo cliente não podem aprovar a fala.
2. Hoshino/Lilith e Alistair fazem uma revisão curta com o executor já
   configurado, sem ferramentas, sem canal de pensamento e até192 tokens de
   saída. Nenhum transcritor/modelo novo foi instalado.
3. A revisão recebe a transcrição atual inteira, até6000 caracteres, e até
   seis mensagens anteriores do mesmo fio, com trechos limitados e omissão
   explícita. Não busca outro chat, diário ou memória privada para adivinhar
   uma intenção. Entrada maior fica pendente de esclarecimento, sem corte
   silencioso da fala atual.
4. `understood`: o fluxo normal recebe o **mesmo texto original**, com suas
   permissões e confirmações existentes. Compreensível não significa áudio
   verificado nem autorização adicional.
5. `clarify`: publica a pergunta e não inicia ferramenta ou tarefa a partir
   dessa entrada. Nome, fatos, gostos, reação afetiva e extração automática
   ficam adiados. Em Hoshino/Lilith, o turno duvidoso não é promovido a episódio
   de experiência para alimentar reflexões; o chat permanece preservado.
6. JSON inválido, resposta sem contrato, contexto insuficiente ou falha do
   executor: pergunta de indisponibilidade, sem repetir inferência/efeitos para
   tentar fabricar aprovação. O erro técnico fica no diagnóstico.

A resposta seguinte continua pelo histórico normal. Não há novo banco, fila,
scheduler, reenvio automático ou substituição silenciosa de palavras. Texto
digitado não paga a chamada extra. Pedidos de parada/correção conservam a
possibilidade de interromper trabalho por segurança antes da revisão; isso
não autoriza iniciar/retomar efeitos usando uma interpretação inventada.

## Procedência e memória

O marcador de voz vem de `audio_job_id` no envelope autenticado ou da captura
local com modalidade `fala`; escrever “[fala]” numa mensagem não muda sua
procedência. Ausência de métricas é **desconhecido**, não confiança alta.
Log-probabilidade média e probabilidade de ausência de fala são indicadores
do ASR, não a chance de o texto estar semanticamente correto e não identidade
biométrica. O estado de compreensão só vem da revisão do LLM.

O escriba e o aprendizado de nome recusam entradas ASR não compreendidas.
Esses guardas também valem para extração posterior/compactação com procedência.
O chat original e a pergunta continuam consultáveis; dados antigos não foram
apagados ou reclassificados retroativamente. Em Alistair, os turnos permanecem
citações atribuídas no SQLite do PC; não viram fatos por serem recuperados.

Capturas antigas/locais sem indicadores ainda recebem a checagem semântica.
Os sinais numéricos da Central passam a acompanhar novos envios quando o
lançador atualizado estiver carregado. Áudio ambiente continua sendo percepção
contextual, não ordem humana; esta revisão operacional se aplica às mensagens
dirigidas pela entrada de fala, não cria uma fila de ordens do ambiente.

## Componentes e compatibilidade

| Componente | Responsabilidade |
|---|---|
| `app/core/speech_perception.py` | Contrato, contexto limitado, indicadores fechados e validação da revisão |
| `iniciar_entidades.py:audio_origin` | Metadados derivados do job ASR pertencente à entidade |
| `app/main.py` | Revisão antes do roteamento/execução de tarefas faladas; pergunta sem aprendizado |
| `app/alistair_runner.py` | Mesmo contrato antes de ações, inclusive despertar/apresentação |
| `app/core/chat_identity.py`, `app/mind/scribe.py` | Não aprender nome/fatos de fala ainda duvidosa |

No Xbox, a revisão usa o payload textual já suportado: não envia o campo
`format/json_schema`, que a integração não aceita. O JSON é validado no PC.
Backend, modelo, limites de contexto e permissões existentes são preservados.
Na ausência de contrato válido não há fallback escondido para outro executor.

## Validação e operação

- 16 testes específicos de percepção: formato, procedência, isolamento do fio,
  preservação de texto, reconhecimento de dúvida antes de tarefas, resposta
  normal quando compreensível, texto digitado sem revisão extra, guardas de
  nome/fatos/afeto e publicação sem consolidar a fala duvidosa.
- 29 testes de continuidade de Alistair, incluindo três novos casos de voz
  e compatibilidade do pedido com Xbox sem `format`.
- Passagem final: **88/88 grupos offline aprovados**, com16 casos de percepção
  e29 de continuidade de Alistair. A verificação está
  registrada em `/tmp/percepcao-fala-suite-final-20261023.log`; os casos focados
  em `/tmp/percepcao-fala-final-20261023.log` e
  `/tmp/percepcao-fala-alistair-final-20261023.log`.

As fixtures de Alistair tiveram dois ajustes no teste novo: faltava `role` na
resposta simulada; depois a asserção consultava o fim da lista após ela receber
a resposta do assistente. Os logs intermediários foram preservados. Não se
enfraqueceu o contrato do executor para fazê-los passar.

Na inspeção inicial, Hoshino/Lilith estavam sleeping, Alistair offline, sem
jobs/leases. Não foram acordados, não houve reset, inferência em modelos reais,
captura de microfone, consumo de voz, instalação ou mudança no treino noturno.
Código novo precisa estar carregado pelos processos ao abrir/acordar novamente;
testes isolados não provam que uma janela/processo antigo recebeu hot reload.
Na inspeção final de processos não havia lançador, interface nativa ou runners
ativos do projeto; nenhum processo do usuário foi fechado. A próxima abertura
normal da Central e o despertar dos runners carregarão esta implementação.

## Limites e próximo teste humano

A checagem acrescenta uma chamada curta ao LLM por entrada falada. Sua latência
real depende do executor, fila e estado de residência; não foi medida aqui.
Não detecta todos os erros de reconhecimento: uma frase errada, mas plausível
no contexto, ainda pode passar. Também pode haver falso pedido de esclarecimento.
Não afirmar que a entidade ouviu novamente ou corrigiu a gravação.

No próximo uso, comparar fala clara, troca grave de palavra/negação/número,
referente ausente e mudança legítima de assunto. Conferir a pergunta no chat,
a ausência de ferramenta/fato indevido e a continuação depois da reformulação.
Esses resultados reais ainda estão pendentes; os testes acima são de software.
