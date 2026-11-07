#!/bin/bash
# Roda a suíte inteira da Hoshino. Nenhum teste precisa de Ollama, GPU, rede,
# interface ou do banco real — todos usam banco temporário.
#
#   ./rodar_testes.sh
ROOT="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
source "$ROOT/scripts/ambiente.sh"
cd "$ROOT" || exit 1
[[ -x "$PY" ]] || { echo "Ambiente principal ausente."; exit 1; }
# Tests import the project as top-level packages (core, mind, tools, ...).
# Export the project root once instead of relying on each test to tweak sys.path.
export PYTHONPATH="$APP_DIR:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Um inventário único inclui os históricos reconciliados. Não executar globs:
# o teste de microfone contínuo continua manual, com hardware de verdade.
if ! lista=$("$PY" -B testes/catalogo.py "$@"); then
    exit 2
fi
mapfile -t TESTES <<< "$lista"

falhou=0
passou=0
for t in "${TESTES[@]}"; do
    printf "%-26s " "$t"
    if saida=$("$PY" -B testes/executar_isolado.py "testes/$t.py" 2>&1); then
        echo "OK"
        passou=$((passou + 1))
    else
        echo "FALHOU"
        echo "$saida" | tail -15
        falhou=1
    fi
done

echo
echo "$passou/${#TESTES[@]} grupos aprovados (offline)."
if [ $falhou -eq 0 ]; then
    echo "Tudo passou."
else
    echo "Há falhas acima."
fi
exit $falhou
