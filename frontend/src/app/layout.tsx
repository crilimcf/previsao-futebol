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

const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL || "https://football-prediction-murex.vercel.app";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "Football Prediction AI | Accurate Soccer Tips",
  description:
    "Get the most accurate football predictions powered by AI. Check match tips and confidence levels for your favorite teams. Updated daily.",
  keywords: [
    "football prediction",
    "soccer tips",
    "AI predictions",
    "match stats",
    "betting tips",
    "sports analytics",
    "football stats",
  ],
  authors: [{ name: "Fernando Casas", url: "https://github.com/fernandosc14" }],
  creator: "Fernando Casas",
  openGraph: {
    title: "Football Prediction AI | Accurate Soccer Tips",
    description:
      "Get the most accurate football predictions powered by AI. Check match tips and confidence levels for your favorite teams. Updated daily.",
    url: siteUrl,
    siteName: "Football Prediction AI",
    images: [{ url: "/file.png", width: 1200, height: 630, alt: "Football Prediction AI" }],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Football Prediction AI | Accurate Soccer Tips",
    description:
      "Get the most accurate football predictions powered by AI. Check match tips and confidence levels for your favorite teams. Updated daily.",
    images: ["/file.png"],
    creator: "@FernandoCasass_",
  },
  robots: { index: true, follow: true, nocache: false },
  manifest: "/manifest.json",
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
        {/* Google Analytics via next/script (melhor prática) */}
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
