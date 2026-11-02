#!/usr/bin/env python3
"""
M3 on any topology: Suurballe edge-disjoint pair for every host pair.
Install time: primary path rules (priority 20) AND backup path rules (priority 10), both matched on
(in_port, eth_src, eth_dst). Failure time: for every flow whose primary path uses the failed link the
controller deletes ONE rule (the primary ingress rule); the dormant backup rules take over. No path
computation happens at failure time.

    T3_TOPO=ladder8 ryu-manager m3_controller_multi.py --ofp-tcp-listen-port 6633
"""
import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

from sdn_core import plan_m3, path_edges
from ryu_common import topo_from_env, send_rule, delete_rule, stamp


class M3Multi(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.name_, self.topo = topo_from_env()
        t0 = time.time()
        self.rules, self.flows = plan_m3(self.topo)
        self.dps = {}
        self.failed = set()
        stamp('M3', 'topology %s: Suurballe pairs for %d flows computed in %.1f ms, %d rules' % (
            self.name_, len(self.flows), (time.time() - t0) * 1000, len(self.rules)))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features(self, ev):
        dp = ev.msg.datapath
        self.dps[dp.id] = dp
        self.failed.clear()             # new run: forget links that failed in the previous run
        for r in self.rules:
            if r['dpid'] == dp.id:
                send_rule(dp, r)
        stamp('M3', 'switch %d connected, primary + backup rules installed' % dp.id)

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
            return
        self.failed.add(edge)
        sent = 0
        for f in self.flows:
            if 'primary' in f and edge in path_edges(f['primary']):
                for r in self.rules:
                    if (r['role'] == 'primary' and r['dpid'] == f['ingress'] and r['in_port'] == f['ingress_port']
                            and r['eth_src'] == f['eth_src'] and r['eth_dst'] == f['eth_dst']):
                        delete_rule(self.dps[f['ingress']], r)
                        sent += 1
        stamp('M3', 'link s%d-s%d DOWN: %d flow-mod deletions sent, controller reaction %.2f ms' % (dp.id, nbr, sent, (time.time() - t0) * 1000))
