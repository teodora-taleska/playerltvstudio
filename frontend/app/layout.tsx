import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "GemBlast LTV Studio",
  description: "Player Lifetime Value & Campaign ROI Analytics",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-950 text-gray-100 min-h-screen antialiased`}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 p-8 pt-16 lg:pt-8 overflow-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}
