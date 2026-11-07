# Adaptações e motor portátil — 06/10/2026

Não foi importada uma aplicação inteira. Só componentes pequenos foram
reescritos para o código Python e verificados por testes próprios.

- AIRI, MIT, Neko Ayaka: commit `94fa5d7cc5bcfb927a65d78c25ae20377802bc32`,
  [load-queue.ts](https://github.com/moeru-ai/airi/blob/94fa5d7cc5bcfb927a65d78c25ae20377802bc32/packages/stage-ui/src/libs/inference/load-queue.ts)
  e [priority.ts](https://github.com/moeru-ai/airi/blob/94fa5d7cc5bcfb927a65d78c25ae20377802bc32/packages/pipelines-audio/src/priority.ts).
  Adaptação em `app/core/work_queue.py`: fila limitada, uma tarefa ativa por
  worker, prioridade, FIFO no empate, cancelamento de pendentes. Foram adicionados
  envelhecimento contra inanição e contagem correta para drenagem. Nosso áudio
  dá prioridade à transcrição pedida pelo usuário; as prioridades não são iguais
  às do AIRI. Não interrompe uma tarefa ativa só por outra ter prioridade maior.
- Neuro SDK público, MIT, Vedal AI: commit
  `0cad33ac692f6cc90d36747fea9bbc53ca34b97a`,
  [ActionWindow.cs](https://github.com/VedalAI/neuro-sdk/blob/0cad33ac692f6cc90d36747fea9bbc53ca34b97a/Unity/Assets/Actions/ActionWindow.cs)
  e [contrato de ações](https://github.com/VedalAI/neuro-sdk/blob/0cad33ac692f6cc90d36747fea9bbc53ca34b97a/API/SPECIFICATION.md).
  `app/core/action_window.py` adapta construção/registro/encerramento e contratos
  imutáveis. Acrescenta validação estrita, recibos por id e exclusão concorrente.
  Alistair usa recibos duráveis locais: queda entre efeito e confirmação permanece
  incerta, sem repetição automática. Aceitação não significa tarefa concluída.
  Isso não é o LLM, a memória ou o código privado de Neuro-sama.
- Shogun: consultado o [perfil oficial de Bruno Miyauti](https://linktr.ee/miiyauti).
  Não encontrei um repositório oficial verificável nesta pesquisa; nenhum código
  de terceiros apresentado como Shogun foi copiado. Não inventamos sua arquitetura.
- Motor: binário Ollama local versão `0.32.6`, bibliotecas CPU da mesma instalação,
  [Ollama](https://github.com/ollama/ollama/tree/v0.32.6) e
  [llama.cpp](https://github.com/ggml-org/llama.cpp), MIT. Bibliotecas de sistema
  (glibc, libstdc++, libgcc, eventualmente libgomp) não são redistribuídas;
  são verificadas no Mint. CUDA, ROCm e Vulkan não entram no pacote.
- Modelo: Qwen3 4B Instruct 2507 Q4_K_M, alias `alistair-qwen3-4b:latest`.
  O manifesto e todos os blobs necessários já existentes são copiados;
  a licença Apache-2.0 existente no blob do modelo acompanha o pacote.
  SHA-256 do peso: `85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9`.

Licenças integrais preservadas em `third_party/licenses`. O manifesto do pacote
registra hashes dos arquivos físicos e alvos dos links. Esses hashes verificam
cópia/transferência; não são uma auditoria da cadeia de fornecimento upstream.

## Dependência de imagem local — registro de 10/10/2026

O checkout de `stable-diffusion.cpp` em `compartilhado/servicos/` é dependência
externa, não uma segunda aplicação desenvolvida neste repositório. Origem:
`https://github.com/leejet/stable-diffusion.cpp.git`, commit local
`b167b942f77ecb17e7f78e163a8c32ff7ac95c10`; submódulo `ggml` no commit
`4bf5f6000653b7881d00963cd6ddb665ccd62a8d`. As licenças upstream permanecem
no checkout. Não houve alteração funcional nesse motor nesta sincronização.

Checkout, build, binários e assets dessa dependência ficam fora do Git do
projeto, mas permanecem no disco. A configuração local continua apontando para
o `sd-cli` já instalado. Um clone deste repositório não instala esse motor,
os ambientes ou os pesos; suas adaptações/consumidores Python são versionados.
Este registro não altera as origens históricas do pacote descrito acima.
