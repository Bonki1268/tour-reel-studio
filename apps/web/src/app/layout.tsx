import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Tour Reel Studio", description: "觀光宣傳短片產生器" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant-TW">
      <body>{children}</body>
    </html>
  );
}
