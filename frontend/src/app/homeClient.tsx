"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Header from "@/components/header";
import InfoCard from "@/components/infoCards";
import StatsAverage, { StatsType } from "@/components/StatsAverage";
import CardSkeleton from "@/components/CardSkeleton";
import StatsSkeleton from "@/components/StatsSkeleton";
import PredictionCard from "@/components/predictionCard";
import TopPredictionCard from "@/components/topPredictionCard";

import {
  getPredictions,
  getStats,
  getLastUpdate,
  triggerUpdate,
  type Prediction,
} from "@/services/api";
import { getFixturesByLeague } from "@/services/proxy";

// 🕒 Helper de tempo decorrido
function timeSince(ts: number) {
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 60) return `${seconds}s atrás`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m atrás`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h atrás`;
}

// YYYY-MM-DD local (browser)
function ymd(d: Date) {
  const off = d.getTimezoneOffset();
  const local = new Date(d.getTime() - off * 60000);
  return local.toISOString().split("T")[0];
}

const leagues = [
  { id: "all", name: "🌍 Todas as Ligas" },
  { id: 39, name: "🇬🇧 Premier League" },
  { id: 140, name: "🇪🇸 La Liga" },
  { id: 135, name: "🇮🇹 Serie A" },
  { id: 78, name: "🇩🇪 Bundesliga" },
  { id: 61, name: "🇫🇷 Ligue 1" },
  { id: 94, name: "🇵🇹 Primeira Liga" },
  { id: 88, name: "🇳🇱 Eredivisie" },
  { id: 2, name: "🏆 Champions League" },
];

const dateTabs = [
  { key: "today", label: "Hoje", calc: () => new Date() },
  { key: "tomorrow", label: "Amanhã", calc: () => new Date(Date.now() + 86400000) },
  { key: "after", label: "Depois de Amanhã", calc: () => new Date(Date.now() + 2 * 86400000) },
];

