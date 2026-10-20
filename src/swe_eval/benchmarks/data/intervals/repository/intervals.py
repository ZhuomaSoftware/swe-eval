"""Utilities for merging closed numeric intervals."""


def merge_ranges(ranges):
    """Return sorted, disjoint closed intervals without mutating the input."""
    ordered = sorted((start, end) for start, end in ranges)
    if any(start > end for start, end in ordered):
        raise ValueError("range start must not exceed its end")
    merged = []
    for start, end in ordered:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
