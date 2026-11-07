# Handoff técnico — arquitetura completa do Laboratório Neural e Professor (11/10/2026)

Este é o **estado do projeto discutido e autorizado**, incluindo ideias futuras e etapas comprovadas. Diferenciar sempre **desejo / design / código entregue / teste unitário / teste real**. A versão executável mais nova, **v0.5**, foi **instalada no PC do operador** e testada: 35/35 testes unitários PASS; modelos adicionais ainda não baixados. Código da pasta `laboratorio/` completa foi distribuído em ZIP privado, **não sincronizado integralmente no repositório GitHub** pelos commits documentais. Repositório `atominen/hoshino-e-lilith` PRIVADO.

## 1. Objetivo: três agentes com continuidade, autonomia e personalidade estável

- **Hoshino**: inspiração de Blue Archive, com descontração, humor de veterana, resistência ao esforço sem propósito, franqueza, proteção em situações importantes; não copiar falas como roteiro, inventar enredo como autobiografia ou transformá-la num bordão.
- **Lilith**: inspiração de *The NOexistenceN of you AND me*, introspecção existencial, afeto, estranheza, humor inesperado e ambiguidade emocional; não converter todo turno em monólogo existencial ou em `tsundere` automático.
- **Alistair**: identidade própria de coordenador/standby textual e organização; executor original 4B CPU preferencial/obrigatória com GPU oportunista apenas quando seguro, memória própria, sem herança de memórias de Hoshino/Lilith, sem voz, manifestação `entidades/alistair/entidade.json`.
- Cada personalidade deve aparecer em **escolhas, ritmo, razões, iniciativa e comportamento observado**, não num ator lendo um script. A personalidade evolui gradualmente com evidências reais; valores e relações NÃO são redefinidos a cada turno.
- Tudo que é memória factual, relações, episódios, diário, configurações/identidade ou preferências mutáveis deve permanecer no sistema externo de memória de cada entidade. **Peso neural não substitui biografia nem banco mental.** Fine-tuning ensina tendências, julgamento, seleção de ferramentas, uso correto da memória e estabilidade conversacional.

## 2. Sistemas já existentes na Central — reutilizar, não duplicar

| Área | Origem | Função / invariante |
|---|---|---|
| Histórico e continuidade | `app/core/history.py`, episódios SQLite, JSONL diagnóstico, caixa postal | Conversas, eventos, origem e cronologia; consultas por período / resumos incrementais |
| Escriba | `app/mind/scribe.py` | Memória automática por regras e extração posterior, com metadados da autoria real; aprende evidências de comportamento a cada turno |
| Personalidade | `app/mind/personality.py` | Traços com evidências e atualização gradual tipo média móvel, gosto/valência com motivo; consolidação após massa crítica |
| Reflexão noturna | `app/mind/night_reflection.py` | Analisa material do dia; já reconhece aviso explícito de dormir; limita recortes e preserva referências/hashes; reflexão não equivale a fato |
| Conhecimento e causalidade | `app/memory/knowledge_store.py`, lições/diagramas versionados | Distinguir evidência, interpretação, hipótese, exceção e confiança; recall ligado a registros reais |
| Resumos incrementais | `docs/CONSOLIDACAO_COGNITIVA_20261010.md` | Cobertura persistida, lotes retomáveis, registros tardios; não marcar fontes omitidas como processadas |
| Resource Manager | `app/core/resource_manager.py`, `gpu_resource.py` | Locks, leases, prioridade, VRAM física, isolamento e dimensionamento de contexto |
| Central local | `iniciar_entidades.py`, `app/core/central_control.py` | UI, serviços, supervisor, acesso restrito; produção separada dos experimentos |
| Ofício/mods | `app/tools/workspace.py` / `laboratorio/` | Não confundir os arquivos da Central, memórias, artefatos temporários e cópias experimentais |

**Razão histórica para o escriba**: confiar que a LLM invocará uma ferramenta de memória não é suficiente; no projeto foram observadas conversas sem memórias gravadas apesar de prompts. A extração automática garante persistência sem depender só da ação espontânea do modelo. Treinamentos também devem reforçar *quando usar* ferramentas de memória, mas não substituir a política externa.

