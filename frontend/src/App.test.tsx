import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { api, type GlobalOptimization, type QuantumQAOAResult, type RouteIntelligence, type RunRecord } from "./api/client";

vi.mock("./GlobalNetworkMap", () => ({
  default: () => <div data-testid="global-map" />,
}));

vi.mock("./api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api/client")>();
  return {
    ...original,
    api: {
      health: vi.fn(),
      capabilities: vi.fn(),
      runQuantumQAOA: vi.fn(),
      instances: vi.fn(),
      network: vi.fn(),
      globalNetwork: vi.fn(),
      globalShipments: vi.fn(),
      globalDemos: vi.fn(),
      globalScenarios: vi.fn(),
      createGlobalScenario: vi.fn(),
      deleteGlobalScenario: vi.fn(),
      globalRoutes: vi.fn(),
      routeIntelligence: vi.fn(),
      globalOptimizations: vi.fn(),
      globalOptimization: vi.fn(),
      createGlobalOptimization: vi.fn(),
      optimizationReport: vi.fn(),
      optimizationPdfReport: vi.fn(),
      askDecisionQuestion: vi.fn(),
      shipmentPosition: vi.fn(),
      runs: vi.fn(),
      run: vi.fn(),
      createRun: vi.fn(),
    },
  };
});

const completedRun: RunRecord = {
  id: "test-run-1234",
  instance_id: "synthetic-5",
  solver: "nearest-neighbor+2-opt",
  status: "completed",
  created_at: "2026-11-05T12:00:00Z",
  started_at: "2026-11-05T12:00:00Z",
  completed_at: "2026-11-05T12:00:00Z",
  result: {
    instance_id: "synthetic-5",
    instance_name: "Synthetic CVRP (5 customers)",
    synthetic: true,
    customer_count: 5,
    solver: "nearest-neighbor+2-opt",
    routes: { "vehicle-1": ["depot", "customer-1", "customer-3", "depot"] },
    feasible: true,
    total_distance: 42,
    total_distance_exact: "42",
    elapsed_seconds: 0.002,
    initial_distance: 50,
    initial_distance_exact: "50",
    improvement_percent: 16,
    exact_reference_distance: 40,
    exact_reference_distance_exact: "40",
    exact_reference_elapsed_seconds: 0.01,
    optimality_gap_percent: 5,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.health).mockResolvedValue({
    status: "ok",
    service: "q-supply-api",
  });
  vi.mocked(api.capabilities).mockResolvedValue({
    solvers: [],
    features: [],
    integrations: [
      {
        id: "qiskit-qaoa",
        status: "optional_dependency_missing",
        description: "Install requirements-qiskit.txt to enable Qiskit StatevectorSampler execution.",
      },
      {
        id: "qulacs-qaoa",
        status: "optional_dependency_missing",
        description: "Install requirements-quantum.txt to enable Qulacs QAOA execution.",
      },
      {
        id: "fujitsu-qarp",
        status: "not_configured_or_verified",
        description: "No QARP adapter or FX700 connection is configured.",
      },
    ],
    exact_cvrp_customer_limit: 10,
  });
  vi.mocked(api.instances).mockResolvedValue([
    {
      id: "synthetic-5",
      name: "Synthetic CVRP (5 customers)",
      customer_count: 5,
      seed: 2031,
      synthetic: true,
      exact_supported: true,
    },
    {
      id: "synthetic-11",
      name: "Synthetic CVRP (11 customers)",
      customer_count: 11,
      seed: 2037,
      synthetic: true,
      exact_supported: false,
    },
  ]);
  vi.mocked(api.network).mockResolvedValue({
    id: "synthetic-india-europe",
    name: "Synthetic network",
    synthetic: true,
    quantity_unit: "load_unit",
    cost_unit: "synthetic_cost_unit",
    time_unit: "day",
    carbon_unit: "kgCO2e",
    nodes: [],
    links: [],
    scenarios: [],
  });
  vi.mocked(api.globalNetwork).mockResolvedValue({
    id: "synthetic-global-network-v1",
    name: "Synthetic Global Network",
    synthetic: true,
    quantity_unit: "load_unit",
    cost_unit: "synthetic_cost_unit",
    time_unit: "day",
    carbon_unit: "kgCO2e",
    nodes: [],
    links: [],
    scenarios: [
      {
        id: "synthetic-suez-capacity-restriction",
        name: "Synthetic Suez capacity restriction",
        description: "Synthetic corridor capacity scenario.",
        synthetic: true,
        custom: false,
        closed_link_ids: [],
        unavailable_location_ids: [],
        capacity_overrides: { "sea-jebel-rotterdam": 3 },
        cost_multipliers: {},
        transit_time_multipliers: {},
      },
    ],
  });
  vi.mocked(api.globalShipments).mockResolvedValue([]);
  vi.mocked(api.globalDemos).mockResolvedValue([]);
  vi.mocked(api.globalScenarios).mockResolvedValue([
    {
      id: "synthetic-suez-capacity-restriction",
      name: "Synthetic Suez capacity restriction",
      description: "Synthetic corridor capacity scenario.",
      synthetic: true,
      custom: false,
      closed_link_ids: [],
      unavailable_location_ids: [],
      capacity_overrides: { "sea-jebel-rotterdam": 3 },
      cost_multipliers: {},
      transit_time_multipliers: {},
      transit_time_additions: {},
    },
  ]);
  vi.mocked(api.globalRoutes).mockResolvedValue([]);
  vi.mocked(api.routeIntelligence).mockRejectedValue(
    new Error("No route intelligence fixture configured"),
  );
  vi.mocked(api.globalOptimizations).mockResolvedValue({ items: [] });
  vi.mocked(api.createGlobalOptimization).mockRejectedValue(
    new Error("No global optimization fixture configured"),
  );
  vi.mocked(api.shipmentPosition).mockRejectedValue(
    new Error("No shipment position fixture configured"),
  );
  vi.mocked(api.createGlobalScenario).mockRejectedValue(
    new Error("No custom scenario fixture configured"),
  );
  vi.mocked(api.deleteGlobalScenario).mockResolvedValue(undefined);
  vi.mocked(api.optimizationReport).mockRejectedValue(new Error("No CSV fixture configured"));
  vi.mocked(api.optimizationPdfReport).mockRejectedValue(new Error("No PDF fixture configured"));
  vi.mocked(api.askDecisionQuestion).mockRejectedValue(new Error("No decision answer fixture configured"));
  vi.mocked(api.runs).mockResolvedValue({ items: [] });
});

