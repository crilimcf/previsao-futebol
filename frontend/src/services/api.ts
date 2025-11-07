// =====================================================
// src/services/api.ts
// Cliente HTTP para comunicar com a API FastAPI (Render)
// =====================================================

import axios from "axios";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "https://previsao-futebol.onrender.com";

export const API_TOKEN =
  process.env.NEXT_PUBLIC_API_TOKEN || "d110d6f22b446c54deadcadef7b234f6966af678";

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 12_000,
  headers: {
    Accept: "application/json",
    "Cache-Control": "no-cache",
    Pragma: "no-cache",
  },
});

export const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000,
  headers: {
    Authorization: `Bearer ${API_TOKEN}`,
    "Content-Type": "application/json",
    Accept: "application/json",
    "Cache-Control": "no-cache",
    Pragma: "no-cache",
  },
});

// helper para bustar cache de GETs
function withTs(params?: Record<string, any>) {
  return { ...(params || {}), _ts: Date.now() };
}

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
  league?: string;
  league_name?: string;
  country?: string;
  date: string; // ISO
  home_team: string;
  away_team: string;
  home_logo?: string;
  away_logo?: string;
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
  predicted_scorers?: {
    home?: { player: string; prob: number; xg: number; position?: string }[];
    away?: { player: string; prob: number; xg: number; position?: string }[];
  };
};

export type LastUpdate = { last_update: string | null };

export type LeagueItem = {
  id: number | string;
  name: string;
  country?: string;
  type?: "League" | "Cup" | string;
};

// =====================================================
// 📊 Funções principais para o frontend consumir
// =====================================================

/** Obtém previsões (suporta filtros via query params). */
export async function getPredictions(
  params?: { date?: string; league_id?: number | string }
): Promise<Prediction[]> {
  try {
    const normalized = params
      ? {
          ...params,
          league_id:
            params.league_id !== undefined && params.league_id !== null
              ? String(params.league_id)
              : undefined,
        }
      : undefined;

    const r = await api.get("/predictions", { params: withTs(normalized) });
    return Array.isArray(r.data) ? (r.data as Prediction[]) : [];
  } catch {
    return [];
  }
}

/** Obtém estatísticas agregadas (fallback para objeto vazio). */
export async function getStats() {
  try {
    const r = await api.get("/stats", { params: withTs() });
    return r.data ?? {};
  } catch {
    return {};
  }
}

/** Obtém a data da última atualização (robusto ao tipo do axios). */
export async function getLastUpdate(): Promise<LastUpdate> {
  try {
    const r = await api.get("/meta/last-update", { params: withTs() });
    const d: any = r?.data ?? {};
    if (d && typeof d === "object" && "last_update" in d) {
      const lu = (d as any).last_update;
      if (typeof lu === "string" || lu === null) {
        return { last_update: lu };
      }
    }
    return { last_update: null };
  } catch {
    return { last_update: null };
  }
}

/** (ADMIN-ONLY) Força atualização do backend — não usar no frontend público. */
export async function triggerUpdate(body?: any) {
  const r = await authApi.post("/meta/update", body ?? {});
  return r.data;
}

/** Testa estado geral da API. */
export async function getApiHealth() {
  try {
    const r = await api.get("/healthz", { params: withTs() });
    return r.data ?? { status: "unknown" };
  } catch {
    return { status: "offline" };
  }
}

/**
 * ✅ Lista curada de ligas/taças servida pelo TEU backend.
 * Primeiro tenta /meta/leagues (o que já tens no Render). Se não existir, cai para /leagues.
 * NUNCA chama a API-Football diretamente.
 */
export async function getLeagues(season?: string): Promise<LeagueItem[]> {
  try {
    const s = season ?? (process.env.NEXT_PUBLIC_SEASON ?? "2024");

    // 1) tenta /meta/leagues
    try {
      const r1 = await api.get("/meta/leagues", { params: withTs({ season: s }) });
      const data1 = r1?.data as any;
      const arr1: any[] = Array.isArray(data1)
        ? data1
        : Array.isArray(data1?.items)
        ? data1.items
        : Array.isArray(data1?.data)
        ? data1.data
        : Array.isArray(data1?.leagues)
        ? data1.leagues
        : [];

      if (arr1.length) {
        return normalizeLeagues(arr1);
      }
    } catch {
      /* continua para /leagues */
    }

    // 2) fallback /leagues
    const r2 = await api.get("/leagues", { params: withTs({ season: s }) });
    const data2 = r2?.data as any;
    const arr2: any[] = Array.isArray(data2)
      ? data2
      : Array.isArray(data2?.items)
      ? data2.items
      : Array.isArray(data2?.data)
      ? data2.data
      : Array.isArray(data2?.leagues)
      ? data2.leagues
      : [];

    return normalizeLeagues(arr2);
  } catch {
    return [];
  }
}

function normalizeLeagues(arr: any[]): LeagueItem[] {
  const norm: LeagueItem[] = arr
    .map((x) => ({
      id: String(x.id ?? x.league_id ?? x.code ?? ""),
      name: String(x.name ?? x.league ?? "").trim(),
      country: x.country ? String(x.country) : undefined,
      type: x.type ? String(x.type) : undefined,
    }))
    .filter((x) => x.id && x.name);

  norm.sort((a, b) => {
    const ca = (a.country ?? "").localeCompare(b.country ?? "", "pt-PT");
    return ca !== 0 ? ca : a.name.localeCompare(b.name, "pt-PT");
  });

  return norm;
}
