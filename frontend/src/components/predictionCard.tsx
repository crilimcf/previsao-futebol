"use client";

import Image from "next/image";

type DCClass = 0 | 1 | 2;
const dcLabel = (dc: DCClass | undefined) => (dc === 0 ? "1X" : dc === 1 ? "12" : dc === 2 ? "X2" : "-");
const toPct = (v?: number | null) => (typeof v === "number" ? `${Math.round(v * 100)}%` : "—");
const oddFmt = (v?: number | null) => (typeof v === "number" ? v.toFixed(2) : "—");

const FALLBACK_SVG =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'><rect width='100%' height='100%' fill='%23222'/></svg>";

export interface PredictionCardProps {
  league?: string;
  league_name?: string;
  country?: string;
  date: string;
  home_team: string;
  away_team: string;
  home_logo?: string;
  away_logo?: string;
  predictions?: {
    winner?: { class: 0 | 1 | 2; prob: number };
    double_chance?: { class: DCClass; prob: number };
    over_2_5?: { class: 0 | 1; prob: number };
    over_1_5?: { class: 0 | 1; prob: number };
    btts?: { class: 0 | 1; prob: number };
    correct_score?: { best?: string; top3?: { score: string; prob: number }[] };
  };
  odds?: {
    ["1x2"]?: { home?: number; draw?: number; away?: number };
    over_under?: Record<string, { over?: number; under?: number }>;
    btts?: { yes?: number; no?: number };
  };
  top_scorers?: { player: string; team: string; goals: number }[];
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
}: PredictionCardProps) {
  const winnerClass = predictions?.winner?.class;
  const winnerLabel = winnerClass === 0 ? home_team : winnerClass === 1 ? "Empate" : winnerClass === 2 ? away_team : "—";

  return (
    <div className="p-5 rounded-2xl border border-gray-800 bg-gray-950 hover:border-green-500 transition flex flex-col gap-4">
      {/* header */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-400">
          {league_name || league} {country ? `(${country})` : ""}
        </div>
        <div className="text-xs text-gray-500">
          {new Date(date).toLocaleString("pt-PT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
        </div>
      </div>

      {/* teams */}
      <div className="flex items-center justify-center gap-3">
        <Image src={home_logo || FALLBACK_SVG} alt={home_team || "Home"} width={28} height={28} className="w-7 h-7" unoptimized />
        <div className="text-white font-semibold text-center">{home_team}</div>
        <div className="text-gray-500">vs</div>
        <div className="text-white font-semibold text-center">{away_team}</div>
        <Image src={away_logo || FALLBACK_SVG} alt={away_team || "Away"} width={28} height={28} className="w-7 h-7" unoptimized />
      </div>

      {/* tips */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Winner</div>
          <div className="text-sm text-white">
            {winnerLabel} <span className="text-gray-400 ml-1">({toPct(predictions?.winner?.prob)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Double Chance</div>
          <div className="text-sm text-white">
            {dcLabel(predictions?.double_chance?.class)} <span className="text-gray-400 ml-1">({toPct(predictions?.double_chance?.prob)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Over 2.5</div>
          <div className="text-sm text-white">
            {predictions?.over_2_5?.class ? "Sim" : "Não"} <span className="text-gray-400 ml-1">({toPct(predictions?.over_2_5?.prob)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Over 1.5</div>
          <div className="text-sm text-white">
            {predictions?.over_1_5?.class ? "Sim" : "Não"} <span className="text-gray-400 ml-1">({toPct(predictions?.over_1_5?.prob)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3 col-span-2">
          <div className="text-xs text-gray-400">BTTS</div>
          <div className="text-sm text-white">
            {predictions?.btts?.class ? "Sim" : "Não"} <span className="text-gray-400 ml-1">({toPct(predictions?.btts?.prob)})</span>
          </div>
        </div>
      </div>

      {/* odds */}
      {odds && (
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400 mb-2">Odds</div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <div>
              <div className="text-gray-400 text-xs mb-1">1X2</div>
              <div className="text-white">
                {oddFmt(odds?.["1x2"]?.home)} / {oddFmt(odds?.["1x2"]?.draw)} / {oddFmt(odds?.["1x2"]?.away)}
              </div>
            </div>
            <div>
              <div className="text-gray-400 text-xs mb-1">O/U 2.5</div>
              <div className="text-white">
                O {oddFmt(odds?.over_under?.["2.5"]?.over)} · U {oddFmt(odds?.over_under?.["2.5"]?.under)}
              </div>
            </div>
            <div>
              <div className="text-gray-400 text-xs mb-1">BTTS</div>
              <div className="text-white">
                Sim {oddFmt(odds?.btts?.yes)} · Não {oddFmt(odds?.btts?.no)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* detalhes */}
      <details className="rounded-xl bg-gray-900 border border-gray-800 p-3">
        <summary className="cursor-pointer text-sm text-gray-200 select-none">Detalhes (Correct Score & Marcadores)</summary>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <div className="text-xs text-gray-400 mb-1">Top-3 Correct Score</div>
            <ul className="text-sm text-white space-y-1">
              {(predictions?.correct_score?.top3 || []).slice(0, 3).map((cs, idx) => (
                <li key={idx} className="flex justify-between">
                  <span>{cs.score}</span>
                  <span className="text-gray-400">{Math.round((cs.prob ?? 0) * 1000) / 10}%</span>
                </li>
              ))}
              {(!predictions?.correct_score?.top3 || predictions?.correct_score?.top3?.length === 0) && (
                <li className="text-gray-500">—</li>
              )}
            </ul>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">Top Scorers (liga)</div>
            <ul className="text-sm text-white space-y-1">
              {(top_scorers || []).slice(0, 5).map((sc, idx) => (
                <li key={idx} className="flex justify-between">
                  <span>
                    {sc.player} <span className="text-gray-400">({sc.team})</span>
                  </span>
                  <span className="text-gray-400">{sc.goals} golos</span>
                </li>
              ))}
              {(!top_scorers || top_scorers.length === 0) && <li className="text-gray-500">—</li>}
            </ul>
          </div>
        </div>
      </details>
    </div>
  );
}
