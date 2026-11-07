# Painel, senha local e limpeza de testes — 16/10/2026

Atualização posterior: em19/10 o botão existente **Apagar todas** passou a
abranger memória, conhecimento e chat da entidade selecionada, com prévia
explícita e backup. [Escopo e preservação atuais](CENTRAL_OFICIAL_20261019.md).
Os relatos de limpezas abaixo continuam históricos; não significam que esta
atualização executou outra limpeza ou redefiniu a senha do usuário.

Solicitação humana: fixar a Central no painel inferior, investigar a senha de exclusão e apagar as memórias de testes. Em duas confirmações posteriores o usuário autorizou **memórias e conversas das três entidades** e **redefinição somente da senha local**. A senha informada não foi repetida, testada em comandos, incorporada ao código ou registrada nos relatórios.

## Ícone fixado

O lançador instalado `hoshino-e-lilith.desktop` já era reconhecido pelo Cinnamon, mas não constava nos favoritos da instância 2 de `grouped-window-list@cinnamon.org`. O ícone da janela em execução não equivalia a um ícone fixado.

- Guardada cópia da configuração anterior em `compartilhado/runtime/ensaios/painel-limpeza-20261016/painel-antes.json`.
- Acrescentado somente o lançador da Central. Os nove atalhos anteriores mantiveram sua ordem.
- A edição do arquivo não atualizou imediatamente o estado em memória do painel. Aplicada então a operação nativa `pinnedFavorites.addFavorite` da instância identificada, sem reiniciar Cinnamon ou alterar outros applets.
- Consultas ao Cinnamon em execução confirmaram `pinned=true`, aplicativo reconhecido e favorito resolvido. O `.desktop` passou por `desktop-file-validate`.

Isto fixa o lançador; não habilita inicialização automática nem acorda entidades. Aparência/posição visual final permanece disponível para avaliação do usuário.

## Senha

A configuração antiga existia, com hash scrypt e permissão 0600. O formulário atual aceita 8–200 caracteres; a sequência de seis dígitos mencionada pelo usuário não poderia ser cadastrada por esse formulário. **Não se demonstrou que o hash anterior correspondia a essa sequência**, nem se afirmou que um reinício mudou a senha.

Após autorização explícita, retirados apenas `password_hash`, `salt` e `algorithm` da configuração local usando o escritor atômico/revisionado existente. Ele guardou a configuração anterior em `compartilhado/config/central_security.json.backup-*`, com permissão 0600. Nenhuma senha nova foi inventada ou registrada. A API real confirmou `configured=false` após a reabertura.

O usuário deve cadastrar uma nova senha de pelo menos oito caracteres em **Memória → Definir / alterar senha**, usando o campo oculto. Enquanto não a cadastrar, o botão de exclusão continua recusando exclusões; autenticação, scrypt e limite de tentativas não foram relaxados. Não se alteraram senhas do Linux, GitHub ou serviços.

## Limpeza autorizada, recuperável

Antes da operação: três entidades dormindo, nenhum job ativo, nenhuma reserva de recurso, laboratório sem worker/job/sessão ativa e nenhum pedido de despertar pendente. Central PID 26214 encerrou pelo endpoint autenticado existente; conferidos recibo da geração correspondente, `complete`, ausência de blockers, saída real do processo e porta livre.

Durante a operação administrativa local: lock exclusivo do supervisor e os três `entity.lock`, usando a verificação ociosa existente. **Não foi adicionado endpoint para ignorar senha.** A autorização humana desta operação não desabilita a proteção da interface.

Backup completo das fontes SQLite, índices vetoriais e estados transitórios existentes antes da primeira exclusão. Backups SQLite passaram por `integrity_check`. Utilizado `core.memory_maintenance` para memórias/vetores; tabelas adicionais de conhecimento, relações de teste, atividades, emoções e tarefas antigas foram explicitamente delimitadas. Não foi usado o reset genérico que apaga todas as tabelas, pois ele também apagaria identidade e recibos.

| Entidade | Memórias/episódios/propriedades/turnos removidos | Outros registros dinâmicos de teste | Cópias locais de mensagens | Eventos antigos arquivados |
|---|---:|---:|---:|---:|
| Hoshino | 0 | 336 | 0 | 12057 |
| Lilith | 22 | 61 | 22 | 755 |
| Alistair | 18 | 0 | 0 | 536 |

Também removidos 22 registros vetoriais da Lilith e 224 envelopes de conversa do barramento compartilhado, com seus 108 vínculos de resposta, 115 chaves de notificação e três pedidos antigos de despertar. Presença e pedidos de sono foram preservados. As cópias locais e os envelopes podem representar a mesma interação; não somá-los como conversas distintas.

Eventos históricos podem conter entradas humanas e alimentar a consolidação diária. Por isso o histórico completo anterior foi **arquivado fora das fontes ativas**, e não apenas retirado da tela. Seus 13348 eventos técnicos permanecem nos backups; os recibos compartilhados, ações do Alistair, logs e relatórios não foram apagados. Estados transitórios de humor/atividade e marcadores de reflexão foram igualmente arquivados para não retomar a sessão de teste.

Preservados e conferidos por digest: arquivos de identidade, manifestos e configurações, além das tabelas existentes `traits`, `tastes`, `self_model_versions`, `skill_profile`, `alistair_actions` e `alistair_watched_jobs`. Relações com pessoas dos testes foram removidas; traços canônicos não. Modelos, adaptadores, datasets, arquivos do usuário e relatórios não foram alterados. Nenhum treino, professor, inferência, captura ambiental ou ElevenLabs foi executado.

Backup principal, privado e ignorado pelo Git:

`compartilhado/runtime/ensaios/painel-limpeza-20261016/backup-limpeza/`

