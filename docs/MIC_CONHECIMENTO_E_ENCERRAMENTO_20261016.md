# Central — microfone, conhecimento e encerramento

Rodada de 16/10/2026, posterior a `CORRECOES_PRIMEIRO_USO_20261016.md`.

## Solicitação e preservação

Corrigir atalho global e envio automático da fala; revisar “apagar todas as memórias”; oferecer cartões de conhecimento separados; dar identidade ao app na barra de tarefas; confirmar e finalizar o projeto ao fechar a Central.

Não foram apagadas memórias, conversas, modelos ou datasets reais. Não houve inferência de LLM, treino, síntese paga, captura ambiental nem envio de mensagens artificiais às entidades nesta rodada. Testes de ASR/entrega usam transporte controlado; isso não substitui o teste de voz do usuário.

Snapshot anterior dos arquivos editados: `compartilhado/runtime/ensaios/central-mic-conhecimento-saida-20261016/codigo-antes.tgz`, sem bancos ou credenciais.

## 1. Atalho global

**Causa observada na configuração real:** combinação `Alt+W`, mas `hotkey_enabled=false`. A combinação estava salva sem ativar o listener. A janela estava usando o ambiente gráfico reduzido do iniciador, não o ambiente completo do terminal.

Mudanças:

- Escolher uma combinação marca a opção de habilitação; ainda é necessário salvar. Configuração desligada é anunciada explicitamente como DESLIGADO.
- Botão **Testar atalho · sem gravar**: dez segundos para confirmar pressionar/soltar, sem captura, ASR ou envio.
- Durante a escolha da tecla, o editor não abre o microfone por acidente.
- Listener continua sendo o `GlobalPTT` existente no ambiente principal, pertencente à janela. Não foi instalado daemon, criado outro mecanismo de captura ou gravado um histórico de teclas.

**Verificado fisicamente no X11:** cliente Qt real, com o mesmo ambiente reduzido usado pelo iniciador, recebeu `ready → press → release` para Alt+W. Repetição com foco em outra janela **do próprio ensaio** também passou: `central_not_focused=true`. O alvo foi conferido antes de injetar qualquer tecla; não se enviaram teclas a janelas do usuário. `recorded=false`, processo exit 0.

Os primeiros probes ficaram inconclusivos: a proteção recusou injeção sem foco confirmado; uma janela-alvo ainda não mapeada gerou BadMatch; e injeção de caractere por XSendEvent não reproduzia uma tecla física entre processos. O harness foi corrigido para aguardar o mapeamento, confirmar a janela-alvo e usar XTest. Não se alterou o listener para maquiar esses resultados.

Evidência final: `/tmp/central-atalho-interface-fora-foco-final-20261016.log`.

## 2. Fala → transcrição → envio

O usuário pediu envio automático tanto no modo aberto quanto ao pressionar para falar. A configuração real foi alterada, por revisão e backup existentes, para `auto_send=true` e `hotkey_enabled=true`, preservando Alt+W, entrada, saída, volume, limiares e modo manual previamente escolhido. O modo aberto continua sendo iniciado pelo usuário; habilitar o atalho não abre captura.

Correções no cliente:

- Envio automático usa **somente a transcrição**, não concatena e envia rascunhos digitados por engano.
- Entidade e sessão ficam vinculadas à origem da captura, inclusive se a seleção mudar enquanto o ASR termina. O backend continua validando a sessão atual e o job de origem.
- Testes de microfone/ASR nunca enviam conversa automaticamente.
- ASR ocupado guarda até quatro trechos nesta janela. Ao saturar, o microfone pausa com aviso; não há fila ilimitada nem descarte silencioso.
- Silêncio no fim de uma captura real não é enviado ao ASR automaticamente. A gravação de teste continua disponível mesmo sem fala.
- Resultado de envio incerto não causa replay: texto fica no rascunho com aviso; a deduplicação existente foi preservada.

**Comprovado em execução controlada:** transcrição exata, preservação do rascunho, destino/sessão de origem, testes sem envio, espera limitada e ausência de repetição automática. **Pendente:** usuário falar pela tecla física ou modo aberto na nova janela, com ASR real e resposta real da entidade. Não foi gravado o ambiente para fabricar essa aprovação.

