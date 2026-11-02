#!/usr/bin/env python3
"""
M1 on any topology (reactive). Initial state: destination-based shortest-path rules (priority 10).
On a port-DOWN event the controller finds every host pair whose path uses the failed link, computes a
new shortest path that avoids all failed links and pushes priority-20 rules on every switch of that path.
The time from the port-status message to the last flow-mod being sent is printed ("controller reaction").

    T3_TOPO=ladder8 ryu-manager m1_controller_multi.py --ofp-tcp-listen-port 6633
"""
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

import time
from sdn_core import plan_m1, react_m1, DataPlane, path_edges
from ryu_common import topo_from_env, send_rule, stamp


class M1Multi(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.name_, self.topo = topo_from_env()
        self.rules, _ = plan_m1(self.topo)
        self.dps = {}
        self.failed = set()
        names = sorted(self.topo.hosts)
        self.pairs = [(x, y) for x in names for y in names if x != y and self.topo.hosts[x][1] != self.topo.hosts[y][1]]
        base = DataPlane(self.topo, self.rules)
        self.paths = {p: base.send(*p) for p in self.pairs}
        stamp('M1', 'topology %s: %d switches, %d host pairs' % (self.name_, len(self.topo.adj), len(self.pairs)))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features(self, ev):
        dp = ev.msg.datapath
        self.dps[dp.id] = dp
        self.failed.clear()             # new run: forget links that failed in the previous run
        for r in self.rules:
            if r['dpid'] == dp.id:
                send_rule(dp, r)
        stamp('M1', 'switch %d connected, base rules installed' % dp.id)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status(self, ev):
        t0 = time.time()
        msg = ev.msg
        dp = msg.datapath
        if not (msg.desc.state & dp.ofproto.OFPPS_LINK_DOWN):
            return
        nbr = self.topo.port_to_nbr.get((dp.id, msg.desc.port_no))
        if nbr is None:
            return
        edge = frozenset((dp.id, nbr))
        if edge in self.failed:
            return                      # the other end of the link reports the same failure
        self.failed.add(edge)
        sent = 0
        for p in self.pairs:
            path = self.paths[p]
            if path and edge in path_edges(path):
                for r in react_m1(self.topo, [tuple(e) for e in self.failed], *p):
                    if r['dpid'] in self.dps:
                        send_rule(self.dps[r['dpid']], r)
                        sent += 1
        stamp('M1', 'link s%d-s%d DOWN: %d flow-mods sent, controller reaction %.2f ms' % (dp.id, nbr, sent, (time.time() - t0) * 1000))