**Segregação de dados:** diários privados `reflections.tipo=diario` e visibilidade por entidade não podem ser liberados ao professor por simples prompt. Acesso aos arquivos, comandos e exportações precisa respeitar ACL real; não misturar histórias entre agentes. Os resumos e reflexões podem ter um recorte limitado; não dizer "leu todo o dia" se houve exclusões.

## 3. Inventário de modelos e decisões, com histórico de exceções

| Papel | Modelo/fonte | Decisão atual | Thinking real |
|---|---|---|---|
| Hoshino principal / Lilith principal | `ccharnkij/Qwen3.5-9B-Uncensored` Safetensors multimodal (treino), base idêntica e LoRA separados | Primeiro grande experimento prioritário; download **incompleto** em 13:49 | Família Qwen3.5 com ON/OFF via template/backend; validar no artefato exato |
| Alistair laboratório | `Qwen/Qwen3.5-4B` Safetensors multimodal | Piloto individual autorizado, **ainda não baixado** | Suporte esperado na família; testar modelo/backend |
| Alistair executor antigo | `unsloth/Qwen3.5-4B-GGUF` (origem anterior) | Histórico de produção; pode não estar mais presente após limpeza Ollama | Não associar automaticamente a LoRA feita numa outra base |
| 6B exceção | `01-ai/Yi-1.5-6B-Chat` | Antes descartado por não pensar; **reautorizado** em 11/10 **SEM obrigação de thinking**, piloto 30 min | NÃO possui comutador nativo comprovado; não simular thinking |
| 7B experimental | `tencent/Hunyuan-7B-Instruct` | Havia sido descartado; candidato exploratório com testes necessários | ON/OFF descrito/documentado, **teste real obrigatório** |
| 8B alternativa | `Qwen/Qwen3-8B` | Limite de porte flexibilizado para comparação; 8B, não 7B literal | `enable_thinking=True/False`, testar Ollama |
| 7B baseline antigo | `Qwen2.5-7B-Instruct` | Referência histórica de QLoRA na RX 6650 XT; modelos Ollama apagados na limpeza | NÃO possui thinking nativo comutável; não atende requisito atual de 7B |
| Professor | `mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF`, `Huihui-Qwen3.5-27B-abliterated.Q4_K_M.gguf` | **Somente GGUF inferência/curadoria, nunca treinar professor**, arquivo ~16,5 GB; ainda NÃO baixado | Modos thinking/direto documentados na família; confirmar na variante quantizada |

- O pedido inicial era 7B e ~6B não muito inferiores aos padrões; depois o usuário exigiu thinking ON/OFF em ambos; posteriormente **retirou essa exigência EXCLUSIVAMENTE para 6B**, exigência mantida para 7B. Não fingir que `Yi` passou a pensar.
- Procurou-se tanto um 6B com thinking quanto um sem; **nenhum 6B com ON/OFF nativo, qualidade comprovada e tamanho apropriado foi homologado**; não rotular um 3B como 6B nem pegar derivados não validados só para fechar tabela.
- `Hunyuan 7B` já havia sido rejeitado e só voltou para estudo. `Qwen3-8B` possui thinking comutável e é alternativa mais confiável na família, mas tem ~8B.
- `Huihui abliterated` significa pesos modificados para reduzir recusas; NÃO certifica raciocínio, verdade, JSON, estabilidade, privacidade ou superioridade ao `Qwen/Qwen3.5-27B` original. Fazer benchmark do professor antes de lhe dar autonomia mais ampla.
- **Inventário na interface operacional** deve listar **somente modelos realmente instalados/completos**, jamais candidatos planejados. Descoberta de futuros checkpoints deve ser dinâmica; arquiteturas não homologadas aparecem só leitura, sem treino habilitado.

## 4. Evolução histórica do Laboratório Neural

