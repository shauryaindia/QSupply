import { describe, expect, it } from "vitest";
import { corridorDisplayName, readableUnit, scenarioDisplayName } from "./presentation";
import type { GlobalOptimization, NetworkResponse } from "./api/client";

describe("enterprise presentation labels", () => {
  it("uses readable units for modeled quantities", () => {
    expect(readableUnit("synthetic_cost_unit", "cost")).toBe("cost units");
    expect(readableUnit("day", "time")).toBe("days");
    expect(readableUnit("kgCO2e", "carbon")).toBe("kg CO₂e");
    expect(readableUnit("load_unit", "quantity")).toBe("load units");
  });

  it("prefers scenario names and humanizes legacy identifiers", () => {
    const run = {
      scenario_id: "synthetic-china-us-port-closure",
      result: { scenario_snapshot: { name: "China–US port disruption" } },
    } as GlobalOptimization;
    expect(scenarioDisplayName(run)).toBe("China–US port disruption");
    expect(scenarioDisplayName({ ...run, result: null } as GlobalOptimization)).toBe(
      "China US Port Closure",
    );
    expect(scenarioDisplayName({ ...run, scenario_id: null } as GlobalOptimization)).toBe(
      "Baseline network",
    );
  });

  it("shows corridor endpoints instead of internal link IDs", () => {
    const network = {
      nodes: [
        { id: "origin", label: "Mumbai Port" },
        { id: "destination", label: "Jebel Ali" },
      ],
      links: [{ id: "sea-mumbai-jebel-ali", source: "origin", target: "destination", mode: "sea" }],
    } as NetworkResponse;
    expect(corridorDisplayName(network, "sea-mumbai-jebel-ali")).toBe(
      "Mumbai Port → Jebel Ali · sea",
    );
    expect(corridorDisplayName(network, "retired-link")).toBe(
      "Unknown corridor (retired-link)",
    );
  });
});
