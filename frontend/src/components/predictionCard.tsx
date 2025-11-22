"use client";

import Image from "next/image";

type DCClass = 0 | 1 | 2;

const FALLBACK_SVG =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'><rect width='100%' height='100%' fill='%23222'/></svg>";

const dcLabel = (dc: DCClass | undefined) =>
  dc === 0 ? "1X" : dc === 1 ? "12" : dc === 2 ? "X2" : "—";

// normaliza 0..1 ou 0..100 para percentagem
function prob01(v?: number | null): number {
  if (typeof v !== "number" || !isFinite(v)) return 0;
  return v > 1 ? Math.max(0, Math.min(1, v / 100)) : Math.max(0, Math.min(1, v));
}
const toPct = (v?: number | null) => `${Math.round(prob01(v) * 100)}%`;
const oddFmt = (v?: number | null) =>
  typeof v === "number" && isFinite(v) ? v.toFixed(2) : "—";

const isValidOdd = (v?: number | null) =>
  typeof v === "number" && isFinite(v) && v >= 1.2 && v <= 100;

// evita crash se vier undefined ou uma string inválida
function safeDate(val?: string | number | Date) {
  if (val === undefined || val === null) return new Date();
  const d = new Date(val as any);
  if (!isNaN(d.getTime())) return d;
  // tenta fallback simples (ex.: "YYYY-MM-DD HH:MM" -> "YYYY-MM-DDTHH:MM")
  if (typeof val === "string") {
    const d2 = new Date(val.replace(" ", "T"));
    if (!isNaN(d2.getTime())) return d2;
  }
  return new Date();
}

// -----------------------------
// TIPOS
// -----------------------------

type ProbableScorer = {
  player_id?: number;
  name: string;
  team_id?: number;
  team_name?: string;
  position?: string;
  photo?: string;
  stats?: any;
  probability?: number;      // 0..1
  probability_pct?: number;  // 0..100
};

export interface PredictionCardProps {
  league?: string;
  league_name?: string;
  country?: string;
  date?: string; // pode vir ausente em alguns registos
  home_team: string;
  away_team: string;
  home_logo?: string;
  away_logo?: string;
  odds_source?: "market" | "model"; // <— para ocultar OU 2.5 se não for mercado
  predictions?: {
    winner?: { class: 0 | 1 | 2; prob?: number; confidence?: number };
    double_chance?: { class: DCClass; prob?: number; confidence?: number };
    over_2_5?: { class: 0 | 1; prob?: number; confidence?: number };
    over_1_5?: { class: 0 | 1; prob?: number; confidence?: number };
    btts?: { class: 0 | 1; prob?: number; confidence?: number };
    correct_score?: { best?: string; top3?: { score: string; prob: number }[] };
  };
  odds?: {
    winner?: { home?: number; draw?: number; away?: number };
    ["1x2"]?: { home?: number; draw?: number; away?: number };
    over_2_5?: { over?: number; under?: number };
    over_under?: Record<string, { over?: number; under?: number }>;
    btts?: { yes?: number; no?: number };
  };
  // ranking geral da liga (mantido como fallback)
  top_scorers?: { player: string; team: string; goals: number }[];
  // NOVO: marcadores prováveis por jogo (casa/fora)
  probable_scorers?: {
    home?: ProbableScorer[];
    away?: ProbableScorer[];
  };
}

