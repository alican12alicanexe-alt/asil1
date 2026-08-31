# TrainSim
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^INCREASE PLATFORM LENGTH^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
A schematic-level, microscopic railway simulator in Python — a testbed for
railway systems questions rather than a game. It exists to answer things like
*how many trains per hour will this line carry*, *what would ERTMS/ETCS change*,
and *can a smarter dispatcher recover this timetable*.

Deliberately **dependency-free**: the simulator and its schematic view run on a
bare Python install with nothing to `pip install`, so it works on a locked-down
machine.

```
python run.py scenarios/corridor3              # live schematic
python run.py scenarios/corridor3 --headless   # no window, prints a summary
python run.py scenarios/corridor3 --check      # validate and report on the layout
python run.py scenarios/corridor3 --compare    # every ETCS level, side by side
python run.py scenarios/corridor3 --system etcs_moving_block   # watch one
python run.py scenarios/metro --compare        # the other line, opposite answer
python run.py scenarios/metro/scenario-disrupted.yaml --propagation
python run.py scenarios/junction --check       # a real junction's route table
python run_tests.py                            # 217 tests, stdlib unittest
```

Requires Python 3.7+. `requirements-optional.txt` lists things that make it
nicer, none of which are needed. **[COMMANDS.md](COMMANDS.md)** is the full
command reference: every mode, every option, every scenario, and how to read the
output.

---

## What Milestone 1 does

A 30 km double-track corridor — **Alpha** (km 0), **Beta** (km 12), **Gamma**
(km 30) — under conventional three-aspect fixed-block signalling, with nine
services over 75 simulated minutes.

The scenario is built around one operational idea: a 140 km/h fast follows a
120 km/h stopper two minutes behind. Under fixed block it gets repeatedly
**checked down by yellow signals** — braking to about 60 km/h and
re-accelerating each time the signal clears — until the stopper takes the **loop
road at Beta**, at which point the fast gets a green and **overtakes** it.
That concertina is the characteristic capacity cost of mixed-speed traffic, and
it is exactly what the later ERTMS levels are meant to reduce.

Watch it: run the view, press `z` a few times over Beta around 07:07.

### Controls

| key | action |
|---|---|
| `space` | pause / resume |
| `b` | braking envelopes and authority markers on / off |
| `.` | single step while paused |
| `+` / `-` | faster / slower |
| `←` / `→` | pan |
| `z` / `x` | zoom in / out |
| `0` | reset the view |
| `q`, `Esc` | quit |

In the view: signal lamps show the live aspect, occupied blocks tint red, trains
are blue on the up line and orange on the down, purple while dwelling. The table
underneath says what is governing each train — `line speed`, `obeying caution`,
`signal at danger`, `station stop BETA`.

**The view follows the signalling system.** Run `--system etcs_moving_block` and
the lamps disappear — Level 2 and above put the authority in the cab and leave
only unlit marker boards on the ground, so drawing green lamps would be a picture
of a railway that does not exist. Blocks stop tinting too: under distance
separation a block is not the unit of safety. What you get instead is the moving
block itself — a hatched **braking envelope** travelling with each train, the
distance it needs to stop, shrinking as it slows, with a cyan tick where its
authority runs out.

Those envelopes are drawn under *every* system, and that is the clearest single
picture in the project: under fixed block each train's envelope sits inside a lit
block several times longer than it. The difference is the space fixed block
throws away.

---

## How it is put together

```
run.py                       launcher (no install needed)
run_tests.py                 test runner (no pytest needed)
scenarios/depotline/         a single line between two depots: 60 km, three
                             stations, and every road used in turn
scenarios/twoway/            the same railway with a line each way, and the
                             crossovers that let a train work either one
trainsim/
  core/
    units.py                 SI conversions and the braking-curve formulae
    network.py               nodes, segments, platforms, stations, path finding
    signals.py               block sections, occupancy, three-aspect logic
    train.py                 rolling stock, paths, train state, kinematics
    driver.py                braking curve -> acceleration
    timetable.py             services (the plan) vs trains (the execution)
    points.py                switches, derived from the topology
    routes.py                the route table: what movements exist
    interlocking.py          may this movement be made?  <- the safety layer
    vss.py                   virtual sub-sections, for Hybrid Level 3
    dispatcher.py            train lifecycle + route requests; the seat for a TMS
    disruption.py            declared perturbation, and the speed-limit seam
    simulation.py            the fixed-timestep kernel
    signalling/
      base.py                SignallingSystem + MovementAuthority  <- the seam
      common.py              where is the first point this train may not pass?
      fixed_block.py         conventional three-aspect
      etcs.py                ETCS L1, L2 and full moving block
      hybrid_l3.py           Hybrid Level 3 over virtual sub-sections
      virtual_coupling.py    relative braking distance over a V2V link
  analysis/
    kpi.py                   run metrics and the side-by-side comparison
    propagation.py           primary vs knock-on delay, by difference
  scenario/
    builder.py               expands a compact line description into a railway
    loader.py                reads YAML/JSON, assembles a Simulation
    checks.py                signal spacing, and whether the plan is workable
    schema.py                what keys a scenario file may contain
    minyaml.py               YAML-subset parser, so no PyYAML is needed
  viz/
    layout.py                schematic coordinates -> pixels
    schematic_tk.py          the live view (tkinter)
```

### The kernel

Fixed timestep, 1 simulated second per tick, deterministic. Each tick:

1. **dispatch** — introduce services, run dwells, terminate arrivals
2. **sense** — each running train observes the signalling and gets a movement
   authority, all against the *same* occupancy snapshot, so the result never
   depends on dictionary ordering
3. **decide and move** — the driver turns the authority into an acceleration
4. **update** — rebuild occupancy and aspects, then assert that no block holds
   two trains

### The physics

A train is a body with mass, pushed by a traction system that fades, dragged
back by the air and pulled at by gravity. `core/dynamics.py` is that force
balance:

    m_eff · a  =  F_traction(v)  −  R(v)  −  m · g · sin θ

**Traction is flat, then falling.** Below *base speed* the motors are current
limited and produce constant tractive effort; above it they are power limited,
so effort falls as `P / v`. This is the term that matters most. A 200 m EMU used
to reach 140 km/h in 43 seconds and 840 metres — roughly twice as good as any
real one. It now takes 66 seconds and 1.5 km, because the last 20 km/h cost
about as much distance as the first 80. Every run time and every headway
downstream of that was optimistic before, and the timetables have been rebooked
on the new figures.

**Resistance is the Davis equation**, `R = A + Bv + Cv²`: rolling and journal
resistance that barely varies, a flange term linear in speed, and aerodynamic
drag that dominates above about 100 km/h. `A` and `B` scale with mass, `C` with
length, and the default coefficients put a 200 m EMU at ~35 N per tonne at
140 km/h, which is where measured stock of that kind sits. It is what makes a
coasting train slow down and why the last few km/h take so long to gain.

**Gradient is `g · sin θ`**, near enough `g · ‰ / 1000`. Ten per thousand is
0.098 m/s², a ninth of an EMU's starting acceleration and three times its air
drag at line speed — after the brake, gravity is the largest force acting on a
train, which is why a run-time calculation asks for a gradient profile first.

Two more limits sit on the brake rather than in the force balance. **Adhesion**
caps any retardation at `μ · g` — 2.9 m/s² on dry rail, well above any service
rate here, so it only bites if a scenario asks for a brake nobody could deliver.
**Build-up** is the second or two the retardation takes to come in; the driver
allows for it by starting to brake earlier, exactly as an ERTMS braking curve
does, and it lengthens the moving-block envelope by 39 m at 140 km/h.

The split between the driver and the train is the point. The driver asks for an
acceleration — it is closing a loop on speed and does not know which forces get
it there. The train answers with what it can deliver. So the driver model did not
have to learn about any of this, and neither did the signalling.

**Gradients on the railway.** A track may be laid on a gradient, per stretch:

```yaml
tracks:
  - id: UP
    serves: [ALPHA, BETA, GAMMA]
    gradients:
      - {from: ALPHA, to: BETA,  grade_permille: 10}   # 1 in 100 up to the ridge
      - {from: BETA,  to: GAMMA, grade_permille: -5}
```

Rise per thousand, in the direction the entry is written; the down line reads the
same entries negated, because a bank that climbs one way falls the other. What
follows from it is not symmetrical, and that is the interesting part. Working up
a bank costs real time, because the train has that much less acceleration to
spare. Running down one buys none of it back: line speed is line speed, so the
surplus has nowhere to go — and it is spent again on a longer braking distance
into the next stop. A 20 per thousand fall lengthens the signal spacing a
three-aspect layout needs from 1222 m to 1600 m, and `--check` says so.

Nothing shipped is on a gradient yet: every scenario here is level, so every
number in this file is comparable with the one before it. The rolling stock keys
are the same story — `mass_t`, `power_kw`, the Davis coefficients, `adhesion`
and `brake_buildup_s` are all optional, and what a timetable does not say is
derived from the length, speed and acceleration it already declared.

### The seam that matters

Every train control system is an implementation of one interface:

```python
class SignallingSystem:
    def observe(self, train, sim): ...           # what the driver learns, and when
    def movement_authority(self, train, sim) -> MovementAuthority: ...
```

