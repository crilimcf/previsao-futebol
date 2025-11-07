"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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

// ---- Utils de data
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

  // 1) Buscar ligas curadas ao backend (para dropdown)
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

  // conj. de IDs curados (para eventual filtro quando NÃO for “all”)
  const allowedLeagueIds = useMemo(
    () => new Set<string>(backendLeagues.map((x) => String(x.id))),
    [backendLeagues]
  );

  // Dropdown com “Todas” + curadas
  const allLeagues: { id: string; name: string }[] = useMemo(() => {
    const arr = backendLeagues.map((x) => ({ id: String(x.id), name: x.name }));
    return [{ id: "all", name: "🌍 Todas as Ligas" }, ...arr];
  }, [backendLeagues]);

  // Sincroniza estado inicial com querystring (uma vez)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedDateISO = useMemo(() => {
    const tab = dateTabs.find((t) => t.key === selectedDateKey) ?? dateTabs[0];
    return ymd(tab.calc());
  }, [selectedDateKey]);

  // Reflete filtros na URL (para partilha/bookmark)
  useEffect(() => {
    const params = new URLSearchParams(search.toString());
    params.set("date", selectedDateISO);
    if (selectedLeague && selectedLeague !== "all") params.set("league_id", String(selectedLeague));
    else params.delete("league_id");
    router.replace(`?${params.toString()}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDateISO, selectedLeague]);

  // ---- Carrega previsões + stats + lastUpdate
  const loadMainData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const params =
        selectedLeague === "all"
          ? { date: selectedDateISO }
          : { date: selectedDateISO, league_id: selectedLeague };

      const [preds, statsData, lastU] = await Promise.all([getPredictions(params), getStats(), getLastUpdate()]);
      const predsArray = Array.isArray(preds) ? (preds as Prediction[]) : [];

      // ⚠️ Regra DOURADA:
      // - Se “Todas as Ligas”: NUNCA filtrar por curadas — mostra tudo o que vier do backend
      // - Se liga específica E houver lista de curadas: filtra por segurança
      let finalPreds = predsArray;
      if (selectedLeague !== "all" && allowedLeagueIds.size > 0) {
        finalPreds = predsArray.filter((p: any) =>
          allowedLeagueIds.has(String(p.league_id ?? p.leagueId ?? p.league?.id))
        );
      }

      // fallback de segurança: se por algum motivo vazio, mostra preds brutos
      if (finalPreds.length === 0 && predsArray.length > 0) {
        finalPreds = predsArray;
      }

      setPredictions(finalPreds);

      // tipagem defensiva evita o erro do Vercel
      const s: any = statsData;
      setStats(s && typeof s === "object" && Object.keys(s).length > 0 ? (s as StatsType) : null);

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
      setError("Falha ao carregar dados. Tenta novamente mais tarde.");
    } finally {
      setLoading(false);
    }
  }, [selectedLeague, selectedDateISO, allowedLeagueIds]);

  useEffect(() => {
    loadMainData();
  }, [loadMainData]);

  // ---- UI

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

        {stats ? <StatsAverage stats={stats} /> : null}

        {/* Filtros */}
        <div className="flex flex-col md:flex-row items-center justify-center gap-3 md:gap-4 mb-8">
          {/* Ligas (curadas) */}
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
              try {
                await triggerUpdate();
                await loadMainData();
              } catch (e) {
                console.error(e);
              }
            }}
            className="btn btn-ghost"
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? "⏳ A atualizar…" : "🔁 Atualizar"}
          </button>

          {/* Limpar */}
          <button
            onClick={() => {
              setSelectedLeague("all");
              setSelectedDateKey("today");
              setPredictions([]);
              setError("");
              const params = new URLSearchParams();
              params.set("date", ymd(new Date()));
              router.replace(`?${params.toString()}`);
              loadMainData();
            }}
            className="btn btn-ghost"
            title="Limpar filtros"
          >
            🧹 Limpar
          </button>
        </div>

        {/* Lista de jogos */}
        {Array.isArray(predictions) && predictions.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {predictions.map((p: any) => (
              <div
                key={String(p.match_id ?? p.fixture_id ?? p.fixture?.id ?? `${p.home_team}-${p.away_team}-${p.date}`)}
                className="card p-5 hover:border-emerald-400 transition flex flex-col gap-3"
              >
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <div>
                    {(p.league_name ?? p.league?.name ?? "Liga")}{" "}
                    {p.league?.country ? `(${p.league.country})` : ""}
                  </div>
                  <div>
                    {new Date(p.date ?? p.fixture?.date ?? new Date()).toLocaleString("pt-PT", {
                      day: "2-digit",
                      month: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </div>
                </div>

                <div className="flex items-center justify-center gap-3">
                  {!!(p.home_logo ?? p.teams?.home?.logo) && (
                    <Image src={p.home_logo ?? p.teams.home.logo} alt="" width={28} height={28} />
                  )}
                  <div className="text-white font-semibold text-center">
                    {p.home_team ?? p.teams?.home?.name ?? "Casa"}
                  </div>
                  <div className="text-gray-500">vs</div>
                  <div className="text-white font-semibold text-center">
                    {p.away_team ?? p.teams?.away?.name ?? "Fora"}
                  </div>
                  {!!(p.away_logo ?? p.teams?.away?.logo) && (
                    <Image src={p.away_logo ?? p.teams.away.logo} alt="" width={28} height={28} />
                  )}
                </div>

                {p.predictions && Object.keys(p.predictions).length > 0 ? (
                  <div className="rounded-xl bg-white/5 border border-white/10 p-3 text-sm text-gray-300">
                    {/* espaço para tu recompores os mercados quando os dados de predictions estiverem cheios */}
                    Tip sugerida disponível.
                  </div>
                ) : (
                  <div className="text-xs text-gray-500">Sem tip calculada para este jogo.</div>
                )}
              </div>
            ))}
          </div>
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
