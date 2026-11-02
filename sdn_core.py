#!/usr/bin/env python3
"""
Team T3 -- shared core for M1 / M2 / M3 on ARBITRARY topologies (v3).

Everything the three controllers push to the switches is *computed here* as plain data
(rules and groups), so the same code is
  * turned into OpenFlow messages by m1_controller_multi.py / m2_controller_multi.py / m3_controller_multi.py
  * exercised offline by evaluate_models.py (which walks packets through the same rules).

Python 3.8 compatible. No Ryu / Mininet imports.

Rule  : dict(dpid, priority, in_port|None, eth_src|None, eth_dst, action, role)
        action = ('out', port) | ('group', gid)
Group : dict(dpid, gid, buckets=[(watch_port|None, ('out', port) | ('in',))])   # fast-failover semantics
"""
import random

from m3_paths import Topo, dijkstra, path_from_pred, shortest_path, suurballe, path_cost, INF, diamond

# ----------------------------------------------------------------------------------------
# Topologies
# ----------------------------------------------------------------------------------------

def mac_of(dpid):
    return '00:00:00:00:00:%02x' % dpid


def _with_hosts(links, nodes, costs=None):
    """one host h<dpid> on every switch, attached to the last port of that switch."""
    adj = {u: set() for u in nodes}
    for (u, v) in links:
        adj[u].add(v)
        adj[v].add(u)
    ports = {u: {v: i + 1 for i, v in enumerate(sorted(adj[u]))} for u in nodes}
    hosts = {'h%d' % u: (mac_of(u), u, len(adj[u]) + 1) for u in nodes}
    cl = {(u, v): (costs or {}).get((u, v), 1) for (u, v) in links}
    return Topo(cl, hosts, ports)


def ring(n):
    return _with_hosts([(i, i % n + 1) for i in range(1, n + 1)], range(1, n + 1))


def ladder(k):
    """2 x k ladder: switches 1..k (top row) and k+1..2k (bottom row), rungs between them."""
    links = [(i, i + 1) for i in range(1, k)] + [(k + i, k + i + 1) for i in range(1, k)] + [(i, k + i) for i in range(1, k + 1)]
    return _with_hosts(links, range(1, 2 * k + 1))


def grid(r, c):
    idx = lambda i, j: i * c + j + 1
    links = []
    for i in range(r):
        for j in range(c):
            if j + 1 < c:
                links.append((idx(i, j), idx(i, j + 1)))
            if i + 1 < r:
                links.append((idx(i, j), idx(i + 1, j)))
    return _with_hosts(links, range(1, r * c + 1))


def ring_chords(n, chords, seed):
    """ring of n switches plus `chords` random chords, link costs drawn from {1,2,3} (seeded)."""
    rnd = random.Random(seed)
    links = [(i, i % n + 1) for i in range(1, n + 1)]
    have = {frozenset(e) for e in links}
    while len(links) < n + chords:
        u, v = rnd.sample(range(1, n + 1), 2)
        if frozenset((u, v)) not in have:
            have.add(frozenset((u, v)))
            links.append((min(u, v), max(u, v)))
    costs = {e: rnd.choice([1, 2, 3]) for e in links}
    return _with_hosts(links, range(1, n + 1), costs)


TOPOLOGIES = {
    'diamond4': lambda: diamond(),
    'ring6': lambda: ring(6),
    'ladder8': lambda: ladder(4),
    'grid3x3': lambda: grid(3, 3),
    'mesh10': lambda: ring_chords(10, 5, 11),
    'mesh12': lambda: ring_chords(12, 6, 12),
}


def edges_of(topo):
    return sorted({tuple(sorted((u, v))) for u in topo.adj for v in topo.adj[u]})


def host_by_mac(topo):
    return {m: h for h, (m, _, _) in topo.hosts.items()}


# ----------------------------------------------------------------------------------------
# Plans
# ----------------------------------------------------------------------------------------

def _rule(dpid, prio, eth_dst, action, role, in_port=None, eth_src=None):
    return dict(dpid=dpid, priority=prio, in_port=in_port, eth_src=eth_src, eth_dst=eth_dst, action=action, role=role)


def spt_next_hops(topo, d):
    """next hop of every switch towards switch d on the (deterministic) shortest-path tree."""
    _, pred = dijkstra(topo.adj, d)
    return pred


def plan_m1(topo):
    """M1 initial state: destination-based shortest-path rules, priority 10."""
    rules = []
    for h, (mac, d, hport) in topo.hosts.items():
        pred = spt_next_hops(topo, d)
        rules.append(_rule(d, 10, mac, ('out', hport), 'base'))
        for x, nh in pred.items():
            rules.append(_rule(x, 10, mac, ('out', topo.ports[x][nh]), 'base'))
    return rules, []


def react_m1(topo, failed_edges, src_h, dst_h):
    """Rules the controller pushes for ONE flow once it learns of the failure: shortest path avoiding
    all failed links, installed on every switch of the new path (priority 20, matched on src+dst MAC)."""
    ms, a, ph_a = topo.hosts[src_h]
    md, b, ph_b = topo.hosts[dst_h]
    banned = {frozenset(e) for e in failed_edges}
    p, _ = shortest_path(topo.adj, a, b, banned)
    if p is None:
        return []
    out = []
    for k, sw in enumerate(p):
        port = ph_b if k == len(p) - 1 else topo.ports[sw][p[k + 1]]
        out.append(_rule(sw, 20, md, ('out', port), 'm1-backup', eth_src=ms))
    return out


