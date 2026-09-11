# TrainSim

A microscopic, schematic-level railway simulator in standard-library Python, and
the study it was written for: **does virtual coupling actually deliver capacity,
or does something else on the railway bind first?**

Six train control systems are implemented behind one interface and handed the
same railway, the same trains and the same timetable, so a difference between two
runs is the signalling and nothing else. The answer, measured rather than
argued, is on a 70 km circuit with eleven stations:

| | all-green headway | |
|---|---|---|
| fixed block, 3-aspect | 148 s | |
| ETCS Level 2 | 118 s | |
| ETCS Hybrid Level 3 (VSS) | 88 s | ← virtualising the block is worth 30 s |
| ETCS moving block | 78 s | |
| **virtual coupling** | **71 s** | ← coupling the trains is worth 7 s |

Seven variables were swept and none of them moved that seven seconds. Taking a
single station out of a line moved every system by twenty-six
(`scenarios/capacity2`). **The platform binds, and a platform is not a following
distance.**

Deliberately **dependency-free** — the simulator and its schematic view run on a
bare Python 3.7+ install with nothing to `pip install`.

```
python run.py scenarios/ring                    # live schematic
python run.py scenarios/ring --headless         # no window, prints a summary
python run.py scenarios/ring --check            # validate and report the layout
python run.py scenarios/ring --compare          # all six systems, one table
python run.py scenarios/ring --system virtual_coupling

python scenarios/ring/_sweep_headway.py etcs_moving_block   # what it holds
python scenarios/ring/_sweep_express.py etcs_moving_block   # without the platforms
python scenarios/ring/_sweep_convoy.py                      # can a rule build one
python scenarios/ring/_generate_convoy.py 60                # rebuild that flight
python run.py scenarios/ring/scenario-convoy-stopping.yaml --headless
python run.py scenarios/ring/scenario-grade.yaml --compare      # the same circuit, graded
python stats.py scenarios/ring                  # every derived number, with its formula
python run_tests.py                             # 292 tests, ~15 s

python ui_tk.py                                 # desktop front end, nothing to install
python ui_qt.py                                 # the same, on Qt (needs PySide6)
```

**[COMMANDS.md](COMMANDS.md)** is the full command reference. Every scenario
file carries its own header explaining what it measures, what was expected and
what came back — those headers are the study's notebook and are more current
than any summary here.

---

## The finding, in one page

**The gap is real, small and structurally bounded.** Seven seconds on the
stopping service, seven again with every platform taken out of the way (39 s
against 32 s non-stop). Brake rate, adhesion, leader-brake credit, route-request
timing, stopping pattern, fleet mix and pacing — seven sweeps, none of them moved
it. The closed form says why:

```
MB = 3v + v²/2b + 125
VC = 3.5v + v²/2b − v²/2b_credit + 75
```

Credit the leader the brake the follower plans on and the quadratic cancels, so
the saving is linear in speed and independent of brake rate. There is no
parameter to tune it with.

**The convoys were never assembled.** Virtual coupling lets trains run closer.
Nothing in it makes them *get* closer — closing up is a speed manoeuvre, and on a
homogeneous fleet at line speed there is no speed difference to close with. Over
a 30 km leg with no station, not one tick where two trains came within 200 m.

**Give it a speed difference and the benefit appears — and it is much larger
than seven seconds.** A leader capped at 65 km/h on an 80 km/h line, follower
uncapped, non-stop lap. The convoy forms at km 18 and holds to the end:

| | settled gap | closest | ticks inside 200 m |
|---|---|---|---|
| fixed block, 3-aspect | 1211 m | 764 m | 0 |
| ETCS Hybrid Level 3 | 475 m | 330 m | 0 |
| ETCS moving block | 301 m | 247 m | 0 |
| **virtual coupling** | **163 m** | 136 m | 2689 |

46 % closer than moving block, against 9 % on the headway sweep. Not a
contradiction — in a convoy the leader is *moving*, so the brake credit relative
braking rests on is fully available. At a platform the leader is stopping and has
none left to lend.

**An operating rule cannot manufacture that speed difference cheaply.**
`scenario-convoy.yaml` caps every train at 70 km/h and releases it to line speed
once it is within braking distance plus a margin of the train in front — paying
a follower, in line speed, for closing up. It does assemble convoys, at 192 m
against plain virtual coupling's 1053 m. It also never fires below a ~600 m
radius (an incentive that requires proximity cannot create proximity), becomes
"no cap" above ~1500 m, and in the band where it works costs every train 5 % of
its journey — including the train at the front, which can never earn the release
because there is nobody ahead of it to earn it from.

