#!/usr/bin/env python3
"""
Team T3 -- analyse ALL failover trials in a logs folder (v2).

What changed from v1 (important):
  v1 looked for the biggest gap between replies. If traffic never came back
  after the link cut, there simply were no replies after it, so v1 saw no big
  gap and reported a tiny "recovery time" with 0% loss. v2 uses the cut time
  stored in the meta file and checks whether any probe sent AFTER the cut was
  answered.

Definitions (match the paper):
  send time of a probe      = reply timestamp - RTT
  recovery time R           = send time of the first answered probe sent after
                              the cut  -  cut time        (resolution = probe interval)
  probes lost               = sequence numbers between the last answered probe
                              before the cut and the first answered probe after it
  recovered                 = at least one probe sent after the cut was answered

Usage:
    python3 analyze_log.py --logs-dir logs
    python3 analyze_log.py --logs-dir logs --since 20261018-000000   (only newer runs)

Writes logs/trials.csv, logs/summary.json, logs/recovery_trials.png
"""

import argparse
import csv
import glob
import itertools
import json
import os
import random
import re
import statistics as st
import sys

LINE_RE = re.compile(r'^\[(?P<ts>\d+\.\d+)\]\s+\d+ bytes from .*icmp_seq=(?P<seq>\d+).*time=(?P<rtt>[\d.]+)\s*ms')
NAME_RE = re.compile(r'ping_(?P<label>m(?:2c|[123]))_(?P<stamp>\d{8}-\d{6})\.log$')


def read_meta(path):
    meta = {}
    with open(path) as f:
        for line in f:
            if '=' in line:
                k, v = line.strip().split('=', 1)
                meta[k] = v
    return meta


def parse_ping(path):
    out = []
    with open(path) as f:
        for line in f:
            m = LINE_RE.match(line.strip())
            if m:
                ts, rtt = float(m.group('ts')), float(m.group('rtt'))
                out.append({'seq': int(m.group('seq')), 'recv': ts, 'rtt_ms': rtt, 'send': ts - rtt / 1000.0})
    out.sort(key=lambda r: r['send'])
    return out


def analyse_trial(ping_path, meta_path):
    meta = read_meta(meta_path)
    t_cut = float(meta['link_cut'])
    interval = float(meta.get('interval', 0.2))
    replies = parse_ping(ping_path)
    before = [r for r in replies if r['send'] < t_cut]
    after = [r for r in replies if r['send'] >= t_cut]
    res = {
        'file': os.path.basename(ping_path),
        'interval_ms': interval * 1000,
        'replies_total': len(replies),
        'replies_after_cut': len(after),
        'recovered': bool(after),
        'recovery_ms': None,
        'probes_lost': None,
    }
    if after and before:
        first_after = min(after, key=lambda r: r['send'])
        last_before = max(before, key=lambda r: r['seq'])
        res['recovery_ms'] = round((first_after['send'] - t_cut) * 1000, 2)
        res['probes_lost'] = first_after['seq'] - last_before['seq'] - 1
    return res


def perm_test(a, b, max_exact=200000, n_random=100000, seed=1):
    """Two-sided permutation test on the difference of means. Exact when feasible."""
    pooled = a + b
    n, na = len(pooled), len(a)
    observed = abs(st.mean(a) - st.mean(b))
    total = sum(pooled)
    combos = 1
    for i in range(na):
        combos = combos * (n - i) // (i + 1)
    count = 0
    if combos <= max_exact:
        for idx in itertools.combinations(range(n), na):
            sa = sum(pooled[i] for i in idx)
            if abs(sa / na - (total - sa) / (n - na)) >= observed - 1e-12:
                count += 1
        return count / combos, 'exact'
    rng = random.Random(seed)
    for _ in range(n_random):
        rng.shuffle(pooled)
        if abs(st.mean(pooled[:na]) - st.mean(pooled[na:])) >= observed - 1e-12:
            count += 1
    return (count + 1) / (n_random + 1), 'monte-carlo'


def describe(vals):
    if not vals:
        return None
    return {'n': len(vals), 'mean': round(st.mean(vals), 2),
            'sd': round(st.stdev(vals), 2) if len(vals) > 1 else 0.0,
            'median': round(st.median(vals), 2), 'min': min(vals), 'max': max(vals)}


