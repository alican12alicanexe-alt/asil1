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

SVG is written by hand rather than through a plotting library because the
simulator has no plotting dependency and this is not worth acquiring one for.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trainsim.core.train import RollingStock
from trainsim.core import dynamics

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
W, H = 1180, 760
PW, PH = 470, 250
def panel(ox, oy, series, xi, title, xlabel, note):
    """series: list of (label, points, colour, dash)"""
    xs = max(max(p[xi] for p in pts) for _, pts, _, _ in series)
    ys = max(max(p[2] for p in pts) for _, pts, _, _ in series)*3.6
    xs = xs*1.02 or 1.0
    ys = 130.0
    def px(v): return ox + v/xs*PW
    def py(v): return oy + PH - v/ys*PH
    o = ['<text x="%d" y="%d" class="ti">%s</text>' % (ox, oy-24, title)]
    o.append('<text x="%d" y="%d" class="no">%s</text>' % (ox, oy-8, note))
    # grid
    steps = 5
    for i in range(steps+1):
        gx = ox + i*PW/steps
        o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" class="g"/>'
                 % (gx, oy, gx, oy+PH))
        o.append('<text x="%.1f" y="%d" class="ax" text-anchor="middle">%s</text>'
                 % (gx, oy+PH+16, ("%.0f" % (i*xs/steps))))
    for sp in range(0, 131, 20):
        gy = py(sp)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="g"/>'
                 % (ox, gy, ox+PW, gy))
        o.append('<text x="%d" y="%.1f" class="ax" text-anchor="end">%d</text>'
                 % (ox-6, gy+4, sp))
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="ln"/>' % (ox, oy, ox, oy+PH))
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="ln"/>'
             % (ox, oy+PH, ox+PW, oy+PH))
    o.append('<text x="%.0f" y="%d" class="ax" text-anchor="middle">%s</text>'
             % (ox+PW/2, oy+PH+36, xlabel))
    o.append('<text x="%d" y="%.0f" class="ax" text-anchor="middle" '
             'transform="rotate(-90 %d %.0f)">speed  km/h</text>'
             % (ox-40, oy+PH/2, ox-40, oy+PH/2))
    ly = oy + 14
    for label, pts, col, dash in series:
        d = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", px(p[xi]), py(p[2]*3.6))
                     for i, p in enumerate(pts))
        o.append('<path d="%s" fill="none" stroke="%s" stroke-width="2.2" %s/>'
                 % (d, col, 'stroke-dasharray="6 4"' if dash else ''))
        o.append('<text x="%d" y="%d" class="lg" fill="%s">%s</text>'
                 % (ox+PW-8, ly, col, label))
        ly += 16
    return "\n".join(o)

def fmt(pts):
    return pts[-1][0], pts[-1][1]

svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
       'viewBox="0 0 %d %d">' % (W, H, W, H),
       '<style>text{font-family:ui-sans-serif,system-ui,sans-serif}'
       '.ti{font-size:15px;font-weight:600;fill:#111}'
       '.no{font-size:11px;fill:#666}.ax{font-size:11px;fill:#555}'
       '.lg{font-size:11px;text-anchor:end}'
       '.g{stroke:#e6e6e6;stroke-width:1}.ln{stroke:#999;stroke-width:1}'
       '.h{font-size:19px;font-weight:700;fill:#111}'
       '.s{font-size:12px;fill:#444}</style>',
       '<rect width="100%" height="100%" fill="#fff"/>']
svg.append('<text x="70" y="34" class="h">EMU  160 m  288 t  0.9 / 1.0 / 1.5 m/s2  120 km/h</text>')
svg.append('<text x="70" y="54" class="s">Run through the simulator\'s own dynamics: '
           'traction curve, Davis resistance, adhesion cap, jerk limit, trapezoidal integration. Level track.</text>')

ta, xa = fmt(acc)
ts, xs_ = fmt(svc)
te, xe = fmt(emg)
svg.append(panel(120, 130, [("power on", acc, "#1a6dcc", 0)], 0,
                 "Acceleration from rest", "time  s",
                 "0 to 120 km/h in %.0f s, %.0f m" % (ta, xa)))
svg.append(panel(690, 130, [("power on", acc, "#1a6dcc", 0)], 1,
                 "Acceleration from rest", "distance  m",
                 "base speed 48 km/h - traction falls as P/v above it"))
svg.append(panel(120, 500, [("service 1.0", svc, "#c0392b", 0),
                            ("emergency 1.5", emg, "#e08b1a", 1)], 0,
                 "Braking from 120 km/h", "time  s",
                 "service %.0f s / %.0f m,  emergency %.0f s / %.0f m"
                 % (ts, xs_, te, xe)))
svg.append(panel(690, 500, [("service 1.0", svc, "#c0392b", 0),
                            ("emergency 1.5", emg, "#e08b1a", 1)], 1,
                 "Braking from 120 km/h", "distance  m",
                 "first ~2 s is brake build-up, not full rate"))
svg.append('</svg>')
out = sys.argv[1] if len(sys.argv) > 1 else "curves.svg"
open(out, "w").write("\n".join(svg))

print("accel   0->120 km/h : %5.1f s  %6.1f m" % (ta, xa))
print("service 120->0 km/h : %5.1f s  %6.1f m" % (ts, xs_))
print("emerg   120->0 km/h : %5.1f s  %6.1f m" % (te, xe))
for mark in (30, 60, 90, 110, 119):
    for t, x, v, a in acc:
        if v*3.6 >= mark:
            print("  reach %3d km/h : %5.1f s  %6.1f m" % (mark, t, x)); break
