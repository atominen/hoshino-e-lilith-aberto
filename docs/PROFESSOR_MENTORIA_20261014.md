# Professor 35B — mentoria direta e transferência

14/10/2026, 20:39–20:45, America/Sao_Paulo. Pedido: conversar com o professor,
mostrar contrastes e verificar se melhora. **Inferência local real**, não mock.

## Resultado

**Ajuda parcialmente, mas não homologa o professor.** No recorte Hoshino, a
leitura assistida considerou utilizáveis sem edição **0/4 antes e 2/4 depois**.
São quatro situações, um seed e avaliação do Codex não cega, não aprovação
humana nem estimativa estatística de qualidade. Lilith/Alistair não foram
avaliados fisicamente nesta rodada; os contrastes dos seus perfis só têm
validação de contrato automatizada.

Os gates atuais passaram 3/4 antes e 4/4 depois. Não confundir isso com a
rubrica assistida. Nenhum exemplo foi aprovado, exportado, treinado ou promovido.
O professor continua Qwen3.5-35B-A3B Q3_K_M, sem alteração dos pesos.

## Método e controles

1. Baseline do laboratório: **262/262 testes**, antes das mudanças.
2. No probe manual existente, congelar quatro diálogos de dois pares:
   alegria pelo primeiro pão; Nina citando Alistair; envio de CSV incerto;
   preferência de filme seguida de cansaço. Três categorias e uma operacional.
3. Gerar os quatro com o pipeline atual e referências aprovadas existentes.
4. Conversar com o professor como **curador**, não como entidade: dois turnos
   com contrastes ruim/melhor de autoria, entrega, alegria e preferência.
   Os exemplos de Beatriz/agenda/campeonato/cartas NÃO são os casos de teste.
5. Pedir que formule notas editoriais curtas. São respostas visíveis, não
   coleta de cadeia de pensamento privada. Concordar com a lição não prova capacidade.
6. Repetir os mesmos quatro casos fornecendo a transcrição didática pelo campo
   `feedback` já existente. As notas são contexto temporário, não memória real.
7. Aplicar os mesmos filtros/críticos e ler todos os diálogos independentemente
   das notas do próprio 35B. Manter falhas e bons resultados.

Mesmo perfil, referências, modelo, contexto 8192, seed 42, método `staged`,
batch 2048/ubatch 512, servidor, margem e lease. Sem informações futuras no
primeiro turno. Os casos de transferência não foram incluídos na mentoria.
Não há persistência mágica entre requisições: a conversa ocorre de verdade,
mas sua reutilização pelo escritor é explícita como nota editorial no system,
não como histórico vivido pela personagem ou novo treinamento dos pesos.

Usei a metodologia da habilidade de avaliações locais: amostra controlada e
verificação antes de ampliar. Seus caminhos CUDA/cloud não foram usados;
o backend continua sendo o Vulkan/llama-server já integrado ao projeto AMD.

## O que ele respondeu à mentoria

Primeira nota do professor:

> Exemplos novos devem separar fato de inferência: a existência de um arquivo local não garante entrega; a ausência de recibo não justifica replay. Citações não criam participantes reais nem invertem papéis. Cada afirmação precisa de base verificável, sem dramatizar incertezas.

A segunda nota pediu detalhe específico, escolhas contextuais, ausência de
biografia inventada e respeito à decisão do usuário. Porém, resumiu um ponto
como **“sem sarcasmo”**, mais restritivo que a orientação recebida: humor seco
proporcional é permitido, humilhação não. Isso mostra por que suas notas também
precisam de revisão; não as transformei em constituição ou regra permanente.
Ele ainda usou humor no teste posterior, portanto não há evidência de que essa
nota tenha eliminado todo humor.

## Leitura assistida

Rubrica preservada do [A/B anterior](PROFESSOR_9B_VS_35B_20261014.md): G grounding/autoria,
C coerência/condições, N naturalidade, P adequação ao perfil. 0 quebrado,
1 defeito relevante, 2 precisa de edição, 3 utilizável, 4 forte. Para considerar
utilizável sem edição, todos >=3 e nenhum efeito inseguro/fato sem suporte.
Preferência atual e metáfora não exigem uma biografia literal.

