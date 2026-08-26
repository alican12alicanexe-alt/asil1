"""Longitudinal dynamics: traction, resistance, gradient and the brake.

The simulator used to accelerate every train at ``max_accel`` from a stand to
line speed and brake it at ``service_brake`` whatever the railway did. Nothing
opposed it, so a 200 m EMU reached 140 km/h in 43 seconds and 840 metres - about
twice as good as any real one - and every run time and headway downstream of
that was optimistic.

These tests pin the four things that replaced it: a traction curve that falls
away above base speed, Davis running resistance, gravity on a gradient, and a
brake that is limited by adhesion and takes a moment to come on. They are stated
against figures a traction engineer would recognise rather than against whatever
the code happens to produce, because the point of the change is to be right
about the physics and not merely to be slower.
"""

import unittest

import support
from trainsim.core import dynamics
from trainsim.core.train import RollingStock
from trainsim.core.units import kmh_to_ms, ms_to_kmh


def stock(**overrides):
    """A 200 m, 140 km/h EMU - the corridor scenario's fast unit."""
    spec = dict(id="EMU", name="EMU", length_m=200.0,
                max_speed_ms=kmh_to_ms(140), max_accel=0.9,
                service_brake=0.7, emergency_brake=1.2)
    spec.update(overrides)
    return RollingStock(**spec)


class TestDerivedParameters(unittest.TestCase):
    """What a scenario that says nothing about mass or power gets."""

    def test_a_train_is_weighed_by_its_length(self):
        self.assertAlmostEqual(stock().mass_t, 360.0)
        self.assertAlmostEqual(stock(length_m=120.0).mass_t, 216.0)

    def test_declared_mass_wins(self):
        self.assertAlmostEqual(stock(mass_t=205.0).mass_t, 205.0)

    def test_rotating_parts_make_the_train_behave_heavier(self):
        unit = stock(mass_t=200.0, rotating_mass_pct=8.0)
        self.assertAlmostEqual(dynamics.effective_mass_kg(unit), 216000.0)

    def test_starting_effort_still_delivers_the_declared_acceleration(self):
        """The one thing that must not change: away from a platform, as booked."""
        unit = stock()
        self.assertAlmostEqual(
            unit.starting_effort_n / dynamics.effective_mass_kg(unit),
            unit.max_accel, places=9,
        )

    def test_base_speed_lands_where_real_stock_changes_over(self):
        self.assertAlmostEqual(ms_to_kmh(stock().base_speed_ms), 56.0, places=3)
        self.assertAlmostEqual(
            ms_to_kmh(stock(max_speed_ms=kmh_to_ms(90)).base_speed_ms),
            36.0, places=3)

    def test_declared_power_wins(self):
        unit = stock(power_kw=2000.0)
        self.assertAlmostEqual(unit.power_kw, 2000.0)
        self.assertAlmostEqual(unit.base_speed_ms,
                               2000e3 / unit.starting_effort_n)


class TestTractionCurve(unittest.TestCase):

    def test_effort_is_flat_below_base_speed(self):
        unit = stock()
        at_rest = dynamics.tractive_effort_n(unit, 0.0)
        half_way = dynamics.tractive_effort_n(unit, 0.5 * unit.base_speed_ms)
        self.assertAlmostEqual(at_rest, half_way, places=6)

    def test_effort_falls_as_power_over_speed_above_it(self):
        unit = stock()
        fast = 2.0 * unit.base_speed_ms
        self.assertAlmostEqual(dynamics.tractive_effort_n(unit, fast),
                               unit.power_w / fast, places=6)

    def test_acceleration_at_line_speed_is_a_fraction_of_the_starting_rate(self):
        """The headline change. 0.9 m/s2 all the way up was never real."""
        unit = stock()
        top = dynamics.traction_accel(unit, unit.max_speed_ms)
        self.assertLess(top, 0.45 * unit.max_accel)
        self.assertGreater(top, 0.1)

    def test_a_train_still_reaches_its_line_speed_on_the_level(self):
        """Geared to its maximum, as stock is: balancing speed is not below it."""
        self.assertAlmostEqual(ms_to_kmh(stock().balancing_speed_ms), 140.0,
                               delta=0.5)

    def test_a_bank_holds_a_heavy_train_below_line_speed(self):
        """What a gradient profile is for: the train cannot always do the limit.

        A 1200-tonne train on 2 MW is a freight, and a 15 per thousand bank is
        the sort of thing that has banking engines stationed at the foot of it.
        """
        heavy = stock(mass_t=1200.0, power_kw=2000.0, max_accel=0.3,
                      max_speed_ms=kmh_to_ms(100))
        self.assertAlmostEqual(ms_to_kmh(heavy.balancing_speed_ms), 100.0,
                               delta=0.5)
        banked = dynamics.balancing_speed_ms(heavy, grade_permille=15)
        self.assertLess(ms_to_kmh(banked), 70.0)
        self.assertGreater(ms_to_kmh(banked), 20.0)


