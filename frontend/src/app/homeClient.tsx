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

export default function HomeClient() {
  // loading / erro
  const [loading, setLoading] = useState(true);
  const [loadingFixtures, setLoadingFixtures] = useState(false);
  const [error, setError] = useState<string>("");

  // dados principais
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");

  // filtros
  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [selectedDateKey, setSelectedDateKey] = useState<string>("today");

  // ligas “curadas” pelo backend
  const [backendLeagues, setBackendLeagues] = useState<LeagueItem[]>([]);

  // fixtures reais (quando filtra por liga)
  const [liveFixtures, setLiveFixtures] = useState<any[]>([]);

  // carregar ligas do backend (uma vez)
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

  // conjuntos derivados
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

  // carregar previsões + stats + lastUpdate sempre que filtros mudem
  useEffect(() => {
    let cancelled = false;
    (async () => {
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

        if (cancelled) return;

        const predsArray: any[] = Array.isArray(preds) ? (preds as any[]) : [];
        const filtered =
          allowedLeagueIds.size > 0
            ? predsArray.filter((p) =>
                allowedLeagueIds.has(String(p.league_id ?? p.leagueId ?? p.league?.id))
              )
            : predsArray;

        setPredictions(filtered as Prediction[]);
        setStats(statsData && Object.keys(statsData || {}).length > 0 ? (statsData as StatsType) : null);

        const lastUpdateRaw = (lastU as { last_update?: string })?.last_update;
        if (typeof lastUpdateRaw === "string" && lastUpdateRaw) {
          const d = new Date(lastUpdateRaw.replace(" ", "T"));
          setLastUpdate(
            `${d.toLocaleDateString("pt-PT", { day: "2-digit", month: "2-digit", year: "numeric" })} ${d.toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })}`
          );
        } else {
          setLastUpdate("");
        }
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          setError("Falha ao carregar dados. Tenta novamente mais tarde.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedLeague, selectedDateISO, allowedLeagueIds]);

  // carregar fixtures reais quando seleciona liga específica
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (selectedLeague === "all") {
        setLiveFixtures([]);
        return;
      }
      try {
        setLoadingFixtures(true);
        const data = await getFixturesByLeague(Number(selectedLeague), 2); // 2 dias
        if (!cancelled) setLiveFixtures(data?.response || []);
      } catch (err) {
        if (!cancelled) console.error("Erro ao carregar fixtures:", err);
      } finally {
        if (!cancelled) setLoadingFixtures(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedLeague]);

  function fixtureDateSafe(d?: string) {
    const t = d ? Date.parse(d) : NaN;
    return Number.isFinite(t) ? new Date(d as string) : new Date();
  }

  // loading
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

  // erro
  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-center px-4">
        <Header />
        <div className="mt-12 text-red-400 font-semibold">{error}</div>
      </div>
    );
  }

  // UI
  return (
    <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
      <Header />
      <main className="space-y-12 md:space-y-16">
        <InfoCard />
        {stats && <StatsAverage stats={stats} />}

        {/* Filtros */}
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
                className={`btn ${selectedDateKey === d.key ? "btn-primary" : "btn-ghost"}`}
              >
                {d.label}
              </button>
            ))}
          </div>

          <button
            onClick={async () => {
              if (selectedLeague === "all") {
                await triggerUpdate();
                // recarrega dados após o backend atualizar
                setLoading(true);
                try {
                  const params = { date: ymd(new Date()) };
                  const [preds, statsData, lastU] = await Promise.all([
                    getPredictions(params),
                    getStats(),
                    getLastUpdate(),
                  ]);
                  const predsArray: any[] = Array.isArray(preds) ? (preds as any[]) : [];
                  const filtered =
                    allowedLeagueIds.size > 0
                      ? predsArray.filter((p) =>
                          allowedLeagueIds.has(String(p.league_id ?? p.leagueId ?? p.league?.id))
                        )
                      : predsArray;
                  setPredictions(filtered as Prediction[]);
                  setStats(statsData && Object.keys(statsData || {}).length > 0 ? (statsData as StatsType) : null);

                  const lastUpdateRaw = (lastU as { last_update?: string })?.last_update;
                  if (typeof lastUpdateRaw === "string" && lastUpdateRaw) {
                    const d = new Date(lastUpdateRaw.replace(" ", "T"));
                    setLastUpdate(
                      `${d.toLocaleDateString("pt-PT", { day: "2-digit", month: "2-digit", year: "numeric" })} ${d.toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })}`
                    );
                  }
                } catch (e) {
                  console.error(e);
                } finally {
                  setLoading(false);
                }
              } else {
                // se estiver por liga específica, atualiza apenas fixtures
                setLoadingFixtures(true);
                try {
                  const data = await getFixturesByLeague(Number(selectedLeague), 2);
                  setLiveFixtures(data?.response || []);
                } catch (e) {
                  console.error(e);
                } finally {
                  setLoadingFixtures(false);
                }
              }
            }}
            className="btn btn-ghost"
            disabled={loading || loadingFixtures}
          >
            {loading || loadingFixtures ? "⏳ A atualizar…" : "🔁 Atualizar"}
          </button>
        </div>

        {/* Jogos reais */}
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

        {/* Mensagem simples (para evitar helpers não usados) */}
        {Array.isArray(predictions) && predictions.length > 0 ? (
          <p className="text-center text-gray-400 mt-10">Previsões carregadas com sucesso!</p>
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
