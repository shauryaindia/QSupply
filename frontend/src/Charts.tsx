import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type ChartDatum = { label: string; value: number };

export default function Charts({
  data,
  variant,
}: {
  data: ChartDatum[];
  variant: "history" | "comparison";
}) {
  const history = variant === "history";
  return (
    <ResponsiveContainer width="100%" height={history ? 226 : 195}>
      <BarChart data={data} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid
          strokeDasharray="3 3"
          vertical={false}
          stroke="#edf0f4"
        />
        <XAxis
          dataKey="label"
          tickLine={false}
          axisLine={false}
          tick={{ fill: "#8792a2", fontSize: 11 }}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          tick={{ fill: "#8792a2", fontSize: 11 }}
          width={42}
        />
        <Tooltip formatter={(value) => [`${value} units`, "Route distance"]} />
        <Bar
          dataKey="value"
          fill="#237d73"
          radius={[5, 5, 0, 0]}
          maxBarSize={48}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
