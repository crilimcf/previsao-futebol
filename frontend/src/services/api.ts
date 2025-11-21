// =====================================================
// src/services/api.ts
// Cliente HTTP para comunicar com a API FastAPI (Render)
// Agora com toggle v1/v2 (env + localStorage) e suporte
// para marcadores prováveis da V2 + ligas por data.
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

export type ScorerEntry = {
  player_id?: number | string;
  name?: string;
  player?: string;
  full_name?: string;
  team_id?: number | string;
  team_name?: string;
  position?: string;
  probability?: number;
  probability_pct?: number;
  prob?: number;
  confidence?: number;
  [key: string]: any;
};

export type Prediction = {
  match_id: number | string;
  league_id: number | string;
  league?: string;
  league_name?: string;
  country?: string;
  date: string; // ISO
  date_ymd?: string;

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
    double_chance: { class: DCClass; confidence?: number; prob?: number; label?: string };
    btts: { class: 0 | 1; confidence?: number; prob?: number };
    correct_score?: { best?: string; top3?: { score: string; prob: number }[] };
  };

  correct_score_top3?: { score: string; prob: number }[];

  top_scorers?: { player: string; team: string; goals: number }[];

  // V1: predicted_scorers, V2: probable_scorers(_home/_away)
  predicted_scorers?: {
    home?: ScorerEntry[];
    away?: ScorerEntry[];
  };

  probable_scorers?: {
    home?: ScorerEntry[];
    away?: ScorerEntry[];
  };

  // novo: explicação gerada pelo backend
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

/** Normaliza array de previsões (v1 ou v2) para Prediction[] seguro. */
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

  const normScorers = (homeRaw: any, awayRaw: any): { home?: ScorerEntry[]; away?: ScorerEntry[] } => {
    const home = Array.isArray(homeRaw) ? homeRaw : [];
    const away = Array.isArray(awayRaw) ? awayRaw : [];
    return { home, away };
  };

  return arr
    .map((p) => {
      const explanation = Array.isArray(p.explanation)
        ? p.explanation.map((s: any) => String(s))
        : undefined;

      const lambdaHome =
        typeof p.lambda_home === "number" ? p.lambda_home : undefined;
      const lambdaAway =
        typeof p.lambda_away === "number" ? p.lambda_away : undefined;

      // --- marcadores ---
      // V2 pode mandar:
      //  - probable_scorers: { home: [...], away: [...] }
      //  - probable_scorers_home / probable_scorers_away
      const probable = normScorers(
        p.probable_scorers?.home ?? p.probable_scorers_home,
        p.probable_scorers?.away ?? p.probable_scorers_away
      );

      // V1 pode mandar predicted_scorers
      const predictedRaw = p.predicted_scorers || {};
      const predicted: { home?: ScorerEntry[]; away?: ScorerEntry[] } = {
        home:
          Array.isArray(predictedRaw.home) && predictedRaw.home.length
            ? predictedRaw.home
            : probable.home,
        away:
          Array.isArray(predictedRaw.away) && predictedRaw.away.length
            ? predictedRaw.away
            : probable.away,
      };

      const dateStr: string =
        typeof p.date === "string"
          ? p.date
          : typeof p.fixture_date === "string"
          ? p.fixture_date
          : typeof p.kickoff === "string"
          ? p.kickoff
          : "";

      const dateYmd =
        typeof p.date_ymd === "string"
          ? p.date_ymd
          : dateStr
          ? dateStr.slice(0, 10)
          : undefined;

      return {
        match_id: String(p.match_id ?? p.fixture_id ?? p.id ?? ""),
        league_id: String(p.league_id ?? p.league?.id ?? ""),
        league: p.league ?? p.league_name ?? undefined,
        league_name: p.league_name ?? p.league ?? undefined,
        country: p.country ?? p.country_name ?? undefined,

        date: dateStr,
        date_ymd: dateYmd,

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

        // unificação V1 + V2
        probable_scorers: probable,
        predicted_scorers: predicted,

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

// ---------------------------
// Ligas / Taças do backend
// ---------------------------

type GetLeaguesParams = {
  season?: string;
  date?: string;
};

/**
 * ✅ Lista curada de ligas/taças servida pelo TEU backend.
 * - Aceita { season?, date? }.
 * - Primeiro tenta /meta/leagues; se não existir, cai para /leagues.
 */
export async function getLeagues(params?: GetLeaguesParams): Promise<LeagueItem[]> {
  try {
    const season = params?.season ?? (process.env.NEXT_PUBLIC_SEASON ?? "2024");

    const baseQuery: Record<string, any> = { season };
    if (params?.date) baseQuery.date = params.date;

    // 1) tenta /meta/leagues
    try {
      const r1 = await api.get("/meta/leagues", { params: withTs(baseQuery) });
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
    const r2 = await api.get("/leagues", { params: withTs(baseQuery) });
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
