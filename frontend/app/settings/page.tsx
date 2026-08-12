"use client";

import { useEffect, useState } from "react";
import ProviderSetup from "@/components/ProviderSetup";
import { api, type SettingsOut } from "@/lib/api";

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsOut | null>(null);
  const [companies, setCompanies] = useState("");
  const [ashbyBoards, setAshbyBoards] = useState("");
  const [capabilities, setCapabilities] = useState<{
    pdf: boolean;
    pdf_detail: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.settings(),
      api.capabilities(),
      api.greenhouseCompanies(),
      api.ashbyBoards(),
    ])
      .then(([s, caps, cos, boards]) => {
        setSettings(s);
        setCapabilities(caps);
        setCompanies(cos.join("\n"));
        setAshbyBoards(boards.join("\n"));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Load failed."));
  }, []);

  if (error && !settings) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <p className="card border-gold/60 bg-gold/10 p-4 text-sm">{error}</p>
      </div>
    );
  }
  if (!settings) {
    return <p className="px-6 py-8 text-sm text-muted">Loading…</p>;
  }

  async function save(patch: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      setSettings(await api.saveSettings(patch));
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted">
          Stored in the local SQLite database. Keys never leave this machine and are never
          returned by the API once saved.
        </p>
      </header>

      {error && (
        <p className="card mb-4 border-gold/60 bg-gold/10 p-4 text-sm">{error}</p>
      )}
      {saved && (
        <p className="card mb-4 border-brand/30 bg-brand-tint p-4 text-sm">Saved.</p>
      )}

      {/* Same component the search and resume pages use, so there is exactly one
          implementation of "connect a model" to keep correct. */}
      <div className="mb-4">
        <ProviderSetup settings={settings} onSaved={setSettings} />
      </div>

      {/* ---------------- greenhouse ---------------- */}
      <section className="card mb-4 p-5">
        <h2 className="font-bold">Greenhouse companies</h2>
        <p className="mt-1 text-sm text-muted">
          Greenhouse serves one board per company — there is no global search — so this
          list defines what gets searched. One slug per line, taken from{" "}
          <code className="rounded bg-page px-1">
            boards.greenhouse.io/<b>slug</b>
          </code>
          .
        </p>
        <textarea
          className="field mt-3 min-h-[160px] resize-y font-mono text-xs"
          value={companies}
          onChange={(e) => setCompanies(e.target.value)}
        />
        <button
          className="btn-primary mt-3"
          disabled={busy}
          onClick={() =>
            save({
              greenhouse_companies: companies
                .split("\n")
                .map((c) => c.trim())
                .filter(Boolean),
            })
          }
        >
          Save companies
        </button>
      </section>

      {/* ---------------- ashby ---------------- */}
      <section className="card mb-4 p-5">
        <h2 className="font-bold">Ashby internship boards</h2>
        <p className="mt-1 text-sm text-muted">
          One employer board per line, taken from{" "}
          <code className="rounded bg-page px-1">
            jobs.ashbyhq.com/<b>board</b>
          </code>
          . Only postings explicitly identified as internships or co-ops are shown.
        </p>
        <textarea
          className="field mt-3 min-h-[140px] resize-y font-mono text-xs"
          value={ashbyBoards}
          onChange={(event) => setAshbyBoards(event.target.value)}
        />
        <button
          className="btn-primary mt-3"
          disabled={busy}
          onClick={() =>
            save({
              ashby_boards: ashbyBoards
                .split("\n")
                .map((board) => board.trim())
                .filter(Boolean),
            })
          }
        >
          Save Ashby boards
        </button>
      </section>

      {/* ---------------- capabilities ---------------- */}
      <section className="card p-5">
        <h2 className="font-bold">This install</h2>
        <dl className="mt-3 grid gap-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-muted">DOCX rendering</dt>
            <dd className="font-semibold text-brand">Available</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted">PDF rendering</dt>
            <dd className={capabilities?.pdf ? "font-semibold text-brand" : "text-muted"}>
              {capabilities?.pdf ? "Available · single page" : "Unavailable"}
            </dd>
          </div>
        </dl>
        {capabilities && !capabilities.pdf && (
          <p className="mt-3 text-xs leading-relaxed text-muted">
            {capabilities.pdf_detail}
          </p>
        )}
      </section>
    </div>
  );
}