### v0.1 — painel, agenda 21h e mods
Artefato `laboratorio_neural_painel_mods_v0_1.zip`. Servidor HTTP Python em `127.0.0.1:8787`, inventário de estado, logs, parciais HF, disco; sistema de mods `laboratorio/mods/<id>/manifest.json` + `files/`. Build de **cópias físicas de arquivos Git rastreados** em `~/laboratorio-lora/overlays/builds/`, link `overlays/current`, sem editar originais, sem hardlink para fonte, sem dados mentais, sem segredos nem caches. Mod ativado depois sobrepõe arquivo no **snapshot**, não na Central ao vivo. **Overlay não é sandbox anti-malware**; não executar mod não confiável com acesso aos bancos reais. Controle de `SIGSTOP` ao pai e timer `systemd --user` anti-PID reuse. Cinco testes iniciais.

### v0.2 — experimentos orientados a dados e GGUF
Artefato `laboratorio_neural_v0_2.zip`. Catálogo amplo preliminar 6B/7B (incl. Qwen2.5-VL-7B, DeepSeek-R1-Distill-Qwen-7B, Qwen2.5-7B, Qwen2.5-Omni-7B, Yi-VL-6B, Yi-1.5-6B); dataset `train/validation JSONL` v2/v3 por entidade, upload/importação pelo navegador, configuração do treino, jobs/logs, conversão base F16 → Q4_K_M + LoRA separado; smoke tests textuais no Ollama isolado `11557`. **Visão de multimodais não pode ser declarada preservada no Ollama sem pipeline mmproj/llama.cpp real**. Catálogo foi refinado posteriormente. Doze a quatorze testes de desenvolvimento conforme rodada.

### v0.3 — raciocínio ON/OFF e inventário apenas local
Artefato `laboratorio_neural_v0_3.zip`. Requisito inicial de thinking ON/OFF em faixa ~6B/7B; elegíveis Qwen3-8B e Hunyuan-7B, ainda sem 6B satisfatório. `laboratorio.candidatos list` mostra pesquisas por CLI, `installed` mostra checkpoints físicos; a página `/api/catalog` exclui opções futuras. Download apenas acionado explicitamente, recibo `lab_revision.json`, shards Safetensors completos e ausência de `.incomplete`. `cycle_30m` planeja probe real thinking ON/OFF, LoRA por 30 minutos, GGUF e Ollama; não contém resultados de treino físico. Dezessete testes.

### v0.4 — Professor 27B e Alistair terceiro aluno
Artefato `laboratorio_neural_v0_4_professor_alistair.zip`, **instalado localmente e 26 testes PASS**. Professor Qwen3.5-27B GGUF `mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF`: não treinar, CPU/llama-server em `11558`, unload obrigatório após planos; diretório `~/laboratorio-lora/professor-27b/gguf/`. Validador de propostas SFT `professor_schema.py`, por entidade e evidência ID existente, duration 0/10/30 min, sem execução automática de proposta. Consulta snapshots JSONL **manuais** em `~/laboratorio-lora/historicos-curadoria/`, até **40 registros ou 2 MiB**, com histórico de alguns jobs; não existe leitura automática do histórico integral. Alistair: `Qwen/Qwen3.5-4B` em Safetensors + treino multimodal text-only, 51 train / 27 validação / 16 holdout sintéticos em `~/laboratorio-lora/datasets-alistair-seed/`; pesos de visão preservados no escopo das camadas congeladas. Probe/gpu ainda pendentes. Corrigido pré-voo para aceitar `preprocessor_config.json` do HF. Não aplicar adaptador treinado na base oficial ao GGUF Unsloth antigo sem prova de revisão/compatibilidade.

