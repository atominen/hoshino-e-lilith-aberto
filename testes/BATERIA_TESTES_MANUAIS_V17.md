# Bateria de testes manuais — Hoshino V17

Objetivo: testar entendimento de comandos, execução em múltiplas etapas, criação/alteração/execução de ferramentas, uso do sistema e persistência de abas.

## Como registrar

Faça os testes na ordem. Não ajude a Hoshino informando qual ferramenta ela deve usar. O objetivo é observar se ela escolhe e encadeia as capacidades sozinha.

Para cada teste marque: **PASSOU**, **PASSOU COM DESVIO** ou **FALHOU**.

Considere falha crítica quando ela disser que fez algo que não fez, inventar resultado/estado, esquecer uma etapa já explicitamente assumida, usar a aba errada, executar uma etapa depois de você mandar parar, ou entrar em loop.

Antes de começar, deixe a janela da Hoshino aberta e com diagnóstico/logs habilitados.

---

## T01 — comando simples

**Envie:**

```text
que horas são?
```

**Esperado:** uma resposta direta e uso de `get_system_time` quando necessário. Sem ferramentas irrelevantes.

---

## T02 — criação e leitura em duas etapas

**Envie:**

```text
Crie o arquivo ~/Hoshino-Testes/v17_duas_etapas.txt com exatamente a frase V17_ETAPA_1. Depois leia o arquivo e me diga exatamente o que ficou gravado.
```

**Esperado:** `write_file` → `read_file`. O conteúdo final deve ser exatamente `V17_ETAPA_1`.

**Falha crítica:** responder o conteúdo sem ter lido o arquivo ou esquecer a segunda etapa.

---

## T03 — oficina: criar projeto, escrever, executar e conferir

**Envie:**

```text
Crie na sua oficina um projeto chamado v17_manual. Dentro dele faça um main.py que imprime V17_OFICINA_OK. Execute o programa e depois leia o resultado para confirmar que realmente funcionou.
```

**Esperado:** criação → escrita → execução → leitura/verificação. Não basta afirmar que o arquivo existe.

---

## T04 — criar uma ferramenta própria e usá-la

**Envie:**

```text
Crie uma ferramenta própria chamada conta_teste_v17 que receba x e y e devolva x + y. Teste a ferramenta com 2 e 3.
```

**Esperado:** ferramenta criada, validada e ativada; resultado `5`.

Depois envie:

```text
Agora use a mesma ferramenta com 10 e 7.
```

**Esperado:** resultado `17`, sem recriar a ferramenta.

---

## T05 — alterar a ferramenta própria

**Envie:**

```text
Altere a conta_teste_v17 para multiplicar x por y em vez de somar. Depois teste com 4 e 5.
```

**Esperado:** nova versão da ferramenta, resultado `20`. A versão anterior deve continuar arquivada em `versoes/`.

Depois:

```text
Leia o código atual da conta_teste_v17 e me diga qual operação ela faz.
```

**Esperado:** leitura do código atual, sem confundir com a versão anterior.

---

## T06 — ferramenta própria quebrada e recuperação

**Envie:**

```text
Crie uma ferramenta própria chamada teste_recuperacao_v17 que tente dividir 10 por um argumento chamado divisor. Teste com divisor 0.
```

**Esperado:** falha real do teste e ferramenta não ficar falsamente marcada como saudável.

Depois:

```text
Corrija a teste_recuperacao_v17 para retornar 0 quando divisor for zero e, nos outros casos, fazer 10 dividido pelo divisor. Teste com 0 e com 2.
```

**Esperado:** `0` e `5`; ferramenta volta a ficar utilizável.

---

## T07 — sistema: criar, alterar e executar arquivo

Use uma pasta de teste que possa ser apagada depois.

**Envie:**

```text
Crie o arquivo ~/Hoshino-Testes/v17_sistema.py com um programa que imprima SISTEMA_V1. Depois altere o arquivo para imprimir SISTEMA_V2 e execute a versão atual pelo sistema. Me mostre a saída real.
```

**Esperado:** criação → alteração → execução. A saída precisa ser `SISTEMA_V2`.

**Falha crítica:** executar a primeira versão ou inventar a saída.

---

## T08 — abrir aplicativo específico

**Envie:**

```text
Abra o Firefox do sistema.
```

Depois:

```text
Liste as janelas abertas e me diga qual janela do Firefox está aberta.
```

**Esperado:** abertura real e identificação factual da janela.

---

## T09 — aplicativo sem depender de alias óbvio

Use um aplicativo instalado no seu Mint cujo nome não seja Firefox, Chrome, Discord ou Steam. Por exemplo, uma calculadora, editor de texto ou outro programa disponível.

**Envie:**

```text
Abra a calculadora do sistema.
```

**Esperado:** Hoshino deve localizar o aplicativo pelo sistema, não simplesmente procurar um executável com o mesmo nome.

Se o aplicativo não existir, ela deve dizer isso sem inventar que abriu.

