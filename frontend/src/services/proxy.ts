// =====================================================
// src/services/proxy.ts
// Proxy seguro para a API-Football via Render/Python-Proxy
// - Suporta "date" + "timezone" e retro-compat com "next"
// - Cache em memória + fallback localStorage
// - Filtro anti Women e U-xx em fixtures do proxy
// =====================================================

/**
 * Permite as duas envs para compat:
 *  - NEXT_PUBLIC_PROXY_URL
 *  - NEXT_PUBLIC_PROXY_BASE
 */
const API_PROXY_URL =
  process.env.NEXT_PUBLIC_PROXY_URL ||
  process.env.NEXT_PUBLIC_PROXY_BASE ||
  "https://football-proxy-4ymo.onrender.com";

const PROXY_TOKEN =
  process.env.NEXT_PUBLIC_PROXY_TOKEN || "CF_Proxy_2025_Secret_!@#839";

const DEFAULT_TTL_MS = 60_000; // 1 min (cache memória)
const DEFAULT_TZ =
  process.env.NEXT_PUBLIC_TIMEZONE || "Europe/Lisbon";

// ---------------------------
// Tipos básicos
// ---------------------------
type Team = { id?: number; name?: string; logo?: string };
type League = { id?: number; name?: string; country?: string };
export type ProxyFixture = {
  fixture: { id: number; date: string };
  league: League;
  teams: { home: Team; away: Team };
};

// ---------------------------
// Regras de exclusão
// ---------------------------

// U-15..U-23
const YOUTH_RE = /\bU(?:15|16|17|18|19|20|21|22|23)\b/i;

// Women robusto (women/feminino/femenino/ladies/girls) e tokens " W " / "(W)" / "-W"
const WOMEN_RE =
  /(?:\b(women|femenin[oa]?|feminin|feminino|femenino|ladies|girls)\b|(?:^|\s|[(-])w(?:\s|[)-]|$))/i;

function isWomenOrYouth(name?: string | null) {
  if (!name) return false;
  return WOMEN_RE.test(name) || YOUTH_RE.test(name);
}

// ---------------------------
// Cache em memória (com TTL)
// ---------------------------
type CacheEntry = { data: any; timestamp: number; ttlMs: number };
const memCache: Record<string, CacheEntry> = {};

function cacheGet(key: string) {
  const it = memCache[key];
  if (!it) return null;
  if (Date.now() - it.timestamp > it.ttlMs) {
    delete memCache[key];
    return null;
  }
  return it.data;
}
function cacheSet(key: string, data: any, ttlMs: number) {
  memCache[key] = { data, timestamp: Date.now(), ttlMs };
}