Contém bancos anteriores, vetores, estados arquivados, plano com contagens/digests e `resultado.json` com `verified=true`. `memory_maintenance` também conservou seus backups próprios em `entidades/<entidade>/runtime/memory-backups/manual-*`. Backups e logs conservam cópias; **isto não é apagamento forense de todas as evidências**. Restauração deve ocorrer com entidades paradas e reconciliação dos bancos relacionados, não por substituição de arquivos durante execução.

## Verificação e retorno

- Ensaio administrativo em quatro testes isolados: limpeza completa/backup/preservação, recusa de entidade ativa, fonte alterada e recusa de link/falha de backup. **4/4** no desfecho. As primeiras execuções falharam por caminho de fixture e por asserção incorreta sobre o formato de `presence()`; não tocaram dados reais.
- Três regressões existentes de senha/limite de tentativas/preservação na exclusão: **3/3**.
- Wrapper dos contratos Qt existente: **passou**. O transporte é controlado; não é avaliação humana da janela.
- Operação real: processo **exit 0**, resultado verificado, bancos ativos com `quick_check=ok`, backups conferidos. Alvos SQL zerados e linhas de identidade/recibos preservadas.
- Reabertura única da mesma Central, PID **49772**, porta 8769, sem `--entity`, sem despertar ninguém. API confirmou três entidades dormindo, zero reservas, conversas locais/privadas vazias e prévias de memória zeradas nas três entidades.
- `git diff --check` sem erros. Código funcional do app não precisou ser alterado nesta rodada; alterações preexistentes do checkout foram preservadas. Não se alega nova execução da suíte completa: a rodada foi administrativa, com testes focados e verificação real.

Logs: `/tmp/painel-limpeza-fixtures-20261016.log` (primeira falha), `/tmp/painel-limpeza-fixtures-final-20261016.log`, `/tmp/painel-limpeza-qt-20261016.log`, `/tmp/painel-limpeza-real-20261016.log`; cópias no diretório do ensaio. Script único e testes isolados também estão nesse diretório, sem importação pelo app, sem agendamento e com recusa de repetição após a marca de início.

Pendências humanas: cadastrar a nova senha em campo oculto, conferir o ícone no painel e começar conversas novas. O cliente já existente detecta a nova geração da Central e limpa sua visualização; se não atualizar, reabrir pelo ícone. Não foram fabricadas conversas para verificar personalidade.

## Correção do formulário de cadastro — 19/10/2026

O usuário relatou pedidos repetidos para definir uma senha. Na verificação atual,
o arquivo de segurança ainda era o objeto vazio resultante da redefinição anterior,
com permissão 0600 e data de modificação de 16/10; a API autenticada confirmou
`configured=false`. Não se inspecionou a senha que o usuário tentou digitar nem
se demonstrou qual validação específica recusou aquela tentativa.

Havia um problema no fluxo da janela nativa: senha e confirmação eram pedidas em
diálogos sucessivos que fechavam antes do resultado. Em caso de recusa, o erro
ficava no rodapé da Central, separado do aviso de que faltava cadastrar a senha.
Assim, uma nova tentativa de exclusão voltava a pedir o cadastro, sem um
formulário persistente para corrigir o erro. Uma senha com menos de oito
caracteres reproduz essa condição em fixture; não foi usada senha real no ensaio.

O cadastro agora usa uma única janela, com campos ocultos e erro dentro dela.
Comprimento de 8–200 caracteres e confirmação são validados antes do envio;
alteração de senha existente exige a atual. O formulário permanece aberto em
caso de recusa, impede diálogos/envios duplicados e só anuncia sucesso após
resposta de gravação **e nova consulta** com `configured=true`. Resultado não
confirmado oferece conferência somente leitura, sem repetir o cadastro sozinho.
Troca de geração do backend cancela a janela antiga; fechar limpa os campos.
Salvar senha não aciona exclusão de memória.

O backend de segurança não precisou ser alterado: scrypt, permissão 0600,
verificação da senha atual, limite de tentativas e proteções da exclusão foram
preservados. Nenhuma senha foi definida, removida ou redefinida pelo agente
nesta correção. Nenhuma memória foi apagada.

Verificação pelo runner isolado: 41 testes de refinamento, 57 de Central,
20 de isolamento e um de browser passaram (**119 testes de topo**). O grupo
de refinamento inclui **79 contratos Qt** com transporte simulado, cobrindo
senha curta, confirmação diferente, senha atual ausente, erro do servidor,
gravação não confirmada, conferência sem novo envio, cancelamento e mudança de
backend. O ensaio de persistência abre outro Control sobre o mesmo arquivo
temporário e verifica a senha; não usa configuração real. Não é suíte completa
nem confirmação de que o usuário já cadastrou sua nova senha.

Após aprovação humana para reabrir e descartar rascunhos/áudio não enviados,
confirmados três estados de sono, nenhum job/lease ativo e laboratório sem sessão
ativa. Supervisor anterior 112383 encerrou pelo endpoint autenticado, com recibo
da geração correta e saída confirmada. A janela descartável exata 112392 foi
encerrada; seu listener próprio 112419 terminou por EOF. Nenhum processo foi
selecionado por nome ou porta, nem houve SIGKILL. Após confirmar porta livre,
reaberta a mesma aplicação sem `--entity`: supervisor 115165, janela 115169.
A configuração de segurança foi preservada byte a byte durante a troca.

Logs locais: `/tmp/central-senha-20261019-*.log` e
`compartilhado/runtime/launcher/central-senha-reload-20261019.log`.
O usuário pode cadastrar em **Memória → Definir / alterar senha**, sem enviar a
senha pelo chat. A correção é do cadastro; não reduz o mínimo de oito caracteres.
