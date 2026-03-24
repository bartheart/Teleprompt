import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Teleprompt",
  description: "Realtime speech assistant with live transcript and speaking cues.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">{children}</body>
    </html>
  );
}
