import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "nfinit — Make anything",
  description: "Describe, refine, and export production-ready 3D parts.",
};

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
            __html: `(function(){try{var t=localStorage.getItem("nfinit:theme");if(t!=="midnight"&&t!=="porcelain"){t=matchMedia("(prefers-color-scheme: light)").matches?"porcelain":"midnight"}var r=document.documentElement;r.dataset.theme=t;r.classList.toggle("dark",t==="midnight");r.style.colorScheme=t==="midnight"?"dark":"light"}catch(e){document.documentElement.dataset.theme="midnight";document.documentElement.classList.add("dark")}})();`,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