`MovementAuthority` is just *how far may this train go, and how fast*. The
kernel, the driver and the trains know nothing else about signalling. ETCS L1/L2,
Hybrid Level 3 and moving block are therefore additions here rather than
rewrites — and the headway differences between them fall out of the braking
physics instead of being tuned constants.

Conventional signalling models the discreteness explicitly: a driver only learns
the state of the railway when a signal is sighted or passed, so braking for an
occupied block begins at the yellow signal one block back rather than where
braking would actually need to start. That is precisely the time ETCS L2 gets
back.

### The interlocking

Milestone 2. Everything that wants a train to move asks the same question - *may
this movement be made?* - and one component answers it:

```
dispatcher/TMS  ->  route request  ->  INTERLOCKING  ->  route locked
                                              |
                          signal or RBC  <----+  ->  MovementAuthority  ->  driver
```

It grants a route only when the route exists in the table, no other route holds
its block, the block is clear, and every point it needs is free or already lying
the right way. Then it throws and locks the points, locks the route, and lets the
signal clear. Refusals come back with the reason a signaller would be given:
`PT_UP_11250_F locked to BETA_3 by R_BETA_3, set for S1`.

**It is a separate component from the signalling system, on purpose.** The
interlocking logic is identical under conventional signals, ETCS L1, L2 and L3;
what differs is only how the resulting authority reaches the driver. Putting it
inside `SignallingSystem` would mean reimplementing it four times.

**Points and routes are derived, not declared.** Nothing in the scenario file
mentions either. Two segments leaving a node is a facing point; two arriving is a
trailing point; the route table is generated from there. A route is *controlled*
if it needs points - otherwise it is plain automatic block and its signal simply
follows occupancy. depotline has 10 points and 57 routes, 24 of them
controlled.

**Sectional release is what makes the railway work.** Each point is given back the
moment the train's rear is past it, not when the whole movement finishes:

```
07:04:22  points          S1   PT_UP_11250_F to BETA_3
07:04:22  route_set       S1   R_BETA_3 (into BETA_3, PT_UP_11250_F to BETA_3)
07:05:26  points_released S1   PT_UP_11250_F      <- S1 is still standing in the loop
07:06:07  points          F1   PT_UP_11250_F to BETA_1
07:06:07  route_set       F1   R_BETA_1
07:07:05  route_set       F1   R_UP_007_from_BETA_1 (PT_UP_12750_T to BETA_1)
07:10:00  route_set       S1   R_UP_007_from_BETA_3 (60 s before its booked departure)
```

Hold the points until the whole route clears and a train dwelling in the loop
blocks the road behind it - the overtake the loop exists for becomes impossible.
A test asserts the release happens *while* S1 is still in the loop, for exactly
that reason.

Two design details that turned out to matter, both found by the simulation
failing:

- **A route must not reach past its exit signal.** The route into the loop holds
  only the points at the near end; the route *out* is a separate request made
  when the train departs. Fold them together and the standing train keeps the far
  points for its whole dwell.
- **A signal reads the signal ahead, not the block ahead.** A controlled signal
  protecting a clear block still stands at danger when no route is set, and the
  signal behind has to warn about that exactly as it would about an occupied
  block. Computing aspects from occupancy alone put a green immediately before a
  red, with no braking distance in between.

Set `interlocking: {enabled: false}` to run without it, as idealised automatic
block: every signal then follows occupancy, and nothing is ever waited on.

### A signal is red until somebody asks

The chain is always the same: **the interlocking sets the route, the route clears
the signal, the signal gives the movement authority.** Nothing skips a link -
ETCS Level 2 has no lineside signals at all and still stops in the same place,
because `route_limit` caps every authority at the first signal ahead with no
route locked. A radio authority is still bounded by the routes that exist — what
changes under distance separation is which routes the interlocking will set, not
whether the authority obeys them.

What differs between railways is only *which* signals need a route:

| `automatic_signals` | plain-line signals | an empty railway looks like |
|---|---|---|
| `true` - automatic block | work themselves off track occupancy | green everywhere, red only at the platforms |
| `false` - worked by route | need a route like any other | **all red**, greens only ahead of a train |

depotline is `false`: 57 of 57 signals wait on the interlocking. The whole line
in chainage order, `.` red, `y` yellow, `G` green:

```
start, empty railway   .........................................................
t=1200 s               ....Gy.Gy.y...Gy.Gy..Gy..Gy..............................
end, all trains gone   .........................................................
```

The greens are a two-signal window travelling ahead of each train, and that is
the whole display: nothing is lit that nobody has asked for.

**Two signals ahead is a requirement, not a tuning choice.** A three-aspect
signal shows green only when the signal beyond it is off, and that one is off
only if a route has been set through it too. `route_lookahead: 1` on a route-set
railway means every driver runs on yellows - 255 s onto a 42-minute journey.
Above two, nothing improves.

**It costs 45 seconds of headway**, and that is the real price of the picture
above:

| Marlowe-Ashdown blocks | automatic block | worked entirely by route |
|---|---|---|
| 1800 m (shipped) | 165 s, 21.8 tph | 210 s, 17.1 tph |
| 1200 m | 150 s, 24.0 tph | 195 s, 18.5 tph |

Both rows measured on the road-1-only flight this line ran until the roads were
used in turn, and not re-run since; the 45 s is a property of the reservation,
not of which platform a train is booked into. Flat either way, so it is not
interacting with block length - it is the reservation itself. A route holds its block from the moment it is set, two
signals ahead of the train, until the train has cleared it; an automatic signal
holds a section only while a train is standing in it. Two blocks of extra
reservation depth, and the follower pays for them.

It is asserted rather than believed. `Simulation.clear_without_a_route()` runs
every tick and records a violation for any signal showing a proceed aspect that
had no route set; take the route check out of `_must_stand_at_danger` and a
ten-minute depotline run reports 13462 of them.

The same principle decides the defaults. `sim.aspects.get(signal_id, RED)`, not
`GREEN`: a signal the railway has said nothing about is a signal that has not
cleared, and the lamp on the schematic is drawn red before the first refresh for
the same reason. Absence of information is danger, never permission.

### Which road: the second head

An aspect says how far a train may go. It does not say **which way**, and until
now the schematic could not either: three roads at Marlowe, one green lamp, and
no way to tell from the picture which of them the interlocking had set.

So a signal with a choice of road ahead gets a **second head** on the same post,
further out from the rail. The **inner** head is the line ahead; the **outer**
head is everything that diverges from it. Which head is lit says which road; the
aspect on it says how far.

```
     ○   outer: dark                 ●   outer: green
     ●   inner: green                ○   inner: red
   ─────────────────────           ─────────────────────
   carrying on along the line      taking the road off it
```

One rule decides both heads: **the head for the road that is set carries the
aspect, and the other head is dark.** Everything else follows.

| state | inner | outer | |
|---|---|---|---|
| nothing set | red | dark | stopped, and no road decided yet |
| line ahead set | green / yellow | dark | carry on |
| diverging road set | **red** | green / yellow | you are leaving the line |
| diverging road set, not yet clear | **red** | **red** | that way, but not yet |

The inner head *has* to be red in the third row. The route it stands for is not
set, and a proceed aspect for a route nobody set is precisely what
`clear_without_a_route()` exists to catch.

The fourth row is not special-cased — it falls out of the rule, and it is worth
having. "You are going that way, and you are not going yet" is a different
picture from "you are stopped and nobody has decided", and until now they looked
identical. Measured on `twoway`: 4314 ticks of both-red against 166174 of
inner-red-outer-dark.

**A dark head is not a red one.** Two reds on a post leave a driver working out
which of them applies to them, and on a schematic they are indistinguishable
from a signal that has failed. Dark says "not this way", which is a different
statement from "this way, and stop".

**One head per divergence, not one per road.** Where three roads diverge —
Marlowe's platforms 2 and 3 off the through road — the outer head says "not the
line ahead", and the road that lights up on the schematic says which. A second
head cannot carry a road number and this one does not pretend to.

**It changes nothing.** A train is given its path at dispatch and the
interlocking guarantees the points agree with it, so nothing chooses at the
junction and nothing needs telling. This is a display of a fact the simulator
already knew and could not show. Measured: 20 posts on `twoway` carry a second
head and 5 on `depotline`; the outer head lights at 8 places on the booked
twoway service and 9 on the diverted one — the extra two being `UP@13500` and
`DN@28000`, a train turned off its own line and put back beyond the
obstruction. No run's numbers move by a second.

### One post, one lamp

Three roads at Marlowe had three lamps at one place, one per road. A train
standing there is looking at one signal post, and it is one post on the ground
too: a home signal reading into any of several roads is one post, with the
second head on it carrying which road. So the alternatives at a facing
divergence share a post, and its inner head shows the least restrictive aspect
of the group — which is not a fudge, because only one route can be set at a
time, so at most one of them is off and the one that is off is the one being
shown to the driver. `twoway` draws 104 posts for 158 signals, `depotline` 49
for 57.

The signals at the **departure** end of a station are the opposite case and stay
separate. Three roads converging on one block is three starting signals, one per
platform — which is what a real station has, because each of them protects a
different road and a train at platform 3 must not be released by platform 1's
lamp. Merging them would make the whole station one block, and Marlowe's third
road would stop paying for itself.

