import { fetchCampaigns } from "@/lib/api";
import RoasChart from "@/components/RoasChart";

export const dynamic = "force-dynamic";

function ProfitableBadge({ profitable }: { profitable: boolean }) {
  return profitable ? (
    <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-emerald-900/60 text-emerald-300 border border-emerald-700">
      Profitable
    </span>
  ) : (
    <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-rose-900/60 text-rose-300 border border-rose-700">
      Unprofitable
    </span>
  );
}

export default async function CampaignsPage() {
  const campaigns = await fetchCampaigns().catch(() => []);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-xl font-bold text-white">Campaigns</h1>
        <p className="text-sm text-gray-500 mt-1">
          Campaign ROI &mdash; predicted revenue vs ad spend
        </p>
      </div>

      {campaigns.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-gray-500 text-sm">
          No campaign data &mdash; run the campaign model first.
        </div>
      ) : (
        <div className="space-y-6">
          {/* ROAS chart */}
          <RoasChart campaigns={campaigns} />

          {/* KPI summary row */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Total Spend</p>
              <p className="text-xl font-bold text-white">
                ${campaigns.reduce((s, c) => s + c.spend, 0).toLocaleString()}
              </p>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Total Predicted Revenue</p>
              <p className="text-xl font-bold text-white">
                $
                {campaigns
                  .reduce((s, c) => s + c.total_predicted_revenue_90d, 0)
                  .toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Best ROAS</p>
              <p className="text-xl font-bold text-indigo-400">
                {Math.max(...campaigns.map((c) => c.roas)).toFixed(2)}x
              </p>
            </div>
          </div>

          {/* Detail table */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="border-b border-gray-800">
                <tr className="text-gray-500">
                  <th className="text-left px-4 py-3 font-medium">Campaign</th>
                  <th className="text-right px-4 py-3 font-medium">Spend</th>
                  <th className="text-right px-4 py-3 font-medium">Players</th>
                  <th className="text-right px-4 py-3 font-medium">Avg LTV Acquired</th>
                  <th className="text-right px-4 py-3 font-medium">Predicted Revenue (90d)</th>
                  <th className="text-right px-4 py-3 font-medium">ROAS</th>
                  <th className="text-right px-4 py-3 font-medium">Payback</th>
                  <th className="text-right px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.campaign_id} className="border-b border-gray-800/50 hover:bg-gray-800/40 transition-colors">
                    <td className="px-4 py-3 text-gray-200 font-medium capitalize">
                      {c.campaign_name.replace(/_/g, " ")}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      ${c.spend.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-400">
                      {c.n_players.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      ${c.avg_ltv_acquired.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      ${c.total_predicted_revenue_90d.toLocaleString()}
                    </td>
                    <td className={`px-4 py-3 text-right font-semibold ${
                      c.roas >= 1 ? "text-emerald-400" : "text-rose-400"
                    }`}>
                      {c.roas.toFixed(2)}x
                    </td>
                    <td className="px-4 py-3 text-right text-gray-400">
                      {c.payback_period_days != null
                        ? `${c.payback_period_days.toFixed(0)}d`
                        : "N/A"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <ProfitableBadge profitable={c.is_profitable} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