## 3. Apagar memórias

Consultas reais, sem exclusão, confirmaram prévia funcional nas três entidades e senha já configurada. Contagens da consulta: Hoshino sem registros nessas categorias; Lilith 9 memórias, 1 propriedade e 8 episódios; Alistair 9 turnos próprios. Nenhum desses registros foi apagado neste ensaio.

Não foi reproduzido um defeito destrutivo no backend real. Foram corrigidos pontos do fluxo que podiam dar aparência de botão inoperante:

- Pré-requisitos, progresso e resultado ficam visíveis na área de memória.
- Se ativa, a entidade só recebe pedido de sono após confirmação; a interface espera processo, jobs e leases ficarem livres e então faz **nova prévia**.
- Senha inexistente, senha incorreta, falha de prévia ou exclusão incerta aparecem em aviso, não apenas no rodapé.
- Duas operações de exclusão não são disparadas pelo mesmo fluxo ao mesmo tempo.
- A interface só anuncia exclusão se o backend devolver `verified=true`; resultado incerto não é repetido.
- Continuam obrigatórios: senha, confirmação, alvo específico, fingerprint atual, entity.lock, backup e verificação SQL/vetor.

**Validado em bases isoladas:** excluir selecionadas/todas, backup, vetores reais temporários sem embeddings/download, proteção da outra entidade, erro de senha, alvo ocupado e falha sem falso sucesso. O botão não passou por exclusão em dados de produção, deliberadamente.

O contrato anterior permanece: identidade, relações/traços canônicos, recibos e histórico bruto/caixa postal não são apagados por esse botão. A prévia informa isso; conversas preservadas podem voltar ao contexto. Não se implementou nem executou um reset irrestrito disfarçado de correção.

## 4. Conhecimento em cartões

Nova área **Conhecimento**, separada do inspetor de memória, com busca, filtros e paginação. Cartões de pessoas, itens/assuntos, conceitos e procedimentos mostram os registros existentes, fonte, confiança, data, IDs e evidências disponíveis.

- Projeção somente leitura das tabelas `people`, `properties`, `memories` e `procedures` do SQLite da entidade selecionada.
- Não é outro banco, classificador LLM ou mecanismo de aprendizado. Não transforma automaticamente o histórico em fatos.
- IDs de pessoas diferentes não são fundidos por compartilharem nome. Referência legada apenas por nome é identificada como tal; autoria não é inventada.
- Hipótese e interpretação continuam rotuladas, não promovidas a fatos. Confiança 0 é preservada; ausência de confiança não vira certeza.
- Não lê diários ou histórico bruto. Não consulta o banco de outra entidade para preencher um cartão.
- Limite explícito de 300 registros recentes por tabela; 24 cartões por página. Ausência na consulta limitada não significa esquecimento ou inexistência.
- Trocar entidade limpa os cartões anteriores e descarta respostas de consultas antigas.

**Verificado no backend real após instalação:** 13 cartões retornados para Lilith, `read_only=true`. Não foi necessário mostrar conteúdo privado nos logs. **Verificado visualmente:** renderização Qt dos cartões de exemplo em `cartoes-ui-fixture.png`; a imagem está marcada como simulação, não memória real.

## 5. Ícone e fechamento

- SVG próprio com as três cores; ícone da janela, identidade Qt e desktop file `hoshino-e-lilith` alinhados.
- Atualizados o lançador do projeto, o atalho da área de trabalho e o menu instalado. Arquivos passaram por `desktop-file-validate`; cache do menu atualizado.
- **Observado no X11:** `WM_CLASS = "hoshino-e-lilith", "hoshino-e-lilith"`; renderização do ícone não nula. Aparência/pinagem no painel do usuário ainda requer reabrir a janela antiga.

Ao fechar a nova janela, ou usar Encerrar com segurança:

