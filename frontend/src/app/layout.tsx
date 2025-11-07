// app/layout.tsx
import type { Metadata, Viewport } from "next";
import { Inter, Bebas_Neue } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import Footer from "@/components/footer";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const bebas = Bebas_Neue({
  variable: "--font-bebas",
  subsets: ["latin"],
  weight: "400",
  display: "swap",
});

// URL do site (podes definir NEXT_PUBLIC_SITE_URL no .env.local)
const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL || "https://football-prediction-murex.vercel.app";

// Versão para matar cache de assets públicos (/public)
const contentVersion = process.env.NEXT_PUBLIC_CONTENT_VERSION || "3";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "Previsão de Futebol | IA de Prognósticos",
  description:
    "Previsões de futebol com IA: dicas, probabilidades e níveis de confiança. Atualizado diariamente.",
  keywords: [
    "previsão de futebol",
    "palpites futebol",
    "IA futebol",
    "estatísticas de jogos",
    "tips futebol",
    "análise desportiva",
    "probabilidades",
  ],
  authors: [{ name: "Carlos Fernandes" }],
  creator: "Carlos Fernandes",
  openGraph: {
    title: "Previsão de Futebol | IA de Prognósticos",
    description:
      "Previsões de futebol com IA: dicas, probabilidades e níveis de confiança. Atualizado diariamente.",
    url: siteUrl,
    siteName: "Previsão de Futebol",
    images: [
      { url: `/file.png?v=${contentVersion}`, width: 1200, height: 630, alt: "Previsão de Futebol" },
    ],
    locale: "pt_PT",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Previsão de Futebol | IA de Prognósticos",
    description:
      "Previsões de futebol com IA: dicas, probabilidades e níveis de confiança. Atualizado diariamente.",
    images: [`/file.png?v=${contentVersion}`],
  },
  robots: { index: true, follow: true, nocache: false },
  manifest: `/manifest.json?v=${contentVersion}`,
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/favicon.ico",
  },
  category: "sports",
};

export const viewport: Viewport = {
  themeColor: "#0ea5e9",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt">
      <head>
        {/* Google Analytics */}
        <Script async src="https://www.googletagmanager.com/gtag/js?id=G-NNKXJQDTQ3" />
        <Script id="ga" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', 'G-NNKXJQDTQ3');
          `}
        </Script>
      </head>
      <body className={`${inter.variable} ${bebas.variable} antialiased bg-app text-white`}>
        {children}
        <Footer />
      </body>
    </html>
  );
}
