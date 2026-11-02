#!/usr/bin/env python3
"""
SIMULATION of the recovery-time estimator (Eq. 4), not a measurement of any network.

For an ASSUMED true recovery time T, it writes ping-style logs (the same text format as `ping -D`) with the
probe interval delta, and runs the real analyse_trial() from analyze_log.py on them. The probe phase relative to the
cut is random. Model assumptions (stated in the paper):
  * a probe sent at or after cut+T is answered; a probe sent before the cut is answered only if it passed the failed
    link before the cut (it needs W = 4 ms to get there: two links of 2 ms);
  * RTT 16 ms before the failure, RTT_AFTER after it.
Output: results_estimator.json  (T is an input here, so nothing in it is a recovery time of M1/M2/M3).
"""
import json, os, random, statistics as st, tempfile
from analyze_log import analyse_trial

W = 0.004
RTT = 0.016
CUT = 1000.0

def make_logs(d, delta, T, phase, rtt_after=0.016):
    ping, meta = os.path.join(d, 'ping.log'), os.path.join(d, 'meta.txt')
    with open(meta, 'w') as f:
        f.write('link_cut=%r\ninterval=%r\n' % (CUT, delta))
    seq = 0
    with open(ping, 'w') as f:
        k0 = int(-0.5 / delta)
        s = CUT - 0.5 + phase        # probes from 0.5 s before the cut to 0.5 s after it
        t = s
        while t < CUT + 0.5:
            seq += 1
            ok = (t >= CUT + T) or (t + W < CUT)
            if ok:
                rtt = rtt_after if t >= CUT else RTT
                f.write('[%.6f] 64 bytes from 10.0.0.2: icmp_seq=%d ttl=64 time=%.3f ms\n' % (t + rtt, seq, rtt * 1000))
            t += delta
    return ping, meta

def run(delta, T, n=400, seed=7):
    rnd = random.Random(seed)
    R, L = [], []
    with tempfile.TemporaryDirectory() as d:
        for _ in range(n):
            ping, meta = make_logs(d, delta, T, rnd.uniform(0, delta))
            r = analyse_trial(ping, meta)
            R.append(r['recovery_ms']); L.append(r['probes_lost'])
    R = [x for x in R if x is not None]
    R.sort()
    return dict(delta_ms=delta * 1000, T_assumed_ms=T * 1000, n=len(R), R_mean=round(st.mean(R), 2), R_sd=round(st.stdev(R), 2),
                R_min=round(R[0], 2), R_max=round(R[-1], 2), bias_mean=round(st.mean(R) - T * 1000, 2),
                lost_mean=round(st.mean(L), 2), lost_min=min(L), lost_max=max(L))

if __name__ == '__main__':
    out = []
    for delta in (0.2, 0.01):
        for T in (0.003, 0.010, 0.020, 0.050):
            out.append(run(delta, T))
            print(out[-1])
    json.dump(out, open('results_estimator.json', 'w'), indent=1)
