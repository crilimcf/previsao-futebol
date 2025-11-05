// =====================================================
// src/services/proxy.ts
// Proxy seguro para a API-Football via Render/Node
// =====================================================

const API_PROXY_URL =
  process.env.NEXT_PUBLIC_PROXY_BASE || "https://football-proxy-4ymo.onrender.com";

const PROXY_TOKEN =
  process.env.NEXT_PUBLIC_PROXY_TOKEN || "CF_Proxy_2025_Secret_!@#839";

// TTL padrão de cache (em milissegundos)
const DEFAULT_TTL = 60 * 1000; // 1 minuto

// Cache local em memória
const cache: Record<string, { data: any; timestamp: number }> = {};

// Helpers de cache
function getCache(key: string) {
  const item = cache[key];
  if (!item) return null;
  const expired = Date.now() - item.timestamp > DEFAULT_TTL;
  if (expired) {
    delete cache[key];
    return null;
  }
  return item.data;
}

function setCache(key: string, data: any) {
  cache[key] = { data, timestamp: Date.now() };
}

// Fallback localStorage
function getFallback(key: string) {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(`football_proxy_${key}`) : null;
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

type FetchOpts = { noStore?: boolean; timeoutMs?: number };

// Função genérica para chamadas com cache e fallback
async function fetchFromProxy(endpoint: string, params?: Record<string, any>, opts: FetchOpts = {}) {
  const key = `${endpoint}?${JSON.stringify(params || {})}`;

  // 1) Cache memória (salvo se noStore)
  if (!opts.noStore) {
    const cached = getCache(key);
    if (cached) return cached;
  }

  // 2) Fetch ao proxy
  const url = new URL(`${API_PROXY_URL}${endpoint}`);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.append(k, String(v)));

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts.timeoutMs ?? 12000);

  try {
    const res = await fetch(url.toString(), {
      headers: { "x-proxy-token": PROXY_TOKEN },
      cache: opts.noStore ? "no-store" : "default",
      next: { revalidate: 60 },
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      throw new Error(`Erro ${res.status}: ${await res.text()}`);
    }

    const data = await res.json();

    if (!opts.noStore) setCache(key, data);
    setFallback(key, data);
    return data;
  } catch (err) {
    clearTimeout(timeout);
    const fallback = getFallback(key);
    if (fallback) return fallback;
    throw err;
  }
}

// Endpoints específicos
export async function getFixturesByLeague(leagueId: number, next = 5) {
  // se next === 0, força no-store (sem cache de rede)
  return fetchFromProxy("/fixtures", { league: leagueId, next }, { noStore: next === 0 });
}

export async function getNextFixtures() {
  return fetchFromProxy("/fixtures", { next: 10 });
}

export async function getStatus() {
  return fetchFromProxy("/status");
}
