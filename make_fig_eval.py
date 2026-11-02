#!/usr/bin/env python3
"""Figures for the multi-switch evaluation (reads results_models.json and results_suurballe.json)."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

R = json.load(open('results_models.json'))
S = json.load(open('results_suurballe.json'))
MECH = ['M1', 'M2', 'M2+cb', 'M3']
COL = {'M1': '#2a78d6', 'M2': '#eb6834', 'M2+cb': '#1baf7a', 'M3': '#eda100'}
HATCH = {'M1': '', 'M2': '//', 'M2+cb': '..', 'M3': 'xx'}
LAB = {'M1': 'M1 reactive', 'M2': 'M2 fast-failover', 'M2+cb': 'M2 + crankback', 'M3': 'M3 Suurballe'}
INK, MUTED, GRID = '#0b0b0b', '#52514e', '#e1e0d9'
plt.rcParams.update({'font.size': 9, 'axes.edgecolor': '#c3c2b7', 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': MUTED})
topos = list(R)
xl = ['%s\n(%d sw)' % (t.replace('diamond4', 'diamond').replace('ring6', 'ring').replace('ladder8', 'ladder').replace('grid3x3', 'grid').replace('mesh10', 'mesh-10').replace('mesh12', 'mesh-12'), R[t]['switches']) for t in topos]


def style(ax):
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.grid(axis='y', color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def grouped(ax, key, fmt, ymax=None):
    w = 0.2
    for k, m in enumerate(MECH):
        xs = [i + (k - 1.5) * w for i in range(len(topos))]
        vals = [R[t]['mechs'][m][key] for t in topos]
        ax.bar(xs, vals, w * 0.92, color=COL[m], hatch=HATCH[m], edgecolor='white', linewidth=0.6, label=LAB[m], zorder=3)
        for x, v in zip(xs, vals):
            ax.text(x, v + (ymax or max(max(R[t]['mechs'][mm][key] for mm in MECH) for t in topos)) * 0.012, fmt(v), ha='center', va='bottom', fontsize=6.3, color=INK, rotation=90)
    ax.set_xticks(range(len(topos)))
    ax.set_xticklabels(xl)
    style(ax)


# Figure 3: recovery rate
fig, ax = plt.subplots(figsize=(6.4, 3.5))
grouped(ax, 'recovery_rate', lambda v: '%.0f%%' % v, ymax=100)
ax.set_ylim(0, 128)
ax.set_yticks([0, 25, 50, 75, 100])
ax.set_ylabel('Affected flows delivered after\nthe failure (%)')
ax.legend(ncol=4, loc='upper center', frameon=False, fontsize=7.6, bbox_to_anchor=(0.5, 1.06), handlelength=1.4, columnspacing=1.0)
fig.tight_layout()
fig.savefig('fig_eval_recovery.png', dpi=300, facecolor='white')

# Figure 4: control work and installed state
fig, (a, b) = plt.subplots(1, 2, figsize=(6.6, 3.3))
grouped(a, 'flowmods_per_case', lambda v: '%.1f' % v)
a.set_ylim(0, 7.2)
a.set_ylabel('Flow-mods sent per affected flow')
a.set_title('(a) Controller work at failure time', fontsize=8.5, loc='left', color=INK)
w = 0.2
for k, m in enumerate(MECH):
    xs = [i + (k - 1.5) * w for i in range(len(topos))]
    vals = [R[t]['mechs'][m]['rules'] + R[t]['mechs'][m]['groups'] for t in topos]
    b.bar(xs, vals, w * 0.92, color=COL[m], hatch=HATCH[m], edgecolor='white', linewidth=0.6, zorder=3)
b.set_xticks(range(len(topos)))
b.set_xticklabels(xl)
style(b)
b.set_ylabel('Rules + groups installed\nbefore any failure')
b.set_title('(b) Forwarding state', fontsize=8.5, loc='left', color=INK)
for ax_ in (a, b):
    ax_.tick_params(axis='x', labelsize=6.2)
h, l = a.get_legend_handles_labels()
fig.legend(h, l, ncol=4, loc='lower center', frameon=False, fontsize=7.6, bbox_to_anchor=(0.5, -0.01), handlelength=1.4)
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.savefig('fig_eval_cost.png', dpi=300, facecolor='white')

# Figure 5: Suurballe run time
fig, ax = plt.subplots(figsize=(5.2, 3.0))
g = [t for t in S['timing'] if t['topology'].startswith('grid')]
c = [t for t in S['timing'] if t['topology'].startswith('ring')]
ax.plot([t['nodes'] for t in g], [t['median_ms'] for t in g], 'o-', color='#2a78d6', lw=2, ms=6, mec='#fcfcfb', mew=1.5, label='grid')
ax.plot([t['nodes'] for t in c], [t['median_ms'] for t in c], 's-', color='#eb6834', lw=2, ms=6, mec='#fcfcfb', mew=1.5, label='ring + chords')
ax.set_xlabel('Switches in the topology')
ax.set_ylabel('Suurballe, one host pair\n(median ms)')
ax.set_ylim(0, 3)
ax.legend(frameon=False, fontsize=8, loc='upper left')
style(ax)
fig.tight_layout()
fig.savefig('fig_eval_runtime.png', dpi=300, facecolor='white')
print('ok')
