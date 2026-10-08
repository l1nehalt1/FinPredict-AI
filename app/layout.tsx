import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinPredict AI — финансовый кабинет",
  description: "Приватный финансовый кабинет с аналитикой и прогнозом будущих расходов.",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body className="antialiased">{children}</body>
    </html>
  );
}
