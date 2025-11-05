import HomeClient from "./homeClient";

export const dynamic = "force-dynamic"; // evita SSG quando há useSearchParams

export default function Page() {
  return <HomeClient />;
}