// ---------------------------
// Fallback localStorage
// ---------------------------
function lsGet(key: string) {
  try {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem(`football_proxy_${key}`);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function lsSet(key: string, data: any) {
  try {
    if (typeof window !== "undefined") {
      localStorage.setItem(`football_proxy_${key}`, JSON.stringify(data));
    }
  } catch {
    /* ignore */
  }
}

// ---------------------------
// Fetch genérico com cache
// ---------------------------
type FetchOpts = {
  noStore?: boolean;   // força não usar cache de rede
  timeoutMs?: number;  // timeout do fetch
  ttlMs?: number;      // TTL do cache em memória
};

function buildUrl(endpoint: string, params?: Record<string, any>) {
  const base = API_PROXY_URL.replace(/\/+$/, "");
  const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = new URL(`${base}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.append(k, String(v));
    });
  }
  return url;
}

async function fetchFromProxy(
  endpoint: string,
  params?: Record<string, any>,
  opts: FetchOpts = {}
) {
  const ttlMs = opts.ttlMs ?? DEFAULT_TTL_MS;

  // usa a URL final como chave de cache (estável)
  const url = buildUrl(endpoint, params);
  const key = url.toString();

  if (!opts.noStore) {
    const cached = cacheGet(key);
    if (cached) return cached;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts.timeoutMs ?? 12_000);

  try {
    const res = await fetch(url.toString(), {
      headers: {
        "x-proxy-token": PROXY_TOKEN,
        "Accept": "application/json",
      },
      cache: opts.noStore ? "no-store" : "default",
      next: { revalidate: Math.ceil(ttlMs / 1000) }, // dica p/ Next.js
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Proxy ${res.status}: ${text || res.statusText}`);
    }

    const data = await res.json().catch(() => null);

    if (!opts.noStore) cacheSet(key, data, ttlMs);
    lsSet(key, data);
    return data;
  } catch (err) {
    // fallback localStorage
    const fb = lsGet(key);
    if (fb) return fb;
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}

// ---------------------------
// Endpoints específicos
// ---------------------------

/**
 * Preferido (por data):
 *   getFixturesByLeague(61, "2025-11-13", 5)
 *     -> ?league=61&date=YYYY-MM-DD&timezone=Europe/Lisbon&_ts=<bucket>
 *
 * Retro-compat ("next"):
 *   getFixturesByLeague(61, 5)   // usa ?next=5
 *   getFixturesByLeague(61, 0)   // força noStore
 */
export function getFixturesByLeague(
  leagueId: number,
  dateISO: string,
  cacheMinutes?: number
): Promise<{ response: ProxyFixture[] }>;
export function getFixturesByLeague(
  leagueId: number,
  next: number
): Promise<{ response: ProxyFixture[] }>;
export async function getFixturesByLeague(
  leagueId: number,
  dateOrNext: string | number,
  cacheMinutes = 5
) {
  // ---------- modo por data (preferido) ----------
  if (typeof dateOrNext === "string") {
    const bucket =
      cacheMinutes > 0
        ? Math.floor(Date.now() / (cacheMinutes * 60_000))
        : Date.now();

    const data = await fetchFromProxy(
      "/fixtures",
      {
        league: leagueId,
        date: dateOrNext,     // YYYY-MM-DD
        timezone: DEFAULT_TZ, // horas corretas
        _ts: bucket,          // bust simples de cache (server/CDN)
      },
      {
        noStore: cacheMinutes === 0,
        ttlMs: Math.max(1, cacheMinutes) * 60_000,
      }
    );

    let list: ProxyFixture[] = Array.isArray(data?.response) ? data.response : [];

    // Filtro anti Women/U-xx — aplica-se a liga e equipas
    list = list.filter((f) => {
      const ln = f?.league?.name ?? "";
      const hn = f?.teams?.home?.name ?? "";
      const an = f?.teams?.away?.name ?? "";
      if (isWomenOrYouth(ln) || isWomenOrYouth(hn) || isWomenOrYouth(an)) return false;
      return true;
    });

    return { response: list };
  }

  // ---------- retro-compat (modo "next") ----------
  const next = dateOrNext;
  const data = await fetchFromProxy(
    "/fixtures",
    {
      league: leagueId,
      next,
      timezone: DEFAULT_TZ,
      _ts: next === 0 ? Date.now() : Math.floor(Date.now() / 300_000), // 5m bucket
    },
    { noStore: next === 0, ttlMs: 60_000 }
  );

  let list: ProxyFixture[] = Array.isArray(data?.response) ? data.response : [];
  list = list.filter((f) => {
    const ln = f?.league?.name ?? "";
    const hn = f?.teams?.home?.name ?? "";
    const an = f?.teams?.away?.name ?? "";
    if (isWomenOrYouth(ln) || isWomenOrYouth(hn) || isWomenOrYouth(an)) return false;
    return true;
  });

  return { response: list };
}

export async function getNextFixtures() {
  const data = await fetchFromProxy("/fixtures", {
    next: 10,
    timezone: DEFAULT_TZ,
    _ts: Math.floor(Date.now() / 300_000),
  });
  let list: ProxyFixture[] = Array.isArray(data?.response) ? data.response : [];
  list = list.filter((f) => {
    const ln = f?.league?.name ?? "";
    const hn = f?.teams?.home?.name ?? "";
    const an = f?.teams?.away?.name ?? "";
    if (isWomenOrYouth(ln) || isWomenOrYouth(hn) || isWomenOrYouth(an)) return false;
    return true;
  });
  return { response: list };
}

export async function getStatus() {
  return fetchFromProxy("/status", { _ts: Math.floor(Date.now() / 60_000) });
}
