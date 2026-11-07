# Alistair no Xbox — preservação e otimização antes de migrar

**Decisão posterior ao ensaio:** em18/10 o usuário autorizou oficializar o
seletorPC/PC2/Xbox naCentral, sincronização técnica e início ao acordar.
[Implementação, limites e reversão](ALISTAIR_DESTINO_E_SINCRONIZACAO_20261018.md).
Os resultados e decisões anteriores abaixo são históricos. Aprovação de
qualidade continuafalse; cadastrar acesso e validar fisicamente o novo perfil
não pode ser substituído por testes offline.

## Decisão vigente —18/10/2026

O usuário escolheu **otimizar antes de migrar**. Isso substitui a hipótese
anterior de ativar imediatamente o Xbox no lugar do PC2. A Central e sua rota
continuam inalteradas; Hoshino/Lilith, identidades, memórias e treinos não mudam.
PC2 permanece completo em `pc2/` e `pacotes/alistair_pc2/`.
Não há autorização para novo treino, cloud, concorrênciaGPU ou rotina diária.

### Resultado mais recente —18/10,19:27America/Sao_Paulo

**Ganho real medido na bateria isolada; migração e qualidade ainda não aprovadas.**
Comparação ABBA concluída em5min25s: original→otimizado→otimizado→original,
com nova carga em cada etapa, três casos sintéticos e duas rodadas. Os seis
pares tiveram pedidos, respostas, contagens de tokens e término idênticos;
as12respostas terminaram naturalmente, sem truncamento/retry. Mesmo.6,
mesmos pesos/alpha/precisão, contexto2048, temperatura0/semente42 e33camadasGPU.

| Média de duas respostas por caso | Original host0 | Otimizado host1 |
|---|---:|---:|
| Código,181tokens |20,53s|16,03s|
| Texto,202tokens |22,02s|16,93s|
| Contexto,85tokens |23,05s|20,82s|

Para936tokens de saída por modo, o totalHTTP caiu131,20→107,56s:
**18,02% menos tempo /21,98% mais tokens por segundo ponta a ponta**.
A métrica primária pré-declarada, mediana das seis razões pareadas, foi1,2808
(+28,08%); o limiar útil foi satisfeito. Prefill nativo somado quase inalterado:
42,318→42,046s. Não há cronômetro nativo de decode/TTFT:HTTP−prefill é apenas
aproximação de geração+transporte, não taxa pura de geração.

Nas duas cargas host1, logs comprovaram248paresFP16LoRA emCPU/15,48MiB,
sem bufferLoRA GPU na ativação atual; base2569,25MiB/33camadasGPU preservada.
As62conferências extraídas das cargas, pós-pedidos e telemetria dos pedidos
passaram, comerrors[] em todos os pedidos. Picoamostrado host0:
app3535122432/GPU2828017664bytes; host1:app3533209600/GPU2811629568.
Essas62 não incluem preflight, observações de fechamento e observação final.
Não somar poolsUMA; sem termometria, estabilidade de horas ou comparaçãoAthlon.
189testes offline do cliente passaram; não são avaliação de qualidade do4B.

Qualidade: o código fez parse e contém trêsasserts, **não foi executado**.
Texto tem cinco itens, mas afirmações sobre privacidade, imutabilidade e
permissões não comprovam implementação. JSON de32registros válido, contagem
e cincoIDs corretos, porém somasERRADAS960/480/480, corretas1056/512/544,
iguais nos quatro estágios. O erro anterior10−5−3=4 também permanece registrado.
Ganho de desempenho não corrige raciocínio nem homologa personalidade.

**Recomendação: manter host1 como opção experimental útil.** Conforme combinado,
o ensaio terminou com o **perfil original host0 restaurado**, PID6368, flag0,
app ocioso/normal; última observação22:27:32UTC com margens aprovadas.
Não houve ativação definitiva da otimização nem migração daCentral.
Central/bancos/identidades/memórias/treinos/PC2 inalterados, nenhum upload de
pesos ou uso de conversa real. Último pacote.6 e fallback.5 preservados noPC.
Antes de integrar: contexto8K sem corte silencioso, ferramentas executadas
somente noPC, recibos fiéis, privacidade/persistência e revisão de qualidade.

Evidência bruta imutável `lora-host-ab-20261018.json`, SHA256
`1cff16c6b9c5450c8e72c53f7db9db4223d23c061e719f3dcc5c402d08690c02`;
revisão separada `lora-host-ab-review-20261018.json` na cópia de ensaio.
As seções abaixo preservam a cronologia anterior, inclusive bloqueios já
superados; não descrevem o estado atual quando dizem que host1 está pendente.

