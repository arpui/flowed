#!/usr/bin/env bash
# Verificació del fix "merge marker into closing line". Executar a railab
# (o a llvm canviant el port) amb el model deep ja engegat.
set -e
cd ~/projects/fluent_dev2/tests/manual-probe
PORT="${1:-12322}"
mkdir -p results-v2
for scenario in missing-word complete-sentence; do
  for i in $(seq 1 10); do
    curl -s -X POST "http://localhost:${PORT}/v1/chat/completions" \
      -H "Content-Type: application/json" \
      -d @"payload-${scenario}.json" \
      > "results-v2/r-${scenario}-${i}.json"
    echo "done ${scenario} ${i}"
  done
done
