import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ScenarioBuilder from "./ScenarioBuilder";
import { api, type GlobalOptimization, type NetworkResponse } from "./api/client";
import type { components } from "./api/generated";

vi.mock("./api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api/client")>();
  return { ...original, api: { ...original.api, createGlobalScenario: vi.fn(), deleteGlobalScenario: vi.fn() } };
});

const network = {
  id: "synthetic-network",
  name: "Synthetic network",
  synthetic: true,
  quantity_unit: "load_unit",
  cost_unit: "EUR",
  time_unit: "day",
  carbon_unit: "kgCO2e",
  nodes: [
    { id: "origin", label: "Origin", kind: "port", country_code: "IN", country_name: "India", region: "Asia", timezone: "Asia/Kolkata", latitude: 1, longitude: 2, transfer_modes: ["sea"] },
    { id: "destination", label: "Destination", kind: "port", country_code: "NL", country_name: "Netherlands", region: "Europe", timezone: "Europe/Amsterdam", latitude: 3, longitude: 4, transfer_modes: ["sea"] },
  ],
  links: [
    { id: "sea-1", source: "origin", target: "destination", mode: "sea", capacity: 10, capacity_unit: "load_unit", fixed_cost: 5, variable_cost_per_quantity_unit: 2, transit_time: 8, carbon_per_quantity_unit: 1, available: true, capabilities: [], distance_km: 100, geometry: [[1, 2], [3, 4]], resilience_exposure: 0.1 },
  ],
  scenarios: [],
} as NetworkResponse;

const savedScenario = {
  id: "custom-scenario-1",
  name: "Port delay",
  description: "Delay at origin port",
  synthetic: true,
  custom: true,
  created_at: "2026-11-06T00:00:00Z",
  closed_link_ids: ["sea-1"],
  unavailable_location_ids: [],
  capacity_overrides: { "sea-1": 5 },
  cost_multipliers: { "sea-1": 1.2 },
  transit_time_multipliers: {},
  transit_time_additions: { "sea-1": 2 },
} as components["schemas"]["NetworkScenario"];

function run(id: string, scenarioId: string | null, cost: number, carbon: number): GlobalOptimization {
  return {
    id,
    status: "completed",
    created_at: "2026-11-06T00:00:00Z",
    scenario_id: scenarioId,
    weights: { cost: 40, delivery_time: 25, carbon: 20, resilience: 15 },
    result: {
      id,
      status: "completed",
      synthetic: true,
      scenario_id: scenarioId,
      scenario_snapshot: null,
      weights: { cost: 40, delivery_time: 25, carbon: 20, resilience: 15 },
      normalization_references: { cost: 1, delivery_time: 1, carbon: 1, resilience: 1 },
      recovery_feasible: true,
      failure_reason: null,
      baseline: { routes: {}, alternatives: {}, metrics: { freight_cost: cost, delay_penalty: 0, total_cost: cost, delivery_time: 20, carbon_kg: carbon, resilience_exposure: 0.5, weighted_objective: 1 }, capacity_usage: {}, capacity_utilization: {}, method: "exact" },
      recovery: scenarioId ? { routes: {}, alternatives: {}, metrics: { freight_cost: cost, delay_penalty: 0, total_cost: cost, delivery_time: 20, carbon_kg: carbon, resilience_exposure: 0.5, weighted_objective: 1 }, capacity_usage: {}, capacity_utilization: {}, method: "exact" } : null,
      algorithm: "bounded exact candidate assignment",
      optimality_scope: "generated routes",
    },
    error: null,
  } as GlobalOptimization;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.createGlobalScenario).mockResolvedValue(savedScenario);
  vi.mocked(api.deleteGlobalScenario).mockResolvedValue(undefined);
});

describe("ScenarioBuilder", () => {
  it("saves combined closures, capacity, cost and time overlays through the API", async () => {
    const user = userEvent.setup();
    const onUseScenario = vi.fn();
    const onScenariosChange = vi.fn();
    render(<ScenarioBuilder network={network} scenarios={[]} runs={[]} selectedScenarioId="" onScenariosChange={onScenariosChange} onUseScenario={onUseScenario} />);
    await user.type(screen.getByLabelText("Scenario name"), "Port delay");
    await user.type(screen.getByLabelText("Description"), "Delay at origin port");
    await user.selectOptions(screen.getByRole("listbox", { name: /Close transport links/ }), "sea-1");
    await user.type(screen.getByLabelText("Capacity limit (load_unit)"), "5");
    await user.type(screen.getByLabelText("Freight cost multiplier"), "1.2");
    await user.type(screen.getByLabelText("Customs delay (day)"), "2");
    await user.click(screen.getByRole("button", { name: "Add / update link changes" }));
    await user.click(screen.getByRole("button", { name: "Save scenario" }));
    expect(api.createGlobalScenario).toHaveBeenCalledWith({
      name: "Port delay",
      description: "Delay at origin port",
      closed_link_ids: ["sea-1"],
      unavailable_location_ids: [],
      capacity_overrides: { "sea-1": 5 },
      cost_multipliers: { "sea-1": 1.2 },
      transit_time_multipliers: {},
      transit_time_additions: { "sea-1": 2 },
    });
    expect(onScenariosChange).toHaveBeenCalledWith([savedScenario]);
    expect(onUseScenario).toHaveBeenCalledWith(savedScenario.id);
  });

  it("compares persisted feasible run results instead of invented scenario outputs", () => {
    render(<ScenarioBuilder network={network} scenarios={[savedScenario]} runs={[run("base", null, 100, 90), run("recovery", "custom-scenario-1", 115, 70)]} selectedScenarioId="" onScenariosChange={vi.fn()} onUseScenario={vi.fn()} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /Baseline/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /custom-scenario-1/ }));
    expect(screen.getByText("15 EUR")).toBeInTheDocument();
    expect(screen.getByText("-20 kgCO2e")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("Feasible")).toBeInTheDocument();
  });
});
