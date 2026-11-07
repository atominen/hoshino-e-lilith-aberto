# Relatório geral — Hoshino, Lilith e Alistair

Data: 6 de outubro de 2026.

## 1. Avaliação resumida

**O projeto é hoje um protótipo avançado, com uma infraestrutura muito mais
organizada e verificável. Ainda não é um sistema autônomo completo e comprovadamente
confiável no cotidiano.** A parte de engenharia está mais madura que a experiência
de conversa, voz, jogos e evolução de personalidade.

Há trabalho concreto: separação de entidades, três motores conversacionais,
mensagens persistentes, execução acompanhada, áudio integrado, geração real de
imagem, observações compartilhadas e pacote portátil de Alistair. Também há
limitações concretas: voz lenta, jogos sem aprovação ao vivo, integração de voz
Discord ausente no bot atual, cognição ainda parcialmente heurística e riscos na
classificação/recuperação de memória.

Não atribuo uma porcentagem de conclusão: não temos uma lista completa de requisitos
com critérios de aceitação encerrados. Uma nota numérica daria precisão falsa.

## 2. O que esta revisão verificou

Revisei os registros das etapas, os relatórios de ensaios reais, os manifestos das
entidades e os caminhos principais de execução: conversas, ferramentas, memória,
reflexão, áudio, integrações, central e executor PC2. Reli o benchmark `aa` como
referência de aceitação, sem executar suas instruções nesta revisão.

Executei novamente a **suíte principal de 30 grupos: todos passaram**. São testes
isolados, sem escrever nas memórias reais nem exigir modelos, dispositivos ou
serviços externos. Não é auditoria de cada linha de toda a instalação, nem prova
de ausência de bugs. Existem 56 módulos `test_*.py` na pasta; a bateria principal
seleciona 30 grupos. Os outros não foram todos executados nesta rodada.

Não reiniciei serviços, não alterei código funcional, não abri o microfone, não
entrei no Discord/Minecraft e não ativei o PC2/cloud. A consulta de estado nesta
revisão mostrou Alistair em atividade, Hoshino sem execução confirmada e nenhum
recurso exclusivo ocupado. Isso não é teste de conversa real das três.

## 3. O que foi feito

### Organização e preservação

A raiz passou a ser `/home/gustavo/hoshino e lilith`. Código comum, modelos,
ambientes e serviços foram separados dos dados particulares de cada entidade.
Hoshino, Lilith e Alistair possuem pastas próprias para identidade, memória,
runtime, configuração e oficina. O caminho antigo foi mantido por compatibilidade.
A migração registrou backups e conferência de hashes; a verificação histórica
conferiu 382 arquivos e três bancos. Não é garantia de integridade contínua depois
de todas as sessões futuras.

### Identidades e três LLMs

- Hoshino: Qwen3.5 9B existente, porta 11435, GPU coordenada.
- Lilith: cópia física própria da mesma base 9B, alias e daemon próprios, porta 11436.
- Alistair: Qwen3 4B Instruct, porta 11437, CPU; organizador e standby textual.

Lilith não recebeu as lembranças da Hoshino. Tem uma predisposição inicial própria,
com afeto, curiosidade, humor e inclinação filosófica. Hoshino foi preservada: seu
arquivo inicial não contém uma lista fixa de traços da personagem de Blue Archive.
Alistair tem estilo inicial discreto/formal e memória textual própria.

**Modelo próprio significa instalação/execução e estado separados, não treinamento
individual novo.** Os pesos-base de Hoshino/Lilith têm a mesma origem; o aprendizado
atual ocorre principalmente em memória, traços, estados e contexto, não por treino
contínuo dos pesos. TTS/ASR/imagem são motores especializados, não um quarto LLM
conversacional de standby.

### Inicialização, sono e comunicação

Foi criada uma central única com seleção das três entidades, conversa, estados,
trabalhos e diagnóstico. Há controle de instância única, acompanhamento de
processos e sono cooperativo: trabalhos pendentes não viram sucesso só para sair.

O canal entre entidades guarda mensagens durante o sono, preserva autoria e
confirma leitura apenas pela destinatária. Existe pedido de despertar, mas ele
depende da central funcionando e da confirmação de presença real. Há limite de
trocas automáticas para evitar conversas infinitas consumindo inferência.

