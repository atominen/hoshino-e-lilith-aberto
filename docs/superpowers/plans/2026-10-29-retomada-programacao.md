# Retomada do desafio de programação — 29/10

Execução direta autorizada: ler material novo e continuar o desafio. **Decisão
humana posterior: terminar os ajustes e pausar para conferência; não retomar.** Papel
preservado do condutor: infraestrutura, contratos e avaliação; nunca escrever
o C++/shader/física da Lilith. Tarefa existente`ct-6499763ae6`, orçamento600.

## Estado e falhas reproduzidas

Retomada216→237; sono cooperativo confirmado,0jobs/leases, antes de editar
código carregado. Foram lidos os relatórios novos, contratoC1–C9 e checkpoint.
Revisões independentes, sem acessar diário/raciocínio privado, confirmaram:

- leitura6054caracteres perde cauda em6000 e aparece sem aviso;
- árvore/listagem limita entradas antes de filtrar artefatos de build;
- quarta leitura de qualquer trecho bloqueia intervalo nunca mostrado;
- consultas/configuração com código0 podem receber crédito de execução;
- execução não está ligada ao projeto/versão atual dos arquivos;
- término gráfico sem janela pode ser considerado execução comprovada;
- dispatcher não classifica corretamente falhas da oficina após prefixoArquivo.

## Implementação e verificação

- [x] Testes vermelhos de conteúdo6054preservado; corte explícito acima do
  orçamento; intervalo novo permitido após quatro diferentes; fontes visíveis
  apesar de400+arquivosCMakeFiles.
- [x] `project_agent.record(..., raiz=None)`: saída armazenada com limite
  conhecido e metadados de corte; guardar evidência de execução apenas quando
  comando executa artefato próprio e saída/janela são comprovadas.
- [x] `project_agent.view/releitura_excessiva`: avisar cortes; permitir trechos
  não mostrados, preservando guarda de repetição; versão de arquivo invalida
  repetição/conclusão antiga.
- [x] Qualificar execução com projeto e fingerprint dos fontes/recursos
  atuais. Consultas, configuração e build isolado não qualificam; legacy
  last_ok_run permanece histórico, sem virar aprovação.
- [x] Janela exigida pelo contrato: captura confirmada, não apenas processo
  encerrado. `completion_problem` valida evidência atual e requisito gráfico.
- [x] `project_agent` separa configuração e build real; comandos cuja execução
  não se pode confirmar não recebem comprovação por substring.
- [x] Dispatcher: exit não zero é erro; timeout permanece incerto; stdout
  com palavraerro/código forjado não substitui status do wrapper.
- [x] Listagem da oficina filtra arquivos internos antes do limite, com testes.
- [x] Limite de decisões por checkpoint`max_total_steps`, além do limite por
  sessão; tarefa atual recebe600 e`require_graphical_run=True` por contrato.
- [x] Grupos afetados e suíte offline completa; conservar mudanças preexistentes.
- [x] Cancelada a recarga/retomada pela decisão humana posterior. Tarefa
  marcada `paused`, três entidades dormindo, sem jobs/leases. Não houve
  nova entrada de retomada após a manutenção.

Revisão independente: corrigidas a guarda genérica que ignorava versões,
a contagem de decisões sem ferramenta/incompletas, o crédito de wrappers
shell/dry-runs e o vínculo de shaders/recursos reconhecidos dentro de `build/`.
22 testes do ciclo e 100/100 grupos da suíte offline passaram na rodada final.

## Avaliação e preservação

Não reiniciar desafio nem apagar fontes/recibos. Metadados novos do checkpoint
exigem revisão atribuída/CAS, preservando o registro anterior. Manter contador
de237 e autoria. A conclusão declarada pelo modelo continua sujeita aos critérios
C1–C9 externos, incluindo física, imagens, compute shader e desempenho.
Este plano não autoriza instalação, professor, treino ou outra entidade.
