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

/* ----------------------------- */
/*   ✨ Helpers de destaque      */
/* ----------------------------- */
function prob01(v?: number | null): number {
  // aceita 0..1 (preferido) ou 0..100
  if (typeof v !== "number" || !isFinite(v)) return 0;
  return v > 1 ? Math.max(0, Math.min(1, v / 100)) : Math.max(0, Math.min(1, v));
}
function pctStr01(v?: number | null): string {
  return `${Math.round(prob01(v) * 100)}%`;
}
function tileClass(prob: number, isMax: boolean): string {
  const p = Math.round(prob * 100);
  // máximo do conjunto -> ring e border mais forte
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

export default function HomeClient() {
  const router = useRouter();
  const search = useSearchParams();

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

  /* ----------------------------- */
  /* 1) Ligas só do backend curado */
  /* ----------------------------- */
  const [backendLeagues, setBackendLeagues] = useState<LeagueItem[]>([]);
  useEffect(() => {
    (async () => {
      try {
        const ls = await getLeagues(); // <- deve devolver apenas as ligas curadas
        setBackendLeagues(ls ?? []);
      } catch {
        setBackendLeagues([]);
      }
    })();
  }, []);

  // Conjunto de IDs permitidos (para "cinto e suspensórios" no render das previsões)
  const allowedLeagueIds = useMemo(
    () => new Set<string>(backendLeagues.map((x) => String(x.id))),
    [backendLeagues]
  );

  // Dropdown: só ligas curadas + opção "Todas" (agregado das curadas)
  const allLeagues: { id: string; name: string }[] = useMemo(() => {
    const arr = backendLeagues.map((x) => ({ id: String(x.id), name: x.name }));
    return [{ id: "all", name: "🌍 Todas as Ligas" }, ...arr];
  }, [backendLeagues]);

  // Sincroniza estado inicial com query params
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
      const predsArray = Array.isArray(preds) ? (preds as Prediction[]) : [];

      // 🔒 Filtra previsões por ligas curadas (se houver lista do backend)
      const filteredPreds =
        allowedLeagueIds.size > 0
          ? predsArray.filter((p: any) => allowedLeagueIds.has(String(p.league_id ?? p.leagueId ?? p.league?.id)))
          : predsArray;

      setPredictions(filteredPreds);
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
      } else {
        setLastUpdate("");
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
  }, [selectedLeague, selectedDateISO, allowedLeagueIds]);

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
    }
  }

  useEffect(() => {
    loadFixtures();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeague]);

  // Helpers UI
  const dcLabel = (dc: DCClass | undefined) => (dc === 0 ? "1X" : dc === 1 ? "12" : dc === 2 ? "X2" : "—");
  const toPct = (v?: number | null) => (typeof v === "number" ? `${Math.round(prob01(v) * 100)}%` : "—");
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
          {/* Ligas dinâmicas (APENAS do backend curado) */}
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

          {/* Atualizar (único botão) */}
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
                await loadFixtures(true);
              }
            }}
            className="btn btn-ghost"
            disabled={loading || loadingFixtures}
            aria-busy={loading || loadingFixtures}
          >
            {loading || loadingFixtures ? "⏳ A atualizar…" : "🔁 Atualizar"}
          </button>

          {/* 🧹 Limpar */}
          <button
            onClick={() => {
              setSelectedLeague("all");
              setSelectedDateKey("today");
              setPredictions([]);
              setLiveFixtures([]);
              setLastFixturesUpdate(null);
              setError("");
              const params = new URLSearchParams();
              params.set("date", ymd(new Date()));
              router.replace(`?${params.toString()}`);
              loadMainData();
            }}
            className="btn btn-ghost"
            title="Limpar jogos visíveis e filtros"
          >
            🧹 Limpar
          </button>
        </div>

        {/* Jogos reais (liga específica) */}
        {selectedLeague !== "all" && (
          <div className="card p-6 mb-10">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-emerald-400">Jogos Reais (via API-Football)</h2>
              <span className="text-xs text-gray-500">Use o botão “Atualizar” no topo</span>
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
                      {new Date(fixtureDateSafe(f.fixture?.date)).toLocaleString("pt-PT")}
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
              <div className="text-xs text-center text-gray-500 mt-4">
                Última atualização: {timeSince(lastFixturesUpdate)}
              </div>
            )}
          </div>
        )}

        {/* Previsões (já filtradas pelas ligas curadas) */}
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

              // 🔎 percentagens normalizadas (0..1)
              const prWinner = prob01(winner?.confidence ?? winner?.prob);
              const prDC = prob01(dc?.confidence ?? dc?.prob);
              const prO25 = prob01(over25?.confidence ?? over25?.prob);
              const prO15 = prob01(over15?.confidence ?? over15?.prob);

              // ⭐ mercado "top" (maior % entre os quatro)
              const marketEntries: [keyof any, number][] = [
                ["winner", prWinner],
                ["double", prDC],
                ["over25", prO25],
                ["over15", prO15],
              ];
              const topEntry = marketEntries.reduce((a, b) => (b[1] > a[1] ? b : a), ["winner", -1]);
              const isTop = (k: string) => topEntry[0] === k;

              return (
                <div
                  key={String(p.match_id ?? p.fixture_id)}
                  className="card p-5 hover:border-emerald-400 transition flex flex-col gap-4"
                >
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-gray-400">
                      {(p.league_name ?? p.league) || "Liga"} {p.country ? `(${p.country})` : ""}
                    </div>
                    <div className="text-xs text-gray-500">
                      {new Date(p.date).toLocaleString("pt-PT", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
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

                  {/* Tips com destaque */}
                  <div className="grid grid-cols-2 gap-2">
                    {/* Winner */}
                    <div className={`rounded-xl border p-3 ${tileClass(prWinner, isTop("winner"))}`}>
                      <div className="text-xs text-gray-400 flex items-center justify-between">
                        <span>Winner</span>
                        {isTop("winner") && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/80 text-white">TOP</span>}
                      </div>
                      <div className="text-sm text-white mt-0.5">
                        {winnerLabel}{" "}
                        <span className={`ml-1 px-1.5 py-0.5 rounded text-[11px] ${badgeClass(prWinner, isTop("winner"))}`}>
                          {pctStr01(winner?.confidence ?? winner?.prob)}
                        </span>
                      </div>
                    </div>

                    {/* Double Chance */}
                    <div className={`rounded-xl border p-3 ${tileClass(prDC, isTop("double"))}`}>
                      <div className="text-xs text-gray-400 flex items-center justify-between">
                        <span>Double Chance</span>
                        {isTop("double") && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/80 text-white">TOP</span>}
                      </div>
                      <div className="text-sm text-white mt-0.5">
                        {dcLabel(dc?.class)}{" "}
                        <span className={`ml-1 px-1.5 py-0.5 rounded text-[11px] ${badgeClass(prDC, isTop("double"))}`}>
                          {pctStr01(dc?.confidence ?? dc?.prob)}
                        </span>
                      </div>
                    </div>

                    {/* Over 2.5 */}
                    <div className={`rounded-xl border p-3 ${tileClass(prO25, isTop("over25"))}`}>
                      <div className="text-xs text-gray-400 flex items-center justify-between">
                        <span>Over 2.5</span>
                        {isTop("over25") && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/80 text-white">TOP</span>}
                      </div>
                      <div className="text-sm text-white mt-0.5">
                        {over25?.class ? "Sim" : "Não"}{" "}
                        <span className={`ml-1 px-1.5 py-0.5 rounded text-[11px] ${badgeClass(prO25, isTop("over25"))}`}>
                          {pctStr01(over25?.confidence ?? over25?.prob)}
                        </span>
                      </div>
                    </div>

                    {/* Over 1.5 */}
                    <div className={`rounded-xl border p-3 ${tileClass(prO15, isTop("over15"))}`}>
                      <div className="text-xs text-gray-400 flex items-center justify-between">
                        <span>Over 1.5</span>
                        {isTop("over15") && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/80 text-white">TOP</span>}
                      </div>
                      <div className="text-sm text-white mt-0.5">
                        {over15?.class ? "Sim" : "Não"}{" "}
                        <span className={`ml-1 px-1.5 py-0.5 rounded text-[11px] ${badgeClass(prO15, isTop("over15"))}`}>
                          {pctStr01(over15?.confidence ?? over15?.prob)}
                        </span>
                      </div>
                    </div>

                    {/* BTTS (mantive, sem competir no TOP pedido) */}
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
                      {/* Correct Score */}
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Top-3 Correct Score</div>
                        <ul className="text-sm text-white space-y-1">
                          {(p.correct_score_top3 ?? p?.predictions?.correct_score?.top3 ?? [])
                            .slice(0, 3)
                            .map((cs: any, idx: number) => (
                              <li key={idx} className="flex justify-between">
                                <span>{cs.score}</span>
                                <span className="text-gray-400">{Math.round(prob01(cs.prob) * 1000) / 10}%</span>
                              </li>
                            ))}
                          {((p.correct_score_top3 ?? p?.predictions?.correct_score?.top3 ?? []).length === 0) && (
                            <li className="text-gray-500">—</li>
                          )}
                        </ul>
                      </div>

                      {/* Marcadores Prováveis */}
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Marcadores Prováveis</div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          <ul className="text-sm text-white space-y-1">
                            <li className="text-emerald-400">{p.home_team}</li>
                            {(p.predicted_scorers?.home ?? []).slice(0, 3).map((sc: any, idx: number) => (
                              <li key={idx} className="flex justify-between">
                                <span>{sc.player}</span>
                                <span className="text-gray-400">{Math.round(prob01(sc.prob) * 100)}%</span>
                              </li>
                            ))}
                            {!(p.predicted_scorers?.home ?? []).length && <li className="text-gray-500">—</li>}
                          </ul>

                          <ul className="text-sm text-white space-y-1">
                            <li className="text-emerald-400">{p.away_team}</li>
                            {(p.predicted_scorers?.away ?? []).slice(0, 3).map((sc: any, idx: number) => (
                              <li key={idx} className="flex justify-between">
                                <span>{sc.player}</span>
                                <span className="text-gray-400">{Math.round(prob01(sc.prob) * 100)}%</span>
                              </li>
                            ))}
                            {!(p.predicted_scorers?.away ?? []).length && <li className="text-gray-500">—</li>}
                          </ul>
                        </div>
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

// Evita crash se a API der date inválida
function fixtureDateSafe(d?: string) {
  const t = d ? Date.parse(d) : NaN;
  return Number.isFinite(t) ? new Date(d as string) : new Date();
}