Alistair acompanha imagens, informa fila/execução/resultado e pode enviar mensagens
ou solicitar despertar. Não responde em nome das outras. Seu papel atual é menor
que o secretário/catalisador social completo descrito nos rascunhos.

### Lógica de tarefas e versatilidade

Foram reforçados roteamento de ferramentas, continuidade de tarefas, divisão em
etapas, recuperação de caminhos, acompanhamento de progresso e exigência de
evidência antes de afirmar conclusão. Cálculo e sorteios têm ferramentas
determinísticas, sem depender de o modelo adivinhar o resultado.

Há filas por conversa e separação de participantes/canais. Consultas sem efeitos
conhecidos podem rodar em paralelo; mudanças no sistema são serializadas. Os
modelos GPU também disputam um recurso coordenado. **Várias tarefas podem avançar,
mas isso não significa todas as ações ou os dois 9B simultaneamente na GPU.**

O registro estático tem 161 declarações de ferramentas, cobrindo arquivos,
terminal, navegador, aplicativos, agenda, visão, comunicação, jogos e imagens.
Esse número mede a superfície disponível, não 161 capacidades certificadas em
uso real. Ainda depende de boa escolha de ferramenta, argumentos, estado e retorno.

### Memória e cognição

Existem histórico, episódios, conhecimento estruturado, recuperação de memória,
traços por evidências, gostos, relações, reflexões e um estado psicológico de médio
prazo separado de humor/identidade. Há regras para priorizar ações e para não
interpretar estado ambiental desconhecido como presença/ausência humana certa.

Isso é mais que uma personalidade escrita num prompt. Porém parte das mudanças
é conduzida por eventos e pesos definidos no código; inferências/reflexões ainda
podem estar erradas. Relações direcionais mais profundas, valores adquiridos,
revisão de crenças e avaliação longitudinal continuam incompletos. Não há prova
de consciência ou de uma mente humana; o que podemos verificar é comportamento,
persistência e funcionamento dos mecanismos.

### Áudio

A central grava pelo navegador, transcreve localmente e preenche um rascunho
revisável. Não envia a transcrição automaticamente para as entidades. Hoshino e
Lilith possuem candidatos de voz diferentes, Serena e Vivian, no Qwen3-TTS 0.6B.
Alistair permanece textual. A fala automática começa desligada.

ASR/TTS são compartilhados, com fila limitada, prioridade de transcrição,
cancelamento, timeouts, liberação de RAM e validação dos WAVs. Evitamos duplicar
captura/reprodução na execução pela central. O Kokoro legado foi preservado.

Os ensaios reais provaram síntese, transcrição de áudio sintético, cancelamento e
encerramento dos workers. **Não provaram captura da sua voz, saída física,
naturalidade ou sotaque satisfatório.** A versão central e a interface antiga
ainda têm caminhos de voz diferentes. Não existe isolamento global de áudio por
aplicativo nem identificação biométrica/diarização pronta.

### Imagem e estado compartilhado

Qwen-Image foi integrado com presets, parâmetros explícitos, execução assíncrona,
progresso observado, catálogo persistente e prévia na central. O arquivo só fica
concluído após conferência técnica. Há proteção de recursos e subprocesso.

A geração real funcionou, mas errou parte do conteúdo pedido. PNG válido não
significa imagem semanticamente correta. Jobs sobrevivem como registros; a
computação interrompida não retoma automaticamente do ponto anterior.

O estado factual compartilhado registra observações com fonte, validade e
confiança. As interpretações e memórias continuam individuais. Leituras vencidas,
conflitantes ou desconhecidas não são tratadas como certezas. Inicialização
concorrente de bancos compartilhados também foi reforçada.

### Discord e Minecraft

O Discord tem adaptador de texto: menções, DMs, canais habilitados, anexos,
entrada/saída persistente, contatos e confirmação de entrega. Foram melhoradas
filas para não misturar perguntas externas em uma única mensagem.

Minecraft tem ponte Mineflayer para Java/LAN: conexão e estado, inventário, chat,
navegação, mineração, coleta, fabricação, equipamento, ataque, colocação de blocos,
uso de item e seguir jogador. O cliente verifica a versão do protocolo da ponte.

