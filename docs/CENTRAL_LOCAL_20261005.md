# Central local — entrega de 05/10/2026

Registro histórico. A [entrega de 06/10](ENTREGA_20261006.md) substitui as
informações abaixo sobre Alistair ausente, modelos compartilhados e jobs em memória.

## Como abrir

Execute `iniciar_entidades.py` ou o atalho `Hoshino e Lilith.desktop` na raiz.
A central abre no navegador em 127.0.0.1:8769 e oferece Hoshino, Lilith ou ambas.
Não cria perfis de uso. O servidor aceita apenas conexões locais e fornece uma
chave temporária à própria aba. Fechar a aba não encerra as entidades.

O executável também aceita `--verify`, `--status`, `--entity ambas`,
`--sleep hoshino` e `--wake usuario lilith`. Um pedido de despertar só é
atendido enquanto a central estiver rodando; a confirmação depende de presença
real, não apenas de ter criado um processo.

## Implementado

- Interface de conversa com seleção da destinatária, autores, histórico, estado
  das duas entidades e painel separado para recursos. Não inicia modelos só por abrir.
- Caixa postal SQLite compartilhada, independente dos bancos mentais. Mensagens
  enviadas durante o sono permanecem pendentes. Despertar é opcional e explícito.
- Respostas passam pelo mesmo canal privado. A fila não marca a mensagem como
  lida antecipadamente. Respostas a uma mesma mensagem/destinatário são
  idempotentes, inclusive após uma interrupção.
- Até seis respostas automáticas por cadeia. Ao chegar ao limite, a mensagem é
  registrada sem nova inferência; uma nova mensagem humana começa outra cadeia.
- Instância única por identidade, supervisor único, acompanhamento de saída e
  espera entre novas tentativas após falha. Não mata processos a partir de PID antigo.
- Pausa cooperativa: deixa terminar conversas, HTTP do modelo, consolidação de
  memória acompanhada e imagens antes de sair. Operação pendente não vira sucesso.
- Arbitragem interprocessos da GPU com renovação de telemetria. O lock real
  continua válido mesmo se o tempo estimado expirar. Chat, visão e imagens usam
  a mesma coordenação. Pesos concorrentes dos daemons dedicados 11435/11436 são
  descarregados e conferidos antes de usar a GPU; o daemon padrão 11434 não é alvo.
- Portas distintas para as pontes Minecraft: Hoshino 8765, Lilith 8766. A identidade
  também é passada às integrações iniciadas pelo gerenciador de serviços.
- Nome de saída de imagem único e conferência de integridade/dimensões do PNG.

## Verificação e limites

A suíte offline inclui testes de mensagens persistentes, confirmação de leitura,
resposta duplicada, concorrência de escritores, queda de processo, exclusão de
GPU, despertar pendente, HTTP local e uma sessão Textual headless com roteamento
real e resposta de modelo simulada. Os testes usam arquivos temporários.

Esses testes **não** demonstram uma conversa real entre os dois LLMs, conectividade
com um mundo Minecraft, funcionamento dos dois bots Discord ou aprovação no
benchmark `aa`. Não há credencial Discord própria da Lilith validada nesta entrega.

Resultado desta etapa: os 21 grupos da suíte passaram; o grupo novo contém 15
testes. A estrutura de inicialização das duas entidades também passou na
verificação sem iniciar serviços. A central foi aberta e inspecionada no navegador,
sem enviar mensagens de teste para as memórias reais.

O microfone da interface antiga continua disponível no iniciador individual.
No modo central/headless a captura foi desabilitada para não duplicar escuta e
atalhos globais entre processos. Microfone/voz no navegador ainda precisam de
integração e teste com o dispositivo real. Não há ainda cancelamento remoto de
uma operação travada: a pausa espera, não promete encerramento instantâneo.

O gerenciador arbitra a GPU; não é ainda um escalonador completo de RAM, CPU,
prioridades ou quotas. Jobs de imagem ainda têm catálogo em memória. Os arquivos
gerados permanecem, mas retomar o catálogo de jobs após crash está pendente.

## Material AAAA: direção aceita, sem confundir rascunho com entrega

Referência original arquivada em `planejamento/AAAA_20261005_referencia.txt`.
Ela orientou a central conversacional, a autoria explícita e o isolamento dos
estados. Não foi usada como autorização para instalar modelos, mudar drivers,
alterar kernel ou inventar uma terceira identidade.

Próximas etapas de projeto, ainda não implementadas:

1. Filtrar saliência antes de transformar nomes de pastas/janelas em emoção ou
   curiosidade. Avaliar relevância, persistência e vínculo com objetivos.
2. Separar fato, interpretação e confiança; relações direcionais e pendências
   relacionais não devem ser tratadas como emoções momentâneas.
3. Valores adquiridos só após evidências repetidas e reflexão; predisposição
   inicial não deve fingir ser experiência vivida.
4. Consolidar arbitragem de decisão e reduzir chamadas ao modelo por relevância,
   sem cortar respostas ou impor um roteiro rígido de personalidade.
5. Alistair como organizador textual leve, sem falar pelas outras. Nesta entrega
   há uma central mecânica, **não um Alistair com LLM instalado**.
6. Progresso/estimativas e standby de imagem, retomada de jobs, áudio no navegador.

## Aceitação do material aa

Não declarar aprovado sem executar e registrar, para cada entidade:

- Exatamente três desafios: rodada jogável de 21, moeda e dois D6.
- Regras explícitas, valores sorteados e validação matemática independente.
- Geração real de imagem representando os três desafios; conferir conteúdo visual,
  não apenas existência do arquivo ou status da fila.
- Relatório com data, resultados, verificações e falhas; reler o relatório salvo.
- Para Hoshino, o caminho legado informado em `aa` resolve para sua oficina.
  Para Lilith, usar a própria `entidades/lilith/workspace` para não cruzar memória.
- Só concluir depois da imagem pronta e de todas as verificações. Testes simulados
  da infraestrutura não substituem este ensaio de orquestração.
