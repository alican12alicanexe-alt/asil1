# Commands

Everything runs through `run.py`. No installation, no arguments beyond a scenario
path, and nothing here needs the internet.

```
python run.py <scenario> [options]
```

`<scenario>` is either a **directory** (which uses its `scenario.yaml`) or a
specific **scenario file**, so `scenarios/metro` and
`scenarios/metro/scenario-60.yaml` are both valid.

---

## The five modes

| command | what it does |
|---|---|
| `python run.py <scenario>` | Opens the live schematic. The default. |
| `python run.py <scenario> --headless` | Runs it with no window and prints a summary plus a per-service arrivals table. This is the one to use for numbers. |
| `python run.py <scenario> --check` | Loads and validates without running: layout, block lengths against braking distance, whether the *timetable* is physically runnable, booked platform conflicts, the route table, points, and any level crossings. Exits non-zero if the layout could not be signalled or the plan cannot be run. |
| `python run.py <scenario> --compare` | Runs the same timetable under every signalling system and tabulates them. |
| `python run.py <scenario> --propagation` | Runs the scenario twice, with and without its declared disruptions, and reports what the incident cost. Needs a scenario with a `disruptions:` block. |

## Options

| option | what it does |
|---|---|
| `--system NAME` | Override the signalling system for this run. |
| `--compare A B` | Compare only the named systems instead of the whole ladder. |
| `--leader-brake RATE` | Virtual coupling only: `emergency` (default) or `service` — which brake the follower credits the train in front with. |
| `--as-fitted` | Run every system on the equipment and driver the timetable declares, instead of fitting both to the system being run. |
| `--events` | After a headless run, print the full event log — every route set, refused, released, every arrival and departure. |
| `--log FILE` | Record a time-based trace of every train to a spreadsheet — `.xlsx`, `.csv` or `.tsv`, picked from the extension. |
| `--log-every N` | Sample the trace every N simulated seconds instead of every timestep. |
| `--duration N` | Override the run length in simulated seconds. |
| `--speed N` | Simulated seconds per real second in the view. `--speed 1` is real time; the scenarios default to 20–30. |
| `--strict` | Raise on a block-exclusivity violation instead of logging it. Use it when changing the kernel: it turns a silent wrong answer into a stack trace. |

## The run trace

The summary says how a run came out; `--log` says how it got there. One row per
train per sample:

```
python run.py scenarios/capacity --headless --log run.xlsx --log-every 5
python run.py scenarios/capacity --system etcs_moving_block --log mb.csv
```

| column | |
|---|---|
| `time_s`, `clock` | simulated time, and the same as a wall clock |
| `train`, `state` | which unit, and whether it is running or dwelling |
| `km`, `chainage_m` | where it is on its path |
| `speed_kmh`, `accel_ms2` | current speed, and the acceleration actually applied that tick — after traction limits, resistance and the jerk limit |
| `target_kmh`, `limit_kmh` | what the driver was aiming at, and the line speed under the train |
| `grade_permille` | gradient at the front |
| `authority_m` | distance left in the movement authority |
| `service_brake_m`, `emergency_brake_m` | room needed to stop from the current speed at each rate |
| `ahead`, `gap_m`, `headway_s` | the train in front, the gap to its rear, and that gap at the current speed |
| `delay_s`, `next_stop` | how late, and where it is going next |
| `reason` | what the authority was limited by, in the signalling system's own words |

Comparing `gap_m` against `service_brake_m` is the quickest way to see a
signalling system's behaviour: under moving block the gap tracks the braking
distance, under virtual coupling it sits inside it, and under fixed block it
steps between block boundaries.

The recorder only reads state after a tick has finished, so a traced run gives
exactly the same results as an untraced one.

The `.xlsx` writer is built in — the format is a zip of XML parts, and writing
those is smaller than taking on a spreadsheet dependency for a debug log.

## Graphing a run

`graph.py` runs a scenario and draws what happened, as SVG:

```
python graph.py --system virtual_coupling U03
python graph.py --system virtual_coupling U03 U08
python graph.py scenarios/express/scenario-tight.yaml \
                --system etcs_moving_block U03 U08 -o mb.svg
python graph.py --system virtual_coupling            # fleet mean only
```

A first argument that is a path is the scenario, as in `run.py`; without one it
runs `scenarios/express`. `--scenario PATH` does the same thing if you prefer
it named.

Name the trains you want and they are drawn individually; every panel also
carries the fleet mean over all services in grey, so a train reads against what
the rest of the railway was doing in the same place. Six panels: speed against
distance and against time, the gap to the train ahead, time headway, and the
fleet mean speed and gap on their own.

