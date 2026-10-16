import type { Metadata, Viewport } from "next";
import { Archivo, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { WalletProvider } from "@/components/WalletProvider";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

const archivo = Archivo({ subsets: ["latin"], variable: "--font-archivo", display: "swap", axes: ["wdth"] });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jbmono", display: "swap" });

export const metadata: Metadata = {
  title: "BackedBy: is this bridged token actually backed?",
  description: "BackedBy reads the tokens locked in a bridge's vault and the supply minted against them, at pinned blocks on both chains, from two RPCs each. Code decides BACKED or UNDER_BACKED. Built on GenLayer.",
};

export const viewport: Viewport = { themeColor: "#1b1e23" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${archivo.variable} ${mono.variable}`}>
      <body className="min-h-screen antialiased">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-plate focus:px-3 focus:py-2">Skip to content</a>
        <WalletProvider>
          <Header />
          <main id="main" className="mx-auto w-full max-w-6xl px-4 pb-24 sm:px-6">{children}</main>
          <Footer />
        </WalletProvider>
      </body>
    </html>
  );
}