def make_chart(trials, out_png):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = {'m1': '#2a78d6', 'm2': '#eb6834', 'm2c': '#1baf7a', 'm3': '#eda100'}
    labs = [l for l in ('m1', 'm2', 'm2c', 'm3') if any(t['label'] == l for t in trials)]
    names = {'m1': 'M1\nReactive (controller)', 'm2': 'M2\nFast-Failover (switch)', 'm2c': 'M2 + crankback\n(switch)', 'm3': 'M3\nDisjoint pair (Suurballe)'}
    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    for i, lab in enumerate(labs):
        vals = [t['recovery_ms'] for t in trials if t['label'] == lab and t['recovery_ms'] is not None]
        if not vals:
            continue
        jitter = [i + (k - (len(vals) - 1) / 2) * 0.05 for k in range(len(vals))]
        ax.scatter(jitter, vals, s=40, color=colors[lab], edgecolor='white', linewidth=1.5, zorder=3)
        m = st.mean(vals)
        sd = st.stdev(vals) if len(vals) > 1 else 0
        ax.errorbar([i + 0.28], [m], yerr=[sd], fmt='D', color='#0b0b0b', markersize=6, capsize=4, lw=1.2, zorder=4)
        ax.text(i + 0.36, m, f'mean {m:.1f} ms\n± {sd:.1f} (n={len(vals)})', va='center', fontsize=8.5)
    ax.set_xticks(range(len(labs)))
    ax.set_xticklabels([names[l] for l in labs], fontsize=9.5)
    ax.set_xlim(-0.5, len(labs) - 0.1)
    ax.set_ylim(bottom=0)
    top = ax.get_ylim()[1]
    for i, lab in enumerate(labs):
        nr = sum(1 for t in trials if t['label'] == lab and not t['recovered'])
        if nr:
            ax.text(i, top * 0.03, f'{nr} run(s) did not recover', ha='center', fontsize=8, color='#b23b3b')
    ax.set_ylabel('Recovery time (ms)', fontsize=9.5)
    ax.grid(axis='y', color='#e4e3df', lw=0.8)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_png, dpi=300, facecolor='white')
    print(f'chart -> {out_png}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--logs-dir', default='logs')
    ap.add_argument('--since', default=None, help='only runs with timestamp >= this (YYYYMMDD-HHMMSS)')
    args = ap.parse_args()

    trials = []
    for ping_path in sorted(glob.glob(os.path.join(args.logs_dir, 'ping_m*_*.log'))):
        m = NAME_RE.search(os.path.basename(ping_path))
        if not m or (args.since and m.group('stamp') < args.since):
            continue
        meta_path = os.path.join(args.logs_dir, f"meta_{m.group('label')}_{m.group('stamp')}.txt")
        if not os.path.exists(meta_path):
            print(f'skip {ping_path}: no matching meta file')
            continue
        t = analyse_trial(ping_path, meta_path)
        t['label'] = m.group('label')
        t['stamp'] = m.group('stamp')
        trials.append(t)

    if not trials:
        sys.exit('No trials found. Run run_experiment.py first.')

    print('\n=== Team T3 -- every trial ===\n')
    print(f'{"run":22s} {"mech":4s} {"probe":>7s} {"recovered":>10s} {"recovery ms":>12s} {"lost":>5s} {"replies after cut":>18s}')
    print('-' * 84)
    for t in trials:
        rec = f"{t['recovery_ms']:.1f}" if t['recovery_ms'] is not None else '-'
        lost = str(t['probes_lost']) if t['probes_lost'] is not None else '-'
        print(f"{t['stamp']:22s} {t['label'].upper():4s} {t['interval_ms']:5.0f}ms {('YES' if t['recovered'] else 'NO'):>10s} "
              f"{rec:>12s} {lost:>5s} {t['replies_after_cut']:>18d}")

    summary = {}
    LABELS = [l for l in ('m1', 'm2', 'm2c', 'm3') if any(t['label'] == l for t in trials)]
    for lab in LABELS:
        ts = [t for t in trials if t['label'] == lab]
        ok = [t for t in ts if t['recovery_ms'] is not None]
        summary[lab] = {
            'trials': len(ts),
            'recovered': sum(1 for t in ts if t['recovered']),
            'recovery_ms': describe([t['recovery_ms'] for t in ok]),
            'probes_lost': describe([t['probes_lost'] for t in ok]),
        }
    for i, x in enumerate(LABELS):
        for y in LABELS[i + 1:]:
            a = [t['recovery_ms'] for t in trials if t['label'] == x and t['recovery_ms'] is not None]
            b = [t['recovery_ms'] for t in trials if t['label'] == y and t['recovery_ms'] is not None]
            if len(a) >= 2 and len(b) >= 2:
                p, kind = perm_test(a, b)
                summary[f'{x}_vs_{y}_recovery_p_value'] = round(p, 4)
                summary['test'] = f'two-sided {kind} permutation test, difference in mean recovery time'

    print('\n=== Team T3 -- summary (mean +/- SD over recovered trials) ===\n')
    for lab in LABELS:
        s = summary[lab]
        r = s['recovery_ms']
        l = s['probes_lost']
        rs = f"{r['mean']:.1f} +/- {r['sd']:.1f} ms (median {r['median']:.1f})" if r else 'n/a'
        ls = f"{l['mean']:.1f} +/- {l['sd']:.1f}" if l else 'n/a'
        print(f"{lab.upper()}: recovered {s['recovered']}/{s['trials']}   recovery {rs}   probes lost {ls}")
    for k, v in summary.items():
        if k.endswith('_p_value'):
            print(f"p-value ({k.replace('_recovery_p_value','').replace('_vs_',' vs ').upper()} recovery time): {v}  [{summary['test']}]")

    with open(os.path.join(args.logs_dir, 'trials.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(trials[0].keys()))
        w.writeheader()
        w.writerows(trials)
    with open(os.path.join(args.logs_dir, 'summary.json'), 'w') as f:
        json.dump({'trials': trials, 'summary': summary}, f, indent=2)
    print(f"\ntables -> {os.path.join(args.logs_dir, 'trials.csv')}, {os.path.join(args.logs_dir, 'summary.json')}")
    try:
        make_chart(trials, os.path.join(args.logs_dir, 'recovery_trials.png'))
    except ImportError:
        print('matplotlib missing: sudo apt install -y python3-matplotlib  (numbers above are still valid)')


if __name__ == '__main__':
    main()
