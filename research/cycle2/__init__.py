"""OFFLINE-RESEARCH-CYCLE-2 minimum tooling (OPENING-1 §6, built by unit §7.1).

Nothing in this package executes research on import. ``driver.py`` invokes the
engine only when run as a script without ``--dry-run``; ``multiple_testing.py``
and ``regime_session.py`` are pure functions over data they are handed.
"""
