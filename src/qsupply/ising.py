"""Dependency-free QUBO to Ising conversion using named variables."""

from collections.abc import Mapping
from fractions import Fraction
from math import isfinite
from numbers import Real
from types import MappingProxyType

from .qubo import QUBO


class IsingModel:
    """An Ising energy ``C + sum(h[i] z[i]) + sum(J[i,j] z[i] z[j])``.

    ``variables`` preserves the source QUBO's declared order. ``linear`` is
    keyed by variable name; ``quadratic`` is keyed by canonical pairs in that
    order (the lower index first). The constant is included by :meth:`energy`.
    """

    def __init__(
        self,
        variables: tuple[str, ...],
        constant: Real,
        linear: Mapping[str, Real],
        quadratic: Mapping[tuple[str, str], Real],
    ) -> None:
        if any(
            not isinstance(variable, str) or not variable for variable in variables
        ):
            raise ValueError("variables must be non-empty strings")
        if len(set(variables)) != len(variables):
            raise ValueError("variables must be unique")
        if not isinstance(linear, Mapping) or not isinstance(quadratic, Mapping):
            raise TypeError("linear and quadratic coefficients must be mappings")
        self._variables = tuple(variables)
        self._indices = MappingProxyType(
            {variable: index for index, variable in enumerate(self._variables)}
        )
        self._constant = _finite_real(constant, "constant")
        if any(not isinstance(variable, str) for variable in linear):
            raise ValueError("linear coefficient keys must be declared variable names")
        self._linear = MappingProxyType(
            {
                variable: _finite_real(value, f"linear coefficient for {variable!r}")
                for variable, value in linear.items()
            }
        )
        self._quadratic = MappingProxyType(
            {
                pair: _finite_real(value, f"quadratic coefficient for {pair!r}")
                for pair, value in quadratic.items()
            }
        )
        if set(self._linear) != set(self._variables):
            raise ValueError("linear coefficients must contain every declared variable")
        for pair in self._quadratic:
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not all(isinstance(variable, str) for variable in pair)
                or pair[0] not in self._indices
                or pair[1] not in self._indices
                or self._indices[pair[0]] >= self._indices[pair[1]]
            ):
                raise ValueError(
                    "quadratic coefficient keys must be ordered distinct declared variables"
                )

    @property
    def variables(self) -> tuple[str, ...]:
        """Variables in the same order as their source QUBO."""
        return self._variables

    @property
    def variable_indices(self) -> Mapping[str, int]:
        """Read-only mapping from variable name to register index."""
        return self._indices

    @property
    def constant(self) -> Real:
        """Constant energy offset, including any supplied formulation offset."""
        return self._constant

    @property
    def linear(self) -> Mapping[str, Real]:
        """Read-only linear Ising coefficients ``h[i]``."""
        return self._linear

    @property
    def quadratic(self) -> Mapping[tuple[str, str], Real]:
        """Read-only canonical quadratic coefficients ``J[i,j]``."""
        return self._quadratic

    def energy(self, spins: Mapping[str, int]) -> Real:
        """Evaluate a complete spin assignment with values only in ``{-1, 1}``."""
        _validate_assignment(spins, self._variables, (-1, 1), "spin")
        value: Real = self._constant
        for variable in self._variables:
            value += self._linear[variable] * spins[variable]
        for (left, right), coefficient in self._quadratic.items():
            value += coefficient * spins[left] * spins[right]
        return value

    def energy_from_binary(self, assignment: Mapping[str, int]) -> Real:
        """Evaluate using QUBO bits, mapping 0 to +1 and 1 to -1."""
        _validate_assignment(
            assignment, self._variables, (0, 1), "binary", allow_bool=True
        )
        spins = {variable: 1 - 2 * assignment[variable] for variable in self._variables}
        return self.energy(spins)


def qubo_to_ising(qubo: QUBO, *, offset: Real = 0) -> IsingModel:
    """Convert a QUBO to Ising form, optionally preserving a separate constant.

    The source QUBO evaluates ordered pairs as supplied. For each unordered
    pair, both orientations therefore combine as ``Q[i,j] + Q[j,i]``.
    The optional ``offset`` is added to the Ising constant; pass an
    :class:`ImportExportFormulation`'s ``offset`` to preserve its full energy.
    No source model or coefficient mapping is modified.
    """
    if not isinstance(qubo, QUBO):
        raise TypeError("qubo must be a QUBO instance")
    constant: Real = _finite_real(offset, "offset")
    linear: dict[str, Real] = {}
    quadratic: dict[tuple[str, str], Real] = {}

    for variable in qubo.variables:
        diagonal = qubo.coefficients.get((variable, variable), 0)
        linear[variable] = -diagonal * Fraction(1, 2)
        constant += diagonal * Fraction(1, 2)

    for left_index, left in enumerate(qubo.variables):
        for right in qubo.variables[left_index + 1 :]:
            pair_coefficient = qubo.coefficients.get(
                (left, right), 0
            ) + qubo.coefficients.get((right, left), 0)
            if pair_coefficient:
                contribution = pair_coefficient * Fraction(1, 4)
                quadratic[(left, right)] = contribution
                linear[left] -= contribution
                linear[right] -= contribution
                constant += contribution

    return IsingModel(qubo.variables, constant, linear, quadratic)


def _finite_real(value: Real, name: str) -> Real:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be finite")
    return value


def _validate_assignment(
    assignment: Mapping[str, int],
    variables: tuple[str, ...],
    allowed: tuple[int, int],
    label: str,
    *,
    allow_bool: bool = False,
) -> None:
    if not isinstance(assignment, Mapping):
        raise TypeError(f"{label} assignment must be a mapping")
    expected = set(variables)
    supplied = set(assignment)
    missing = expected - supplied
    unknown = supplied - expected
    if missing:
        raise ValueError(f"assignment is missing variables: {sorted(missing)!r}")
    if unknown:
        raise ValueError(f"assignment contains unknown variables: {sorted(unknown)!r}")
    for variable in variables:
        value = assignment[variable]
        if (
            (isinstance(value, bool) and not allow_bool)
            or not isinstance(value, Real)
            or value not in allowed
        ):
            choices = " or ".join(map(str, allowed))
            raise ValueError(
                f"{label} for variable {variable!r} must be {choices}; got {value!r}"
            )
