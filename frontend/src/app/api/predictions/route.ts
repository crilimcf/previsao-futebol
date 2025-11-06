import { NextResponse } from "next/server";

export const runtime = "edge";
export const dynamic = "force-dynamic";
export const revalidate = 0;
export const fetchCache = "force-no-store";

export async function GET(request: Request) {
  const base =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "https://previsao-futebol.onrender.com";

  const { searchParams } = new URL(request.url);
  const date = searchParams.get("date");
  const league_id = searchParams.get("league_id");

  const url = new URL("/predictions", base);
  if (date) url.searchParams.set("date", date);
  if (league_id) url.searchParams.set("league_id", league_id);

  const r = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  const data = await r.json();
  return NextResponse.json(data, {
    headers: { "Cache-Control": "no-store" },
  });
}
