"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Megaphone, Gem, ChevronLeft, ChevronRight } from "lucide-react";
import { useState, useEffect } from "react";

const links = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/players", label: "Players", icon: Users },
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
];

export default function Sidebar({ onOpenChange }: { onOpenChange?: (open: boolean) => void }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const toggle = (value: boolean) => {
    setOpen(value);
    onOpenChange?.(value);
  };

  // Close on route change
  useEffect(() => {
    toggle(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") toggle(false); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      {/* Backdrop for mobile */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={() => toggle(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-full bg-gray-900 border-r border-gray-800 flex flex-col z-40 transition-all duration-300 ease-in-out ${
          open ? "w-56 shadow-2xl" : "w-12"
        }`}
      >
        {/* Logo — visible when open */}
        <div className={`flex items-center border-b border-gray-800 overflow-hidden transition-all duration-300 ${open ? "gap-2.5 px-4 py-5" : "px-0 py-5 justify-center"}`}>
          {open ? (
            <>
              <Gem className="text-indigo-400 shrink-0" size={22} />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-white leading-tight">GemBlast</p>
                <p className="text-xs text-gray-500 leading-tight">LTV Studio</p>
              </div>
            </>
          ) : (
            <Gem className="text-indigo-400" size={20} />
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 px-1.5 py-4 space-y-1 overflow-hidden">
          {links.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                title={!open ? label : undefined}
                className={`flex items-center gap-3 px-2.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  open ? "" : "justify-center"
                } ${
                  active
                    ? "bg-indigo-600 text-white"
                    : "text-gray-400 hover:text-white hover:bg-gray-800"
                }`}
              >
                <Icon size={17} className="shrink-0" />
                {open && <span className="whitespace-nowrap">{label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Footer + toggle button */}
        <div className="border-t border-gray-800 px-1.5 py-3 flex items-center justify-between">
          {open && <p className="text-xs text-gray-600 px-2">v0.1.0</p>}
          <button
            onClick={() => toggle(!open)}
            className={`p-2 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors ${!open ? "mx-auto" : ""}`}
            aria-label={open ? "Collapse sidebar" : "Expand sidebar"}
          >
            {open ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
          </button>
        </div>
      </aside>
    </>
  );
}