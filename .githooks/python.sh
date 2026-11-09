python=
for candidato in python3 python py; do
    if "$candidato" -c "" 2>/dev/null; then
        python=$candidato
        break
    fi
done
if [ -z "$python" ]; then
    echo "${0##*/}: python no corre desde el PATH (se probaron python3, python y py); /odd-ws:doctor lo revisa (item python)" >&2
    exit 1
fi
