"use client";

import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { DashboardDailyActivity } from "@/lib/satmiApi";

export default function UserActivityChart({ data }: { data: DashboardDailyActivity[] }) {
  if (!data || data.length === 0) {
    return <span className="text-sm text-[#475569]">No chart data available.</span>;
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-md border border-[#D7C5B5] bg-white p-3 shadow-lg">
          <p className="text-sm font-semibold text-[#1A252F]">{label}</p>
          <p className="text-xs text-[#7A1E1E] font-medium mt-1">{`${payload[0].value} conversations`}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex h-full w-full items-center justify-center min-h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{
            top: 10,
            right: 10,
            left: -20,
            bottom: 0,
          }}
        >
          <defs>
            <linearGradient id="colorSessions" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#7A1E1E" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#7A1E1E" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2D8D0" />
          <XAxis 
            dataKey="date" 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: '#64748B', fontSize: 12 }} 
            tickFormatter={(val) => {
                const d = new Date(val);
                return `${d.getMonth()+1}/${d.getDate()}`;
            }}
            dy={10}
          />
          <YAxis 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: '#64748B', fontSize: 12 }} 
            allowDecimals={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area 
            type="monotone" 
            dataKey="sessions" 
            stroke="#7A1E1E" 
            strokeWidth={3}
            fillOpacity={1} 
            fill="url(#colorSessions)" 
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