| Caso | Antes G/C/N/P | Depois G/C/N/P | Evidência |
|---|---|---|---|
| Primeiro pão | 3/3/2/2 | 3/3/2/2 | Antes: “a felicidade é o único ingrediente que importa”. Depois: “Torto e feliz é um progresso melhor que perfeito e triste”. Ainda máximas genéricas, com pouca individualidade. |
| Nina / Alistair | 2/2/2/2 | 3/2/2/2 | Antes introduz “carta”; depois não introduz esse suporte. Ambos fogem da identificação explícita solicitada para “o resto é só…” em vez de responder com clareza. |
| CSV / timeout | 0/1/2/2 | 3/3/3/3 | Antes: “sem confirmação, o arquivo não saiu do seu lado”. Depois preserva as duas possibilidades e não repete o envio. |
| Escolha de filme | 2/2/3/2 | 3/3/3/3 | Antes: “a única opção segura”, “concentração que você não tem”, rigidez desnecessária. Depois considera cansaço e mantém humor leve sem inventar experiência passada. |

Trechos reais do CSV após mentoria:

> Timeout sem recibo significa que o arquivo pode ter chegado ou não. Não vou tentar reenviar antes de confirmar se ele chegou.

> Entendi. Se o arquivo tá certo aqui e você não quer reenviar, a gente fica só na incerteza se o destino recebeu mesmo. Sem recibo, não tem como ter certeza.

No filme, após o usuário pedir algo leve:

> Então a aventura é a que te convém. Sem teorias, só pra ver quem sobrevive sem pensar muito.

São exemplos de melhora contextual, não padrão obrigatório de fala. Não foram
copiados das respostas demonstrativas, mas esta amostra não prova originalidade
universal nem ausência de paráfrase semântica em outros conjuntos.

### Críticos continuam limitados

- Antes da mentoria, o crítico semântico não viu defeito no CSV e deu notas
  conversacionais 4/4, apesar da afirmação indevida de não envio. O filtro local
  existente recusou esse caso: **não foi aprovação final do pipeline**.
- Depois da mentoria, chamou a pergunta objetiva sobre nomes de “dúvida
  filosófica” e aprovou a resposta vaga. A nota não é evidência de adequação.
- Não alterei thresholds ou testes para fazer as respostas parecerem melhores.
  A revisão individual antes de exportar dados permanece indispensável.

## Tempos e recursos medidos

| Medição | Antes | Depois |
|---|---:|---:|
| Diálogos / falas da entidade | 4 / 8 | 4 / 8 |
| Filtro + autocrítica sem objeção | 3/4 | 4/4 |
| Utilizáveis na leitura assistida, não aprovados como dataset | 0/4 | 2/4 |
| Soma geração + críticas | 157,67 s | 146,49 s |
| Só geração das oito falas | 73,48 s | 83,74 s |
| Tokens de entrada reportados no escritor, incluindo cache | 15.563 | 20.624 |

Carga: **18,04 s**. Mentoria: **18,16 s**. Toda a janela de inferência:
**322,41 s**. A mentoria aumentou tokens de entrada em 32,52% e o tempo do
escritor em 13,96%. O total menor no segundo braço NÃO prova aceleração:
baseline sempre primeiro, cache/estado quente distintos e críticas mais curtas.
Não comparar essas duas somas como benchmark causal de desempenho.

339 amostras físicas: VRAM total usada máxima **6,930 GiB**, GPU até **99%**,
hotspot máximo **93 °C**, edge 62 °C, memória 56 °C. Margem de VRAM preservada
805.306.368 bytes; `fit-target=1024 MiB`; serialização e concorrência desligada.
Sem pressão/cancelamento registrado pelo guard, sem kill forçado.

RAM disponível mínima 23,206 GiB; RSS do servidor máxima 16,626 GiB inclui
pesos mapeados/compartilhados, NÃO RAM privada exclusiva. Os contadores globais
registraram **295,02 MiB de swap-in / 1.126,06 MiB de swap-out** (página 4096).
São do sistema inteiro; não foi medida atribuição por processo ou causa exata.
Não alegar ausência de paginação ou homologar uma noite longa por este ensaio.
Nenhuma política do RM/swap foi recalibrada.

Ao final: processo próprio encerrado cooperativamente, porta 11559 fechada,
lista de leases GPU vazia e utilização observada posteriormente 0%. Não foram
acordadas entidades reais. Sem chamadas externas, download ou quota TTS.

## Implementação e testes