### v0.5 — professor com recursos/contexto dinâmicos, exceção Yi 6B, fila
Artefato `laboratorio_neural_v0_5_professor_6b.zip`, **INSTALADO NO PC REAL, 35/35 TESTES UNITÁRIOS PASS** (11/10). Novos arquivos `recursos_professor.py`, `pilotos.py`, painel atualizado.
- Detecta `MemAvailable` (RAM, não swap), CPUs lógicas e VRAM física; contexto em buckets **4096, 8192, 12288, 16384, 24576, 32768** conforme necessidade/reserva física, não forçar 32K por padrão. Threads CPU até nCPU−2. Offload GPU opcional com poucas camadas se >=6GiB livres mensurados; se não, CPU explícita. Heurística de pré-voo, NÃO benchmark de hardware.
- Conta tokens reais por `llama-server /tokenize` e reserva 1600 tokens de resposta + 384 de protocolo antes de aceitar snapshot; se ultrapassar, recusa/demanda divisão de lotes, não trunca silenciosamente.
- `laboratorio.pilotos plan --six-entity <hoshino|lilith|alistair>` somente leitura; `run --six-entity ... --confirm` seria piloto sequencial **Alistair 4B → Yi-1.5-6B**, ambos de até 30 min de treino; **sem downloads automáticos, sem implantação em produção e sem desligamento do PC**.
- Yi 6B em `01-ai/Yi-1.5-6B-Chat` sem thinking nativo; para 7/8B exigência permanece real e ON/OFF deve renderizar templates distintos (não falsificar).
- Teste `treino_texto.py` exige ROCm/máscara válida, recusa truncamento excessivo; mensagens e corpus segregados por entidade. Bloqueio `gate_9b` impede novos downloads e trabalho GPU se 9B ainda estiver em execução/reservado, inclusive se pai pausado.
- Painel operacional permanece mostrando **somente checkpoints completos reconhecidos**.

## 5. Resultados REAIS de instalação da v0.4/v0.5

Trechos de terminal fornecidos pelo operador (não substituir por expectativas):

```text
v0.4: Ran 26 tests ... OK
v0.5: Ran 35 tests in 0.057s ... OK

python -m laboratorio.professor status:
  professor=mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF
  installed=false; trainable=false; proposals=0
  mem_available_gib=25.82; cpu_threads_detected=12

python -m laboratorio.alistair status:
  entity=alistair; repo=Qwen/Qwen3.5-4B
  base_complete=false; dataset_present=true
  probe_passed=false; checkpoints=0; trained_in_this_session=false

python -m laboratorio.pilotos plan --six-entity hoshino:
  alistair_base_complete=false
  alistair_seed_present=true
  alistair_probe_passed=false
  six_b_model=yi15-6b
  six_b_repo=01-ai/Yi-1.5-6B-Chat
  six_b_complete=false; six_b_native_thinking=false
  six_b_entity=hoshino
  six_b_dataset=pacote_neural_v3:hoshino
  requested_minutes_per_student=30
  will_download=false
  will_change_production=false
  will_shutdown=false
  ready_to_run=false
```

As tentativas reais `python -m laboratorio.alistair download`, `probe` e `train --minutes 30` foram **BLOQUEADAS CORRETAMENTE**: `gate_9b` viu download do 9B em curso e pai existente/pausado (nesse momento). **Nenhum treino Alistair, Yi6B ou professor foi executado.** A situação do 9B mudou posteriormente: ambos PIDs desapareceram às 13:49; ver handoff operacional específico. Não reinterpretar a ausência de PID como autorização automática para consumir disco.

## 6. Visão futura: professor neural noturno com autonomia limitada e verificável

Proposta discutida e aprovada **conceitualmente**, mas ainda NÃO implementada de ponta a ponta:

