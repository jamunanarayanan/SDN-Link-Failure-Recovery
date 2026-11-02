#!/bin/bash
# usage: sudo bash run_trials_multi.sh <topo> <m1|m2|m3> [N]   (matching controller already running)
TOPO=$1; LABEL=$2; N=${3:-5}
for i in $(seq 1 "$N"); do
  echo "=========== $TOPO $LABEL trial $i of $N ==========="
  python3 run_multi.py --topo "$TOPO" --label "$LABEL"
  sleep 3
done
echo "now: python3 analyze_log.py --logs-dir logs_$TOPO"