export default function HomeClient() {
  const router = useRouter();
  const search = useSearchParams();

  // -------------------------------
  // Estados
  // -------------------------------
  const [loading, setLoading] = useState(true);
  const [loadingFixtures, setLoadingFixtures] = useState(false);
  const [error, setError] = useState<string>("");

  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");

  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [selectedDateKey, setSelectedDateKey] = useState<string>("today");

  const [liveFixtures, setLiveFixtures] = useState<any[]>([]);
  const [lastFixturesUpdate, setLastFixturesUpdate] = useState<number | null>(null);

  const manualTriggerRef = useRef(false);

  // -------------------------------
  // Ler filtros da URL (se existirem)
  // -------------------------------
  useEffect(() => {
    const qpLeague = search.get("league_id");
    const qpDate = search.get("date");

    if (qpLeague) setSelectedLeague(qpLeague);

    if (qpDate) {
      const today = ymd(new Date());
      const tomorrow = ymd(new Date(Date.now() + 86400000));
      const after = ymd(new Date(Date.now() + 2 * 86400000));
      const key =
        qpDate === today ? "today" : qpDate === tomorrow ? "tomorrow" : qpDate === after ? "after" : "today";
      setSelectedDateKey(key);
    }
  }, [search]);

  // Data alvo conforme a tab
  const selectedDateISO = useMemo(() => {
    const tab = dateTabs.find((t) => t.key === selectedDateKey) ?? dateTabs[0];
    return ymd(tab.calc());
  }, [selectedDateKey]);

  // Escrever filtros na URL
  useEffect(() => {
    const params = new URLSearchParams(search.toString());
    params.set("date", selectedDateISO);
    if (selectedLeague && selectedLeague !== "all") params.set("league_id", String(selectedLeague));
    else params.delete("league_id");
    router.replace(`?${params.toString()}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDateISO, selectedLeague]);

  // -------------------------------
  // Fetch principal (predictions + stats + lastUpdate)
  // -------------------------------
  async function loadMainData() {
    setLoading(true);
    setError("");

    try {
      const params =
        selectedLeague === "all"
          ? { date: selectedDateISO }
          : { date: selectedDateISO, league_id: selectedLeague };

      const [preds, statsData, lastU] = await Promise.all([
        getPredictions(params),
        getStats(),
        getLastUpdate(),
      ]);

      setPredictions(Array.isArray(preds) ? (preds as Prediction[]) : []);
      setStats(statsData && Object.keys(statsData).length > 0 ? (statsData as StatsType) : null);

      const lastUpdateRaw = (lastU as { last_update?: string | null })?.last_update;
      if (typeof lastUpdateRaw === "string" && lastUpdateRaw.trim()) {
        const d = new Date(lastUpdateRaw.replace(" ", "T"));
        setLastUpdate(
          `${d.toLocaleDateString("pt-PT", { day: "2-digit", month: "2-digit", year: "numeric" })} ${d.toLocaleTimeString(
            "pt-PT",
            { hour: "2-digit", minute: "2-digit" }
          )}`
        );
      } else {
        setLastUpdate("");
      }
    } catch (e: any) {
      console.error(e);
      setError("Falha ao carregar dados. Tenta novamente mais tarde.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMainData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeague, selectedDateISO]);

  // -------------------------------
  // Fixtures reais via proxy (liga específica)
  // -------------------------------
  async function loadFixtures(ignoreCache = false) {
    if (selectedLeague === "all") {
      setLiveFixtures([]);
      setLastFixturesUpdate(null);
      return;
    }
    try {
      setLoadingFixtures(true);
      // usar next diferente para "furar" a cache em memória do proxy
      const data = await getFixturesByLeague(Number(selectedLeague), ignoreCache ? 0 : 5);
      setLiveFixtures(data?.response || []);
      setLastFixturesUpdate(Date.now());
    } catch (err) {
      console.error("Erro ao carregar fixtures:", err);
    } finally {
      setLoadingFixtures(false);
      manualTriggerRef.current = false;
    }
  }

  useEffect(() => {
    loadFixtures();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeague]);

  // -------------------------------
  // UI: Loading / Error
  // -------------------------------
  if (loading) {
    return (
      <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
        <Header />
        <main className="space-y-12 md:space-y-16">
          <InfoCard />
          <div className="mb-8">
            <StatsSkeleton />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[...Array(3)].map((_, idx) => (
              <CardSkeleton key={idx} />
            ))}
          </div>
        </main>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-center px-4">
        <Header />
        <div className="mt-12 text-red-400 font-semibold">{error}</div>
      </div>
    );
  }

  // -------------------------------
  // UI principal
  // -------------------------------
  return (
    <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
      <Header />
      <main className="space-y-12 md:space-y-16">
        <InfoCard />
        {stats && <StatsAverage stats={stats} />}

        {/* FILTROS */}
        <div className="flex flex-col md:flex-row items-center justify-center gap-4 mb-8">
          {/* Ligas */}
          <select
            value={selectedLeague}
            onChange={(e) => setSelectedLeague(e.target.value)}
            className="bg-gray-800 text-white px-5 py-2 rounded-xl border border-gray-700 focus:outline-none focus:ring-2 focus:ring-green-400 shadow-lg"
          >
            {leagues.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>

          {/* Datas */}
          <div className="flex gap-2">
            {dateTabs.map((d) => (
              <button
                key={d.key}
                onClick={() => setSelectedDateKey(d.key)}
                className={`px-4 py-2 rounded-lg font-medium transition ${
                  selectedDateKey === d.key ? "bg-green-500 text-white" : "bg-gray-800 text-gray-300 hover:bg-gray-700"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>

          {/* Botão Atualizar */}
          <button
            onClick={async () => {
              try {
                if (selectedLeague === "all") {
                  await triggerUpdate();      // força refresh no backend
                  await loadMainData();       // refaz fetch conforme filtros
                } else {
                  manualTriggerRef.current = true;
                  await loadFixtures(true);   // força refresh nos fixtures da liga
                }
              } catch (e) {
                console.error(e);
              }
            }}
            className="flex items-center gap-2 bg-gray-800 text-sm text-gray-200 px-4 py-2 rounded-lg hover:bg-gray-700 transition"
          >
            🔁 Atualizar
          </button>
        </div>

        {/* ⚽ BLOCO: JOGOS REAIS (proxy) — apenas quando liga específica */}
        {selectedLeague !== "all" && (
          <div className="bg-gray-900 p-6 rounded-2xl shadow-lg border border-gray-800 mb-10">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-green-400">Jogos Reais (via API-Football)</h2>
              <button
                onClick={() => {
                  manualTriggerRef.current = true;
                  loadFixtures(true);
                }}
                disabled={loadingFixtures}
                className="flex items-center gap-2 bg-gray-800 text-sm text-gray-200 px-4 py-2 rounded-lg hover:bg-gray-700 transition disabled:opacity-50"
              >
                {loadingFixtures ? "⏳ A atualizar..." : "🔁 Atualizar"}
              </button>
            </div>

            {loadingFixtures && (
              <div className="text-center text-sm text-gray-400 animate-pulse mb-4">
                A carregar jogos reais…
              </div>
            )}

            {liveFixtures.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {liveFixtures.map((f: any) => (
                  <div
                    key={f.fixture.id}
                    className="p-4 rounded-xl border border-gray-800 bg-gray-950 hover:border-green-500 transition"
                  >
                    <div className="flex items-center justify-center space-x-2 mb-2">
                      {f.teams?.home?.logo ? (
                        <img src={f.teams.home.logo} className="w-6 h-6" alt="" />
                      ) : (
                        <div className="w-6 h-6" />
                      )}
                      <span className="text-white font-medium">{f.teams?.home?.name}</span>
                      <span className="text-gray-400">vs</span>
                      <span className="text-white font-medium">{f.teams?.away?.name}</span>
                      {f.teams?.away?.logo ? (
                        <img src={f.teams.away.logo} className="w-6 h-6" alt="" />
                      ) : (
                        <div className="w-6 h-6" />
                      )}
                    </div>
                    <p className="text-sm text-center text-gray-400">
                      {new Date(f.fixture.date).toLocaleString("pt-PT")}
                    </p>
                    <p className="text-xs text-center text-gray-500 mt-1">
                      {f.league?.name} {f.league?.country ? `(${f.league.country})` : ""}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              !loadingFixtures && <p className="text-center text-gray-400 mt-4">Nenhum jogo encontrado.</p>
            )}

            {lastFixturesUpdate && (
              <div className="text-xs text-center text-gray-500 mt-4">
                Última atualização: {timeSince(lastFixturesUpdate)}
              </div>
            )}
          </div>
        )}

        {/* 🔮 PREVISÕES (agora usando os componentes PRO) */}
        {Array.isArray(predictions) && predictions.length > 0 ? (
          <>
            {/* Destaque do 1º jogo */}
            <div className="mb-6">
              <TopPredictionCard p={predictions[0]} />
            </div>

            {/* Restantes jogos */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {predictions.slice(1).map((p) => (
                <PredictionCard key={p.match_id} p={p} />
              ))}
            </div>
          </>
        ) : (
          <p className="text-center text-gray-400 mt-10">Nenhum jogo encontrado para os filtros.</p>
        )}

        {lastUpdate && (
          <div className="w-full text-center mt-10">
            <span className="text-xs text-gray-400">Última atualização global: {lastUpdate}</span>
          </div>
        )}
      </main>
    </div>
  );
}