def plan_m2(topo, crankback):
    """M2: per (switch, destination) a fast-failover group [primary, local alternate, (bounce)].
    local alternate = first hop of the shortest path that avoids the primary's first link.
    crankback=True adds a final OFPP_IN_PORT bucket and one receiver rule per group."""
    rules, groups = [], []
    for gid, (h, (mac, d, hport)) in enumerate(sorted(topo.hosts.items()), start=1):
        pred = spt_next_hops(topo, d)
        rules.append(_rule(d, 10, mac, ('out', hport), 'base'))
        for x, prim in pred.items():
            pport = topo.ports[x][prim]
            buckets = [(pport, ('out', pport))]
            alt_path, _ = shortest_path(topo.adj, x, d, {frozenset((x, prim))})
            if alt_path:
                aport = topo.ports[x][alt_path[1]]
                buckets.append((aport, ('out', aport)))
                if crankback:
                    # a packet that comes back from the primary next hop is a bounced packet
                    rules.append(_rule(x, 20, mac, ('out', aport), 'crankback-rx', in_port=pport))
            if crankback:
                buckets.append((None, ('in',)))
            groups.append(dict(dpid=x, gid=gid, buckets=buckets))
            rules.append(_rule(x, 10, mac, ('group', gid), 'base'))
    return rules, groups


def plan_m3(topo):
    """M3: Suurballe pair per host pair; primary rules priority 20, backup rules priority 10, both matched
    on (in_port, eth_src, eth_dst). Returns rules and the per-direction flow records."""
    rules, flows = [], []
    names = sorted(topo.hosts)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ma, sa, pa = topo.hosts[a]
            mb, sb, pb = topo.hosts[b]
            if sa == sb:
                continue
            pair = suurballe(topo.adj, sa, sb)
            if pair is None:
                flows.append(dict(src=a, dst=b, error='no edge-disjoint pair'))
                continue
            prim, back = pair
            for src, dst, msrc, mdst, pp, bp, ih, oh in ((a, b, ma, mb, prim, back, pa, pb),
                                                         (b, a, mb, ma, prim[::-1], back[::-1], pb, pa)):
                for role, path, prio in (('primary', pp, 20), ('backup', bp, 10)):
                    for k, sw in enumerate(path):
                        inp = ih if k == 0 else topo.ports[sw][path[k - 1]]
                        outp = oh if k == len(path) - 1 else topo.ports[sw][path[k + 1]]
                        rules.append(_rule(sw, prio, mdst, ('out', outp), role, in_port=inp, eth_src=msrc))
                flows.append(dict(src=src, dst=dst, eth_src=msrc, eth_dst=mdst, primary=pp, backup=bp,
                                  ingress=pp[0], ingress_port=ih))
    return rules, flows


def react_m3(rules, flows, failed_edge):
    """On a port-down event: withdraw the primary ingress rule of every flow whose primary path uses the
    failed link. Returns (new rule list, number of flow-mod deletions)."""
    fe = frozenset(failed_edge)
    hit = [f for f in flows if 'primary' in f and fe in {frozenset(e) for e in zip(f['primary'], f['primary'][1:])}]
    drop = {(f['ingress'], f['ingress_port'], f['eth_src'], f['eth_dst']) for f in hit}
    new = [r for r in rules if not (r['role'] == 'primary' and (r['dpid'], r['in_port'], r['eth_src'], r['eth_dst']) in drop)]
    return new, len(drop)


# ----------------------------------------------------------------------------------------
# Data-plane model (offline tests only): OpenFlow-style rule match + fast-failover groups
# ----------------------------------------------------------------------------------------

class DataPlane:
    def __init__(self, topo, rules, groups=(), failed=()):
        self.t = topo
        self.idx = {}
        for r in rules:
            self.idx.setdefault((r['dpid'], r['eth_dst']), []).append(r)
        self.groups = {(g['dpid'], g['gid']): g for g in groups}
        self.failed = {frozenset(e) for e in failed}
        self.host_ports = {(sw, p): h for h, (_, sw, p) in topo.hosts.items()}

    def live(self, sw, port):
        if (sw, port) in self.host_ports:
            return True
        nbr = self.t.port_to_nbr.get((sw, port))
        return nbr is not None and frozenset((sw, nbr)) not in self.failed

    def send(self, src_h, dst_h, max_hops=64):
        """returns the list of switches visited if delivered, else None (drop / blackhole / loop)."""
        mac_s, sw, in_port = self.t.hosts[src_h]
        mac_d = self.t.hosts[dst_h][0]
        visited = [sw]
        seen = set()
        for _ in range(max_hops):
            if (sw, in_port) in seen:
                return None                    # forwarding loop
            seen.add((sw, in_port))
            cand = [r for r in self.idx.get((sw, mac_d), [])
                    if r['in_port'] in (None, in_port) and r['eth_src'] in (None, mac_s)]
            if not cand:
                return None
            r = max(cand, key=lambda x: (x['priority'], (x['in_port'] is not None) + (x['eth_src'] is not None)))
            act = r['action']
            if act[0] == 'group':
                g = self.groups[(sw, act[1])]
                act = None
                for w, a in g['buckets']:
                    if w is None or self.live(sw, w):
                        act = a
                        break
                if act is None:
                    return None
            if act[0] == 'in':
                out = in_port
                if (sw, out) in self.host_ports:
                    return None
            else:
                out = act[1]
            if (sw, out) in self.host_ports:
                return visited if self.host_ports[(sw, out)] == dst_h else None
            if not self.live(sw, out):
                return None                    # sent into a dead link
            nbr = self.t.port_to_nbr[(sw, out)]
            in_port = self.t.ports[nbr][sw]
            sw = nbr
            visited.append(sw)
        return None


def path_edges(p):
    return {frozenset(e) for e in zip(p, p[1:])}
