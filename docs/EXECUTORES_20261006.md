# Executores leves e Alistair oportunista — 06/10/2026

## Escopo

Implementação no Resource Manager existente, no mesmo banco/locks. Não há
segundo scheduler, outro banco mental ou identidade copiada entre entidades.
O congelamento está em `ESCOPO_CONGELADO.md`: depois desta expansão, somente
refinamento das capacidades existentes. Cloud permanece desativada no JSON
de capacidades. Azure/Qwen/Kokoro e ferramentas existentes foram preservados.

## Seleção do executor

Hoshino/Lilith mantêm seu principal 9B e recebem um executor 7B independente.
O modelo escolhido é [Qwen2.5 7B Instruct Q4_K_M](https://ollama.com/library/qwen2.5:7b-instruct-q4_K_M):
7,62 bilhões de parâmetros, cerca de 4,7 GB por cópia, português e ferramentas.
Não foi escolhido um novo gerenciador ou uma nova entidade.

O catálogo fixo é `entidades/{hoshino,lilith}/config/executores.json`.
O principal continua vindo da configuração atual da entidade, sem mudança de
nome/peso. Configuração antiga ou ausência do leve conservam o principal.
Catálogo inválido ou tentativa de adicionar modelo não aprovado é diagnosticada.

Antes da inferência, o Resource Manager combina complexidade, prioridade,
contexto (incluindo schemas de ferramentas), RAM livre, VRAM/utilização,
compute ocupado, fila, residência, custo de recarga e latências previstas.
Qualidade é uma restrição: complexidade desconhecida, conversa importante,
tarefas operacionais, reflexão profunda, compactação e imagens ficam no 9B.
Saudações, traduções/reformulações curtas, avaliações internas pequenas e
pensamento espontâneo simples podem usar o 7B. Um 9B quente pode vencer o 7B
frio pelo custo de troca. O modelo leve usa contexto de 8k, teto de 1024 tokens
de saída para trabalhos leves e não recebe `think`. O principal mantém o teto
configurado anteriormente. Nenhuma memória é cortada para forçar encaixe no
leve; contexto longo usa 9B.

O contexto de execução é privado por tarefa assíncrona. Escolha imutável é
fixada durante resposta, ciclos de ferramentas, retry e conferência final.
Reflexão, extração e compactação possuem ciclos internos independentes.
Outra resposta/tarefa não herda o executor escolhido por um pai assíncrono.
Não há escrita em `config.MODEL_NAME` durante inferência.

O adaptador GPU recebeu o modelo real do payload, inclusive para estimativa
de catálogo e residência. Visão continua usando o principal com suporte visual.
Encerramento descarrega/verifica os dois executores da própria entidade sob
manutenção coordenada, sem atingir catálogo/daemon de outra entidade.

## Residência e hardware

`gpu_residency` permanece compatível; nenhuma migração destrutiva. O estado
derivado é `gpu_resident` (VRAM>0), `ram_resident` (VRAM=0), `unloaded` (ausente)
ou `unknown` (sonda vencida/incerta). Zero não vira ausência.
Sonda limitada `/api/ps` atualiza apenas o daemon local da entidade, sem
inferência/unload. [Contrato oficial](https://docs.ollama.com/api/ps).

O limite permanece 8 GiB (ou o total físico menor reportado pelo amdgpu), margem
768 MiB, concorrência agressiva desativada. Não depende de CUDA/NVML. VRAM
resident não bloqueia compute por si só; nova carga exige previsão segura de
VRAM e RAM de staging. MemAvailable decide RAM, sem contar swap.
Latências iniciais são **heurísticas**, não benchmarks reais. O custo de load
observado pelo backend substitui a estimativa quando disponível.

## Alistair

Boot/PC2 continuam CPU. Inferência local passa pelo mesmo compute lease com
prioridade P5 e flag oportunista. GPU é negada se há áudio interativo, compute
ativo, pedido prioritário ou qualquer Hoshino/Lilith aguardando, uso GPU incerto/
elevado, RAM/VRAM insuficiente ou recarga mais cara que benefício previsto.
Alistair não realiza unload de pares para ganhar espaço. Negação tenta CPU com
RAM segura; falta de recursos gera espera limitada/falha, nunca sucesso falso.

CPU envia `num_gpu:0`; GPU deixa Ollama selecionar Vulkan. Não há preempção
insegura ou repetição de efeitos. Ao finalizar HTTP, compute é liberado e a
residência é reobservada. Pesos podem ficar quentes, mas não há posse eterna
de compute. Uma interação que chega durante Alistair não o mata; fila prioritária
é atendida depois do trabalho atual, ou usa fallback seguro existente.

Telemetria usa eventos existentes `executor.selected`, `gpu.queued`,
`gpu.compute_acquired/released`, recarga e sondas. Registra escolha/motivo/custo,
prioridade, filas, VRAM e duração; não grava chave nem altera personalidade.

## Instalação e reversibilidade

O instalador `scripts/preparar_executores_leves.py` é somente leitura por
padrão. `--instalar` permite apenas os dois leves congelados nos daemons
11435/11436 existentes, não inicia/reinicia processo ou faz inferência.
Estimativa conservadora: 10 GiB finais + 5 GiB staging + 10 GiB reserva = 25 GiB
livres necessários. Espaço é revalidado antes de cada pull e durante stream.
Arquivos parciais não são removidos cegamente. Os aliases não gravam identidade;
o prompt atual da aplicação fornece identidade/mente da entidade.
Cada blob é conferido por tamanho e SHA256, sem symlinks de pesos entre entidades.

O disco começou com cerca de 15,8 GiB livres/98%; download foi inicialmente bloqueado.
Após o usuário liberar espaço, havia cerca de 92 GiB livres/89% e o planejamento
aprovou instalação. A primeira tentativa detectou falta de permissão: modelo
antigo pertence a `ollama`, daemon atual a `gustavo`. Foi acrescentada somente
ACL `u:gustavo:rwx` aos diretórios `ollama/blobs` e `ollama/manifests`; nenhuma
permissão de arquivo existente foi alterada. Reversão desta ACL: retirar essa
entrada nominal nesses **dois caminhos exatos**, sem chown/chmod recursivo.

Backup de código anterior: `arquivo/executores-20261006/codigo_antes.tar.gz`.
Reversão consiste em restaurar somente os arquivos correspondentes de código;
não extrair backup sobre modelos/memórias. Os 7B podem ficar no disco sem serem
selecionados pela versão antiga. Não houve exclusão de dados/modelos antigos.
Entidades em execução não foram reiniciadas; abrir novamente a central depois
de encerramento seguro carrega a implementação nova.

## Testes e riscos

Antes: roteiro oficial completo, 39/39 grupos passaram.
Após: primeira execução ampliada, 40/40 grupos passaram. Novos testes cobrem
seleção/complexidade/custos, isolamento assíncrono, resposta fixa, limites de
contexto, categorias de residência, CPU/GPU Alistair, prioridade do áudio/fila,
não expulsão/não interrupção, espaço e integridade de instalação.

Verificação adicional de 25 arquivos históricos fora do roteiro oficial revelou
expectativas antigas e um teste manual; resultados finais estão na seção de
fechamento abaixo. Não foram alteradas capacidades para satisfazer testes
obsoletos. O teste `test_microfone_continuo_v33.py` é explicitamente manual:
tentou inicializar captura/ASR e terminou por timeout sem resultado reconhecido;
foi bloqueado no executor automatizado e downloads incidentais Hugging Face
foram desativados no ambiente de testes. Nenhum processo deste teste restou
ativo na inspeção posterior.

Riscos: classificação determinística inicial conservadora; timings precisam de
calibração AMD real, qualidade/naturalidade do 7B precisam de uso; áudio/ASR já
podem ocupar boa parte da RAM. Não há promessa de vários modelos simultâneos
na GPU, nem redução arbitrária da margem para evitar fallback.

## Fechamento

Instalação concluída e verificada. Cada cópia contém 4.683.073.952 bytes de peso;
SHA256 `2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730`.
Os inodes são distintos (7609154 e 21375461 no dispositivo 66306), sem symlink
ou hardlink entre entidades. Os aliases possuem prompt neutro, sem herdar
“You are Qwen”. Cerca de 83,2 GiB ficaram livres após instalação, acima da reserva.

O Ollama ignora `system:""` ao herdar a fonte: isso foi detectado em `/api/show`
e corrigido por um prompt neutro explícito. Há regressão específica para este
bug. Contexto de 8192 e capacidades textuais/ferramentas foram confirmados no
catálogo de cada alias. Os dois principais 9B e Alistair 4B continuam presentes.

Testes reais isolados, sem memória/conversa/ação externa e sem reiniciar entidades:

- Hoshino 7B: `PRONTO`, lease GPU, 4,647 s incluindo carga inicial de 4,425 s.
- Lilith 7B: `PRONTO`, lease GPU, 2,793 s incluindo carga inicial de 2,515 s.
- Alistair 4B: `PRONTO` pela rota oportunista GPU (confirmada na telemetria),
  4,344 s; fallback CPU explícito, `PRONTO` em 3,755 s.
- Os testes pediram `keep_alive:0` somente para seus executores, para não deixar
  carga de teste residente. Ao final, `/api/ps` confirmou ausência dos modelos
  testados e nenhum compute lease ficou ativo. Isso não modifica a política
  de residência quente da execução normal.

São probes mínimos, não benchmarks de conversa longa, áudio simultâneo ou
qualidade de personalidade. Um primeiro probe de Alistair recebeu 404 porque
o ambiente do terminal ainda exportava o modelo de Hoshino; o harness foi
corrigido para selecionar explicitamente o modelo da entidade. Não houve
troca de executor no meio da inferência nem alteração do loader de ambiente.

Resultado final do roteiro oficial: **40/40 grupos passaram**, depois das
últimas mudanças de código. A nova bateria contém **47/47 regressões passando**.
Inclui prazo/cancelamento de manutenção, limites de saída/contexto do 7B,
preservação do prompt de identidade, RAM de staging GPU e neutralidade dos aliases.

Na auditoria histórica adicional: **15/25 arquivos passaram**; **9 falharam**
e **1 era manual**, inadequado a execução offline. Falhas que permanecem:

- `test_capacidade_operacional`, `test_execucao_paralela`,
  `test_v17_arquitetura`, `test_v18_continuidade`, `test_v19_continuidade`:
  expectativas antigas sobre `write_file/read_file` e contratos substituídos
  pelo workspace/controller atual.
- `test_ollama_lifecycle`: mock de recuperação espera comportamento antigo de
  reinício systemd; este caminho de recuperação não foi alterado nesta etapa.
- `test_v20_iniciativa`: fixture sem tabela `goals` no banco isolado.
- `test_v32_multimodal`: pressupõe o modelo antigo de imagem Animagine XL 4.
- `test_v35_hardening`: worker fake não envia o identificador do pedido de voz,
  exigido pelo contrato atual.
- Manual: `test_microfone_continuo_v33`; agora recusado pelo executor offline.

Essas falhas precisam ser reconciliadas em refinamento. Não são contadas como
aprovações, nem há alegação de que todos os arquivos de teste passaram.

## Arquivos desta etapa

Modificados:

- `app/core/resource_manager.py`: escolha de executor e invariantes de residência,
  RAM e GPU oportunista, no gerenciador existente.
- `app/core/gpu_resource.py`: modelo real do pedido, orçamento do leve e prazo/
  cancelamento de manutenção.
- `app/core/ollama_lifecycle.py`: encerramento coordenado dos dois executores.
- `app/main.py`: escopos de resposta/tarefas internas e payload do leve.
- `app/alistair_runner.py`: roteamento local GPU/CPU e sondas/encerramento próprios.
- `rodar_testes.sh`: inclusão do grupo de regressão novo.
- `testes/executar_isolado.py`: catálogo temporário, sondas mockadas, proteção
  offline contra downloads e bloqueio do teste manual.
- `README.md`: descrição atual de cinco executores e congelamento.

Criados:

- `entidades/hoshino/config/executores.json` e
  `entidades/lilith/config/executores.json`.
- `scripts/preparar_executores_leves.py`.
- `testes/test_executores_leves.py`.
- `ESCOPO_CONGELADO.md` e este relatório.

Mudanças intencionais de comportamento: tarefas simples podem usar o 7B,
Alistair local pode usar GPU ociosa, sono encerra ambos os executores próprios,
e testes automatizados não podem iniciar captura manual/downloads de modelos.
O 9B, identidades, memórias, relações, estado e fallbacks locais continuam
preservados. Próxima fase é somente refinamento, sem novas capacidades/modelos.
