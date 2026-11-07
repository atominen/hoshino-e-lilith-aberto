# Mapa do projeto e responsabilidade dos arquivos

Mapa iniciado em **14/10/2026**, ampliado em **24/10/2026**, sem mover o runtime. A estrutura
física já separa código, entidades e infraestrutura. Antes de mover/remover um
arquivo, localizar consumidores, imports, launchers, testes e aliases; nome
“antigo” não prova que deixou de ser usado.

## Pastas principais

| Caminho na raiz | Responsabilidade | Preservação/versionamento |
|---|---|---|
| `app/` | Central, mente, memória, ferramentas e Resource Manager existentes | Código versionável; `app/memory` é implementação, não banco mental |
| `entidades/hoshino/`, `entidades/lilith/`, `entidades/alistair/` | Estado individual de cada entidade | Identidade, memória, configurações e histórico reais ficam locais |
| `compartilhado/modelos/` | Executores compactos, stores Ollama, visão/imagem/áudio | Pesos/cache locais; não publicar nem apagar por organização |
| `compartilhado/ambientes/` | Ambientes Python e dependências | Instalação local; manter caminhos dos executáveis |
| `compartilhado/servicos/` | Bridges/backends já integrados | Fontes próprias/exemplos versionáveis; builds e dependências externos locais |
| `compartilhado/config/`, `compartilhado/runtime/` | Configuração e coordenação da infraestrutura | Dados reais locais; examples não secretos podem ser versionados |
| `laboratorio/` | Interface, professor, treinamento, curadoria e testes | Código/documentação versionáveis |
| `laboratorio-local/` | Bases HF, professor GGUF, corpora, perfis, jobs, adaptadores, logs | Ignorado pelo Git; não é outra instalação nem outra mente |
| `scripts/` | Inicialização/manutenção e verificadores existentes | Não executar migrations/downloads/limpezas só por estar nesta pasta |
| `testes/` | Catálogo e suíte isolada da aplicação | Dados temporários; hardware/local são categorias separadas |
| `pc2/`, `pacotes/` | Fontes/pacote do executor LAN de Alistair | Não transferir propriedade da entidade, banco mental ou credenciais |
| `docs/` | Índice, mapas, resultados datados, planejamento e histórico | Guias atuais separados de evidências históricas |
| `desktop/`, atalhos na raiz | Entradas da Central e compatibilidade | Preservar alvos/caminhos |
| `third_party/` | Origem/licenças de adaptações | Não confundir com código mental próprio |
| `arquivo/`, `compat/` | Legados e aliases compatíveis | Não remover sem mapa de dependências |

## Uma entidade não é seu checkpoint

```text
entidades/<id>/
├── entidade.json       manifesto
├── identity/           constituição, personalidade e modelo de si
├── memory/             SQLite/vetores próprios
├── runtime/            conversas, tarefas, diários, canais e entregas
├── workspace/          oficina própria
└── config/             configuração por entidade
```

Os algoritmos em `app/mind` e `app/memory` são compartilhados; vivências e
autoria não são. Treinar/selecionar um executor não move identidade ou memória
para outra entidade. Cache RAM/RM compartilhado também não mistura bancos.

## Entradas de operação

### Atividade própria e recuperação de contexto — 23/10

`app/core/initiative.py` conserva o ponto de retomada no
`entidades/<id>/runtime/estado_mente.json` existente e notas/observações na tabela
`episodes` do SQLite individual. Não há banco mental, agenda ou scheduler novo.
`autonomy.py` controla o escopo de execução; `dispatch.py` oferece as capacidades
escolhidas; `compaction.py` projeta resultados com referência ao recibo, sem
reescrever a identidade. [Contrato, limites e evidências](AUTONOMIA_CONTINUA_E_CONTEXTO_20261023.md).

Os dados desses registros continuam privados/locais. Organizar o projeto
não autoriza movê-los, exportá-los ao Git ou limpar experiências.

### Operação existente

`app/core/yi_companion.py` valida o recibo do terceiro executor Yi6B por entidade;
`scripts/verificar_yi_basico.py` é um ensaio físico opt-in, fora da suíte automática.
Os testes reais reprovaram e os pesos Yi foram posteriormente retirados.
O suporte permanece histórico, não um modelo instalado/ativo. O experimento
Qwen3-4B também foi removido, preservando o Qwen3.5-4B de Alistair.
[Retiradas e composição atual](SUBSTITUICAO_YI_EXECUTOR_RAPIDO_20261024.md);
[pesquisa de substituto 6B, ainda sem instalação](CANDIDATOS_6B_20261024.md).

`app/core/resource_profiles.py` calcula predefinições de custo por tarefa para
o `resource_manager.py` existente, sem alterar gates físicos ou criar outra
fila. Central → Recursos apresenta decisões históricas, não desempenho já
comprovado. [Auditoria, limites e reversão](PERFIS_DINAMICOS_RECURSOS_20261024.md).

`app/core/speech_perception.py` valida compreensão de mensagens faladas antes
de ações/aprendizado, usando somente o contexto do fio existente. Não é outro
ASR, banco ou histórico. [Contrato e testes](PERCEPCAO_DE_FALA_20261023.md).