afterEach(() => cleanup());

describe("QSupply dashboard interactions", () => {
  it("shows the official QSupply logo in the sidebar", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    expect(screen.getByRole("img", { name: "QSupply logo" })).toHaveAttribute(
      "src",
      "/qsupply-mark.png",
    );
  });

  it("shows unavailable Qulacs execution honestly when the optional backend is missing", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    await user.click(screen.getByRole("button", { name: /Quantum computing/ }));
    expect(
      await screen.findByText("Qulacs execution is unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run QAOA experiment" })).toBeDisabled();
    expect(screen.getByText("Not configured or verified")).toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
  });

  it("submits a real QAOA request and displays returned measured results", async () => {
    const user = userEvent.setup();
    vi.mocked(api.capabilities).mockResolvedValue({
      solvers: [],
      features: [],
      integrations: [
        { id: "qiskit-qaoa", status: "available", description: "QAOA on Qiskit 2.6.2 StatevectorSampler." },
        { id: "qulacs-qaoa", status: "optional_dependency_missing", description: "Install requirements-quantum.txt." },
        { id: "fujitsu-qarp", status: "not_configured_or_verified", description: "No QARP adapter." },
      ],
      exact_cvrp_customer_limit: 10,
    });
    const quantumResult: QuantumQAOAResult = {
      run_id: "qaoa-test-run",
      status: "completed",
      backend_name: "Qiskit StatevectorSampler (local state-vector simulator)",
      backend_id: "qiskit",
      backend_version: "2.6.2",
      algorithm_name: "Quantum Approximate Optimization Algorithm",
      algorithm_version: "1.0",
      example: "synthetic-import-export",
      synthetic: true,
      variable_count: 5,
      variable_order: ["x0", "x1", "x2", "x3", "x4"],
      depth: 1,
      optimizer: "spsa",
      optimizer_iterations: 1,
      shots_per_evaluation: 32,
      cost_normalization_scale: "20",
      final_sample_count: 32,
      total_sample_count: 160,
      random_seed: 2026,
      best_binary_assignment: { x0: 0, x1: 1, x2: 1, x3: 0, x4: 1 },
      best_spin_assignment: { x0: 1, x1: -1, x2: -1, x3: 1, x4: -1 },
      best_sample_frequency: 9,
      sample_frequencies: [{ bitstring: "01101", count: 9 }, { bitstring: "00000", count: 23 }],
      qubo_energy: "-43",
      full_energy: "17",
      ising_energy: "17",
      average_sampled_energy: "26/1",
      exact_reference_energy: "17",
      energy_gap_percent: 0,
      feasible: true,
      feasible_sample_rate: 0.5,
      decoded_solution: { S1: "B", S2: "A" },
      business_objective: "17",
      optimization_time_seconds: 0.02,
      circuit_execution_time_seconds: 0.01,
      exact_reference_time_seconds: 0.003,
      elapsed_seconds: 0.04,
    };
    vi.mocked(api.runQuantumQAOA).mockResolvedValue(quantumResult);

    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    await user.click(screen.getByRole("button", { name: /Quantum computing/ }));
    await user.selectOptions(screen.getByRole("combobox", { name: /Simulator backend/ }), "qiskit");
    await user.click(await screen.findByRole("button", { name: "Run QAOA experiment" }));

    expect(api.runQuantumQAOA).toHaveBeenCalledWith({
      example: "synthetic-import-export",
      backend: "qiskit",
      depth: 1,
      optimizer: "spsa",
      max_iterations: 5,
      shots: 128,
      random_seed: 2026,
      compare_exact: true,
    });
    expect(await screen.findByText("QAOA measured result")).toBeInTheDocument();
    expect(screen.getByText("S1: B")).toBeInTheDocument();
    expect(screen.getAllByText("17.000").length).toBeGreaterThan(1);
    expect(screen.getByText("Best observed")).toBeInTheDocument();
  });

  it("loads a runnable named global demo and its explicit assignment scope", async () => {
    const shipment = {
      id: "EXP-104", origin_id: "shanghai-hub", origin_name: "Shanghai",
      destination_id: "rotterdam-hub", destination_name: "Rotterdam", quantity: 2,
      quantity_unit: "load_unit", cargo_category: "Electronics", priority: 5,
      deadline: 24, deadline_unit: "day", delay_penalty_per_day: 18,
      maximum_transit_time: 60, departure_time: "2026-01-01T00:00:00Z", synthetic: true,
    };
    vi.mocked(api.globalShipments).mockResolvedValue([shipment]);
    vi.mocked(api.globalDemos).mockResolvedValue([{
      id: "demo-china-germany",
      name: "China → Germany: mode trade-off",
      business_problem: "Compare sea, air and rail routes for Shanghai electronics.",
      shipment_ids: [shipment.id],
      scenario_id: null,
      constraints: ["Synthetic shipment quantity: 2 load units"],
      alternatives: ["Sea", "Air", "Rail"],
      synthetic: true,
    }]);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    await user.click(within(screen.getByRole("navigation", { name: "Main navigation" })).getByRole("button", { name: /Network explorer/ }));
    expect(await screen.findByLabelText("Global demonstration scenario")).toHaveValue("demo-china-germany");
    expect(screen.getByLabelText("Shipment")).toHaveValue(shipment.id);
    expect((screen.getByLabelText("Joint assignment shipments") as HTMLSelectElement).selectedOptions[0]?.value).toBe(shipment.id);
    expect(screen.getByText("Compare sea, air and rail routes for Shanghai electronics.")).toBeInTheDocument();
    expect(screen.getByLabelText("Map region")).toBeInTheDocument();
    expect(screen.getByLabelText("Map country")).toBeInTheDocument();
  });

  it("formats exact rational distances in run history as readable decimals", async () => {
    const rationalRun: RunRecord = {
      ...completedRun,
      result: {
        ...completedRun.result!,
        total_distance: 171.967459644671,
        total_distance_exact: "96809073396948901/562949953421312",
      },
    };
    vi.mocked(api.runs).mockResolvedValue({ items: [rationalRun] });
    render(<App />);
    const formattedDistances = await screen.findAllByText("171.967 units");
    expect(formattedDistances.length).toBeGreaterThanOrEqual(1);
  });

  it("submits the selected solver and renders its returned route and metrics", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createRun).mockResolvedValue(completedRun);
    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    await user.click(
      within(
        screen.getByRole("navigation", { name: "Main navigation" }),
      ).getByRole("button", { name: /Optimization/ }),
    );
    await screen.findByText("Configure a CVRP run");
    await user.selectOptions(
      screen.getByLabelText("Solver"),
      "nearest-neighbor+2-opt",
    );
    await user.click(screen.getByRole("button", { name: /Run optimization/ }));
    await screen.findByText("42.000", { selector: "strong" });
    expect(api.createRun).toHaveBeenCalledWith({
      instance_id: "synthetic-5",
      solver: "nearest-neighbor+2-opt",
      include_exact_reference: false,
    });
    expect(screen.getByText("customer-1")).toBeInTheDocument();
    expect(screen.getByText("Validated")).toBeInTheDocument();
    expect(screen.getByText("2-opt improvement")).toBeInTheDocument();
    expect(screen.getByText("Initial heuristic")).toBeInTheDocument();
    expect(
      screen.getByText("50.000 units", { selector: "strong" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("40.000 units", { selector: "strong" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Final heuristic optimality gap"),
    ).toBeInTheDocument();
  });

  it("presents a depot-only route as an unused vehicle without altering the result", async () => {
    const user = userEvent.setup();
    const runWithUnusedVehicle: RunRecord = {
      ...completedRun,
      result: {
        ...completedRun.result!,
        routes: {
          "vehicle-1": ["depot", "customer-1", "depot"],
          "vehicle-2": ["depot", "depot"],
        },
      },
    };
    vi.mocked(api.createRun).mockResolvedValue(runWithUnusedVehicle);
    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    await user.click(
      within(
        screen.getByRole("navigation", { name: "Main navigation" }),
      ).getByRole("button", { name: /Optimization/ }),
    );
    await user.click(screen.getByRole("button", { name: /Run optimization/ }));
    expect(await screen.findByText("Unused vehicle")).toBeInTheDocument();
    expect(
      screen.getByText("No customers assigned · Depot → Depot"),
    ).toBeInTheDocument();
    expect(screen.getByText("customer-1")).toBeInTheDocument();
    expect(runWithUnusedVehicle.result?.routes["vehicle-2"]).toEqual([
      "depot",
      "depot",
    ]);
  });

  it("disables exact solver and exact comparison above the supported size", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    fireEvent.click(
      within(
        screen.getByRole("navigation", { name: "Main navigation" }),
      ).getByRole("button", { name: /Optimization/ }),
    );
    await screen.findByText("Configure a CVRP run");
    await userEvent
      .setup()
      .selectOptions(screen.getAllByRole("combobox")[0], "synthetic-11");
    expect(
      screen.getByRole("option", { name: /Exact Solver.*over limit/ }),
    ).toBeDisabled();
    expect(
      screen.getByRole("checkbox", { name: /Compare with exact reference/ }),
    ).toBeDisabled();
  });

  it("submits the configured synthetic recovery optimization to the API", async () => {
    const user = userEvent.setup();
    const scenarioId = "synthetic-suez-capacity-restriction";
    const route = {
      id: "route-shanghai-rotterdam",
      shipment_id: "EXP-104",
      location_ids: ["shanghai", "jebel-ali", "rotterdam"],
      link_ids: ["sea-shanghai-jebel", "sea-jebel-rotterdam"],
      legs: [],
      modes: ["sea"],
      distance_km: 10000,
      transit_time: 20,
      freight_cost: 213,
      carbon_kg: 10,
      resilience_exposure: 0.69,
      transfer_count: 0,
      bottleneck_capacity: 3,
      geometry: [[31.2, 121.5], [25.2, 55.3], [51.9, 4.5]] as [number, number][],
    };
    const assignment = {
      routes: { "EXP-104": route, "EXP-205": route },
      alternatives: { "EXP-104": [], "EXP-205": [] },
      metrics: {
        freight_cost: 426,
        delay_penalty: 0,
        total_cost: 426,
        delivery_time: 34.3,
        carbon_kg: 20,
        resilience_exposure: 1.38,
        weighted_objective: 0.51,
      },
      capacity_usage: { "sea-jebel-rotterdam": 2 },
      capacity_utilization: { "sea-jebel-rotterdam": 0.66 },
      method: "exact-enumeration-over-generated-candidates",
    };
    const optimization = {
      id: "global-run-123",
      status: "completed",
      created_at: "2026-11-06T00:00:00Z",
      scenario_id: scenarioId,
      weights: { cost: 40, delivery_time: 25, carbon: 20, resilience: 15 },
      result: {
        id: "global-run-123",
        status: "completed",
        synthetic: true,
        scenario_id: scenarioId,
        weights: { cost: 40, delivery_time: 25, carbon: 20, resilience: 15 },
        normalization_references: { cost: 500, delivery_time: 50, carbon: 30, resilience: 2 },
        recovery_feasible: true,
        failure_reason: null,
        baseline: assignment,
        recovery: assignment,
        algorithm: "bounded candidate route enumeration",
        optimality_scope: "Exact over generated candidate routes only",
      },
    } as unknown as GlobalOptimization;
    const shipment = {
      id: "EXP-104",
      origin_id: "shanghai",
      origin_name: "Shanghai",
      destination_id: "rotterdam",
      destination_name: "Rotterdam",
      quantity: 2,
      quantity_unit: "load_unit",
      cargo_category: "electronics",
      priority: 5,
      deadline: 25,
      deadline_unit: "day",
      delay_penalty_per_day: 20,
      maximum_transit_time: 35,
      departure_time: "2026-01-01T00:00:00Z",
      synthetic: true,
    };
    vi.mocked(api.routeIntelligence).mockResolvedValue({
      shipment_id: shipment.id,
      scenario_id: scenarioId,
      synthetic: true,
      recommended_route_id: route.id,
      assignment_route_id: route.id,
      baseline_route: route,
      routes: [route],
      rankings: { cost: [route.id], time: [route.id], carbon: [route.id], resilience: [route.id], balanced: [route.id] },
      analyses: {
        [route.id]: {
          route_id: route.id,
          total_cost: 213,
          delay_penalty: 0,
          deadline_met: true,
          deadline_slack_days: 5,
          balanced_score: 0.4,
          maximum_capacity_utilization: 2 / 3,
          route_feasible: true,
          feasibility_constraints: ["Individual link capacity checked."],
          capacity_constraints: [{ link_id: "sea-jebel-rotterdam", quantity: 2, capacity: 3, utilization: 2 / 3 }],
          transfer_count: 1,
          transfer_cost_modelled: false,
          handling_cost_modelled: false,
          cost_drivers: [{ link_id: "sea-jebel-rotterdam", mode: "sea", value: 100, unit: "cost units" }],
          time_drivers: [{ link_id: "sea-jebel-rotterdam", mode: "sea", value: 10, unit: "days" }],
          carbon_hotspots: [{ link_id: "sea-jebel-rotterdam", mode: "sea", value: 10, unit: "kgCO2e estimate" }],
          disruption_exposure: 0.1,
          recovery_recommendation: "Selected by joint assignment.",
          carbon_by_mode_kg: { sea: 10 },
          largest_cost_leg_id: "sea-jebel-rotterdam",
          largest_carbon_leg_id: "sea-jebel-rotterdam",
          delta_vs_baseline: { baseline_route_id: route.id, cost_savings: 0, cost_savings_percent: 0, time_savings_days: 0, carbon_savings_kg: 0, carbon_savings_percent: 0 },
          recommendation: "Recommended for the configured weighted profile.",
          advantages: ["Meets the modeled deadline."],
          tradeoffs: ["No measured reliability data."],
          analysis_type: "deterministic_rule_based",
          uses_llm: false,
        },
      },
      recovery_feasible: true,
      normalization_references: { cost: 500, delivery_time: 50, carbon: 30, resilience: 2 },
      assumptions: ["Synthetic demonstration data."],
    } as RouteIntelligence);
    vi.mocked(api.globalShipments).mockResolvedValue([shipment]);
    vi.mocked(api.createGlobalOptimization).mockResolvedValue(optimization);
    vi.mocked(api.askDecisionQuestion).mockResolvedValue({
      run_id: optimization.id,
      shipment_id: shipment.id,
      route_id: route.id,
      answer: "The synthetic carbon estimate is 10.00 kgCO2e.",
      analysis_type: "deterministic_fact_lookup",
      uses_llm: false,
      source_data: { carbon_estimate_kgco2e: 10, route_id: route.id },
    });

    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    await user.click(
      within(screen.getByRole("navigation", { name: "Main navigation" })).getByRole("button", { name: /Network explorer/ }),
    );
    await screen.findByTestId("global-map");
    expect(await screen.findByLabelText("Shipment")).toHaveValue("EXP-104");
    await user.click(screen.getByRole("button", { name: "Run recovery optimization" }));
    expect(api.createGlobalOptimization).toHaveBeenCalledWith({
      scenario_id: scenarioId,
      weights: { cost: 40, delivery_time: 25, carbon: 20, resilience: 15 },
      max_routes: 8,
      shipment_ids: [shipment.id],
    });
    expect(await screen.findByText("Recovery feasible")).toBeInTheDocument();
    expect(await screen.findByText("Recommended for the configured weighted profile.")).toBeInTheDocument();
    expect(screen.getByText("DETERMINISTIC ROUTE INTELLIGENCE · NO LLM")).toBeInTheDocument();
    expect(screen.getByText("Estimated carbon by mode")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download CSV report" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download PDF summary" })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("e.g. What is driving its carbon estimate?"), "What is the carbon estimate?");
    await user.click(screen.getByRole("button", { name: "Ask QSupply" }));
    expect(await screen.findByText("The synthetic carbon estimate is 10.00 kgCO2e.")).toBeInTheDocument();
    expect(api.askDecisionQuestion).toHaveBeenCalledWith(optimization.id, {
      shipment_id: shipment.id,
      route_id: route.id,
      question: "What is the carbon estimate?",
    });
    expect(screen.getByText("Shipment movement · simulated")).toBeInTheDocument();
  });

  it("applies a predefined multi-objective profile with weights totaling 100", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    await user.click(
      within(screen.getByRole("navigation", { name: "Main navigation" })).getByRole("button", { name: /Network explorer/ }),
    );
    await user.selectOptions(await screen.findByLabelText("Objective profile"), "cost-priority");
    expect(await screen.findByRole("spinbutton", { name: /^cost/ })).toHaveValue(70);
    expect(screen.getByRole("spinbutton", { name: /delivery time/ })).toHaveValue(10);
    expect(screen.getByRole("spinbutton", { name: /carbon/ })).toHaveValue(10);
    expect(screen.getByRole("spinbutton", { name: /resilience/ })).toHaveValue(10);
    expect(screen.getByText("Objective weights: 100% · valid")).toBeInTheDocument();
  });
});
