"""Longitudinal dynamics: what actually limits a train's acceleration.

Until now a train accelerated at ``max_accel`` from a stand right up to line
speed, and braked at ``service_brake`` regardless of anything. Nothing opposed
it: no drag, no rolling resistance, no gravity. A 200 m EMU reached 140 km/h in
43 seconds and 840 metres, which is roughly twice as good as any real one
manages, and it made every run time - and therefore every headway - optimistic
in a way no amount of signalling detail could compensate for.

This module replaces that with the force balance a real train obeys:

    m_eff * a  =  F_traction(v)  -  R(v)  -  m * g * sin(theta)

Three terms, each of which limits a different part of the journey:

**Traction** is flat then falling. Below *base speed* the motors are limited by
current and produce a constant tractive effort; above it they are limited by
power, so effort falls as ``P / v`` and acceleration with it. This is the term
that matters most here: it is why a train covers the last 20 km/h of its run-up
in about as much distance as the first 80, and why a timetable planner cares
about how far a train is from a stop rather than just how fast the line is.

**Resistance** is the Davis equation, ``R = A + Bv + Cv^2``: journal and rolling
resistance that barely varies, a flange and track term linear in speed, and
aerodynamic drag that dominates everything above about 100 km/h. At 140 km/h it
is worth some 30 N per tonne - small against traction, but it is what makes a
coasting train slow down and it is why the last few km/h take so long to gain.

**Gradient** is ``g * sin(theta)``, near enough ``g * grade / 1000`` for the
gradients railways are built to. A 10 permille climb costs 0.098 m/s2, which is
a tenth of an EMU's starting acceleration and more than three times its air
drag at line speed - gravity is by a distance the biggest force on this list,
which is why gradient profiles are the first thing a real run-time calculation
asks for.

Two further limits are separate from the force balance because they are limits
on what the *brake* can do rather than on what the train can pull:

**Adhesion.** No brake can retard the train harder than the wheel-rail contact
will bear, ``mu * g``. On dry rail mu is around 0.3, giving 2.9 m/s2 - well
above any service rate here, which is the point: it is a ceiling that only bites
if a scenario asks for a brake rate that could not be delivered on real rail.

**Build-up.** A brake demand is not a brake application. Air has to be moved,
so the retardation ramps in over a couple of seconds rather than appearing at
once, and the same is true (for comfort rather than for physics) of a traction
demand. Both are modelled as one limit on how fast the achieved acceleration may
change - jerk - which is also the quantity passenger comfort standards are
written in terms of.

Everything here is a pure function of the rolling stock, the speed and the
gradient, so the driver model can ask the same questions when it decides *when*
to brake that the train answers when it moves.
"""

#: Standard gravity, m/s2.
G = 9.80665

#: Where the traction curve breaks, as a fraction of the train's maximum speed,
#: when the scenario does not give a power rating. 0.4 puts base speed at 56
#: km/h for a 140 km/h EMU and 36 km/h for a 90 km/h metro unit, which is where
#: real stock of each kind changes over from constant effort to constant power.
BASE_SPEED_FRACTION = 0.4

#: Below this speed the constant-power branch is meaningless (it goes to
#: infinity at a stand), so the starting effort applies.
_CREEP_MS = 0.5


#: Davis coefficients used when a scenario gives none, in SI with speed in m/s.
#: ``A`` and ``B`` scale with mass because journal, rolling and flange
#: resistance are a matter of how much weight is on the rail; ``C`` scales with
#: length rather than mass because drag is a matter of how much air the train
#: has to push and drag along its sides. A 200 m, 360 t EMU comes out at about
#: 30 N per tonne at 140 km/h and a 120 m metro unit at 17 N per tonne at 90,
#: both of which are where measured stock of that kind sits.
DAVIS_A_N_PER_T = 6.5
DAVIS_B_N_PER_MS_PER_T = 0.13
DAVIS_C_N_PER_MS2_BASE = 1.1
DAVIS_C_N_PER_MS2_PER_M = 0.022

