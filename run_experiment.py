#!/usr/bin/env python3
"""
Team T3 -- automated failover experiment (v2).

Changes from v1:
  * --interval (default 0.01 s = 10 ms). Mininet hosts run as root, so ping
    may probe faster than the 0.2 s limit for normal users. Finer probing means
    a shorter outage can actually be seen.
  * The meta file now also records the probe interval and the run end time,
    so analyze_log.py can check whether ANY replies came back after the cut
    (v1 could not tell "recovered with no loss" from "never recovered").
  * Prints a quick verdict at the end of every run.

Usage (inside the VM, controller already running in the other terminal):
    sudo python3 run_experiment.py --label m1
    sudo python3 run_experiment.py --label m2
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mininet.log import setLogLevel, info
from topo import build_net


def quick_verdict(logfile, t_cut):
    after = 0
    total = 0
    try:
        with open(logfile) as f:
            for line in f:
                if 'bytes from' in line and line.startswith('['):
                    total += 1
                    ts = float(line[1:line.index(']')])
                    if ts > t_cut:
                        after += 1
    except OSError:
        pass
    return total, after


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--label', required=True, choices=['m1', 'm2'])
    ap.add_argument('--controller-port', type=int, default=6633)
    ap.add_argument('--interval', type=float, default=0.01, help='ping probe interval in seconds')
    ap.add_argument('--fail-at', type=float, default=8.0)
    ap.add_argument('--after', type=float, default=12.0)
    ap.add_argument('--outdir', default='logs')
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    ts = time.strftime('%Y%m%d-%H%M%S')
    logfile = os.path.join(args.outdir, f'ping_{args.label}_{ts}.log')
    metafile = os.path.join(args.outdir, f'meta_{args.label}_{ts}.txt')

    setLogLevel('info')
    net = build_net(controller_port=args.controller_port)
    net.start()
    for sw in ('s1', 's2', 's3', 's4'):
        net.get(sw).cmd(f'ovs-vsctl set bridge {sw} protocols=OpenFlow13')

    h1, h2 = net.get('h1'), net.get('h2')
    h1.setARP(h2.IP(), h2.MAC())
    h2.setARP(h1.IP(), h1.MAC())

    info('*** waiting 3s for the controller to push its initial flows/groups\n')
    time.sleep(3)
    loss = net.pingAll()
    info(f'*** pingAll loss = {loss}%\n')

    ping_cmd = f'ping -D -i {args.interval} {h2.IP()} > {os.path.abspath(logfile)} 2>&1'
    ping_proc = h1.popen(['bash', '-c', ping_cmd])
    t_start = time.time()
    info(f'*** ping every {args.interval}s started; cutting s1<->s2 in {args.fail_at}s\n')
    time.sleep(args.fail_at)

    t_cut = time.time()
    info(f'*** CUTTING LINK s1<->s2 at t={t_cut:.6f}\n')
    net.configLinkStatus('s1', 's2', 'down')
    time.sleep(args.after)
    t_end = time.time()

    ping_proc.terminate()
    time.sleep(0.5)

    with open(metafile, 'w') as f:
        f.write(f'label={args.label}\n')
        f.write(f'ping_start={t_start}\n')
        f.write(f'link_cut={t_cut}\n')
        f.write(f'run_end={t_end}\n')
        f.write(f'interval={args.interval}\n')
        f.write(f'pingall_loss_percent={loss}\n')
        f.write(f'logfile={os.path.abspath(logfile)}\n')

    total, after = quick_verdict(logfile, t_cut)
    info(f'*** replies received: {total} in total, {after} after the cut\n')
    if after == 0:
        info('*** WARNING: NO replies after the link cut -> traffic did NOT recover in this run\n')
    else:
        info('*** OK: traffic came back after the cut\n')
    info(f'*** ping log: {logfile}\n*** meta: {metafile}\n')
    net.stop()


if __name__ == '__main__':
    if os.geteuid() != 0:
        sys.exit('run_experiment.py needs root (Mininet requires it) -- run with sudo.')
    main()
