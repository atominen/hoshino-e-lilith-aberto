# Triagem do novo executor 6B — 24/10/2026

> Histórico: a seleção vigente desde27/10 é
> [4B/9B, com professor preservado](ORGANIZACAO_4B_9B_20261027.md).
> A preservação do6B mencionada abaixo foi substituída pela retirada dos pesos.

**Decisão humana posterior:** a troca dinâmica fica somente com **7B e 9B**.
A busca/integração de um terceiro executor está pausada. O Qwen3-6B baixado
deve ser preservado, fora da rota automática; a triagem e seus próximos passos
abaixo são históricos, não uma fila autorizada para continuar.
[Estado vigente](SUBSTITUICAO_YI_EXECUTOR_RAPIDO_20261024.md).

**Resultado posterior:** Qwen3-6B podado baixado/testado com autorização, mas
não homologado: primeiro caso incompleto em dois perfis NF4 e conversão sem
suporte. O texto abaixo preserva a triagem anterior.
[Ensaio, aquisição e resultado](ENSAIO_QWEN3_6B_SNIPER_20261024.md).

## Requisitos e limite desta pesquisa

Manter 6B/7B/9B para cada Hoshino/Lilith e o modelo fixo de Alistair.
Pesquisar um 6B conversacional, treinável a partir dos originais e convertível
para o backend local. A rota rápida precisa demonstrar vantagem sobre o
Qwen2.5-7B, sem perder português, autoria, contexto e instruções básicas.
Não se selecionou um 4B ou 8B para contornar essa exigência.

Foram lidos cartões, configurações e metadados HF públicos. **Nenhum peso novo
foi baixado, nenhum código remoto foi executado e nenhum candidato foi ativado.**
Safetensors disponível não comprova compatibilidade do ciclo de treino/conversão
local nem qualidade. Menos parâmetros não garantem menor latência.

## Candidato para a próxima análise de compatibilidade

[parmanu-lcs2/Qwen3-6B](https://huggingface.co/parmanu-lcs2/Qwen3-6B), revisão
`d6990725bfc555b09e1c1b76bd07cd0dcaf7aceb`: **6.198.014.464 parâmetros** segundo
o cartão, originais Safetensors (12.396.072.584 bytes no inventário HF), licença
declarada Apache-2.0. É Qwen3-8B **reduzido por poda estruturada SNIPER**, não um
4B ampliado. O autor informa recuperação LoRA já incorporada aos pesos.

É um candidato de **pesquisa**, não um substituto escolhido para instalação.
A configuração declara `PrunedQwen3ForCausalLM`, com camadas de formatos
diferentes e blocos removidos. Seu uso HF pede código remoto próprio.
O conversor local reconhece Qwen3 padrão, mas não registra essa arquitetura
podada. Trocar apenas o nome para Qwen3 padrão seria incorreto: a viabilidade
de conversão/exportação ainda está **bloqueada por compatibilidade não provada**.
Não executar `trust_remote_code` sem revisão isolada e revisão pinada.

O [artigo SNIPER](https://arxiv.org/abs/2608.12953), publicado em agosto de 2026,
descreve o método e avaliações de retenção de desempenho. Isso não demonstra
português, personalidade ou vantagem na RX6650XT deste projeto.

## Alternativas verificadas e motivos para não instalar agora

| Modelo | Originais / arquitetura observada | Limitação para este projeto |
|---|---|---|
| [Llama-3.1-6B-Instruct, Parmanu](https://huggingface.co/parmanu-lcs2/Llama-3.1-6B-Instruct) | 6.030.118.912 parâmetros declarados; Safetensors; `PrunedLlamaForCausalLM` | Mesma questão de formatos heterogêneos/conversão; licença precisa ser conciliada com a base Llama antes de adoção |
| [HelpingAI2-6B](https://huggingface.co/HelpingAI/HelpingAI2-6B) | Safetensors; Llama padrão, 22 camadas; sem `auto_map` | Cartão voltado a inglês; licença customizada aponta para `LICENSE.md`, ausente no inventário consultado; origem/capacidade em português ainda não comprovadas. Alegações de EQ não são validação |
| [DeciLM-6b-instruct](https://huggingface.co/Deci/DeciLM-6b-instruct) | Safetensors; `DeciLMForCausalLM`, atenção agrupada variável | Inglês e licença própria/Llama2; há conversor Deci local, mas isso não prova suporte a essa variante 6B. Não aplicar números de throughput em A10/batch64–128 ao uso interativo AMD |
| [Qwen3-Jan-v1-6B Brainstorm](https://huggingface.co/DavidAU/Qwen3-Jan-v1-256k-ctx-6B-Brainstorm20x) | Safetensors; Qwen3 padrão, 55 camadas | Deriva de Jan-v1-4B expandido. Não presumir capacidade superior nem velocidade por dizer 6B; não é recomendação de instalação |
| [Karnak-6B](https://huggingface.co/Applied-Innovation-Center/Karnak-6B-v1.0) | Safetensors; Qwen3 padrão, 54 camadas | Expansão de Qwen3-4B-Instruct-2507, foco árabe/inglês e tokenizer modificado; não priorizar para português |
| [Helium6B, Kyutai](https://huggingface.co/kyutai/Sequential_Helium_6B) | Base multilíngue, incluindo português; Safetensors | O próprio autor exclui chat/instruções sem ajuste prévio. Não é substituto conversacional pronto |

Não foi encontrada nesta triagem uma opção **já homologada e pronta** que
comprove todos os requisitos. A prioridade acima é investigar o Qwen3-6B
podado sem instalar; se a conversão exigir uma nova arquitetura/custo excessivo,
registrar a reprovação em vez de improvisar outro 4B ou fingir compatibilidade.
Esta pesquisa não adiciona candidato ao catálogo treinável/automático.

## Próximas verificações, antes de qualquer download de pesos

1. Auditar código/configuração da revisão pinada e descrever formatos podados;
   confirmar exportação GGUF real e caminho LoRA → checkpoint → recarga → export.
2. Se houver caminho viável, planejar ensaio pequeno isolado com hashes e fonte,
   mesmo backend/quantização/contexto do 7B e liberação entre modelos.
3. Testar português, identidade externa, negação, autoria, contexto, informação
   desconhecida, instruções, ferramentas e EOS; revisão semântica além de regex.
4. Medir carga fria, primeiro token, latência quente e tokens/s em tarefas reais,
   RAM/VRAM/temperaturas e `pressure[]`. Não treinar para maquiar falha básica.
5. Adotar somente após resultado suficiente e autorização apropriada; Alistair,
   modelos selecionados e dados das entidades permanecem intactos.
