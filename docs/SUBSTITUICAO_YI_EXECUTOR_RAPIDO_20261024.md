# Troca dinâmica 7B/9B, 6B preservado e retiradas históricas — 24/10/2026

> Snapshot histórico: em27/10 a decisão foi substituída por
> [4B/9B, professor preservado](ORGANIZACAO_4B_9B_20261027.md).
> Pesos6B/7B foram retirados; não restaurar pela instrução antiga abaixo.

**Atualização posterior à limpeza:** o candidato Qwen3-6B foi baixado e
testado, mas não homologado. [Resultados](ENSAIO_QWEN3_6B_SNIPER_20261024.md).
Os bytes liberados abaixo são histórico das retiradas, não o espaço livre
atual após essa nova aquisição.

## Estado e decisão humana registrados em24/10

- Hoshino e Lilith: **troca dinâmica somente entre 7B e 9B por entidade**.
  A exigência anterior de um terceiro 6B foi substituída; a busca/integração
  desse terceiro executor está pausada, não é pendência de implantação.
- O **Qwen3-6B SNIPER baixado fica preservado**, por pedido explícito. Seus
  originais, revisão, tokenizer e código auditado continuam no laboratório,
  sem conversão, treino ou seleção automática. Não foi declarado ruim em
  todas as precisões: os limites dos ensaios NF4 permanecem no relatório.
- Alistair mantém **o mesmo Qwen3.5-4B**, no destino já configurado, sem
  alternância entre famílias. Não é o Qwen3-4B experimental removido abaixo.
- A escolha anterior de Qwen3-4B para Hoshino/Lilith foi um erro do assistente,
  não autorização humana para reduzir o requisito. Não reaproveitá-lo.

Pesquisa e limitações dos novos candidatos: [triagem 6B](CANDIDATOS_6B_20261024.md).
Não houve outro download, treino, ativação ou nova inferência nesta limpeza.

### Limpeza pontual após a decisão 7B/9B

As duas configurações `entidades/{hoshino,lilith}/config/executores.json`
já contêm somente o principal e o leve, sem `companion`. A seleção pinada
contém apenas `qwen35-9b`/`qwen25-7b` para Hoshino/Lilith e `alistair-4b`
para Alistair. Não foi necessário regravar configuração ou reiniciar serviços.

Removidas somente **oito cópias incrementais redundantes** (`*.json.backup-*`)
dos dois recibos em `compartilhado/runtime/ensaios/qwen3-6b-sniper-20261024/`:
50.860 bytes lógicos. Os eventos e logs brutos de cada cópia foram conferidos
como presentes nos JSON finais antes da remoção. As cópias intermediárias não
têm recuperação própria; os dois recibos finais completos e as evidências
dos erros permanecem intactos. Isso não representa limpeza de gigabytes.

Pesos 6B (Safetensors de12.396.072.584 bytes), arquivos de aquisição, código
diagnóstico, testes e relatórios úteis preservados. Nenhum reset de memórias,
conversas ou identidades; nenhum processo encerrado, serviço recarregado,
treino iniciado ou modelo promovido nesta organização.

Verificação desta limpeza: catálogo resolvido com a mesma seleção de início
do lançador confirmou exatamente principal9B + leve7B instalados para cada
Hoshino/Lilith. **99/99 testes offline de executores e18/18 testes dirigidos
do laboratório passaram**. SHA256 do Safetensors6B, código/revisão de origem,
configurações selecionadas e os dois recibos finais conferidos sem alteração.
Não houve nova inferência nem aprovação de qualidade por esses testes.

## Limpeza concluída

| Alvo autorizado | O que saiu | Blocos ocupados liberados |
|---|---|---:|
| Yi-1.5-6B reprovado | Originais HF, conversão exata, dois blobs e quatro aliases comprovadamente Yi | 23.148.810.240 bytes |
| Qwen3-4B experimental | Originais HF/cache local, GGUF, blob de execução, manifesto e metadados exclusivos desse alias | 13.055.590.400 bytes |

Total das duas retiradas: **36.204.400.640 bytes (~36,20 GB)**. Não confundir
esse valor com tamanho total do projeto ou nova medição de espaço livre.
Os pesos não têm backup local nem no GitHub; recuperação exigiria download
das revisões de origem e reconversão/importação. Não há reinstalação automática.

Antes da retirada foram conferidos ociosidade, locks, referências a blobs,
hashes dos pesos experimentais e ausência de consumidores acessíveis. Após a
limpeza, todos os outros manifestos e as configurações selecionadas mantiveram
os hashes. Nenhum prune global, processo morto ou serviço reiniciado.
Identidades, memórias, conversas, corpora e modelos de Alistair/7B/9B/voz/
imagem/professor permaneceram intactos.

Recibos locais, pequenos e sem pesos, preservados em
`laboratorio-local/controle-laboratorio/treinamento-unificado/reports/`:

- `remocao-yi-20261024.json`;
- `remocao-qwen3-4b-experimental-20261024.json`.

Os scripts `scripts/retirar_yi_20261024.py` e
`scripts/retirar_qwen3_4b_20261024.py` registram os alvos históricos exatos;
são dry-run por padrão e recusam reaplicar uma tentativa já registrada.
Não são coletores genéricos de modelos nem nova rotina de limpeza.

## Organização do código

Yi e Qwen3-4B ficam apenas como registros `retired` no catálogo: os caminhos
de download direto e de planos antigos recusam reinstalá-los antes de I/O de
download. Não aparecem como instalados sem pesos completos.

Foram retirados o comando `download-reference`, específico do experimento 4B,
e seu script de benchmark/importação. As regressões agora conferem a retirada
e a recusa de reinstalação. Permanecem a implementação histórica do Yi e seus
diagnósticos, necessários para entender falhas anteriores, sem ativação.

## Evidência histórica resumida, não aprovação

O [diagnóstico do Yi](YI6B_INTEGRACAO_E_TESTES_20261024.md) permanece íntegro.
O Qwen3-4B usou originais `Qwen/Qwen3-4B` na revisão
`1cfa9a7208912126459214e8b04321603b3df60c` e GGUF oficial Q4_K_M, revisão
`bc640142c66e1fdd12af0bd68f40445458f3869b`.

No ensaio isolado RX6650XT/Ollama Vulkan, contexto 2048 e thinking desligado,
a mediana de decodificação foi 56,88 tokens/s contra 35,52 do 7B; latência quente
2,420 s contra 3,782 s para saídas de 128 tokens. Não foi medido primeiro token
real. O corte intencional desse teste de vazão não aprovava conversa.

Qualidade: **6/8 na revisão semântica**, apesar de 7/8 no classificador.
Houve duas atribuições de sujeito/preferência erradas. Os oito casos terminaram
com EOS, mas isso não aprovou personalidade, integração de Lilith ou uso real.
Pico físico: 5.712.367.616 bytes VRAM, junction 77°C, `pressure=[]`.
Unload, encerramento owned e liberação de leases foram confirmados.

O recibo permanece em
`compartilhado/runtime/ensaios/qwen3-4b-20261024/comparacao-7b.json`;
o alias `hoshino-qwen3-4b-candidate-20261024:latest` **foi removido**.
Guardar esse resultado não conserva pesos nem autoriza repetir o ensaio.

## Treinamento anterior

O agendamento vencido de 23–24/10 não iniciou, não foi reprogramado e não foi
reutilizado para um substituto. [Impedimento documentado](ACOMPANHAMENTO_TREINO_20261023_24.md).
Uma lista histórica de sete treinos não comprova sete executores atuais.
