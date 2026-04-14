import { fetchSegments, fetchPlayers } from "@/lib/api";
import type { PlayerLTV } from "@/lib/api";
import KpiCard from "@/components/KpiCard";
import SegmentDonut from "@/components/SegmentDonut";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const [segments, page] = await Promise.all([
    fetchSegments().catch(() => []),
    fetchPlayers({ limit: 500 }).catch(() => ({ total: 0, limit: 500, offset: 0, items: [] as PlayerLTV[] })),
  ]);

  const players = page.items;
  const avgLTV =
    players.length > 0
      ? players.reduce((s: number, p: PlayerLTV) => s + p.expected_ltv_90d, 0) / players.length
      : 0;
  const avgChurn =
    players.length > 0
      ? players.reduce((s: number, p: PlayerLTV) => s + p.churn_probability, 0) / players.length
      : 0;
  const highLtvCount = segments.find((s) => s.segment === "high_ltv")?.count ?? 0;
  const totalRevenue = segments.reduce((s, seg) => s + seg.total_ltv_90d, 0);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-xl font-bold text-white">Overview</h1>
        <p className="text-sm text-gray-500 mt-1">
          LTV model summary: {page.total.toLocaleString()} players scored
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-8">
        <KpiCard
          label="Avg LTV (90d)"
          value={`$${avgLTV.toFixed(2)}`}
          sub="per player"
          accent="indigo"
        />
        <KpiCard
          label="Avg Churn Probability"
          value={`${(avgChurn * 100).toFixed(1)}%`}
          sub="across all players"
          accent="rose"
        />
        <KpiCard
          label="High-LTV Players"
          value={highLtvCount.toLocaleString()}
          sub="top 20% by LTV"
          accent="emerald"
        />
        <KpiCard
          label="Total Predicted Revenue"
          value={`$${(totalRevenue / 1000).toFixed(1)}k`}
          sub="90-day horizon"
          accent="amber"
        />
      </div>

      {/* Charts + breakdown */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {segments.length > 0 ? (
          <SegmentDonut segments={segments} />
        ) : (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-gray-500 text-sm">
            No segment data &mdash; run the model pipeline first.
          </div>
        )}

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 overflow-hidden">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Segment Breakdown
          </h2>
          {segments.length === 0 ? (
            <p className="text-gray-500 text-sm">No data.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[360px]">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-800">
                    <th className="text-left pb-2 font-medium whitespace-nowrap">Segment</th>
                    <th className="text-right pb-2 font-medium whitespace-nowrap">Players</th>
                    <th className="text-right pb-2 font-medium whitespace-nowrap">Avg LTV</th>
                    <th className="text-right pb-2 font-medium whitespace-nowrap">Total LTV</th>
                    <th className="text-right pb-2 font-medium whitespace-nowrap">Share</th>
                  </tr>
                </thead>
                <tbody>
                  {segments.map((s) => (
                    <tr key={s.segment} className="border-b border-gray-800/50">
                      <td className="py-3 text-gray-300 capitalize whitespace-nowrap">
                        {s.segment.replace("_", " ")}
                      </td>
                      <td className="py-3 text-right text-gray-300 whitespace-nowrap">
                        {s.count.toLocaleString()}
                      </td>
                      <td className="py-3 text-right text-gray-300 whitespace-nowrap">
                        ${s.avg_ltv_90d.toFixed(2)}
                      </td>
                      <td className="py-3 text-right text-gray-300 whitespace-nowrap">
                        ${s.total_ltv_90d.toLocaleString()}
                      </td>
                      <td className="py-3 text-right text-gray-400 whitespace-nowrap">
                        {s.pct_of_players}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
