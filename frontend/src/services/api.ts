// =====================================================
// src/services/api.ts
// Cliente HTTP para comunicar com a API FastAPI (Render)
// Agora com toggle v1/v2 (env + localStorage) e fallback automático
// + getLeagues compatível com string OU objeto { season?, date? }
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
// Toggle v2 helpers
// ---------------------------
function wantV2FromEnv(): boolean {
  const v = (process.env.NEXT_PUBLIC_PREDICTIONS_VERSION || "").toLowerCase();
  if (v === "v2") return true;
  const u2 = (process.env.NEXT_PUBLIC_USE_V2 || "").trim();
  return u2 === "1" || u2.toLowerCase() === "true";
}

function wantV2(): boolean {
  try {
    if (typeof window !== "undefined") {
      const ls = window.localStorage.getItem("use_v2");
      if (ls === "1") return true;
      if (ls === "0") return false;
    }
  } catch {
    /* ignore */
  }
  return wantV2FromEnv();
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

  // novo: lambdas guardados pelo backend
  lambda_home?: number;
  lambda_away?: number;

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

  // novo: explicação gerada pelo backend (já não usamos texto cru)
  explanation?: string[];
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

type GetPredParams = { date?: string; league_id?: number | string };
type GetPredOpts = { version?: "v1" | "v2"; allowFallback?: boolean };

/**
 * Obtém previsões.
 * - Por omissão, respeita env/localStorage (v2 se configurado).
 * - Se `version: "v2"`, força v2 (com fallback p/ v1 se allowFallback=true).
 */
export async function getPredictions(
  params?: GetPredParams,
  opts: GetPredOpts = {}
): Promise<Prediction[]> {
  const normalized = params
    ? {
        ...params,
        league_id:
          params.league_id !== undefined && params.league_id !== null
            ? String(params.league_id)
            : undefined,
      }
    : undefined;

  const preferV2 = opts.version ? opts.version === "v2" : wantV2();
  const allowFallback = opts.allowFallback !== false; // default true

  if (preferV2) {
    try {
      const r2 = await api.get("/predictions/v2", { params: withTs(normalized) });
      return normalizePredArray(r2.data);
    } catch (err) {
      if (!allowFallback) throw err;
      // cai para v1 silenciosamente
      try {
        const r1 = await api.get("/predictions", { params: withTs(normalized) });
        return normalizePredArray(r1.data);
      } catch {
        return [];
      }
    }
  } else {
    try {
      const r1 = await api.get("/predictions", { params: withTs(normalized) });
      return normalizePredArray(r1.data);
    } catch (err) {
      if (!allowFallback) throw err;
      // tenta v2 como fallback
      try {
        const r2 = await api.get("/predictions/v2", { params: withTs(normalized) });
        return normalizePredArray(r2.data);
      } catch {
        return [];
      }
    }
  }
}

/** Normaliza qualquer payload de previsões para Prediction[] seguro. */
function normalizePredArray(data: any): Prediction[] {
  const arr: any[] = Array.isArray(data)
    ? data
    : Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.data)
    ? data.data
    : Array.isArray(data?.predictions)
    ? data.predictions
    : [];

  // Garantir campos mínimos e strings
  return arr
    .map((p) => {
      const explanation = Array.isArray(p.explanation)
        ? p.explanation.map((s: any) => String(s))
        : undefined;

      const lambdaHome =
        typeof p.lambda_home === "number" ? p.lambda_home : undefined;
      const lambdaAway =
        typeof p.lambda_away === "number" ? p.lambda_away : undefined;

      return {
        match_id: String(p.match_id ?? p.fixture_id ?? p.id ?? ""),
        league_id: String(p.league_id ?? p.league?.id ?? ""),
        league: p.league ?? p.league_name ?? undefined,
        league_name: p.league_name ?? p.league ?? undefined,
        country: p.country ?? p.country_name ?? undefined,
        date: String(p.date ?? p.fixture_date ?? p.kickoff ?? ""),
        home_team: String(p.home_team ?? p.home?.name ?? p.home ?? ""),
        away_team: String(p.away_team ?? p.away?.name ?? p.away ?? ""),
        home_logo: p.home_logo ?? p.home?.logo ?? undefined,
        away_logo: p.away_logo ?? p.away?.logo ?? undefined,
        odds: p.odds ?? undefined,
        predictions:
          p.predictions ??
          ({
            winner: { class: 1 as 0 | 1 | 2, prob: 0.33 },
            over_2_5: { class: 0 as 0 | 1, prob: 0.5 },
            over_1_5: { class: 1 as 0 | 1, prob: 0.6 },
            double_chance: { class: 0 as DCClass, prob: 0.5 },
            btts: { class: 0 as 0 | 1, prob: 0.5 },
          } as Prediction["predictions"]),
        correct_score_top3:
          p.correct_score_top3 ??
          p.predictions?.correct_score?.top3 ??
          [],
        top_scorers: p.top_scorers ?? [],
        predicted_scorers: p.predicted_scorers ?? {},

        // novos campos
        lambda_home: lambdaHome,
        lambda_away: lambdaAway,
        explanation,
      } as Prediction;
    })
    .filter((x) => x.match_id && x.date && x.home_team && x.away_team);
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

// =====================================================
// 📚 Ligas – sempre via TEU backend (meta/leagues ou fallback /leagues)
// Agora aceita:
//   - getLeagues()
//   - getLeagues("2024")
//   - getLeagues({ season: "2024", date: "2025-11-21" })
//   - getLeagues({ date })
// =====================================================

type LeagueFilters = {
  season?: string;
  date?: string;
};

export async function getLeagues(
  filters?: string | number | LeagueFilters
): Promise<LeagueItem[]> {
  let season: string | undefined;
  const extra: Record<string, any> = {};

  if (typeof filters === "string" || typeof filters === "number") {
    season = String(filters);
  } else if (filters && typeof filters === "object") {
    if (filters.season) {
      season = filters.season;
    }
    if (filters.date) {
      extra.date = filters.date;
    }
  }

  const s = season ?? (process.env.NEXT_PUBLIC_SEASON ?? "2024");

  try {
    // 1) tenta /meta/leagues
    try {
      const r1 = await api.get("/meta/leagues", {
        params: withTs({ season: s, ...extra }),
      });
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
      // continua para /leagues
    }

    // 2) fallback /leagues
    const r2 = await api.get("/leagues", {
      params: withTs({ season: s, ...extra }),
    });
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