### Esclarecimento posterior — reduzir Dev Mode para25GB

O proprietário informou que reduzirá a reserva doDevMode para25GB e considera
que os dados do ambiente serão apagados. Autorização vigente: preservar a
última versão noPC, reconstruir primeiro apenas o executor4B e só depois
experimentar transcrição. **O banco de dados, identidades, memórias, histórico,
permissões e ferramentas ficam noPC; oXbox executa inferência.** Isso define
a futura integração, não a ativa agora. PC2 continua preservado.

Às16:43de18/10 foram conferidos novamente os pacotes.6(candidato mais recente)
e.5(referência já medida), seus recibos/certificados/dependência, e os dois
GGUF originais noPC por tamanho/cabeçalho/hash integral. Par4B+LoRA:
2725071168bytes, aproximadamente2,73GB. Não duplicar pesos sem necessidade.
O índice local `pacotes/xbox_alistair_1.6.0.6/reinstalacao-4b.json` guarda
caminhos/SHA e configuração sintética exata para reconstrução; o guia
`REINSTALACAO_25GB.md` registra a ordem e as verificações. O diretório do
instalador não inclui os pesos: preservar também os blobsPC referenciados.

Nenhuma conexão aoXbox ou operação de redimensionamento/limpeza foi feita
nessa preparação. Os recibos da duplicidade.5/.6 permanecem como falha
observada, não são apagados nem reaproveitados como autorização de replay.
Depois do reset informado pelo proprietário, exigir inventário/certificado
atual, provisionamento novo com recibo próprio, Game/PID/margens e hashes
físicos.25GB de armazenamento não aumenta aRAM/VRAM concedida ao processo.
Antes de contexto real, testar também que o executor não persiste prompts
em histórico/logs, não corta contexto silenciosamente e devolve propostas
de ferramentas sem executá-las noXbox. Não copiar bancos para o console.

### Desfecho do4B após a redução informada —18/10,17:06

O estado observado não estava vazio: ainda havia.5/.6, com configurações
sintéticas iguais e os dois GGUF nos tamanhos esperados. O instalador novo
parou na conferência, **sem nenhum upload**. Não presumir que o redimensionamento
apagou todos os dados nem que25GB foram medidos pelaAPI.

Uma abertura única foi permitida SOMENTE em diagnóstico: as duas versões
conhecidas tinham `resource-probe.flag=1\n`, nenhuma inferência concorrente e
controles fixados. O cliente antigo de disambiguar rejeitou a mudança no
inventário depois de ativar; seu recibo de falha permanece intacto. Consulta
nativa identificou.6/PID5060 sem modelo, limite5GiB e margens aprovadas.
O inventário autenticado subsequente confirmou **somente.6**, semCPUoriginal.
Não houve desinstalação realizada pelo cliente nem se afirma a causa exata
do desaparecimento do registro.5.

