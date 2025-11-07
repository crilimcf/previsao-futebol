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
  timeout: 15000,
  headers: {
    Accept: "application/json",
  },
});

export const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
  headers: {
    Authorization: `Bearer ${API_TOKEN}`,
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// helper para bustar cache de GETs
function withTs(params?: Record<string, any>) {
  return { ...(params || {}), _ts: Date.now() };
}

// --------- Tipos usados no frontend ----------
export type DCClass = 0 | 1 | 2; // 0=1X, 1=12, 2=X2

export type OddsMap = {
  winner?: { home?: number | null; draw?: number | null; away?: number | null } | null;
  over_2_5?: { over?: number | null; under?: number | null } | null;
  over_1_5?: { over?: number | null; under?: number | null } | null;
  btts?: { yes?: number | null; no?: number | null } | null;
};

export type Prediction = {
  match_id?: number | string;
  fixture_id?: number | string;
  league_id?: number | string;
  league?: string;
  league_name?: string;
  country?: string;
  date?: string; // ISO
  home_team?: string;
  away_team?: string;
  home_logo?: string;
  away_logo?: string;
  odds?: OddsMap;
  predictions?: any;
  // quando vem “bruto” da API-Football:
  fixture?: any;
  leagueObj?: any;
  leagueData?: any;
  teams?: any;
};

export type LastUpdate = { last_update: string | null };
export type LeagueItem = { id: number | string; name: string; country?: string };

// --------- Normalização de respostas ----------
function normalizeList(data: any): any[] {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.response)) return data.response;
  if (Array.isArray(data?.data)) return data.data;
  if (Array.isArray(data?.items)) return data.items;
  if (Array.isArray(data?.result)) return data.result;
  return [];
}

// =====================================================
// 📊 Funções principais para o frontend consumir
// =====================================================

/** Obtém previsões (suporta filtros via query params). */
export async function getPredictions(
  params?: { date?: string; league_id?: number | string }
): Promise<Prediction[]> {
  try {
    const normalizedParams =
      params && Object.keys(params).length
        ? {
            ...params,
            league_id:
              params.league_id !== undefined && params.league_id !== null
                ? String(params.league_id)
                : undefined,
          }
        : undefined;

    // 1ª tentativa: com os filtros recebidos
    const r1 = await api.get("/predictions", { params: withTs(normalizedParams) });
    let list = normalizeList(r1.data);

    // Debug leve no browser
    if (typeof window !== "undefined") {
      console.debug(
        "[getPredictions] req1",
        `${API_BASE_URL}/predictions`,
        normalizedParams,
        "len=",
        list.length
      );
    }

    // Fallback: se pediste por data e veio vazio, tenta sem filtros (para não ficar o ecrã em branco)
    if ((!list || list.length === 0) && normalizedParams && normalizedParams.date) {
      const r2 = await api.get("/predictions", { params: withTs() });
      const list2 = normalizeList(r2.data);
      if (typeof window !== "undefined") {
        console.debug("[getPredictions] fallback sem filtros -> len=", list2.length);
      }
      list = list2;
    }

    return (list || []) as Prediction[];
  } catch (err) {
    if (typeof window !== "undefined") console.error("[getPredictions] erro:", err);
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

/** Força atualização manual das previsões (endpoint protegido). */
export async function triggerUpdate() {
  const r = await authApi.post("/meta/update");
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

/** Lista de ligas conhecidas pelo backend. Aceita vários formatos. */
export async function getLeagues(): Promise<LeagueItem[]> {
  try {
    const r = await api.get("/meta/leagues", { params: withTs() });
    return normalizeList(r?.data);
  } catch {
    return [];
  }
}
