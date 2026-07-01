import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AutoZS",
  description: "Home Depot to eBay automation dashboard"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
