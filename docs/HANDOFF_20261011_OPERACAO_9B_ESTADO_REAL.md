# Handoff operacional — Qwen3.5-9B Uncensored multimodal (11/10/2026, 13:49 BRT)

**LEIA PRIMEIRO se for retomar o trabalho em outro chat.** Documento produzido a partir de saídas reais do terminal fornecidas pelo operador e dos procedimentos versionados no repositório privado. **Não é prova de conclusão do download ou treinamento.** Caminhos com `~` representam a pasta pessoal no Linux Mint do operador. Fuso `America/Sao_Paulo` (UTC−03 na data).

## 0. Estado preciso no momento da transferência

| Componente | Última evidência | Interpretação |
|---|---|---|
| Orquestrador 9B v1.4 | PID histórico 66998 **não existe** (duas consultas `ps` vazias) | NÃO está em execução nem pausado; um PID no arquivo de estado não comprova processo vivo |
| Downloader filho | PID histórico 66999 **não existe**, `pgrep` sem correspondências | Download **interrompido**, não está transferindo agora |
| HF Safetensors final | `model.safetensors` não existe | Modelo não concluído; não fazer probe/treinamento |
| Pasta HF de destino | `du -sh = 18G` às 13:47 e 13:49 | Ocupação de disco, **não** conclusão verificada |
| Parcial antigo | `.../download/...1cd297d8.incomplete` = 1.024.000.000 bytes; modificado 01:03:02 | Preservar, não confundir com modelo válido |
| Parcial da retomada | `.../download/...68163666.incomplete` = 17.731.420.160 bytes; modificado 13:41:58 | Aproximadamente 94,2% do peso monolítico esperado, mas incompleto e sem hash/renomeação final |
| Peso monolítico esperado | `model.safetensors` ~18.819.721.632 bytes (conforme erro HTTP) | Faltam dados da transferência; não presumir integridade |
| Status persistido | `stage=deleted`, `status=failed`, `at=2026-10-11T03:19:31-0300` | Estado **antigo** da primeira falha; ausência de atualização na retomada não é confirmação de conclusão |
| `last_error` persistido | `Subprocesso falhou com código 1. Verifique os logs; etapas seguintes não serão iniciadas.` | Falha histórica anterior; verificar a causa da saída mais recente separadamente |
| Timer user systemd | `lab-retomar-9b-66998-6276946.timer`, agendado 21:00 11/10/2026 | Registro apareceu anteriormente, mas aponta para **PID morto**. Não supor retomada automática válida às 21h |
| Disco | `/dev/nvme0n1p2`: total 817G, usado 721G, livre 55G, 93% | Necessário recalcular antes de converter GGUF e baixar outros modelos |

**Diagnóstico:** após o erro de conexão Hugging Face, o processo filho chegou a 17,7 GB parciais e encerrou/desapareceu; o processo pai também não existe. O log da retomada termina em `Trying to resume download...`, sem traceback final adicional no trecho fornecido. **Não é possível afirmar por que ambos terminaram** (não inventar OOM, SIGKILL, falha de rede definitiva, morte do terminal ou bug). Às 13:49, `ps -p 66999` já não retornava linha. As duas verificações posteriores mostram ambos ausentes. A automação ainda NÃO executou provas de 9B, LoRA 9B, exportação nem comparação.

## 1. Objetivo do experimento 9B

- Baixar **apenas** `ccharnkij/Qwen3.5-9B-Uncensored`, revisão fixada `cfcad5b1d1771e7803e08c49fb3dfcd202182f8c`, Safetensors multimodal texto+visão, ~18,8 GB decimais; não baixar outro Qwen oficial para esse adaptador.
- Mesmo modelo-base para Hoshino e Lilith, **adaptadores LoRA separados**, dados de cada entidade isolados. Dataset neural v3: **722 train, 131 validation, 104 holdout por entidade** (corpus sintético estruturado; conferir arquivos antes de executar).
- Probes obrigatórios de BF16/NF4, forward/backward real e visão no ROCm, sem fallback CPU silencioso, antes de aprovar treino. Para modelo multimodal usar `Qwen3_5ForConditionalGeneration`/AutoProcessor onde compatível; pesos de visão congelados na adaptação textual.
- Se probes aprovados: até **300 minutos Hoshino + 300 minutos Lilith, sequenciais**; tempo de download/probe/export não conta nas 10 horas.
- Checkpoints LoRA periódicos e validação; interrupção antecipada se piorar. Não há retomada exata do otimizador comprovada.
- Converter base para GGUF Q4_K_M, produzir `mmproj-f16.gguf` separado, converter LoRAs separadamente; testar texto no Ollama isolado **11555** e visão em llama.cpp **11556**, sem declarar visão no Ollama baseada num segundo `FROM`. **Nunca** instalar em produção automaticamente.
- Modelos Ollama antigos foram removidos **anteriormente com autorização expressa** (~20,92 GiB), mantendo bancos, identidades, código, memórias e diários; não repetir exclusão nem reset.

