<!-- vibeflow-directory-purpose -->
# Offline preview browser acceptance

Browser assertions against real rendered Python and JavaScript snapshots. Called by
the pytest full gate with its locked renderer. Screenshots and runtime output are
written into the caller's isolated scratch directory, never this source directory.

`planned.cjs` checks planned status, effective behavior, body availability, repeated calls, Loop expansion and snapshot review links for both Targets.
