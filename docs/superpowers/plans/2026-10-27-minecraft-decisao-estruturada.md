# Decisão Minecraft estruturada e contexto conciso

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Implementação direta já autorizada pelo humano; sem nova rodada de perguntas.

**Goal:** reduzir escolhas fora das possibilidades observadas sem escrever decisões de jogo pelo condutor.

**Architecture:** mesmo9B, tarefa,RM,dispatcher e verificador. Uma seleção estruturada deID+comentário curto destaca a meta autoral e remove repetições de faltas em cada transição. `outra` preserva o catálogo nativo completo; respostas nativas antigas continuam sujeitas às validações existentes.

**Tech Stack:** Python, Ollama/llama.cpp local, Mineflayer existente.

**Spec:** pedido humano de continuar/pesquisar soluções externas e `docs/MINECRAFT_REFERENCIAS_E_RETOMADA_CODEX_20261027.md`.

## Global Constraints

- Hoshino/Lilith somente7B/9B, mínimo7B; Alistair4B e seu protocolo preservados.
- Não mudar parâmetros ativos/modelos/identidades/memórias; entidades dormindo e0jobs/leases antes de editar.
- Nenhuma ação de jogo do condutor. Incerteza não autoriza replay.
- Toda aprovação física depende de recibo+estado, não da escolha ou comentário.

## Abordagens e decisão do implementador

Mais anotações no prompt já falharam nesta amostra. Habilidades compostas como
noMindcraft são uma opção posterior com maior escopo. Escolho primeiro separar
seleção estruturada de ação e manter feedback conciso: o protótipo real escolheu
aproximar-se da bancada para sua própria meta de forno, enquanto o anterior
tentou coleta inválida. Amostra pequena; não prova autonomia. Custo se errado:
persistência de escolhas irrelevantes apesar de um formato válido.

## Review Focus

- ID inexistente/argumentos injetados/comentário inválido: recusa antes do efeito.
- Compactação não altera fatos, receitas, inventário ou referência de recibo.
- `outra` continua permitindo pesquisa, receitas e ferramentas livres existentes.
- Resposta nativa antiga mantém argumentos e verificação; não há retry oculto.
- Falha do modelo/efeito incerto conserva pendência e interrompe como antes.

## Task1 — representação e integração

- [x] RED: decisão JSON real chega à ação exata; formato oferece somenteIDs observados+outra.
- [x] RED: compactação preserva meta, fatos, receitas e recibos, sem repetir faltas em cada transição nem mutar entrada.
- [x] RED: rejeitarID inventado, campos extras e nota longa antes de qualquer ferramenta; catálogo livre preservado.
- [x] Implementar helpers puros em`app/core/minecraft_cognition.py` e integrar em`app/main.py`.
- [x] Focados67/148 e suíte geral96/96, exit0, `/tmp/minecraft-structured-final-suite-20261027.log`.
- [x] Revisão fresca Claude16377302 e três correções importantes RED→GREEN: autoria sem meta, protocolo do catálogo e preservação da nota/plano anterior. Commit próprio preparado.

## Task2 — mundo e documentação

- [ ] Conferir novamente sono/jobs/leases; única retomada identificada da tarefa existente.
- [ ] Reconectar, comparar estado ao snapshot anterior, registrar revisão atribuída de sessão e ajuda humana confirmada.
- [ ] Observar forno/fundição e registrar resultado real; não fabricar pelo condutor.
- [ ] Atualizar relatório, entradaCLAUDE e commits sem misturar alterações6B/SNIPER.

## Incremento após ensaio: recursos e chat pedido pelo humano

O bloqueio real posterior não foi uma decisão de jogo: perfil candidato32 foi
guardado antes da admissão, e o fallback20 admitido com métrica incerta não foi
guardado. A fila passou a reservar um upgrade que nunca ocorreu. Sono/saída
real/0jobs/leases conferidos antes desta edição. Dois testes RED→GREEN cobrem
cache de candidato recusado e manutenção do fallback realmente admitido.

