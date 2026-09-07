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

## 2. The junction, measured without a platform in the way

`infrastructure-merge.yaml` puts the Sincan branch into Akyurt 1, which is a
station - so it measures the platform again, which is the one thing this
circuit was built to escape. Only half of it conflicts, too: joining crosses
the down line, leaving crosses nothing.

Stations sit at km 2.6, 5.1, 8.2, 11.0, 14.8, 17.3, 20.8, 23.6, 27.6, 30.7
and 33.4. The widest gap is 4.0 km, so there is nowhere on the running lines
to put a junction that is clear of a platform. The fix is the flight, not the
geometry: run the NON-STOP lap over it and nothing stops anywhere, so the
crossing is the only thing in the way wherever it sits. The control is already
measured - the ring's own express sweep, 39 s under moving block and 32 s
under virtual coupling, on the same railway with no junction at all.

Wants: `infrastructure-cross.yaml` - a second double-track railway crossing
the circuit at grade, sharing no track with it, so the diamond is the only
interaction in the model and every movement on both railways conflicts. The
in-file control is `grade_separated` on the junction, which turns it into a
flyover.

Measure movements per hour through the diamond before delay runs away, not
headway. Stated before the run, as this repository does: the ceiling should
barely move. A diamond's occupancy is train length plus crossing length over
speed, plus route setting and release, and no system here shortens any of
those. What virtual coupling can shorten is the approach - the next train is
nearer when the slot opens - and how fast a queue clears once it has built.

If the ceiling does not move, that is the finding, and it generalises the
study: virtual coupling shortens following distances, it does not shorten
occupancies, and this railway is limited by occupancies.
