// Tiny inline trend line used in route / airline rows.

import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { useChartTheme } from "../hooks/useChartTheme";

export function Sparkline({
  data,
  color,
  height = 32,
}: {
  data: (number | null)[];
  color?: string;
  height?: number;
}) {
  const t = useChartTheme();
  const stroke = color ?? t.brand;
  const points = data.map((v, i) => ({ i, v }));
  return (
    <div style={{ width: 96, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <defs>
            <linearGradient id={`spark-${stroke.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={stroke} stopOpacity={0.35} />
              <stop offset="95%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={stroke}
            strokeWidth={1.6}
            fill={`url(#spark-${stroke.replace("#", "")})`}
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
