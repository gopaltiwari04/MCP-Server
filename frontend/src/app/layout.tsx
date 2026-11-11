import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "QuantMCP // Market Intelligence Terminal",
  description:
    "Institutional Market Intelligence & Portfolio Risk Workbench powered by Zero-Trust MCP Gateway",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable} dark`}>
      <body className="min-h-screen bg-[#08090c] text-[#e6e8ee] font-sans antialiased selection:bg-amber-500/25 selection:text-amber-200">
        {children}
      </body>
    </html>
  );
}