## 2. Cronologia factual relevante

1. Foram montados pacotes `automacao_9b_vision_v1` a `v1_4`; ajustes trataram links simbólicos, limpeza limitada, verificação ROCm, exportação GGUF e testes visão/texto. Ferramentas llama.cpp instaladas localmente; checkpoint grande 9B não tinha backward validado.
2. Primeira execução em 11/10/2026, 03:19:31-03: download falhou com **CAS/Xet** `File reconstruction error: CAS Client Error ... error decoding response body`; limpeza anterior já concluída; estado persistido `stage=deleted,status=failed`; ~996MB parciais.
3. Validados ausência de processo antigo e `stage=deleted`; retomada **sem nova limpeza**, usando `automacao_9b_vision_v1_4/orquestrar_9b.py start` com ambiente `HF_HUB_DISABLE_XET=1`, `HF_HUB_DOWNLOAD_TIMEOUT=120`, `HF_HUB_ETAG_TIMEOUT=60`, e `-u HSA_OVERRIDE_GFX_VERSION`. Processos observados: orquestrador `66998`, downloader `66999`. Log `~/laboratorio-lora/logs/9b-vision-retomada.log`.
4. Progresso por ocupação da pasta: ~996 MB → 1,5 GB → 1,6 GB → 17 GB → 18 GB; `0/9` no tqdm significa **0 arquivos concluídos**, não 0 bytes recebidos. Aviso `unauthenticated requests` não era, por si só, falha fatal.
5. Usuário precisaria do PC de dia; pai recebeu `SIGSTOP` (mais tarde `STAT=T` confirmado) e filho ficou `STAT=Ssl`, com timer **21:00** `lab-retomar-9b-66998-6276946.timer`. Portanto o downloader seguiu transferindo enquanto o treino ficou bloqueado.
6. Log reportou erro HTTP `peer closed connection without sending complete message body (received 983687458 bytes, expected 18819721632)` e `Trying to resume download...`. O texto `received...` é referente à resposta interrompida, não aos bytes totais retidos na pasta.
7. Às **13:47:05**: 18G no diretório, parcial atual `17.731.420.160 bytes` com mtime 13:41:58 e antigo `1.024.000.000 bytes`; ao medir de novo às **13:49:05** continuou 18G, mas PID 66999 já não existia.
8. Verificações seguintes: `ps -p 66998,66999` **vazio**, `pgrep -af '[b]aixar_9b.py|[o]rquestrar_9b.py'` **vazio**; `model.safetensors` ausente; `orquestrar_9b.py status` ainda mostrou a falha histórica 03:19 e PID salvo 66998; log da retomada sem novas mensagens depois de `Trying to resume download...`. Esse é o **último estado real** conhecido.

## 3. Caminhos e comandos importantes

```text
Projeto / checkout:                ~/hoshino e lilith/
Venv ROCm:                        ~/laboratorio-lora/.venv-rocm/
Automação 9B:                     ~/laboratorio-lora/automacao_9b_vision_v1_4/
Orquestrador:                     automacao_9b_vision_v1_4/orquestrar_9b.py
Downloader:                       automacao_9b_vision_v1_4/baixar_9b.py
Modelo HF parcial:                ~/laboratorio-lora/modelos/qwen3.5-9b-uncensored-hf/
Cache HF incompleto:              [modelo]/.cache/huggingface/download/*.incomplete
Log retomada:                     ~/laboratorio-lora/logs/9b-vision-retomada.log
Estado:                           ~/laboratorio-lora/experimentos/orquestrador-9b-vision-v1-4/estado.json
Timer obsoleto (precisa conferir): lab-retomar-9b-66998-6276946.timer
Portas de laboratório:            8787 (painel); 11555 (Ollama 9B); 11556 (visão llama.cpp); 11557 (Ollama 6/7B); 11558 (professor)
```

Leituras **sem efeitos** para o próximo chat:

