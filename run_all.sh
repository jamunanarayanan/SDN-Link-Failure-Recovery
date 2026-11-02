#!/bin/bash
# One command, no babysitting: runs N trials of M1, M2, M2+crankback and M3 on one topology, then analyses them.
#
#   source ~/ryu-venv/bin/activate            # the venv that has ryu-manager (whatever yours is called)
#   sudo env "PATH=$PATH" bash run_all.sh diamond4 10
#
# About 20 s per run -> roughly 15 minutes for 4 mechanisms x 10 trials. Run it, go away, come back.
# Other topologies for the paper:  ring6  mesh10
TOPO=${1:-diamond4}
N=${2:-10}
RYU=${RYU:-$(which ryu-manager)}
PYBIN=${PYBIN:-/usr/bin/python3}          # the python that has Mininet (the venv python usually does not)
[ -x "$RYU" ] || { echo "ryu-manager not found: activate your venv first, and use  sudo env \"PATH=\$PATH\" bash run_all.sh"; exit 1; }
export PYTHONPATH=.
export T3_TOPO=$TOPO

run_set() {   # label controller crankback
  local label=$1 ctrl=$2 crank=$3
  echo "=================== $TOPO / $label : starting controller ==================="
  T3_CRANKBACK=$crank "$RYU" "$ctrl" --ofp-tcp-listen-port 6633 > "ryu_${TOPO}_${label}.log" 2>&1 &
  local cp=$!
  sleep 5
  for i in $(seq 1 "$N"); do
    echo "---- $TOPO $label trial $i of $N ----"
    "$PYBIN" run_multi.py --topo "$TOPO" --label "$label" --fail-at 5 --after 5
    sleep 2
  done
  kill "$cp" 2>/dev/null; wait "$cp" 2>/dev/null
  sleep 2
}

run_set m1  m1_controller_multi.py 1
run_set m2  m2_controller_multi.py 0
run_set m2c m2_controller_multi.py 1
run_set m3  m3_controller_multi.py 1

echo "=================== analysis ==================="
"$PYBIN" analyze_log.py --logs-dir "logs_$TOPO"
echo "Send logs_$TOPO/trials.csv and logs_$TOPO/summary.json (and recovery_trials.png)."
echo "Also check for soft-lockup warnings:  dmesg | grep -i lockup"
