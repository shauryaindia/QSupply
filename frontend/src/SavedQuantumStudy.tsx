import { useState } from "react";
import study from "../../benchmarks/quantum/study.json";

const names: Record<string, string> = {
  "exact-qubo": "Exact QUBO",
  "classical-assignment": "Classical route assignment",
  qiskit: "Qiskit simulator",
  qulacs: "Qulacs simulator",
};

function metric(value: number | null, unit = "") {
  return value === null ? "—" : value.toLocaleString(undefined, { maximumSignificantDigits: 4 }) + unit;
}

export default function SavedQuantumStudy() {
  const [id, setId] = useState(study.cases[0].id);
  const entry = study.cases.find(item => item.id === id)!;
  return <section className="panel" aria-label="Saved quantum benchmark">
    <div className="panel-heading"><div>
      <h2>Saved benchmark results</h2>
      <p>Compare measured solver outcomes on {study.cases.length} synthetic shipment portfolios.</p>
    </div></div>
    <label>Benchmark instance <select value={id} onChange={event => setId(event.target.value)}>
      {study.cases.map(item => <option key={item.id} value={item.id}>{item.id} · {item.variables} bits · {item.profile}</option>)}
    </select></label>
    <p>{entry.shipments.length} shipments · {entry.candidates} candidate routes · {entry.variables} binary variables · {entry.profile} objective</p>
    {entry.reason && <p>{entry.reason}</p>}
    {entry.selected && <p>QAOA depth {study.depth} · {study.optimizer.toUpperCase()} · {study.iterations} iterations · {study.shots} shots per evaluation · seeds {study.seeds.join(", ")}</p>}
    <div className="table-scroll" role="region" aria-label="Saved solver comparison" tabIndex={0}>
      <table className="quantum-sample-table"><thead><tr>
        <th>Method</th><th>Completed</th><th>Feasible plans</th><th>Optimal trials</th><th>Best objective</th><th>Mean feasible gap</th><th>Mean solver time</th>
      </tr></thead><tbody>{entry.methods.map(m => <tr key={m.method}>
        <td>{names[m.method] ?? m.method}</td><td>{m.completed}/{m.trials}{m.completed < m.trials && " · " + Object.keys(m.outcomes).filter(s => s !== "completed").join(", ")}</td>
        <td>{m.feasibility_rate === null ? "—" : metric(m.feasibility_rate * 100, "%")}</td>
        <td>{m.optimal_rate === null ? "—" : metric(m.optimal_rate * 100, "%")}</td>
        <td>{metric(m.best_objective)}</td><td>{metric(m.mean_gap_percent, "%")}</td><td>{metric(m.mean_seconds, " s")}</td>
      </tr>)}</tbody></table>
    </div>
    <p className="table-scroll-hint">Scroll the table horizontally to see all comparison metrics.</p>
    <p>Lower objectives are better. Optimal trials reached the best feasible objective over the generated routes. A dash means the measure is unavailable or inapplicable.</p>
  </section>;
}
