"""Schematic visualisation.

The view is strictly read-only: it inspects simulation state and draws it, never
altering it. That is what keeps headless batch runs possible, and it is why the
kernel has no idea a window exists.
"""
