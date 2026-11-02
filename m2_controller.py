#!/usr/bin/env python3
"""
Team T3 -- M2: OpenFlow Fast-Failover (FF) group tables, WITH crankback (v2)

Why v2 exists
-------------
In v1, s1 and s4 each had a FF group that watched their OWN ports. When the
s1<->s2 link is cut, s1 notices (its port goes down) and switches h1->h2 traffic
to s3. But s4's port towards s2 stays UP, so s4 kept sending the h2->h1 replies
to s2, and s2 tried to forward them over the dead s2->s1 link, where they were
dropped. A fast-failover group can only react to a failure on a link that is
attached to the switch it sits on.

v2 fixes the return path entirely in the data plane ("crankback"):
  * s2 gets FF groups too. If s2's port towards s1 is down, packets for h1 are
    sent straight back out of the port they came in on (OFPP_IN_PORT), i.e.
    back to s4. Same idea for packets towards h2 if the s2<->s4 link fails.
  * s4 gets one extra rule: a packet for h1 that ARRIVES from s2 can only be a
    bounced-back packet (in normal operation h1-bound traffic never enters s4
    from s2), so it is sent to s3 instead. s1 gets the mirror-image rule.
No controller message is needed for any of this; the controller still only
logs port-status events.

Run with:
    ryu-manager m2_controller.py --ofp-tcp-listen-port 6633
"""

import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3

H1_MAC = '00:00:00:00:00:01'
H2_MAC = '00:00:00:00:00:02'

PORTS = {
    1: {'h1': 1, 's2': 2, 's3': 3},   # s1
    2: {'s1': 1, 's4': 2},            # s2
    3: {'s1': 1, 's4': 2},            # s3
    4: {'s2': 1, 's3': 2, 'h2': 3},   # s4
}

GROUP_TO_H2 = 1
GROUP_TO_H1 = 2


class M2FastFailoverController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}

    def log(self, msg):
        print(f"[M2] t={time.time():.6f}  {msg}", flush=True)

    def add_flow(self, dp, priority, match, actions):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority, match=match,
                                      instructions=inst, buffer_id=ofp.OFP_NO_BUFFER))

    def ff_group(self, dp, group_id, buckets):
        """buckets = list of (watch_port, out_port). out_port may be OFPP_IN_PORT."""
        ofp, parser = dp.ofproto, dp.ofproto_parser
        bl = [parser.OFPBucket(watch_port=w, watch_group=ofp.OFPG_ANY,
                               actions=[parser.OFPActionOutput(o)]) for w, o in buckets]
        dp.send_msg(parser.OFPGroupMod(datapath=dp, command=ofp.OFPGC_ADD, type_=ofp.OFPGT_FF,
                                       group_id=group_id, buckets=bl))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        self.datapaths[dp.id] = dp
        IN = ofp.OFPP_IN_PORT
        to = lambda mac: parser.OFPMatch(eth_dst=mac)
        grp = lambda gid: [parser.OFPActionGroup(gid)]
        out = lambda p: [parser.OFPActionOutput(p)]

        # table-miss -> controller (only used for logging/debugging)
        self.add_flow(dp, 0, parser.OFPMatch(),
                      [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)])

        if dp.id == 1:      # s1: branch point towards h2
            p = PORTS[1]
            self.ff_group(dp, GROUP_TO_H2, [(p['s2'], p['s2']), (p['s3'], p['s3'])])
            self.add_flow(dp, 10, to(H2_MAC), grp(GROUP_TO_H2))
            self.add_flow(dp, 10, to(H1_MAC), out(p['h1']))
            # crankback receiver: h2-bound packet bounced back by s2 -> use s3
            self.add_flow(dp, 20, parser.OFPMatch(in_port=p['s2'], eth_dst=H2_MAC), out(p['s3']))

        elif dp.id == 2:    # s2: primary-path transit switch, now with crankback
            p = PORTS[2]
            self.ff_group(dp, GROUP_TO_H2, [(p['s4'], p['s4']), (p['s1'], IN)])
            self.ff_group(dp, GROUP_TO_H1, [(p['s1'], p['s1']), (p['s4'], IN)])
            self.add_flow(dp, 10, to(H2_MAC), grp(GROUP_TO_H2))
            self.add_flow(dp, 10, to(H1_MAC), grp(GROUP_TO_H1))

        elif dp.id == 3:    # s3: backup-path transit switch, plain forwarding
            p = PORTS[3]
            self.add_flow(dp, 10, to(H2_MAC), out(p['s4']))
            self.add_flow(dp, 10, to(H1_MAC), out(p['s1']))

        elif dp.id == 4:    # s4: branch point towards h1
            p = PORTS[4]
            self.ff_group(dp, GROUP_TO_H1, [(p['s2'], p['s2']), (p['s3'], p['s3'])])
            self.add_flow(dp, 10, to(H1_MAC), grp(GROUP_TO_H1))
            self.add_flow(dp, 10, to(H2_MAC), out(p['h2']))
            # crankback receiver: h1-bound packet bounced back by s2 -> use s3
            self.add_flow(dp, 20, parser.OFPMatch(in_port=p['s2'], eth_dst=H1_MAC), out(p['s3']))

        self.log(f"switch dpid={dp.id} connected, fast-failover + crankback state installed")

    # observability only -- NOT part of the failover path
    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        ofp = msg.datapath.ofproto
        down = bool(msg.desc.state & ofp.OFPPS_LINK_DOWN)
        self.log(f"port status: dpid={msg.datapath.id} port={msg.desc.port_no} "
                 f"{'DOWN (switch already failed over by itself; controller only logs this)' if down else 'UP'}")
