interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
  accent?: "indigo" | "emerald" | "rose" | "amber";
}

const accents = {
  indigo: "border-indigo-500 text-indigo-400",
  emerald: "border-emerald-500 text-emerald-400",
  rose: "border-rose-500 text-rose-400",
  amber: "border-amber-500 text-amber-400",
};

export default function KpiCard({ label, value, sub, accent = "indigo" }: KpiCardProps) {
  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-xl p-5 border-l-2 ${accents[accent]}`}>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{label}</p>
      <p className={`text-2xl font-bold ${accents[accent].split(" ")[1]}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}
