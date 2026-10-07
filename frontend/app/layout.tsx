import "./globals.css";
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "VIN-Twin — диспетчер смены",
  description: "Прототип цифрового двойника. Демонстрационные данные.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
