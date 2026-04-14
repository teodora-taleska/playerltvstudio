"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Megaphone, Gem, Menu, X } from "lucide-react";
import { useState, useEffect } from "react";

const links = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/players", label: "Players", icon: Users },
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close on route change (mobile nav tap)
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  // Prevent body scroll when sidebar is open on mobile
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  return (
    <>
      {/* Mobile toggle button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="fixed top-4 left-4 z-50 p-2 rounded-lg bg-gray-900 border border-gray-800 text-gray-400 hover:text-white transition-colors lg:hidden"
        aria-label="Toggle navigation"
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Desktop collapse button — inside sidebar when open, floating when closed */}
      <button
        onClick={() => setOpen((o) => !o)}
        className={`hidden lg:flex fixed top-4 z-50 p-1.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-400 hover:text-white transition-all duration-300 ${
          open ? "left-[13.5rem]" : "left-4"
        }`}
        aria-label="Toggle navigation"
      >
        {open ? <X size={16} /> : <Menu size={16} />}
      </button>

      {/* Backdrop — mobile only */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={`fixed top-0 left-0 h-full w-56 bg-gray-900 border-r border-gray-800 flex flex-col z-40 transition-transform duration-300 ease-in-out ${
          open ? "translate-x-0 shadow-2xl" : "-translate-x-full"
        }`}
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-5 py-5 border-b border-gray-800">
          <Gem className="text-indigo-400" size={22} />
          <div>
            <p className="text-sm font-semibold text-white leading-tight">GemBlast</p>
            <p className="text-xs text-gray-500 leading-tight">LTV Studio</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {links.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? "bg-indigo-600 text-white"
                    : "text-gray-400 hover:text-white hover:bg-gray-800"
                }`}
              >
                <Icon size={17} />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="px-5 py-4 border-t border-gray-800">
          <p className="text-xs text-gray-600">v0.1.0</p>
        </div>
      </aside>
    </>
  );
}
