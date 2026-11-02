#!/usr/bin/env python3
"""
M2 on any topology (OpenFlow fast-failover groups). Per (switch, destination) one FF group with the
buckets [primary next hop, local alternate, (bounce back out of the ingress port)]. With crankback ON
(default) every switch also gets one receiver rule that forwards a bounced packet to its local alternate.
The controller does nothing at failure time except log the port-status message.

    T3_TOPO=ladder8 ryu-manager m2_controller_multi.py --ofp-tcp-listen-port 6633
    T3_CRANKBACK=0 ...       # plain local fast-failover, no bounce bucket
"""
import os

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

from sdn_core import plan_m2
from ryu_common import topo_from_env, send_rule, send_group, barrier, stamp


class M2Multi(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.name_, self.topo = topo_from_env()
        self.crank = os.environ.get('T3_CRANKBACK', '1') != '0'
        self.rules, self.groups = plan_m2(self.topo, self.crank)
        stamp('M2', 'topology %s, crankback=%s' % (self.name_, self.crank))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features(self, ev):
        dp = ev.msg.datapath
        for g in self.groups:
            if g['dpid'] == dp.id:
                send_group(dp, g)
        barrier(dp)                     # groups must exist before rules refer to them
        for r in self.rules:
            if r['dpid'] == dp.id:
                send_rule(dp, r)
        stamp('M2', 'switch %d connected: %d groups, rules installed' % (dp.id, sum(1 for g in self.groups if g['dpid'] == dp.id)))

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status(self, ev):
        msg = ev.msg
        if msg.desc.state & msg.datapath.ofproto.OFPPS_LINK_DOWN:
            stamp('M2', 'port status: dpid=%d port=%d DOWN (switch fails over by itself; controller only logs)' % (msg.datapath.id, msg.desc.port_no))
