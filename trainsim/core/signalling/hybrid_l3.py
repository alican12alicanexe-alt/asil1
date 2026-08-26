"""Hybrid ERTMS/ETCS Level 3.

The interesting one, and a genuine Shift2Rail flagship (X2Rail-3, and the ABZ
2018 formal-methods case study). It buys most of moving block's capacity without
requiring the whole fleet to be able to report its position and confirm its
integrity - which no railway's fleet can, during migration.

The trackside keeps its existing train detection sections and subdivides each
into virtual sub-sections. A movement authority runs to the start of the first
sub-section ahead that is not *free*. For a fitted train following another fitted
train, that is a fraction of a block rather than a whole one. For an unfitted
train, or one behind an unfitted train, the sub-sections all go *unknown* and the
behaviour degrades gracefully to Level 2 - safe, just no better than before.

That graceful degradation is the entire selling point, so the scenario is worth
running with a fleet of mixed fitment to see it.
"""

from .. import vss as vss_module
from .base import SEPARATION_BY_DISTANCE, MovementAuthority, SignallingSystem
from .common import limit_by_route


class HybridLevel3(SignallingSystem):
    """Virtual sub-sections over physical train detection."""

    name = "etcs_hybrid_l3"
    has_lineside_signals = False
    # Sub-sections are finer than block sections, so two trains may share
    # one block legitimately; the kernel checks separation, not exclusivity.
    separates_by = SEPARATION_BY_DISTANCE

    def __init__(self, vss_per_block: int = 4, safety_margin_m: float = 50.0):
        super().__init__()
        self.vss_per_block = int(vss_per_block)
        self.safety_margin_m = float(safety_margin_m)
        self._state = None
        self._updated_at = None

    # ------------------------------------------------------------------ per tick

    def _ensure_state(self, sim) -> None:
        """Rebuild sub-section states once per tick, not once per train."""
        if self._state is None:
            self._state = vss_module.VSSState(
                vss_module.subdivide(sim.blocks, self.vss_per_block)
            )
            self._updated_at = None
        if self._updated_at != sim.time_s:
            vss_module.update(self._state, sim)
            self._updated_at = sim.time_s

    def observe(self, train, sim) -> None:
        self._ensure_state(sim)

    # -------------------------------------------------------- movement authority

    def movement_authority(self, train, sim) -> MovementAuthority:
        self._ensure_state(sim)

        vss_point, vss_reason, blocked = vss_module.first_blocked(
            self._state, train, sim)
        # The margin separates this train from what is in front of it.
        # Applying it to the end of the line as well would stop trains short
        # of their own platforms, which is not a separation problem at all.
        danger = vss_point - self.safety_margin_m if blocked else vss_point
        reason = vss_reason

        # No fixed-block cap on top. The trackside sections are still the safety
        # net, but they act *through* the sub-section states: a train that cannot
        # report its position marks every sub-section of its block unknown, so a
        # follower's authority already stops at that block's entry. Capping here
        # as well would stop the authority at the block entry in every case and
        # turn Hybrid Level 3 back into Level 2.
        danger, reason = limit_by_route(danger, reason, train, sim)
        return MovementAuthority(
            end_distance_m=max(0.0, danger - train.chainage_m),
            target_speed_ms=0.0,
            reason="HL3: %s" % reason,
        )

    # ------------------------------------------------------------------ reports

    @property
    def vss_state(self):
        """The live sub-section states, for the view and for tests."""
        return self._state

    def describe(self) -> str:
        return ("Hybrid ETCS Level 3 (%d virtual sub-sections per block, "
                "margin %.0f m)" % (self.vss_per_block, self.safety_margin_m))
