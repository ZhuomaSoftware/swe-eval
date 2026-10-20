# Interval utilities

`merge_ranges` merges closed intervals, returns tuples sorted by start, and
does not mutate its input. Invalid reversed intervals raise `ValueError`.

Run the public smoke tests with `python3 -m unittest -v test_public`.
