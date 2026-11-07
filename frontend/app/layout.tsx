import type { Metadata } from "next";
import { Courier_Prime, IBM_Plex_Sans, Newsreader } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

const newsreader = Newsreader({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-newsreader",
});

const plex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-plex",
});

const courier = Courier_Prime({
  subsets: ["latin"],
  weight: ["400", "700"],
  display: "swap",
  variable: "--font-courier",
});

export const metadata: Metadata = {
  title: "Open work",
  description: "The case record is read-only. Sign-off happens in Switch.",
};

const column = "mx-auto w-full max-w-column px-margin";

export default function RootLayout({ children }: { children: ReactNode }) {
  const roomLabel = process.env.NEXT_PUBLIC_ROOM_LABEL ?? "ARCHIVE";
  const switchUrl = process.env.NEXT_PUBLIC_SWITCH_ROOM_URL;

  return (
    <html
      lang="en"
      className={`${newsreader.variable} ${plex.variable} ${courier.variable}`}
    >
      <body className="flex min-h-screen flex-col bg-canvas font-sans text-ink">
        <header className="h-header shrink-0 border-b border-hairline">
          <div className={`${column} flex h-full items-center justify-between gap-6`}>
            <p className="flex min-w-0 items-baseline gap-3">
              <span className="font-sans text-section font-semibold text-ink">
                DEVTEAM
              </span>
              <span className="text-graphite" aria-hidden="true">
                /
              </span>
              <span className="truncate font-sans text-section font-medium uppercase text-graphite">
                {roomLabel}
              </span>
            </p>
            {switchUrl ? (
              <a
                href={switchUrl}
                className="shrink-0 font-sans text-section font-semibold text-pine underline decoration-pine decoration-1 underline-offset-4"
              >
                SWITCH ↗
              </a>
            ) : null}
          </div>
        </header>
        <main className={`${column} flex-1`}>{children}</main>
        <footer className="shrink-0 border-t border-hairline">
          <div
            className={`${column} flex flex-wrap items-baseline justify-between gap-x-8 gap-y-3 py-6`}
          >
            <p className="max-w-xl font-sans text-meta text-graphite">
              The case record is immutable and read-only. Sign-off happens in
              Switch.
            </p>
            <nav className="flex gap-6" aria-label="Record">
              <a
                href="/"
                className="font-sans text-section font-semibold text-ink underline decoration-ink decoration-1 underline-offset-4"
              >
                INCIDENT LOG
              </a>
              <a
                href="#timeline"
                className="font-sans text-section font-semibold text-ink underline decoration-ink decoration-1 underline-offset-4"
              >
                AUDIT TRAIL
              </a>
            </nav>
          </div>
        </footer>
      </body>
    </html>
  );
}