The separation panel is the one a signalling comparison lives in. The solid line
is the gap to the rear of the train ahead; the dashed line beneath it is the
distance that train needs to stop from its current speed. Under moving block the
gap tracks the dashed line — that *is* the authority. Under virtual coupling it
sits below it, because the follower may plan on the leader stopping too.

| option | |
|---|---|
| `--scenario PATH` | which scenario, if not given as the first argument (default `scenarios/express`) |
| `--system NAME` | signalling system; the fleet is fitted for it, as `run.py` does |
| `--as-fitted` | do not re-equip the fleet or change the driver |
| `--every N` | trace sampling interval in simulated seconds (default 2) |
| `--bin KM` | bin width for the fleet means (default 0.5 km) |
| `-o FILE` | output file (default `graph.svg`) |
| `--log FILE` | also write the underlying trace as `.xlsx`/`.csv` |

It prints a summary table too — journey time, mean and max speed, minimum and
mean gap, minimum time headway per train.

The graphs come from the same per-tick trace `--log` writes, so a picture and a
spreadsheet of the same run agree by construction. `_plot_curves.py` draws the
stock's acceleration and braking envelope through the same renderer.

## The fleet is fitted to the system

Name a system with `--system` or `--compare` and the fleet is re-equipped for it
before the run — ETCS level, train integrity monitoring, V2V radio link — from
the `FITMENT` table in `trainsim/core/signalling`. The CLI says on stderr what
it changed:

```
$ python run.py scenarios/express --headless --system virtual_coupling
fitted EMU for virtual_coupling: ETCS l3, with integrity report, with radio link
```

This matters more than it looks. A signalling system is only worth what the
train can use: moving block behind a train that cannot report its integrity
falls back to block granularity, and virtual coupling without the radio link
falls back to moving block. Run the whole ladder over one unfitted fleet and
every system reports the same fallback under a different name — quietly, because
every run completes and the table looks reasonable.

The driver goes the same way. Lineside signalling and ETCS Levels 1 and 2 are
read by a person and carry a two-second reaction time; Level 3 and virtual
coupling are driven by ATO and carry none. That is not a claim of instant
response — the control cycle is the simulation timestep, the radio delay is
`v2v_latency_s`, and the brake takes `brake_buildup_s` to come on. The reaction
time is the human, and there isn't one.

`--as-fitted` turns both off and answers the other question instead: what is
each system worth *to the fleet this timetable declares*.

| system | ETCS | integrity report | radio link |
|---|---|---|---|
| `fixed_block_3aspect` | — | no | no |
| `etcs_l1` | L1 | no | no |
| `etcs_l2` | L2 | no | no |
| `etcs_hybrid_l3` | L3 | yes | no |
| `etcs_moving_block` | L3 | yes | no |
| `virtual_coupling` | L3 | yes | yes |

## Which brake the leader is credited with

Under virtual coupling the follower plans to stop where the train in front will
stop, so how much room it needs depends on how hard it assumes that train can
brake. `--leader-brake` picks the assumption:

```
python run.py scenarios/express --system virtual_coupling --leader-brake service
python scenarios/express/_sweep_headway.py virtual_coupling service
```

- **`emergency`** (default) — the leader may make a full emergency application
  at any moment. The follower absorbs the whole difference between the two
  rates, permanently. Safe against anything the train can do to itself.
- **`service`** — the convoy braking rule of the literature: the V2V layer tells
  the leader what is coupled behind it and the whole convoy brakes at the
  weakest rate in it, so the leader may not out-brake its follower.

The second nearly halves the separation — on the express railway a follower
settles 124 m behind a slower train instead of 211 m, against moving block's
427 m. It also moves that railway's headway by one second, because there the
constraint is the depot rather than the following distance. Both facts are
worth having.

This model does not enforce the convoy rule and does not pretend to: nothing in
it ever demands more than a service application, so there is no behaviour for
the constraint to bind on. `service` is a declared assumption about the degraded
case, not a mechanism — see `VirtualCoupling._run_on_m`.

## Signalling systems

Names for `--system` and `--compare`, oldest technology first:

```
fixed_block_3aspect     conventional lineside signalling, red/yellow/green
etcs_l1                 balise at each signal, lineside overlay
etcs_l2                 continuous radio authority, fixed-block detection
etcs_hybrid_l3          virtual sub-sections over trackside detection
etcs_moving_block       full Level 3, authority to the rear of the train ahead
```

## Headway

`--check` reports the **all-green headway**: the closest two trains may follow
each other with the second one never seeing anything but a green signal. It is
the interval a timetable is written to, because braking for a yellow means the
plan has already failed.

```
all-green headway = (2 block sections + train length + sighting distance) / v
```

Two sections, because a signal shows green only when the section beyond the one
it protects is clear as well, so a train uses up two sections rather than the one
it is standing in.

