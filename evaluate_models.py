#!/usr/bin/env python3
"""
Offline evaluation of M1, M2, M2+crankback and M3 on several multi-switch topologies.

For every topology, every single link failure and every ordered host pair whose pre-failure path uses
that link (and for which the failure does not disconnect the pair), the script lets the mechanism react
and then walks a packet through the resulting rules (sdn_core.DataPlane).

This measures forwarding STATE and control-plane WORK (flow-mods), not time. Output: results_models.json
"""
import json
import sys

from sdn_core import (TOPOLOGIES, edges_of, plan_m1, react_m1, plan_m2, plan_m3, react_m3, DataPlane,
                      shortest_path, path_edges)

MECHS = ['M1', 'M2', 'M2+cb', 'M3']


def run_topology(name):
    topo = TOPOLOGIES[name]()
    names = sorted(topo.hosts)
    pairs = [(a, b) for a in names for b in names if a != b and topo.hosts[a][1] != topo.hosts[b][1]]
    r1, _ = plan_m1(topo)
    r2, g2 = plan_m2(topo, False)
    r2c, g2c = plan_m2(topo, True)
    r3, f3 = plan_m3(topo)
    state = {'M1': (len(r1), 0), 'M2': (len(r2), len(g2)), 'M2+cb': (len(r2c), len(g2c)), 'M3': (len(r3), 0)}
    res = {m: dict(cases=0, delivered=0, flowmods=0, reacted=0, stretch=[], before_ok=True) for m in MECHS}
    for e in edges_of(topo):
        banned = {frozenset(e)}
        # which ordered pairs are recoverable at all?
        rec = {(a, b): shortest_path(topo.adj, topo.hosts[a][1], topo.hosts[b][1], banned)[0] is not None for a, b in pairs}
        # baseline paths (no failure) per mechanism
        dp0 = {'M1': DataPlane(topo, r1), 'M2': DataPlane(topo, r2, g2), 'M2+cb': DataPlane(topo, r2c, g2c), 'M3': DataPlane(topo, r3)}
        base = {m: {p: dp0[m].send(*p) for p in pairs} for m in MECHS}
        for m in MECHS:
            if any(v is None for v in base[m].values()):
                res[m]['before_ok'] = False
        # M3 reacts once per failed link
        r3_after, n3 = react_m3(r3, f3, e)
        # M1 reacts per affected flow
        add1 = []
        # common case set: the pairs whose M1/M2 (shortest-path-tree) path uses the failed link; all four
        # mechanisms are evaluated on exactly these cases (a mechanism whose own path avoids the link just keeps it)
        common = [p for p in pairs if rec[p] and base['M1'][p] and frozenset(e) in path_edges(base['M1'][p])]
        aff = {m: common for m in MECHS}
        for p in aff['M1']:
            add1 += react_m1(topo, [e], *p)
        dp1 = {'M1': DataPlane(topo, r1 + add1, (), [e]), 'M2': DataPlane(topo, r2, g2, [e]),
               'M2+cb': DataPlane(topo, r2c, g2c, [e]), 'M3': DataPlane(topo, r3_after, (), [e])}
        for m in MECHS:
            for p in aff[m]:
                res[m]['cases'] += 1
                path = dp1[m].send(*p)
                if path is not None:
                    res[m]['delivered'] += 1
                    res[m]['stretch'].append((len(path) - 1) / max(1, len(base[m][p]) - 1))
        # flow-mods
        res['M1']['flowmods'] += sum(len(react_m1(topo, [e], *p)) for p in aff['M1'])
        res['M1']['reacted'] += len(aff['M1'])
        n3hit = sum(1 for f in f3 if 'primary' in f and (f['src'], f['dst']) in set(common) and frozenset(e) in path_edges(f['primary']))
        res['M3']['flowmods'] += n3hit
        res['M3']['reacted'] += n3hit
    out = {}
    for m in MECHS:
        r = res[m]
        out[m] = dict(cases=r['cases'], delivered=r['delivered'],
                      recovery_rate=round(100.0 * r['delivered'] / r['cases'], 1) if r['cases'] else None,
                      flowmods_per_case=round(r['flowmods'] / r['reacted'], 2) if r['reacted'] else (0.0 if r['cases'] else None),
                      reacted=r['reacted'],
                      mean_stretch=round(sum(r['stretch']) / len(r['stretch']), 3) if r['stretch'] else None,
                      rules=state[m][0], groups=state[m][1], baseline_ok=r['before_ok'])
    return dict(switches=len(topo.adj), links=len(edges_of(topo)), hosts=len(topo.hosts), pairs=len(pairs), mechs=out)


if __name__ == '__main__':
    allres = {}
    for n in TOPOLOGIES:
        allres[n] = run_topology(n)
        r = allres[n]
        print('%-9s sw=%2d links=%2d pairs=%3d' % (n, r['switches'], r['links'], r['pairs']))
        for m in MECHS:
            x = r['mechs'][m]
            print('   %-6s cases=%4d delivered=%4d rate=%5s%% flowmods/case=%s stretch=%s rules=%d groups=%d base_ok=%s' % (
                m, x['cases'], x['delivered'], x['recovery_rate'], x['flowmods_per_case'], x['mean_stretch'], x['rules'], x['groups'], x['baseline_ok']))
    json.dump(allres, open('results_models.json', 'w'), indent=1)