class TestRunningResistance(unittest.TestCase):

    def test_it_rises_with_speed(self):
        unit = stock()
        rates = [dynamics.resistance_n(unit, kmh_to_ms(v))
                 for v in (0, 40, 80, 120, 160)]
        self.assertEqual(rates, sorted(rates))

    def test_it_is_the_right_size_for_a_main_line_emu(self):
        """About 30 N per tonne at 140 km/h, which is where measured stock sits."""
        unit = stock()
        specific = dynamics.resistance_n(unit, kmh_to_ms(140)) / unit.mass_t
        self.assertGreater(specific, 25.0)
        self.assertLess(specific, 45.0)

    def test_drag_dominates_at_speed_and_rolling_resistance_at_rest(self):
        unit = stock()
        at_rest = dynamics.resistance_n(unit, 0.0)
        fast = dynamics.resistance_n(unit, kmh_to_ms(140))
        drag = unit.davis_c_n_per_ms2 * kmh_to_ms(140) ** 2
        self.assertGreater(drag, 0.5 * fast)
        self.assertLess(at_rest, 0.3 * fast)

    def test_a_coasting_train_slows_down(self):
        unit = stock()
        self.assertLess(dynamics.coasting_accel(unit, kmh_to_ms(140)), 0.0)

    def test_declared_coefficients_win(self):
        unit = stock(davis_a_n=1000.0, davis_b_n_per_ms=0.0,
                     davis_c_n_per_ms2=0.0)
        self.assertAlmostEqual(dynamics.resistance_n(unit, 30.0), 1000.0)


class TestGradient(unittest.TestCase):

    def test_a_climb_retards_and_a_fall_assists(self):
        unit = stock()
        self.assertGreater(dynamics.grade_accel(unit, 10), 0.0)
        self.assertLess(dynamics.grade_accel(unit, -10), 0.0)
        self.assertEqual(dynamics.grade_accel(unit, 0), 0.0)

    def test_ten_per_thousand_is_about_a_tenth_of_a_metre_per_second_squared(self):
        """g/100, less the rotating mass share - the figure to sanity-check against."""
        self.assertAlmostEqual(dynamics.grade_accel(stock(), 10), 0.0908,
                               places=4)

    def test_gravity_outweighs_drag_on_any_real_bank(self):
        """Why a gradient profile matters more to run times than aerodynamics."""
        unit = stock()
        drag = dynamics.resistance_accel(unit, kmh_to_ms(140))
        self.assertGreater(dynamics.grade_accel(unit, 10), 2.0 * drag)


class TestTheBrake(unittest.TestCase):

    def test_adhesion_caps_a_brake_rate_nobody_could_deliver(self):
        unit = stock(service_brake=5.0, adhesion=0.30)
        self.assertAlmostEqual(dynamics.brake_rate(unit), 0.30 * dynamics.G,
                               places=6)

    def test_a_normal_service_rate_is_nowhere_near_the_limit(self):
        self.assertAlmostEqual(dynamics.brake_rate(stock()), 0.7, places=6)

    def test_a_falling_gradient_takes_rate_away_from_it(self):
        unit = stock()
        level = dynamics.braking_rate_on_grade(unit, 0)
        downhill = dynamics.braking_rate_on_grade(unit, -20)
        uphill = dynamics.braking_rate_on_grade(unit, 20)
        self.assertLess(downhill, level)
        self.assertGreater(uphill, level)

    def test_running_resistance_is_not_counted_on(self):
        """A braking curve has to hold for a light, clean train in still air."""
        unit = stock()
        self.assertAlmostEqual(dynamics.braking_rate_on_grade(unit, 0),
                               unit.service_brake, places=6)

    def test_build_up_costs_half_the_build_up_time_at_speed(self):
        unit = stock(brake_buildup_s=2.0)
        self.assertAlmostEqual(dynamics.brake_buildup_distance_m(unit, 30.0),
                               30.0, places=6)


