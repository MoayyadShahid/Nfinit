import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";
import { DEMO_ONLY } from "@/lib/site";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Display serif for what people say (spec §3). Never below 24px.
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz", "SOFT", "WONK"],
});

export const metadata: Metadata = {
  title: "nfinit",
  description: "An open-source visual CAD workspace for Claude Code and Codex. Bring references, edit locally, and keep your files.",
};

// Porcelain is the default. Midnight is restored from localStorage on every
// page so landing, login, and studio share one theme.
const SAVED_THEME_SCRIPT = `(function(){var r=document.documentElement,t="porcelain";try{var s=localStorage.getItem("nfinit:theme");if(s==="midnight")t=s}catch(e){}r.dataset.theme=t;r.classList.toggle("dark",t==="midnight");r.style.colorScheme=t==="midnight"?"dark":"light"})();`;

// The public website has no toggle: it follows the visitor's local clock,
// porcelain from 07:00 to 18:59 and midnight otherwise. Nothing is stored or
// sent; the hour is read in the browser.
const CLOCK_THEME_SCRIPT = `(function(){var r=document.documentElement,h=new Date().getHours(),t=h>=7&&h<19?"porcelain":"midnight";r.dataset.theme=t;r.classList.toggle("dark",t==="midnight");r.style.colorScheme=t==="midnight"?"dark":"light"})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: DEMO_ONLY ? CLOCK_THEME_SCRIPT : SAVED_THEME_SCRIPT,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