1. Pergunta com opção padrão de cancelar. Cancelar não para microfone nem backend.
2. Confirmar avisa que rascunhos/áudio ainda não enviados serão descartados; memórias e arquivos salvos são preservados.
3. Para captura/player/listener próprios e pede o encerramento cooperativo existente da Central e das entidades. O overlay pertencente à Central também é encerrado; novos orbes observam o estado de fechamento.
4. Mantém a janela até confirmar conclusão. Um recibo final do drain existente, vinculado à geração autenticada e ao PID/starttime, permite verificar a saída após o HTTP terminar. Falha de conexão, recibo velho/incompleto ou mudança de instância não significa sucesso.
5. Trabalho ativo/incerto mantém a janela para diagnóstico e mostra bloqueio, sem kill por nome/porta, replay ou remoção de proteções. Reavaliação só após novo pedido humano.

**Executado em ambiente isolado real:** subprocesso do supervisor + HTTP autenticado + drain + saída exit 0 + recibo `complete` sem blockers. Testes Qt cobrem cancelar, confirmar uma vez, recibo antigo, bloqueio e manutenção da janela sem falso sucesso.

Isso encerra o projeto, não o computador ou programas alheios. Serviços compartilhados, como daemons Ollama, conservam o contrato existente: modelos são descarregados, sem matar servidores arbitrários. A sessão física completa de fechamento pelo X da nova janela, com tarefas reais, continua sendo avaliação humana.

## Testes e instalação

- Regressões iniciais reproduziram envio indevido de rascunho junto à fala, perda do envio ao trocar seleção e falta de confirmação ao fechar.
- Primeiro conjunto completo: **73/74**. O teste novo de subprocesso tentou conexão não registrada no processo pai e foi corretamente bloqueado pelo guard offline. O teste passou a iniciar e acessar somente seu próprio servidor no filho, com rede restrita àquela porta; o guard não foi relaxado.
- Suíte oficial final: **74/74** (`/tmp/central-mic-conhecimento-oficiais-final-20261016.log`).
- Laboratório: **333/333**, sem professor ou treino reais (`/tmp/central-mic-conhecimento-laboratorio-20261016.log`).
- Contratos Qt: **66 testes** no subprocesso, cobrindo os fluxos novos; resultado final no log `/tmp/central-mic-conhecimento-qt-final-20261016.log`.
- `git diff --check` sem erros.

Backend anterior PID 6079 encerrou cooperativamente; saída e porta livre foram conferidas antes da nova Central PID 26214, na mesma porta 8769. Configuração aplicada pela API existente, com revisão e backup. As três entidades estavam dormindo e permaneceram dormindo; ninguém foi acordado para produzir resultados artificiais. Hashes dos três bancos mentais coincidiram antes/depois.

Evidência de instalação: `/tmp/central-mic-conhecimento-instalacao-20261016.jsonl`. Logs, falhas e snapshots ficam copiados no diretório de ensaio ignorado pelo Git. Não se copiou banco mental para o Git.

## Para usar

**Fechar a janela antiga e reabrir a Central pelo atalho existente.** A instância antiga mantém as classes antigas, mesmo com backend atualizado; ela não foi morta para preservar rascunhos do usuário.

Na nova janela: Alt+W já habilitado; botão de teste sem gravação disponível; envio automático da fala ligado. Para microfone aberto, escolher esse modo, salvar e iniciar a captura. A área Conhecimento é somente consulta. Não há áudio ElevenLabs adicional autorizado/consumido nesta rodada.

Ainda precisam de avaliação humana: fala real ponta a ponta em ambos os modos, comportamento sob áudio prolongado/saturação, cartões com o crescimento das memórias, exclusão de dados reais escolhidos pelo usuário e fechamento com tarefas reais em andamento.

## Arquivos desta rodada

Código: `app/ui/central_native.py`, `app/ui/native_panels.py`, `app/ui/overlay.py`, `app/core/central_control.py`, `app/core/shutdown.py`, `iniciar_entidades.py`. Ícone e lançador: `desktop/hoshino-e-lilith.svg`, `Hoshino e Lilith.desktop` e cópias instaladas na área de trabalho/menu. Regressões: `testes/native_central_contracts.py` e `testes/test_central_refinamento.py`.

As alterações anteriores do checkout foram preservadas. Não foi criado novo cérebro, scheduler, banco mental, seletor de modelos ou serviço permanente.