#: Tonnes per metre of train when the scenario does not weigh it. A 23 m
#: passenger vehicle of 40-50 t is the usual shape of the thing.
MASS_T_PER_M = 1.8


def default_davis(mass_t: float, length_m: float):
    """``(A, B, C)`` for a train of this weight and length."""
    return (
        DAVIS_A_N_PER_T * mass_t,
        DAVIS_B_N_PER_MS_PER_T * mass_t,
        DAVIS_C_N_PER_MS2_BASE + DAVIS_C_N_PER_MS2_PER_M * length_m,
    )


# ------------------------------------------------------------------------ mass

def effective_mass_kg(stock) -> float:
    """Inertial mass: the static mass plus the rotating parts' share.

    Wheels, axles, gearboxes and motor armatures have to be spun up as well as
    moved along, and they resist as if the train were some 8% heavier. Railway
    practice calls it the rotating mass factor; ignoring it overstates
    acceleration by about the same 8%.
    """
    return stock.mass_kg * (1.0 + stock.rotating_mass_pct / 100.0)


# -------------------------------------------------------------------- traction

def tractive_effort_n(stock, speed_ms: float) -> float:
    """Effort at the wheel rim, N: flat below base speed, ``P / v`` above it."""
    starting = stock.starting_effort_n
    if speed_ms <= _CREEP_MS:
        return starting
    return min(starting, stock.power_w / speed_ms)


def traction_accel(stock, speed_ms: float) -> float:
    """Acceleration available from traction alone, before resistance."""
    return tractive_effort_n(stock, speed_ms) / effective_mass_kg(stock)


def base_speed_ms(stock) -> float:
    """Where constant effort gives way to constant power."""
    if stock.starting_effort_n <= 0.0:
        return 0.0
    return stock.power_w / stock.starting_effort_n


# ------------------------------------------------------------------ resistance

def resistance_n(stock, speed_ms: float) -> float:
    """Davis running resistance, N, at ``speed_ms``."""
    speed = abs(speed_ms)
    return (stock.davis_a_n
            + stock.davis_b_n_per_ms * speed
            + stock.davis_c_n_per_ms2 * speed * speed)


def resistance_accel(stock, speed_ms: float) -> float:
    """Retardation from running resistance, m/s2, always positive."""
    return resistance_n(stock, speed_ms) / effective_mass_kg(stock)


def grade_accel(stock, grade_permille: float) -> float:
    """Retardation from gravity, m/s2: positive uphill, negative downhill.

    Gravity acts on the static mass but is resisted by the inertia of the
    rotating parts too, hence the effective mass in the denominator.
    """
    if not grade_permille:
        return 0.0
    return (G * (grade_permille / 1000.0)
            * stock.mass_kg / effective_mass_kg(stock))


# ---------------------------------------------------------------------- braking

def adhesion_limit(stock) -> float:
    """The hardest retardation the rail will accept, m/s2."""
    return stock.adhesion * G


def brake_rate(stock, emergency: bool = False) -> float:
    """The retardation the brake itself delivers, capped by adhesion."""
    demanded = stock.emergency_brake if emergency else stock.service_brake
    return min(demanded, adhesion_limit(stock))


def braking_rate_on_grade(stock, grade_permille: float,
                          emergency: bool = False) -> float:
    """Net retardation available on a gradient, for the driver's braking curve.

    Deliberately ignores running resistance, which also helps a braking train:
    a braking curve has to hold when the train is light, clean and running into
    a tailwind, and none of those is true of the Davis coefficients. Gravity is
    not optional in the same way, so a falling gradient is counted in full.
    """
    rate = brake_rate(stock, emergency) + grade_accel(stock, grade_permille)
    #: Never let a curve be computed against a rate at or below zero - a train
    #: on a 1-in-10 would have an infinite braking distance, and no railway
    #: worth simulating is built like that.
    return max(0.05, rate)


