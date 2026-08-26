"""Scenario definition: reading files and expanding them into a railway."""

from .loader import ScenarioError, load_scenario, read_data_file

__all__ = ["ScenarioError", "load_scenario", "read_data_file"]
