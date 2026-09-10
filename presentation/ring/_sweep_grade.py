"""The stopping sweep, run on the graded circuit instead of the level one.

    python presentation/ring/_sweep_grade.py etcs_moving_block
    python presentation/ring/_sweep_grade.py virtual_coupling

Same flight, same fleet, same all-green criterion as _sweep_headway.py - the
only difference is the drawing underneath, infrastructure-grade.yaml. The
question it answers is whether the seven seconds virtual coupling wins on the
level survive a real gradient profile.

The rebind has to happen before _sweep_headway is imported: everything reads
_generate_timetable.INFRA at call time, so pointing it at the graded railway
first is enough, and is the same arrangement _sweep_express.py uses.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import _generate_timetable as ring     # noqa: E402

ring.use_infrastructure("infrastructure-grade.yaml")

import _sweep_headway as sweep         # noqa: E402 - after the rebind

if __name__ == "__main__":
    sweep.main(*sys.argv[1:2])