Há ferramentas para iniciar/encerrar integrações e atalhos na interface antiga.
**Não está certificado que o comportamento ao vivo funciona corretamente em
todas essas situações.** Lilith ainda não tem seu próprio arquivo de configuração
Discord nesta instalação. O bot Discord atual não implementa conversa de voz
bidirecional: isso é implementação pendente, não apenas um teste manual pendente.

### Recursos, referências externas e PC2

Há arbitragem de GPU, registros de recursos ocupados, fila serial de áudio e
separação de Alistair em CPU. O planejamento geral considera PC principal, Athlon,
cloud leve e cloud normal, mas continua consultivo. O controle de orçamento
cloud é local: não consulta faturas, contrata máquinas ou garante o teto real.

Foram adaptados componentes pequenos do AIRI (filas/prioridades) e do Neuro SDK
público (janelas/contratos de ações), com origem e licenças preservadas. Isso não
importa a inteligência, a memória ou todo o sistema desses projetos. Da Shogun,
não foi identificado código oficial verificável nesta pesquisa.

O pacote de Alistair para o Athlon está pronto: aproximadamente 2,56 GB, modelo
4B e motor CPU incluídos, sem bancos mentais, credenciais Discord ou bibliotecas
GPU. O cliente LAN tem autenticação, limites e tratamento de pedidos incertos.
A mente, correio e ferramentas permanecem no PC principal. O início preparado
para PC2 limita RAM/CPU; **a aplicação desses limites no Mint/PC2 ainda não foi
verificada**. O backend permanece desativado.

## 4. Evidências de funcionamento e desempenho

Os tempos abaixo são amostras históricas, em contextos diferentes. Não são médias,
percentis de latência ou garantias de desempenho futuro.

| Ensaio | Resultado observado | O que não demonstra |
| --- | --- | --- |
| Suíte principal, repetida nesta revisão | 30 grupos passaram | Todos os módulos antigos testados ou funcionamento ao vivo |
| Três LLMs, contexto isolado | Identidade e 14 + 7 corretos; Hoshino 5,50 s, Lilith 5,65 s, Alistair 10,84 s | Qualidade prolongada, personalidade e tarefas complexas |
| Imagem 768×768, 16 passos | PNG concluído em 209,6 s; fidelidade visual parcial | Representação correta de todas as identidades ou benchmark completo |
| Alistair durante imagem | Resposta em 30,92 s, sem ocupar VRAM | Interface sempre rápida ou ausência de contenção de CPU |
| Voz central, candidatas | Cerca de 38–42 s para aproximadamente 7 s de fala | Conversa em tempo real ou timbre aprovado pelo usuário |
| Transcrição integrada | Frase sintética transcrita em 12,059 s | Microfone humano sob ruído, eco e múltiplos falantes |
| Pacote PC2 ensaiado no PC principal | 14 + 7 = 21 em 8,52 s, CPU; encerrou e liberou porta | Velocidade no Athlon, HD, LAN ou convivência com YouTube |

O áudio Qwen atual é aproximadamente cinco vezes mais lento que a duração da
fala. Isso é um obstáculo real para a experiência de companheira em conversa
contínua. Colocar Alistair no PC2 pode reduzir contenção no principal, mas não
podemos prometer que o Athlon acelere suas respostas.

## 5. Pendências técnicas identificadas nesta revisão

### A. Confiança zero pode ser elevada na recuperação de memória

Em [knowledge_store.py](</home/gustavo/hoshino e lilith/app/memory/knowledge_store.py:417>),
o código usa `conf or 0.5` para memórias e `conf or 0.8` para propriedades.
Em Python, zero entra no valor padrão. Portanto confiança explicitamente zero
pode receber peso de 0,5/0,8 na seleção. **É um defeito concreto de tratamento do
valor**, embora esta revisão não demonstre um incidente real causado por ele.
O estado compartilhado novo já trata confiança zero corretamente; a memória
antiga ainda precisa ser alinhada.

### B. Reflexão pode reaparecer como fato

Em [reflection.py](</home/gustavo/hoshino e lilith/app/mind/reflection.py:115>),
conclusões geradas pelo LLM são gravadas no conhecimento como `tipo="fato"`,
apesar de `fonte="reflexao"`. A recuperação examinada mostra o tipo/conteúdo,
sem carregar essa origem no texto do candidato. Isso abre espaço para uma
interpretação reaparecer como fato e se reforçar. **O risco é visível no código;
o efeito em conversas reais ainda precisa ser medido.** Falta preservar a
distinção observação/interpretação/hipótese ao longo de toda a memória, não só
no estado do ambiente.