That is what the signal spacing allows. What the railway actually holds is
usually less, because trains stand at platforms and reoccupation binds before
block spacing does. To measure it, sweep the flight:

```
python scenarios/depotline/_sweep_headway.py            depotline: 223 s, 16.1 tph
python scenarios/depotline/_sweep_headway.py etcs_l2    under any other system
python scenarios/capacity/_sweep_headway.py             capacity: 259 s, 13.9 tph each way
python scenarios/capacity/_sweep_headway.py virtual_coupling
python scenarios/twoway/sweep.py                        all three systems, up trains only
```

Each sweep runs a coarse list of intervals and then closes in. The coarse rows
only bracket the answer — clean at 135 s and checked at 120 s says nothing about
128 s — so it halves the bracket until one second separates the two ends, and
prints every interval it tried on the way. Four or five extra runs, rather than
the fifteen a second-by-second sweep would take.

Two figures come out of it. The **all-green headway** is the closest these trains
follow each other without any of them ever being checked by a signal — a property
of the railway, and the one to quote when comparing signalling systems. The
**keeps-time headway** is the closest they follow each other with every train
still making its booked arrival, and it is a lot tighter: on `capacity`, virtual
coupling is all-green at 121 s and still punctual at 68 s. A run anywhere between
the two shows every train on time and looks entirely normal to watch, and is
genuinely being held down by the signalling the whole way. Both are true.

Three systems are compared: fixed block, moving block, virtual coupling. Both
capacity sweeps declare the fitment per system and give each one what it needs
and nothing more — moving block the integrity report, so it can follow the rear
of the train in front; virtual coupling the radio link on top of that, so it can
plan to stop where the leader will stop.

`scenarios/capacity` is the scenario built for that sweep: one stock type, one
calling pattern, evenly spaced stations and a flat line speed, so that running it
under each system in turn measures the system and nothing else.

Both sweeps fit the train to the system as well as switching the system. That is
not a detail: full moving block falls back to block granularity unless the train
in front reports its integrity, and virtual coupling needs both trains talking to
each other, so a sweep run on one unfitted unit reports the same fallback under
three different names. `--compare` does *not* do this — it runs the scenario's
own timetable, so on a scenario with an unfitted fleet its table is the value of
each system to that fleet. Quote the sweeps for capacity.

## Tests

```
python run_tests.py                 all 182, stdlib unittest, no pytest needed
cd tests && python -m unittest test_junction -v      one file, verbose
```

---

## The scenarios

### `scenarios/corridor3` — a main line

30 km, three stations, a loop at Beta, mixed fast and stopping traffic.

```
python run.py scenarios/corridor3                             watch the overtake
python run.py scenarios/corridor3/scenario-intensive.yaml --compare
python run.py scenarios/corridor3/scenario-disrupted.yaml --propagation
```

- `scenario.yaml` — nine services, below capacity. All ETCS levels converge here.
- `scenario-intensive.yaml` — twelve services at 90 s. This is the one that
  separates the levels: moving block saves 23%.
- `scenario-disrupted.yaml` — the 07:00 stopper stands four minutes over at Beta.

### `scenarios/metro` — an urban line

12 km, six stations, no loops, nothing to overtake.

```
python run.py scenarios/metro --compare              Level 2 saves one second
python run.py scenarios/metro --system fixed_block_3aspect      watch it bunch
python run.py scenarios/metro/scenario-disrupted.yaml --propagation
```

- `scenario.yaml` — 75 s headway. Moving block delivers it exactly; fixed block
  settles at 89 s and loses a train an hour.
- `scenario-60.yaml` — 60 s, which nothing delivers. Moving block has a floor too.
- `scenario-mixed.yaml` — two units without integrity monitoring.
- `scenario-disrupted.yaml` — one door held 90 s at Central.

### `scenarios/junction` — converging traffic

A branch meeting a double-track main line at Beta.

```
python run.py scenarios/junction --check                       the route table
python run.py scenarios/junction --headless --events | grep route_refused
python run.py scenarios/junction/scenario-flat.yaml --check    the diamonds
```

- `scenario.yaml` — the branch beside the up main, nothing crosses anything.
- `scenario-flat.yaml` — the branch beyond the down main, so it crosses it.
- `scenario-flyover.yaml` — the same layout grade separated. The control run.

### `scenarios/fourtrack` — trains changing lines

Up fast, up slow, down slow, down fast, with a crossover between each pair.

```
python run.py scenarios/fourtrack                        watch the semi-fast cross
python run.py scenarios/fourtrack --check                the crossovers and points
python run.py scenarios/fourtrack --headless --events | grep XO_UP
```

Beta has platforms on the slow lines only, so a semi-fast has to call there on
the slow line and then cross to the fast line at km 17 to run on. That move is a
flat junction in the middle of a fast line, and it behaves like one.

