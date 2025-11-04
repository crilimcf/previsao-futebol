// =====================================================
// src/services/api.ts
// Cliente HTTP para comunicar com a API FastAPI (Render)
// =====================================================

import axios from "axios";

// 🌍 URL base da tua API (Render)
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "https://previsao-futebol.onrender.com";

// 🔑 Token de autenticação (igual ao ENDPOINT_API_KEY do backend)
export const API_TOKEN =
  process.env.NEXT_PUBLIC_API_TOKEN || "d110d6f22b446c54deadcadef7b234f6966af678";

// Instância Axios configurada
export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${API_TOKEN}`,
  },
});

// =====================================================
// 📊 Funções principais para o frontend consumir
// =====================================================

/**
 * Obtém todas as previsões atuais.
 */
export async function getPredictions() {
  try {
    const response = await api.get("/predictions");
    return response.data;
  } catch (error: any) {
    console.error("❌ Erro ao obter previsões:", error.message);
    throw error;
  }
}

/**
 * Obtém estatísticas agregadas.
 */
export async function getStats() {
  try {
    const response = await api.get("/stats");
    return response.data;
  } catch (error: any) {
    console.error("❌ Erro ao obter estatísticas:", error.message);
    throw error;
  }
}

/**
 * Obtém a data da última atualização.
 */
export async function getLastUpdate() {
  try {
    const response = await api.get("/meta/last-update");
    return response.data;
  } catch (error: any) {
    console.error("❌ Erro ao obter última atualização:", error.message);
    throw error;
  }
}

/**
 * Força atualização manual das previsões (endpoint protegido).
 */
export async function triggerUpdate() {
  try {
    const response = await api.post("/meta/update");
    return response.data;
  } catch (error: any) {
    console.error("❌ Erro ao atualizar previsões:", error.message);
    throw error;
  }
}

/**
 * Testa estado geral da API.
 */
export async function getApiHealth() {
  try {
    const response = await api.get("/healthz");
    return response.data;
  } catch {
    return { status: "offline" };
  }
}
