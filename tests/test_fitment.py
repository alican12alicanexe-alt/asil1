"""Fitting the fleet to the signalling system it is about to run under."""

import unittest

import support

from trainsim.core import signalling


class TestFitment(unittest.TestCase):

    def _timetable(self):
        _, _, timetable = support.build_test_sim()
        return timetable

    def test_every_system_in_the_ladder_declares_a_fitment(self):
        """A system with no fitment would silently run on whatever it found."""
        for name in signalling.LADDER:
            self.assertIn(name, signalling.FITMENT, name)

    def test_virtual_coupling_needs_the_radio_link(self):
        level, tims, v2v = signalling.fitment_for("virtual_coupling")
        self.assertEqual(level, "l3")
        self.assertTrue(tims)
        self.assertTrue(v2v)

    def test_moving_block_needs_the_integrity_report_but_not_the_link(self):
        level, tims, v2v = signalling.fitment_for("etcs_moving_block")
        self.assertEqual(level, "l3")
        self.assertTrue(tims)
        self.assertFalse(v2v)

    def test_lineside_signalling_needs_nothing(self):
        self.assertEqual(signalling.fitment_for("fixed_block_3aspect"),
                         ("none", False, False))

    def test_an_unknown_system_is_an_error_rather_than_a_default(self):
        with self.assertRaises(ValueError):
            signalling.fitment_for("telepathy")

    def test_fitting_changes_the_equipment_and_nothing_else(self):
        """The physical train has to come through untouched, or the comparison
        stops being a comparison of signalling systems."""
        timetable = self._timetable()
        before = timetable.services[0].stock
        signalling.fit_timetable(timetable, "virtual_coupling")
        after = timetable.services[0].stock

        self.assertTrue(after.v2v)
        self.assertTrue(after.tims)
        self.assertEqual(after.etcs_level, "l3")
        for field in ("id", "length_m", "max_speed_ms", "max_accel",
                      "service_brake", "emergency_brake", "mass_kg",
                      "power_w", "starting_effort_n"):
            self.assertEqual(getattr(after, field), getattr(before, field), field)

    def test_fitting_reports_what_it_changed_and_only_that(self):
        timetable = self._timetable()
        self.assertEqual(signalling.fit_timetable(timetable, "virtual_coupling"),
                         ["UNIT"])
        # Already fitted: nothing to do, and nothing reported.
        self.assertEqual(signalling.fit_timetable(timetable, "virtual_coupling"),
                         [])

    def test_downfitting_works_as_well_as_upfitting(self):
        """Running the ladder from the top down must strip equipment too."""
        timetable = self._timetable()
        signalling.fit_timetable(timetable, "virtual_coupling")
        signalling.fit_timetable(timetable, "fixed_block_3aspect")
        stock = timetable.services[0].stock
        self.assertEqual((stock.etcs_level, stock.tims, stock.v2v),
                         ("none", False, False))


class TestDrivingProfile(unittest.TestCase):
    """Who is driving follows from the system, the same way the equipment does."""

    def test_every_system_in_the_ladder_declares_a_profile(self):
        for name in signalling.LADDER:
            self.assertIn(name, signalling.DRIVING, name)

    def test_lineside_signalling_is_read_by_a_person(self):
        self.assertGreater(
            signalling.driving_for("fixed_block_3aspect")["reaction_time_s"], 0.0)

    def test_the_ato_systems_carry_no_reaction_time(self):
        """Not a claim of instant response: the control cycle is the timestep,
        the radio delay is the signalling system's own, and the brake build-up
        is in the stock. This term is the human, and there is not one."""
        for name in ("etcs_moving_block", "virtual_coupling"):
            self.assertEqual(signalling.driving_for(name)["reaction_time_s"],
                             0.0, name)

    def test_fitting_a_driver_leaves_what_the_system_has_no_opinion_on(self):
        from trainsim.core.driver import DriverConfig
        declared = DriverConfig(reaction_time_s=2.0, safety_margin_m=40.0,
                                stop_tolerance_m=2.5, speed_deadband_ms=0.7)
        fitted = signalling.fit_driver(declared, "virtual_coupling")
        self.assertEqual(fitted.reaction_time_s, 0.0)
        self.assertEqual(fitted.safety_margin_m, 40.0)
        self.assertEqual(fitted.stop_tolerance_m, 2.5)
        self.assertEqual(fitted.speed_deadband_ms, 0.7)

    def test_an_unknown_system_has_no_default_driver(self):
        with self.assertRaises(ValueError):
            signalling.driving_for("telepathy")


if __name__ == "__main__":
    unittest.main()
