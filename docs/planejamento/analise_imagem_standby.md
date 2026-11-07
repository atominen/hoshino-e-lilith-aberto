# Análise do rascunho de imagem e standby — 5 de outubro de 2026

Análise histórica; decisões posteriores e execução integrada estão na
[entrega de 06/10](../ENTREGA_20261006.md). Standby agora é uma função do Alistair,
não um quarto modelo nem uma identidade emprestada da Hoshino/Lilith.

`plano_hoshino_imagem_standby.txt` foi preservado como proposta do usuário.
A leitura complementa a reorganização; não executa automaticamente as dez fases
de implementação contidas no documento.

## Compatibilidade com a organização

Pesos e caches ficam em `compartilhado/modelos`, workers em `app/tools` e
executáveis em `compartilhado/servicos`. A GPU usa uma trava comum; a voz local
roda em CPU. Lilith agora é uma entidade independente. O standby proposto é
uma função auxiliar da entidade que iniciou o trabalho, sem identidade própria.

## Diferenças em relação ao código inspecionado

Na revisão final, o código já havia recebido uma atualização para FLUX.2 klein
4B Q6_K, com diffusion/encoder/VAE separados. Essa atualização foi preservada;
a reorganização ajustou somente seus caminhos. Não é o backend Qwen-Image
proposto no rascunho. Arquivos de benchmark não comprovam execução integrada.

O arquivo `entidades/hoshino/config/hoshino_v32.env` agora está alinhado ao
backend FLUX.2 (modelo, quatro steps, CFG 1, sampler Euler e descarregamento
entre jobs). Isso corrige a divergência de presets; a geração real ainda precisa
ser medida no equipamento para validar desempenho e qualidade.

O gerador atual aceita 1–60 steps e dimensões de 512–1536, com padrão de quatro
steps. Os presets do rascunho precisam ser calibrados para o backend escolhido;
não devem ser aplicados automaticamente ao FLUX.

Jobs ficam em um dicionário Python. Fila, parâmetros, eventos, tentativas e
resultado precisam persistir antes do handoff, para sobreviver a reinícios.
O subprocesso aguarda o término; progresso/ETA exigem leitura incremental de logs.

## Ajustes necessários no plano

1. O benchmark relatado de 319 segundos equivale a 5min19, acima de 4min30.
   Reduzir steps pode ajudar, mas condicionamento/decode têm custo próprio.
   A janela continua sendo uma meta até medir cada preset no equipamento.
2. Os nomes, versões e alegações de qualidade dos modelos precisam de validação
   de proveniência e compatibilidade com o executável instalado antes da adoção.
3. Pesos na RAM não eliminam VRAM para buffers. Medir RAM e pico de VRAM com
   interface, voz e standby ativos.
4. Código deve controlar progresso, conclusão e permissões de ferramentas.
   O modelo pequeno pode redigir respostas, mas não é fonte do estado.
5. O handoff precisa identificar entidade, conversa, job e revisão. Mensagens
   recebidas durante standby precisam persistir e não serem processadas duas vezes.
6. Incluir cancelamento, timeout, falha do standby e reinício do worker. Retomar
   o modelo principal deve funcionar mesmo sem o controlador auxiliar.
7. Conferir código de saída e imagem decodificável. Existência do arquivo sozinha
   pode indicar saída parcial ou antiga.

## Persistência e sequência

Presets pertencem ao módulo compartilhado. Estatísticas por modelo/backend/
hardware podem ser compartilhadas sem prompts. Prompts, referências, jobs,
mensagens pendentes e contratos de handoff pertencem ao runtime da entidade.
Imagens continuam nas entregas/runtime daquela entidade.

Primeiro integrar e validar o backend; depois jobs persistentes, progresso e
presets; em seguida standby e testes de cancelamento/retomada. Nenhum modelo
existente foi removido nesta reorganização.
