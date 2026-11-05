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
import { api, type RunRecord } from "./api/client";

vi.mock("./api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api/client")>();
  return {
    ...original,
    api: {
      health: vi.fn(),
      capabilities: vi.fn(),
      instances: vi.fn(),
      network: vi.fn(),
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
        status: "not_implemented",
        description: "No Qiskit or QAOA integration is implemented.",
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
  vi.mocked(api.runs).mockResolvedValue({ items: [] });
});

afterEach(() => cleanup());

describe("QSupply dashboard interactions", () => {
  it("shows unverified quantum integrations rather than a fabricated connection", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Control tower", level: 1 });
    await user.click(screen.getByRole("button", { name: /Quantum computing/ }));
    expect(
      await screen.findByText("Quantum execution is unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByText("Not configured or verified")).toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
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
    await screen.findByText("42", { selector: "strong" });
    expect(api.createRun).toHaveBeenCalledWith({
      instance_id: "synthetic-5",
      solver: "nearest-neighbor+2-opt",
      include_exact_reference: false,
    });
    expect(screen.getByText("customer-1")).toBeInTheDocument();
    expect(screen.getByText("Validated")).toBeInTheDocument();
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
});
