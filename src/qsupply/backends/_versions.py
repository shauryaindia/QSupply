"""Small dependency-free parser for the stable SDK versions QSupply supports."""

from __future__ import annotations

import re


_RELEASE_VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:\.post(0|[1-9][0-9]*))?"
    r"(?:\+[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?$"
)


def is_release_version_in_range(
    value: str | None,
    *,
    minimum: tuple[int, int, int],
    maximum_exclusive: tuple[int, int, int],
) -> bool:
    """Check a normalized stable release against a half-open version range.

    Stable ``.postN`` and local versions are accepted for their release base.
    Prerelease, dev, epoch and malformed strings are rejected so an unknown SDK
    build is never reported as available without an explicit support decision.
    """
    if not isinstance(value, str):
        return False
    match = _RELEASE_VERSION.fullmatch(value)
    if match is None:
        return False
    release = tuple(int(match.group(index)) for index in (1, 2, 3))
    return minimum <= release < maximum_exclusive