### C. A nova interface não reúne todos os controles existentes

O navegador central reúne conversa, sono, áudio, imagem e diagnóstico. Os
atalhos diretos Discord/Minecraft estão na
[interface antiga](</home/gustavo/hoshino e lilith/app/main.py:205>), não como
controles equivalentes na central nova. Portanto a interface única ainda não é
um painel completo de todas as capacidades.

### D. Sono seguro não equivale a encerramento sempre limitado

A central [espera cooperativamente os processos](</home/gustavo/hoshino e lilith/iniciar_entidades.py:344>).
Isso evita abandonar operações, mas o loop de espera não possui prazo global.
Uma entidade travada pode prolongar o encerramento. Faltam política de escalada,
diagnóstico claro do bloqueio e recuperação de estado incerto, sem repetir
efeitos nem matar processos alheios.

### E. Manutenção e armazenamento merecem atenção

O projeto não está em um repositório Git nesta pasta. Existem backups/registros,
mas isso não substitui um histórico organizado de alterações e reversões.
`app/main.py` tem aproximadamente 3.512 linhas; o registro/despacho de ferramentas
também é grande. Separar código de dados melhorou a organização, mas o controlador
ainda concentra muita responsabilidade e dificulta mudanças de baixo risco.

O disco do PC principal foi observado com **97% de ocupação e cerca de 24 GiB
livres**. Ainda há espaço, mas novos modelos/artefatos podem provocar falhas.
Falta política global de armazenamento. A recomendação é inventário e preservação
antes de qualquer remoção; nada foi apagado nesta revisão.

## 6. O que falta e pode ser feito sem teste manual seu

1. Corrigir confiança zero e separação entre fato, reflexão e hipótese na memória,
   acrescentando regressões e preservando os dados existentes.
2. Ampliar diagnóstico de falhas de persistência: há caminhos psicológicos/reflexivos
   que engolem exceções, podendo ocultar aprendizado não salvo.
3. Unificar controles Discord/Minecraft na central nova, sem perder os atalhos antigos.
4. Completar a implementação de voz Discord se ela continuar no escopo desejado;
   o funcionamento ao vivo depois exigirá um canal real.
5. Melhorar gerenciamento global de RAM/CPU, prioridades e recuperação. As filas
   locais e limites preparados do PC2 não constituem um scheduler distribuído completo.
6. Expandir contratos/recibos de ações mutáveis além de Alistair e testar efeitos
   incertos. Os recibos dele não oferecem transação atômica entre bancos diferentes.
7. Organizar versionamento, matriz completa de testes, atualização de documentação
   histórica e separação gradual do controlador grande.
8. Melhorar testes de comportamento: várias mensagens seguidas, pessoas diferentes,
   interrupções, pedidos simples, recusas fora de contexto e consistência de identidade.
   Os problemas de tom vistos nas imagens antigas não estão comprovadamente resolvidos.
9. Evoluir relações/valores e revisão de crenças com evidência rastreável, sem inserir
   histórias fabricadas nem confundir parâmetros definidos no código com experiência.

Algumas dessas tarefas também terão uma etapa final de validação humana. Não
significa que basta esperar você testar: ainda existe implementação a concluir.

## 7. O que depende de teste real e da sua participação

| Prioridade | Teste | Critério de aprovação |
| --- | --- | --- |
| 1 | PC2: Mint, IPs, transferência, bibliotecas, limites, LAN | Iniciar, inferir e parar corretamente; chave/relógios válidos; consumo limitado |
| 2 | PC2 com e sem YouTube, inferência fria/quente | Tempos registrados, vídeo utilizável, RAM e responsividade aceitáveis |
| 3 | Microfone na central | Sua frase transcrita corretamente, destinatária certa, cancelamento e saída funcionando |
| 4 | Vozes Hoshino/Lilith | Timbres distinguíveis, texto fiel, sotaque e naturalidade aprovados por você; latência aceitável |
| 5 | Discord texto ao vivo | Menções/DMs, várias pessoas, ordem das respostas, recuperação e nenhuma conclusão falsa |
| 6 | Minecraft Java/LAN ao vivo | Entrar no mundo e executar ações verificadas; falhas/reconexão sem estado inventado |
| 7 | Conversas entre entidades | Autoria correta, entrega após acordar, memória separada e sem cadeia infinita |
| 8 | Benchmark `aa`, por Hoshino/Lilith | Três desafios reais, validação independente, imagem coerente, relatório salvo e relido |
| 9 | Uso prolongado e simultâneo | Horas de operação, reinício/falhas, consumo e continuidade acompanhados |

