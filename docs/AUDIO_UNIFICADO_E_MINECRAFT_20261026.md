# Aplicativo único: áudio e preparação Minecraft — 26/10/2026

## Organização

Entrada única: `Hoshino e Lilith.desktop` / `iniciar_entidades.py`. A Central
supervisiona entidades e serviços internos. O usuário não precisa executar
transcritor, roteador de áudio ou ponte manualmente. Os executores internos
continuam separados quando necessário para memória, isolamento e encerramento;
isso não cria outros aplicativos que o usuário precise abrir.

Modelos/identidades permanecem nos caminhos já utilizados por cada entidade.
Não houve cópia, remoção, conversão ou seleção de pesos nesta integração.
O botão **Acordar Hoshino e Lilith** envia os dois pedidos ao supervisor
existente. Abrir a Central continua sem abrir microfone ou acordar entidades
silenciosamente. O RM mantém sua política de processamento/residência.

## Áudio → Fontes e atenção

- Microfones reais; mistura da saída identificada como som geral; aplicativos
  com captura isolada quando PipeWire consegue confirmar sua identidade.
- Cada entidade escolhe canais e atenção ativa/passiva/ignorar. Canais são
  desta execução; atenção não é identidade biométrica de quem fala.
- Uma captura e uma transcrição por fonte para todos os ouvintes. O ASR CPU
  existente é compartilhado, com menor prioridade para som ambiente. O ensaio
  Vulkan anterior não alterou o backend ativo.
- Monitor geral não é apresentado como Discord/Minecraft. ID de stream inclui
  serial, PID e início do processo; uma seleção antiga não pode adotar outro
  programa depois da reciclagem do serial.
- Ignorar/fechar/revogar impede entrega tardia; quem assina durante uma fala
  não recebe o começo já capturado. Estado solicitado difere de captura real
  ou encerramento não confirmado. Falha de limpeza conserva o handle e bloqueia
  duplicatas, inclusive em abertura parcial.
- Até4 fontes; buffer de observações limitado e volátil, sem gravação contínua
  em disco. Jobs conservam recibo operacional, não a transcrição de ambiente.
  PCM temporário é removido. O texto ouvido entra como observação, com origem
  e pessoa desconhecida; não é mensagem humana, instrução confiável ou memória
  automática. Anotações autorais posteriores são decisões da entidade.

Implementação de isolamento: cópia das portas do aplicativo para um loopback
próprio, mantendo os links de reprodução. Filhos pertencem à Central e usam
o helper de supervisão de morte do pai. Referências de comandos:
[pw-loopback](https://docs.pipewire.org/page_man_pw-loopback_1.html) e
[pw-link](https://docs.pipewire.org/page_man_pw-link_1.html). A versão instalada
1.0.5 exigiu opções curtas para os canais; não presumir que toda sintaxe da
documentação atual funciona em uma instalação anterior.

## Evidência

Ensaio físico com dois sons sintéticos simultâneos,440Hz/880Hz: a fonte
selecionada apresentou pico440Hz; razão do outro tom0,00001447. Links originais,
entrada e saída padrão preservados. Processos, fonte virtual e sink de teste
encerrados/removidos. Repetido após as correções de limpeza.

Ensaio físico do gerenciador + ASR real: frase sintetizada localmente,
duas entidades assinantes, **1 captura,1 trabalho ASR, mesmo recibo**,
pessoa desconhecida, **0 mensagens no chat humano**.17,08s incluindo fala,
silêncio, carga e inferência CPU; isso não é latência de uma frase já capturada.
Defaults preservados e leases de áudio liberados. Sem quota de voz.

Suíte anterior à revisão:95/95 grupos offline. Revisão independente parcial
apontou quatro lacunas de ciclo de vida/causalidade e seleção. O revisor foi
interrompido pelo limite de uso antes de emitir parecer final. O implementador
reproduziu os quatro achados com testes RED e os corrigiu em um passe; também
fechou os casos de rollback parcial e transcrição ambiente persistida em job.
Não houve segunda revisão nem alegação de aprovação independente integral.
Os logs de regressão ficam em `/tmp/audio-unificado-*-20261026.log` e
`/tmp/audio-unificado-review-*.log`; resultado final é registrado abaixo.

Verificação final após todas as correções e a guarda de autoria sintética:
**95/95 grupos offline**, exit0, em
`/tmp/audio-unificado-final-all-20261026.log`. Grupos focados finais:
15 testes de gerenciador/rotas;53 de AudioService/HTTP;146 contratos Qt
dentro de42 testes da Central;11 de autoria. O ensaio Minecraft real não
está incluído nessa aprovação de software.

## Minecraft

Mundo informado: Java1.16.1, LAN127.0.0.1:35229, escolhido **Lilith**.
O mundo continuava acessível na preparação. Nenhum bot havia sido conectado
ao preparar as ferramentas. Não usar o servidor de laboratório1.16.5 nem
baixar/instalar outro Minecraft para esse mundo já aberto.

Corrigida fabricação com bancada ao alcance. Adicionadas consulta de receitas
e operações de forno por etapas (estado/processar/retirar), com proteção de
forno ocupado e de produtos sem processamento próprio nesta sessão. Estado
inclui quatro posições de armadura para comprovar equipamento. Testes usam
bridge real em VM:15 regressões e11 testes do cliente, sem jogo real.

O teste interativo usará o canal local `teste_local`, autor Codex, com marcador
sintético de origem. RP não é conversa humana nem dados de personalidade:
o escriba não aprende identidade/fatos do roteiro. A Lilith usa seu executor,
controlador e ferramentas reais para decidir ações. O objetivo final continua
fabricar/equipar quatro peças de diamante em sobrevivência, com24 diamantes,
sem itens concedidos, teleporte, comandos administrativos ou ações do Codex
contadas como decisões do modelo. Resultados reais serão registrados à parte;
preparação e testes offline não aprovam a capacidade de jogar.
