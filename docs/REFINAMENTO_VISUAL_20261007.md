# Central e orbes — refinamento visual

## Paleta solicitada em 25/10/2026

Hoshino usa rosa claro (`#f7b9d2`), Lilith vermelho rubi luminoso
(`#e65b70`) e Alistair azul-céu (`#87ceeb`). A paleta identifica os cartões,
os cabeçalhos de autoria do chat nativo, os orbes e o ícone do aplicativo.
O texto das mensagens conserva a cor neutra para facilitar a leitura.
Os padrões do cliente web e dos assets acompanham as mesmas cores.

As preferências locais de cor base foram atualizadas; imagens, posições e a
opção existente de variar a tonalidade com o humor foram preservadas.
Validação: 128 contratos Qt passaram; prévia visual conferida e contraste
mínimo de 4,79:1 sobre o fundo dos cartões. Nenhum modelo ou áudio foi iniciado.

## Escopo

Mantida a aplicação QtWidgets existente, APIs, autenticação, filas e controles.
Nenhuma mudança cognitiva, modelo, memória, provider, scheduler ou chamada paga.
Não reiniciados os processos reais nem interrompidos rascunhos/captura do usuário.

## Alterações desta rodada

- `app/ui/native_style.py`: tema compartilhado e desenho raster dos orbes, sem OpenGL/WebEngine.
- `app/ui/central_native.py`: hierarquia de títulos, navegação, cartões por entidade, detalhes técnicos recolhíveis, formulários e controles estilizados; transição de página de 180 ms, sem timer contínuo de animação na Central.
- `app/ui/overlay.py`: gradientes, brilho, anéis e flutuação baseada no tempo; 33 ms por quadro ativo, 66 ms dormindo/offline. Animação parada quando oculto ou movimento reduzido. Estados continuam derivados do backend; pulsação não representa amplitude real do áudio.
- `app/core/central_control.py`: aceita somente booleano para `reduced_motion` no arquivo de preferências existente. Ausência do campo preserva comportamento normal; nenhuma migração.
- `testes/native_central_contracts.py`, `testes/test_central_refinamento.py`, `testes/test_central_control.py`: contratos de redução de movimento, renderização transparente, cores distintas, persistência/validação e timer real do overlay offscreen.

## Validação

- Suíte oficial: **74/74 grupos offline aprovados**.
- Central/refinamento: **34/34**, incluindo **32/32 contratos Qt**.
- Controle: **36/36**, repetido após o último ajuste do overlay.
- A primeira execução encontrou fixture que devolvia `{}` para configurações de interface. Corrigida para o contrato real `settings/revision`; não foi removida nenhuma verificação.
- Prévias Qt verificadas visualmente: dashboard, áudio e três orbes. São fixtures explicitamente identificadas, não evidência de entidades acordadas.
- Central offscreen, janela de 11,606 s: pico 90.588 KiB (~88,5 MiB), 0,434 s CPU (~3,74% de um núcleo, incluindo inicialização).
- Três orbes dormindo offscreen, janela de 1,901 s: pico 58.692 KiB (~57,3 MiB), 0,0384 s CPU (~2% de um núcleo). Movimento reduzido confirmou timers de animação em zero.

## Uso e limites

Reabrir a janela e o overlay carrega o novo visual. O backend precisa ser reiniciado cooperativamente para aceitar a nova preferência `reduced_motion`; as outras preferências permanecem compatíveis. Usar o encerramento seguro e o atalho existente, sem encerrar processos por força.

Configurações → Movimento reduzido → Salvar preferências desliga as animações. Fechar overlay continua sem encerrar entidades.

A fluidez, transparência, arraste e always-on-top no compositor real ainda precisam de confirmação humana. Os números offscreen não são um benchmark de uso prolongado ou medição de GPU. Páginas técnicas continuam exibindo os dados existentes: esta rodada não transforma JSON em métricas que o backend não fornece.
