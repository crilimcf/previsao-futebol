// =====================================================
// src/services/api.ts
// Cliente HTTP para comunicar com a API FastAPI (Render)
// =====================================================

import axios from "axios";

// 🌍 URL base da tua API (Render)
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "https://previsao-futebol.onrender.com";

// 🔑 Token apenas para endpoints protegidos (ex.: /meta/update)
export const API_TOKEN =
  process.env.NEXT_PUBLIC_API_TOKEN || "d110d6f22b446c54deadcadef7b234f6966af678";

// Instância pública (sem headers que disparam preflight)
export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 12_000,
});

// Instância autenticada (usar só quando precisar de Bearer)
export const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000,
  headers: {
    Authorization: `Bearer ${API_TOKEN}`,
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// ---------------------------
// Tipos úteis (frontend)
// ---------------------------
export type DCClass = 0 | 1 | 2; // 0=1X, 1=12, 2=X2

export type OddsMap = {
  winner?: { home?: number | null; draw?: number | null; away?: number | null } | null;
  over_2_5?: { over?: number | null; under?: number | null } | null;
  over_1_5?: { over?: number | null; under?: number | null } | null;
  btts?: { yes?: number | null; no?: number | null } | null;
};

export type Prediction = {
  match_id: number | string;
  league_id: number | string;
  league: string;
  country?: string;
  date: string; // ISO
  home_team: string;
  away_team: string;
  home_logo?: string;
  away_logo?: string;
  odds?: OddsMap;
  predictions: {
    winner: { class: 0 | 1 | 2; confidence: number };
    over_2_5: { class: 0 | 1; confidence: number };
    over_1_5: { class: 0 | 1; confidence: number };
    double_chance: { class: DCClass; confidence: number };
    btts: { class: 0 | 1; confidence: number };
  };
  correct_score_top3?: { score: string; prob: number }[];
  top_scorers?: { player: string; team: string; goals: number }[];
};

// =====================================================
// 📊 Funções principais para o frontend consumir
// =====================================================

/** Obtém previsões (suporta filtros via query params). */
export async function getPredictions(params?: { date?: string; league_id?: number | string }) {
  const r = await api.get("/predictions", {
    params: params ?? {},
    headers: { Accept: "application/json" },
  });
  return r.data ?? [];
}

/** Obtém estatísticas agregadas (fallback para objeto vazio). */
export async function getStats() {
  try {
    const r = await api.get("/stats", { headers: { Accept: "application/json" } });
    return r.data ?? {};
  } catch {
    return {};
  }
}

/** Obtém a data da última atualização (fallback seguro). */
export async function getLastUpdate() {
  try {
    const r = await api.get("/meta/last-update", { headers: { Accept: "application/json" } });
    return r.data ?? { last_update: null };
  } catch {
    return { last_update: null };
  }
}

/** Força atualização manual das previsões (endpoint protegido). */
export async function triggerUpdate() {
  const r = await authApi.post("/meta/update");
  return r.data;
}

/** Testa estado geral da API. */
export async function getApiHealth() {
  try {
    const r = await api.get("/healthz", { headers: { Accept: "application/json" } });
    return r.data ?? { status: "unknown" };
  } catch {
    return { status: "offline" };
  }
}
