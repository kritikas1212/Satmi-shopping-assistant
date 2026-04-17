"use client";

import { PieChart, Pie, Cell, Tooltip } from "recharts";

export default function CategoryPieChart({ data }: { data: any[] }) {
  if (!data || data.length === 0) {
    return <span className="text-sm text-[#475569]">No chart data available.</span>;
  }

  // Predefine standard intent colors for consistency
  const INTENT_COLORS: Record<string, string> = {
    "Product Discovery": "#7A1E1E",
    "Order Tracking": "#B45309",
    "Policy & FAQ": "#1D4ED8",
    "Account & Login": "#0F766E",
    "General Inquiry": "#475569",
  };

  const getFallbackColor = (index: number) => {
    const list = ["#7A1E1E", "#B45309", "#0F766E", "#1D4ED8", "#475569"];
    return list[index % list.length];
  };

  return (
    <div className="flex h-full w-full items-center justify-center">
      <PieChart width={300} height={200}>
        <Pie
          data={data}
          dataKey="count"
          nameKey="intent"
          cx="50%"
          cy="50%"
          outerRadius={65}
          fill="#8884d8"
          label
        >
          {data.map((entry, index) => (
             <Cell key={`cell-${index}`} fill={INTENT_COLORS[entry.intent] || getFallbackColor(index)} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    </div>
  );
}