O benchmark `aa` não está aprovado. A existência de calculadora, sorteios, gerador
de imagem e relatórios não prova que a entidade os orquestra corretamente numa
execução completa. Discord e Minecraft também precisam de revisão/configuração
própria antes de prometer equivalência de capacidades para Lilith.

## 8. Minha avaliação sincera

**Pontos fortes:** separação de estados, mecanismos de execução verificável,
persistência de mensagens/jobs, coordenação de GPU, testes isolados e registros
de ensaios reais. São fundamentos úteis e já demonstrados, não apenas ideias.

**Pontos mais fracos:** latência de áudio, integração cotidiana ainda pouco
comprovada, central incompleta para alguns controles, tratamento desigual de
confiança/origem em memória, recuperação global de falhas e complexidade do
controlador. A evolução de personalidade tem mecanismos, mas ainda não tem
comprovação longitudinal de coerência e de benefício real nas decisões.

**O objetivo de versatilidade está bem encaminhado na quantidade de ferramentas;
a confiabilidade dessa versatilidade ainda precisa crescer.** Ter muito código
e muitos nomes de ferramentas não torna o agente automaticamente bom em decidir,
intercalar tarefas e concluir pedidos sem supervisão.

Não seria honesto equiparar o estado atual à fluidez de um sistema de entretenimento
como Neuro-sama, nem dizer que copiar componentes do AIRI nos dá a maturidade do
projeto inteiro. Também não seria justo chamar tudo de fachada: houve inferências,
áudio e imagens reais, além de uma reorganização e mecanismos persistentes úteis.

Minha recomendação é uma fase de consolidação: **primeiro corrigir os pontos de
memória/estado e fechar a rotina real conversa → ação → verificação → resposta;
depois ampliar a cognição e a distribuição.** Cloud e novos módulos não deveriam
ser usados como atalho para problemas básicos ainda não medidos. O PC2 deve ser
avaliado como forma de distribuir carga, não como aceleração garantida.

## 9. Evidências principais

- [Estrutura e preservação](</home/gustavo/hoshino e lilith/docs/ESTRUTURA_20261005.md>).
- [Correções de lógica e execução](</home/gustavo/hoshino e lilith/docs/VARREDURA_20261004.md>).
- [Três modelos, imagem e standby](</home/gustavo/hoshino e lilith/docs/ENTREGA_20261006.md>).
- [Áudio e seus limites](</home/gustavo/hoshino e lilith/docs/AUDIO_CENTRAL_20261006.md>).
- [Estado compartilhado e planejador](</home/gustavo/hoshino e lilith/docs/ESTADO_COMPARTILHADO_20261006.md>).
- [Pacote PC2 e etapa automática](</home/gustavo/hoshino e lilith/docs/ETAPA_AUTOMATICA_PC2_20261006.md>).
- [Medições dos modelos](</home/gustavo/hoshino e lilith/docs/verificacao_tres_modelos_20261006.json>).
- [Medições de imagem/standby](</home/gustavo/hoshino e lilith/docs/verificacao_imagem_standby_20261006.json>).
- [Medições de áudio](</home/gustavo/hoshino e lilith/docs/verificacao_audio_central_20261006.json>).
- [Verificação PC2, ainda no PC principal](</home/gustavo/hoshino e lilith/docs/verificacao_pc2_20261006.json>).
- [Bateria principal, repetida nesta revisão](</home/gustavo/hoshino e lilith/rodar_testes.sh>).

Os registros históricos descrevem a etapa em que foram escritos. Por exemplo,
áudio e RPC PC2 antes pendentes foram implementados em etapas posteriores, embora
as respectivas validações humanas/LAN continuem pendentes. Este relatório consolida
o estado mais novo e não trata todo item de um rascunho como uma capacidade pronta.