Run the scenario and the mechanism is visible: twelve services booked a minute
apart arrive in pairs seventeen seconds apart, the follower of each pair a
minute early on a plan written at the cap. That flight has to be generated by
`_generate_convoy.py` rather than `_generate_express.py`, because it is the one
timetable here booked at the speed the rule holds a train to, on the one fleet
here fitted with a train-to-train link. Booked at line speed on unfitted stock
it ran as fixed block wearing another name.

`scenario-convoy-stopping.yaml` is the same rule on the circuit's own
twenty-two call lap, and it is the sharper result. A station stop hands the
incentive the speed difference it otherwise has to manufacture — a train
standing thirty seconds is one the follower closes on for free — and the
convoys still do not assemble: twelve services at 60 s arrive strung out at 59
to 64 second intervals, against seventeen second pairs on the non-stop flight
at the same booking. What the follower closes up to is a platform the train in
front has not left, so closing up means standing at a signal rather than
coupling.

**Gradients cost the lap almost nothing and the braking distance a good deal.**
`scenario-grade.yaml` is the circuit with a realistic profile on it — ruling
gradient 15 per thousand, mean 8, summing to zero round the lap because the down
line carries the up line's entries and the builder negates a pair it is asked for
in reverse. A lap with the railway to itself takes 79:12 against the level
railway's 79:09: three seconds in seventy kilometres, because every metre climbed
is given back. What does not cancel is the braking distance. On the steepest fall
the service brake is worth 0.873 m/s² instead of 1.0, stopping from 80 km/h takes
283 m instead of 247, and `--check` reports the signal spacing requirement rising
from 339 m to 378 m — the tightest block margin on the circuit falls from +61 m to
+22 m. At a 300 s booking none of the three systems can be made to care; whether
the graded circuit holds a tighter interval than the level one is a sweep that has
not been run.

**At a junction it buys little.** `tests/railways/junction` runs the same flat
junction under every system and against a flyover control. Moving block gains far
less there than on plain line: a conflicting move has to *clear the points*, and
that is an occupancy, not a following distance.

Which is the general statement:

> **Virtual coupling shortens following distances. It does not shorten
> occupancies. A railway with platforms and junctions in it is limited by
> occupancies.**

---

## The signalling ladder

Every train control system implements one interface, and the kernel knows
nothing else about signalling:

```python
class SignallingSystem:
    def observe(self, train, sim): ...                    # what the driver learns, and when
    def movement_authority(self, train, sim) -> MovementAuthority: ...
```

`MovementAuthority` is *how far may this train go, and how fast*. So the levels
are additions rather than rewrites, and the headway differences between them fall
out of the braking physics instead of being tuned constants.

| system | what ends the authority |
|---|---|
| `fixed_block_3aspect` | the signal protecting the first occupied block |
| `etcs_l1` | the same, but read in the cab at a balise |
| `etcs_l2` | the same block boundary, read continuously — no sighting delay |
| `etcs_hybrid_l3` | a **VSS boundary** — 4 per block here, so 225 m of a 900 m block |
| `etcs_moving_block` | the **actual rear** of the train ahead, less a margin |
| `virtual_coupling` | where the train ahead **will have stopped**, over a radio link |

Conventional signalling models the discreteness explicitly: a driver only learns
the state of the railway when a signal is sighted or passed, so braking for an
occupied block begins at the yellow one block back rather than where braking
would actually need to start. That is precisely the time Level 2 gets back.

`separates_by` distinguishes the two families. Under `"block"` the kernel asserts
block exclusivity; under `"distance"` it does not, because the block is not what
keeps trains apart there — but physical separation is asserted under all six.

**These are behavioural models of the authority each system grants.** They are
not signalling designs and are not validated against any installation.

---

## How it is put together

```
trainsim/core/        the kernel - dynamics, driver, trains, interlocking, points,
                      routes, dispatcher, disruption, and signalling/ (six systems)
trainsim/scenario/    YAML in, railway out - builder, loader, schema, minyaml
trainsim/analysis/    KPIs, per-tick trace, event log
trainsim/viz/         the schematic view, stdlib tkinter

uicore.py             what both front ends share - scenarios, runs, axis scaling
uilang.py             every interface string, English with a Turkish lookup
ui_tk.py              the front end that needs nothing installed
ui_qt.py              the same comparison on Qt, plus the line builder
ui_build.py           the builder page - terrain, fleet, timetable, headway sweep
```

17,600 lines of production Python, 4,900 of tests. The simulator, its schematic
view and `ui_tk.py` have no dependencies at all; `ui_qt.py` is the one part that
asks for a package.

### Motion and authority are two different models

The thing a railway engineer will interrogate first, so it is said plainly.

**Motion** is a force balance: a falling traction curve, Davis resistance,
gradient force, an adhesion cap (μg), and a jerk limit from brake build-up. Not
point-mass kinematics.

