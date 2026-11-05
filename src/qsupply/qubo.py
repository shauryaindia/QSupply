"""A small, dependency-free representation of a binary QUBO objective."""

from collections.abc import Iterable, Mapping
from math import isfinite
from numbers import Real
from types import MappingProxyType


class QUBO:
    """Represent ``sum(Q[i, j] * x[i] * x[j])`` for binary variables.

    Coefficients are keyed by ordered variable pairs. The model evaluates
    exactly the terms supplied; it does not symmetrize the coefficient matrix.
    Boolean assignment values are accepted because ``False`` and ``True``
    represent binary 0 and 1 in Python.
    """

    def __init__(
        self,
        variables: Iterable[str],
        coefficients: Mapping[tuple[str, str], Real],
    ) -> None:
        if isinstance(variables, str):
            raise TypeError("variables must be an iterable of variable names, not a string")
        variable_list = tuple(variables)
        if any(not isinstance(variable, str) or not variable for variable in variable_list):
            raise ValueError("variables must be non-empty strings")
        if len(set(variable_list)) != len(variable_list):
            raise ValueError("variables must be unique")
        if not isinstance(coefficients, Mapping):
            raise TypeError("coefficients must be a mapping of variable pairs to weights")

        variable_set = set(variable_list)
        copied_coefficients: dict[tuple[str, str], Real] = {}
        for pair, weight in coefficients.items():
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not all(isinstance(variable, str) for variable in pair)
                or pair[0] not in variable_set
                or pair[1] not in variable_set
            ):
                raise ValueError(
                    f"coefficient key {pair!r} must be a pair of declared variables"
                )
            if isinstance(weight, bool) or not isinstance(weight, Real):
                raise TypeError(f"coefficient for {pair!r} must be a real number")
            try:
                finite = isfinite(weight)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError(f"coefficient for {pair!r} must be finite")
            copied_coefficients[pair] = weight

        self._variables = variable_list
        self._coefficients = MappingProxyType(copied_coefficients)

    @property
    def variables(self) -> tuple[str, ...]:
        """The model's variables in their declared order."""
        return self._variables

    @property
    def coefficients(self) -> Mapping[tuple[str, str], Real]:
        """Read-only mapping of ordered variable pairs to coefficients."""
        return self._coefficients

    def energy(self, assignment: Mapping[str, int]) -> Real:
        """Evaluate the objective for a complete binary assignment.

        Raises ``TypeError`` for a non-mapping assignment and ``ValueError``
        for missing/unknown variables or values other than 0 and 1.
        """
        if not isinstance(assignment, Mapping):
            raise TypeError("assignment must be a mapping of variable names to 0 or 1")

        expected = set(self._variables)
        supplied = set(assignment)
        missing = expected - supplied
        unknown = supplied - expected
        if missing:
            raise ValueError(f"assignment is missing variables: {sorted(missing)!r}")
        if unknown:
            raise ValueError(f"assignment contains unknown variables: {sorted(unknown)!r}")

        for variable in self._variables:
            value = assignment[variable]
            if isinstance(value, bool):
                continue
            if not isinstance(value, Real) or value not in (0, 1):
                raise ValueError(
                    f"assignment for variable {variable!r} must be 0 or 1; got {value!r}"
                )

        return sum(
            weight * assignment[i] * assignment[j]
            for (i, j), weight in self._coefficients.items()
        )
