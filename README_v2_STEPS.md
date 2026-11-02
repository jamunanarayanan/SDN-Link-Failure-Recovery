# Team T3 – kit v2: what changed and exactly what to run

## Why there is a v2

1. **M2 had a hidden gap on the way back.** When the s1–s2 link is cut, s1 notices and
   sends h1→h2 traffic through s3. But s4's own port towards s2 is still up, so s4 kept
   sending the h2→h1 *replies* to s2, which then had nowhere to go (its link to s1 is dead).
   A fast-failover group only reacts to a link that is plugged into its *own* switch.
   v2 fixes this inside the switches ("crankback"): s2 bounces such packets back to s4,
   and s4 sends them through s3. Still no controller involved.
2. **The old analysis could be fooled.** If replies stopped completely after the cut, the old
   `analyze_log.py` saw no big gap and printed a tiny recovery time with 0% loss. The new
   one checks whether any reply came back *after* the cut and prints YES/NO per run.
3. **Finer probing.** Pings are now sent every 10 ms instead of 200 ms, so short outages
   are actually visible.
4. **Several trials in one go** (`run_trials.sh`), and the analysis now gives
   mean ± SD and a p-value — exactly what the paper's Table 2 needs.

Files replaced: `m2_controller.py`, `run_experiment.py`, `analyze_log.py`.
New file: `run_trials.sh`. **Keep your existing `topo.py` and `m1_controller.py`.**

---

## Step 1 – Put the 4 files into your simulation folder (Windows)

Unzip this kit. Copy `m2_controller.py`, `run_experiment.py`, `analyze_log.py` and
`run_trials.sh` into your `simulation` folder on Windows and say **Replace** when asked.

## Step 2 – Copy them into the VM

In **Windows PowerShell**, use the *same* `scp` command you used last time to copy the
simulation folder into the VM (same port, same username). Only these 4 files need to go.

## Step 3 – Check your OLD runs first (1 minute)

In the **VM terminal**:
```bash
cd ~/t3-sdn/simulation
python3 analyze_log.py --logs-dir logs
```
Look at the `recovered` column. If your old M2 runs say **NO**, that confirms the gap
described above. Take a screenshot of this table – it is useful for the paper.

## Step 4 – Move the old logs aside

Still in the VM terminal:
```bash
mkdir -p old_logs && mv logs/* old_logs/
```

## Step 5 – Run M1 five times

**Terminal A** (VM):
```bash
cd ~/t3-sdn/simulation
source ~/ryu-venv/bin/activate
ryu-manager m1_controller.py --ofp-tcp-listen-port 6633
```
**Terminal B** (VM):
```bash
cd ~/t3-sdn/simulation
sudo bash run_trials.sh m1 5
```
Each trial takes about 25 seconds. Every trial ends with either
`OK: traffic came back after the cut` or a `WARNING`. When all 5 are done, press
**Ctrl+C** in Terminal A.

## Step 6 – Run M2 five times

**Terminal A**:
```bash
ryu-manager m2_controller.py --ofp-tcp-listen-port 6633
```
**Terminal B**:
```bash
sudo bash run_trials.sh m2 5
```
Ctrl+C in Terminal A when finished.

## Step 7 – Get the results

In the VM:
```bash
python3 analyze_log.py --logs-dir logs
```
**Screenshot the whole output** (both tables and the p-value line) and send it.
If you can, also copy `logs/recovery_trials.png` and `logs/summary.json` back to
Windows with `scp` (same way as before) and attach them.

Tip: close other heavy apps on the laptop while the trials run – the VM's timing is
more stable that way.
