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
| `--events` | After a headless run, print the full event log — every route set, refused, released, every arrival and departure. |
| `--duration N` | Override the run length in simulated seconds. |
| `--speed N` | Simulated seconds per real second in the view. `--speed 1` is real time; the scenarios default to 20–30. |
| `--strict` | Raise on a block-exclusivity violation instead of logging it. Use it when changing the kernel: it turns a silent wrong answer into a stack trace. |

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
python scenarios/depotline/_sweep_headway.py            depotline: 210 s, 17.1 tph
python scenarios/depotline/_sweep_headway.py etcs_l2    under any other system
```

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
