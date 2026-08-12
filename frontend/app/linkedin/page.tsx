"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type LinkedInJobImport } from "@/lib/api";

const EMPTY_FORM: LinkedInJobImport = {
  url: "",
  title: "",
  company: "",
  location: "",
  remote: false,
  description: "",
};

export default function LinkedInImportPage() {
  const [form, setForm] = useState<LinkedInJobImport>(EMPTY_FORM);
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applicationId, setApplicationId] = useState<number | null>(null);

  useEffect(() => {
    api
      .baseResume()
      .then((resume) => setHasResume(Boolean(resume)))
      .catch(() => setHasResume(false));
  }, []);

  function update<K extends keyof LinkedInJobImport>(
    key: K,
    value: LinkedInJobImport[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setApplicationId(null);
    try {
      const job = await api.importLinkedInJob(form);
      const application = await api.startTailoring({
        job_id: job.id,
        source: job.source,
        title: job.title,
        company: job.company,
        location: job.location,
        remote: job.remote,
        apply_url: job.apply_url,
      });
      setApplicationId(application.id);
      setForm(EMPTY_FORM);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not import this posting.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Import a LinkedIn internship</h1>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          Copy a posting you found on LinkedIn. SimplyApply saves the text locally and
          uses the normal one-page resume and ATS-review pipeline.
        </p>
      </header>

      <div className="card mb-5 border-brand/30 bg-brand-tint p-4 text-sm leading-relaxed">
        SimplyApply does not sign into, crawl, or automatically read LinkedIn. Paste the
        complete job description here so tailoring has every qualification and
        responsibility available.
      </div>

      {hasResume === false && (
        <div className="card mb-5 flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-sm">
            Save a base resume before importing a posting for tailoring.
          </p>
          <Link href="/resume" className="btn-primary">
            Add resume
          </Link>
        </div>
      )}

      {error && (
        <p className="card mb-5 border-gold/60 bg-gold/10 p-4 text-sm">{error}</p>
      )}
      {applicationId !== null && (
        <div className="card mb-5 flex flex-wrap items-center justify-between gap-3 border-brand/30 p-4">
          <p className="text-sm font-semibold">
            Added to Applications. Resume tailoring is running in the background.
          </p>
          <Link href="/applications" className="btn-primary">
            Track progress →
          </Link>
        </div>
      )}

      <form onSubmit={submit} className="card p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-semibold sm:col-span-2">
            LinkedIn job URL
            <input
              className="field mt-1.5 font-normal"
              type="url"
              required
              placeholder="https://www.linkedin.com/jobs/view/…"
              value={form.url}
              onChange={(event) => update("url", event.target.value)}
            />
          </label>
          <label className="text-sm font-semibold">
            Internship title
            <input
              className="field mt-1.5 font-normal"
              required
              placeholder="Software Engineering Intern"
              value={form.title}
              onChange={(event) => update("title", event.target.value)}
            />
          </label>
          <label className="text-sm font-semibold">
            Company
            <input
              className="field mt-1.5 font-normal"
              required
              placeholder="Company name"
              value={form.company}
              onChange={(event) => update("company", event.target.value)}
            />
          </label>
          <label className="text-sm font-semibold sm:col-span-2">
            Location
            <input
              className="field mt-1.5 font-normal"
              placeholder="Seattle, WA"
              value={form.location}
              onChange={(event) => update("location", event.target.value)}
            />
          </label>
          <label className="flex w-fit cursor-pointer items-center gap-2 text-sm text-muted sm:col-span-2">
            <input
              type="checkbox"
              checked={form.remote}
              onChange={(event) => update("remote", event.target.checked)}
              className="h-4 w-4 accent-ink"
            />
            Remote internship
          </label>
          <label className="text-sm font-semibold sm:col-span-2">
            Complete job description
            <textarea
              className="field mt-1.5 min-h-[300px] resize-y font-normal leading-relaxed"
              required
              minLength={40}
              placeholder="Paste About the role, responsibilities, qualifications, and requirements…"
              value={form.description}
              onChange={(event) => update("description", event.target.value)}
            />
          </label>
        </div>

        <button
          type="submit"
          className="btn-primary mt-5"
          disabled={busy || hasResume !== true}
        >
          {busy ? "Adding to Applications…" : "Import & tailor resume"}
        </button>
      </form>
    </div>
  );
}
