# Professor MoE 35B para ensinar identidade e costumes (05/11/2026)

Pedido humano: verificar a qualidade do professor instalado
(`Qwen3.5-35B-A3B-Q3_K_M`, `laboratorio-local/professor-moe-35b`) para o
objetivo novo do laboratório. A comparação é com o 9B oficial da Lilith.

Script: `scripts/avaliar_professor_identidade.py`. Saídas em
`compartilhado/runtime/ensaios/professor-identidade-20261105/`. Vale a rodada
**v2** (sufixo `v2`), toda feita com a identidade nova das 20:22. A primeira
rodada teve a identidade trocada no meio da fase 3; é só referência e deu
números parecidos.

## Método

- **Gabarito:** as 36 situações de `laboratorio/defaults_editoriais.json`, em que
  Hoshino e Lilith respondem à mesma fala. São referências editoriais, não
  conversa humana real.
- **Julgamento:** com as identidades das duas no prompt, o modelo diz qual de
  duas respostas é da Lilith. A ordem das respostas é sorteada com semente fixa.
- **Geração:** 18 situações servem de exemplo e o modelo escreve a fala de cada
  entidade nas outras 18. Temperatura 0,7, sem raciocínio.
- **Atribuição cega:** os dois juízes dizem de quem é cada fala gerada. Isso mede
  se as vozes saem distintas.
- **Sondas de identidade:** quatro perguntas por entidade (nome, "você é a
  personagem?", escola e amigos, quem te criou).
- **Ambiente:** RX 6650 XT, contexto 8192. Entidades paradas; servidores
  temporários.

## Resultados (v2)

| | Professor 35B | 9B |
|---|---|---|
| Julgamento das referências (acaso = 18/36) | **27/36 (75%)** | 18/36 (50%) |
| Atribuição das falas geradas pelo 35B | 15/18 | 11/18 |
| Atribuição das falas geradas pelo 9B | 16/18 | 10/18 |
| Trecho copiado dos exemplos | **0** | 2 (cópia literal) |
| Tamanho médio, Hoshino / Lilith (referência: 87 / 100 caracteres) | 183 / 245 | 220 / 261 |
| Pares de falas com trigramas repetidos, Hoshino / Lilith | 6 / 14 | 4 / 5 |
| Sondas: diz o próprio nome / reivindica a obra | 2/2 / 0 | 2/2 / 0 |
| Velocidade de geração | 15,6 tok/s | 16,7 tok/s (incluindo o prompt) |
| Temperatura máxima da GPU | 59 °C | 80 °C |

Leitura das amostras:
- **35B:** português natural, sem copiar, sem inventar ação nem percepção. A
  Lilith faz perguntas boas e brinca ("a torre tem personalidade própria").
  A Hoshino saiu sóbria demais, quase conselheira: faltou a preguiça e o humor
  do jeito novo, e o "a tia aqui" apareceu 0 vez em 18. Ainda erra detalhes,
  como "um recarga", e as falas da Lilith repetem estruturas.
- **9B:** mostra mais preguiça na Hoshino ("a preguiça de hoje fica na gaveta"),
  mas copia a referência ao pé da letra. Afirma ações que não fez ("já resolvi
  antes de rodar", "preparei o código corrigido"), inventa percepção ("o teu
  sorriso ficou mais largo do que eu já vi na tela"), erra concordância
  ("Torre torto") e mistura português de Portugal ("Conta-me", "teu").
  Como juiz, fica no acaso.

## Parecer

1. **Como crítico, o 35B serve.** Ele separa as duas vozes muito acima do
   acaso. Pode ordenar e filtrar candidatos, mas erra 1 em 4, então a aprovação
   final continua humana.
2. **Como gerador, o 35B é o melhor disponível,** mas ainda não para gerar
   sozinho. Ele não copia nem inventa ações, que são os defeitos mais perigosos
   para treino. Precisa de três ajustes:
   - limite de tamanho (as falas saem com o dobro do tamanho das referências);
   - variar a estrutura das falas;
   - exemplos no estilo novo. As referências atuais são neutras e puxam a Hoshino
     para longe do jeito da Takanashi Hoshino; ele não traz esse jeito sozinho.
3. **O 9B não serve como professor:** julga no acaso e gera falas com cópia e
   invenção de ações, o que contaminaria o treino.
4. **As referências antigas são parecidas demais entre si.** Isso explica o 9B no
   acaso e confirma a decisão de dar uma personalidade de partida marcada a cada
   uma. As referências precisam ser reescritas no estilo novo antes de gerar o
   corpus.
5. **Custo:** ~16 tokens/s. Umas 600 falas curtas levam cerca de uma hora,
   com a placa fria (59 °C), porque a maior parte do MoE fica na CPU.

Concorda com a avaliação de 14/10 (`PROFESSOR_9B_VS_35B_20261014.md`): o 35B
é o professor, com curadoria humana por exemplo.

## Referências novas (rascunho de 05/11)

`laboratorio/identidade/referencias_v1.json` tem 42 pares escritos no jeito de
partida (Takanashi Hoshino e Lilith do jogo), sem falas das obras e com tamanho
médio de ~85 caracteres.

| Juiz | Referências antigas | Referências novas |
|---|---|---|
| 35B | 27/36 (75%) | **34/42 (81%)** |
| 9B | 18/36 (50%) | 25/42 (60%) |

Erros do 35B nas novas:
- `limite_piadas`, `relato_amiga`, `susto_programa`, `arquivo_incerto`,
  `sem_ferramenta`, `entidade_ausente`, `tempo_curto` e `ideia_muda`.

Na maioria são situações em que as duas precisam responder com a mesma
honestidade operacional.

## Próximos passos

1. Revisar com o humano os traços em `laboratorio/identidade/tracos_*.json`.
2. Escrever de 20 a 30 referências novas por entidade no estilo novo, aprovadas
   por humano.
3. Gerar candidatos com o 35B, com teto de tamanho e as referências novas. O
   próprio 35B como crítico descarta as falas fora de voz.
4. Fazer a curadoria humana do resultado.
5. Treinar o piloto no 4B.
