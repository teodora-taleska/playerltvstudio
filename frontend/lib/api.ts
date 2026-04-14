const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PlayerLTV {
  player_id: string;
  cohort: string;
  install_date: string;
  frequency: number;
  monetary: number;
  segment: "high_ltv" | "mid_ltv" | "low_ltv";
  expected_ltv_90d: number;
  predicted_purchases_30d: number;
  predicted_purchases_90d: number;
  churn_probability: number;
  scored_at: string;
}

export interface PlayerPage {
  total: number;
  limit: number;
  offset: number;
  items: PlayerLTV[];
}

export interface SegmentSummary {
  segment: string;
  count: number;
  avg_ltv_90d: number;
  total_ltv_90d: number;
  pct_of_players: number;
}

export interface CampaignResult {
  campaign_id: string;
  campaign_name: string;
  start_date: string;
  spend: number;
  n_players: number;
  avg_ltv_acquired: number;
  total_predicted_revenue_90d: number;
  roas: number;
  payback_period_days: number | null;
  is_profitable: boolean;
}

export async function fetchPlayers(params: {
  segment?: string;
  limit?: number;
  offset?: number;
}): Promise<PlayerPage> {
  const url = new URL(`${BASE}/players`);
  if (params.segment) url.searchParams.set("segment", params.segment);
  if (params.limit != null) url.searchParams.set("limit", String(params.limit));
  if (params.offset != null) url.searchParams.set("offset", String(params.offset));
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error(`/players failed: ${res.status}`);
  return res.json();
}

export async function fetchSegments(): Promise<SegmentSummary[]> {
  const res = await fetch(`${BASE}/segments`, { cache: "no-store" });
  if (!res.ok) throw new Error(`/segments failed: ${res.status}`);
  return res.json();
}

export async function fetchCampaigns(): Promise<CampaignResult[]> {
  const res = await fetch(`${BASE}/campaigns`, { cache: "no-store" });
  if (!res.ok) throw new Error(`/campaigns failed: ${res.status}`);
  return res.json();
}

export async function runModels(): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/run-models`, { method: "POST" });
  if (!res.ok) throw new Error(`/run-models failed: ${res.status}`);
  return res.json();
}