### `scenarios/capacity` — the comparison base

Sixty kilometres, a line each way, three stations between two depots. Every
train the same unit, calling everywhere, so the only thing that can move a
number between two runs is the signalling.

```
python run.py scenarios/capacity --compare
python scenarios/capacity/_sweep_headway.py virtual_coupling
```

### `scenarios/express` — the same railway, non-stop

The capacity layout with three things changed: nothing calls anywhere, the
speed profile is long runs at 120 with two gentle easings every twelve
kilometres instead of a new limit every 650 m, and the crossovers no longer
brace the plain line — a crossover's 40 applies to the train that takes it.

```
python run.py scenarios/express --headless
python run.py scenarios/express --headless --system virtual_coupling --log vc.xlsx
python scenarios/express/_sweep_headway.py virtual_coupling
python graph.py --scenario scenarios/express/scenario-tight.yaml \
                --system virtual_coupling U03 U08
```

`scenario-tight.yaml` is the same flight booked at 25 s instead of 240 s —
below what moving block holds and above what virtual coupling holds, so the two
systems draw visibly different pictures. At the default 240 s the trains are
seven kilometres apart and the separation panel says nothing.

It exists because the base scenario cannot separate the two cab systems: every
train there calls at every station, so past about 120 s the binding constraint
is a platform road and closing the gap between trains buys nothing. Take the
stops out and keep the trains fast and it does separate — keeping time, virtual
coupling goes from 8 % better than moving block to 26 %.

Read the two together. The base is the lower end of what relative-braking
separation is worth and this is the upper end; a real service is in between.

---

## In the view

| key | action |
|---|---|
| `space` | pause / resume |
| `.` | single step while paused |
| `b` | braking envelopes and authority markers on / off |
| `+` / `-` | faster / slower |
| `←` / `→` | pan |
| `z` / `x` | zoom in / out |
| `0` | reset the view |
| `q`, `Esc` | quit |

The header line says what kind of railway you are looking at — lineside signals
or cab signalling, block separation or distance separation, and which routes are
currently set. The table underneath says what is governing each train:
`line speed`, `obeying caution`, `signal at danger`, `station stop BETA`.

---

## Scenario-specific scripts

These are not part of the simulator; they regenerate or study one scenario.

```
python scenarios/metro/_generate_timetables.py     rebuild the metro timetables
python scenarios/junction/_generate_timetable.py   rebuild the junction timetable
python scenarios/junction/_sweep_phase.py          what the diamond costs, swept
                                                   across every branch phasing
```

The timetables are **derived data**: each service is booked on the run times a
single unimpeded train achieves, so the plan is workable in isolation and any
delay a run shows is the railway rather than the plan. Re-run the generator after
changing a dwell, a chainage or the rolling stock, or the booked times go stale.

---

## Reading the output

**`--headless` summary.** `violations: 0` is the one to check first — it means no
two trains were ever in the same block (under fixed block) and no train ever
passed the rear of another (under any system). `worst arrival` uses the usual
railway 30-second tolerance, so `on time` means within half a minute.

**`--check` output, in three parts.** *Signal spacing* is about the railway: is
every block long enough to brake in from line speed. *Timetable* is about the
plan: is any leg booked faster than the train can physically run it, and is any
call booked out of order. *Booked platform conflicts* are neither - they are two
trains booked to want the same platform road, which is a conflict somebody has to
resolve rather than a mistake. The dispatcher resolves it today by holding the
second train out, so it has always shown up as unexplained delay; now it is said
before the run instead of inferred after it.

Unknown keys are refused outright. `max_speed_kph` is not `max_speed_kmh`, and it
used to leave the track at its 140 km/h default without a word.

**`--compare` table.**

```
signalling               journey   vs base restrained  min hdwy   auth m   done
fixed_block_3aspect        17:32         -      5156s       90s     1363  12/12
etcs_moving_block          13:32     -4:00        54s       90s     3283  12/12
```

- `journey` — mean origin to destination over all services.
- `restrained` — seconds trains spent held down by the signalling rather than by
  line speed or a booked stop. **This is the direct cost of the train control
  system**, and the number that should fall as the level goes up.
- `auth m` — mean length of movement authority granted. Fixed block can only ever
  grant to a block boundary; moving block grants to the train in front. Watching
  this grow is watching the mechanism rather than the outcome.
- `min hdwy` — shortest gap between two trains entering the same block. Not a
  design figure; it is what this timetable happened to achieve.

**`--propagation` report.** `primary` is time lost by the train the incident
happened to; `knock-on` is time lost by trains it merely got in the way of.
The ratio says how much the railway amplifies its own incidents. Read it beside
the `on the day` column: knock-on is measured against each system's *own* clean
run, so a system that was already slow has less left to lose and can score well
while delivering the worse railway.
