#!/usr/bin/env python3
"""
Team T3 -- M3: Suurballe edge-disjoint path pairs + the forwarding state built from them.

Pure Python 3 (no Ryu / Mininet imports), so it can be unit-tested anywhere.
The Ryu application (m3_controller.py) and the offline tests (test_m3.py) both import this file.

Graph format : dict  node -> {neighbour: cost}   (undirected, symmetric, positive costs)
"""
import heapq
from itertools import count

INF = float('inf')


# ----------------------------------------------------------------------------------------
# Shortest paths and Suurballe's algorithm
# ----------------------------------------------------------------------------------------
def dijkstra(adj, src, weight=None):
    """adj: node -> {nbr: cost}. weight(u, v) may override the cost (used for reduced costs).
    Ties are broken by node id, so results are deterministic. Returns (dist, pred)."""
    dist = {src: 0}
    pred = {}
    heap = [(0, src)]
    done = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        for v, c in sorted(adj.get(u, {}).items()):
            w = weight(u, v) if weight else c
            nd = d + w
            if nd < dist.get(v, INF):
                dist[v] = nd
                pred[v] = u
                heapq.heappush(heap, (nd, v))
    return dist, pred


def path_from_pred(pred, src, dst):
    if dst != src and dst not in pred:
        return None
    p = [dst]
    while p[-1] != src:
        p.append(pred[p[-1]])
    return p[::-1]


def path_cost(adj, path):
    return sum(adj[a][b] for a, b in zip(path, path[1:]))


def shortest_path(adj, src, dst, banned_edges=frozenset()):
    """Dijkstra that ignores the undirected edges in banned_edges (set of frozenset({u, v}))."""
    sub = {u: {v: c for v, c in nb.items() if frozenset((u, v)) not in banned_edges}
           for u, nb in adj.items()}
    dist, pred = dijkstra(sub, src)
    p = path_from_pred(pred, src, dst)
    return (p, dist[dst]) if p else (None, INF)


def suurballe(adj, s, t):
    """Minimum-total-cost pair of EDGE-disjoint s-t paths in an undirected graph.
    Returns (path1, path2) as node lists, or None if no such pair exists.

    1. Dijkstra from s -> distances d and shortest path P1.
    2. Reduced costs w'(u,v) = w(u,v) + d(u) - d(v) >= 0.
    3. Residual graph: drop the arcs of P1 in their forward direction; their reverse arcs get real
       cost -w, i.e. reduced cost 0 (the undirected edge's original reverse arc is replaced by it).
    4. Dijkstra on the residual graph with reduced costs gives P2.
    5. Cancel arcs that P1 and P2 use in opposite directions; what is left is two disjoint paths.
    """
    if s == t:
        return None
    d, pred = dijkstra(adj, s)
    if t not in d:
        return None
    p1 = path_from_pred(pred, s, t)
    p1_arcs = set(zip(p1, p1[1:]))

    p1_rev = {(v, u) for (u, v) in p1_arcs}

    def w_red(u, v):
        if (u, v) in p1_rev:
            return 0                          # reversed P1 arc: real cost -w, reduced cost 0
        return adj[u][v] + d[u] - d[v]

    resid = {}
    for u, nb in adj.items():
        if u not in d:
            continue                          # unreachable from s: irrelevant
        resid[u] = {v: c for v, c in nb.items() if v in d and (u, v) not in p1_arcs}
    d2, pred2 = dijkstra(resid, s, weight=w_red)
    p2 = path_from_pred(pred2, s, t)
    if p2 is None:
        return None
    arcs = set(p1_arcs)
    for a in zip(p2, p2[1:]):
        rev = (a[1], a[0])
        if rev in arcs:
            arcs.discard(rev)                 # opposite-direction use cancels
        else:
            arcs.add(a)
    out = {}
    for u, v in arcs:
        out.setdefault(u, []).append(v)
    paths = []
    for _ in range(2):
        cur, path = s, [s]
        while cur != t:
            nxt = sorted(out[cur])[0]
            out[cur].remove(nxt)
            path.append(nxt)
            cur = nxt
        paths.append(path)
    # primary = the cheaper (shorter) of the two; tie -> lexicographically smaller
    paths.sort(key=lambda p: (path_cost(adj, p), p))
    return paths[0], paths[1]


def two_step(adj, s, t):
    """Baseline: shortest path, then shortest path in the graph without its edges."""
    p1, _ = shortest_path(adj, s, t)
    if p1 is None:
        return None
    banned = {frozenset(e) for e in zip(p1, p1[1:])}
    p2, _ = shortest_path(adj, s, t, banned)
    return (p1, p2) if p2 else None


def brute_force_min_pair_cost(adj, s, t):
    """Exhaustive reference: enumerate every simple s-t path, return the minimum total cost
    over all edge-disjoint pairs (INF if none). Only for small graphs."""
    paths = []

    def dfs(u, seen, path):
        if u == t:
            paths.append(list(path))
            return
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                path.append(v)
                dfs(v, seen, path)
                path.pop()
                seen.discard(v)

    dfs(s, {s}, [s])
    edges = [frozenset(zip(p, p[1:])) if False else {frozenset(e) for e in zip(p, p[1:])} for p in paths]
    costs = [path_cost(adj, p) for p in paths]
    best = INF
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            if not (edges[i] & edges[j]):
                best = min(best, costs[i] + costs[j])
    return best


def edge_disjoint(p, q):
    return not ({frozenset(e) for e in zip(p, p[1:])} & {frozenset(e) for e in zip(q, q[1:])})


# ----------------------------------------------------------------------------------------
# Topology description and forwarding state
# ----------------------------------------------------------------------------------------
class Topo:
    """switches: iterable of dpids; links: {(u, v): cost}; ports: {dpid: {neighbour_dpid: port}}
    hosts: {name: (mac, dpid, port)}"""

    def __init__(self, links, hosts, ports=None):
        self.adj = {}
        for (u, v), c in links.items():
            self.adj.setdefault(u, {})[v] = c
            self.adj.setdefault(v, {})[u] = c
        self.hosts = dict(hosts)
        self.ports = ports if ports is not None else self._auto_ports()
        # reverse map for port-status events: (dpid, port) -> neighbour dpid
        self.port_to_nbr = {(u, p): v for u, nb in self.ports.items() for v, p in nb.items()}

    def _auto_ports(self):
        ports = {}
        for u in self.adj:
            ports[u] = {v: i + 1 for i, v in enumerate(sorted(self.adj[u]))}
        return ports


def diamond():
    """The testbed of Section 3: h1 - s1 - {s2 | s3} - s4 - h2 with the same port numbers as M1/M2."""
    links = {(1, 2): 1, (1, 3): 1, (2, 4): 1, (3, 4): 1}
    ports = {1: {2: 2, 3: 3}, 2: {1: 1, 4: 2}, 3: {1: 1, 4: 2}, 4: {2: 1, 3: 2}}
    hosts = {'h1': ('00:00:00:00:00:01', 1, 1), 'h2': ('00:00:00:00:00:02', 4, 3)}
    return Topo(links, hosts, ports)
