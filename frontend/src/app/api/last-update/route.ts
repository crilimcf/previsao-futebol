import { NextResponse } from "next/server";

export const runtime = "edge";
export const dynamic = "force-dynamic";

export async function GET() {
  const base =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "https://previsao-futebol.onrender.com";

  const r = await fetch(`${base}/meta/last-update`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  const data = await r.json();
  return NextResponse.json(data, {
    headers: { "Cache-Control": "no-store" },
  });
}
