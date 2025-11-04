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
  // Não definas Content-Type nem Authorization por defeito.
  // Isso evita OPTIONS em GETs simples.
  timeout: 12_000,
});

// Instância autenticada, usada só quando precisa
export const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000,
  headers: {
    Authorization: `Bearer ${API_TOKEN}`,
    "Content-Type": "application/json",
  },
});

// =====================================================
// 📊 Funções principais para o frontend consumir
// =====================================================

/** Obtém todas as previsões atuais. */
export async function getPredictions() {
  const r = await api.get("/predictions", { headers: { Accept: "application/json" } });
  if (!r.data) throw new Error("Predictions empty");
  return r.data;
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
  const r = await authApi.post("/meta/update"); // usa instância com Bearer
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
