
for ((i = 0; i < 5; i++)); do
    expect Dostoyevsky.exp localhost 7877 2>&1 >/dev/null &
done

wait $(jobs -p)