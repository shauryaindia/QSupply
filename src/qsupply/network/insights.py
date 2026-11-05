"""Deterministic route comparison and rule-based decision explanations.

This module only analyzes values already calculated by the route engine. It
does not call an LLM or derive new operational data from unsupported sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from .planning import ObjectiveReferences, ObjectiveWeights, ShipmentProfile
from .routing import CandidateRoute


@dataclass(frozen=True)
class RouteExplanationContext:
    """Structured, computed facts supplied to an explanation provider."""

    route_id: str
    baseline_route_id: str
    shipment_id: str
    origin_id: str
    destination_id: str
    quantity: int
    quantity_unit: str
    scenario_id: str | None
    objective_weights: Mapping[str, int]
    route_metrics: Mapping[str, float]
    baseline_metrics: Mapping[str, float]
    route_legs: tuple[Mapping[str, object], ...]
    balanced_recommended: bool
    cost_savings: float
    cost_savings_percent: float | None
    time_savings_days: float
    carbon_savings_kg: float
    carbon_savings_percent: float | None
    deadline_met: bool | None
    deadline_slack_days: float | None
    cost_rank: int
    time_rank: int
    carbon_rank: int
    resilience_rank: int
    balanced_rank: int


class RouteExplanationProvider(Protocol):
    """Extension point for later language-model providers using structured facts."""

    name: str

    def explain(self, context: RouteExplanationContext) -> tuple[list[str], list[str], str]:
        """Return advantages, trade-offs, and a recommendation from supplied facts."""


class DeterministicRouteExplanationProvider:
    """Explain computed route metrics with deterministic comparison rules."""

    name = "deterministic_rule_based"

    def explain(self, context: RouteExplanationContext) -> tuple[list[str], list[str], str]:
        advantages: list[str] = []
        tradeoffs: list[str] = []
        for value, label, unit in (
            (context.cost_savings, "modeled cost saved", "cost units"),
            (context.time_savings_days, "delivery time saved", "days"),
            (context.carbon_savings_kg, "estimated emissions saved", "kgCO2e"),
        ):
            if value > 1e-9:
                advantages.append(f"{value:.2f} {unit} {label} versus the baseline route.")
            elif value < -1e-9:
                tradeoffs.append(f"Adds {abs(value):.2f} {unit} versus the baseline route ({label.replace(' saved', '')}).")

        ranks = [
            context.cost_rank,
            context.time_rank,
            context.carbon_rank,
            context.resilience_rank,
        ]
        if context.balanced_recommended:
            recommendation = (
                "Recommended for the configured balanced profile: it has the lowest "
                "weighted normalized score among the generated feasible candidates."
            )
        else:
            recommendation = (
                f"Ranked {context.balanced_rank} by the configured weighted normalized "
                "score among generated feasible candidates."
            )
        if context.deadline_met is True:
            advantages.append(f"Meets the modeled deadline with {context.deadline_slack_days:.2f} days of slack.")
        elif context.deadline_met is False:
            tradeoffs.append(f"Misses the modeled deadline by {abs(context.deadline_slack_days):.2f} days.")
        best_categories = [
            label
            for label, rank in zip(
                ("cost", "time", "carbon", "resilience"), ranks
            )
            if rank == 1
        ]
        if best_categories:
            advantages.append("Ranks first for " + ", ".join(best_categories) + ".")
        if not advantages:
            advantages.append("No modeled metric improves over the selected baseline route.")
        if not tradeoffs:
            tradeoffs.append("No modeled cost, time, or emissions penalty versus the baseline route.")
        return advantages, tradeoffs, recommendation


def _delay_penalty(profile: ShipmentProfile, route: CandidateRoute) -> float:
    if profile.request.deadline is None:
        return 0.0
    delay = max(0.0, float(route.transit_time) - float(profile.request.deadline))
    return delay * float(profile.delay_penalty_per_day)


def _balanced_score(
    profile: ShipmentProfile,
    route: CandidateRoute,
    weights: ObjectiveWeights,
    references: ObjectiveReferences,
) -> float:
    priority = profile.priority
    cost = float(route.freight_cost) + _delay_penalty(profile, route)
    components = (cost, float(route.transit_time), float(route.carbon_kg), float(route.resilience_exposure))
    denominators = (references.cost, references.delivery_time, references.carbon, references.resilience)
    weights_pct = (weights.cost, weights.delivery_time, weights.carbon, weights.resilience)
    return sum(
        weight / 100 * component * priority / denominator
        for weight, component, denominator in zip(weights_pct, components, denominators)
    )


def analyze_route_alternatives(
    profile: ShipmentProfile,
    routes: tuple[CandidateRoute, ...],
    baseline_route: CandidateRoute,
    weights: ObjectiveWeights,
    references: ObjectiveReferences,
    *,
    scenario_id: str | None = None,
    explanation_provider: RouteExplanationProvider | None = None,
) -> tuple[str, dict[str, list[str]], dict[str, dict[str, object]]]:
    """Rank generated alternatives and calculate deltas against a chosen baseline."""
    if not routes:
        raise ValueError("at least one route alternative is required for analysis")
    if any(route.shipment_id != profile.request.id for route in routes):
        raise ValueError("all alternatives must belong to the selected shipment")
    if baseline_route.shipment_id != profile.request.id:
        raise ValueError("baseline route must belong to the selected shipment")
    provider = explanation_provider or DeterministicRouteExplanationProvider()

    route_cost = {
        route.id: float(route.freight_cost) + _delay_penalty(profile, route)
        for route in routes
    }
    metric_values = {
        "cost": route_cost,
        "time": {route.id: float(route.transit_time) for route in routes},
        "carbon": {route.id: float(route.carbon_kg) for route in routes},
        "resilience": {route.id: float(route.resilience_exposure) for route in routes},
        "balanced": {
            route.id: _balanced_score(profile, route, weights, references)
            for route in routes
        },
    }
    rankings = {
        key: sorted(values, key=lambda route_id: (values[route_id], route_id))
        for key, values in metric_values.items()
    }
    rank_lookup = {
        key: {route_id: index + 1 for index, route_id in enumerate(route_ids)}
        for key, route_ids in rankings.items()
    }
    baseline_cost = float(baseline_route.freight_cost) + _delay_penalty(profile, baseline_route)
    baseline_time = float(baseline_route.transit_time)
    baseline_carbon = float(baseline_route.carbon_kg)
    quantity = profile.request.quantity
    analyses: dict[str, dict[str, object]] = {}
    for route in routes:
        cost = route_cost[route.id]
        carbon_by_mode: dict[str, float] = {}
        for leg in route.legs:
            carbon_by_mode[leg.mode.value] = carbon_by_mode.get(leg.mode.value, 0.0) + leg.carbon_kg
        utilizations = [
            quantity / leg.capacity
            for leg in route.legs
            if leg.capacity is not None and leg.capacity > 0
        ]
        deadline_slack = (
            float(profile.request.deadline) - float(route.transit_time)
            if profile.request.deadline is not None
            else None
        )
        cost_savings = baseline_cost - cost
        carbon_savings = baseline_carbon - float(route.carbon_kg)
        context = RouteExplanationContext(
            route_id=route.id,
            baseline_route_id=baseline_route.id,
            shipment_id=profile.request.id,
            origin_id=profile.request.origin_id,
            destination_id=profile.request.destination_id,
            quantity=quantity,
            quantity_unit=profile.request.quantity_unit,
            scenario_id=scenario_id,
            objective_weights={
                "cost": weights.cost,
                "delivery_time": weights.delivery_time,
                "carbon": weights.carbon,
                "resilience": weights.resilience,
            },
            route_metrics={
                "freight_cost": float(route.freight_cost),
                "delay_penalty": _delay_penalty(profile, route),
                "total_cost": cost,
                "delivery_time": float(route.transit_time),
                "carbon_estimate_kg": float(route.carbon_kg),
                "resilience_exposure": float(route.resilience_exposure),
                "distance_km": float(route.distance_km),
                "transfer_count": float(route.transfer_count),
                "maximum_capacity_utilization": max(utilizations) if utilizations else 0.0,
            },
            baseline_metrics={
                "freight_cost": float(baseline_route.freight_cost),
                "delay_penalty": _delay_penalty(profile, baseline_route),
                "total_cost": baseline_cost,
                "delivery_time": baseline_time,
                "carbon_estimate_kg": baseline_carbon,
                "resilience_exposure": float(baseline_route.resilience_exposure),
                "distance_km": float(baseline_route.distance_km),
                "transfer_count": float(baseline_route.transfer_count),
            },
            route_legs=tuple(
                {
                    "link_id": leg.link_id,
                    "origin_id": leg.origin_id,
                    "destination_id": leg.destination_id,
                    "mode": leg.mode.value,
                    "distance_km": leg.distance_km,
                    "transit_time": leg.transit_time,
                    "freight_cost": leg.freight_cost,
                    "carbon_estimate_kg": leg.carbon_kg,
                    "resilience_exposure": leg.resilience_exposure,
                    "capacity": leg.capacity,
                }
                for leg in route.legs
            ),
            balanced_recommended=rank_lookup["balanced"][route.id] == 1,
            cost_savings=cost_savings,
            cost_savings_percent=(100 * cost_savings / baseline_cost if baseline_cost else None),
            time_savings_days=baseline_time - float(route.transit_time),
            carbon_savings_kg=carbon_savings,
            carbon_savings_percent=(100 * carbon_savings / baseline_carbon if baseline_carbon else None),
            deadline_met=None if deadline_slack is None else deadline_slack >= 0,
            deadline_slack_days=deadline_slack,
            cost_rank=rank_lookup["cost"][route.id],
            time_rank=rank_lookup["time"][route.id],
            carbon_rank=rank_lookup["carbon"][route.id],
            resilience_rank=rank_lookup["resilience"][route.id],
            balanced_rank=rank_lookup["balanced"][route.id],
        )
        advantages, tradeoffs, recommendation = provider.explain(context)
        analyses[route.id] = {
            "route_id": route.id,
            "total_cost": cost,
            "delay_penalty": _delay_penalty(profile, route),
            "deadline_met": context.deadline_met,
            "deadline_slack_days": deadline_slack,
            "balanced_score": metric_values["balanced"][route.id],
            "maximum_capacity_utilization": max(utilizations) if utilizations else None,
            "carbon_by_mode_kg": carbon_by_mode,
            "largest_cost_leg_id": max(route.legs, key=lambda leg: leg.freight_cost).link_id if route.legs else None,
            "largest_carbon_leg_id": max(route.legs, key=lambda leg: leg.carbon_kg).link_id if route.legs else None,
            "delta_vs_baseline": {
                "baseline_route_id": baseline_route.id,
                "cost_savings": cost_savings,
                "cost_savings_percent": context.cost_savings_percent,
                "time_savings_days": context.time_savings_days,
                "carbon_savings_kg": carbon_savings,
                "carbon_savings_percent": context.carbon_savings_percent,
            },
            "recommendation": recommendation,
            "advantages": advantages,
            "tradeoffs": tradeoffs,
            "analysis_type": provider.name,
            "uses_llm": False,
        }
    return rankings["balanced"][0], rankings, analyses
