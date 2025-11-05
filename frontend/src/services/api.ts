// frontend/src/services/api.ts
import axios from "axios";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "https://previsao-futebol.onrender.com";

export const API_TOKEN =
  process.env.NEXT_PUBLIC_API_TOKEN || "d110d6f22b446c54deadcadef7b234f6966af678";

// Instância pública (sem headers “extras” que forçam preflight)
export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 12000,
});

// Instância autenticada
export const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
  headers: {
    Authorization: `Bearer ${API_TOKEN}`,
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// ---------------------------
// Tipos
// ---------------------------
export type DCClass = 0 | 1 | 2;

export type OddsMap = {
  winner?: { home?: number | null; draw?: number | null; away?: number | null } | null;
  over_2_5?: { over?: number | null; under?: number | null } | null;
  over_1_5?: { over?: number | null; under?: number | null } | null;
  btts?: { yes?: number | null; no?: number | null } | null;
};

export type Prediction = {
  match_id: number | string;
  league_id: number | string;
  league?: string;
  league_name?: string;
  country?: string | null;
  date: string; // ISO
  home_team: string;
  away_team: string;
  home_logo?: string | null;
  away_logo?: string | null;
  odds?: OddsMap;
  predictions: {
    winner: { class: 0 | 1 | 2; confidence?: number; prob?: number };
    over_2_5: { class: 0 | 1; confidence?: number; prob?: number };
    over_1_5: { class: 0 | 1; confidence?: number; prob?: number };
    double_chance: { class: DCClass; confidence?: number; prob?: number };
    btts: { class: 0 | 1; confidence?: number; prob?: number };
    correct_score?: { best?: string; top3?: { score: string; prob: number }[] };
  };
  correct_score_top3?: { score: string; prob: number }[];
  top_scorers?: { player: string; team: string; goals: number }[];
};

export type LastUpdate = { last_update: string | null };
export type LeagueItem = { id: string; name: string; country?: string | null };

// ---------------------------
// API helpers
// ---------------------------
export async function getPredictions(params?: { date?: string; league_id?: number | string }) {
  try {
    const normalized =
      params && params.league_id != null
        ? { ...params, league_id: String(params.league_id) }
        : params;

    const r = await api.get("/predictions", {
      params: normalized,
      headers: { Accept: "application/json", "Cache-Control": "no-store" },
    });
    return Array.isArray(r.data) ? (r.data as Prediction[]) : [];
  } catch {
    return [];
  }
}

export async function getStats() {
  try {
    const r = await api.get("/stats", { headers: { Accept: "application/json" } });
    return r.data ?? {};
  } catch {
    return {};
  }
}

export async function getLastUpdate(): Promise<LastUpdate> {
  try {
    const r = await api.get("/meta/last-update", { headers: { Accept: "application/json" } });
    return (r.data as LastUpdate) ?? { last_update: null };
  } catch {
    return { last_update: null };
  }
}

export async function triggerUpdate() {
  const r = await authApi.post("/meta/update");
  return r.data;
}

// 🔥 NOVO — lista de ligas do backend
export async function getLeagues(): Promise<LeagueItem[]> {
  try {
    const r = await api.get("/meta/leagues", {
      headers: { Accept: "application/json", "Cache-Control": "no-store" },
    });
    const items = Array.isArray(r.data?.items) ? r.data.items : [];
    return items as LeagueItem[];
  } catch {
    return [];
  }
}

export async function getApiHealth() {
  try {
    const r = await api.get("/healthz", { headers: { Accept: "application/json" } });
    return r.data ?? { status: "unknown" };
  } catch {
    return { status: "offline" };
  }
}
