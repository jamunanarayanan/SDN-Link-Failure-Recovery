# Team T3 – kit v3: M3 and multi-switch topologies

What is new compared with kit v2
- `m3_paths.py`   Suurballe's algorithm (edge-disjoint pair of minimum total cost), two-step baseline, exhaustive checker.
- `sdn_core.py`   Topologies (diamond4, ring6, ladder8, grid3x3, mesh10, mesh12) and the rule/group tables of M1, M2 (with and
                  without crankback) and M3 for ANY topology, plus a small data-plane model that walks a packet through them.
- `evaluate_models.py`, `test_m3.py`, `make_fig_eval.py`   the offline evaluation reported in Section 4.4 of the paper.
- `results_models.json`, `results_suurballe.json`, `fig_eval_*.png`   the numbers and figures in the paper.
- `m1_controller_multi.py`, `m2_controller_multi.py`, `m3_controller_multi.py`   Ryu apps for any topology (pick it with T3_TOPO).
- `topo_multi.py`, `run_multi.py`, `run_trials_multi.sh`   Mininet topology builder and the failure experiment.
- `analyze_log.py` now handles m1, m2 and m3.

## 1. Re-run the offline evaluation (any computer with Python 3, no Mininet needed)
    python3 test_m3.py          # Suurballe vs exhaustive search, run time  -> results_suurballe.json
    python3 evaluate_models.py  # M1/M2/M3 on six topologies                -> results_models.json
    python3 make_fig_eval.py    # needs matplotlib                          -> fig_eval_*.png

## 2. Run all the trials with ONE command (in your VM, about 15 minutes, unattended)
    source ~/<your-ryu-venv>/bin/activate
    cd <kit folder>
    sudo env "PATH=$PATH" bash run_all.sh diamond4 10

This starts each controller itself (M1, M2, M2+crankback, M3), runs 10 trials of each, stops the controller, and finally runs
the analysis. Results: logs_diamond4/trials.csv, summary.json, recovery_trials.png. Then, if you have time, repeat with `ring6` and `mesh10`.
Check `dmesg | grep -i lockup` afterwards; discard the batch if the VM reported a soft lockup, and close other programs first.

Notes
- Labels: m1 = M1, m2 = plain fast-failover, m2c = fast-failover with crankback, m3 = M3.
- The M2 crankback bucket uses watch_port = OFPP_ANY ("always live"). Open vSwitch treats that as live. If the
  group-mod is rejected on your OVS version, the ryu_<topo>_m2c.log file will say so - tell us and we will change it.
- The controllers and Mininet scripts were checked for syntax and use the same rule tables as the offline evaluation,
  but they were not run against Mininet/Ryu (the cloud sandbox cannot run Mininet). If run_all.sh stops with an error, send us the last 20 lines.
- Send us trials.csv / summary.json and we will add the results table to Section 4 and update the abstract and conclusion.

## 3. Putting the code on GitHub and Zenodo (for the Data availability statement)
1. Create a public GitHub repository (e.g. t3-sdn-link-recovery) and upload this folder plus your probe logs.
2. In Zenodo, link your GitHub account, switch the repository on, and create a release on GitHub; Zenodo then issues a DOI.
3. Paste the GitHub URL and the Zenodo DOI into the yellow placeholders of the Data availability paragraph.
