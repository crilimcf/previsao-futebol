"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";

import Header from "@/components/header";
import InfoCard from "@/components/infoCards";
import StatsAverage, { StatsType } from "@/components/StatsAverage"; // <- usado
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

type DCClass = 0 | 1 | 2; // 0=1X, 1=12, 2=X2

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
  { key: "after", label: "Depois de Amanhã", calc: () => new Date(Date.now() + 2 * 86400000) },
];

export default function HomeClient() {
  const router = useRouter();
  const search = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [loadingFixtures, setLoadingFixtures] = useState(false);
  const [error, setError] = useState<string>("");

  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null); // <- usado
  const [lastUpdate, setLastUpdate] = useState("");

  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [selectedDateKey, setSelectedDateKey] = useState<string>("today");

  const [liveFixtures, setLiveFixtures] = useState<any[]>([]);
  const [lastFixturesUpdate, setLastFixturesUpdate] = useState<number | null>(null);
  const manualTriggerRef = useRef(false);

  // Ligas vindas do backend (/meta/leagues) — fallback para ligas presentes nas previsões
  const [backendLeagues, setBackendLeagues] = useState<LeagueItem[]>([]);
  useEffect(() => {
    (async () => {
      const ls = await getLeagues();
      setBackendLeagues(ls);
    })();
  }, []);

  // Fallback: construir lista a partir de predictions caso backend não devolva nada
  const leaguesFromPreds = useMemo(() => {
    const map = new Map<string, string>();
    predictions.forEach((p) => {
      const id = String(p.league_id ?? "");
      const name = (p.league_name ?? p.league ?? "Liga").toString();
      if (id && !map.has(id)) map.set(id, name);
    });
    return Array.from(map.entries())
      .sort((a, b) => a[1].localeCompare(b[1], "pt-PT"))
      .map(([id, name]) => ({ id, name }));
  }, [predictions]);

  const allLeagues: { id: string; name: string }[] = useMemo(() => {
    const source = backendLeagues.length > 0 ? backendLeagues : leaguesFromPreds;
    const arr = source.map((x) => ({ id: String(x.id), name: x.name }));
    return [{ id: "all", name: "🌍 Todas as Ligas" }, ...arr];
  }, [backendLeagues, leaguesFromPreds]);

  // Sincroniza estado inicial com query params
  useEffect(() => {
    const qpLeague = search.get("league_id");
    const qpDate = search.get("date");
    if (qpLeague) setSelectedLeague(qpLeague);

    if (qpDate) {
      const today = ymd(new Date());
      const tomorrow = ymd(new Date(Date.now() + 86400000));
      const after = ymd(new Date(Date.now() + 2 * 86400000));
      const key = qpDate === today ? "today" : qpDate === tomorrow ? "tomorrow" : qpDate === after ? "after" : "today";
      setSelectedDateKey(key);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedDateISO = useMemo(() => {
    const tab = dateTabs.find((t) => t.key === selectedDateKey) ?? dateTabs[0];
    return ymd(tab.calc());
  }, [selectedDateKey]);

  // Reflete filtros na URL
  useEffect(() => {
    const params = new URLSearchParams(search.toString());
    params.set("date", selectedDateISO);
    if (selectedLeague && selectedLeague !== "all") params.set("league_id", String(selectedLeague));
    else params.delete("league_id");
    router.replace(`?${params.toString()}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDateISO, selectedLeague]);

  // Carrega previsões + stats + lastUpdate
  async function loadMainData() {
    setLoading(true);
    setError("");

    try {
      const params =
        selectedLeague === "all"
          ? { date: selectedDateISO }
          : { date: selectedDateISO, league_id: selectedLeague };

      const [preds, statsData, lastU] = await Promise.all([getPredictions(params), getStats(), getLastUpdate()]);
      setPredictions(Array.isArray(preds) ? (preds as Prediction[]) : []);
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
    } catch (e) {
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

  // Fixtures reais por liga (proxy)
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

  // Helpers
  const dcLabel = (dc: DCClass | undefined) => (dc === 0 ? "1X" : dc === 1 ? "12" : dc === 2 ? "X2" : "—");
  const toPct = (v?: number | null) => (typeof v === "number" ? `${Math.round(v * 100)}%` : "—");
  const oddFmt = (v?: number | null) => (typeof v === "number" ? v.toFixed(2) : "—");
  const bestCorrectScore = (p: any) =>
    p?.correct_score_top3?.[0]?.score ?? p?.predictions?.correct_score?.best ?? "—";

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

        {/* Usa StatsAverage se existir */}
        {stats ? <StatsAverage stats={stats} /> : null}

        {/* Filtros */}
        <div className="flex flex-col md:flex-row items-center justify-center gap-3 md:gap-4 mb-8">
          {/* Ligas dinâmicas (do backend se houver, senão das previsões) */}
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

          {/* Datas — com espaçamento */}
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
                try {
                  await triggerUpdate();
                  await loadMainData();
                } catch (e) {
                  console.error(e);
                }
              } else {
                manualTriggerRef.current = true;
                await loadFixtures(true);
              }
            }}
            className="btn btn-ghost"
            disabled={loading || loadingFixtures}
            aria-busy={loading || loadingFixtures}
          >
            {loading || loadingFixtures ? "⏳ A atualizar…" : "🔁 Atualizar"}
          </button>
        </div>

        {/* Jogos reais (liga específica) */}
        {selectedLeague !== "all" && (
          <div className="card p-6 mb-10">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-emerald-400">Jogos Reais (via API-Football)</h2>
              <button
                onClick={() => {
                  manualTriggerRef.current = true;
                  loadFixtures(true);
                }}
                disabled={loadingFixtures}
                className="btn btn-ghost disabled:opacity-50"
              >
                {loadingFixtures ? "⏳ A atualizar…" : "🔁 Atualizar"}
              </button>
            </div>

            {loadingFixtures && (
              <div className="text-center text-sm text-gray-400 animate-pulse mb-4">A carregar jogos reais…</div>
            )}

            {liveFixtures.length > 0 ? (
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

        {/* Previsões */}
        {Array.isArray(predictions) && predictions.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {predictions.map((p: any) => {
              const winner = p?.predictions?.winner;
              const dc = p?.predictions?.double_chance;
              const over25 = p?.predictions?.over_2_5;
              const over15 = p?.predictions?.over_1_5;
              const btts = p?.predictions?.btts;

              const winnerLabel =
                winner?.class === 0 ? p.home_team :
                winner?.class === 1 ? "Empate" :
                winner?.class === 2 ? p.away_team : "—";

              const odds1x2 = p?.odds?.winner ?? p?.odds?.["1x2"] ?? {};
              const oddsOU25 = p?.odds?.over_2_5 ?? (p?.odds?.over_under?.["2.5"] ?? {});
              const oddsBTTS = p?.odds?.btts ?? {};

              return (
                <div key={String(p.match_id ?? p.fixture_id)} className="card p-5 hover:border-emerald-400 transition flex flex-col gap-4">
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-gray-400">
                      {(p.league_name ?? p.league) || "Liga"} {p.country ? `(${p.country})` : ""}
                    </div>
                    <div className="text-xs text-gray-500">
                      {new Date(p.date).toLocaleString("pt-PT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </div>
                  </div>

                  {/* Teams */}
                  <div className="flex items-center justify-center gap-3">
                    {!!p.home_logo && <Image src={p.home_logo} alt="" width={28} height={28} />}
                    <div className="text-white font-semibold text-center">{p.home_team}</div>
                    <div className="text-gray-500">vs</div>
                    <div className="text-white font-semibold text-center">{p.away_team}</div>
                    {!!p.away_logo && <Image src={p.away_logo} alt="" width={28} height={28} />}
                  </div>

                  {/* Correct score (best) */}
                  <div className="flex items-center justify-center gap-2">
                    <span className="badge">Correct Score</span>
                    <span className="text-sm text-white">{bestCorrectScore(p)}</span>
                  </div>

                  {/* Tips */}
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-xl bg-white/5 border border-white/10 p-3">
                      <div className="text-xs text-gray-400">Winner</div>
                      <div className="text-sm text-white">
                        {winnerLabel}{" "}
                        <span className="text-gray-400 ml-1">({toPct(winner?.confidence ?? winner?.prob)})</span>
                      </div>
                    </div>

                    <div className="rounded-xl bg-white/5 border border-white/10 p-3">
                      <div className="text-xs text-gray-400">Double Chance</div>
                      <div className="text-sm text-white">
                        {dcLabel(dc?.class)}{" "}
                        <span className="text-gray-400 ml-1">({toPct(dc?.confidence ?? dc?.prob)})</span>
                      </div>
                    </div>

                    <div className="rounded-xl bg-white/5 border border-white/10 p-3">
                      <div className="text-xs text-gray-400">Over 2.5</div>
                      <div className="text-sm text-white">
                        {over25?.class ? "Sim" : "Não"}{" "}
                        <span className="text-gray-400 ml-1">({toPct(over25?.confidence ?? over25?.prob)})</span>
                      </div>
                    </div>

                    <div className="rounded-xl bg-white/5 border border-white/10 p-3">
                      <div className="text-xs text-gray-400">Over 1.5</div>
                      <div className="text-sm text-white">
                        {over15?.class ? "Sim" : "Não"}{" "}
                        <span className="text-gray-400 ml-1">({toPct(over15?.confidence ?? over15?.prob)})</span>
                      </div>
                    </div>

                    <div className="rounded-xl bg-white/5 border border-white/10 p-3 col-span-2">
                      <div className="text-xs text-gray-400">BTTS</div>
                      <div className="text-sm text-white">
                        {btts?.class ? "Sim" : "Não"}{" "}
                        <span className="text-gray-400 ml-1">({toPct(btts?.confidence ?? btts?.prob)})</span>
                      </div>
                    </div>
                  </div>

                  {/* Odds */}
                  {(odds1x2 || oddsOU25 || oddsBTTS) && (
                    <div className="rounded-xl bg-white/5 border border-white/10 p-3">
                      <div className="text-xs text-gray-400 mb-2">Odds</div>
                      <div className="grid grid-cols-3 gap-2 text-sm">
                        <div>
                          <div className="text-gray-400 text-xs mb-1">1X2</div>
                          <div className="text-white">
                            {oddFmt(odds1x2?.home)} / {oddFmt(odds1x2?.draw)} / {oddFmt(odds1x2?.away)}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-400 text-xs mb-1">O/U 2.5</div>
                          <div className="text-white">
                            O {oddFmt(oddsOU25?.over)} · U {oddFmt(oddsOU25?.under)}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-400 text-xs mb-1">BTTS</div>
                          <div className="text-white">
                            Sim {oddFmt(oddsBTTS?.yes)} · Não {oddFmt(oddsBTTS?.no)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Detalhes */}
                  <details className="rounded-xl bg-white/5 border border-white/10 p-3">
                    <summary className="cursor-pointer text-sm text-gray-200 select-none">
                      Detalhes (Correct Score & Marcadores)
                    </summary>
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Top-3 Correct Score</div>
                        <ul className="text-sm text-white space-y-1">
                          {(p.correct_score_top3 ?? p?.predictions?.correct_score?.top3 ?? [])
                            .slice(0, 3)
                            .map((cs: any, idx: number) => (
                              <li key={idx} className="flex justify-between">
                                <span>{cs.score}</span>
                                <span className="text-gray-400">{Math.round((cs.prob ?? 0) * 1000) / 10}%</span>
                              </li>
                            ))}
                          {((p.correct_score_top3 ?? p?.predictions?.correct_score?.top3 ?? []).length === 0) && (
                            <li className="text-gray-500">—</li>
                          )}
                        </ul>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Top Scorers (liga)</div>
                        <ul className="text-sm text-white space-y-1">
                          {(p.top_scorers ?? []).slice(0, 5).map((sc: any, idx: number) => (
                            <li key={idx} className="flex justify-between">
                              <span>
                                {sc.player} <span className="text-gray-400">({sc.team})</span>
                              </span>
                              <span className="text-gray-400">{sc.goals} golos</span>
                            </li>
                          ))}
                          {(!(p.top_scorers ?? []).length) && <li className="text-gray-500">—</li>}
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
