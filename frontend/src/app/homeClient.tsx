"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

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
} from "@/services/api";
import { getFixturesByLeague } from "@/services/proxy";

// -------------------------------
// Utils
// -------------------------------
function timeSince(ts: number) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return `${s}s atrás`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m atrás`;
  const h = Math.floor(m / 60);
  return `${h}h atrás`;
}
function ymdLocal(d: Date) {
  const off = d.getTimezoneOffset();
  const local = new Date(d.getTime() - off * 60000);
  return local.toISOString().split("T")[0];
}

const dateTabs = [
  { key: "today", label: "Hoje", calc: () => new Date() },
  { key: "tomorrow", label: "Amanhã", calc: () => new Date(Date.now() + 86400000) },
  { key: "after", label: "Depois de Amanhã", calc: () => new Date(Date.now() + 2 * 86400000) },
] as const;
type DateKey = typeof dateTabs[number]["key"];

// -------------------------------
// Componente
// -------------------------------
function HomeClientInner() {
  const router = useRouter();
  const search = useSearchParams();

  // Estados principais
  const [loading, setLoading] = useState(true);
  const [loadingFixtures, setLoadingFixtures] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string>("");

  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");

  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [selectedDateKey, setSelectedDateKey] = useState<DateKey>("today");

  const [liveFixtures, setLiveFixtures] = useState<any[]>([]);
  const [lastFixturesUpdate, setLastFixturesUpdate] = useState<number | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  // Leitura inicial de query params
  useEffect(() => {
    const qpLeague = search.get("league_id");
    const qpDate = search.get("date");
    if (qpLeague) setSelectedLeague(qpLeague);
    if (qpDate) {
      const t = ymdLocal(new Date());
      const tm = ymdLocal(new Date(Date.now() + 86400000));
      const af = ymdLocal(new Date(Date.now() + 2 * 86400000));
      const key: DateKey =
        qpDate === t ? "today" : qpDate === tm ? "tomorrow" : qpDate === af ? "after" : "today";
      setSelectedDateKey(key);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Data ISO da tab selecionada
  const selectedDateISO = useMemo(() => {
    const tab = dateTabs.find((t) => t.key === selectedDateKey) ?? dateTabs[0];
    return ymdLocal(tab.calc());
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

  // Carrega dados principais (predictions/stats/lastUpdate) com cancelamento
  async function loadMainData() {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

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

      if (ac.signal.aborted) return;

      setPredictions(Array.isArray(preds) ? preds : []);
      setStats(statsData && Object.keys(statsData).length > 0 ? (statsData as StatsType) : null);

      const lu = (lastU as { last_update?: string })?.last_update;
      if (lu && typeof lu === "string") {
        const d = new Date(lu.replace(" ", "T"));
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
      if (!ac.signal.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    loadMainData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeague, selectedDateISO]);

  // Fixtures reais via proxy (só quando liga específica)
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

  // Construção dinâmica da lista de ligas a partir das previsões
  const availableLeagues = useMemo(() => {
    const set = new Map<string, { id: string; name: string }>();
    for (const p of predictions) {
      const id = String(p.league_id ?? "");
      if (!id) continue;
      const nm =
        p.league_name || p.league || (p.country ? `${p.country}` : "Liga") + (id ? ` (${id})` : "");
      if (!set.has(id)) set.set(id, { id, name: nm });
    }
    const arr = Array.from(set.values()).sort((a, b) => a.name.localeCompare(b.name));
    return [{ id: "all", name: "🌍 Todas as Ligas" }, ...arr];
  }, [predictions]);

  // Se a liga selecionada não existir mais, regressa a "all"
  useEffect(() => {
    if (selectedLeague !== "all") {
      const exists = availableLeagues.some((l) => String(l.id) === String(selectedLeague));
      if (!exists) setSelectedLeague("all");
    }
  }, [availableLeagues, selectedLeague]);

  // Helpers UI
  const dcLabel = (dc: any) => (dc === "1X" || dc === "12" || dc === "X2" ? dc : "—");
  const toPct = (v?: number | null) => (typeof v === "number" ? `${Math.round(v * 100)}%` : "—");
  const oddFmt = (v?: number | null) => (typeof v === "number" ? v.toFixed(2) : "—");

  // Loading / Error
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

  // UI principal
  return (
    <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
      <Header />
      <main className="space-y-12 md:space-y-16">
        <InfoCard />
        {stats && <StatsAverage stats={stats} />}

        {/* FILTROS */}
        <div className="flex flex-col md:flex-row items-center justify-center gap-4 mb-8">
          {/* Ligas dinâmicas */}
          <select
            value={selectedLeague}
            onChange={(e) => {
              setSelectedLeague(e.target.value);
              // Quando troca de liga, recarrega imediatamente as fixtures da liga
              setTimeout(() => loadFixtures(true), 0);
            }}
            className="bg-gray-800 text-white px-5 py-2 rounded-xl border border-gray-700 focus:outline-none focus:ring-2 focus:ring-green-400 shadow-lg min-w-[220px]"
          >
            {availableLeagues.map((l) => (
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
                onClick={() => {
                  setSelectedDateKey(d.key);
                  // força fetch imediato sem esperar pelo useEffect
                  setTimeout(() => loadMainData(), 0);
                }}
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
                setUpdating(true);
                if (selectedLeague === "all") {
                  await triggerUpdate();
                  await loadMainData();
                } else {
                  await loadFixtures(true);
                }
              } catch (e) {
                console.error(e);
              } finally {
                setUpdating(false);
              }
            }}
            disabled={updating}
            className="flex items-center gap-2 bg-gray-800 text-sm text-gray-200 px-4 py-2 rounded-lg hover:bg-gray-700 transition disabled:opacity-60"
          >
            {updating ? "⏳ A atualizar..." : "🔁 Atualizar"}
          </button>
        </div>

        {/* ⚽ BLOCO: JOGOS REAIS (proxy) — só quando liga específica */}
        {selectedLeague !== "all" && (
          <div className="bg-gray-900 p-6 rounded-2xl shadow-lg border border-gray-800 mb-10">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-green-400">Jogos Reais (via API-Football)</h2>
              <button
                onClick={() => loadFixtures(true)}
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
                    <div className="flex items-center justify-center space-x-2 mb-2">
                      <img src={f.teams.home.logo} className="w-6 h-6" alt="" />
                      <span className="text-white font-medium">{f.teams.home.name}</span>
                      <span className="text-gray-400">vs</span>
                      <span className="text-white font-medium">{f.teams.away.name}</span>
                      <img src={f.teams.away.logo} className="w-6 h-6" alt="" />
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

        {/* BLOCO: PREVISÕES */}
        {Array.isArray(predictions) && predictions.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {predictions.map((p) => {
              const pr = p.predictions || ({} as Prediction["predictions"]);
              const winner = pr?.winner;
              const dc = pr?.double_chance;
              const over25 = pr?.over_2_5;
              const over15 = pr?.over_1_5;
              const btts = pr?.btts;

              const winnerLabel =
                winner?.class === 0 ? p.home_team : winner?.class === 1 ? "Empate" : winner?.class === 2 ? p.away_team : "—";
              const bestCS = pr?.correct_score?.best || "";

              return (
                <div
                  key={String(p.match_id)}
                  className="p-5 rounded-2xl border border-gray-800 bg-gray-950 hover:border-green-500 transition flex flex-col gap-4"
                >
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-gray-400">
                      {p.league_name || p.league || "Liga"} {p.country ? `(${p.country})` : ""}
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
                    <img src={p.home_logo || ""} alt="" className="w-7 h-7" />
                    <div className="text-white font-semibold text-center">{p.home_team}</div>
                    <div className="text-gray-500">vs</div>
                    <div className="text-white font-semibold text-center">{p.away_team}</div>
                    <img src={p.away_logo || ""} alt="" className="w-7 h-7" />
                  </div>

                  {/* Correct Score (best) destacado */}
                  <div className="flex items-center justify-center">
                    <span className="text-xs text-gray-400 mr-2">Correct Score (best):</span>
                    <span className="px-2 py-0.5 rounded bg-green-600/20 border border-green-600/40 text-green-300 text-xs">
                      {bestCS || "—"}
                    </span>
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
                        {dcLabel(dc?.class)} <span className="text-gray-400 ml-1">({toPct(dc?.prob)})</span>
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
                  {p.odds && (
                    <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
                      <div className="text-xs text-gray-400 mb-2">Odds</div>
                      <div className="grid grid-cols-3 gap-2 text-sm">
                        <div>
                          <div className="text-gray-400 text-xs mb-1">1X2</div>
                          <div className="text-white">
                            {oddFmt(p.odds?.["1x2"]?.home)} / {oddFmt(p.odds?.["1x2"]?.draw)} / {oddFmt(p.odds?.["1x2"]?.away)}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-400 text-xs mb-1">O/U 2.5</div>
                          <div className="text-white">
                            O {oddFmt(p.odds?.over_under?.["2.5"]?.over)} · U {oddFmt(p.odds?.over_under?.["2.5"]?.under)}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-400 text-xs mb-1">BTTS</div>
                          <div className="text-white">
                            Sim {oddFmt(p.odds?.btts?.yes)} · Não {oddFmt(p.odds?.btts?.no)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Detalhes: Correct Score top-3 e Top Scorers */}
                  <details className="rounded-xl bg-gray-900 border border-gray-800 p-3">
                    <summary className="cursor-pointer text-sm text-gray-200 select-none">Detalhes (Correct Score & Marcadores)</summary>
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Top-3 Correct Score</div>
                        <ul className="text-sm text-white space-y-1">
                          {(pr?.correct_score?.top3 || []).slice(0, 3).map((cs, idx) => (
                            <li key={idx} className="flex justify-between">
                              <span>{cs.score}</span>
                              <span className="text-gray-400">{Math.round((cs.prob ?? 0) * 1000) / 10}%</span>
                            </li>
                          ))}
                          {(!pr?.correct_score?.top3 || pr.correct_score.top3.length === 0) && (
                            <li className="text-gray-500">—</li>
                          )}
                        </ul>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Top Scorers (liga)</div>
                        <ul className="text-sm text-white space-y-1">
                          {(p.top_scorers || []).slice(0, 5).map((sc, idx) => (
                            <li key={idx} className="flex justify-between">
                              <span>
                                {sc.player} <span className="text-gray-400">({sc.team})</span>
                              </span>
                              <span className="text-gray-400">{sc.goals} golos</span>
                            </li>
                          ))}
                          {(!p.top_scorers || p.top_scorers.length === 0) && <li className="text-gray-500">—</li>}
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
            <span className="text-xs text-gray-400">Última atualização: {lastUpdate}</span>
          </div>
        )}
      </main>
    </div>
  );
}

// Envolvido em Suspense (Next 13+/15 exige para useSearchParams estável)
export default function HomeClient() {
  return (
    <Suspense fallback={<div className="min-h-screen container mx-auto px-4 py-16"><StatsSkeleton /></div>}>
      <HomeClientInner />
    </Suspense>
  );
}
