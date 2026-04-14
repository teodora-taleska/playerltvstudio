"use client";

import { useState } from "react";
import Sidebar from "@/components/Sidebar";

export default function LayoutShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex min-h-screen">
      <Sidebar onOpenChange={setSidebarOpen} />
      <main
        className={`flex-1 p-6 md:p-8 overflow-x-hidden transition-all duration-300 ease-in-out ${
          sidebarOpen ? "ml-56" : "ml-12"
        }`}
      >
        {children}
      </main>
    </div>
  );
}