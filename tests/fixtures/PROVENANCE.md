# Authored fixtures

All default fixtures are synthetic, hand-authored in `tests/conftest.py` or Rust
adapter tests. They are not real market observations. No real archives are in Git.

The Python fixture has ten original rows, nine accepted books and three
executions in a 60-second session. The right-closed 10-second grid accepts ends
20, 50 and 60 seconds. At (10,20], bid size 100->130 gives +30 and ask size
120->100 gives +20, so L1 OFI is +50. Depth averages 125 and 115 to 120.
A rejected quote at 21 seconds has a valid independent sell execution of nine
shares. Segment initialization at 31 seconds is unknown. At (40,50], bid size
130->110 gives -20. The last three-share sell executes exactly at session close.
Tied 11-second events retain their original IDs. Deeper-only first-bucket updates
exercise L1 classification. Poisoned reference files verify independence.
