#!/usr/bin/env python3
"""Offline checks of the Suurballe implementation (m3_paths.py). Output: results_suurballe.json
  1. optimality: total cost equals an exhaustive search over all simple-path pairs (small random graphs)
  2. baseline: 'shortest path, then shortest path without its links' (two-step) on the same instances
  3. run time versus topology size
"""
import json
import random
import statistics
import time

from m3_paths import suurballe, two_step, brute_force_min_pair_cost, path_cost, edge_disjoint, INF
from sdn_core import grid, ring_chords


def rand_graph(rnd, n):
    adj = {i: {} for i in range(n)}
    nodes = list(range(n))
    rnd.shuffle(nodes)
    for a, b in zip(nodes, nodes[1:]):               # random spanning path -> connected
        c = rnd.randint(1, 5)
        adj[a][b] = adj[b][a] = c
    for _ in range(rnd.randint(1, n + 2)):
        a, b = rnd.sample(range(n), 2)
        if b not in adj[a]:
            c = rnd.randint(1, 5)
            adj[a][b] = adj[b][a] = c
    return adj


def main():
    rnd = random.Random(2026)
    N = 3000
    pair_exists = agree = disjoint_ok = 0
    ts_found = ts_opt = 0
    ts_missed = 0
    excess = []
    for _ in range(N):
        n = rnd.randint(5, 9)
        adj = rand_graph(rnd, n)
        s, t = rnd.sample(range(n), 2)
        best = brute_force_min_pair_cost(adj, s, t)
        sp = suurballe(adj, s, t)
        if best == INF:
            assert sp is None
            continue
        pair_exists += 1
        assert sp is not None
        p, q = sp
        disjoint_ok += edge_disjoint(p, q) and p[0] == s and p[-1] == t and q[0] == s and q[-1] == t
        cost = path_cost(adj, p) + path_cost(adj, q)
        agree += (cost == best)
        ts = two_step(adj, s, t)
        if ts is None:
            ts_missed += 1
        else:
            ts_found += 1
            c2 = path_cost(adj, ts[0]) + path_cost(adj, ts[1])
            ts_opt += (c2 == best)
            excess.append(100.0 * (c2 - best) / best)
    res = dict(instances=N, with_disjoint_pair=pair_exists, suurballe_optimal=agree, suurballe_valid_disjoint=disjoint_ok,
               two_step_found=ts_found, two_step_missed=ts_missed, two_step_optimal=ts_opt,
               two_step_mean_excess_pct_when_found=round(statistics.mean(excess), 2) if excess else None)
    # timing
    timing = []
    for label, topo in [('grid %dx%d' % (k, k), grid(k, k)) for k in (3, 6, 10, 15, 20)] + \
                       [('ring+chords n=%d' % n, ring_chords(n, n // 2, 5)) for n in (50, 200, 500)]:
        adj = topo.adj
        nodes = sorted(adj)
        s, t = nodes[0], nodes[-1]
        runs = []
        for _ in range(7):
            t0 = time.perf_counter()
            r = suurballe(adj, s, t)
            runs.append((time.perf_counter() - t0) * 1000)
        assert r is not None and edge_disjoint(*r)
        timing.append(dict(topology=label, nodes=len(adj), links=sum(len(v) for v in adj.values()) // 2,
                           median_ms=round(statistics.median(runs), 3)))
    res['timing'] = timing
    json.dump(res, open('results_suurballe.json', 'w'), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