1. Ao receber aviso de dormir ou em janela configurada, congelar snapshot por entidade com IDs de origem, eventos de ferramentas, autor, timestamp e hashes. Reutilizar histórico, escriba, reflexão noturna e resumos incrementais; não inventar um segundo banco mental.
2. Processar **todo o histórico relevante por lotes com cursor persistente**, cobrindo mensagens tardias e delimitando omissões. v0.5 **ainda não cobre tudo**, só snapshots manuais curtos.
3. Professor 27B GGUF (sem treino), com instruções, exemplos, histórias recentes, revisões anteriores, métricas de qualidade, versões LoRA e incidentes, propõe o que vale treinar, **duração, intensidade, curriculum, replay e critérios de parada**. Também pode escolher `não treinar`.
4. Curadoria: distinguir observações, hipóteses, evidências e alvo SFT. Validar correções com resultados de ferramentas/feedback. Não recompensar erro bem escrito nem converter diários/fatos pessoais instáveis em pesos.
5. Professor monta dataset auditável por entidade, checksums, conjunto reservado, experiências antigas (`experience replay`), adaptador-base/revisão fixos, plano JSON imutável; descarrega-se completamente antes de alocar GPU ao aluno. O supervisor mantém fila/locks e progresso mesmo sem professor carregado.
6. Treinos sequenciais Hoshino, Lilith, Alistair (e modelos 6/7/8B experimentais conforme autorização), QLoRA com orçamento parametrizado e checkpoints atômicos; testar save+reload, e **futuramente estado completo do otimizador** para retomada exata.
7. Avaliação *independente* da curadoria do professor: prompts holdout, raciocínio ON/OFF quando suportado, lógica, JSON/ferramentas, identidade, naturalidade, uso de memória, visão separada, regressões e estabilidade. Métricas de quality gate; comparar base, versão aprovada anterior e candidato. Se regrediu, rollback.
8. Professor pode recarregar para analisar anomalias e propor novas tentativas dentro de orçamento rígido; promoção à Central só após testes reais e autorização apropriada. Não deve editar constituições, identidades, bancos nem código real.
9. No fim, **desligamento automático do PC foi solicitado como objetivo futuro**, mas NÃO habilitado: será ação do supervisor determinístico com política previamente autorizada, verificação de todos os trabalhos/salvamentos, usuário ocioso, contagem regressiva cancelável, sem colocar `sudo shutdown` num prompt da LLM.

### Estratégias e riscos levantados

- **SFT/QLoRA** por exemplos de competência e personalidade contextual; **knowledge distillation** na geração de bons alvos; **experience replay** para reduzir esquecimento; *curriculum learning* para níveis; **DPO** somente posteriormente com pares de preferência confiáveis, não como implementação já pronta.
- Preferir *aprender diariamente* via memória/curadoria, mas **treinar somente quando houver volume/diversidade suficientes**, não forçar 30 minutos em três exemplos. Proteger contra sobreajuste e regressão.
- Evitar *self-training contamination*: resposta errada do próprio aluno não vira solução "correta"; alvo deve ser validado por fonte independente. Professor não pode ser o único juiz do próprio dataset.
- Distinguir personalidade demonstrada de atuação estereotipada; modelo maior não decide sozinho novos valores ou fatos de biografia.
- **Autoridade do professor:** ler dados autorizados, analisar, escolher parâmetros de perfis homologados, gerar plano, solicitar jobs dentro do orçamento. **Supervisor** reserva RAM/GPU, verifica arquivos, dispara subprocessos, desliga apenas se política autorizada; a LLM não recebe shell/root irrestrito.
- Professor 27B não precisa de pesos Safetensors (~55GB); apenas **GGUF Q4_K_M (~16,5GB)** para inferência CPU + eventual offload mínimo. Com Ryzen 5 5500/32GB RAM/8GB VRAM, medir tokens/s, swap, pressão de memória, carga/unload e contexto verdadeiro antes de prometer janelas grandes.
- Nenhum outro LLM baixado por abrir o painel. Instalar, testar e treinar são etapas explícitas; nenhuma execução diária autônoma foi ativada na v0.5.

## 7. Arquitetura de arquivos/isolamento

```text
~/hoshino e lilith/
  app/{core,mind,memory,tools,ui}/         Central e mecanismos cognitivos existentes
  entidades/{hoshino,lilith,alistair}/     identidades e estados separados
  laboratorio/                             ZIP v0.5 instalado localmente
    core.py, controle.py, labctl.py, painel.py
    catalogo.py, candidatos.py
    experimentos.py, trabalhador.py, treino_texto.py
    professor.py, professor_schema.py, recursos_professor.py
    alistair.py, treino_qwen35_entidade.py, pilotos.py
    mods/{id}/manifest.json, files/
    tests/*, web/{index.html,style.css,app.js}
~/laboratorio-lora/
  .venv-rocm/                              PyTorch nightly ROCm experimental
  automacao_9b_vision_v1_4/               orquestrador inicial 9B (separado do labctl)
  modelos/qwen3.5-9b-uncensored-hf/       download 9B incompleto atual
  modelos-extras/<id>/hf/                 outros checkpoints HF (não presentes na v0.5 observada)
  datasets-alistair-seed/                 sintético, presente
  professor-27b/gguf/                     previsto, não baixado
  historicos-curadoria/                   snapshots autorizados quando produzidos
  overlays/builds/                        cópias de código + mods; não é sandbox real
  logs/                                    logs privados, não versionar
```

