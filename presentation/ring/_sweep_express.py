"""What does the circuit hold when nothing stops on it?

The same sweep as _sweep_headway.py, over the non-stop flight instead of the
stopping one:

    python scenarios/ring/_sweep_express.py                  3-aspect
    python scenarios/ring/_sweep_express.py etcs_l2
    python scenarios/ring/_sweep_express.py etcs_moving_block
    python scenarios/ring/_sweep_express.py virtual_coupling

The stopping sweep answers 78 s under moving block and 71 s under virtual
coupling - a 7 s spread, on a circuit where what the interval has to fit
through is a platform road. This asks the same question of the same railway
with the platforms out of the way, which is the only way to find out whether
that 7 s is what relative braking is worth or what the platform left it.

Import order is the whole of it. _generate_express rebinds LAP to the non-stop
lap and this rebinds flight_spec to the non-stop spec, both before
_sweep_headway is imported - so the sweep's own ``from _generate_timetable
import flight_spec`` picks up the express one and every function in it runs
unchanged on the express flight.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import _generate_express as express     # rebinds ring.LAP  (must come first)
import _generate_timetable as ring

ring.flight_spec = express.express_spec

import _sweep_headway as sweep          # noqa: E402 - after the rebinds

#: Tighter at the bottom than the stopping sweep. With no platform to queue for
#: the binding constraint is the following distance, and on a 70 km circuit at
#: 80 km/h that is a long way below anything the stopping flight reaches.
sweep.HEADWAYS = (300, 240, 180, 150, 120, 100, 85, 70, 60, 50, 42, 36, 30,
                  26, 22, 18, 15)
sweep.FLIGHT_DESCRIPTION = "none of them calling anywhere"

if __name__ == "__main__":
    sweep.main(sys.argv[1] if len(sys.argv) > 1 else "fixed_block_3aspect")