```bash
cd ~/laboratorio-lora
source .venv-rocm/bin/activate
date
pgrep -af '[o]rquestrar_9b.py|[b]aixar_9b.py' || true
python automacao_9b_vision_v1_4/orquestrar_9b.py status
du -sh modelos/qwen3.5-9b-uncensored-hf
ls -lh modelos/qwen3.5-9b-uncensored-hf/model.safetensors || true
find modelos/qwen3.5-9b-uncensored-hf -type f -name '*.incomplete' \
  -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n'
df -h ~
tail -n 50 logs/9b-vision-retomada.log
systemctl --user list-timers --all | grep -Ei 'lab|9b|retomar' || true
```

**Não colar nem enviar tokens HF, credenciais, bancos SQLite, diários ou dados reais ao GitHub.**

## 4. Conduta para recuperar com segurança (não é autorização para começar imediatamente)

1. Antes de qualquer reinício, confirmar que nenhum 9B ou pipeline associado está ativo e que a interface/lock de recursos não reserva GPU indevidamente. Fazer `df -h` e checar estado dos parciais. Não apagar `.incomplete` por impulso.
2. O timer 21h ainda registrava PID **66998**. Se esse PID estiver morto, o executor `resume-if-same` com verificações anti-reutilização deverá recusá-lo; **não assumir que o timer fará nova execução do orquestrador**. Inspecionar `systemctl --user cat lab-retomar-9b-66998-6276946.timer` e `.service`. Se confirmado obsoleto, parar/desabilitar o timer transitório de forma pontual, depois replanejar com o novo processo — não mandar `SIGCONT` manual para PID desconhecido.
3. Inspecionar logs adicionais do sistema/daemon/HF e status do script, **sem concluir a causa da morte apenas pelo último trecho do log**. Verificar permissões, relógio, processos restantes, espaço e versão Hugging Face. `HF_HUB_DISABLE_XET=1` confirmado no processo 66999 anteriormente, mas isso sozinho não prova que toda rota usou transporte sem Xet.
4. Investigar se os `17.731.420.160` bytes são recuperáveis pelo `huggingface_hub`/snapshot_download. Se for preciso fazer retomada, usar a **mesma revisão fixa e diretório**, sem repetir a exclusão Ollama. A automação v1.4 tinha retomada desde `stage=deleted` demonstrada; verificar **código atual** e estado antes de novo `start`. Nunca usar novamente a opção de limpeza destrutiva.
5. Como é 11/10 e o usuário reservou a **janela a partir de 21h**, mesmo que o download volte durante o dia, impedir probes/treino até essa janela por mecanismo persistente; antigo pai pausado não existe mais. Se o processo mudar, timer anterior não o libera. Não contornar bloqueios de concorrência do Laboratório.
6. Probes reais de treinamento e visão precisam ser concluídos antes de permitir até 10 horas de LoRA; se falharem, salvar evidências e interromper.
7. Se faltar disco para pesos + GGUF F16 intermediário + Q4 + mmproj + checkpoints, não apagar históricos, identidades, arquivos desconhecidos nem downloads úteis sem plano e aprovação.

## 5. Armadilhas documentais a evitar

- A frase antiga "a retomada funcionou" significava que processos estavam vivos **naquele momento**; não vale após 13:49.
- O `stage=deleted` não quer dizer que a limpeza precisa ser repetida. Quer dizer que a exclusão antiga foi completada e que o estado não avançou desde a falha persistida.
- O PID salvo 66998 e o timer registrado **não confirmam que existe algum processo para retomar**.
- `du -sh=18G` não é `model.safetensors` válido: existem dois parciais ocupando espaço, e o arquivo final NÃO existe.
- Não afirmar `download 94% concluído e retomável` como garantido: ~94,2% é a comparação aproximada do maior **arquivo parcial** com o tamanho esperado, não uma verificação de integridade/cobertura exata do download.
- Treinamento 9B, exportação GGUF, teste visual real e implantação de Hoshino/Lilith **não ocorreram comprovadamente**.
- O resultado de 35 testes do Laboratório v0.5 é de lógica e UI, não de backward de 9B/4B/6B em ROCm.

## 6. Referências do repositório

- [Plano completo do 9B e evolução v1.0–v1.4](OPERACAO_UNICA_9B_UNCENSORED_VISAO_20261011.md)
- [Planejamento neural anterior e observações 7B/6B](PLANO_TREINAMENTO_NEURAL_9B_7B_6B_20261010.md)
- [Laboratório, agenda e mods](LABORATORIO_NEURAL_E_MODS_20261011.md)
- [Handoff geral](HANDOFF_20261011_INDICE_E_DECISOES.md)

> **Última atualização registrada:** 2026-10-11, aproximadamente 13:58 BRT, com base nas saídas do operador. Não há acesso remoto ao shell do computador. O status real poderá mudar depois deste registro.
