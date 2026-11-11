import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Market Intelligence MCP Terminal",
  description:
    "Institutional Market Intelligence & Portfolio Risk UI backed by AI Orchestrator and Zero-Trust MCP Gateway",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#080c14] text-slate-100 antialiased selection:bg-emerald-500/30 selection:text-emerald-200">
        {children}
      </body>
    </html>
  );
}
