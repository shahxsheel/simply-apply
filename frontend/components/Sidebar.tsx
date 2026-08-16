"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "./ThemeToggle";

const NAV = [
  { href: "/simplify", label: "Simplify Job Tracker", icon: TrackerIcon, featured: true },
  { href: "/ashby", label: "Ashby Internships", icon: BriefcaseIcon, featured: true },
  { href: "/greenhouse", label: "Greenhouse Internships", icon: GreenhouseIcon, featured: true },
  { href: "/quick-apply", label: "Quick Apply", icon: QuickApplyIcon, featured: true },
  { href: "/resume", label: "Resume", icon: DocIcon, featured: false },
  { href: "/applications", label: "Applications", icon: ListIcon, featured: false },
  { href: "/metrics", label: "Metrics", icon: MetricsIcon, featured: false },
  { href: "/settings", label: "Settings", icon: GearIcon, featured: false },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-ink/10 bg-surface/60 px-4 py-3 backdrop-blur-2xl md:hidden">
        <div className="flex items-center justify-between gap-4">
          <Link
            href="/greenhouse"
            className="flex items-center gap-2"
            aria-label="SimplyApply home"
          >
            <BrandMark />
            <span className="font-display text-lg tracking-[-0.025em]">SimplyApply</span>
          </Link>
          <div className="w-28 shrink-0">
            <ThemeToggle />
          </div>
        </div>
        <nav
          className="-mx-1 mt-3 flex gap-1 overflow-x-auto px-1 pb-0.5"
          aria-label="Primary navigation"
        >
          {NAV.map(({ href, label }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium ${
                  active
                    ? "bg-solid text-on-solid"
                    : "border border-ink/10 bg-surface/60 text-muted"
                }`}
              >
                {label.replace(" Internships", "").replace(" Job Tracker", "")}
              </Link>
            );
          })}
        </nav>
      </header>

      <aside className="hidden w-64 shrink-0 border-r border-ink/10 bg-surface/55 px-4 py-6 backdrop-blur-2xl md:sticky md:top-0 md:flex md:h-screen md:flex-col">
        <div className="px-2 pb-6">
          <Link
            href="/greenhouse"
            className="group flex items-center gap-3"
            aria-label="SimplyApply home"
          >
            <BrandMark />
            <span className="min-w-0">
              <span className="block truncate font-display text-xl leading-none tracking-[-0.025em]">
                SimplyApply
              </span>
              <span className="mt-1 block text-[9px] font-semibold uppercase tracking-[0.18em] text-muted">
                Career studio
              </span>
            </span>
          </Link>
          <div className="mt-4">
            <ThemeToggle />
          </div>
        </div>

        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon, featured }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-solid text-on-solid"
                    : "text-muted hover:bg-surface/70 hover:text-ink"
                }`}
                aria-current={active ? "page" : undefined}
              >
                <Icon />
                <span className="min-w-0 flex-1">{label}</span>
                {featured && (
                  <span
                    className={`rounded-full border px-1.5 py-0.5 text-[8px] font-semibold uppercase tracking-[0.12em] ${
                      active
                        ? "border-on-solid/25 text-on-solid/70"
                        : "border-ink/15 text-muted"
                    }`}
                  >
                    Live
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto">
          <div className="overflow-hidden rounded-2xl border border-ink/10 bg-surface/60 backdrop-blur-2xl">
            <div className="h-1.5 bg-[var(--dawn-arc)]" />
            <p className="p-4 text-xs leading-relaxed text-muted">
              <span className="mb-1 block font-semibold text-ink">
                Private by design.
              </span>
              Your resume and API keys stay on this machine.
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}

function BrandMark() {
  return (
    <span
      className="relative grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-xl bg-[var(--dawn-arc)] ring-1 ring-ink/10 transition-transform group-hover:rotate-3"
      aria-hidden="true"
    >
      <span className="font-display text-2xl leading-none text-white drop-shadow-sm">S</span>
    </span>
  );
}

/* Inline SVGs rather than an icon package — four icons isn't worth a dependency. */
const strokeProps = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function TrackerIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
      <path d="m3 6 5-3 5 4 7-5" />
    </svg>
  );
}

function QuickApplyIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <path d="M12 3v18M3 12h18" />
      <path d="m17 7 4 5-4 5M7 17l-4-5 4-5" />
    </svg>
  );
}

function BriefcaseIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2" />
    </svg>
  );
}

function GreenhouseIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <path d="M4 21V9l8-6 8 6v12M8 21v-7h8v7M2 21h20" />
      <path d="M7 9h10" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  );
}

function MetricsIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
      <path d="m3 6 5-3 5 4 7-5" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.14.6.66 1.03 1.28 1.05H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
