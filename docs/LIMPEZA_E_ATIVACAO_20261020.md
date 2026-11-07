# Limpeza autorizada e ativação de Hoshino/Lilith — 20/10/2026

## Escopo autorizado

O usuário autorizou remover os três itens apresentados na análise de espaço,
atualizar o GitHub privado e investigar a ativação de Hoshino/Lilith. Após o
diagnóstico, confirmou explicitamente corrigir o lançador e publicar. Não é
autorização para apagar outros checkpoints, trocar modelos, despertar entidades,
iniciar treinos/professor ou limpar memórias.

## Arquivos removidos do PC

| Diretório relativo à raiz | Espaço ocupado antes |
|---|---:|
| `laboratorio-local/controle-laboratorio/treinamento-unificado/conversions/qwen35-9b/c13d1be90065aabc1d5f3abbb2874827f634860590cbe1f204448b7ac8551ec0` | 6.547.296.256 bytes |
| `laboratorio-local/modelos-extras/defiant-fable-9b` | 6.829.031.424 bytes |
| `laboratorio-local/modelos/qwen3.5-0.8b` | 1.770.098.688 bytes |

Total dos três alvos: **15.146.426.368 bytes (~15,15 GB decimais)**.
A pasta completa passou de201.153.318.912 para186.006.900.736 bytes
(~186,01 GB), após preservar o pequeno recibo de conversão antigo. Medida de
blocos ocupados, não tamanho de download ou apenas soma aparente dos pesos.

Antes de remover: caminhos explícitos conferidos, sem diretórios simbólicos ou
links para dados externos e sem consumidores encontrados nos comandos, mapas
de memória ou arquivos abertos dos processos acessíveis do usuário. A antiga
conversão9B não tinha referência nos módulos/configurações atuais, apenas no
próprio `converted.json`; o contrato atual usa a conversão `c4b1e81b916b…`.

Preservado o metadado em
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/remocao-modelos-20261020/converted-qwen35-9b-legado.json`.
Não foi criada outra cópia local dos15GB de pesos. Para recuperar os modelos
experimentais seria necessário novo download; a conversão antiga exigiria
reconversão/reobtenção compatível. Registros dos ensaios e suas falhas permanecem.

Preservados os sete candidatos selecionados, checkpoints anteriores, bases HF
originais6B/7B/9B/4B, professor35B, modelos de voz/imagem, ambientes, memórias,
identidades, configurações, material do PC2 e pacotes Xbox. Não houve limpeza
de blobs Ollama, promoção ou substituição de modelos. O catálogo continua
podendo citar os experimentos removidos, mas peso ausente não é instalação e
nada é baixado automaticamente por abrir a Central.

## Diagnóstico da ativação

No momento da verificação, a Central e os endpoints Ollama11435/11436 estavam
fechados/inacessíveis. Isso não foi tratado como prova de defeito nos pesos.
Não se abriu a Central nem se acordou alguém para fabricar um teste físico.

As verificações estruturais existentes passaram para ambas. As seis seleções
6B/7B/9B de Hoshino/Lilith têm aliases presentes e recibos de versão válidos nos
respectivos stores. Principais atuais:9B treinado; leves:7B treinado. Portas e
armazenamentos permanecem separados, sem apontar Lilith para Hoshino.

**Falha concreta reproduzida:** o helper `scripts/ambiente.sh` acrescentava
somente `app/` ao `PYTHONPATH`. Ao executar o script absoluto
`app/entity_runner.py`, o Python não inclui automaticamente a raiz/cwd na busca.
O seletor de executores importa `laboratorio.recuperacao_modelos` e também
depende de `scripts/`; sem a raiz, o catálogo de ambos falhava com
`ModuleNotFoundError: No module named 'laboratorio'` antes da chamada ao modelo.
Um ambiente interativo com a raiz já exportada podia mascarar esse defeito.

O lançador Xbox já tinha uma exportação específica da raiz, mas isso não
cobria o caminho normal Hoshino/Lilith. As verificações anteriores da suíte
também forneciam a raiz explicitamente, por isso não detectavam esse cenário.

## Correção autorizada

O helper comum agora exporta **raiz + app + path herdado**, usando caminhos
físicos ancorados no projeto. Não depende do diretório de abertura da janela
ou do ambiente do terminal. Não muda modelos, portas, .env, identidade,
permissões de ferramentas, política GPU ou arquivos mentais.

Novo teste de regressão no grupo existente `test_estrutura_entidades`:
processo filho com ambiente limpo, script de entrada absoluto e fixtures para
Hoshino/Lilith/Alistair, sem .env real, rede, modelo ou entidade. Antes da
correção: os três subcasos falhavam pelo módulo ausente. Depois: **9/9 testes**
do grupo passaram. O teste verifica resolução dos módulos e separação das
variáveis, não simula uma inferência bem-sucedida.

Repetida a conferência com os aliases reais no mesmo caminho de importação:
catálogos de ambas sem erro, principal9B treinado com perfil medido20camadas,
leve7B treinado e pré-verificação de recuperação `ready/needed=false`.
Esse diagnóstico bloqueou explicitamente novas partidas de workers e escritas
no registro. Nenhuma carga de pesos ou recuperação foi iniciada.

Suíte oficial completa após a correção: **77/77 grupos offline**, exit0, pelo
runner isolado existente. Sintaxe dos scripts conferida com `bash -n` e diff
preparado sem erros de espaços. Nenhum teste usou modelos/rede/bancos reais.

Logs locais:

- `/tmp/ativacao-hoshino-lilith-20261020-regressao-antes.log`
- `/tmp/ativacao-hoshino-lilith-20261020-regressao-depois.log`
- `/tmp/limpeza-ativacao-20261020-oficiais.log`

A correção será usada na próxima abertura/ativação normal. Funcionamento físico
com geração, voz, personalidade e convivência prolongada não é comprovado por
esta verificação sem carregar modelos.

## Publicação e limites

Código do helper, regressão e este relatório na mesma branch privada de entrega
`laboratorio-v11-organizacao-20261012`/PR#1, sem force push, merge automático ou
modificação do PR#2. Pesos removidos eram dados locais ignorados; o GitHub não
era backup desses pesos e não pode restaurá-los. Nenhum banco/configuração
real, segredo, ambiente, peso ou log privado entra no commit.
