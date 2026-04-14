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

export default function RoasChart({ campaigns }: { campaigns: CampaignResult[] }) {
  const data = {
    labels: campaigns.map((c) => c.campaign_name.replace("_", " ")),
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
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => ` ROAS: ${(ctx.raw as number).toFixed(2)}x`,
        },
      },
    },
    scales: {
      x: {
        ticks: { color: "#9ca3af" },
        grid: { color: "#1f2937" },
      },
      y: {
        ticks: {
          color: "#9ca3af",
          callback: (v) => `${v}x`,
        },
        grid: { color: "#1f2937" },
      },
    },
    // Draw break-even line via annotation plugin isn't available,
    // so we use a custom afterDraw instead
  };

  // Plugin to draw a break-even reference line at ROAS = 1
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
      ctx.fillText("Break-even", chartArea.right - 76, y - 5);
      ctx.restore();
    },
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-5">
        ROAS by Campaign
      </h2>
      <Bar data={data} options={options} plugins={[breakEvenPlugin]} />
    </div>
  );
}
