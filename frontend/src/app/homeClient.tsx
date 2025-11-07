"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";

import Header from "@/components/header";
import InfoCard from "@/components/infoCards";
import StatsAverage, { StatsType } from "@/components/StatsAverage";
import CardSkeleton from "@/components/CardSkeleton";
import StatsSkeleton from "@/components/StatsSkeleton";
import {
  getPredictions,
  getStats,
  getLastUpdate,
  triggerUpdate,
  type Prediction,
  getLeagues,
  type LeagueItem,
} from "@/services/api";
import { getFixturesByLeague } from "@/services/proxy";

/* ----------------------------- */
/*  Utils e constantes auxiliares */
/* ----------------------------- */
function timeSince(ts: number) {
  const sec = Math.floor((Date.now() - ts) / 1000);
  if (sec < 60) return `${sec}s atrás`;
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m}m atrás`;
  const h = Math.floor(m / 60);
  return `${h}h atrás`;
}

function ymd(d: Date) {
  const off = d.getTimezoneOffset();
  const local = new Date(d.getTime() - off * 60000);
  return local.toISOString().split("T")[0];
}

const dateTabs = [
  { key: "today", label: "Hoje", calc: () => new Date() },
  { key: "tomorrow", label: "Amanhã", calc: () => new Date(Date.now() + 86400000) },
];

/* ----------------------------- */
/* Helpers de probabilidade/tipo */
/* ----------------------------- */
function prob01(v?: number | null): number {
  if (typeof v !== "number" || !isFinite(v)) return 0;
  return v > 1 ? Math.max(0, Math.min(1, v / 100)) : Math.max(0, Math.min(1, v));
}
function pctStr01(v?: number | null): string {
  return `${Math.round(prob01(v) * 100)}%`;
}
function tileClass(prob: number, isMax: boolean): string {
  const p = Math.round(prob * 100);
  if (isMax) return "bg-emerald-600/15 border-emerald-500/60 ring-2 ring-emerald-400";
  if (p >= 70) return "bg-emerald-500/10 border-emerald-400/40";
  if (p >= 60) return "bg-amber-500/10 border-amber-400/40";
  if (p >= 50) return "bg-sky-500/10 border-sky-400/40";
  return "bg-white/5 border-white/10";
}
function badgeClass(prob: number, isMax: boolean): string {
  const p = Math.round(prob * 100);
  if (isMax) return "bg-emerald-600 text-white font-semibold";
  if (p >= 70) return "bg-emerald-200 text-emerald-900";
  if (p >= 60) return "bg-amber-200 text-amber-900";
  if (p >= 50) return "bg-sky-200 text-sky-900";
  return "bg-gray-100 text-gray-700";
}

/* ----------------------------- */
/* Componente principal          */
/* ----------------------------- */
export default function HomeClient() {
  const router = useRouter();
  const search = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [loadingFixtures, setLoadingFixtures] = useState(false);
  const [error, setError] = useState("");

  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");
  const [selectedLeague, setSelectedLeague] = useState("all");
  const [selectedDateKey, setSelectedDateKey] = useState("today");

  const [backendLeagues, setBackendLeagues] = useState<LeagueItem[]>([]);
  const [liveFixtures, setLiveFixtures] = useState<any[]>([]);
  const [lastFixturesUpdate, setLastFixturesUpdate] = useState<number | null>(null);

  /* ---------- Ligas ---------- */
  useEffect(() => {
    (async () => {
      try {
        const ls = await getLeagues();
        setBackendLeagues(ls ?? []);
      } catch {
        setBackendLeagues([]);
      }
    })();
  }, []);

  const allowedLeagueIds = useMemo(
    () => new Set<string>(backendLeagues.map((x) => String(x.id))),
    [backendLeagues]
  );

  const allLeagues = useMemo(() => {
    const arr = backendLeagues.map((x) => ({ id: String(x.id), name: x.name }));
    return [{ id: "all", name: "🌍 Todas as Ligas" }, ...arr];
  }, [backendLeagues]);

  /* ---------- Data selecionada ---------- */
  const selectedDateISO = useMemo(() => {
    const tab = dateTabs.find((t) => t.key === selectedDateKey) ?? dateTabs[0];
    return ymd(tab.calc());
  }, [selectedDateKey]);

  /* ---------- Carrega dados principais ---------- */
  async function loadMainData() {
    setLoading(true);
    setError("");

    try {
      const params =
        selectedLeague === "all"
          ? { date: selectedDateISO }
          : { date: selectedDateISO, league_id: selectedLeague };

      // 🧩 IMPORTANTE: o backend retorna um array direto, não { predictions: [...] }
      const [resPreds, resStats, resUpdate] = await Promise.all([
        getPredictions(params),
        getStats(),
        getLastUpdate(),
      ]);

      const predsArray = Array.isArray(resPreds)
        ? (resPreds as Prediction[])
        : Array.isArray(resPreds?.response)
        ? (resPreds.response as Prediction[])
        : [];

      const filteredPreds =
        allowedLeagueIds.size > 0
          ? predsArray.filter((p: any) => allowedLeagueIds.has(String(p.league_id ?? p.leagueId ?? p.league?.id)))
          : predsArray;

      setPredictions(filteredPreds);
      setStats(resStats && Object.keys(resStats).length > 0 ? (resStats as StatsType) : null);

      const lastUpdateRaw = (resUpdate as { last_update?: string })?.last_update;
      if (lastUpdateRaw) {
        const d = new Date(lastUpdateRaw.replace(" ", "T"));
        setLastUpdate(
          `${d.toLocaleDateString("pt-PT")} ${d.toLocaleTimeString("pt-PT", {
            hour: "2-digit",
            minute: "2-digit",
          })}`
        );
      }
    } catch (err) {
      console.error("❌ Erro a carregar previsões:", err);
      setError("Falha ao carregar dados. Tenta novamente mais tarde.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMainData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeague, selectedDateISO, allowedLeagueIds]);

  /* ---------- Fixtures ---------- */
  async function loadFixtures(ignoreCache = false) {
    if (selectedLeague === "all") {
      setLiveFixtures([]);
      setLastFixturesUpdate(null);
      return;
    }
    try {
      setLoadingFixtures(true);
      const data = await getFixturesByLeague(Number(selectedLeague), ignoreCache ? 0 : 5);
      setLiveFixtures(data?.response || []);
      setLastFixturesUpdate(Date.now());
    } catch (err) {
      console.error("Erro ao carregar fixtures:", err);
    } finally {
      setLoadingFixtures(false);
    }
  }

  /* ---------- Render ---------- */
  if (loading) {
    return (
      <div className="min-h-screen container mx-auto px-4 py-8">
        <Header />
        <main className="space-y-12">
          <InfoCard />
          <StatsSkeleton />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[...Array(6)].map((_, idx) => (
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

  /* ---------- UI principal ---------- */
  return (
    <div className="min-h-screen container mx-auto px-4 py-8">
      <Header />
      <main className="space-y-12">
        <InfoCard />

        {stats ? <StatsAverage stats={stats} /> : null}

        {/* Filtros */}
        <div className="flex flex-col md:flex-row items-center justify-center gap-3 mb-8">
          <select
            value={selectedLeague}
            onChange={(e) => setSelectedLeague(e.target.value)}
            className="bg-white/5 text-white px-5 py-2 rounded-xl border border-white/10"
          >
            {allLeagues.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>

          <div className="flex gap-3">
            {dateTabs.map((d) => (
              <button
                key={d.key}
                onClick={() => setSelectedDateKey(d.key)}
                className={`btn ${selectedDateKey === d.key ? "btn-primary" : "btn-ghost"}`}
              >
                {d.label}
              </button>
            ))}
          </div>

          <button
            onClick={async () => {
              await triggerUpdate();
              await loadMainData();
            }}
            className="btn btn-ghost"
            disabled={loading || loadingFixtures}
          >
            {loading || loadingFixtures ? "⏳ A atualizar…" : "🔁 Atualizar"}
          </button>
        </div>

        {/* Previsões */}
        {Array.isArray(predictions) && predictions.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {predictions.map((p: any) => (
              <div key={p.fixture_id ?? p.match_id} className="card p-5">
                <div className="text-white font-semibold text-center">
                  {p.home_team} vs {p.away_team}
                </div>
                <div className="text-sm text-gray-400 text-center">
                  {p.league_name ?? "Liga"} ({p.country ?? "?"})
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-center text-gray-400">Nenhum jogo encontrado.</p>
        )}

        {lastUpdate && (
          <div className="text-center text-xs text-gray-500 mt-8">
            Última atualização global: {lastUpdate}
          </div>
        )}
      </main>
    </div>
  );
}
