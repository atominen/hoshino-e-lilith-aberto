# Estrutura e migração — 5 de outubro de 2026

## Fronteiras

O pedido desta etapa foi revisar e organizar o projeto existente, preservar a
Hoshino e preparar uma Lilith independente. Lilith agora está habilitada para
conversa local, com estado e modelo lógico próprios; integrações externas ainda
não foram habilitadas para ela.

Uma entidade usa seu próprio `identity`, `memory`, `runtime`, `workspace` e
`config`. Os algoritmos de mente e memória pertencem ao código comum. Lembranças,
emoções, relações, preferências aprendidas e estado psicológico pertencem aos
bancos e arquivos daquela entidade.

O processo seleciona `HOSHINO_ENTIDADE` ao importar a configuração (padrão:
`hoshino`). A pasta deve ter manifesto válido e ativo. Lilith tem manifesto
`ativa` e pode ser selecionada explicitamente. Não se deve trocar
entidade em um processo já iniciado: vários módulos mantêm clientes e estados
globais, por isso cada entidade precisa de seu processo.

## Preservação

- Diretórios grandes são movidos no mesmo disco, sem redownload de pesos.
- Identidade, memória e estado são conferidos por SHA-256 antes e depois.
- A cópia anterior está em `arquivo/migracao-20261005/dados-antes-da-mudanca.tar.gz`.
- Movimentos e hashes estão em `movimentos.json` e `dados-verificados.json`
  dentro desse mesmo diretório.
- Backups antigos e o manifesto anterior estão em `arquivo/legado-20261005`.
  O manifesto antigo descreve a distribuição anterior, não a árvore atual.
- O caminho antigo é um link para `compat/hoshino`. Aliases relativos à raiz nova
  preservam shebangs dos ambientes Python, builds e referências históricas.
  O código atual usa os caminhos canônicos de `app/config.py`.

A cópia contém dados pessoais e credenciais do projeto e usa permissão 600.
Ela não é um pacote público de diagnóstico.

## Limites para duas entidades simultâneas

Lilith tem identidade, prompt de origem, vocabulário de voz lógico e mensagens
próprias. Discord ainda precisará de configuração própria; Minecraft precisará de
validação em LAN com os bots distintos. A central posterior a esta migração já
separa as portas das pontes e coordena os consumidores de GPU; consulte
[central local](CENTRAL_LOCAL_20261005.md) para as verificações e limitações.

A trava de GPU pertence à infraestrutura compartilhada. Estado de tarefas,
histórico, saídas, memória e oficina pertencem a cada entidade separadamente. Essa
organização é a base operacional das duas entidades; a evolução de personalidade
continua limitada por evidência e memória de cada uma.

## Recuperação

Não sobreponha bancos anteriores a uma sessão em execução. Encerre a interface
e auxiliares, consulte o mapa de movimentos e restaure seletivamente a cópia em
um diretório separado. A mudança de pastas preserva conteúdo e schema dos bancos.
Não execute novamente o script pontual de reorganização.

## Verificação e pendências observadas

A auditoria `scripts/verificar_migracao.py` conferiu 382 arquivos por hash,
três bancos por `PRAGMA quick_check` somente leitura e os links legados.
A inicialização com `--verificar` funciona pelo caminho novo e pelo antigo.

Os 20 grupos da suíte `rodar_testes.sh` passaram com estado temporário. Essa
suíte não certifica serviços ao vivo, geração de imagem ou captura física de áudio.
O worker de voz agora possui timeout configurável (`HOSHINO_TTS_WORKER_TIMEOUT`,
padrão 120 segundos), evitando que uma síntese travada bloqueie o processo.
A captura física e a reprodução ainda exigem teste no equipamento antes de
declarar o áudio certificado.

O mesmo teste revelou que caminhos relativos de arquivos usavam a home comum.
Isso foi corrigido: sem base explícita, usam a oficina da entidade. A regressão
está coberta em `test_estrutura_entidades.py`. O arquivo de exemplo criado pelo
teste antigo foi preservado em `arquivo/migracao-20261005/hello-do-teste-v35.txt`.
O executor de testes redireciona o estado; não é um sandbox de segurança para
executar testes arbitrários não confiáveis.
