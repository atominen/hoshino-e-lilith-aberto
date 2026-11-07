# Laboratório v0.5 — instalação rápida

**Situação no PC do operador ao preparar esta versão:** 9B reservado/baixando; Alistair 4B Safetensors e GGUF 27B ausentes; 26 testes v0.4 passaram localmente no computador do operador. Os 35 testes da v0.5 passaram em ambiente de desenvolvimento separado, não na Radeon.

1. Descompacte o ZIP v0.5 em staging, `rsync -a --exclude='mods/'` apenas a pasta `laboratorio/`, preservando cópia v0.4.
2. Execute `python3 -m unittest discover -s laboratorio/tests -v` e reinicie **somente** o painel 8787.
3. Verifique `python -m laboratorio.pilotos plan --six-entity hoshino`. Nenhum download/treino acontece durante o plano.
4. Deixe **primeiro** o 9B finalizar seu próprio download/experimento; não contorne seus guardas nem apague parciais.
5. Depois: baixar base 4B e Yi6B separadamente, conferir 35+ GiB livres antes do Yi6B e, somente se pronto, executar `python -m laboratorio.pilotos run --six-entity hoshino --confirm` no ambiente ROCm com `env -u HSA_OVERRIDE_GFX_VERSION`.
6. Professor `python -m laboratorio.professor download` instala **só GGUF Q4_K_M** (não treina), exige 32GiB livres e compatibilidade do servidor llama.cpp; só após instalar deve executar plano com snapshot exportado.

O 6B Yi-1.5 não possui thinking nativo; Hunyuan 7B e Qwen3 8B são experimentais com thinking ON/OFF documentado mas requerem teste efetivo. Treino, conversão e deploy não são resultados já concluídos.

Detalhes completos: `README_PROFESSOR_V0_5.md`.
