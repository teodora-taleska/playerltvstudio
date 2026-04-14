"use client";

import { Doughnut } from "react-chartjs-2";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import type { SegmentSummary } from "@/lib/api";

ChartJS.register(ArcElement, Tooltip, Legend);

const COLORS = ["#10b981", "#6366f1", "#6b7280"];
const LABELS: Record<string, string> = {
  high_ltv: "High LTV",
  mid_ltv: "Mid LTV",
  low_ltv: "Low LTV",
};

export default function SegmentDonut({ segments }: { segments: SegmentSummary[] }) {
  const ordered = ["high_ltv", "mid_ltv", "low_ltv"]
    .map((s) => segments.find((x) => x.segment === s))
    .filter(Boolean) as SegmentSummary[];

  const data = {
    labels: ordered.map((s) => LABELS[s.segment]),
    datasets: [
      {
        data: ordered.map((s) => s.count),
        backgroundColor: COLORS,
        borderColor: "#111827",
        borderWidth: 3,
        hoverOffset: 6,
      },
    ],
  };

  const options = {
    cutout: "68%",
    plugins: {
      legend: {
        position: "bottom" as const,
        labels: {
          color: "#9ca3af",
          padding: 16,
          font: { size: 12 },
        },
      },
      tooltip: {
        callbacks: {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          label: (ctx: any) => {
            const seg = ordered[ctx.dataIndex];
            return ` ${ctx.label}: ${seg.count} players (${seg.pct_of_players}%)`;
          },
        },
      },
    },
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
        Player Segments
      </h2>
      <div className="max-w-xs mx-auto">
        <Doughnut data={data} options={options} />
      </div>
      <div className="mt-4 space-y-2">
        {ordered.map((s, i) => (
          <div key={s.segment} className="flex justify-between text-sm">
            <span className="flex items-center gap-2 text-gray-400">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full"
                style={{ background: COLORS[i] }}
              />
              {LABELS[s.segment]}
            </span>
            <span className="text-gray-300">
              avg ${s.avg_ltv_90d.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
