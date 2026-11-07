# Memória, caderno visual e continuidade — 22/10/2026

Implementação incremental da [auditoria de21/10](REVISAO_COGNITIVA_E_ESTRATEGIA_20261021.md).
O código foi alterado; nenhum banco mental real, identidade, gosto já existente,
modelo ou treino foi modificado. Sem reinício de serviços, inferência real,
professor, quota externa ou publicação no GitHub nesta rodada.

## O que mudou

### Integridade e relevância das lembranças

- `remember` não substitui mais uma memória pela mera semelhança entre frases.
  Preferências por café de manhã e à noite coexistem. Atualização do mesmo
  atributo continua disponível pela chave explícita, respeitando as guardas
  de autoria já existentes. Não se tenta adivinhar conflitos semânticos.
- Recência calcula o mesmo instante com offset UTC ou no formato local legado,
  sem reescrever datas. Datas inválidas/futuras não ganham prioridade ilimitada.
- Recência, confiança e frequência de acesso só ordenam candidatos relevantes;
  não conseguem, sozinhas, trazer a bicicleta de alguém numa pergunta sobre
  a capital da Mongólia. Distâncias negativas, infinitas e NaN são descartadas.
- Uma correspondência exclusivamente vetorial exige similaridade transformada
  de pelo menos0,7 (`1/(1+distância)`). É um limiar conservador de engenharia,
  **não uma probabilidade de correção nem um benchmark calibrado**. A comparação
  lexical permanece como alternativa. Reavaliar com consultas reais antes de
  afirmar precisão/abrangência da recuperação.
- Episódios sugeridos pelo vetor são reconsultados no SQLite. Texto antigo,
  registro excluído/inativo ou ID órfão no índice não vira lembrança no contexto.
  O histórico integral continua disponível pelas consultas próprias; o recorte
  vetorial não representa toda a conversa.

### Individualidade e conversa

- O gosto declarado pelo interlocutor fica registrado como gosto **dele**.
  Não provoca mais `registrar_gosto` na entidade. Gostos antigos não são apagados.
- Código, citações e blocos citados deixam de ser tratados como indícios de
  afeto/curiosidade da entidade. Perguntas de confirmação não bastam para
  inferir curiosidade; uma recusa não gera evidência de teimosia.
- Reclamações que citam alvos técnicos, como app, comando ou microfone, não
  geram automaticamente apreciação afetiva de crítica pessoal. Feedback misto
  fica indeterminado. Essas regras são conservadoras, não compreensão semântica
  completa de sentimento, intenção ou personalidade.
- A orientação comum de conversa preserva autoria e correções recentes, evita
  reiniciar apresentações e perguntas respondidas e orienta pedir esclarecimento
  quando faltar o referente de “continue/isso/pronto”. Trocar de assunto não
  significa retomar qualquer tarefa antiga do mesmo fio.
- O tom continua vindo da identidade própria e do contexto; não há respostas
  prontas novas, outro LLM julgador ou execução automática de tarefas.

## Oficina: o que já existia e o que faltava

O desenho original já estava implementado: nós, relações dirigidas, condições,
exceções, graus de confiança e tabelas; editor Qt com arraste; revisões preservadas
nas próprias memórias e referências verificadas. O diário também já existia,
separado do recall público e com compartilhamento explícito de trechos.

Faltava um caminho honesto para **pensar antes de ter evidência**. Exigir um
episódio já registrado até para uma hipótese incentivava inventar uma fonte.

Agora `oficina_logica` e o editor usam dois modos:

| Modo | Fontes | Significado armazenado |
|---|---|---|
| Rascunho | Opcionais, verificadas quando fornecidas | Hipótese, rotulada como não validada |
| Com evidências | De1 a30 IDs locais existentes | Interpretação revisável; não fato confirmado |

Rascunho sem fonte não admite nós afirmados como observações/eventos/fatos
informados nem setas com base em observação/fonte informada. Hipóteses e conceitos
podem ser livres. Para acrescentar evidências, cria-se revisão com motivo e
referência à anterior. Uma revisão substituída não retorna falso sucesso se
reenviada. Não há segundo banco, scheduler ou motor de desenho.

A ferramenta agora descreve o formato dos nós, relações e tabelas no contrato
recebido pelo modelo. O roteamento a encontra para rascunhos, mapas mentais,
hipóteses, gráficos e problemas complexos. Notas pessoais também disponibilizam
o diário. Ter a ferramenta disponível **não prova que o LLM saberá usá-la bem**.

### Diagrama não é gráfico numérico

O caderno visual organiza dependências e comparações. Para curvas, medições,
gráficos de funções ou simulações, permanece o caminho existente de código e
arquivos na oficina, sujeito às permissões normais. Não foi criado um renderizador
matemático novo nem usado gerador de imagens como substituto de cálculo.
Diagramas são opcionais: uma pergunta simples não exige uma gravação persistente.

## Validação e limites

Regressões em `test_refinamento_cognitivo.py` cobrem convivência/correção de fatos,
relevância, datas, índices obsoletos, autoria dos gostos, sinais textuais,
rascunhos, fontes falsas, promoção a interpretação e revisões. O caminho de
ferramenta foi exercitado sob as identidades de Hoshino e Lilith usando bancos
descartáveis. O editor possui teste Qt para salvar sem referências inventadas
e para preservar o modo com evidências. Isso não é avaliação de LLM real.

Resultado final: **82/82 grupos offline aprovados**, incluindo as15 novas
regressões. Log: `/tmp/refinamento-cognitivo-final-20261022.log`.
O grupo de Central/oficina também foi executado separadamente após os últimos
ajustes de interface: **42 testes aprovados**, incluindo seu subprocesso Qt;
log `/tmp/refinamento-oficina-ui-20261022.log`. `git diff --check` sem erros.

A primeira passagem teve81/82: o teste antigo de Hoshino exigia substituir
“respostas diretas” por “respostas diretas e curtas” apenas por similaridade.
A expectativa foi corrigida para coexistência sem chave explícita; a regressão
nova confirma separadamente que uma correção com chave continua substituindo
o atributo anterior. A regra defeituosa não foi restaurada para satisfazer o teste.

Pendências ao encerrar esta primeira etapa (avanço posterior em
[audiência e prioridade](AUDIENCIA_E_PRIORIDADE_MEMORIAS_20261022.md)): filtro de audiência em **todos** os caminhos
semânticos/derivados para impedir transferência de contexto direto ao global;
importância Ferro/Ouro/Diamante/Platina no ranking cognitivo; busca de grande
escala sem varrer a memória inteira; calibração longitudinal de personalidade
e qualidade natural das respostas dos modelos. Não tratar estes itens como
concluídos pela aprovação de testes mecânicos. A auditoria anterior continua
sendo o registro desses limites.

## Desafio futuro

O [desafio autoral do buraco negro](DESAFIO_AUTONOMO_BURACO_NEGRO_20261013.md)
permanece **não iniciado**. A referência de[kavan010](https://github.com/kavan010/black_hole)
foi conferida, sem clone, instalação, execução ou inserção de solução nas memórias.
Os requisitos e a separação entre ajuda de infraestrutura e autoria das entidades
continuam no documento existente. Não confundir uma ferramenta de diagramas
aprovada em testes com a capacidade já comprovada de criar essa simulação.
