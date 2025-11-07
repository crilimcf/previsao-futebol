"use client";

import { useEffect, useMemo, useState } from "react";
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

type DCClass = 0 | 1 | 2;

function ymd(d: Date) {
  const off = d.getTimezoneOffset();
  const local = new Date(d.getTime() - off * 60000);
  return local.toISOString().split("T")[0];
}

const dateTabs = [
  { key: "today", label: "Hoje", calc: () => new Date() },
  { key: "tomorrow", label: "Amanhã", calc: () => new Date(Date.now() + 86400000) },
  { key: "after", label: "Depois de Amanhã", calc: () => new Date(Date.now() + 2 * 86400000) },
];

function prob01(v?: number | null): number {
  if (typeof v !== "number" || !isFinite(v)) return 0;
  return v > 1 ? Math.max(0, Math.min(1, v / 100)) : Math.max(0, Math.min(1, v));
}

export default function HomeClient() {
  const [loading, setLoading] = useState(true);
  const [loadingFixtures, setLoadingFixtures] = useState(false);
  const [error, setError] = useState<string>("");

  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");

  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [selectedDateKey, setSelectedDateKey] = useState<string>("today");

  const [liveFixtures, setLiveFixtures] = useState<any[]>([]);
  const [backendLeagues, setBackendLeagues] = useState<LeagueItem[]>([]);

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

  const selectedDateISO = useMemo(() => {
    const tab = dateTabs.find((t) => t.key === selectedDateKey) ?? dateTabs[0];
    return ymd(tab.calc());
  }, [selectedDateKey]);

  const loadMainData = async () => {
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

      const predsArray = Array.isArray(preds) ? preds : [];
      const filteredPreds =
        allowedLeagueIds.size > 0
          ? predsArray.filter((p: any) =>
              allowedLeagueIds.has(String(p.league_id ?? p.leagueId ?? p.league?.id))
            )
          : predsArray;

      setPredictions(filteredPreds);
      setStats(statsData && Object.keys(statsData).length > 0 ? statsData : null);

      const lastUpdateRaw = (lastU as { last_update?: string })?.last_update;
      if (lastUpdateRaw && typeof lastUpdateRaw === "string") {
        const d = new Date(lastUpdateRaw.replace(" ", "T"));
        setLastUpdate(
          `${d.toLocaleDateString("pt-PT", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
          })} ${d.toLocaleTimeString("pt-PT", {
            hour: "2-digit",
            minute: "2-digit",
          })}`
        );
      } else {
        setLastUpdate("");
      }
    } catch (e) {
      console.error(e);
      setError("Falha ao carregar dados. Tenta novamente mais tarde.");
    } finally {
      setLoading(false);
    }
  };

  const loadFixtures = async (ignoreCache = false) => {
    if (selectedLeague === "all") {
      setLiveFixtures([]);
      return;
    }
    try {
      setLoadingFixtures(true);
      const data = await getFixturesByLeague(Number(selectedLeague), ignoreCache ? 0 : 2);
      setLiveFixtures(data?.response || []);
    } catch (err) {
      console.error("Erro ao carregar fixtures:", err);
    } finally {
      setLoadingFixtures(false);
    }
  };

  useEffect(() => {
    loadMainData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeague, selectedDateISO, allowedLeagueIds]);

  useEffect(() => {
    loadFixtures();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeague]);

  function fixtureDateSafe(d?: string) {
    const t = d ? Date.parse(d) : NaN;
    return Number.isFinite(t) ? new Date(d as string) : new Date();
  }

  if (loading) {
    return (
      <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
        <Header />
        <main className="space-y-12 md:space-y-16">
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

  return (
    <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
      <Header />
      <main className="space-y-12 md:space-y-16">
        <InfoCard />
        {stats && <StatsAverage stats={stats} />}

        <div className="flex flex-col md:flex-row items-center justify-center gap-3 md:gap-4 mb-8">
          <select
            value={selectedLeague}
            onChange={(e) => setSelectedLeague(e.target.value)}
            className="bg-white/5 text-white px-5 py-2 rounded-xl border border-white/10 focus:outline-none focus:ring-2 focus:ring-emerald-400 shadow-lg"
          >
            {allLeagues.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>

          <div className="flex gap-3 md:gap-4">
            {dateTabs.map((d) => (
              <button
                key={d.key}
                onClick={() => setSelectedDateKey(d.key)}
                className={`btn ${
                  selectedDateKey === d.key ? "btn-primary" : "btn-ghost"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>

          <button
            onClick={async () => {
              if (selectedLeague === "all") {
                await triggerUpdate();
                await loadMainData();
              } else {
                await loadFixtures(true);
              }
            }}
            className="btn btn-ghost"
            disabled={loading || loadingFixtures}
          >
            {loading || loadingFixtures ? "⏳ A atualizar…" : "🔁 Atualizar"}
          </button>
        </div>

        {selectedLeague !== "all" && liveFixtures.length > 0 && (
          <div className="card p-6 mb-10">
            <h2 className="text-lg font-semibold text-emerald-400 mb-4">
              Jogos Reais (via API-Football)
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {liveFixtures.map((f: any) => (
                <div key={f.fixture.id} className="card p-4 hover:border-emerald-400 transition">
                  <div className="flex items-center justify-center gap-3 mb-2">
                    <Image src={f.teams.home.logo} alt="" width={24} height={24} />
                    <span className="text-white font-medium">{f.teams.home.name}</span>
                    <span className="text-gray-400">vs</span>
                    <span className="text-white font-medium">{f.teams.away.name}</span>
                    <Image src={f.teams.away.logo} alt="" width={24} height={24} />
                  </div>
                  <p className="text-sm text-center text-gray-400">
                    {new Date(fixtureDateSafe(f.fixture?.date)).toLocaleString("pt-PT")}
                  </p>
                  <p className="text-xs text-center text-gray-500 mt-1">
                    {f.league.name} ({f.league.country})
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {Array.isArray(predictions) && predictions.length > 0 ? (
          <p className="text-center text-gray-400 mt-10">Previsões carregadas com sucesso!</p>
        ) : (
          <p className="text-center text-gray-400 mt-10">
            Nenhum jogo encontrado para os filtros.
          </p>
        )}

        {lastUpdate && (
          <div className="w-full text-center mt-10">
            <span className="text-xs text-gray-400">
              Última atualização global: {lastUpdate}
            </span>
          </div>
        )}
      </main>
    </div>
  );
}
