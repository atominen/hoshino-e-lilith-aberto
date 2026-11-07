# Minecraft: decidir a próxima ação pelo resultado observado

Autorização: continuar o teste da Lilith, corrigindo até executar a progressão
real; alvo humano atual1.16.5Fabric,37837. Execução direta na instalação atual,
sem outro ambiente, modelos, privilégios ou ações de jogo pelo Codex.

## Diagnóstico e escolha

O plano fixo antecipa recursos ainda não observados. O9B com raciocínio levou
200s em uma tentativa e atingiu300s em outra; o7B respondeu17s, mas também
errou dependências. Aumentar esforço não corrigiu a interface de decisão.
Será usado o executor existente para escolher **uma ação**, receber seu recibo
e decidir novamente. Não há roteiro de mineração/fabricação escrito pelo Codex.

## Contrato

- Modo limitado a objetivos Minecraft com resultado verificável: itens nomeados,
  bancada colocada e peças de armadura equipadas. Um mapa explícito de nomes de
  equipamentos define critérios, não ações. Objetivos ainda não reconhecidos
  continuam no fluxo existente, com falha de planejamento bloqueando fallback.
- Objetivo e checkpoint na mesma SQLite de tarefas; recibos no job_bus e episódios
  existentes. Nenhum scheduler, daemon ou barramento adicional.
- Modelo escolhe ferramenta e argumentos; dispatcher, permissões, trava de ação,
  cancelamento, guardas de ameaça e de efeito incerto permanecem obrigatórios.
- Escolha e argumentos na mesma chamada nativa de ferramenta. A tentativa inicial
  de escolher por JSON e reformatar argumentos em outra inferência perdeu o alvo
  intermediário; não usar esse contrato em duas chamadas no ciclo observado.
- Somente capacidades Minecraft necessárias; não abrir outro servidor, baixar
  dados ou acessar ferramentas externas. Endereço explícito pertence ao humano.
- Próxima escolha usa estado e recibos reais, com contrato de argumentos completo,
  sem cadeia de pensamento ou identidade inteira duplicada em cada chamada.
- Conclusão só por inventário/equipamento e recibos de fabricação/colocação;
  texto do modelo ou uma mera conexão não satisfaz um pedido de ferramentas.
- Limite finito existente e parada por falta de progresso/efeito incerto. Estado
  persistido antes/depois das ações; nunca repetir ação cujo desfecho seja incerto.
- Comentários breves do modelo são separados dos recibos automáticos da aplicação.
  Ensaio continua synthetic_test, sem aprendizado de história humana ou voz paga.
- Integração reversível: módulo/caminho específico, esquema aditivo sem apagar
  dados; código anterior ignora checkpoint. Somente recarregar após sono e0leases.

## Execução e validação

- [x] RED critérios, conclusão falsa, origem/porta, checkpoint, retomada sem replay.
- [x] Núcleo do ciclo e integração pelo dispatcher existente, sem plano fixo.
- [x] RED→GREEN fechamento/cancelamento, falta de progresso e incerteza.
- [x] Testes focados e suíte inteira com inferências físicas paradas:96/96grupos,
  `/tmp/minecraft-observed-delivery-20261026.log`;18casos de integração incluindo
  valores canônicos de forno/equipamento.
- [ ] Retomar na37837 e verificar bancada/picareta; depois ferro/diamante por
  objetivos progressivos. Nenhuma aprovação de armadura sem quatro peças reais.
- [ ] Atualizar relatório, registrar intervenções e diferenças de capacidade.

## Revisão independente única

Revisor reportou5Important, nenhumCritical. Corrigidos com regressões RED→GREEN:
objeto adicional de diamantes não pode sumir do contrato; estado expõe destino e
vincula checkpoint/sessão, inclusive depois da trava; posições colocadas são
únicas e reconferidas no mundo; retomada explícita renova a tentativa sem limpar
incertezas/falhas; observação usa dispatcher e permissões atuais.

Complementos: um recibo não conta duas fabricações; mudança de posição sozinha
não libera pré-condição de ingredientes; alteração de sessão durante decisão
não executa argumentos antigos; snapshot do bloco anterior é valor imutável.
23 casos do núcleo,126 de prontidão e18 da ponte verdes. Suíte final em
`/tmp/minecraft-observed-final-20261026.log`. Sem re-review nem aprovação física
antecipada. Modo limitado a metas nomeadas simples; combinações não cobertas
são recusadas, sem certificar uma fração do pedido.