They are drawn at the end of their own platform rather than out at the throat
with the others. That is where a real starter stands, just ahead of the nose of
the train at the platform: a 240 m platform sits in the middle of a 1200 m
block, so the lamp moves 480 m back from the block boundary — the rearward
slide the positioning pass already allows, since showing a driver a signal
sooner than it stands costs nothing and showing it later would lie.

### The all-green headway

The interval a timetable is written to is not the one at which trains can just
about stop in time. It is the one at which they never have to slow down at all.
Braking for a yellow is a *degraded* state - it means the plan has already
failed - so the figure that matters is the **all-green headway**: the closest two
trains may follow each other with the second never seeing anything but green.

What that costs is a whole extra section of railway standing empty ahead of every
train. A signal shows green only when the section beyond the one it protects is
also clear, so a follower may run unchecked only from behind a green, and a train
effectively uses up **two** block sections rather than the one it is standing in:

```
all-green headway = (2 block sections + train length + sighting distance) / v
```

`--check` reports it per stretch:

```
signal spacing (3-aspect, 1 block of warning)
  ML   50 blocks  1200-1867 m   needs >= 591 m (EMU)   tightest margin +609 m
       all-green headway 101-253 s at 120 km/h; WDEPOT_1 sets it at 253 s (14.2 trains/hour)
```

**Read the top of that range, not the bottom.** A line is only as close-worked as
its worst section, so 101-253 s does not mean this railway will do 101 s. The
253 s belongs to the ten 40 km/h roads — both roads at each depot and every loop
— and is survivable only because a road is reoccupied by the second, third or
fourth service after the one standing in it, never by the next one. The worst
open-line section the flight meets is 149 s, an 1867 m block between Marlowe and
Ashdown; what the slow roads cost is run time rather than headway.

That is the theoretical figure, and it assumes the only thing in a train's way is
the train in front. The measured one comes from running the flight:

```
$ python scenarios/depotline/_sweep_headway.py

  headway   restrained   mean delay      worst
    270 s         0 s        0.0 s        0 s
    240 s         0 s        0.0 s        0 s     <- all-green
    210 s        30 s        2.0 s       16 s     <- degraded
    195 s        75 s        4.9 s       31 s
    165 s       258 s       16.6 s       63 s
    120 s      1168 s       77.6 s      153 s
     60 s      3250 s      264.6 s      452 s

all-green headway: 240 s (15.0 trains an hour)
```

240 s measured against a 149 s worst section. The theory is a floor and it is not
a tight one: signal spacing is only part of the story, and the rest is the route
reservation and the roads the flight is booked over, neither of which the spacing
formula knows anything about. Restraint is reported over what the flight pays
with the line entirely to itself, which is now zero seconds: every platform road
carries its own speed limit, so a train alone is braking for the platform before
any signal has anything to say to it. The whole of the column is trains getting
in each other's way.

**Below the all-green headway the line does not fail, it degrades** - each train
a little later than the one in front, which is what a real railway does when it
is booked tighter than it can work.

### What sets it, and what doesn't

depotline was 27 km with 5-8 km between stations before it was 60 km with 12-18.
Journey time roughly doubled, as it must. The headway moved too, 195 s to 210 s -
but not because of the spacing.

`block_length_m` is a *target* the builder divides evenly into each stretch, so
the same 1800 m request that produced 1700 m sections over 8 km produces 1867 m
ones over 18. Longer blocks, longer headway. Cut that one stretch back to 1200 m
blocks and the measured figure returns, with nothing else touched:

```
Marlowe-Ashdown blocks   all-green headway
       1800 m (shipped)       210 s   17.1 trains/hour
       1200 m                 195 s   18.5 trains/hour
```

(Both measured on the road-1-only flight this line ran until the roads were used
in turn, and not re-run since. The 15 s is the block length; it is not a claim
about today's booked headway, which is 240 s.)

Station spacing buys journey time. Block length buys headway. They are
independent, and only the fact that block length is declared as a target rather
than a count ties them together at all.

The loops are not the next lever, tempting as it is that Marlowe has four roads:

```
MARLOWE_1  main road,   60 km/h    169 s
MARLOWE_2  loop,        40 km/h    253 s
ML_022     open line,  100 km/h    149 s   <- what binds on the open line
```

Every station road is worth more than the open line, so the platforms are what a
closer working runs into first, and the line holds 240 s only because no road is
reoccupied by the train behind — a road at Marlowe waits four trains for its
next one.

A flight using the loops in turn puts half its trains in a 253 s road to escape
the 169 s one, and that is what it measures: spreading this flight across every
road at every station took the all-green headway from 210 s to 240 s — 17.1
trains an hour to 15.0. Loops let a fast train past a slow one; this flight has
nothing to overtake.

The shipped timetable uses them anyway. A station's roads existing and never
being used is its own kind of lie about the railway, and the cost is now a
measured number rather than a prediction. Every service is booked from its own
unimpeded run, because the loops are slower and one probe no longer describes
the flight.

### The ETCS levels

Milestone 3. Six train control systems, all reading the same interlocking, all
using the same braking physics, driver model and timetable. They differ along
exactly two axes and nothing else:

| system | danger point from | train learns it |
|---|---|---|
| conventional 3-aspect | fixed-block detection | lineside lamp, at sighting range |
| ETCS Level 1 | fixed-block detection | at a balise (lineside overlay) |
| ETCS Level 2 | fixed-block detection | continuously, by radio |
| Hybrid Level 3 | virtual sub-sections | continuously, by radio |
| moving block (L3) | rear of the train ahead | continuously, by radio |
| virtual coupling | where the train ahead **will stop** | continuously, train to train |

`--compare` runs one timetable through all of them:

```
signalling               journey   vs base restrained  min hdwy   auth m   done
-------------------------------------------------------------------------------
fixed_block_3aspect        17:32         -      5156s       90s     1363  12/12
etcs_l1                    16:38     -0:53      4297s       90s     1814  12/12
etcs_l2                    15:20     -2:12      2105s       90s     2174  12/12
etcs_hybrid_l3             13:32     -4:00        76s       90s     3122  12/12
etcs_moving_block          13:32     -4:00        54s       90s     3283  12/12
```

*(`scenarios/corridor3/scenario-intensive.yaml` - twelve services at a 90-second
interval, deliberately closer than fixed block can deliver.)*

Moving block saves **4 minutes on a 30 km run, 23%**. Nothing in the code was
tuned to produce that: the numbers fall out of braking curves and the information
each system gives the train. `restrained` - seconds trains spent held down by
signalling rather than by line speed or a booked stop - falls from 5156 s to
54 s, and `auth m` - how far ahead a train was actually allowed to run - more than
doubles. Those two columns are the mechanism; journey time is only the result.

**Hybrid Level 3 captures essentially all of moving block's benefit** (13:32
against 13:32) without needing every train to report its position and confirm its
integrity. That is exactly its selling point, and it is the reason it is a
Shift2Rail flagship rather than an academic curiosity.

#### Below capacity, the levels converge

The same comparison on the *default* corridor3 timetable, which is well under
capacity:

```
fixed_block_3aspect        18:18         -       429s
etcs_l2                    18:01   on time        66s
etcs_moving_block          18:01   on time        66s
```

Seventeen seconds, and moving block adds nothing over Level 2. This is the right
answer and the model has to produce it: on a railway that is not busy there is
nothing for better separation to win. A capacity claim is meaningless without the
traffic level stated alongside it, and a test asserts this convergence precisely
so the model cannot drift into flattering the technology.

#### Virtual sub-sections and mixed fitment

Hybrid Level 3 keeps the physical train detection sections and subdivides each
into virtual sub-sections, each holding one of four states after the ABZ 2018
formulation - **free**, **occupied**, **ambiguous**, **unknown**. Only *free* may
be given away in an authority, and that one rule is what makes mixed fitment safe:

- a train that reports position **and** confirms integrity (TIMS) resolves to the
  sub-sections it really covers - fine granularity, near-moving-block headway
- a train that reports position but **cannot** confirm integrity marks what is
  behind its reported front **ambiguous**, because the rest of it may still be
  there
- a train that reports nothing marks its whole block **unknown**, which is Level 2
  behaviour - safe, just coarse

So a partly-fitted fleet degrades gracefully instead of failing, which is the
whole point during migration. Tests drive a fitted train behind each kind of
leader and assert the following distance changes the right way.

Set fitment per rolling stock type:

```yaml
stock:
  - id: EMU_FAST
    etcs_level: l2      # none | l1 | l2 | l3
    tims: true          # can it confirm its own integrity?
    v2v: false          # train-to-train link, for virtual coupling
```

#### Seeing it: fixed block against moving block

The same twelve trains, the same second, on the intensive timetable:

| | fixed block | moving block |
|---|---|---|
| lineside | red / yellow / green lamps throughout | nothing lit, marker boards only |
| track | whole blocks lit red | untinted; a braking envelope per train |
| speeds | 140, 109, 105, 76, **63**, 140, 77 km/h | every train 140 km/h |
| governed by | three trains `obeying caution` | every train `line speed` |
| spacing | 22.7, 17.4, 14.3, 11.1, 7.7, 5.2, 2.8 km | 24.0, 20.5, 17.0, 13.5, 10.0, 6.5, 3.0 km |