- **Central:** `Hoshino e Lilith.desktop` / `iniciar_entidades.py`.
- **Hoshino individual/compatibilidade:** `iniciar_hoshino.sh`.
- **Laboratório:** Central → Laboratório Neural; painel localhost:8788.
- **Testes offline:** `rodar_testes.sh`; laboratório em `laboratorio/tests`.
- **Integrações existentes:** scripts de Discord/Minecraft continuam em seus
  caminhos; este mapa não solicita login, abertura, wake ou execução.

O launcher/supervisor e o backend continuam fontes de estado; documentos/UI
não devem inventar estado, preencher filas ou criar um segundo scheduler.

## Módulos do laboratório

| Área | Fontes existentes |
|---|---|
| Painel/API/UX | `painel.py`, `web/`, `integracao_central.py` |
| Catálogo, plano e jobs | `treinos_unificados.py`, `trabalhador.py` |
| Treino e monitoramento físico | `treino_nf4_curto.py` |
| Professor 35B | `professor_moe.py` |
| Esquema, extração e auditoria | `professor_schema.py`, `professor_auditoria.py`, helpers de `professor.py` |
| Perfil cognitivo versionado | `personalizacao.py` |
| Candidato, estável e rollback | `versionamento_lora.py` |
| Recuperação de executor local ausente | `recuperacao_modelos.py` |
| Política noturna no supervisor existente | `rotina_noturna.py` |
| Mods/cópias e CLI | `core.py`, `labctl.py`, `controle.py` |
| Contratos offline e ensaios explícitos | `tests/test_*.py`, `tests/probe_*.py`, `tests/browser.cjs` |

`experimentos.py`, `alistair.py`, `catalogo.py`, `autopreset.py` e outros módulos
de apoio/compatibilidade não são dispensáveis por nome. Alguns contratos e
adaptadores encaminham ao fluxo unificado. Runners antigos aposentados podem
ser importados por testes ou servir de evidência; não mover para criar uma
versão paralela nem reativar agendas antigas.

## Dados do laboratório e pesos de execução são coisas diferentes

```text
laboratorio-local/
├── modelos/ e modelos-extras/       bases locais de treino/pesquisa
├── professor-moe-35b/
│   ├── gguf/                       professor instalado
│   ├── trabalhos/ e propostas/      pedidos e curadoria
│   └── metricas/                    ensaios e logs privados
├── historicos-curadoria/            snapshots/perfis autorizados
├── pacote_neural_v3/                corpora separados por entidade
└── controle-laboratorio/
    └── treinamento-unificado/      jobs, versões, conversões, relatórios, backups
```

É um mapa de responsabilidades, **não lista de modelos instalados**. Outras
pastas privadas existentes não são lixo automaticamente. HF/Safetensors serve
como base de treinamento; GGUF/store Ollama serve à inferência. LoRA candidato,
checkpoint recuperável, estável aprovado e executor publicado têm contratos
distintos. A última estável não substitui o original; converter não aprova
qualidade ou autorização de deploy. Referências e metadados podem existir
depois da remoção autorizada de um peso; o catálogo precisa conferir o disco.

## Compatibilidade verificada nesta organização

- `/home/gustavo/hoshino` → `/home/gustavo/hoshino e lilith/compat/hoshino`.
- `/home/gustavo/laboratorio-lora` → `/home/gustavo/hoshino e lilith/laboratorio-local`.

Esses links não duplicam os dados. Ambientes/builds e referências antigas
podem depender deles. Nenhum foi movido/removido. Os nomes/caminhos dos
relatórios também permanecem, salvo trechos do README separados como histórico.

## Histórico da organização de14/10

O relato abaixo e suas contagens pertencem à organização de14/10, não ao
inventário ou validação atuais. A [entrega de24/10](SINCRONIZACAO_GITHUB_20261024.md)
registra as limpezas autorizadas posteriores e a nova suíte offline.

README de entrada atualizado, [índice por assunto](README.md), mapa acima e
[histórico do README](historico/README_20261011.md). Guias do laboratório e
handoff/manual mestre apontam ao estado atual antes de instruções históricas.
Links locais verificados; nenhum componente executável ou dado real alterado.

Não houve inferência, treino, instalação/download, limpeza mental, exclusão de
modelo, nova integração, habilitação de cloud/GPU concorrente ou mudança de
perfil térmico. Próximas correções do 35B estão no índice como **pendências**.

Validação desta organização: **182 links locais sem erro**, todos os **79
documentos Markdown de `docs/`** cobertos pelo índice; **74/74 grupos offline
e 262/262 testes do laboratório** aprovados. Os dois blocos históricos movidos
do README foram comparados com o backup, preservando o texto e ajustando só
os destinos dos links. A ajuda da CLI foi consultada sem iniciar servidor.

Backup único dos cinco guias anteriores em
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/documentacao-20261014/guias-antes.tar.gz`,
local e ignorado pelo Git. Código preexistente modificado preservado; sem
commit/push ou declaração de sincronização remota nesta rodada.