Antes do4B, base e adaptador foram lidos integralmente DOXbox e os doisSHA256
conferiram;2,73GB/246,3s de leitura, sem upload, conversão ou alteração de pesos.
Três amostras pré-carga passaram. Diagnóstico5060 foi fechado sem força;
somente a flag diagnóstica mudou1→0. A ativação normal fixou também o parâmetro
`package` com oPFN.6 completo, além de `appid`, conforme a
[API documentada daMicrosoft](https://learn.microsoft.com/en-us/windows/uwp/debug-test-perf/device-portal-api-core#start-a-modern-app).
Isso evita depender só doAUMID compartilhado por versões.

Execução física:PID5748,33/33camadasD3D12, buffer de pesos2569,25MiB,
LoRA runtime aplicado e `LoRA host placement: OFF (baseline)`. Duas respostas
terminaram porEOS; seis conferências em carga aprovadas, telemetria de cada
pedido comerrors[]. Picoamostrado3515367424bytesapp/2824347648GPU,
menores margens1853341696app/1161918874GPU. PoolsUMA se sobrepõem; não somar.
Não houve medição térmica nem ensaio prolongado.176testes offline passaram.

| Caso sintético | Resposta | ParedeHTTP | Avaliação |
|---|---|---:|---|
|Nome/papel em uma frase|“Meu nome é Alistair e sou um mordomo digital organizado e cordial.”|4,435s/18tokens|Acertou este caso; não homologa personalidade completa.|
|10min menos tarefas de5min e3min|“Quatro minutos sobrarão…”|4,823s/18tokens|**Errado: sobram2min.**|

**Funcionamento físico confirmado; qualidade e adoção de produção NÃO aprovadas.**
A otimização host1 não foi ativada/comparada e nenhum ganho foi comprovado.
Central, bancos, memórias, identidades, treinos ePC2 continuam inalterados.
Recibos: `after-resize-4b-smoke-20261018.json`(SHA256
`f3c970c5ae1db63016f7f68689b08a46cbaae6ab769ff840c7178123df5ceefb`)
e `after-resize-4b-review-20261018.json`, na cópia de ensaio.

Na consulta posterior de19:10(22:10UTC), oportal11443 aceitou conexão mas
aAPI11434 expirou ao conectar. Isso não desfaz o teste concluído às17:06,
nem prova crash, OOM ou serviço atualmente ativo. Não houve novo start/replay.
Pedir ao proprietário que mantenha o app.6 em primeiro plano e confirme antes
de reconciliar novamente e continuar uma comparação isolada. Transcrição e
integração real permanecem para depois; o erro aritmético não pode ser ocultado.

## App já preservado

Diretório local canônico: `pacotes/xbox_alistair_1.6.0.5/`.
Contém MSIX, dependência x64, certificado público, licença, três recibos e guia
de instalação/limites. Não contém pesos, senhas ou chaves privadas; fica fora
doGit, como os outros pacotes locais.

MSIX SHA256:
`2abbbb75a66e1674f1c0c3eaf9fb1176cdc10728ce40f62bd84113c9be830177`.
Origem: receita privada `atominen/xllama-xbox-4b-gpu`, commit
`e696179e37d7839e65d680b55b641df744f4f481`, run39128578779.
Não depender apenas da retenção temporária do GitHubActions.

Os seis arquivos foram comparados byte a byte com o ZIP original e sua cópia
extraída. Só depois o diretório emDownloads foi consolidado no pacote canônico
e o ZIP redundante eliminado. O app continua recuperável pelo diretório acima;
não se promete downgrade de versão, desinstalação ou reset deLocalState.
Também foram removidos13caches de código,4345856bytes, regeneráveis.
Nenhum banco, dataset, checkpoint, peso ou evidência de falha foi apagado.

## Resultado físico de referência

XboxSeriesS, app separado1.6.0.5, Game, contexto2048 e33/33camadasD3D12.
O par base+LoRA é o já existente; não houve conversão/fusão de pesos.

| Caso | Entrada/saída emtokens | Parede HTTP | Saída/parede |
|---|---:|---:|---:|
| Guia técnico |152/509|53,016s|9,60tokens/s|
|80registros sintéticos|893/418|69,698s|6,00tokens/s|

Ambos terminaram porEOS,23amostras completas semerro; não é ensaio de horas.
Limiteapp5GiB, orçamentoGPU3986266522bytes. Picoamostrado3,29GiBapp/2,63GiBGPU;
poolsUMA não devem ser somados. Não houve medição térmica. Não aprovar
qualidade: somas3600/1800 estavam erradas, corretas9720/4920.
Não há benchmark pareado no Athlon3000G: o Xbox é promissor, mas a comparação
de desempenho com aquela máquina permanece inferência, não medição.

Evidência local detalhada na cópia de ensaio:
`/home/gustavo/.codex/worktrees/xbox-4b-ensaio/hoshino e lilith/experimentos/xbox_4b/`.
Recibos brutos são preservados, não outra fila ou scheduler.

## Candidato atual — LoRA diretamente no host

A [implementação D3D12 fixada](https://github.com/gianlucamazza/xllama/blob/5271350761f75da6953a1644ea12f72e2bdd334f/src/bridge/ggml_d3d12.cpp)
aceita os matmuls quantizados, não os FP16 doLoRA. O adaptador estava alocado
emD3D12_Weights; o fallbackCPU pode exigir readback/transferências dessas
matrizes. Não é evidência de que todas as operações rodem naGPU.

O candidato testa somente a alocação dos pares FP16 doLoRA emRAMCPU, mantendo
os mesmos valores, alpha, operações, amostragem e33camadas base naGPU.
Não faz fusão/quantização, troca de modelo, shader novo, overclock ou ajuste
de proteção. Um ganho é hipótese até comparação física.

- Ausência ou `0\n` em `LocalState/gguf_lora_host.flag`: loader original.
- `1\n`: opt-in no próximo carregamento. Arquivo inválido bloqueia carga.
- Só alterar com o app owned confirmado fechado. Retorno pelo valor0 e nova
  ativação; não usar desinstalação/reset para voltar.
- Função nova preserva a API original e só muda paresFP16 cujo buffer base
  seja exatamenteD3D12_Weights. Zero pares elegíveis falha explicitamente.
- Fontes xllama/llama.cpp e três hashes foram fixados; todos os inputs são
  validados antes do patch.27testes locais passaram, incluindo parserC++
  compilado. Isso não substitui compilação Windows nem teste noXbox.

Receita candidata: `1995d6313acf3c3adf4648a2062cd3d888c36045`.
[Compilação única6](https://github.com/atominen/xllama-xbox-4b-gpu/actions/runs/39155164682),
limite20min, sem deploy automático. Concluiu com sucesso em cerca de12min,
incluindo compilação nativa, SignTool e verificação dos marcadores compilados.

Candidato1.6.0.6 salvo em `pacotes/xbox_alistair_1.6.0.6/`:
MSIX20948627bytes, SHA256
`b445df909ea8d7cdb962b4013114e1ad7b95cd2391e3c5449811ebec15fbe3df`.
Digest doZIP, CRC/allowlist de7arquivos, hashes individuais e certificado
correspondente ao signer incorporado conferidos. OZIP temporário foi removido
após a extração verificada.132testes offline do cliente passaram; nenhuma
atualização, mudança de flag ou inferência nova noXbox nesta preparação.
**Atualização aceita; bloqueado antes de abrir o diagnóstico. Sem ganho medido.**

### Atualização física —18/10,16:10–16:13America/Sao_Paulo

Após o proprietário confirmar ambos os apps fechados, o inventário autenticado
comprovouCPUoriginal+.5inativos. O cliente fixou a folha pública nova doWDP,
assinatura/issuer/IP/datas conferidos contra a mesma raiz já conhecida; não
desativouTLS ou mudou confiança do sistema.143testes offline passaram antes
da chamada (14contratos do atualizador/reconciliação passaram depois).

Uma única sequência foi aceita: flag diagnóstica0→1(HTTP200), certificado
público(HTTP200), pacote.6+dependência(HTTP202). Estado da instalação informou
Success/Code0, mas o inventário passou a listar **.5 e .6 simultaneamente**.
O cliente parou antes da ativação. Uma reconciliação separada, somente leitura,
confirmou a duplicidade em10observações. Nenhum pacote foi reenviado, nenhuma
ativação/inferência aconteceu e o opt-inLoRA não mudou. Não classificar o
update como versão atual única homologada nem como benchmark.

Recibos brutos preservados na cópia de ensaio:
`gpu-lora-host-update-20261018.json`(SHA256
`e7a400e0a0266e1b29ea47a144e520b0fa0c20716672705e934dbce8bd601094`)
e `gpu-lora-host-reconciliation-20261018.json`. OCPUoriginal continua no
inventário; arquivos/identidades/treinos/rotas daCentral não foram alterados.
A preservação pós-update deLocalState ainda precisa ser conferida: não
inferir isso apenas do aceiteHTTP ou do inventário.

Próximo passo solicitado: reinício manual peloDevHome, sem sair doDevMode,
apagar apps ou resetarLocalState. Depois reconciliar somente leitura antes
de qualquer ativação. Exigir novamente Game/orçamentos reais, dados técnicos
preservados e versão/PID inequívocos antes de carregar o4B. Se a duplicidade
persistir, investigar registro/instalação sem desinstalar automaticamente.

## Gates de migração — estado após a comparação

1. Compilação nativa, assinatura e hashes aprovados; pacotes.6/.5 preservados.
2. .6única, GGUF preservados/hash integral aprovado, Game5GiB confirmado.
   O registroCPUoriginal não apareceu no inventário pós-redução; os arquivos
   e o materialPC2 noPC continuam preservados. Sem carga4B emApp1GiB.
3. Comparação pareada33/contexto2048 concluída acima, com ganho útil sem
   regressão das saídas ou pressão amostrada. Sem homologar estabilidade longa.
4. Perfiloriginal restaurado; host1 recomendado, não ativado definitivamente.
5. Antes da migração, a Central precisa de contexto até8192 e
   tradução fiel das chamadas/recibos de ferramentas. O xllama tem propostas
   de ferramentas, mas esse par4B ainda não foi homologado nessa rota.
   O servidor também pode cortar turnos antigos para caber: a integração
   precisa impedir essa perda silenciosa antes de enviar memórias reais.

Central, serviços de produção, personalidade e conteúdo mental permanecem
inalterados. As alterações físicas ficaram restritas ao app experimental do
Xbox e às flags explicitamente registradas na cronologia acima.