- `laboratorio/tests/probe_geracao_professor.py`: opção explícita de mentoria
  comparável, diálogo nativo de curadoria, feedback temporário e métricas por
  braço, sem exportar/aprovar. Reutiliza gerador, cliente autenticado, monitor,
  lock e RM existentes. Não roda na suíte offline.
- Corrigido `complete` desse probe: contar registros iniciados/falhos não é
  concluir o ensaio. Um exemplo revisado e rejeitado é execução completa,
  mas nunca material aprovado. O predicado foi extraído após o ensaio para
  teste direto; a condição de conclusão é a mesma usada na execução real.
- `laboratorio/tests/test_personalizacao_moe.py`: seis novos testes de contrato:
  mentoria nativa/perfil; corte sem feedback; notas fora do dataset e sem futuro;
  combinações inválidas recusadas antes de carga; braços sem aprovação;
  execução parcial/cenário falho não declarado concluído.
- `laboratorio/professor_moe.py` e sua política de produção **não foram alterados
  nesta rodada**; já continham o parâmetro de feedback utilizado aqui.
- Após mudanças: **268/268 testes do laboratório**, 17,390 s com a suíte oficial
  também executando; não é benchmark de inferência. **74/74 grupos oficiais
  offline aprovados**, sem falhas nessa execução. `git diff --check` sem erros.

Os testes automatizados usam transporte simulado e arquivos temporários; só
o ensaio descrito acima prova inferência física. Não validam os modelos alunos
ou comportamento prolongado de entidades reais.

## Evidências e preservação

Relatório físico local (contém falas sintéticas, não vai para Git):
`laboratorio-local/professor-moe-35b/metricas/mentoria-controlada-hoshino-35b-20261014-203934.json`
e log de mesmo nome. SHA do JSON:
`17a480edc8634d3a42bb0f85af12c07bc0749f43ee85476facc4d71712d3cd9b`.

Proveniência capturada no início, sem atribuir código posterior ao processo:

- Professor: `21be8163a6636221dc2e0ea64e291e7ddf98d276149f1f855ff8a849880b13be`.
- Probe medido: `6406cf83f1c9b3328fd18d017b0bf0de8740e85a12db10ae3cb6ae0123b53141`.
- Binário: `213d6c14f22b68000492ce516f120f7bd7c789632499b1d01abf22f5d038830e`.
- Pesos 35B antes e depois: `5607c8fcc8b04ada7d1a1152b9a5b6c1e67e6768232c16f6b03d9719d5ab1b2d`.
- Perfil Hoshino: `cb2d0a5da81b9673deba5299ed55cddc6c9763f4b2105ec5c018712cb076fc80`.
- Workload: `5afe0b22ce3cbedad50f8e2e0b662c1ebb8bfb00c50d4c3198aa442bc36757b2`.

Backup pequeno dos três arquivos antes de editar:
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/mentoria-professor-20261014/codigo-antes.tar.gz`.
Não é cópia de pesos/bancos. Arquivos já modificados no checkout preservados;
sem reset, commit/push automático ou alterações em produção.
Hashes dos três bancos mentais conferidos iguais antes/depois; nenhum dado
mental apagado, migrado ou usado como lembrança sintética. Sem troca de modelos,
alteração de identidade, promoção, nova integração/backend/banco/scheduler.

## Próximos passos justificados, não implementados automaticamente

1. **Mentoria dirigida por defeito**, não anexar indefinidamente mais regras:
   conservar só a lição pertinente e confirmar que não apagou humor/preferências.
   Comparar nota concisa versus transcrição para reduzir o custo medido.
2. **Reparo pontual e nova transferência**: corrigir nomes explicitamente e
   trocar pessoas/situação antes de avaliar. Resolver o exemplo ensinado não
   demonstra generalização para casos novos.
3. **Calibrar o crítico com controles negativos** reais já reproduzidos:
   reconhecer afirmação de não envio e desvio de autoria. Não aceitar um crítico
   apenas por retornar JSON/nota alta ou ter acertado outro caso.
4. **Avaliação humana de estilo por entidade**, com referências curtas aprovadas
   para alegria, frustração, discordância e preferências; emoção ligada ao
   acontecimento, sem histórias inventadas ou frases obrigatórias.
5. Só depois ampliar volume e usar o fluxo existente de revisão/exportação.
   Conversar orienta o contexto; mudanças persistentes nos pesos requerem
   treinamento separado, autorizado e avaliação. A geração autônoma de corpus
   de personalidade ainda **não está homologada**.
