"use client";

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

export default function CategoryPieChart({ data }: { data: any[] }) {
  if (!data || data.length === 0) {
    return <span className="text-sm text-[#475569]">No chart data available.</span>;
  }

  const getColor = (index: number) => {
    const list = [
      "#7A1E1E", "#B45309", "#0F766E", "#1D4ED8", "#475569",
      "#D97706", "#DC2626", "#EA580C", "#65A30D", "#16A34A",
      "#059669", "#0891B2", "#0284C7", "#2563EB", "#4F46E5",
      "#7C3AED", "#9333EA", "#C026D3", "#DB2777", "#E11D48"
    ];
    return list[index % list.length];
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-md border border-white/20 bg-white/80 backdrop-blur-md p-3 shadow-lg">
          <p className="text-sm font-semibold text-[#1A252F]">{`${payload[0].name}`}</p>
          <p className="text-xs text-[#475569] mt-1">{`${payload[0].value} chats`}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex h-full w-full items-center justify-center min-h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="count"
            nameKey="category"
            cx="50%"
            cy="50%"
            outerRadius={80}
            innerRadius={50}
            fill="#8884d8"
            paddingAngle={2}
          >
            {data.map((entry, index) => (
               <Cell key={`cell-${index}`} fill={getColor(index)} stroke="rgba(255,255,255,0.5)" strokeWidth={2} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