export default function PredictionCard({
  league,
  league_name,
  country,
  date,
  home_team,
  away_team,
  home_logo,
  away_logo,
  predictions,
  odds,
  top_scorers,
  odds_source,
  probable_scorers, // NOVO
}: PredictionCardProps) {
  // Winner baseado SEMPRE nas probabilidades calibradas (bivariado+iso ou ficheiro)
  const winnerProbs = (predictions as any)?.winner?.probs as
    | { home?: number; draw?: number; away?: number }
    | undefined;

  let winnerSide: 0 | 1 | 2 | null = predictions?.winner?.class ?? null;
  if (winnerProbs) {
    const ph = typeof winnerProbs.home === "number" ? winnerProbs.home : 0;
    const pd = typeof winnerProbs.draw === "number" ? winnerProbs.draw : 0;
    const pa = typeof winnerProbs.away === "number" ? winnerProbs.away : 0;
    const arr: Array<{ idx: 0 | 1 | 2; p: number }> = [
      { idx: 0, p: ph },
      { idx: 1, p: pd },
      { idx: 2, p: pa },
    ];
    arr.sort((a, b) => b.p - a.p);
    winnerSide = arr[0]?.idx ?? winnerSide;
  }

  const winnerLabel =
    winnerSide === 0 ? home_team :
    winnerSide === 1 ? "Empate" :
    winnerSide === 2 ? away_team : "—";

  const odds1x2 = odds?.winner ?? odds?.["1x2"] ?? {};
  const oddsOU25 = odds?.over_2_5 ?? (odds?.over_under?.["2.5"] ?? {});
  const oddsBTTS = odds?.btts ?? {};

  // Só consideramos odds quando a fonte é explicitamente "market"
  const show1x2 =
    odds_source === "market" &&
    isValidOdd(odds1x2?.home) &&
    isValidOdd(odds1x2?.draw) &&
    isValidOdd(odds1x2?.away);

  // Só mostra OU 2.5 se vier de mercado E for válido
  const showOU25 =
    odds_source === "market" &&
    isValidOdd(oddsOU25?.over) &&
    isValidOdd(oddsOU25?.under);

  const showBTTS =
    odds_source === "market" &&
    isValidOdd(oddsBTTS?.yes) && isValidOdd(oddsBTTS?.no);

  const showAnyOdds = show1x2 || showOU25 || showBTTS;

  const bestCS =
    predictions?.correct_score?.top3?.[0]?.score ??
    predictions?.correct_score?.best ??
    "—";

  const prob = (x?: { prob?: number; confidence?: number }) =>
    x?.confidence ?? x?.prob;

  // NOVO: arrays de marcadores prováveis casa/fora
  const homeProbScorers = probable_scorers?.home ?? [];
  const awayProbScorers = probable_scorers?.away ?? [];

  function displayScorerPct(p?: ProbableScorer) {
    if (!p) return "—";
    const pct = typeof p.probability_pct === "number" ? p.probability_pct : typeof p.probability === "number" ? p.probability * 100 : NaN;
    if (!isFinite(pct)) return "—";
    if (pct >= 99.9) return "≈100%";
    return `${Math.round(pct)}%`;
  }

  return (
    <div className="p-5 rounded-2xl border border-gray-800 bg-gray-950 hover:border-green-500 transition flex flex-col gap-4">
      {/* header */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-400">
          {league_name || league || "Liga"} {country ? `(${country})` : ""}
        </div>
        <div className="text-xs text-gray-500">
          {safeDate(date).toLocaleString("pt-PT", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>

      {/* teams */}
      <div className="flex items-center justify-center gap-3">
        <Image
          src={home_logo || FALLBACK_SVG}
          alt={home_team || "Home"}
          width={28}
          height={28}
          className="w-7 h-7"
          unoptimized
        />
        <div className="text-white font-semibold text-center">{home_team}</div>
        <div className="text-gray-500">vs</div>
        <div className="text-white font-semibold text-center">{away_team}</div>
        <Image
          src={away_logo || FALLBACK_SVG}
          alt={away_team || "Away"}
          width={28}
          height={28}
          className="w-7 h-7"
          unoptimized
        />
      </div>

      {/* correct score */}
      <div className="flex items-center justify-center gap-2">
        <span className="badge">Correct Score</span>
        <span className="text-sm text-white">{bestCS}</span>
      </div>

      {/* tips */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Winner</div>
          <div className="text-sm text-white">
            {winnerLabel}{" "}
            <span className="text-gray-400 ml-1">({toPct(prob(predictions?.winner))})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Double Chance</div>
          <div className="text-sm text-white">
            {dcLabel(predictions?.double_chance?.class)}{" "}
            <span className="text-gray-400 ml-1">({toPct(prob(predictions?.double_chance))})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Over 2.5</div>
          <div className="text-sm text-white">
            {predictions?.over_2_5?.class ? "Sim" : "Não"}{" "}
            <span className="text-gray-400 ml-1">
              ({toPct(
                predictions?.over_2_5?.class
                  ? prob(predictions?.over_2_5)
                  : 1 - (prob(predictions?.over_2_5) ?? 0)
              )})
            </span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Over 1.5</div>
          <div className="text-sm text-white">
            {predictions?.over_1_5?.class ? "Sim" : "Não"}{" "}
            <span className="text-gray-400 ml-1">
              ({toPct(
                predictions?.over_1_5?.class
                  ? prob(predictions?.over_1_5)
                  : 1 - (prob(predictions?.over_1_5) ?? 0)
              )})
            </span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3 col-span-2">
          <div className="text-xs text-gray-400">BTTS</div>
          <div className="text-sm text-white">
            {predictions?.btts?.class ? "Sim" : "Não"}{" "}
            <span className="text-gray-400 ml-1">
              ({toPct(
                predictions?.btts?.class
                  ? prob(predictions?.btts)
                  : 1 - (prob(predictions?.btts) ?? 0)
              )})
            </span>
          </div>
        </div>
      </div>

      {/* odds (mostra só os sub-blocos válidos) */}
      {showAnyOdds && (
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400 mb-2">
            Odds {odds_source === "market" ? "(mercado)" : "(modelo)"}
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            {show1x2 && (
              <div>
                <div className="text-gray-400 text-xs mb-1">1X2</div>
                <div className="text-white">
                  {oddFmt(odds1x2?.home)} / {oddFmt(odds1x2?.draw)} / {oddFmt(odds1x2?.away)}
                </div>
              </div>
            )}
            {showOU25 && (
              <div>
                <div className="text-gray-400 text-xs mb-1">O/U 2.5</div>
                <div className="text-white">
                  O {oddFmt(oddsOU25?.over)} · U {oddFmt(oddsOU25?.under)}
                </div>
              </div>
            )}
            {showBTTS && (
              <div>
                <div className="text-gray-400 text-xs mb-1">BTTS</div>
                <div className="text-white">
                  Sim {oddFmt(oddsBTTS?.yes)} · Não {oddFmt(oddsBTTS?.no)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* detalhes */}
      <details className="rounded-xl bg-gray-900 border border-gray-800 p-3">
        <summary className="cursor-pointer text-sm text-gray-200 select-none">
          Detalhes (Correct Score & Marcadores)
        </summary>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <div className="text-xs text-gray-400 mb-1">Top-3 Correct Score</div>
            <ul className="text-sm text-white space-y-1">
              {(predictions?.correct_score?.top3 ?? [])
                .slice(0, 3)
                .map((cs, idx) => (
                  <li key={idx} className="flex justify-between">
                    <span>{cs.score}</span>
                    <span className="text-gray-400">
                      {Math.round(prob01(cs.prob) * 1000) / 10}%
                    </span>
                  </li>
                ))}
              {!(predictions?.correct_score?.top3 ?? []).length && (
                <li className="text-gray-500">—</li>
              )}
            </ul>
          </div>

          {/* NOVO BLOCO: Marcadores Prováveis por equipa com fallback para top_scorers */}
          <div>
            <div className="text-xs text-gray-400 mb-1">Marcadores Prováveis</div>

            {homeProbScorers.length || awayProbScorers.length ? (
              <div className="grid grid-cols-2 gap-3 text-xs sm:text-sm">
                <div>
                  <div className="font-semibold text-gray-300 mb-1">{home_team}</div>
                  <ul className="space-y-1">
                    {homeProbScorers.slice(0, 3).map((p, idx) => (
                      <li
                        key={p.player_id ?? `${p.name}-${idx}`}
                        className="flex justify-between"
                      >
                        <span>{p.name}</span>
                        <span className="text-gray-400">{displayScorerPct(p)}</span>
                      </li>
                    ))}
                    {!homeProbScorers.length && (
                      <li className="text-gray-500">—</li>
                    )}
                  </ul>
                </div>
                <div>
                  <div className="font-semibold text-gray-300 mb-1">{away_team}</div>
                  <ul className="space-y-1">
                    {awayProbScorers.slice(0, 3).map((p, idx) => (
                      <li
                        key={p.player_id ?? `${p.name}-${idx}`}
                        className="flex justify-between"
                      >
                        <span>{p.name}</span>
                        <span className="text-gray-400">{displayScorerPct(p)}</span>
                      </li>
                    ))}
                    {!awayProbScorers.length && (
                      <li className="text-gray-500">—</li>
                    )}
                  </ul>
                </div>
              </div>
            ) : (
              // fallback: se por algum motivo não vier probable_scorers,
              // mostra ranking da liga como antes
              <ul className="text-sm text-white space-y-1">
                {(top_scorers ?? []).slice(0, 5).map((sc, idx) => (
                  <li key={idx} className="flex justify-between">
                    <span>
                      {sc.player} <span className="text-gray-400">({sc.team})</span>
                    </span>
                    <span className="text-gray-400">{sc.goals} golos</span>
                  </li>
                ))}
                {!(top_scorers ?? []).length && (
                  <li className="text-gray-500">—</li>
                )}
              </ul>
            )}
          </div>
        </div>
      </details>
    </div>
  );
}
