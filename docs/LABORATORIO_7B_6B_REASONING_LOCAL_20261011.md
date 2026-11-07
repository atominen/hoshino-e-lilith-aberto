# Laboratório 7B/6B com thinking alternável — 11/10/2026

Implementação v0.3 entregue por ZIP: `laboratorio_neural_v0_3.zip`. O repositório GitHub recebeu a documentação, mas os scripts precisam ser instalados e versionados localmente. Nenhuma execução de download, fine-tuning, GGUF real ou inferência foi realizada no PC do operador por esta entrega.

## Requisitos de seleção

- Tamanho próximo do segmento de 6B–7B, sem comprometer acentuadamente desempenho ou memória.
- Capacidade comprovada na documentação do modelo de **ligar e desligar raciocínio**, não apenas ocultar tokens de reflexão na resposta.
- Compatibilidade experimental HF Safetensors/QLoRA local, com exportação GGUF e comparação Ollama sujeitas a probes reais.
- Risco máximo de VRAM: RX 6650 XT 8 GiB. Descoberta não equivale à aprovação técnica no PC.

## Modelos admitidos para pesquisa

1. `Qwen/Qwen3-8B` — cerca de 8B, um pouco maior que o alvo 7B, mas oferece `enable_thinking` nativo com `True` e `False`, suporte documentado de GGUF. Ficha https://huggingface.co/Qwen/Qwen3-8B e guia https://github.com/QwenLM/Qwen3/blob/main/docs/source/run_locally/llama.cpp.md.
2. `tencent/Hunyuan-7B-Instruct` — 7B, alterna `enable_thinking` no chat template, ou `/think` e `/no_think`. Ficha https://huggingface.co/tencent/Hunyuan-7B-Instruct. **Já foi descartado anteriormente no projeto**, portanto é candidato a comparação, não reabilitação em produção. Exige especial validação de arquitetura GGUF/QLoRA.

Nenhum checkpoint de **6B** foi confirmado como satisfazendo simultaneamente o requisito de toggle nativo, qualidade adequada e trajetória de integração local; a vaga permanece vazia. Não vender modelo 4B como 6B nem R1 destilado como thinking ON/OFF com o mesmo contrato.

## Protocolo comparativo

- Candidatos ficam fora do painel até download **completo** verificado em `~/laboratorio-lora/modelos-extras/<id>/hf`; recibo `lab_revision.json` só aparece após `snapshot_download` e inspeção.
- Sem iniciar download em paralelo ao download 9B, sem treino/comparação enquanto orquestrador 9B existir (inclusive pausado); prioridade do timer 21h preservada.
- Um experimento por vez. Base HF NF4 testada em `thinking=False` e `True`, segue QLoRA de 30 min com corpus separado por entidade; checkpoints e logs no laboratório. Após, `llama.cpp` converte a base para Q4_K_M e o LoRA separadamente; Ollama laboratório 11557 executa prompts idênticos em ambas as versões e modos.
- Valores de loss e respostas servem para avaliação **comparativa manual**, não prova de superioridade; modelo e LoRA podem falhar por VRAM, template ou importador.
- Proteções: pré-voo de disco, recusas sem checkpoint local, sem download automático ao abrir página, sem alterações na produção ou nos bancos mentais.

Consulte `laboratorio/README.md` do pacote e `laboratorio/CHANGELOG_V0_3.md` para instalação e limitações.

**Evolução do inventário:** modelos futuros com recibo de instalação e pesos completos sob `modelos-extras` aparecem automaticamente sem alterar a lista de candidatos. Arquiteturas desconhecidas são somente leitura, proibidas para treino/convert até homologação.