**Authority** is planned on a flat quadratic —
`braking_distance(v, rate) + build-up + v·t_react + margin`, with a 25 m margin
and a 2.0 s reaction time lineside, 0 under ATO fitment.

Real railways keep a *performance* model and a *safety* model separate and we do
not. That is the largest single assumption in the study, and it is stated before
any result rather than in a limitations slide at the end.

### The interlocking was making moving block behave like fixed block

Worth recording because it was invisible for a long time and the fix is not
obvious.

An authority is capped at the first controlled signal ahead with no route set —
correctly, since no ETCS level overrides an interlocking. But the interlocking
refused a route into an occupied block and held each route until its train had
left the block entirely. So a follower's route stopped at the signal behind
whatever block the train ahead was standing in, and its authority stopped there
too. The rear of the train ahead never entered into it. **Moving block was
running to block boundaries with extra steps.**

Under `separates_by = "distance"` the interlocking now sets a route into an
occupied block, and gives the route back as soon as the train is on it and clear
of its points rather than when it has left the block. Crossings are untouched:
two trains meeting on a flat junction is not a following move, and no separation
model makes it one.

Points are unchanged — still locked to a position, still released sectionally.

### What else is modelled

Sectional release, approach locking, facing and trailing points, overlaps (off by
default, so their cost can be measured rather than assumed), crossovers between
running lines, diamonds derived from the drawing rather than declared,
bidirectional working with a section direction lock, route queueing, and
disruption injection — late starts, dwell overruns and temporary speed
restrictions, with knock-on delay measured by difference against an undisturbed
baseline.

**Nothing decides anything.** The dispatcher runs the plan as written and the
interlocking answers yes or no. There is no traffic regulation: routes go to
whoever asks first, subject to one rule — the train nearest the signal wins. On
single-line working that means one direction batches through and then the other,
which is a real arrangement under the worst possible regulation. A test asserts
that nothing decides, so the day something does, it fails and has to be rewritten
to say what it decided.

---

## The railways

### `scenarios/` — the study

| | what it is | what it measured |
|---|---|---|
| **ring** | 70 km circuit, 11 stations, 22 calls a lap | the ladder, and everything that could not move it |
| capacity | 60 km corridor, 3 stations, the base | the comparison the others are read against |
| capacity2 | capacity with one station removed | a station costs 26 s under every system alike |
| depotline | single-track between two depots | fixed block on a line with no room to pass |
| express | capacity run non-stop | superseded by the ring's own non-stop lap |
| twoway | an up and a down line, and single-line working | what the connections cost when one road is closed |

**A circuit, because out-and-back railways stop measuring signalling** past a
certain interval and start measuring the terminus despatch sequence — which no
signalling system changes. A ring has no ends.

The ring carries its own experiment drawings, one per question, so the other
scenarios do not load routes they never book:

- `infrastructure.yaml` — the circuit
- `infrastructure-merge.yaml` — a branch joining at Akyurt 1. A flat junction,
  but at a *station*, so what binds there is a platform road rather than the
  junction: read the header before quoting anything from it.

and its own experiment scripts — `_sweep_headway.py`, `_sweep_express.py`,
`_sweep_convoy.py`, `_sweep_timestep.py`, each with its results recorded in its
docstring.

### `tests/railways/` — fixtures

`corridor3`, `metro`, `junction`, `fourtrack`. These exist to be tested against.
**Nothing in the study is quoted from them.**

```
python run.py tests/railways/corridor3 --compare
python run.py tests/railways/junction --check     # a real junction's route table
```

---

## Scenario files

Written the way an engineer would describe a line — stations at chainages, tracks
that serve them, platforms, block lengths — and expanded by `scenario/builder.py`
into segments, blocks, signals, points and routes.

```yaml
stations:
  - {id: BETA, name: Beta, km: 12.0}

tracks:
  - id: UP
    direction: up
    serves: [ALPHA, BETA, GAMMA]
    block_length_m: 2000
    block_lengths:                                        # per-stretch override
      - {from: ALPHA, to: BETA, block_length_m: 1500}
    speed_limits:                                         # permanent, by km
      - {from_km: 10.0, to_km: 10.9, max_speed_kmh: 50}

platforms:
  - {id: BETA_3, station: BETA, track: UP, length_m: 220,
     max_speed_kmh: 80, y_offset: -0.34, berth: centre}   # the loop road

crossovers:
  - {id: XO_BETA, from: UP, to: DN, km: 13.5, length_m: 400, type: scissors}
  - {id: DIA_1,   from: BRANCH_UP, to: DN, km: 26.6, type: diamond}
```

Parallel platform roads are several segments sharing a pair of nodes — no switch
model is needed for them to be safe, since each road is its own block and the
approach block ahead of the divergence holds one train.

