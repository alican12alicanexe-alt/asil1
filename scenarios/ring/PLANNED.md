# Not built yet

Two experiments the circuit should carry, and the conventions they follow.
Written down because the measurements behind them exist only in a chat log,
and a number nobody can re-run is not a measurement.

## Convention

One experiment, one `infrastructure-*.yaml` here. `infrastructure-merge.yaml`
set the precedent: the branch lives on its own drawing so the other scenarios
do not carry 41 routes they never book. Anything a test names gets the same
treatment - a drawing small enough to load fast and read in one sitting.

## 1. The convoy, assembled by a slower leader

Nothing on this railway makes trains close up, so no convoy ever forms
(`scenarios/capacity2` measured zero ticks inside 200 m over a 30 km leg).
A convoy needs a speed difference, and a speed difference needs two classes
of train - not a manoeuvre, and not the leader being held back.

Probed on the non-stop lap, two services 120 s apart, leader capped at
65 km/h on an 80 km/h line, follower uncapped. The convoy forms at km 18 and
holds to the end of the lap:

                          settled gap, km 20-65   closest   ticks < 200 m
    fixed block 3-aspect          1211 m            764 m         0
    ETCS hybrid L3 (VSS)           475 m            330 m         0
    ETCS moving block              301 m            247 m         0
    virtual coupling               163 m            136 m      2689

Virtual coupling holds the convoy 138 m tighter than moving block - 46 %
closer, against 9 % on the headway sweep. Not a contradiction: in a convoy
the leader is moving, so the brake credit relative braking rests on is fully
available. At a platform the leader is stopping and has none left to lend.

Wants: `infrastructure-*.yaml` unchanged from the ring, a two-class timetable,
and the gap trace above turned into a script beside `_sweep_timestep.py`.

## 2. The junction - BUILT, see `scenario-cross.yaml`

Done. `infrastructure-cross.yaml`, `_generate_cross.py`, `_sweep_cross.py`
and `tests/test_cross.py`. Virtual coupling is checked 28 % less at a flat
crossing and arrives exactly as late - 475 s against 475 s. The numbers and
the reasoning are in `scenario-cross.yaml`'s header.