class TestWhatTheTrainDeliversWhenAsked(unittest.TestCase):
    """``achievable_accel`` - the driver asks, the train answers."""

    def test_a_modest_demand_is_met_in_full(self):
        unit = stock()
        got = dynamics.achievable_accel(unit, 20.0, 0.2, previous_accel=0.2)
        self.assertAlmostEqual(got, 0.2, places=9)

    def test_full_power_at_line_speed_is_not(self):
        unit = stock()
        got = dynamics.achievable_accel(unit, unit.max_speed_ms, unit.max_accel,
                                        immediate=True)
        self.assertLess(got, 0.5 * unit.max_accel)
        self.assertGreater(got, 0.0)

    def test_a_bank_can_beat_full_power(self):
        """Steep enough, and the train slows down with everything it has open."""
        unit = stock()
        got = dynamics.achievable_accel(unit, unit.max_speed_ms, unit.max_accel,
                                        grade_permille=60, previous_accel=0.0,
                                        dt=100.0)
        self.assertLess(got, 0.0)

    def test_the_brake_cannot_beat_its_own_rate(self):
        unit = stock()
        got = dynamics.achievable_accel(unit, 30.0, -9.0, previous_accel=-9.0,
                                        immediate=True)
        self.assertGreater(got, -(unit.emergency_brake + 0.1))

    def test_jerk_is_limited_and_the_stopping_tick_is_exempt(self):
        unit = stock()
        ramped = dynamics.achievable_accel(unit, 30.0, -0.7, previous_accel=0.0,
                                           dt=1.0)
        self.assertGreater(ramped, -0.7)
        immediate = dynamics.achievable_accel(unit, 30.0, -0.7,
                                              previous_accel=0.0, dt=1.0,
                                              immediate=True)
        self.assertAlmostEqual(immediate, -0.7, places=6)


class TestRunningTrains(unittest.TestCase):
    """The same physics, seen from the outside on the test line."""

    def _run(self, infra_spec=None):
        sim, infra, timetable = support.build_test_sim(infra_spec=infra_spec)
        started = None
        top_speed = 0.0
        while not sim.finished:
            sim.step()
            train = sim.trains.get("T1")
            if train is None:
                continue
            if started is None:
                started = sim.time_s
            top_speed = max(top_speed, train.speed_ms)
            if train.state == "finished":
                break
        train = sim.trains["T1"]
        return {
            "run_s": sim.time_s - started,
            "top_kmh": ms_to_kmh(top_speed),
            "stop_error_m": train.chainage_m - timetable.services[0].stops[-1].stop_chainage_m,
        }

    def test_the_run_up_to_line_speed_takes_a_realistic_time(self):
        """Roughly a minute and the better part of two kilometres, not 43 s."""
        sim, infra, timetable = support.build_test_sim()
        elapsed = None
        while not sim.finished:
            sim.step()
            train = sim.trains.get("T1")
            if train is None or train.state != "running":
                continue
            if elapsed is None:
                elapsed = (sim.time_s, train.chainage_m)
            if ms_to_kmh(train.speed_ms) >= 139.0:
                took = sim.time_s - elapsed[0]
                ran = train.chainage_m - elapsed[1]
                break
        else:
            self.fail("the train never reached line speed")
        self.assertGreater(took, 55.0)
        self.assertLess(took, 90.0)
        self.assertGreater(ran, 1400.0)
        self.assertLess(ran, 2500.0)

    def test_a_climb_costs_time_but_a_fall_does_not_buy_any(self):
        """Gradients are not symmetrical, and the reason is the speed limit.

        Working up a bank, the train has less acceleration left over and takes
        longer to reach line speed - real time lost. Running down one it reaches
        line speed sooner, but line speed is line speed: the surplus has nowhere
        to go, and what it does buy is spent again braking into the platform,
        which now takes longer. Downhill is a wash; uphill is a cost.
        """
        level = self._run()
        climbing = self._run(support.sloped_infra(25))
        falling = self._run(support.sloped_infra(-25))
        self.assertGreater(climbing["run_s"], level["run_s"] + 5.0)
        self.assertLess(abs(falling["run_s"] - level["run_s"]), 5.0)

    def test_a_train_berths_on_the_mark_whatever_the_gradient(self):
        """The driver's curve allows for the gradient, so the stop is unaffected."""
        for spec in (None, support.sloped_infra(20), support.sloped_infra(-20)):
            result = self._run(spec)
            self.assertLess(abs(result["stop_error_m"]), 1.0)

    def test_braking_starts_earlier_downhill(self):
        """Where the gradient actually shows up: in when the brake goes on."""
        starts = {}
        for grade in (0, -20):
            spec = support.sloped_infra(grade) if grade else None
            sim, infra, timetable = support.build_test_sim(infra_spec=spec)
            top = 0.0
            while not sim.finished:
                sim.step()
                train = sim.trains.get("T1")
                if train is None:
                    continue
                top = max(top, train.speed_ms)
                if top > 30.0 and train.speed_ms < top - 1.0:
                    starts[grade] = train.chainage_m
                    break
        self.assertLess(starts[-20], starts[0])


if __name__ == "__main__":
    unittest.main()
