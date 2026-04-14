"use client";

import { useState, useEffect, useCallback } from "react";
import { fetchPlayers } from "@/lib/api";
import type { PlayerLTV, PlayerPage } from "@/lib/api";
import SegmentBadge from "@/components/SegmentBadge";
import { Download, ChevronLeft, ChevronRight } from "lucide-react";

const SEGMENTS = [
  { value: "", label: "All segments" },
  { value: "high_ltv", label: "High LTV" },
  { value: "mid_ltv", label: "Mid LTV" },
  { value: "low_ltv", label: "Low LTV" },
];

const PAGE_SIZE = 50;

function exportCsv(items: PlayerLTV[]) {
  const headers = [
    "player_id",
    "segment",
    "expected_ltv_90d",
    "churn_probability",
    "predicted_purchases_30d",
    "predicted_purchases_90d",
    "frequency",
    "monetary",
    "cohort",
    "install_date",
    "scored_at",
  ];
  const rows = items.map((p) =>
    [
      p.player_id,
      p.segment,
      p.expected_ltv_90d,
      p.churn_probability,
      p.predicted_purchases_30d,
      p.predicted_purchases_90d,
      p.frequency,
      p.monetary,
      p.cohort,
      p.install_date,
      p.scored_at,
    ].join(",")
  );
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "players_ltv.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export default function PlayersClient() {
  const [segment, setSegment] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<PlayerPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await fetchPlayers({ segment: segment || undefined, limit: PAGE_SIZE, offset });
      setData(page);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [segment, offset]);

  useEffect(() => {
    load();
  }, [load]);

  // Reset to page 0 on segment change
  const handleSegmentChange = (v: string) => {
    setSegment(v);
    setOffset(0);
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-5 gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          {SEGMENTS.map((s) => (
            <button
              key={s.value}
              onClick={() => handleSegmentChange(s.value)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                segment === s.value
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <button
          onClick={() => data && exportCsv(data.items)}
          disabled={!data || data.items.length === 0}
          className="flex items-center gap-2 px-3 py-1.5 bg-gray-800 text-gray-300 hover:text-white hover:bg-gray-700 rounded-lg text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Download size={15} />
          Export CSV
        </button>
      </div>

      {/* Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {error && (
          <div className="p-6 text-rose-400 text-sm">
            Failed to load players: {error}
          </div>
        )}

        {!error && (
          <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead className="border-b border-gray-800">
              <tr className="text-gray-500">
                <th className="text-left px-4 py-3 font-medium whitespace-nowrap">Player ID</th>
                <th className="text-left px-4 py-3 font-medium whitespace-nowrap">Segment</th>
                <th className="text-right px-4 py-3 font-medium whitespace-nowrap">LTV (90d)</th>
                <th className="text-right px-4 py-3 font-medium whitespace-nowrap">Churn Prob</th>
                <th className="text-right px-4 py-3 font-medium whitespace-nowrap">Sessions 30d</th>
                <th className="text-right px-4 py-3 font-medium whitespace-nowrap">Sessions 90d</th>
                <th className="text-right px-4 py-3 font-medium whitespace-nowrap">Total Spend</th>
                <th className="text-right px-4 py-3 font-medium whitespace-nowrap">Install Date</th>
              </tr>
            </thead>
            <tbody>
              {loading &&
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i} className="border-b border-gray-800/50 animate-pulse">
                    {Array.from({ length: 8 }).map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-3.5 bg-gray-800 rounded w-full" />
                      </td>
                    ))}
                  </tr>
                ))}

              {!loading &&
                data?.items.map((p) => (
                  <tr
                    key={p.player_id}
                    className="border-b border-gray-800/50 hover:bg-gray-800/40 transition-colors"
                  >
                    <td className="px-4 py-3 font-mono text-gray-300 text-xs">{p.player_id}</td>
                    <td className="px-4 py-3">
                      <SegmentBadge segment={p.segment} />
                    </td>
                    <td className="px-4 py-3 text-right text-emerald-400 font-medium">
                      ${p.expected_ltv_90d.toFixed(2)}
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${
                      p.churn_probability > 0.7
                        ? "text-rose-400"
                        : p.churn_probability > 0.4
                        ? "text-amber-400"
                        : "text-gray-300"
                    }`}>
                      {(p.churn_probability * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 text-right text-gray-400">
                      {p.predicted_purchases_30d.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-400">
                      {p.predicted_purchases_90d.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      ${p.monetary.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-500 text-xs">
                      {p.install_date.split("T")[0]}
                    </td>
                  </tr>
                ))}

              {!loading && data?.items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-gray-500">
                    No players found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between mt-4 text-sm text-gray-500">
          <span>
            Showing {offset + 1} to {Math.min(offset + PAGE_SIZE, data.total)} of{" "}
            {data.total.toLocaleString()} players
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              disabled={offset === 0}
              className="p-1.5 rounded-lg bg-gray-800 text-gray-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-gray-400">
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= data.total}
              className="p-1.5 rounded-lg bg-gray-800 text-gray-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
