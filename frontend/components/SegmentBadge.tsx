const styles: Record<string, string> = {
  high_ltv: "bg-emerald-900/60 text-emerald-300 border border-emerald-700",
  mid_ltv: "bg-indigo-900/60 text-indigo-300 border border-indigo-700",
  low_ltv: "bg-gray-800 text-gray-400 border border-gray-700",
};

const labels: Record<string, string> = {
  high_ltv: "High LTV",
  mid_ltv: "Mid LTV",
  low_ltv: "Low LTV",
};

export default function SegmentBadge({ segment }: { segment: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${styles[segment] ?? "bg-gray-800 text-gray-400"}`}>
      {labels[segment] ?? segment}
    </span>
  );
}
