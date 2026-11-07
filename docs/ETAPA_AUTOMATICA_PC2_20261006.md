# Etapa automática e pacote de Alistair — 06/10/2026

## Concluído sem testes manuais do usuário

- Pesquisa de fontes públicas, com licença e origem preservadas:
  [AIRI](https://github.com/moeru-ai/airi) e
  [Neuro SDK](https://github.com/VedalAI/neuro-sdk). A pesquisa da Shogun chegou
  ao [criador Bruno Miyauti](https://linktr.ee/miiyauti), mas não identificou
  código oficial verificável para reaproveitar. Veja [origens exatas](../third_party/ORIGENS.md).
- Fila adaptada do AIRI no áudio compartilhado: prioriza transcrição solicitada
  pelo usuário, mantém FIFO entre prioridades iguais, limita pendentes, remove
  cancelados imediatamente e envelhece pedidos para evitar inanição. ASR/TTS
  continuam com uma execução ativa e sem duplicação de modelos por entidade.
- Contratos adaptados da janela de ações do Neuro SDK **em Alistair**: construção,
  registro e encerramento; parâmetros desconhecidos, entidade inválida e booleano
  em texto/número são rejeitados antes do efeito. Ferramentas além de quatro por
  rodada recebem recusa explícita, não são ignoradas silenciosamente.
- Recibos locais duráveis de ações mutáveis: id repetido com mesmos argumentos
  reutiliza resultado; argumentos diferentes falham. Se a aplicação cair entre
  o efeito e o recibo final, a ação fica incerta e não se repete automaticamente.
  Isso não promete transação atômica entre bancos diferentes nem resolução
  automática de efeitos incertos. Consultas de estado/histórico permanecem atuais.
- Cliente LAN opcional e executor portátil, exclusivos do LLM de Alistair.
  A mente/standby, correio e ferramentas continuam no PC principal. Contextos
  selecionados são enviados para inferência quando você habilitar esse backend;
  bancos e arquivos privados de identidade não são exportados como instalação.
- Autenticação HMAC, IPs LAN literais permitidos, proteção contra replay, corpos
  limitados e sem proxies. Não há endpoint de shell, arquivos, ferramentas ou
  upload. HTTP não cifra o conteúdo: usar apenas LAN confiável, sem expor portas.
- Um pedido ambíguo é consultado/cancelado pelo mesmo id. Não aciona uma cópia
  local enquanto o término remoto for incerto. Falha/cancelamento confirmados
  permitem fallback local. O cache remoto é em RAM e limitado: queda/expiração
  exigem revisão, não criam sucesso fictício.
- Motor 4B e bibliotecas CPU incluídos por lista permitida, sem ambientes Python
  pesados, GPU, históricos, bancos mentais, `.env`, chave Discord ou chave LAN.
  A chave é gerada depois, durante o pareamento no segundo PC.

## Pacote para transferir

[alistair_pc2.tar](../pacotes/alistair_pc2.tar), **2.565.345.280 bytes** (~2,56 GB;
2,39 GiB), mais [SHA-256](../pacotes/alistair_pc2.tar.sha256).
A [pasta pronta](../pacotes/alistair_pc2) também pode ser copiada diretamente.
O tar não é comprimido, para economizar CPU de extração no Athlon; não requer
download do modelo nem instalação de Ollama. Basta um Mint compatível com as
bibliotecas básicas verificadas e Python 3.10+.

Instruções completas em [LEIA-ME do pacote](../pacotes/alistair_pc2/LEIA-ME.md).
O início usa um scope do usuário: RAM até 7 GiB, CPU até 150%, Nice 10 e swap
do scope desativado. Duas threads, um pedido ativo e duas vagas pendentes;
contexto até 4096 e saída até 768 tokens, sem corte silencioso.
Se os limites não estiverem disponíveis, o atalho não inicia sem proteção.
Esses limites contêm consumo, não garantem fluidez do YouTube.

O PC principal permanece com `compartilhado/config/alistair_pc2.json` desativado.
O pareamento/teste posterior usa `scripts/conectar_alistair_pc2.py`; habilitar é
uma opção explícita depois da medição. O planejador geral de quatro destinos
continua consultivo; cloud não foi contratada, ligada nem conectada.

## Verificação efetuada

**30 grupos da suíte passaram**, com **34 regressões novas** desta etapa.
Cobertura: prioridade, cancelamento, concorrência, contratos, recibos duráveis,
assinatura/replay, limites, RAM desconhecida, fila cheia, falhas, pedidos ambíguos,
idempotência, recuperação e exportação sem arquivos privados. Estado de teste
isolado: sem modelos reais, dispositivos ou mensagens nas mentes na suíte.
Sintaxe de dezesseis arquivos Python e três scripts shell também foi conferida.

Os blobs do modelo foram conferidos contra seus digests originais, e todos os
arquivos do tar contra o manifesto. O pacote real foi ensaiado **no PC principal**:
motor próprio em 11438, duas threads CPU, contexto isolado de 1024, cálculo 14 + 7
respondido como 21 em 8,52 s incluindo fila/carga. Daemon encerrou e liberou a porta.
Esse tempo **não é benchmark do Athlon**, não mede contexto máximo nem seu HD.
Foi criada zero mensagem nas mentes. Licenças e 58 arquivos constam do manifesto.

A central foi retomada com o código novo e Alistair ativo, com residência CPU
confirmada. Hoshino/Lilith não foram acordadas para testes. Veja o
[registro factual](verificacao_pc2_20261006.json).

## Próxima fase — depende de você e do segundo PC

1. Conferir a versão do Mint e os IPs LAN dos dois PCs; transferir/extrair o pacote.
2. Rodar a verificação/início no Athlon, conferir limites e parear com o principal.
3. Medir inferência fria/quente, primeiro sem YouTube e depois reproduzindo vídeo;
   conferir RAM, responsividade e encerramento. Habilitar o backend somente então.
4. Testar microfone real: frase curta → rascunho correto → enviar; depois avaliar
   audição/naturalidade de Hoshino e Lilith e cancelamento durante gravação/fala.
5. Testar Discord (mensagens rápidas de pessoas diferentes, fila, voz) e Minecraft
   LAN (entrar no mundo, ações e reconexão). Os testes offline desses adaptadores
   passaram; não substituem servidor/canal/mundo reais.
6. Executar os cenários completos dos rascunhos no dia a dia. Personalidade
   evolutiva, conversa prolongada, jogo e geração de imagem juntos não receberam
   aprovação geral por esta etapa limitada.

Não há necessidade de teste manual antes desta entrega. Para prosseguir na fase
do PC2, faltam a versão exata do Mint e os IPs LAN; nenhum endereço foi inventado.
