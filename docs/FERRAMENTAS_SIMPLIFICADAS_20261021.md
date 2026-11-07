# Ferramentas por capacidade — 21/10/2026

A aba da Central nativa e do navegador deixa de apresentar uma chave para cada
função técnica. Agora mostra apenas as capacidades disponíveis para a entidade
selecionada, com nomes e explicações legíveis:

| Controle | Escopo |
|---|---|
| Discord | Integração inteira: contatos, entrada, saída, abertura e consultas |
| Minecraft | Conexão e comandos da ponte, incluindo aliases de inicialização |
| Gerar imagens | Geração e funções do gerador existente |
| Ouvir o ambiente | Canais de escuta e microfone contínuo/detecção |
| Ler arquivos | Leitura, listagem e busca nas ferramentas de arquivos |
| Escrever arquivos | Escrita, criação de pastas, importação e entrega de arquivos |
| Internet e navegador | Pesquisa, páginas e navegação controlada |
| Controlar o computador | Tela, janelas, aplicativos, mouse e teclado |
| Executar comandos e código | Terminal e execução na oficina/laboratório existente |
| Jogar xadrez | Partidas e consultas do xadrez existente |

Hoshino/Lilith têm os dez controles. Alistair só recebe controles aplicáveis ao
seu catálogo atual, mais o controle de detecção de áudio da Central; não ganha
ferramentas novas por esta mudança. Não há chave de memória, identidade,
personalidade, relações ou conversa local. Voz de saída e microfone por comando
continuam na aba Áudio, sem serem confundidos com escuta do ambiente.

## Efeito e compatibilidade

- Política no mesmo `interface.json`, por entidade, e aplicada no dispatcher.
  `workspace` é filtrado e validado por operação: bloquear escrita não bloqueia
  leitura, e vice-versa. O schema original não é alterado globalmente.
- As restrições antigas por função são preservadas. Um controle parcialmente
  marcado indica restrições antigas naquele grupo. Somente grupos efetivamente
  alterados são enviados; permitir explicitamente um grupo remove as restrições
  antigas correspondentes, sem liberar outros grupos ou outras entidades.
- Memória sai dos controles visuais, mas não se apagam configurações antigas de
  autorização, bancos, conversas, cartões, gostos ou estados emocionais.
- Discord bloqueado não recebe novas entradas nem inicia novas entregas; a ponte
  se encerra cooperativamente entre entregas. Pendências e recibos são mantidos.
- Minecraft bloqueado não inicia ponte/conexão nem novos comandos. Rotinas de
  parada/desconexão de limpeza continuam possíveis internamente. Não fecha o
  jogo, mata processos ou cancela à força uma operação já iniciada.
- Escuta do ambiente bloqueada fecha capturas próprias contínuas; na Central a
  política é conferida também durante a captura. A origem e o modo ficam no job
  de áudio, e o backend verifica novamente antes de encaminhar sua transcrição.
  No global, áudio de detecção só é entregue às entidades acordadas que permitem
  essa capacidade. Mensagens digitadas e por comando mantêm o comportamento normal.
- Ativar uma permissão **não** inicia serviços, gravação, modelos ou treinamento.
  Chamadas já iniciadas conservam seus contratos e recibos; não há replay automático.
- São permissões das capacidades do app, não um sandbox do sistema operacional:
  código autorizado, outros aplicativos e ações humanas têm seus controles
  próprios. Autorizações e restrições de segurança anteriores continuam valendo.

Nenhuma configuração ativa foi alterada só para desenvolver ou testar a UI.
Os ensaios usam arquivos, canais, processos e transportes de fixtures, sem chamar
Discord/Minecraft reais, microfone, modelos, TTS ou professor.

Validação: **81/81 grupos oficiais offline** passaram; **11 contratos específicos**
de permissões e a rechecagem dos **41 testes de áudio** também passaram. Interface
nativa e navegador verificam grupos planos, salvar somente alterações e manter
comando/voz ao bloquear detecção. Logs temporários em
`/tmp/ferramentas-simples-*-20261021.log`; `git diff --check` sem problemas.
