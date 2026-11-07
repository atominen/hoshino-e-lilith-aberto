# DDGS e correção da fala duplicada — 25/10/2026

## Pesquisa DDGS

O projeto já declarava `ddgs>=9.16.0` em `requirements.txt`, mas o ambiente
principal não tinha o pacote: importação retornava `ModuleNotFoundError` e a
ferramenta informava indisponibilidade. Foi instalada a versão **9.16.0** no
mesmo ambiente, sem extras, outro serviço ou alteração de outras dependências.

Foram conferidos `DDGS.text(query, **kwargs)` e suporte ao contexto `with`.
A ferramenta existente importou normalmente e uma pesquisa pública de teste
retornou dois resultados de documentação oficial Python. O teste foi feito
pelo assistente para diagnóstico; não é uma pesquisa autônoma das entidades
nem entrou nas memórias ou conversas. A chave de rede permaneceu respeitada.

Referência da dependência: [DDGS 9.16.0 no PyPI](https://pypi.org/project/ddgs/9.16.0/).
Dependência opcional declarada não equivale a comprovação de instalação.

## Causa da repetição de fala

`Central.query()` descartava todo valor falso ao montar o endereço HTTP.
Isso descartava também o índice **0**, usado no primeiro trecho de áudio.
A interface pedia o áudio completo e depois reproduzia os trechos 1, 2 etc.,
repetindo parte da resposta. A síntese não estava sendo solicitada duas vezes
nos dois turnos recentes analisados.

O diagnóstico conferiu somente identificadores, contagens, hashes e durações,
sem copiar o conteúdo das conversas. Em um dos casos, o primeiro trecho tinha
0,975 s, mas o player reproduziu cerca de 5,8 s, correspondentes ao WAV completo;
em seguida reproduziu novamente o segundo trecho de 4,83 s.

A correção preserva valores numéricos zero no endereço e continua omitindo
campos ausentes, strings vazias e flags falsas. Uma regressão Qt reproduziu
`FULL_REPLY, SECOND` antes da correção e confirmou `FIRST, SECOND` depois.
O teste HTTP também confere que `chunk=0` entrega o WAV do primeiro trecho,
diferente do WAV completo. Não foi necessário mudar provedor, voz ou modelo,
nem fazer nova síntese paga.

## Aplicação e verificação

Backend e entidade foram encerrados cooperativamente, após conferência de
zero jobs ativos e leases. O frontend antigo permaneceu aberto sem backend;
sua instância foi identificada e encerrada por PID antes de editar o módulo
carregado. O auxiliar de atalho libera a escuta ao fechar seu stdin.

Verificação: **42 testes da Central** (incluindo os contratos Qt), **20 testes
de voz** e **44 verificações de integração** passaram. A regressão nova foi
observada falhando antes da correção e passando depois. A pesquisa real pelo
DDGS também retornou resultados; nenhuma síntese paga foi criada nesta rodada.

Central reaberta e janela nativa mapeada no desktop: backend **206516**,
frontend **206525**. Lilith foi retomada uma única vez por pedido registrado
como manutenção autorizada, pois estava acordada antes da parada; Hoshino e
Alistair permaneceram dormindo. A leitura autenticada confirmou Lilith
`awake`, zero jobs ativos e zero leases. A voz automática continua desmarcada
ao reabrir; o usuário pode marcar **Ler novas respostas em voz** para usá-la.

Logs locais: `/tmp/ddgs-voz-qt-regressoes.log`,
`/tmp/ddgs-voz-stream-regressoes.log` e `/tmp/ddgs-integracao-regressoes.log`.