def brake_buildup_distance_m(stock, speed_ms: float) -> float:
    """Distance lost while the brake builds up from demand to full rate.

    Treated the way ERTMS treats it: an equivalent time, half the build-up,
    during which the train is taken to run on unretarded. It is what the driver
    adds to the distance it thinks it needs, and it is why braking starts
    slightly earlier than the textbook curve says.
    """
    return max(0.0, speed_ms) * stock.brake_buildup_s * 0.5


# ------------------------------------------------------------------- resolution

def jerk_limit_ms3(stock) -> float:
    """How fast the achieved acceleration may change, m/s3.

    Derived from the brake build-up time rather than declared separately: a
    brake that reaches its full rate in 2 s is one whose retardation may change
    by ``service_brake / 2`` each second, and traction is held to the same
    figure for want of a better one - it is the right order for the notching
    and jerk limits real traction control applies.
    """
    if stock.brake_buildup_s <= 0.0:
        return float("inf")
    return stock.service_brake / stock.brake_buildup_s


def achievable_accel(stock, speed_ms: float, demanded: float,
                     grade_permille: float = 0.0, previous_accel: float = 0.0,
                     dt: float = 1.0, immediate: bool = False) -> float:
    """What the train actually does when the driver asks for ``demanded``.

    The driver asks for a *net* acceleration - it is closing a loop on speed and
    does not know or care which forces get it there. This function answers with
    what the train can deliver: traction can only give so much at this speed,
    the brake can only give so much on this rail, gravity and drag are there
    whether anyone asked for them, and neither can change instantly.

    ``immediate`` skips the jerk limit for the tick in which the train comes to
    a stand. By then the brake has long been applied and is being modulated, not
    built up, and it is the only way a berthing train can land on its stopping
    mark to the metre rather than sailing a jerk-limited metre past it.
    """
    resistance = resistance_accel(stock, speed_ms)
    gravity = grade_accel(stock, grade_permille)

    if demanded >= 0.0:
        # Power on: what is left of the traction curve once drag and gravity
        # have taken their share. May be negative on a bank steep enough that
        # full power will not hold the speed, which is the correct answer.
        ceiling = traction_accel(stock, speed_ms) - resistance - gravity
        achieved = min(demanded, ceiling)
    else:
        # Braking: drag and a rising gradient help, a falling one hurts.
        emergency = demanded < -stock.service_brake - 1e-9
        floor = -(brake_rate(stock, emergency) + resistance + gravity)
        achieved = max(demanded, floor)

    if immediate:
        return achieved
    return _rate_limited(previous_accel, achieved, jerk_limit_ms3(stock), dt)


def _rate_limited(previous: float, wanted: float, jerk: float,
                  dt: float) -> float:
    """Move ``previous`` towards ``wanted`` at no more than ``jerk`` per second."""
    if jerk == float("inf") or dt <= 0.0:
        return wanted
    step = jerk * dt
    if wanted > previous + step:
        return previous + step
    if wanted < previous - step:
        return previous - step
    return wanted


def coasting_accel(stock, speed_ms: float, grade_permille: float = 0.0) -> float:
    """Net acceleration with no traction and no brake - what a train drifting does."""
    return -(resistance_accel(stock, speed_ms) + grade_accel(stock, grade_permille))


def balancing_speed_ms(stock, grade_permille: float = 0.0,
                       tolerance: float = 0.01) -> float:
    """The speed at which full power exactly balances resistance and gravity.

    The train's true maximum on this gradient, which may be well below the
    figure on its data sheet. Solved by bisection because the traction curve is
    piecewise and the resistance quadratic; both are cheap and this is only ever
    called by reports and tests, never in the tick loop.
    """
    low, high = 0.0, stock.max_speed_ms
    if traction_accel(stock, high) - resistance_accel(stock, high) \
            - grade_accel(stock, grade_permille) >= 0.0:
        return high
    while high - low > tolerance:
        mid = 0.5 * (low + high)
        surplus = (traction_accel(stock, mid) - resistance_accel(stock, mid)
                   - grade_accel(stock, grade_permille))
        if surplus >= 0.0:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)
