"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";

import Header from "@/components/header";
import InfoCard from "@/components/infoCards";
import StatsAverage, { StatsType } from "@/components/StatsAverage";
import CardSkeleton from "@/components/CardSkeleton";
import StatsSkeleton from "@/components/StatsSkeleton";

import {
  getPredictions as apiGetPredictions,
  getStats,
  getLastUpdate,
  triggerUpdate,
  type Prediction as PredictionType,
} from "@/services/api";
import { getFixturesByLeague } from "@/services/proxy";

// -------------------------------
// Tipos (alinhados ao backend)
// -------------------------------
type DCClass = 0 | 1 | 2; // 0=1X, 1=12, 2=X2

// 🕒 Helper de tempo decorrido
function timeSince(ts: number) {
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 60) return `${seconds}s atrás`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m atrás`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h atrás`;
}

// YYYY-MM-DD local
function ymd(d: Date) {
  const off = d.getTimezoneOffset();
  const local = new Date(d.getTime() - off * 60000);
  return local.toISOString().split("T")[0];
}

const FALLBACK_SVG =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'><rect width='100%' height='100%' fill='%23222'/></svg>";

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
  // Estados principais
  // -------------------------------
  const [loading, setLoading] = useState(true);
  const [loadingFixtures, setLoadingFixtures] = useState(false);
  const [error, setError] = useState<string>("");

  const [predictions, setPredictions] = useState<PredictionType[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");

  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [selectedDateKey, setSelectedDateKey] = useState<string>("today");

  const [liveFixtures, setLiveFixtures] = useState<any[]>([]);
  const [lastFixturesUpdate, setLastFixturesUpdate] = useState<number | null>(null);

  const manualTriggerRef = useRef(false);

  // -------------------------------
  // Sincronizar com URL (query params)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Formata a data alvo conforme a tab
  const selectedDateISO = useMemo(() => {
    const tab = dateTabs.find((t) => t.key === selectedDateKey) ?? dateTabs[0];
    return ymd(tab.calc());
  }, [selectedDateKey]);

  // Atualiza URL quando filtros mudam
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
        apiGetPredictions(params),
        getStats(),
        getLastUpdate(),
      ]);

      setPredictions(Array.isArray(preds) ? (preds as PredictionType[]) : []);
      setStats(statsData && Object.keys(statsData).length > 0 ? (statsData as StatsType) : null);

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

      if ((!preds || (Array.isArray(preds) && preds.length === 0)) && (!statsData || Object.keys(statsData).length === 0)) {
        setError("Sem dados disponíveis no momento.");
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
  // Fixtures reais via proxy (para liga específica)
  // -------------------------------
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
      manualTriggerRef.current = false;
    }
  }

  useEffect(() => {
    loadFixtures();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeague]);

  // -------------------------------
  // Render helpers
  // -------------------------------
  const dcLabel = (dc: DCClass | undefined) => (dc === 0 ? "1X" : dc === 1 ? "12" : dc === 2 ? "X2" : "-");
  const toPct = (v?: number | null) => (typeof v === "number" ? `${Math.round(v * 100)}%` : "—");
  const oddFmt = (v?: number | null) => (typeof v === "number" ? v.toFixed(2) : "—");

  // -------------------------------
  // UI Loading / Error
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
              if (selectedLeague === "all") {
                try {
                  await triggerUpdate(); // força refresh no backend
                  await loadMainData();
                } catch (e) {
                  console.error(e);
                }
              } else {
                manualTriggerRef.current = true;
                await loadFixtures(true);
              }
            }}
            className="flex items-center gap-2 bg-gray-800 text-sm text-gray-200 px-4 py-2 rounded-lg hover:bg-gray-700 transition"
          >
            🔁 Atualizar
          </button>
        </div>

        {/* ⚽ BLOCO: JOGOS REAIS (proxy) — só quando liga específica */}
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
              <div className="text-center text-sm text-gray-400 animate-pulse mb-4">A carregar jogos reais…</div>
            )}

            {liveFixtures.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {liveFixtures.map((f: any) => (
                  <div
                    key={f.fixture.id}
                    className="p-4 rounded-xl border border-gray-800 bg-gray-950 hover:border-green-500 transition"
                  >
                    <div className="flex items-center justify-center gap-3 mb-2">
                      <Image
                        src={f.teams.home.logo || FALLBACK_SVG}
                        alt={f.teams?.home?.name || "Home"}
                        width={24}
                        height={24}
                        className="w-6 h-6"
                        unoptimized
                      />
                      <span className="text-white font-medium">{f.teams.home.name}</span>
                      <span className="text-gray-400">vs</span>
                      <span className="text-white font-medium">{f.teams.away.name}</span>
                      <Image
                        src={f.teams.away.logo || FALLBACK_SVG}
                        alt={f.teams?.away?.name || "Away"}
                        width={24}
                        height={24}
                        className="w-6 h-6"
                        unoptimized
                      />
                    </div>
                    <p className="text-sm text-center text-gray-400">
                      {new Date(f.fixture.date).toLocaleString("pt-PT")}
                    </p>
                    <p className="text-xs text-center text-gray-500 mt-1">
                      {f.league.name} ({f.league.country})
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              !loadingFixtures && <p className="text-center text-gray-400 mt-4">Nenhum jogo encontrado.</p>
            )}

            {lastFixturesUpdate && (
              <div className="text-xs text-center text-gray-500 mt-4">Última atualização: {timeSince(lastFixturesUpdate)}</div>
            )}
          </div>
        )}

        {/* BLOCO: PREVISÕES (com campos PRO) */}
        {Array.isArray(predictions) && predictions.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {predictions.map((p) => {
              const winner = (p as any).predictions?.winner;
              const dc = (p as any).predictions?.double_chance;
              const over25 = (p as any).predictions?.over_2_5;
              const over15 = (p as any).predictions?.over_1_5;
              const btts = (p as any).predictions?.btts;

              const winnerLabel =
                winner?.class === 0 ? p.home_team : winner?.class === 1 ? "Empate" : winner?.class === 2 ? p.away_team : "—";

              return (
                <div
                  key={String((p as any).match_id ?? (p as any).fixture_id)}
                  className="p-5 rounded-2xl border border-gray-800 bg-gray-950 hover:border-green-500 transition flex flex-col gap-4"
                >
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-gray-400">
                      {(p as any).league_name || (p as any).league} {(p as any).country ? `(${(p as any).country})` : ""}
                    </div>
                    <div className="text-xs text-gray-500">
                      {new Date(p.date).toLocaleString("pt-PT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </div>
                  </div>

                  {/* Teams */}
                  <div className="flex items-center justify-center gap-3">
                    <Image
                      src={(p as any).home_logo || FALLBACK_SVG}
                      alt={p.home_team || "Home"}
                      width={28}
                      height={28}
                      className="w-7 h-7"
                      unoptimized
                    />
                    <div className="text-white font-semibold text-center">{p.home_team}</div>
                    <div className="text-gray-500">vs</div>
                    <div className="text-white font-semibold text-center">{p.away_team}</div>
                    <Image
                      src={(p as any).away_logo || FALLBACK_SVG}
                      alt={p.away_team || "Away"}
                      width={28}
                      height={28}
                      className="w-7 h-7"
                      unoptimized
                    />
                  </div>

                  {/* Tips principais */}
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
                      <div className="text-xs text-gray-400">Winner</div>
                      <div className="text-sm text-white">
                        {winnerLabel} <span className="text-gray-400 ml-1">({toPct(winner?.prob)})</span>
                      </div>
                    </div>

                    <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
                      <div className="text-xs text-gray-400">Double Chance</div>
                      <div className="text-sm text-white">
                        {dcLabel(dc?.class as DCClass)} <span className="text-gray-400 ml-1">({toPct(dc?.prob)})</span>
                      </div>
                    </div>

                    <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
                      <div className="text-xs text-gray-400">Over 2.5</div>
                      <div className="text-sm text-white">
                        {over25?.class ? "Sim" : "Não"} <span className="text-gray-400 ml-1">({toPct(over25?.prob)})</span>
                      </div>
                    </div>

                    <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
                      <div className="text-xs text-gray-400">Over 1.5</div>
                      <div className="text-sm text-white">
                        {over15?.class ? "Sim" : "Não"} <span className="text-gray-400 ml-1">({toPct(over15?.prob)})</span>
                      </div>
                    </div>

                    <div className="rounded-xl bg-gray-900 border border-gray-800 p-3 col-span-2">
                      <div className="text-xs text-gray-400">BTTS</div>
                      <div className="text-sm text-white">
                        {btts?.class ? "Sim" : "Não"} <span className="text-gray-400 ml-1">({toPct(btts?.prob)})</span>
                      </div>
                    </div>
                  </div>

                  {/* Odds lineadas */}
                  {(p as any).odds && (
                    <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
                      <div className="text-xs text-gray-400 mb-2">Odds</div>
                      <div className="grid grid-cols-3 gap-2 text-sm">
                        <div>
                          <div className="text-gray-400 text-xs mb-1">1X2</div>
                          <div className="text-white">
                            {oddFmt((p as any).odds?.["1x2"]?.home)} / {oddFmt((p as any).odds?.["1x2"]?.draw)} /{" "}
                            {oddFmt((p as any).odds?.["1x2"]?.away)}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-400 text-xs mb-1">O/U 2.5</div>
                          <div className="text-white">
                            O {oddFmt((p as any).odds?.over_under?.["2.5"]?.over)} · U {oddFmt((p as any).odds?.over_under?.["2.5"]?.under)}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-400 text-xs mb-1">BTTS</div>
                          <div className="text-white">
                            Sim {oddFmt((p as any).odds?.btts?.yes)} · Não {oddFmt((p as any).odds?.btts?.no)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Accordion Detalhes: Correct Score + Top Scorers */}
                  <details className="rounded-xl bg-gray-900 border border-gray-800 p-3">
                    <summary className="cursor-pointer text-sm text-gray-200 select-none">Detalhes (Correct Score & Marcadores)</summary>
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Top-3 Correct Score</div>
                        <ul className="text-sm text-white space-y-1">
                          {((p as any).predictions?.correct_score?.top3 || []).slice(0, 3).map((cs: any, idx: number) => (
                            <li key={idx} className="flex justify-between">
                              <span>{cs.score}</span>
                              <span className="text-gray-400">{Math.round((cs.prob ?? 0) * 1000) / 10}%</span>
                            </li>
                          ))}
                          {(!((p as any).predictions?.correct_score?.top3) ||
                            (p as any).predictions?.correct_score?.top3?.length === 0) && (
                            <li className="text-gray-500">—</li>
                          )}
                        </ul>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Top Scorers (liga)</div>
                        <ul className="text-sm text-white space-y-1">
                          {((p as any).top_scorers || []).slice(0, 5).map((sc: any, idx: number) => (
                            <li key={idx} className="flex justify-between">
                              <span>
                                {sc.player} <span className="text-gray-400">({sc.team})</span>
                              </span>
                              <span className="text-gray-400">{sc.goals} golos</span>
                            </li>
                          ))}
                          {(!((p as any).top_scorers) || (p as any).top_scorers?.length === 0) && (
                            <li className="text-gray-500">—</li>
                          )}
                        </ul>
                      </div>
                    </div>
                  </details>
                </div>
              );
            })}
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
