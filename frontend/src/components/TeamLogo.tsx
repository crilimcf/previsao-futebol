"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";
import * as React from "react";

type Props = {
  src?: string | null;
  alt: string;
  size?: number;        // px
  className?: string;
  rounded?: boolean;
};

function initials(name: string) {
  const parts = name.split(" ").filter(Boolean);
  const a = (parts[0]?.[0] ?? "").toUpperCase();
  const b = (parts[1]?.[0] ?? "").toUpperCase();
  return (a + b || a || "⚽");
}

export default function TeamLogo({
  src,
  alt,
  size = 28,
  className,
  rounded = true,
}: Props) {
  const [error, setError] = React.useState(false);
  const showFallback = !src || error;

  return (
    <span
      className={cn(
        "inline-flex items-center justify-center bg-gray-800/70 ring-1 ring-gray-700",
        rounded ? "rounded-full" : "rounded-md",
        className
      )}
      style={{ width: size, height: size }}
      aria-label={alt}
      title={alt}
    >
      {showFallback ? (
        <span
          className="text-[10px] leading-none text-gray-200 font-semibold"
          style={{ transform: "translateY(1px)" }}
        >
          {initials(alt)}
        </span>
      ) : (
        <Image
          src={src}
          alt={alt}
          width={size}
          height={size}
          className={cn(rounded ? "rounded-full" : "rounded-md", "object-contain")}
          onError={() => setError(true)}
          // Se ativar images.unoptimized: true no next.config, remove o priority
          priority={false}
        />
      )}
    </span>
  );
}
