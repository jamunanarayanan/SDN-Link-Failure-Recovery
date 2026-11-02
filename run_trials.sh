#!/bin/bash
# Team T3 -- run several trials of one mechanism back to back.
# Usage (inside the VM, in the simulation folder, with the matching controller
# already running in the other terminal):
#     sudo bash run_trials.sh m1 5
#     sudo bash run_trials.sh m2 5
LABEL=$1
N=${2:-5}
if [ "$LABEL" != "m1" ] && [ "$LABEL" != "m2" ]; then
  echo "usage: sudo bash run_trials.sh m1|m2 [number_of_trials]"; exit 1
fi
for i in $(seq 1 "$N"); do
  echo "================ $LABEL trial $i of $N ================"
  python3 run_experiment.py --label "$LABEL"
  sleep 3
done
echo "done: $N trials of $LABEL. Now run:  python3 analyze_log.py --logs-dir logs"
