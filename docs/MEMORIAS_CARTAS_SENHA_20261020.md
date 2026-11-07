# Memórias, importância dos cartões e senha — 20/10/2026

## Abas atuais

- **Memórias** substitui Conhecimento: cartões estruturados por entidade e
  oficina de lógica, agora dentro da área protegida.
- **Memória do chat** substitui Memória: histórico próprio, episódios, turnos
  e resumos de conversa. Não é um atalho ao inspetor de conhecimento. O histórico
  bruto é somente leitura nessa tela; a limpeza completa permanece no botão
  existente, com prévia, senha, backup e todas as entidades dormindo.

Os nomes foram atualizados tanto na Central nativa quanto no cliente de
navegador. Relatórios anteriores mantêm os nomes que existiam naquelas datas.

## Importância e apresentação

Ordem: **Ferro → Ouro → Diamante → Platina**. Há seletor e aplicação explícita
por cartão; mais importantes aparecem primeiro. Cada nível tem borda/destaque
próprio, com transição breve de brilho/sombra ao passar o mouse ou dar foco.
Movimento reduzido desabilita a animação; não há loop ou renderização contínua.

Cartões anteriores são apresentados como Ferro sem regravar seu conteúdo.
Uma mudança explícita persiste em `memory_card_settings` no SQLite da própria
entidade, com revisão do cartão, exclusão de corrida com o runner, backup e
verificação física. A tabela contém apenas metadados de apresentação, não
uma segunda memória. Apagar o cartão pela UI também remove sua classificação;
a limpeza completa inclui esses metadados.

Importância é organização/destaque **definido pelo usuário**. Não altera a
confiança/veracidade registrada, personalidade, pesos dos modelos, autorização
de ações, treino ou pesos de recuperação do LLM. Platina não torna um cartão
imune a exclusão explícita. Edição continua exigindo a entidade dormindo.

## Senha

- Usa a **mesma senha local já configurada**, sem redefini-la nesta rodada.
- Memórias inicia bloqueada; nada do cartão é carregado antes do desbloqueio.
- Backend verifica senha e emite autorização aleatória, somente em RAM, por
  entidade e por até cinco minutos. Senha/autorização não vão em URL nem em
  armazenamento persistente do cliente. O servidor guarda apenas o hash da
  autorização temporária e a revisão da configuração de senha.
- Token da Central sozinho não permite ler/editar cartões, diagramas ou o
  inspetor semântico legado: essas rotas exigem autorização adicional no header
  `X-Memory-Access`. Não é apenas um bloqueio visual.
- Sair da aba, trocar entidade, minimizar a janela nativa, encerrar normalmente,
  expirar o prazo ou mudar senha exige novo desbloqueio. O navegador também
  bloqueia ao ficar oculto. Reiniciar o backend invalida as autorizações.
- Bloquear limpa os cartões, diagramas e diálogos locais. Respostas atrasadas
  não repovoam a área bloqueada. **Edições locais não salvas são descartadas**;
  nenhuma gravação mutável é repetida automaticamente.
- Exclusão mantém sua confirmação e senha próprias. A aba Memória do chat
  consulta apenas a projeção de conversa; os registros estruturados foram
  retirados dessa consulta para evitar contornar a nova proteção.

É proteção de acesso pela Central, não criptografia dos SQLite/backups nem
substituto da senha/bloqueio do sistema operacional. Conversas continuam visíveis
nos chats autorizados e podem conter o que foi dito; não se promete ocultar
toda informação pessoal existente no aplicativo ou nos arquivos.

## Apagamento completo: confirmação do comportamento existente

**Não é um retorno integral ao padrão. Nenhum apagamento real foi executado.**

- Gostos aprendidos em `tastes` e traços em `traits` são **preservados**.
- Preferências internalizadas por `learn_preference`, em
  `identity/self_model.json → personality.preferences`, são **preservadas**,
  assim como identidade, personalidade e versões existentes.
- `emotion_log` é apagado, mas `emocoes` e `humor` no estado mental são
  **preservados**; emoções seguem seu decaimento normal, não um reset forçado.
- Memórias/conhecimento, pessoas/relações aprendidas, conversas e tarefas do
  escopo escolhido são removidos conforme a prévia existente, com backup.
- Modelos/treinos, configurações fundamentais, habilidades, auditoria técnica
  e recibos que impedem replay continuam preservados.

Esta rodada esclareceu o aviso/resultado da limpeza e adicionou os metadados
dos novos cartões ao escopo, **sem mudar a política de gostos/preferências/
emoções nem solicitar uma limpeza**. Qualquer reset adicional exige novo pedido.

## Evidência

- Suíte oficial: **79/79 grupos offline aprovados** em
  `/tmp/memorias-cartas-oficiais-20261020.log`.
- Contratos de senha/escopo/expiração/revogação/HTTP, importância persistente,
  separação entre entidades e diagnóstico do reset em
  `/tmp/memorias-cartas-contratos-20261020.log`.
- Qt offscreen: bloqueio inicial, navegação, expiração, respostas atrasadas,
  senha oculta, níveis/hover e movimento reduzido; navegador: navegação protegida,
  header de acesso, mudança de nível, hover e bloqueio. Logs:
  `/tmp/memorias-cartas-refinamento-20261020.log`,
  `/tmp/memorias-cartas-browser-20261020.log` e
  `/tmp/memorias-cartas-qa-20261020.log`.
- Aparência inspecionada em
  `/tmp/memorias-cartas-qa-20261020/memorias-cartas-fixture.png`, inteiramente
  fictícia. Não comprova sessão desktop/hardware/conversa real.

Fontes instaladas para o próximo início da Central/backend. Não se iniciaram
entidades, captura de áudio, professor, treino, novos modelos ou serviços em
produção; memórias/configurações reais não foram alteradas. Nenhuma publicação
ou merge no GitHub foi feito por esta solicitação.
