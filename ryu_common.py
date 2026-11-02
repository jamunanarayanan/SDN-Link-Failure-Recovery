"""Translate the plain-data rules/groups of sdn_core.py into OpenFlow 1.3 messages (Ryu)."""
import os
import time

from sdn_core import TOPOLOGIES


def topo_from_env():
    name = os.environ.get('T3_TOPO', 'ladder8')
    if name not in TOPOLOGIES:
        raise SystemExit('unknown T3_TOPO=%s (choose from %s)' % (name, ', '.join(TOPOLOGIES)))
    return name, TOPOLOGIES[name]()


def stamp(tag, msg):
    print('[%s] t=%.6f  %s' % (tag, time.time(), msg), flush=True)


def _match(parser, r):
    kw = {'eth_dst': r['eth_dst']}
    if r['in_port'] is not None:
        kw['in_port'] = r['in_port']
    if r['eth_src'] is not None:
        kw['eth_src'] = r['eth_src']
    return parser.OFPMatch(**kw)


def _action(parser, ofp, act):
    if act[0] == 'out':
        return parser.OFPActionOutput(act[1])
    if act[0] == 'in':
        return parser.OFPActionOutput(ofp.OFPP_IN_PORT)
    return parser.OFPActionGroup(act[1])


def send_rule(dp, r):
    ofp, parser = dp.ofproto, dp.ofproto_parser
    inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [_action(parser, ofp, r['action'])])]
    dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=r['priority'], match=_match(parser, r),
                                  instructions=inst, buffer_id=ofp.OFP_NO_BUFFER))


def delete_rule(dp, r):
    ofp, parser = dp.ofproto, dp.ofproto_parser
    dp.send_msg(parser.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE_STRICT, priority=r['priority'],
                                  match=_match(parser, r), out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY))


def send_group(dp, g):
    ofp, parser = dp.ofproto, dp.ofproto_parser
    buckets = []
    for watch, act in g['buckets']:
        buckets.append(parser.OFPBucket(watch_port=ofp.OFPP_ANY if watch is None else watch,
                                        watch_group=ofp.OFPG_ANY, actions=[_action(parser, ofp, act)]))
    dp.send_msg(parser.OFPGroupMod(datapath=dp, command=ofp.OFPGC_ADD, type_=ofp.OFPGT_FF,
                                   group_id=g['gid'], buckets=buckets))


def barrier(dp):
    dp.send_msg(dp.ofproto_parser.OFPBarrierRequest(dp))
