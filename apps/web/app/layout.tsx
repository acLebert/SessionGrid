import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SessionGrid — Turn demos into arrangement maps",
  description:
    "Upload a song, isolate stems, analyze tempo and structure, and get back a rehearsal-ready guide.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-zinc-950 text-zinc-100 antialiased">
        {children}
      </body>
    </html>
  );
}
