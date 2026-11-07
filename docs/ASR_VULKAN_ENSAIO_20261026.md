# Ensaio real ASR Vulkan — 26/10/2026

## Resultado

Whisper.cpp executou o large-v3 na **RX6650XT física, RADV/Vulkan**, sem
llvmpipe. Fonte231638a0717b7822784297e5980965ffcec05810; modelo GGML F16
large-v3 SHA25664d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2,
revisão HuggingFace5359861c739e955e79d9a303bcbc70fb988958b1.

| Áudio sintético declarado | Atual CPU/int8 | C++ CPU/F16 | C++ Vulkan/F16 |
|---|---:|---:|---:|
| Frase curta, primeira inferência | 10,735s incluindo carga | 13,195s | 1,113s |
| Mesma frase aquecida | 6,013s | 12,640s | 0,713s |
| Frase longa aquecida | 8,381s | não executado | 1,646s |
| Parcial de2s | 5,604s | não executado | 0,702s |

Os processos C++ já estavam carregados nas medições de inferência: carga
separada1,410s CPU e1,407s Vulkan. O CPU atual inclui cold start no primeiro
pedido. São implementações/precisões diferentes; a comparação CPU versus GPU
no mesmo C++ confirma aceleração, enquanto a rota atual mostra o ganho
prático potencial. Isso não é benchmark de conversa completa com LLM residente.

## Qualidade: adoção ainda pendente

A frase longa teve WER0 nas duas rotas. A curta teve WER0 no ASR atual e
0,1111 no C++ CPU/GPU: o nome inicial Hoshino foi omitido. Parciais produziram
hipóteses instáveis, não texto final. Na entrada silenciosa, o atual recusou
com `no_speech`; o C++ bruto inventou “Legenda por Sônia Ruberti”. Isso
reprova uma troca direta sem os filtros pré/pós-ASR existentes e uma rodada
mais ampla de precisão. Sucesso físico/velocidade não equivale à aprovação
de qualidade nem altera o transcritor ativo.

## Recursos e encerramento

RM existente, serialização e leases usados; nenhum LLM de conversa rodou no
ensaio. Minecraft do humano permaneceu aberto como carga externa observada.
Pico total de VRAM4978499584bytes (~4,64GiB), baseline925007872bytes
(~0,86GiB); diferença máxima~3,77GiB. Utilização máxima99%, temperatura
máxima86°C, sem corte105°C, OOM ou crash. RSS máximo do servidor Vulkan
199180KiB; CPU C++3918236KiB. Os dois servidores foram encerrados por PID
owned, exit0, porta livre e VRAM devolvida ao baseline. Não houve replay.

Hospedar ASR residente junto de um9B de conversa pode exigir descarregar e
recarregar pesos nos8GiB; esse custo não foi medido aqui. A integração deve
medir o caminho completo e preservar prioridades do RM antes de adoção.

## Evidências e preservação

Driver de spike, manifestos, referências sintéticas e resultados:
`laboratorio-local/controle-laboratorio/asr-gpu-20261026/`. Build oficial:
`laboratorio-local/whisper.cpp/build-vulkan/`. Ambos são áreas locais
ignoradas, sem envio de pesos/build ao Git. Log resumido:
`/tmp/asr-gpu-benchmark-20261026.log`.

Não houve microfone, fala de entidade, memória fictícia como história humana,
quota, treino, troca ativa de modelo, instalação de driver ou alteração no
jogo do humano. A consulta de status de Minecraft não fez login.

Fontes: [Vulkan oficial](https://github.com/ggml-org/whisper.cpp#vulkan-gpu-support)
e [distribuição GGML](https://huggingface.co/ggerganov/whisper.cpp).