O humano pediu ler/responder ao chat doMinecraft quando não atrapalhar. Usar
mensagens reais dos jogadores, buffer limitado por sessão, excluir eco próprio
e mensagens de sistema. Apresentar uma vez no ciclo existente; responder pelo
catálogo nativo já existente, preservando objetivo/recibos e sem inferência
concorrente. Conversa aceita não fabrica progresso nem consome o contador de
ausência de efeito do trabalho. Não há mensagens artificiais do condutor.

- [x] Testar buffer, isolamento de sessão/eco, contexto sem replay, disponibilidade
  de resposta e preservação do objetivo durante chat.
- [x] Revisão fresca do incremento e correções RED→GREEN; focados105/73/149/44 e suíte final96/96, exit0.
- [ ] Recarga cooperativa e verificação de chat real/forno no mundo.

### Ledger do incremento

- RED→GREEN: candidatoGPU recusado não vira perfil quente e fallback admitido fica registrado;104casos verdes.
- Real: o segundo pedido ainda bloqueou com perfil32 efetivamente carregado. Nova causa demonstrada: margem real após a carga. RED→GREEN permite só descida de degrau medido sob pressão conhecida;105casos. Duas chamadas reais finais passaram em31camadas, sem mudar pesos/contexto/margem.
- Chat RED→GREEN: buffer/sessão/eco, contexto e preservação de tarefa; revisão fresca Claude dc790f8c encontrou fronteiras adicionais, corrigidas num passe: UTF16/comandos, chat tipado, cursor/ordem/gap, contexto antigo, exceção de estagnação só por resposta nova e monitor de trabalho sem passos de conversa.73núcleo/149integração/44ponte verdes.
- Final: Ruling: manter pausa para envio de chat incerto — não esconder pendência nem arriscar repetição; custo: uma falha de transporte lateral também pode pausar o trabalho.
- Final: minor (deferred): novas conversas contínuas ou entre dois bots ainda podem consumir turnos; só contexto novo recebe isenção de estagnação e o teto global permanece. Orçamento social separado não implementado.
- Ruling: permitir descida de degrauGPU já medido quando a pressão conhecida invalida o perfil quente — evita espera artificial sem relaxar margem/qualidade; custo: eventual recarga e latência de CPU maior. Métrica incerta não autoriza descida presumida.
- Task incremento: final após revisão105executores/73núcleo/149integração/44ponte e96/96grupos, exit0 (`/tmp/minecraft-resource-chat-final-suite-20261027.log`). Real: duas inferências em31camadas,0leases ao sair. Leitura/resposta real de jogador ainda não aprovada por esses testes.

## Ledger

- Protótipo temporário sem efeitos: antes abriu catálogo e pediu20iron_ore sem picareta apta. Atual`2f5b57a` pediuID não oferecido. Contexto conciso+JSON escolheu aproximar bancada observada,86,33s; nenhuma ação real foi executada.
- A segunda medição inicial nem chegou ao modelo porVRAM. Repetição de ensaio explicitamente conservou perfil20camadas já residente e conferido; sem configuração de produção alterada. Isso não é correção declarada doRM.
- Ruling: manter compatibilidade com retorno nativo validado — não rejeitar uma operação concreta apenas por representação antiga; custo se errado: formato sozinho não impede todos os erros de escolha, por isso validação local permanece.
- Ruling: pesquisa/receitas via`outra` na seleção estruturada — reduz ruído sem remover capacidade; custo se errado: uma inferência extra para essas operações.
- Final: Ruling: compatibilidade nativa permanece com guardas físicos/dispatcher existentes; garantia deenum só vale para a seleçãoJSON — custo: escolhas nativas inadequadas podem continuar sendo recusadas antes do efeito.
- Final: minor (deferred): nota estruturada240caracteres reduz espaço do plano nesse ramo; plano nativo anterior preservado.
- Final: minor (deferred): hipótese de executor sem ferramentas em ciclo fixado; catálogo7B/9B atual observado oferece ferramentas, qualquer novo executor precisa de contrato próprio.
- Ensaio integrado congelado posterior escolheu carvão em200,21s, sem executar. Formato válido não resolveu sozinho o planejamento. Não contar o protótipo favorável como garantia.
