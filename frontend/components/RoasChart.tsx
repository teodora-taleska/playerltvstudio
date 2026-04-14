"use client";

import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
  type ChartOptions,
} from "chart.js";
import type { CampaignResult } from "@/lib/api";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const COLORS: Record<string, string> = {
  broad_acquisition: "#6366f1",
  whales_only: "#e11d48",
  retargeting: "#10b981",
};

// Short labels for mobile x-axis
const SHORT_LABELS: Record<string, string> = {
  broad_acquisition: "Broad",
  whales_only: "Whales",
  retargeting: "Retarget",
};

export default function RoasChart({ campaigns }: { campaigns: CampaignResult[] }) {
  const data = {
    labels: campaigns.map((c) => SHORT_LABELS[c.campaign_name] ?? c.campaign_name),
    datasets: [
      {
        label: "ROAS",
        data: campaigns.map((c) => c.roas),
        backgroundColor: campaigns.map((c) => COLORS[c.campaign_name] ?? "#6b7280"),
        borderRadius: 6,
        borderSkipped: false,
      },
    ],
  };

  const options: ChartOptions<"bar"> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => {
            // Show full name in tooltip
            const idx = items[0].dataIndex;
            return campaigns[idx].campaign_name.replace(/_/g, " ");
          },
          label: (ctx) => ` ROAS: ${(ctx.raw as number).toFixed(2)}x`,
          afterLabel: (ctx) => {
            const c = campaigns[ctx.dataIndex];
            return [
              ` Spend: $${c.spend.toLocaleString()}`,
              ` Revenue: $${c.total_predicted_revenue_90d.toLocaleString()}`,
              ` Players: ${c.n_players.toLocaleString()}`,
            ].join("\n");
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: "#9ca3af", font: { size: 12 } },
        grid: { color: "#1f2937" },
      },
      y: {
        // Add top padding so break-even label isn't clipped
        suggestedMax: Math.max(...campaigns.map((c) => c.roas)) * 1.2,
        ticks: {
          color: "#9ca3af",
          callback: (v) => `${v}x`,
        },
        grid: { color: "#1f2937" },
      },
    },
  };

  // Break-even reference line at ROAS = 1
  const breakEvenPlugin = {
    id: "breakEvenLine",
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    afterDraw(chart: any) {
      const { ctx, chartArea, scales } = chart;
      if (!scales.y) return;
      const y = scales.y.getPixelForValue(1);
      if (y < chartArea.top || y > chartArea.bottom) return;
      ctx.save();
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = "#6b7280";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(chartArea.left, y);
      ctx.lineTo(chartArea.right, y);
      ctx.stroke();
      ctx.restore();
      ctx.save();
      ctx.fillStyle = "#9ca3af";
      ctx.font = "11px sans-serif";
      // Place label above the line with breathing room
      ctx.fillText("Break-even", chartArea.right - 80, y - 8);
      ctx.restore();
    },
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <div className="flex items-start justify-between mb-5 gap-2">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          ROAS by Campaign
        </h2>
        <span className="text-xs text-gray-600 hidden sm:block">Tap a bar for details</span>
        <span className="text-xs text-gray-600 sm:hidden">Tap bars for details</span>
      </div>
      {/* Fixed height so chart is tall enough on all screens */}
      <div className="h-64 sm:h-80">
        <Bar data={data} options={options} plugins={[breakEvenPlugin]} />
      </div>
    </div>
  );
}
