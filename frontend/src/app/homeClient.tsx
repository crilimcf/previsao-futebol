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
  const router = useRouter();
  const search = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");

  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [selectedDateKey, setSelectedDateKey] = useState<string>("today");

  // Ligas curadas (opcional)
  const [backendLeagues, setBackendLeagues] = useState<LeagueItem[]>([]);
  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        const ls = await getLeagues();
        if (isMounted) setBackendLeagues(ls ?? []);
      } catch {
        if (isMounted) setBackendLeagues([]);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, []);

  const allLeagues = useMemo(() => {
    const arr = backendLeagues.map((x) => ({ id: String(x.id), name: x.name }));
    return [{ id: "all", name: "🌍 Todas as Ligas" }, ...arr];
  }, [backendLeagues]);

  // Sincroniza estado inicial com a querystring
  useEffect(() => {
    const qpLeague = search.get("league_id");
    const qpDate = search.get("date");
    if (qpLeague) setSelectedLeague(qpLeague);

    // Aceita "today|tomorrow|after" ou YYYY-MM-DD
    if (qpDate) {
      const todayISO = ymd(new Date());
      const tomorrowISO = ymd(new Date(Date.now() + 86400000));
      const afterISO = ymd(new Date(Date.now() + 2 * 86400000));
      const key =
        qpDate === "today" || qpDate === todayISO
          ? "today"
          : qpDate === "tomorrow" || qpDate === tomorrowISO
          ? "tomorrow"
          : qpDate === "after" || qpDate === afterISO
          ? "after"
          : "today";
      setSelectedDateKey(key);
    }
    // depende de `search` (estável no Next 15); incluir para satisfazer ESLint
  }, [search]);

  const selectedDateISO = useMemo(() => {
    const tab = dateTabs.find((t) => t.key === selectedDateKey) ?? dateTabs[0];
    return ymd(tab.calc());
  }, [selectedDateKey]);

  // Reflete filtros na URL (inclui router e search nas deps para o ESLint)
  useEffect(() => {
    const params = new URLSearchParams(search.toString());
    params.set("date", selectedDateISO);
    if (selectedLeague && selectedLeague !== "all") params.set("league_id", String(selectedLeague));
    else params.delete("league_id");
    router.replace(`?${params.toString()}`);
  }, [selectedDateISO, selectedLeague, router, search]);

  // Carrega previsões + stats + lastUpdate (sem depender de função externa -> evita warning)
  useEffect(() => {
    let isMounted = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const params =
          selectedLeague === "all"
            ? { date: selectedDateISO }
            : { date: selectedDateISO, league_id: selectedLeague };

        const [preds, statsData, lastU] = await Promise.all([getPredictions(params), getStats(), getLastUpdate()]);
        const predsArray = Array.isArray(preds) ? preds : [];

        if (!isMounted) return;

        // mostra todas as ligas (sem filtro adicional)
        setPredictions(predsArray);
        setStats(statsData && Object.keys(statsData).length > 0 ? statsData : null);

        const lastUpdateRaw = (lastU as { last_update?: string })?.last_update;
        if (lastUpdateRaw && typeof lastUpdateRaw === "string") {
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
      } catch (e) {
        console.error(e);
        if (isMounted) setError("Falha ao carregar dados. Tenta novamente mais tarde.");
      } finally {
        if (isMounted) setLoading(false);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, [selectedLeague, selectedDateISO]);

  // Loading
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
            {[...Array(6)].map((_, idx) => (
              <CardSkeleton key={idx} />
            ))}
          </div>
        </main>
      </div>
    );
  }

  // Erro
  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-center px-4">
        <Header />
        <div className="mt-12 text-red-400 font-semibold">{error}</div>
      </div>
    );
  }

  // UI principal
  return (
    <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
      <Header />
      <main className="space-y-12 md:space-y-16">
        <InfoCard />

        {stats ? <StatsAverage stats={stats} /> : null}

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

          {/* Datas */}
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

          {/* Atualizar */}
          <button
            onClick={async () => {
              if (selectedLeague === "all") {
                await triggerUpdate();
              }
              // Recarrega sempre as previsões
              const params =
                selectedLeague === "all"
                  ? { date: selectedDateISO }
                  : { date: selectedDateISO, league_id: selectedLeague };
              setLoading(true);
              try {
                const [preds, statsData, lastU] = await Promise.all([getPredictions(params), getStats(), getLastUpdate()]);
                setPredictions(Array.isArray(preds) ? preds : []);
                setStats(statsData && Object.keys(statsData).length > 0 ? statsData : null);
                const lastUpdateRaw = (lastU as { last_update?: string })?.last_update;
                if (lastUpdateRaw && typeof lastUpdateRaw === "string") {
                  const d = new Date(lastUpdateRaw.replace(" ", "T"));
                  setLastUpdate(
                    `${d.toLocaleDateString("pt-PT", { day: "2-digit", month: "2-digit", year: "numeric" })} ${d.toLocaleTimeString(
                      "pt-PT",
                      { hour: "2-digit", minute: "2-digit" }
                    )}`
                  );
                }
              } finally {
                setLoading(false);
              }
            }}
            className="btn btn-ghost"
            disabled={loading}
          >
            {loading ? "⏳ A atualizar…" : "🔁 Atualizar"}
          </button>
        </div>

        {/* Previsões */}
        {Array.isArray(predictions) && predictions.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {predictions.slice(0, 60).map((p: any) => (
              <div key={p.fixture?.id ?? `${p.league?.id}-${p.teams?.home?.id}-${p.teams?.away?.id}`} className="card p-5 hover:border-emerald-400 transition">
                <div className="text-sm text-gray-400 mb-1">
                  {p.league?.name} {p.league?.country ? `(${p.league.country})` : ""}
                </div>
                <div className="flex items-center justify-center gap-2">
                  {p.teams?.home?.logo ? <Image src={p.teams.home.logo} alt="" width={24} height={24} /> : null}
                  <span className="text-white font-medium">{p.teams?.home?.name}</span>
                  <span className="text-gray-400">vs</span>
                  <span className="text-white font-medium">{p.teams?.away?.name}</span>
                  {p.teams?.away?.logo ? <Image src={p.teams.away.logo} alt="" width={24} height={24} /> : null}
                </div>
                <div className="text-xs text-gray-500 mt-1 text-center">
                  {p.fixture?.date ? new Date(p.fixture.date).toLocaleString("pt-PT") : "—"}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-center text-gray-400 mt-10">Nenhum jogo encontrado.</p>
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
