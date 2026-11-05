"""Internal exact arithmetic helpers for route-cost comparisons."""

from collections.abc import Mapping, Sequence
from fractions import Fraction
from numbers import Real


def exact_number(value: Real) -> Fraction:
    """Convert a supported real value without losing its represented value.

    Integers and rational values remain exact. A Python float is interpreted
    as its exact stored IEEE-754 binary value via ``Fraction(float)``.
    """
    return Fraction(value)


def public_number(value: Fraction) -> Real:
    """Return an int for integral totals, otherwise retain an exact Fraction."""
    if value.denominator == 1:
        return value.numerator
    return value


def exact_transportation_cost(
    distances: Mapping[tuple[str, str], Real],
    routes: Mapping[str, Sequence[str]],
) -> Real:
    """Sum arc costs exactly, interpreting floats as their exact binary values."""
    total = sum(
        (
            exact_number(distances[(origin, destination)])
            for route in routes.values()
            for origin, destination in zip(route, route[1:])
        ),
        Fraction(0),
    )
    return public_number(total)
