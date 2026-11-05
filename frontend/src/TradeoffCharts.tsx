import type { CandidateRoute, RouteIntelligence } from "./api/client";

function Scatter({
  title,
  xLabel,
  yLabel,
  routes,
  analyses,
  selectedRouteId,
  field,
}: {
  title: string;
  xLabel: string;
  yLabel: string;
  routes: CandidateRoute[];
  analyses: RouteIntelligence["analyses"];
  selectedRouteId: string | null;
  field: "transit_time" | "carbon_kg";
}) {
  const width = 330;
  const height = 190;
  const pad = { left: 42, right: 12, top: 22, bottom: 35 };
  const xs = routes.map((route) => analyses[route.id]?.total_cost ?? route.freight_cost);
  const ys = routes.map((route) => route[field]);
  const xMin = Math.min(...xs, 0);
  const xMax = Math.max(...xs, xMin + 1);
  const yMin = Math.min(...ys, 0);
  const yMax = Math.max(...ys, yMin + 1);
  const x = (value: number) => pad.left + ((value - xMin) / (xMax - xMin)) * (width - pad.left - pad.right);
  const y = (value: number) => height - pad.bottom - ((value - yMin) / (yMax - yMin)) * (height - pad.top - pad.bottom);

  return (
    <figure className="tradeoff-chart">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title}: ${routes.length} generated route alternatives`}>
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} className="tradeoff-axis" />
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} className="tradeoff-axis" />
        {routes.map((route, index) => {
          const routeX = analyses[route.id]?.total_cost ?? route.freight_cost;
          const routeY = route[field];
          const selected = selectedRouteId === route.id;
          return <g key={route.id} className={selected ? "tradeoff-point selected" : "tradeoff-point"}>
            <circle cx={x(routeX)} cy={y(routeY)} r={selected ? 6 : 4} />
            <title>{`Route ${index + 1}: ${routeX.toFixed(1)} cost units, ${routeY.toFixed(1)} ${field === "carbon_kg" ? "kgCO2e" : "days"}`}</title>
          </g>;
        })}
        <text x={width / 2} y={height - 7} textAnchor="middle">{xLabel}</text>
        <text x={12} y={height / 2} textAnchor="middle" transform={`rotate(-90 12 ${height / 2})`}>{yLabel}</text>
      </svg>
      <div className="tradeoff-scale"><span>{xMin.toFixed(1)}</span><span>{xMax.toFixed(1)} · x-axis cost units</span></div>
    </figure>
  );
}

export default function TradeoffCharts({
  routes,
  analyses,
  selectedRouteId,
}: {
  routes: CandidateRoute[];
  analyses: RouteIntelligence["analyses"];
  selectedRouteId: string | null;
}) {
  if (routes.length < 2) return null;
  return <div className="tradeoff-chart-grid">
    <Scatter title="Cost versus delivery time" xLabel="Modeled total cost" yLabel="Transit days" routes={routes} analyses={analyses} selectedRouteId={selectedRouteId} field="transit_time" />
    <Scatter title="Cost versus estimated carbon" xLabel="Modeled total cost" yLabel="kgCO2e estimate" routes={routes} analyses={analyses} selectedRouteId={selectedRouteId} field="carbon_kg" />
  </div>;
}
