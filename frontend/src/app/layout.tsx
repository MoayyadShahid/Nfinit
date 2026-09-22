import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";
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
  description: "Describe a part, click a face to change it, print it tonight.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Light (porcelain) is the default. The landing and login pages are
            always light; the theme is only chosen inside the studio. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var r=document.documentElement,t="porcelain";try{var p=location.pathname;if(p!=="/"&&p!=="/login"){var s=localStorage.getItem("nfinit:theme");if(s==="midnight")t=s}}catch(e){}r.dataset.theme=t;r.classList.toggle("dark",t==="midnight");r.style.colorScheme=t==="midnight"?"dark":"light"})();`,
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