---

## T10 — pasta específica

**Envie:**

```text
Abra no gerenciador de arquivos a pasta ~/Downloads.
```

Depois:

```text
Agora abra a pasta ~/Documentos, sem fechar a anterior.
```

**Esperado:** duas pastas/duas janelas ou abas reais, conforme o comportamento do gerenciador. A Hoshino deve saber que abriu uma segunda localização.

---

## T11 — site específico em nova aba

**Envie:**

```text
No navegador controlado da Hoshino, abra o YouTube em uma nova aba.
```

Depois:

```text
Liste as abas e me diga o ID estável da aba do YouTube.
```

**Esperado:** uma aba com ID do tipo `aba-XX` e URL do YouTube.

---

## T12 — duas abas independentes

**Envie:**

```text
Abra https://www.wikipedia.org/ em uma nova aba. Depois abra https://example.com/ em outra nova aba.
```

Depois:

```text
Leia as duas abas e me diga qual título e URL pertencem a cada uma.
```

**Esperado:** duas identidades diferentes e associação correta de título/URL.

---

## T13 — continuar na mesma aba

Pegue o ID da Wikipedia no teste anterior. Exemplo: `aba-01`.

**Envie:**

```text
Continue na aba ABA_ID. Role a página para baixo e depois leia novamente essa mesma aba. Não mexa na aba do example.com.
```

Substitua `ABA_ID` pelo ID real.

**Esperado:** a rolagem e a leitura acontecem na mesma aba; a segunda aba não muda.

---

## T14 — mudar de URL sem criar aba nova

Pegue o ID do example.com.

**Envie:**

```text
Na mesma aba ABA_ID, abra https://www.openstreetmap.org/ sem criar uma aba nova. Depois me diga a URL atual e o ID da aba.
```

**Esperado:** mesma `aba-XX`, URL nova.

---

## T15 — fechar uma aba sem quebrar as demais

**Envie:**

```text
Feche a aba da Wikipédia. Depois liste novamente as abas abertas e continue trabalhando na aba do OpenStreetMap.
```

**Esperado:** apenas a aba pedida é fechada; o ID da aba restante continua utilizável.

Esse teste é especialmente importante porque os índices podem mudar depois de uma aba ser fechada. A Hoshino deve usar o ID estável, não depender do índice antigo.

---

## T16 — voltar e avançar na mesma aba

Na aba restante:

```text
Volte uma página nessa mesma aba e depois avance novamente. No final me diga a URL atual.
```

**Esperado:** volta e avanço ocorrendo na mesma aba, sem abrir outra.

---

## T17 — conversa contínua sem repetir o contexto

Depois de manter uma aba aberta, envie mensagens separadas:

```text
O que tem nessa aba?
```

Depois:

```text
Agora continue nela e abra a página inicial do YouTube em outra aba.
```

Depois:

```text
Volte para a aba anterior e não altere a nova.
```

**Esperado:** Hoshino conserva a referência das abas entre mensagens e diferencia “aba anterior” de “nova aba”.

---

## T18 — comando composto misturando capacidades

**Envie:**

```text
Crie ~/Hoshino-Testes/misto_v17.txt com a palavra MISTO_OK, abra o Firefox, abra o YouTube no navegador controlado e depois leia o arquivo para confirmar o conteúdo.
```

**Esperado:** criação do arquivo + abertura do aplicativo + abertura do site + leitura do arquivo. A ordem pode ser otimizada quando não houver dependência, mas nenhuma etapa pode desaparecer.

**Falha crítica:** fazer só a primeira ou só a última ação porque a intenção principal apontou para uma única ferramenta.

---

## T19 — correção no meio da tarefa

**Envie:**

```text
Crie ~/Hoshino-Testes/nao_execute_v17.py com print('NAO_EXECUTAR'). Não execute o arquivo.
```

Depois:

```text
Na verdade, não execute mesmo. Apenas leia o conteúdo para conferir.
```

**Esperado:** leitura sem execução.

---

## T20 — erro real não pode virar sucesso imaginário

**Envie:**

```text
Abra o aplicativo HoshinoAplicativoQueNaoExisteV17 e depois me diga o que aconteceu.
```

Depois:

```text
Abra a aba aba-99-que-nao-existe e me diga o que aconteceu.
```

**Esperado:** erros factuais. Nenhuma afirmação de que algo foi aberto.

---

# Resultado final

Depois dos 20 testes, classifique separadamente:

- entendimento do comando;
- seleção da capacidade;
- execução da capacidade;
- passagem para a próxima etapa;
- verificação do resultado;
- persistência de contexto entre mensagens;
- identidade estável das abas;
- criação e evolução das ferramentas próprias;
- recuperação de erro;
- ausência de alucinação de execução.

Uma falha em um desses itens é mais útil que uma falha genérica “ela ficou confusa”: registre **qual etapa ela deveria ter feito, qual ferramenta chamou, qual resultado recebeu e o que fez depois**.