The spacing column is the whole story. Under moving block the trains sit exactly
3.5 km apart — 90 seconds at line speed, which is what the timetable asked for.
Under fixed block the gaps are ragged, because each train is being checked down
behind the one in front and then released: the concertina, visible as a shape
rather than a number.

#### Two things the model insisted on

- **Block exclusivity is not a universal safety property.** Under moving block two
  trains sharing a block section is the entire point. Each system now declares
  `separates_by = "block"` or `"distance"`, and the kernel picks its invariant
  accordingly - but *physical separation*, no train's front passing another's
  rear, is asserted for all six.
- **A train must not be blocked by its own footprint.** An unfitted train marks
  every sub-section of its block unknown, including the ones ahead of its own
  nose, so sub-sections record who claimed them - the same reason
  `Occupancy.is_free` takes an `ignoring` argument.

### The interlocking was making moving block behave like fixed block

For a long time the three distance-separated systems here were barely better than
Level 2, and the reason was not in any of them. It was in the interlocking.

A movement authority is capped at the first controlled signal ahead with no route
set from it — correctly, because no ETCS level overrides an interlocking. But the
interlocking refused to set a route into a block that was occupied or already
held by another train's route, and it held each route until its train had left
the block entirely. So the follower's route stopped at the signal behind whatever
block the train in front happened to be standing in, and its authority stopped
there too. The rear of the train ahead never entered into it. Moving block was
running to block boundaries with extra steps, and the granularity of the
reservation had quietly become the granularity of the railway.

Under `separates_by = "distance"` the interlocking now:

- **sets a route into an occupied block.** The block is not what keeps trains
  apart there, so refusing on occupancy was answering a question the signalling
  system answers better. Crossings are untouched — two trains meeting on a flat
  junction is not a following move, and no separation model makes it one.
- **gives the route back as soon as the train is on it and clear of its points**,
  rather than when it has left the block. A route there is a permission to pass,
  not a reservation of the road ahead.

Points are unchanged: still locked to a position, still released sectionally as
the rear passes, still refused to a route that wants them the other way. That is
the part that was ever doing safety work.

What it is worth, on the flight booked at intervals it cannot keep — mean delay:

| booked | fixed block | ETCS L2 | Hybrid L3 | moving block | virtual coupling |
|---|---|---|---|---|---|
| 120 s | 77.6 s | 13.6 s | 0.5 s | on time | on time |
| 90 s | 156.2 s | 49.8 s | 8.1 s | 4.4 s | 2.1 s |
| 60 s | 264.6 s | 146.0 s | 22.6 s | 15.8 s | 12.4 s |

Before the change, moving block at a 60 s booking was 104.9 s late; it is now
15.8 s. Nothing in `MovingBlock` moved.

The relaxation is safe here because every road has a direction and no route runs
against it — the two directions of a stretch signalled both ways are two roads,
not one road used backwards — so anything already in the block ahead is running
the same way. Opposing moves are kept apart a section at a time instead, by the
crossings and the direction lock.

#### Seeing it: two trains in one block

Neither the change above nor the systems it frees show up on the shipped
scenario, for two reasons that are both the scenario being honest:

- **the fleet is not fitted.** depotline runs lineside signals and unfitted
  stock. A train that cannot confirm its own integrity cannot be followed by
  distance — its rear is not a position anything may believe — so moving block
  falls back to block granularity behind every train and looks exactly like
  fixed block. Correctly. `--check` now says so on a `fleet` line, and a run
  under a distance-separated system warns before it starts.
- **the trains are four minutes apart.** Booked at the 240 s this line can hold,
  no two of them ever come within a block of each other, so there is nothing for
  a closer separation to be closer than.

`scenarios/depotline/scenario-l3.yaml` fixes both: the same eight services, the
same railway, a fleet fitted with Level 3, integrity monitoring and the
train-to-train link, booked at 90 seconds.

```
python run.py scenarios/depotline/scenario-l3.yaml
python run.py scenarios/depotline/scenario-l3.yaml --system fixed_block_3aspect
```

| system | ticks with two trains in one block | mean delay |
|---|---|---|
| fixed block | 0 | 156.2 s |
| ETCS L2 | 0 | 49.8 s |
| Hybrid L3 | 916 | 8.1 s |
| moving block | 1151 | 4.4 s |
| virtual coupling | 1345 | 2.1 s |

Zero violations in every column. Two trains in one block is not a fault under
distance separation — the kernel takes its safety invariant from the signalling
system, and what must hold there is that no train's front passes another's rear.

### Virtual coupling: borrowing the braking distance in front

Moving block already runs a train up to the rear of the train ahead less a
margin, and under absolute braking distance that is as close as it gets: the
follower has to be able to stop short of where the leader *is*, because the
leader might be a wall.

Virtual coupling drops that assumption. A train-to-train radio link tells the
follower what the leader is doing, so the follower may plan to stop where the
leader *will* stop:

```
danger point = rear of the leader
             + how far the leader runs on if it brakes now
             - (standing margin + what the follower covers awaiting the news)
```

The borrowed term is the whole benefit, and it is worth most at speed and
nothing at all against a stationary train — there is nothing to borrow from a
train that has already stopped. The leader's run-on is taken at the *hardest*
rate it can brake at, not the rate it would normally use: the follower is
planning to stop where the leader stops, so it has to assume the leader stops as
short as it possibly can.

Two things pay for it, and both are modelled. The link has latency, which turns
into distance at the follower's speed — the reason the concept waits on FRMCS
rather than GSM-R. And when the link is gone the justification for the tight
margin goes with it, so the degraded margin is the one moving block would have
used; carrying the coupled margin into degraded working would make an unfitted
train appear to outperform moving block on identical physics.

**The control experiment.** With relative braking switched off
(`assume_leader_brakes: false`) and zero latency, virtual coupling reproduces
moving block at the same margin — identical to the second at a 60 s booking,
2965 s restrained and 14.1 s mean delay for both, where the coupled system reads
282 s and 12.4 s. So everything below comes from the borrowed braking distance
and not from a tuned constant. Putting three seconds of latency on the link gives
most of it back: 13.2 s.

**Measured, depotline, the eight-train flight booked at each interval — and it
depends entirely on which roads the flight is booked over.** Mean delay:

| booked | road 1 only, MB | road 1 only, VC | roads in turn, MB | roads in turn, VC |
|---|---|---|---|---|
| 240 s (the line's own headway) | on time | on time | on time | on time |
| 120 s | on time | on time | on time | on time |
| 90 s | 10.9 s late | on time | 4.4 s late | 2.1 s |
| 60 s | 112.4 s late | 84.5 s | 15.8 s late | 12.4 s |

And how close the two actually stand a train behind another, in a queue on one
road: **125 m under moving block, 72 m under virtual coupling** — the margin plus
the driver's own 25 m, and nothing else. That difference is the whole system.

Three things in that table are worth more than the numbers:

- **above the line's own headway it buys nothing.** At 240 s and 120 s every
  system on the ladder is on time, virtual coupling included. It is a congestion
  technology, and this line's constraint at its booked interval is the station
  dwell and the route-setting, not the following distance.
- **it pays where the queue is a following queue.** Send every train to road 1
  and virtual coupling saves a quarter of moving block's delay at 60 s, because
  the trains are nose to tail on one piece of railway. Spread the same flight
  across the roads at each station and both systems nearly empty the delay out
  anyway: what was holding trains up was the platform and the throat, and no
  amount of radio between trains shortens a dwell.
- **an unfitted fleet falls back past moving block, not to it** — 49.8 s against
  4.4 s at 90 s, 146.0 s against 15.8 s at 60 s, which is Level 2's figure to the
  decimal. No link means the rear of the train ahead cannot be trusted at all, so
  the fallback is block granularity rather than absolute distance. That is the
  honest answer, not a penalty: the whole benefit was the link.

The hazard the model does not remove is the one that keeps this off real
railways. Relative braking assumes the leader cannot stop faster than its own
emergency brake. A leader that hits something stops in far less than that, and
the follower, by construction, cannot.

### The metro line: where moving block actually pays

corridor3 is a main line, and on a main line most of what ETCS buys is the
removal of the driver's *sighting and reaction* penalty — which is why Level 2
captures nearly all of the benefit there. `scenarios/metro` is the other kind of
railway, and it gives the opposite answer.

Twelve km, six stations 2.2–2.6 km apart, 90 km/h, 120 m units, every train
calling everywhere, no loops and nothing to overtake. Twelve trains an hour each
way, booked at a **75-second headway** on the run times a single unimpeded train
achieves — so the plan is conflict-free by construction, and any delay that
appears is the signalling refusing to deliver it.

```
signalling               journey   vs base restrained  min hdwy   auth m   done
-------------------------------------------------------------------------------
fixed_block_3aspect        13:07         -      2755s       75s      734  24/24
etcs_l1                    13:07   on time      2755s       75s     1147  24/24
etcs_l2                    13:06   on time      2622s       75s     1159  24/24
etcs_hybrid_l3             11:56     -1:11       591s       75s     1335  24/24
etcs_moving_block          11:52     -1:14         0s       75s     1370  24/24
```

**Level 2 saves one second.** Not because anything is broken — because what is
holding the following train back here is not what it can see. It is that the
train in front occupies a whole 500 m detection section while it stands at the
platform with its doors open, and Level 2 still separates by section. The cost
being removed on a main line is *sighting*; the cost here is *granularity*, and
only making the granularity finer (Hybrid L3) or abolishing it (moving block)
touches it.

Moving block's restraint column reads **`0s`** — not one second, across
twenty-four services, in which any train was held back by another. Run it
headless and every service arrives to the second. Under fixed block:

```
U04 +0:40   U05 +0:53   U06 +1:07   U07 +1:21   U08 +1:35
U09 +1:49   U10 +2:03   U11 +2:17   U12 +2:31
```

Fourteen seconds more per train, never recovering. Fixed block settles at an
**89-second station headway** on this line: 40 trains an hour where the timetable
asked for 48.

The constraint really is the station and not the signal spacing, which is what
makes the comparison mean anything — `--check` reports the open line implying a
45–63 s fixed-block headway, comfortably inside 75. A test asserts that, because
if the blocks were simply too long for the headway then fixed block failing would
prove nothing except that the layout had been badly signalled.

#### The two limits on the other side

It would be easy to read the above as *distance separation removes the limit*. It
does not; it moves it. Two variants say where it lands.

**`scenario-60.yaml` — the same flight at 60 s.** Nothing delivers it: fixed
block +163 s, Level 2 +162 s, moving block +51 s. What is left is not signalling
at all:

```
station headway  =  dwell
                 +  the time the follower needs to close up and berth
                 +  the time the leader needs to pull clear of the platform
```

With a 30-second dwell and 1.1 m/s² those come to a little under 60 s here, so
the flight loses time station by station. The way out is shorter dwells —
platform-edge doors, wider doors, passenger flow — or more acceleration. That is
why metro capacity programmes spend as much on doors as on train control.

**`scenario-mixed.yaml` — two units without integrity monitoring.** U06 and D06
report their position but cannot confirm their rear, so moving block will not
follow them by distance and falls back to section separation. Per train:

| | U01–U05 | **U06** | U07 | U08 | U09 | U10 | U11 | U12 |
|---|---|---|---|---|---|---|---|---|
| restrained | 0 s | **0 s** | 66 s | 62 s | 58 s | 34 s | 16 s | 16 s |
| delay | on time | **on time** | +13 s | +10 s | +7 s | +4 s | +4 s | +4 s |

The unfitted unit runs its booked path perfectly and pays nothing. The entire
cost of not fitting it falls on the services behind, and it never washes out —
the delay settles at four seconds rather than returning to zero, because a plan
booked at the achievable headway has no slack anywhere to absorb it. Whether to
fit a unit is therefore not a decision about that unit.

Note also that every one of those delays is inside the 30-second tolerance the
summary reports as `on time`, so `--headless` shows nothing wrong at all. The
damage this does is not lateness; it is capacity, and it is only visible in the
restrained-seconds column. That is worth remembering before reading a punctuality
figure as evidence that a railway has headroom.

Hybrid Level 3 is not a free rescue here either, which is worth knowing before
quoting it as one. Its default four sub-sections per section is 150 m on this
line, against the ~145 m a moving-block authority leaves on a platform approach,
so out of the box it comes out slightly *worse* rather than better. Sweeping the
granularity on the 75-second timetable:

| `vss_per_block` | 4 (150 m) | 6 (100 m) | 8 (75 m) | 12 (50 m) |
|---|---|---|---|---|
| mean delay | +4 s | +3 s | on time | on time |
| restrained | 591 s | 232 s | 108 s | **0 s** |

So sub-sections want sizing against braking distance at the local speed rather
than counting per block — a conclusion the scenario produced rather than one
built into it, and exactly the sort of thing an HL3 deployment has to decide.

### When something goes wrong

Everything above is a railway working to plan. That is the right baseline, but it
leaves out what operators spend the day on — and it leaves a traffic management
system with nothing to manage.

Three kinds of disturbance can be **declared** in a scenario file: a service
starting late, a train standing over its dwell, and a temporary speed restriction
over a stretch of line for a window of time.

```yaml
disruptions:
  - kind: dwell_overrun
    service: S1
    station: BETA
    minutes: 4                    # or seconds:
    reason: passenger taken ill
  - {kind: late_start, service: F2, minutes: 3}
  - kind: speed_restriction
    track: UP                     # omit for every line
    from_km: 18
    to_km: 22                     # written in either order
    max_speed_kmh: 40
    from_time: "07:00"            # omit for the whole run
    to_time: "07:40"
```

Declared, not random. A random disturbance model would need calibration nobody
here can supply and would make runs irreproducible — which would destroy the one
property every comparison in this project rests on. A named incident answers
*what does this do*, which is the question a study actually asks.

`--propagation` runs the scenario **twice**, with the incident and without it, and
subtracts service by service. That difference splits in two, and the split is the
point:

- **primary delay** — time lost by the service the incident happened to. No
  signalling system can prevent it.
- **knock-on delay** — time lost by services it merely got in the way of. This is
  a property of the *railway*, not the incident, and it is the part better
  signalling, more slack or a cleverer dispatcher can reduce.

#### The same incident on two railways

corridor3, where the 07:00 stopper stands four minutes over at Beta — a line with
a loop road, mixed speeds and running-time supplement in the timetable:

```
  primary delay       240 s
  knock-on delay       49 s
  propagation        0.20 s of knock-on per second of primary
```

One other train, F2, loses 49 seconds. Everything else runs untouched: the loop
absorbs it, which is what the loop is for.

The metro, where U05 stands ninety seconds over at Central — no loops, nothing to
overtake, and a plan booked at the achievable headway with no slack anywhere:

```
  primary delay        88 s
  knock-on delay      630 s
  propagation        7.16 s of knock-on per second of primary
```

**Thirty-five times the amplification, from a smaller incident.** And the shape
of it is the thing to look at. Under fixed block every following train loses
*exactly* the same ninety seconds:

```
U06 +1:30   U07 +1:30   U08 +1:30   U09 +1:30   U10 +1:30   U11 +1:30   U12 +1:30
```

The delay does not decay. It transfers whole, and would run to the end of the
service day. Under moving block, the same incident:

```
U06 +1:26   U07 +1:20   U08 +1:13   U09 +1:05   U10 +0:57   U11 +0:49   U12 +0:41
```

About eight seconds recovered per train, because a following train can close
right up behind the one in front and go the moment it goes. **That is the
clearest thing distance separation buys under disruption, and it is not a journey
time claim at all** — it is the difference between a delay that decays and one
that does not.

#### A trap the metric sets

Run the same incident through every level on corridor3 and the propagation column
ranks fixed block *best*:

```
signalling               primary  knock-on  per s primary     clean  on the day
-------------------------------------------------------------------------------
fixed_block_3aspect         240s       49s           0.20     18:18       18:50
etcs_l1                     240s       82s           0.34     18:07       18:42
etcs_l2                     240s      101s           0.42     18:01       18:39
etcs_hybrid_l3              240s       59s           0.25     18:01       18:34
etcs_moving_block           240s       52s           0.22     18:01       18:33
```

It is not resilience. Knock-on is measured against each system's *own* clean run,
and fixed block's clean run was already 17 seconds slower — so F2 arrives at
almost the same minute in every case (18:50 / 18:42 / 18:39 / 18:34 / 18:33) and
the system with the worse plan simply had less left to lose.

The last column is the one that decides it, and it moves the right way. A
relative resilience figure quoted without the absolute outcome will rank the
better railway lower, every time — which is why the report prints both and says
so underneath.

### Junctions: where the order stops being obvious

corridor3 and metro are both *linear*. Every train is behind or in front of every
other on its road, the interlocking only ever asks whether the road ahead is
clear, and better signalling means trains can run closer together.
`scenarios/junction` is not linear, and it is where capacity is actually lost on
a network.

```
  ALPHA ------------------ BETA ------------------ GAMMA      up main
  ALPHA ------------------ BETA ------------------ GAMMA      down main
                          /    \
                 BR_UP __/      \__ BR_DN
                       |          |
                     HALT      HALT                           the branch
```

A single-track branch converges on the up main at Beta through a **trailing
point**, and the down main throws off to it through a **facing point**. Beta has
one platform road each way — deliberately, because a bay platform for the branch
would make the conflict disappear, which is exactly why bay platforms at junction
stations are expensive and worth it.

Both points fall out of the topology; nothing in the scenario file declares them.
All the file says is where the branch attaches:

```yaml
  - id: BR_UP
    direction: up
    serves: [HALT, BETA]
    junction: {track: UP, at: BETA, length_m: 700, max_speed_kmh: 60}
```

Beta being this track's *last* call is what makes it a joining move and so a
trailing point; a branch whose *first* call is Beta diverges instead, and gets a
facing one. `--check` then prints the route table with the conflicts spelled out:

```
  PT_UP_13400_T      trailing km 13.400  legs UP_007/BR_UP_JN  normal UP_007
    R_BETA_1_from_BR_UP_JN (into BETA_1, PT_UP_13400_T to BR_UP_JN)
      cannot be set with: R_BETA_1_from_UP_007
```

#### What happens

Nothing breaks. The interlocking simply refuses:

```
07:05:10  route_refused BU1   R_BETA_1_from_BR_UP_JN: BETA_1 is held by a
                              route set for MU1
```

and the branch DMU stands on the junction link — 0 km/h, `signal at danger` —
with the entire main line green and empty in front of it. Over six cycles it is
refused six times, and the cost is stable rather than growing:

```
  branch up (BU1-BU6)   +2:21 each
  main line up (MU2-MU6) +1:03 each
  everything else        on time
```

The main line loses time too, and the way it loses it is worth following. The
branch train, pushed 2:21 late, ends up running *ahead* of a main line train it
would otherwise have been clear of — and it is a 100 km/h DMU on a 140 km/h
railway. Instrumenting where each train is restrained shows MU2 held twice: once
at km 12–13 approaching the junction, and again at km 24–29, most of the way to
Gamma. **The junction delay does not stay at the junction.**

#### Why this needed building before the traffic management work

Run the ladder over it:

```
fixed_block_3aspect        16:43         -      2375s restrained
etcs_l2                    16:30   on time      1703s
etcs_moving_block          16:21   on time      1337s
```

**Moving block saves 2.2%.** On the intensive corridor it saves 23%, on the metro
9.5%. Distance separation shortens the gap between trains going the *same way*,
and that is not this problem. Two trains wanting the same points is a question of
*order*, and no train control system answers it.

Nor does anything here. The main line wins because it asked first — the branch
train is shorter, slower, has further to go over the junction, and is the one
with no alternative route, and none of that is considered by anything. That is
not a bug to fix in the interlocking, which is behaving exactly as an
interlocking should. It is a missing layer, and it is the specification for
Phase 5. A test asserts the gap deliberately: if a later dispatcher starts making
a real decision here, `test_nothing_decided_that_the_main_line_should_win` should
fail and be rewritten to say what the decision is.

#### Flat or grade separated: what the diamond costs

The junction above is arranged so that nothing crosses anything — the branch sits
beside the up main and joins it directly. Real junctions are usually not so
convenient. Where the branch is on the far side, a train reaching the up main has
to get across the **down** main to do it, and where that happens on the level it
is a **diamond**: two lines crossing, no connection between them, no points, and
one rule — not two trains at once.

`infrastructure-flat.yaml` puts the branch there:

```
  infrastructure.yaml              infrastructure-flat.yaml

  BR_UP  ‾‾\                       UP    ────────────●───────
  UP     ───●──────                DN    ──────────╳─────────
  DN     ──────────\               BR_UP ─────────╱──────────
  BR_DN            ‾‾              BR_DN ──────\─────────────

  nothing crosses anything         the up branch crosses the down main,
                                   and the down branch crosses the up branch
```

Nothing declares the crossings. They are read off the drawing: a link ramping
from one alignment to another crosses exactly the tracks whose alignment lies
between its two ends. `--check` lists them, and the route table picks them up:

```
level crossings of one line by another (diamonds)
  BR_DN_JN     x BR_UP_JN      no connection, but only one train at a time
  BR_UP_JN     x DN_009        no connection, but only one train at a time

    R_BR_UP_JN (into BR_UP_JN, crosses BR_DN_JN, DN_009)
      cannot be set with: R_BR_DN_JN, R_DN_009
```

`R_BR_UP_JN` has **no points on it at all** and is still a controlled route,
because granting it takes a crossing away from somebody else. In the log that
reads exactly as a signaller would see it — a down main express refused its own
plain line:

```
07:10:25  route_refused MD1  R_DN_009: DN_009 is held by a route set for BU2
```

`scenario-flyover.yaml` is the identical railway with one line changed in the
infrastructure file — `grade_separated: true` on the up branch connection, a
flyover instead of a crossing. Same alignments, same blocks, same trains, same
timetable, so the difference between the runs is the diamond and nothing else:

```
                 flyover      flat      cost
mean journey       1003s     1062s      +59s
total restrained   2441s     4011s    +1570s
```

**And the trains that pay are not the ones doing the crossing.**

```
MU  +0 s      BU  +0 s      BD  +76 s      MD  +160 s
```

The branch train asks first, gets the road, and loses nothing. What loses two and
a half minutes is the down main express, which has no business at the junction at
all. That is the argument for grade separation in one line, and it is the
opposite of the intuition that the train taking the awkward move should be the
one to suffer.

#### One run is not a result

Move the branch service ninety seconds and the conflict misses entirely.
`python scenarios/junction/_sweep_phase.py` runs both layouts across a whole
six-minute service interval:

```
branch phase   flyover      flat     cost
        0 s      1003s     1062s     +59s
       30 s       995s     1043s     +48s
       60 s       988s      988s      +0s
       90 s       980s      980s      +0s
      120 s       971s      971s      +0s
       ...
  best +0 s      mean +9 s      worst +59 s
```

Eight of the twelve phasings cost **nothing**. A flat junction is not a fixed
tax; it is free when the conflicting moves miss each other and expensive when
they coincide. That is why flat junctions survive all over real networks, and why
the case for rebuilding one is argued against a whole timetable rather than
against a layout.

It also hides a cost that appears in none of these numbers: to get one of the
free phasings, the timetable has to be *designed around* the junction. The trains
cannot go where they would otherwise go. Quoting +59 s as "the cost of a flat
junction" would have been picking the number that suited the argument, so a test
asserts the free case too.

### Crossovers: a train changing lines

Every layout so far kept each train on the road it started on. It could take a
loop, a branch or a platform, but never leave its own line for another one.
`scenarios/fourtrack` can:

```
         ___________________________________________ UP FAST
        /
_______/___________________________________________ UP SLOW
                     XO_UP, km 17
```

A **crossover** is a connection between two running lines out on the plain line:
a facing point on the line it leaves, a trailing point on the line it joins, and
a train lying across both while it goes over. It is what a real signalling
schematic is full of, and it is declared as the two ends and a length:

```yaml
crossovers:
  - id: XO_UP
    from: US            # up slow
    to: UF              # up fast
    km: 17.0            # where it leaves the first line
    length_m: 400       # it reaches the second this much further on
    max_speed_kmh: 70
```

Both points fall out of the topology as usual. What is new is that **the block
plan has to be drawn around the connection**: a signal must be able to stand at
each end and a route must be able to finish there, so the builder splits each
stretch at any crossover before dividing it into blocks. That is the order it is
done in on the ground too.

#### Or between two roads, anywhere on the railway

The same list takes platform roads as ends, and then neither the id nor the km is
needed:

```yaml
crossovers:
  - {from: KINGSFORD_2, to: MARLOWE_3, max_speed_kmh: 80}
```

That is a piece of railway from Kingsford's loop to Marlowe's third road, and
`--check` names it back before anything runs:

```
connections
  X_KINGSFORD_2_MARLOWE_3      KINGSFORD_2 -> MARLOWE_3   km 12.600-29.400  16800 m at 80 km/h
                               11 block(s), 12 signal(s), 12 route(s) into them
```

Three things are being decided there, and each of them can bite:

- **the id is derived from the ends**, because that is the only thing anyone
  wants to look it up by. Give an `id` and yours is used instead.
- **the length comes off the ground** when it is not given: the two ends are real
  places with real chainages, and the railway between them is as long as the gap.
- **it is divided into blocks like any line**, to the block length of the line it
  leaves. One 17 km block section would hold one train at a time; left like that
  a connection quietly costs more capacity than it adds, which is worse than
  failing.

**A road end is a throat, not a road.** Every road at a station shares its throat
nodes with the others — that sharing is where the points come from — so a
connection declared from `KINGSFORD_2` leaves the Kingsford throat and a train
off either Kingsford road can take it. Naming the road says *where* the
connection is, not *who* may use it. Joining two roads at one station is refused
for the same reason: they already meet, at the points.

```
crossover 'X_MARLOWE_2_MARLOWE_3' runs backwards: MARLOWE_2 ends at km 30.600
and MARLOWE_3 begins at km 29.400, which is behind it. Two roads at one station
already meet at their throats - the points join them - so a connection between
them has nothing to connect.
```

#### Working a line in both directions, without teaching trains to run backwards

`scenarios/twoway` is depotline's sixty kilometres with a line each way, and it
exists for the move a crossover between an up line and a down line is for: when
something is in the way, a train crosses to the opposite line, runs along it
against the normal direction, and crosses back beyond the obstruction.

The obvious way to model that is to let a train traverse a block backwards. It is
also the wrong way: the path, the signals, the routes and the occupancy would all
have to start asking which way a train is facing, and every one of them is
simpler for not knowing. So the scenario draws a crossover between the up line
and the down line, and says nothing else:

```yaml
crossovers:
  - {id: XO_WEST, from: UP, to: DN, km: 13.5, length_m: 400, type: scissors}
  - {id: XO_EAST, from: DN, to: UP, km: 32.0, length_m: 400, type: scissors}
```

Everything else falls out of those two lines. The stretch **between** them,
km 13.5 to km 32.4, gets **a second set of block sections over the same rails**,
running the other way: `DN_019_R` is the road up the down line where `DN_019` is
the road down it. Every movement over the pointwork then joins two roads that run
the same way, so the rule that a crossover joins lines running the same way is
not being bent.

`type` picks what is laid, and it is not decoration:

| type | what it is | movements |
|------|-----------|-----------|
| `single` (default) | one diagonal. `from` and `to` read in the direction of increasing km, so `UP → DN` is drawn `\` and `DN → UP` is drawn `/` | 2 — the diagonal traversed each way |
| `scissors` | both diagonals over one piece of pointwork | 4 |
| `diamond` | two lines crossing on the level, joined to nothing | 0 |

A diagonal is a piece of railway, so it is traversed both ways: `UP → DN` takes
an up train onto the down line **and** a down train back off it. What it does not
do is take an up train back, which needs the other hand further along — which is
why a diversion is drawn as a `\` at one end and a `/` at the other:

```
UP  ------------------\-----------------------------/-------------
                       \                           /
DN  --------------------\-------------------------/--------------
```

That pair diverts up trains. Down trains need the opposite pair, or `scissors`,
which is what `twoway` uses so that both directions can be worked round Marlowe.
A `diamond` lays nothing at all: no train changes lines there, and all it costs
is that two trains cannot be on it at once — which is the whole cost of a flat
junction, and is already how one is policed here.

One consequence of the same rails carrying two roads: a path finder that only
follows nodes will arrive at a shared node going up and leave it going down,
which on the ground is a train changing ends in the middle of a junction — and
it will do it in preference to a longer legitimate way round. Nothing else in
the simulator models a reversal, so `find_path` refuses one: a train that
arrives travelling towards higher chainage leaves travelling towards higher
chainage. Without that rule the hand of a crossover made no difference, because
every wrong way round was reachable by turning about at a point.

Where the reversible stretch is is not declared, because it is not a free
choice: a line is worked both ways exactly where a train can get onto the
opposite line *and off it again*, which is decided by the crossovers. That is
how a real railway reads too — bidirectional signalling is provided between the
crossovers, because between them is the only place it is any use. Declaring it
separately meant saying the same thing twice in two places that could disagree;
making every line reversible end to end meant signalling twice the railway to no
purpose. Two things police it, and neither is new:

- **each twin block crosses the block underneath it.** Crossing blocks already
  meant something — it is how a flat junction is policed — so the interlocking
  will not set a route over one direction's road while anything holds or occupies
  the other's. The kernel now also reports a violation if two trains are ever in a
  crossing pair at once, under every signalling system: no separation model makes
  it safe to run a train up a line another train is coming down.
- **the two directions share a lamp.** Each road has its own signals at the
  same block boundaries, and drawing both put two lamps at one chainage facing
  each other, which reads as a fault rather than as a pair. Neither is the
  *wrong* one — a line signalled in both directions is signalled in both
  directions, and which way it is set is a state of the railway, the same kind
  of fact as which way a point lies. There is only ever one answer to show,
  because the section is worked one direction at a time, so the pair share a
  lamp and it stands on the side of the direction in force. The side is the
  indication. On `twoway` that turns 158 signals into 112 lamps, and it is why
  only the section between Kingsford and Marlowe looked doubled: that is the
  only station-to-station run inside the two-way stretch.
- **a section worked both ways is worked one way at a time.** Safety is not liveness:
  admit a train at each end and they meet in the middle, each holding what the
  other needs, and neither can be backed out. Every railway that works a section
  both ways solves this the same way — a token, a staff, a pilotman in the cab —
  and the interlocking now refuses a route into a section that is being worked
  the other way.

`scenario-blocked.yaml` books every up train through `MARLOWE_DN_1_R`: the down
main road, taken in the up direction. Each up train then leaves its own line at
km 13.5, runs eighteen kilometres up the down line calling at Marlowe on the way,
and crosses back at km 32.0.

```
service   delay      what happened
U01-U06   on time    815 ticks each on the down line, thirteen minutes
D01       +35:44     queued at Ashdown for a section it could not have
D06       +14:35     by then the up flight was through
```

Nobody is late by accident there. The diverted direction keeps time because it
has the section; the direction that lost its line pays the whole bill, and the
delay decays down the flight as the section frees up. That is what single-line
working costs, and it is the answer the model should give.

Zero ticks with two trains on the same rails, zero violations, across the whole
run.

#### Adding one changes which way the trains go

Building a connection was only half of it. The route finder used to take the way
with the fewest block sections, which is the same answer on a railway with one
way through and the wrong one the moment there are two: an 80 km/h connection of
11 blocks beat the 100 km/h main line of 14, so **every train in the timetable
silently moved onto a road nobody had booked it over**, and the flight went from
on time to half an hour late.

It now takes the way that takes least *time*, which is the road a planner would
pick. On depotline with the connection above, no train uses it — it is slower —
and the comparison table is unchanged to the second from before there was one.

#### Between lines that run the same way, and between lines that don't

A slow-to-fast or fast-to-slow crossover joins two roads worked the same way,
and one declaration is one movement. A crossover between the up line and the
down line is a different animal: it is what makes the stretch between two of
them signalled in both directions, and the builder expands it into the
movements that stretch needs (see [above](#working-a-line-in-both-directions-without-teaching-trains-to-run-backwards)).
It used to be refused outright, on the grounds that a train taking it would be
running against the way the other line is signalled — which is true, and is
exactly the thing that turned out to be worth building rather than refusing.

#### What it is for

Four running lines, and **Beta has platforms on the slow lines only** — which is
how a four-track station is normally built, the fasts running through non-stop
with no platform at all. So a semi-fast that calls at Beta has to be on the slow
line there, and has to get back onto the fast line afterwards to be worth
running. Four times an hour each way, that move is the scenario.

Nothing in the timetable mentions the crossover. The route finder uses it because
it is the only way from a slow-line platform to a fast-line one:

```
BETA_US -> US_009 -> US_010 -> XO_UP -> UF_009 -> ... -> GAMMA_UF
```

And what it produces is **a flat junction in the middle of a fast line, in
everything but name**:

```
07:15:09  route_refused X1  R_UF_009_from_XO_UP: UF_009 is held by a route
                            set for F2
```

The semi-fast waits on the slow line while the express runs past; `worst arrival`
is X1 at +1:42, and every express is on time. Same argument as the junction
scenario, one layer down — and once again the express wins because it asked
first, not because anything decided it should. It is why heavily used four-track
railways put semi-fast connections in a burrowing junction rather than a
crossover.

Better signalling barely touches it, for the same reason as before:

```
fixed_block_3aspect        15:37         -      1473s restrained
etcs_moving_block          15:08   on time       198s
```

Twenty-nine seconds, 3.1%. Distance separation shortens the gap between trains
going the same way; a train wanting to *become* one of them is a question of
order.

---

## Scenario files

Written the way an engineer would describe a line — stations at chainages,
tracks that serve them, platforms, block lengths — and expanded by
`scenario/builder.py` into ~40 segments, blocks and signals.

```yaml
stations:
  - {id: BETA, name: Beta, km: 12.0}

tracks:
  - id: UP
    direction: up
    serves: [ALPHA, BETA, GAMMA]
    block_length_m: 2000
    block_lengths:                                        # per-stretch override
      - {from: ALPHA, to: BETA,  block_length_m: 1500}
      - {from: BETA,  to: GAMMA, block_length_m: 2400}

platforms:
  - {id: BETA_3, station: BETA, track: UP, length_m: 220,
     max_speed_kmh: 80, y_offset: -0.34, berth: centre}   # the loop road
```

Parallel platform roads are simply several segments sharing a pair of nodes. No
switch model is needed for them to be safe: each road is its own block, and the
single approach block ahead of the divergence can only ever hold one train.

**On berthing.** A train's position is its **front** — `chainage_m` is the
distance its nose has run, and its rear is that minus its length. So where a
train stops is where its *nose* stops, and for a train shorter than the platform
that leaves a choice the platform has to make, not the train:

| `berth` | where a short train stands |
|---|---|
| `far` (default) | nose at the far end of the concrete — the stop car marker at the platform end, the usual arrangement where the platform was built for the longest train that calls |
| `centre` | centred on the concrete, which is what a station does when one set of doors and one set of staff serve trains of several lengths |
| `near` | rear at the near end, so a following portion can draw up behind |

A 160 m train in a 240 m platform stands 530–690 m along its road under `far`
and 520–680 under `centre`, with the concrete at 480–720. A train *longer* than its platform overhangs wherever it is put, and
`--check` says so by service and station rather than quietly letting it hang off
the end.

**On block lengths.** They are not uniform, because in practice they are not.
The floor is braking distance — under three aspects a driver passing a yellow
must stop at the next signal, so `block ≥ braking distance + reaction + margin`
(about 1222 m at 140 km/h here). The ceiling is capacity — minimum headway is
roughly the time to clear two blocks plus the train's length, so shorter blocks
mean more trains per hour, paid for with more signals. So the busy Alpha–Beta
section is signalled at 1425 m and the fast open line at 2486 m. `--check`
reports both the margin against the floor and the headway each stretch implies.

Shortening the inner blocks from ~1900 m to 1425 m cut the fast train's
restrained running from ~300 s to ~99 s and its journey by 34 seconds, on the
same timetable — the capacity trade-off, measured.

**Generated timetables.** The metro timetables are derived data, not written by
hand: `scenarios/metro/_generate_timetables.py` runs a single unimpeded train to
measure the section times, then books every service on those times offset by one
headway. That is what makes the plan conflict-free by construction, so a delay in
the comparison is always the signalling and never the plan. Re-run it after
changing a dwell, a chainage or the stock.

**No PyYAML?** `minyaml.py` parses the subset the scenarios use (block mappings
and sequences, flow `{}`/`[]`, comments, scalars). A test asserts it agrees with
PyYAML on every shipped file. `.json` scenario files work too.

---

## Verification

`python run_tests.py` — 217 tests covering:

- **braking** — a train stops within the computed service braking distance and
  berths on its stopping point to within a metre, on the level and on a bank
- **dynamics** — the traction curve, Davis resistance, gradient force, adhesion
  and brake build-up, each checked against the figure a traction engineer would
  expect rather than against whatever the code produces
- **block exclusivity** — asserted every tick of the full corridor3 run
- **red signals** — a train driven at an occupied block stops *before* the
  protecting signal, never past it, and gets going again when it clears
- **aspects** — red over an occupied block, yellow before a red, and a
  divergence taking its least restrictive successor
- **the overtake** — S1 is proved to be inside the loop for a window containing
  F1's passage of the through platform
- **restraint** — the run fails if signalling never checks anybody down, so the
  timetable cannot silently drift to something that demonstrates nothing
- **determinism** — two runs of the same scenario agree exactly
- **the YAML fallback** — agrees with PyYAML on every shipped file
- **the interlocking** — points derived correctly, controlled signals held at
  danger without a route, conflicting requests refused with a reason, approach
  locking refusing to take a route from a braking train, and nothing left locked
  at the end of the day
- **sectional release** — asserted from the event log: the points behind S1 are
  released *while* it stands in the loop, and F1 throws them the other way before
  S1 has moved
- **the route request lead is load-bearing** — set it so a train asks for its
  departure route the instant it berths, and the test asserts the fast is then
  refused the road past the loop
- **the ETCS ladder is monotonic** — restraint, journey time and authority length
  must each improve, or at worst hold, at every step up the ladder
- **below capacity the levels converge** — the model must *not* show moving block
  winning on a quiet railway
- **mixed fitment degrades** — a fitted train follows a fitted leader closely, backs
  off from one that cannot confirm its integrity, and backs off further still from
  one that reports nothing at all
- **the interlocking bounds every level** — no ETCS level may be authorised past a
  signal with no route set
- **the braking envelope** — matches the braking curve, grows with reaction time,
  shrinks faster than linearly as the train slows, and is always shorter than a
  block (or the layout would be unsignalable)
- **lineside signals are declared per system** — the view draws lamps or marker
  boards from that, so it is asserted rather than assumed
- **the metro line's constraint is the station, not the block length** — asserted
  from `--check`, so that fixed block failing there cannot be dismissed as a
  badly signalled layout
- **Level 2 must *not* help on the metro** — the scenario's whole claim, pinned so
  a later change cannot quietly erase it
- **moving block has a floor too** — at a 60-second headway it is late as well,
  and the test says so
- **an unfitted unit costs the trains behind it, not itself** — U06 unrestrained
  and on time while U07 is not
- **a declared disturbance actually reaches the train** — a late start must leave
  late, not merely appear late, or the ready lead would silently absorb it
- **the undisturbed baseline really is undisturbed** — checked against the
  undisrupted scenario file, not just against the override, so a leak could not
  hide behind both runs being equally wrong
- **a temporary speed restriction is obeyed in the stretch** — not merely
  reflected in a slower journey — and does not touch the other line, or a run
  outside its window
- **delay decays under moving block and does not under fixed block** — the shape
  of the propagation, asserted train by train
- **the main line is the normal position at a junction** — which road through a
  point is the straight one has to be judged at the far end of each leg, since at
  the point itself both roads are on the same alignment
- **a branch train stops short of a trailing point set against it** — running
  through one is a derailment
- **the junction delay leaves the junction** — a main line train is checked down
  again 10 km further on, behind the branch unit it was delayed by
- **moving block barely helps at a junction** — under 5%, against 23% on the
  intensive corridor, because order is not a separation problem
- **nothing decides who goes first** — asserted, so that the day something does,
  the test fails and has to be rewritten to say what it decided
- **a route with no points on it can still need asking for** — if it crosses
  another line on the level, granting it takes something from someone
- **the cost of a flat junction falls on the line being crossed** — not on the
  train doing the crossing, which is the counterintuitive half
- **and it depends entirely on the phasing** — a second test moves the branch
  service two minutes and asserts the diamond then costs nothing at all, so the
  single-run figure cannot be quoted as *the* cost
- **a misspelled key is refused, with the nearest legal spelling offered** —
  ``max_speed_kph`` used to leave the track at 140 km/h and say nothing
- **every shipped scenario still loads** — the guard that stops the key lists and
  the code that reads them drifting apart
- **the run-time bound really is a bound** — no shipped timetable may be called
  impossible, or the check becomes a false alarm nobody reads
- **a booked platform clash is a conflict, not a fault** — the junction scenario
  is built around one, so it is reported separately and does not warn
- **a connection between roads is divided into blocks** — one 17 km block would
  hold one train, and a connection that costs capacity is worse than one that
  fails
- **the route finder picks by running time, not by block count** — or an 80 km/h
  chord of 11 sections beats a 100 km/h main line of 14 and quietly reroutes a
  whole timetable
- **a crossover forces a block boundary at each end** — or the connection would
  land mid-block with nowhere for its signal to stand
- **the running line stays the normal position** through both of its points
- **a crossover between opposite-running lines builds the two-way stretch** —
  the twin roads, the crossings that police them, and the section direction lock
- **the route finder uses a crossover without being told to** — no timetable
  names one; a slow-line platform to a fast-line platform simply routes that way
- **and the trains that do not need it never touch it**
- **physical separation** — asserted under all six systems, including the three
  where block exclusivity correctly does not apply

A note on the numbers: the fast services arrive about 41 s early against their
booked times. That is not an error — it is the running-time supplement real
timetables carry (about 5% here, which is normal practice).

---

## Roadmap

Milestone 1 is done. What follows, and why in this order — the themes come from
Shift2Rail / Europe's Rail research.

**Phase 2 — make capacity measurable.** Blocking-time theory (setup, sighting,
approach, running, clearing, release per block), the blocking-time stairway and
time–distance (Marey) diagram, UIC 406 compression for consumed capacity, and
KPI export.

**Phase 4 — topology and disturbance.** *Done.* Perturbation injection — late
starts, dwell overruns and temporary speed restrictions, with primary and
knock-on delay measured by difference. And junctions — a branch converging on a
main line through a trailing point and diverging through a facing one, with two
services competing for the same road at Beta.

Diamonds — two lines crossing on the level — are modelled too, derived from the
schematic rather than declared, so a flat junction can be measured against a
grade-separated one.

Crossovers between running lines are in as well, so a train can change lines out
on the plain line rather than only at a station.

What is left over from it is smaller: flank protection, and overlaps switched on
(the mechanism is already in the route table, off by default so its cost can be
measured rather than assumed). Four-aspect signalling, which gives two blocks of
warning and so permits blocks shorter than braking distance. And blocking-time
theory with UIC 406 compression, which is the capacity method these KPIs are a
down payment on.

**Phase 5 — ATO and traffic management.** Both preconditions are now in place:
something to recover from, and somewhere a decision changes the outcome. Nothing in the simulator can currently *decide*
anything: the dispatcher runs the plan as written and the interlocking answers
yes or no. Recovering the metro incident needs a decision — hold a train, skip a
stop, turn one short — and that is what there is now a testbed for.

 ATO over ETCS at GoA2 following a
journey profile, and a TMS doing conflict detection and resolution. That is the
honest home for the "AI scheduling" idea: start with a greedy heuristic
dispatcher as the baseline, add a proper optimiser, and only then consider a
learning agent — with the heuristic as the thing to beat.

### References

- [X2Rail-3 — IP2 advanced signalling and moving block demonstrator](https://cordis.europa.eu/project/id/826141)
- [Capacity evaluation of ERTMS/ETCS Hybrid Level 3 using simulation methods](https://www.sciencedirect.com/science/article/pii/S2210970624000143)
- [ABZ 2018 case study: Hybrid ERTMS/ETCS Level 3](https://link.springer.com/article/10.1007/s10009-020-00562-3)
- [Exploring the ERTMS/ETCS full moving block specification](https://link.springer.com/article/10.1007/s10009-022-00653-3)
- [Conflict detection and resolution for distance-to-go signalling](https://www.tandfonline.com/doi/full/10.1080/23249935.2025.2592225)
- [Evaluation of ATO benefits under real-time rail traffic control](https://ethz.ch/content/dam/ethz/special-interest/baug/ivt/ivt-dam/publications/students/701-800/sa704short.pdf)
- [Europe's Rail — Flagship Areas](https://rail-research.europa.eu/innovation-pillar/flagship-area-6/)
