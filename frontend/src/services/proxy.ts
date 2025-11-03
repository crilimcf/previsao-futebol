// =====================================================
// src/services/proxy.ts
// Proxy seguro para a API-Football via Render
// =====================================================

export const API_PROXY_URL = "https://football-proxy-4ymo.onrender.com";
export const PROXY_TOKEN = "CF_Proxy_2025_Secret_!@#839";

// TTL padrão de cache (em milissegundos)
const DEFAULT_TTL = 60 * 1000; // 1 minuto

// Cache local em memória
const cache: Record<
  string,
  { data: any; timestamp: number }
> = {};

// Helpers de cache
function getCache(key: string) {
  const item = cache[key];
  if (!item) return null;
  const expired = Date.now() - item.timestamp > DEFAULT_TTL;
  if (expired) {
    console.log(`🕑 [Cache Expirada] ${key}`);
    delete cache[key];
    return null;
  }
  console.log(`⚡ [Cache HIT] ${key}`);
  return item.data;
}

function setCache(key: string, data: any) {
  cache[key] = { data, timestamp: Date.now() };
  console.log(`💾 [Cache SET] ${key}`);
}

// Helpers de fallback local (IndexedDB ou localStorage)
function getFallback(key: string) {
  try {
    const raw = localStorage.getItem(`football_proxy_${key}`);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    console.log(`🪣 [Fallback HIT] ${key}`);
    return obj;
  } catch {
    return null;
  }
}

function setFallback(key: string, data: any) {
  try {
    localStorage.setItem(`football_proxy_${key}`, JSON.stringify(data));
    console.log(`📦 [Fallback SAVED] ${key}`);
  } catch {
    /* ignore */
  }
}

// Função genérica para chamadas com cache e fallback
async function fetchFromProxy(
  endpoint: string,
  params?: Record<string, any>
) {
  const key = `${endpoint}?${JSON.stringify(params || {})}`;

  // 1️⃣ Verifica cache em memória
  const cached = getCache(key);
  if (cached) return cached;

  // 2️⃣ Tenta buscar online
  const url = new URL(`${API_PROXY_URL}${endpoint}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) =>
      url.searchParams.append(k, String(v))
    );
  }

  console.log(`🌐 [Fetch] ${url.toString()}`);

  try {
    const res = await fetch(url.toString(), {
      headers: { "x-proxy-token": PROXY_TOKEN },
      next: { revalidate: 60 },
    });

    if (!res.ok) {
      throw new Error(`Erro ${res.status}: ${await res.text()}`);
    }

    const data = await res.json();

    // 3️⃣ Guarda cache + fallback local
    setCache(key, data);
    setFallback(key, data);

    return data;
  } catch (err) {
    console.warn(`⚠️ [Proxy Falhou] ${err}`);

    // 4️⃣ Usa fallback local se disponível
    const fallback = getFallback(key);
    if (fallback) return fallback;

    throw err;
  }
}

// Endpoints específicos
export async function getFixturesByLeague(leagueId: number, next = 5) {
  return fetchFromProxy("/fixtures", { league: leagueId, next });
}

export async function getNextFixtures() {
  return fetchFromProxy("/fixtures", { next: 10 });
}

export async function getStatus() {
  return fetchFromProxy("/status");
}
