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

### 1a. The convoy by operating rule - BUILT, see `scenario-convoy.yaml`

The other way to manufacture the speed difference: cap every train at 70 and
release it to line speed once it is close enough to the one in front. Built as
`VirtualCoupling(uncoupled_speed_kmh=..., coupling_margin_m=...)`, measured by
`_sweep_convoy.py`, recorded in that script's docstring.

It works, in a band, and the trade is bad - convoys at 192 m against plain
virtual coupling's 1053 m, for 5 % of every journey on the railway. Below a
600 m radius it never fires; above 1500 m it is "no cap" with extra steps. The
slow-leader route in section 1 remains the one worth building.

The flight has its own generator, `_generate_convoy.py`, and needs one: it is
booked at 70 km/h rather than line speed, because a service alone on the
railway never closes up on anything and 70 is its unimpeded speed, and it is
written on stock fitted with a train-to-train link. Until that existed the
scenario used the express timetable and ran as fixed block with a virtual
coupling label - worst arrival +11:43, no convoy possible. Fixed, it keeps
time 12 of 12 and the trains arrive in pairs 17 s apart.

`--stopping` writes the same flight on the twenty-two call lap
(`scenario-convoy-stopping.yaml`), and that one is the sharper result: a
station stop hands the incentive a free speed difference and the convoys still
do not form - 12 services at 60 s arrive 59 to 64 s apart, no pairs at all.
What the follower closes up to is a platform that is not free yet.

## 2. The junction - BUILT AND REMOVED

`infrastructure-cross.yaml` put two railways across each other at grade with
nothing shared, ran clean against a flyover control, and answered: virtual
coupling was checked 7 % less at the diamond and arrived EXACTLY as late,
410 s against 410 s. A true result, and a null one, so it was dropped rather
than kept as a section nobody wants to present. Recovered from git history
if the negative result is ever worth showing:

    git show 07ec16f:scenarios/ring/infrastructure-cross.yaml

The reason it came out null is worth keeping even though the files are gone:
a diamond is held for as long as a train is ON it - length plus block, over
speed - and no system on this ladder shortens any of the three. Any junction
experiment built next will return the same null for the same reason, unless
it is built so that what binds is the APPROACH to the junction rather than
the crossing itself.
