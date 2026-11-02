#!/usr/bin/env python3
"""
Automated failover run on a multi-switch topology (same procedure as run_experiment.py).
It picks the two hosts that are farthest apart, looks at the path that the chosen mechanism uses before
the failure and cuts the FIRST switch-to-switch link of that path.

    sudo python3 run_multi.py --topo ladder8 --label m1      (controller m1_controller_multi.py running)
    sudo python3 run_multi.py --topo ladder8 --label m2      (T3_CRANKBACK=0 for the controller)
    sudo python3 run_multi.py --topo ladder8 --label m2c     (T3_CRANKBACK=1 for the controller)
    sudo python3 run_multi.py --topo ladder8 --label m3
Logs go to logs_<topo>/ ; analyse with  python3 analyze_log.py --logs-dir logs_<topo>
"""
import argparse
import os
import sys
import time

from mininet.log import setLogLevel, info

from sdn_core import plan_m1, plan_m2, plan_m3, DataPlane, shortest_path
from topo_multi import build_net


def baseline_path(topo, label, a, b):
    if label == 'm1':
        r, g = plan_m1(topo)
    elif label in ('m2', 'm2c'):
        r, g = plan_m2(topo, label == 'm2c')      # m2 = plain local fast-failover, m2c = with crankback
    else:
        r, _ = plan_m3(topo)
        g = []
    return DataPlane(topo, r, g).send(a, b)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--topo', required=True)
    ap.add_argument('--label', required=True, choices=['m1', 'm2', 'm2c', 'm3'])
    ap.add_argument('--controller-port', type=int, default=6633)
    ap.add_argument('--interval', type=float, default=0.01)
    ap.add_argument('--fail-at', type=float, default=8.0)
    ap.add_argument('--after', type=float, default=12.0)
    args = ap.parse_args()
    outdir = 'logs_' + args.topo
    os.makedirs(outdir, exist_ok=True)
    ts = time.strftime('%Y%m%d-%H%M%S')
    logfile = os.path.join(outdir, 'ping_%s_%s.log' % (args.label, ts))
    metafile = os.path.join(outdir, 'meta_%s_%s.txt' % (args.label, ts))

    setLogLevel('info')
    net, topo = build_net(args.topo, args.controller_port)
    # farthest pair of hosts (by hop count), ties -> first in name order
    names = sorted(topo.hosts)
    best = None
    for x in names:
        for y in names:
            if x < y and topo.hosts[x][1] != topo.hosts[y][1]:
                p, _ = shortest_path(topo.adj, topo.hosts[x][1], topo.hosts[y][1])
                if best is None or len(p) > best[0]:
                    best = (len(p), x, y)
    _, a, b = best
    path = baseline_path(topo, args.label, a, b)
    u, v = path[0], path[1]
    info('*** probing %s -> %s along switches %s; will cut s%d-s%d\n' % (a, b, path, u, v))
    net.start()
    time.sleep(3)
    ha, hb = net.get(a), net.get(b)
    for h in (ha, hb):
        for o in (ha, hb):
            if h is not o:
                h.setARP(o.IP(), o.MAC())
    loss = net.ping([ha, hb])
    info('*** warm-up ping loss = %s%%\n' % loss)

    cmd = 'ping -D -i %s %s > %s 2>&1' % (args.interval, hb.IP(), os.path.abspath(logfile))
    proc = ha.popen(['bash', '-c', cmd])
    t_start = time.time()
    time.sleep(args.fail_at)
    t_cut = time.time()
    info('*** CUTTING LINK s%d<->s%d at t=%.6f\n' % (u, v, t_cut))
    net.configLinkStatus('s%d' % u, 's%d' % v, 'down')
    time.sleep(args.after)
    t_end = time.time()
    proc.terminate()
    time.sleep(0.5)
    with open(metafile, 'w') as f:
        f.write('label=%s\nping_start=%s\nlink_cut=%s\nrun_end=%s\ninterval=%s\npingall_loss_percent=%s\nlogfile=%s\ntopo=%s\ncut=s%d-s%d\n' % (
            args.label, t_start, t_cut, t_end, args.interval, loss, os.path.abspath(logfile), args.topo, u, v))
    after = total = 0
    with open(logfile) as f:
        for line in f:
            if 'bytes from' in line and line.startswith('['):
                total += 1
                after += float(line[1:line.index(']')]) > t_cut
    info('*** replies: %d total, %d after the cut -> %s\n' % (total, after, 'OK' if after else 'WARNING: NOT recovered'))
    net.stop()


if __name__ == '__main__':
    if os.geteuid() != 0:
        sys.exit('needs root: run with sudo')
    main()