- `rsync -a --exclude='mods/'` foi usado na instalação v0.5 para preservar os mods locais; antes foi feito `cp -a laboratorio ~/laboratorio-lora/backup-laboratorio-v0_4-<timestamp>`. Não promover cópia overlay como produção implicitamente.
- Os pacotes v0.1–v0.5 existiram como ZIPs entregues no chat/baixados pelo usuário; **GitHub possui documentação desses pacotes, não todo o código do diretório `laboratorio/` no ramo remoto**, cuja pasta hoje contém apenas `GUIA_GITHUB.md`. Próxima sincronização de código deve partir do checkout real, revisar `git status`, não subir dados locais/ambientes/pesos, e não sobrescrever alterações existentes.

## 8. Próximos trabalhos, em ordem sugerida

1. Resolver situação do **9B descarregado e incompleto**, sem excluir dados ou presumir timer válido; [handoff operacional](HANDOFF_20261011_OPERACAO_9B_ESTADO_REAL.md).
2. Sincronizar **fontes v0.5** do checkout (após revisão de segurança, `.gitignore` e diffs) para GitHub privado — até aqui a documentação do laboratório é mais recente que o código Git remoto.
3. Verificar espaço físico disponível após 9B e estimar pesos+GGUF+checkpoints, **não baixar em paralelo professor 27B, Alistair 4B e Yi6B** quando há ~55GB livres.
4. Completar/preparar base 4B e Yi6B sequencialmente, executar pilotos reais de 30 min apenas após passar probes ROCm e `gate_9b`, não converter sucesso de testes unitários em aprovação de modelo. Escolher explicitamente entidade do 6B (`--six-entity hoshino|lilith|alistair`).
5. Baixar professor **GGUF apenas**, testar qualidade thinking/direto e tokens/s em CPU, uso de RAM/VRAM e `/tokenize`, unload, sem treinar pesos.
6. Criar leitor do histórico REAL com cursor/ACL e curador completo; critérios de qualidade; supervisor persistente, orçamento noturno, avaliação independente, restauração de estado, promoção com rollback e desligamento autorizado.

## 9. Fontes primárias para consulta no repositório

- [Planos específicos 9B com todas as revisões](OPERACAO_UNICA_9B_UNCENSORED_VISAO_20261011.md)
- [Plano de personalidades e LoRA](PLANO_TREINAMENTO_NEURAL_9B_7B_6B_20261010.md) — **parte histórica superada pela exceção 6B de 11/10**
- [Laboratório v0.1 e overlays](LABORATORIO_NEURAL_E_MODS_20261011.md)
- [v0.2](LABORATORIO_EXPERIMENTOS_6B_7B_20261011.md)
- [v0.3](LABORATORIO_7B_6B_REASONING_LOCAL_20261011.md)
- [v0.4](PROFESSOR_NEURAL_27B_ALISTAIR_V0_4_20261011.md)
- [v0.5](PROFESSOR_NEURAL_RECURSOS_DINAMICOS_6B_V0_5_20261011.md)
- [Memória, aprendizado e evidências](AUDITORIA_COGNITIVA_MEMORIA_HIBRIDA_20261009.md)
- [Reflexão noturna com proveniência](REFLEXAO_EVIDENCIAS_RAM_20261009.md)
- [Consolidação cognitiva](CONSOLIDACAO_COGNITIVA_20261010.md)
- [Escopo e exceções](../ESCOPO_CONGELADO.md)
- [Política de preservação](POLITICA_PRESERVACAO_PROJETO.md)
