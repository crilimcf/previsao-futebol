// =====================================================
// src/services/proxy.ts
// Proxy seguro para a API-Football via Render/Python-Proxy
// Suporta "date" + "timezone" e é retro-compatível com "next"
// =====================================================

const API_PROXY_URL =
  process.env.NEXT_PUBLIC_PROXY_BASE || "https://football-proxy-4ymo.onrender.com";

const PROXY_TOKEN =
  process.env.NEXT_PUBLIC_PROXY_TOKEN || "CF_Proxy_2025_Secret_!@#839";

const DEFAULT_TTL = 60 * 1000; // 1 min (cache memória)
const DEFAULT_TZ =
  process.env.NEXT_PUBLIC_TIMEZONE || "Europe/Lisbon";

// ---------------------------
// Cache em memória (com TTL)
// ---------------------------
type CacheEntry = { data: any; timestamp: number; ttlMs: number };
const cache: Record<string, CacheEntry> = {};

function getCache(key: string) {
  const item = cache[key];
  if (!item) return null;
  const expired = Date.now() - item.timestamp > item.ttlMs;
  if (expired) {
    delete cache[key];
    return null;
  }
  return item.data;
}
function setCache(key: string, data: any, ttlMs: number) {
  cache[key] = { data, timestamp: Date.now(), ttlMs };
}

// ---------------------------
// Fallback localStorage
// ---------------------------
function getFallback(key: string) {
  try {
    const raw =
      typeof window !== "undefined"
        ? localStorage.getItem(`football_proxy_${key}`)
        : null;
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function setFallback(key: string, data: any) {
  try {
    if (typeof window !== "undefined") {
      localStorage.setItem(`football_proxy_${key}`, JSON.stringify(data));
    }
  } catch {
    /* ignore */
  }
}

type FetchOpts = {
  noStore?: boolean;   // força não usar cache de rede
  timeoutMs?: number;  // timeout do fetch
  ttlMs?: number;      // TTL do cache em memória
};

// ---------------------------
// Fetch genérico com cache
// ---------------------------
async function fetchFromProxy(
  endpoint: string,
  params?: Record<string, any>,
  opts: FetchOpts = {}
) {
  const ttlMs = opts.ttlMs ?? DEFAULT_TTL;
  const key = `${endpoint}?${JSON.stringify(params || {})}`;

  if (!opts.noStore) {
    const cached = getCache(key);
    if (cached) return cached;
  }

  const base = API_PROXY_URL.replace(/\/+$/, "");
  const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = new URL(`${base}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.append(k, String(v));
    });
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts.timeoutMs ?? 12000);

  try {
    const res = await fetch(url.toString(), {
      headers: { "x-proxy-token": PROXY_TOKEN },
      cache: opts.noStore ? "no-store" : "default",
      next: { revalidate: Math.ceil(ttlMs / 1000) }, // dica p/ Next.js
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Erro ${res.status}: ${text || res.statusText}`);
    }

    const data = await res.json().catch(() => null);

    if (!opts.noStore) setCache(key, data, ttlMs);
    setFallback(key, data);
    return data;
  } catch (err) {
    clearTimeout(timeout);
    const fb = getFallback(key);
    if (fb) return fb;
    throw err;
  }
}

// ---------------------------
// Endpoints específicos
// ---------------------------

/**
 * Uso preferido (por data):
 *   getFixturesByLeague(61, "2025-11-08", 5)
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
): Promise<any>;
export function getFixturesByLeague(
  leagueId: number,
  next: number
): Promise<any>;
export async function getFixturesByLeague(
  leagueId: number,
  dateOrNext: string | number,
  cacheMinutes = 5
) {
  if (typeof dateOrNext === "string") {
    // Modo por data (preferido)
    const bucket =
      cacheMinutes > 0
        ? Math.floor(Date.now() / (cacheMinutes * 60_000))
        : Date.now();

    return fetchFromProxy(
      "/fixtures",
      {
        league: leagueId,
        date: dateOrNext,         // YYYY-MM-DD
        timezone: DEFAULT_TZ,     // horas certas
        _ts: bucket,              // bust de cache de rede (server/proxy/CDN)
      },
      {
        noStore: cacheMinutes === 0,
        ttlMs: Math.max(1, cacheMinutes) * 60_000,
      }
    );
  }

  // Retro-compat (modo "next")
  const next = dateOrNext;
  return fetchFromProxy(
    "/fixtures",
    {
      league: leagueId,
      next,
      timezone: DEFAULT_TZ,
      _ts: next === 0 ? Date.now() : Math.floor(Date.now() / 300000), // 5m bucket
    },
    { noStore: next === 0, ttlMs: 60_000 }
  );
}

export async function getNextFixtures() {
  return fetchFromProxy("/fixtures", {
    next: 10,
    timezone: DEFAULT_TZ,
    _ts: Math.floor(Date.now() / 300000),
  });
}

export async function getStatus() {
  return fetchFromProxy("/status", { _ts: Math.floor(Date.now() / 60000) });
}
