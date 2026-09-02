"""Draw a stock type's acceleration and braking curves.

    python3 _plot_curves.py [curves.svg]

Not a model of the curves: every point is a real tick through
:func:`trainsim.core.dynamics.achievable_accel` and the same trapezoidal
integration :meth:`trainsim.core.train.Train.advance` uses, so what comes out
is what the stock does in a run. Level track, full power against full service
and emergency brake, no driver and no signalling - this is the envelope the
driver works inside, not a journey.

Four panels: acceleration against time and against distance, then braking
against each. Speed against distance is the one that matters for headway - it
says how much of a section a train spends getting up to line speed.

SVG comes out of trainsim.analysis.chart, which writes the markup directly:
the simulator has no plotting dependency and this is not worth acquiring one
for.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trainsim.analysis.chart import Chart, document
from trainsim.core import dynamics
from trainsim.core.train import RollingStock

S = RollingStock(id="EMU", name="Line unit", length_m=160.0,
                 max_speed_ms=120/3.6, max_accel=0.9,
                 service_brake=1.0, emergency_brake=1.5)

DT = 0.25

def run(v0, demand, stop_at_speed):
    """Tick the real chain: achievable_accel + trapezoidal advance."""
    t, x, v, a = 0.0, 0.0, v0, 0.0
    out = [(0.0, 0.0, v, 0.0)]
    while True:
        stopping = demand < 0 and v + demand*DT <= 1e-9
        a = dynamics.achievable_accel(S, v, demand, previous_accel=a,
                                      dt=DT, immediate=stopping)
        v1 = v + a*DT
        if v1 <= 0.0:
            if a < 0.0:
                ts = v / -a
                x += 0.5*v*ts
                t += ts
            v1 = 0.0
            out.append((t, x, 0.0, a))
            break
        v1 = min(v1, S.max_speed_ms)
        x += 0.5*(v+v1)*DT
        t += DT
        v = v1
        out.append((t, x, v, a))
        if demand > 0 and v >= stop_at_speed:
            break
        if t > 600:
            break
    return out

TOP = S.max_speed_ms - 1e-6
acc = run(0.0, S.max_accel, TOP)
svc = run(S.max_speed_ms, -S.service_brake, 0)
emg = run(S.max_speed_ms, -S.emergency_brake, 0)

# ------------------------------------------------------------------ svg

def kmh(points, xi):
    """(x, speed in km/h) from the tick records, x taken from column ``xi``."""
    return [(p[xi], p[2] * 3.6) for p in points]


def ends(points):
    return points[-1][0], points[-1][1]


ta, xa = ends(acc)
ts, xs_ = ends(svc)
te, xe = ends(emg)

power, service, emergency = "#1a6dcc", "#c0392b", "#e08b1a"

accel_t = Chart("Acceleration from rest", "time  s", "speed  km/h",
                note="0 to 120 km/h in %.0f s, %.0f m" % (ta, xa), y_max=130)
accel_t.line("power on", kmh(acc, 0), power)

accel_x = Chart("Acceleration from rest", "distance  m", "speed  km/h",
                note="base speed 48 km/h - traction falls as P/v above it",
                y_max=130)
accel_x.line("power on", kmh(acc, 1), power)

brake_t = Chart("Braking from 120 km/h", "time  s", "speed  km/h",
                note="service %.0f s / %.0f m,  emergency %.0f s / %.0f m"
                     % (ts, xs_, te, xe), y_max=130)
brake_t.line("service 1.0", kmh(svc, 0), service)
brake_t.line("emergency 1.5", kmh(emg, 0), emergency, dash=True)

brake_x = Chart("Braking from 120 km/h", "distance  m", "speed  km/h",
                note="first ~2 s is brake build-up, not full rate", y_max=130)
brake_x.line("service 1.0", kmh(svc, 1), service)
brake_x.line("emergency 1.5", kmh(emg, 1), emergency, dash=True)

out = sys.argv[1] if len(sys.argv) > 1 else "curves.svg"
with open(out, "w") as handle:
    handle.write(document(
        [accel_t, accel_x, brake_t, brake_x],
        heading="EMU  160 m  288 t  0.9 / 1.0 / 1.5 m/s2  120 km/h",
        subheading="Run through the simulator's own dynamics: traction curve, "
                   "Davis resistance, adhesion cap, jerk limit, trapezoidal "
                   "integration. Level track."))

print("accel   0->120 km/h : %5.1f s  %6.1f m" % (ta, xa))
print("service 120->0 km/h : %5.1f s  %6.1f m" % (ts, xs_))
print("emerg   120->0 km/h : %5.1f s  %6.1f m" % (te, xe))
for mark in (30, 60, 90, 110, 119):
    for t, x, v, a in acc:
        if v*3.6 >= mark:
            print("  reach %3d km/h : %5.1f s  %6.1f m" % (mark, t, x)); break