`speed_limits` are *infrastructure*, not disruptions: a curve is part of the
railway, and putting it in `disruptions:` would report it as something that went
wrong. A misspelled key is refused with the nearest legal spelling offered —
`max_speed_kph` used to leave a track at its default and say nothing.

PyYAML is used when present; `scenario/minyaml.py` is a stdlib fallback for the
subset these files use, and a test asserts the two agree on every shipped file.

---

## Verification

`python run_tests.py` — **289 tests, about 15 seconds**, parallel by default
(`--serial` and `-v` to escape, or name modules to run a subset).

The tests worth knowing about are the ones that stop a result being quietly
erased:

- **the ladder is monotonic** — restraint, journey time and authority length must
  each improve, or at worst hold, at every step up
- **below capacity the levels converge** — the model must *not* show moving block
  winning on a quiet railway
- **Level 2 must not help on the metro** — that scenario's whole claim, pinned
- **the restraint check must be able to fail** — if signalling never checks
  anybody down, the run fails, so a timetable cannot drift to something that
  demonstrates nothing
- **physical separation** under all six systems, including the three where block
  exclusivity correctly does not apply — and the separation check is itself
  tested against hand-placed overlapping trains, so it can be seen to fail
- **nothing decides who goes first** — asserted, so the day something does the
  test fails
- **the cost of a flat junction falls on the line being crossed**, not on the
  train doing the crossing — and a second test moves the branch two minutes and
  asserts the diamond then costs nothing, so a single-run figure cannot be quoted
  as *the* cost
- **a flyover changes nothing but the conflict** — same blocks, signals and
  routes, which is what makes the junction comparison controlled rather than two
  railways that merely resemble each other
- **every shipped scenario still loads**, and the run-time bound really is a bound
- **determinism** — two runs of the same scenario agree exactly

Fast services arrive about 41 s early against their booked times. That is not an
error: it is the running-time supplement real timetables carry, about 5 % here.

---

## What this does not establish

- **No field validation.** The model is calibrated against nothing. Every figure
  here is internal to it.
- **A performance model is used where a real railway would use a safety model.**
- **The V2V link is assumed never to drop a packet.** `v2v_latency_s` charges
  virtual coupling 0.5 s of stale news on a *working* link, every tick. There is
  no loss and no link-loss event: `_linked()` reads static fitment flags that
  nothing mutates during a run, so `fallback_margin_m` is what an *unfitted*
  train gets rather than what a fitted one falls back to. A fitted train never
  makes the transition and never pays the detection timeout before it. That is
  the assumption virtual coupling's safety case leans on hardest here.
- **Four of IEEE 1698 Annex E's ten braking-distance components** are implemented;
  the rest are lumped into a 25 m margin.
- **The timestep is 1.0 s**, and a check shorter than one tick is never sampled.
  Re-run at 0.5 s the boundaries are about 2 s wider (all-green 80/73 rather than
  78/71) — both systems move together and the gap does not.
- **No traffic regulation and no driver advisory.** Nothing holds a train to let
  another run.
- **No convoy manoeuvre.** A closing differential — the leader held back, or the
  follower given headroom — would be a change to the signalling system, not to a
  scenario. `VirtualCoupling.convoy_of` is the hook and is currently unused.
- **A convoy is never booked over a junction as one movement.** The interlocking
  holds crossings exclusive under every system, so the one mechanism with room
  for a large number is untested. That is an *interlocking* change, not a
  signalling one.

`scenarios/ring/PLANNED.md` records the experiments that are designed but not
built, with the probe numbers behind them.

---

## References

- [X2Rail-3 — IP2 advanced signalling and moving block demonstrator](https://cordis.europa.eu/project/id/826141)
- [Capacity evaluation of ERTMS/ETCS Hybrid Level 3 using simulation methods](https://www.sciencedirect.com/science/article/pii/S2210970624000143)
- [ABZ 2018 case study: Hybrid ERTMS/ETCS Level 3](https://link.springer.com/article/10.1007/s10009-020-00562-3)
- [Exploring the ERTMS/ETCS full moving block specification](https://link.springer.com/article/10.1007/s10009-022-00653-3)
- [Conflict detection and resolution for distance-to-go signalling](https://www.tandfonline.com/doi/full/10.1080/23249935.2025.2592225)
- [Evaluation of ATO benefits under real-time rail traffic control](https://ethz.ch/content/dam/ethz/special-interest/baug/ivt/ivt-dam/publications/students/701-800/sa704short.pdf)
- [Europe's Rail — Flagship Areas](https://rail-research.europa.eu/innovation-pillar/flagship-area-6/)

Repository `alican12alicanexe-alt/asil1` — 125 commits, 26 August – 7 September
2026.
