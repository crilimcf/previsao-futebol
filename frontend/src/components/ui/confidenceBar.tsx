"use client";

import React from "react";
import { cn } from "@/lib/utils";

type Props = {
  /** 0..1; aceita também objetos com `prob` ou `confidence` */
  value: number | { prob?: number; confidence?: number } | undefined | null;
  label?: string;
  className?: string;
};

const pick = (v: Props["value"]) => {
  if (typeof v === "number") return v;
  if (!v) return 0;
  const n = (v.prob ?? v.confidence ?? 0) as number;
  return Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0;
};

const color = (p: number) => {
  if (p >= 0.85) return "from-emerald-400 to-emerald-500";
  if (p >= 0.7) return "from-lime-400 to-green-500";
  if (p >= 0.55) return "from-amber-400 to-orange-500";
  return "from-rose-400 to-red-500";
};

export function ConfidenceBar({ value, label, className }: Props) {
  const v = pick(value);
  const pct = Math.round(v * 100);
  return (
    <div className={cn("w-full", className)}>
      {label && (
        <div className="mb-1 flex items-center justify-between text-xs text-gray-400">
          <span>{label}</span>
          <span className="tabular-nums">{pct}%</span>
        </div>
      )}
      <div className="h-2 w-full rounded-full bg-gray-800/80 overflow-hidden">
        <div
          className={cn("h-full bg-gradient-to-r", color(v))}
          style={{ width: `${pct}%` }}
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  );
}
