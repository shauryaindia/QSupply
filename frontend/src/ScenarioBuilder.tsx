import { useMemo, useState, type FormEvent } from "react";
import type { GlobalOptimization } from "./api/client";
import { api, formatNumber, type NetworkResponse } from "./api/client";
import { readableUnit, scenarioDisplayName } from "./presentation";
import type { components } from "./api/generated";

type Scenario = components["schemas"]["NetworkScenario"];
type LinkChanges = {
  capacity?: number;
  costMultiplier?: number;
  timeMultiplier?: number;
  customsDelay?: number;
};

function selectedPlan(run: GlobalOptimization) {
  if (!run.result) return null;
  return run.scenario_id
    ? run.result.recovery_feasible
      ? run.result.recovery
      : null
    : run.result.baseline;
}

export default function ScenarioBuilder({
  network,
  scenarios,
  runs,
  selectedScenarioId,
  onScenariosChange,
  onUseScenario,
}: {
  network: NetworkResponse;
  scenarios: Scenario[];
  runs: GlobalOptimization[];
  selectedScenarioId: string;
  onScenariosChange: (scenarios: Scenario[]) => void;
  onUseScenario: (scenarioId: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [closedLinks, setClosedLinks] = useState<string[]>([]);
  const [unavailableLocations, setUnavailableLocations] = useState<string[]>([]);
  const [targetLink, setTargetLink] = useState(network.links[0]?.id ?? "");
  const [capacity, setCapacity] = useState("");
  const [costMultiplier, setCostMultiplier] = useState("");
  const [timeMultiplier, setTimeMultiplier] = useState("");
  const [customsDelay, setCustomsDelay] = useState("");
  const [linkChanges, setLinkChanges] = useState<Record<string, LinkChanges>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);

  const completedRuns = useMemo(
    () => runs.filter((run) => run.status === "completed" && run.result),
    [runs],
  );
  const compareRuns = comparisonIds
    .map((id) => completedRuns.find((run) => run.id === id))
    .filter((run): run is GlobalOptimization => Boolean(run));
  const plans = compareRuns.map((run) => ({ run, plan: selectedPlan(run) }));

  const applyLinkChanges = () => {
    if (!targetLink) return;
    setLinkChanges((current) => ({
      ...current,
      [targetLink]: {
        ...(capacity !== "" ? { capacity: Number(capacity) } : {}),
        ...(costMultiplier !== "" ? { costMultiplier: Number(costMultiplier) } : {}),
        ...(timeMultiplier !== "" ? { timeMultiplier: Number(timeMultiplier) } : {}),
        ...(customsDelay !== "" ? { customsDelay: Number(customsDelay) } : {}),
      },
    }));
    setCapacity("");
    setCostMultiplier("");
    setTimeMultiplier("");
    setCustomsDelay("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const capacityOverrides: Record<string, number> = {};
    const costMultipliers: Record<string, number> = {};
    const transitTimeMultipliers: Record<string, number> = {};
    const transitTimeAdditions: Record<string, number> = {};
    for (const [linkId, change] of Object.entries(linkChanges)) {
      if (change.capacity !== undefined) capacityOverrides[linkId] = change.capacity;
      if (change.costMultiplier !== undefined) costMultipliers[linkId] = change.costMultiplier;
      if (change.timeMultiplier !== undefined) transitTimeMultipliers[linkId] = change.timeMultiplier;
      if (change.customsDelay !== undefined) transitTimeAdditions[linkId] = change.customsDelay;
    }
    try {
      const scenario = await api.createGlobalScenario({
        name,
        description,
        closed_link_ids: closedLinks,
        unavailable_location_ids: unavailableLocations,
        capacity_overrides: capacityOverrides,
        cost_multipliers: costMultipliers,
        transit_time_multipliers: transitTimeMultipliers,
        transit_time_additions: transitTimeAdditions,
      });
      onScenariosChange([scenario, ...scenarios]);
      onUseScenario(scenario.id);
      setName("");
      setDescription("");
      setClosedLinks([]);
      setUnavailableLocations([]);
      setLinkChanges({});
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save scenario.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (scenario: Scenario) => {
    setError(null);
    try {
      await api.deleteGlobalScenario(scenario.id);
      onScenariosChange(scenarios.filter((item) => item.id !== scenario.id));
      if (selectedScenarioId === scenario.id) onUseScenario("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete scenario.");
    }
  };

  const switchComparison = (id: string) => {
    setComparisonIds((current) => current.includes(id)
      ? current.filter((item) => item !== id)
      : current.length < 2 ? [...current, id] : [current[1], id]);
  };

  const linkLabel = (id: string) => {
    const link = network.links.find((item) => item.id === id);
    const source = network.nodes.find((item) => item.id === link?.source)?.label ?? link?.source;
    const target = network.nodes.find((item) => item.id === link?.target)?.label ?? link?.target;
    return `${source} → ${target} · ${link?.mode ?? "unknown mode"}`;
  };

  return (
    <section className="scenario-workspace" aria-label="Custom scenario builder">
      <div className="scenario-builder-grid">
        <div className="scenario-builder-card">
          <h2>Create a synthetic scenario</h2>
          <p>Saved scenarios are immutable inputs. Create a new version to preserve a reproducible history.</p>
          <form onSubmit={(event) => void submit(event)}>
            <label>Scenario name<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={100} /></label>
            <label>Description<input value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} /></label>
            <div className="scenario-form-grid">
              <label>Close transport links<select multiple value={closedLinks} onChange={(event) => setClosedLinks(Array.from(event.target.selectedOptions, (option) => option.value))}>{network.links.map((link) => <option key={link.id} value={link.id}>{linkLabel(link.id)}</option>)}</select><small>Choose multiple routes or corridors to close.</small></label>
              <label>Unavailable locations<select multiple value={unavailableLocations} onChange={(event) => setUnavailableLocations(Array.from(event.target.selectedOptions, (option) => option.value))}>{network.nodes.map((node) => <option key={node.id} value={node.id}>{node.label} · {node.kind}</option>)}</select><small>Closing a port removes links touching that location.</small></label>
            </div>
            <div className="scenario-link-editor">
              <label>Link for capacity/cost/time changes<select value={targetLink} onChange={(event) => setTargetLink(event.target.value)}>{network.links.map((link) => <option key={link.id} value={link.id}>{linkLabel(link.id)}</option>)}</select></label>
              <div className="scenario-form-grid scenario-number-grid">
                <label>Capacity limit ({readableUnit(network.quantity_unit, "quantity")})<input type="number" min="0" max={network.links.find((link) => link.id === targetLink)?.capacity ?? undefined} value={capacity} onChange={(event) => setCapacity(event.target.value)} placeholder="No change" /></label>
                <label>Freight cost multiplier<input type="number" min="1" step="0.01" value={costMultiplier} onChange={(event) => setCostMultiplier(event.target.value)} placeholder="e.g. 1.2" /></label>
                <label>Transit time multiplier<input type="number" min="1" step="0.01" value={timeMultiplier} onChange={(event) => setTimeMultiplier(event.target.value)} placeholder="e.g. 1.15" /></label>
                <label>Customs delay ({readableUnit(network.time_unit, "time")})<input type="number" min="0" step="0.1" value={customsDelay} onChange={(event) => setCustomsDelay(event.target.value)} placeholder="No change" /></label>
              </div>
              <button className="secondary-button" type="button" onClick={applyLinkChanges}>Add / update link changes</button>
              {Object.entries(linkChanges).length > 0 && <ul className="scenario-change-list">{Object.entries(linkChanges).map(([id, change]) => <li key={id}><span>{linkLabel(id)} · {Object.entries(change).map(([key, value]) => `${key} ${value}`).join(" · ")}</span><button type="button" aria-label={`Remove changes for ${id}`} onClick={() => setLinkChanges((current) => Object.fromEntries(Object.entries(current).filter(([key]) => key !== id)))}>Remove</button></li>)}</ul>}
            </div>
            {error && <p role="alert" className="scenario-error">{error}</p>}
            <button className="primary-button" type="submit" disabled={saving || !name.trim()}>{saving ? "Saving scenario…" : "Save scenario"}</button>
          </form>
        </div>

        <div className="scenario-builder-card">
          <h2>Saved scenarios</h2>
          <p>Choose a scenario in the Network Explorer, then run the same bounded route assignment against it.</p>
          <ul className="saved-scenario-list">{scenarios.map((scenario) => <li key={scenario.id} className={selectedScenarioId === scenario.id ? "active" : ""}>
            <div><strong>{scenario.name || scenario.id}</strong><small>{scenario.description || "No description"} · {scenario.custom ? "Custom synthetic scenario" : "Built-in synthetic scenario"}</small><small>{scenario.closed_link_ids.length} closed links · {scenario.unavailable_location_ids.length} unavailable locations · {Object.keys(scenario.capacity_overrides).length + Object.keys(scenario.cost_multipliers).length + Object.keys(scenario.transit_time_multipliers).length + Object.keys(scenario.transit_time_additions ?? {}).length} link overrides</small></div>
            <button className="secondary-button" type="button" onClick={() => onUseScenario(scenario.id)}>{selectedScenarioId === scenario.id ? "Selected" : "Use scenario"}</button>
            {scenario.custom && <button className="text-button" type="button" onClick={() => void remove(scenario)}>Delete</button>}
          </li>)}</ul>
        </div>
      </div>

      <div className="scenario-builder-card scenario-comparison-card">
        <h2>Compare saved runs</h2>
        <p>Select up to two completed runs. Metrics come from their persisted baseline or jointly feasible scenario assignments.</p>
        <div className="scenario-run-select">{completedRuns.map((run) => <label key={run.id}><input type="checkbox" checked={comparisonIds.includes(run.id)} onChange={() => switchComparison(run.id)} />{scenarioDisplayName(run)} · {run.id.slice(0, 8)}</label>)}</div>
        {plans.length > 0 && <div className="table-scroll"><table><thead><tr><th>Run / scenario</th><th>Recovery</th><th>Total cost</th><th>Delivery time</th><th>Carbon estimate</th><th>Exposure</th></tr></thead><tbody>{plans.map(({ run, plan }) => <tr key={run.id}><td>{scenarioDisplayName(run)}</td><td>{run.scenario_id ? plan ? "Feasible" : "Infeasible" : "Baseline"}</td><td>{plan ? formatNumber(plan.metrics.total_cost, 1) : "—"} {readableUnit(network.cost_unit, "cost")}</td><td>{plan ? formatNumber(plan.metrics.delivery_time) : "—"} {readableUnit(network.time_unit, "time")}</td><td>{plan ? formatNumber(plan.metrics.carbon_kg) : "—"} {readableUnit(network.carbon_unit, "carbon")} est.</td><td>{plan ? formatNumber(plan.metrics.resilience_exposure, 2) : "—"}</td></tr>)}</tbody></table></div>}
        {plans.length === 2 && plans.every(({ plan }) => plan) && <div className="scenario-delta-grid"><div><span>Cost difference</span><strong>{formatNumber(plans[1].plan!.metrics.total_cost - plans[0].plan!.metrics.total_cost, 1)} {readableUnit(network.cost_unit, "cost")}</strong><small>Second selected run minus first</small></div><div><span>Time difference</span><strong>{formatNumber(plans[1].plan!.metrics.delivery_time - plans[0].plan!.metrics.delivery_time)} {readableUnit(network.time_unit, "time")}</strong><small>Summed modeled shipment transit time</small></div><div><span>Carbon difference</span><strong>{formatNumber(plans[1].plan!.metrics.carbon_kg - plans[0].plan!.metrics.carbon_kg)} {readableUnit(network.carbon_unit, "carbon")}</strong><small>Synthetic estimate; second minus first</small></div></div>}
        {!completedRuns.length && <p className="scenario-empty">No completed runs yet. Run a baseline or saved scenario in the Network Explorer to compare results.</p>}
      </div>
      <p className="synthetic-note"><span>i</span><span>Scenario controls modify an immutable overlay. The baseline network is never rewritten. Capacity, cost and time comparisons remain based on the synthetic network inputs.</span></p>
    </section>
  );
}
