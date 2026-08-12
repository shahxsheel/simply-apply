# SimplyApply

**Free, open-source, self-hosted internship tracking + truthful resume tailoring.**

Browse internship-only employer boards, click Apply on one, and get an ATS-safe resume regenerated from
your structured data and tailored to that posting — with a mechanical guarantee that
nothing was invented.

```
internship board → pick a posting → select evidence → verify facts → Jake resume → ATS review → apply
```

Your resume, your API keys, and your application history never leave your machine.

---

## Why this exists

Most resume tailoring tools either paywall the useful part or quietly let a language model
embellish your experience. SimplyApply does neither:

- **The Simplify Job Tracker surfaces Summer 2027 internships first.** It reads the
  public SimplifyJobs/Pitt CSC repository, keeps only direct employer links, and groups
  openings by category with newest roles first.
- **Greenhouse and Ashby have dedicated internship-only pages.** Their employer boards
  are filtered before display; full-time, new-grad, and misleading references such as
  "excluding internships" are rejected.
- **Quick Apply accepts a posting from almost any job site.** Paste its URL and full
  description to tailor a resume for internships or full-time roles without waiting for
  that employer to appear on a supported board.
- **Tailoring is the product, and it's free.** No autofill engine, no accounts, no SaaS.
- **The no-fabrication rule is enforced in code, not in a prompt.** See below.
- **Your resume is structured data, not a file.** Every output is regenerated from it; no
  PDF is ever edited in place.

---

## The no-fabrication guardrail

This is the part that matters, so it's worth being precise about how it works.

Telling a model "don't invent experience" is a request, not a control. So after every
tailoring run, `backend/app/services/guardrail.py` validates the output against your base
resume:

| Checked | Rule |
|---|---|
| Employers, job titles, schools, degrees | Must match a value in your base resume |
| Every date | Must match a date in your base resume — no stretching to close a gap |
| Every number, percentage, and metric | Must appear in your base resume — 15% cannot become 40% |
| Every skill and keyword | Must appear *somewhere* in your base resume |

Reordering, rephrasing, dropping irrelevant roles or bullets, and rewriting your summary
are all free — that's what tailoring is. The model ranks evidence for the job, and a
deterministic one-page budget keeps at most three roles, three bullets per role, and two
projects. Surfacing a skill that's buried inside a bullet is allowed. Adding one because
the job description asked for it is not.

**If the check fails, it retries once with the specific violations fed back. If it fails
again, you get your original resume plus an explicit warning** — never silently
fabricated content. The worst case is a generic application, not a rescinded offer.

It's a whitelist over your resume rather than a blocklist of suspicious phrases, so its
failure mode is a false positive (mildly annoying) instead of a false negative (career
damage).

---

## Quick start

### Docker (recommended)

```bash
git clone <your-fork-url> simplyapply
cd simplyapply
cp .env.example .env      # optional — you can set everything in the UI instead
docker compose up
```

Open <http://localhost:3000>.

The Compose path is verified locally: the frontend proxies `/api` to the backend service,
and the Settings API is reachable through <http://localhost:3000>.

### Native (verified)

Requires Python 3.12+ and Node 20+.

```bash
# backend
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/uvicorn app.main:app --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The frontend proxies `/api` to the backend, so the browser
only ever talks to one origin.

---

## Configuring an AI provider

Tailoring and resume parsing need a model. Open **Settings** and pick one:

| Provider | Notes |
|---|---|
| **Anthropic** | Recommended. Defaults to `claude-opus-4-8`. Strongest at structured extraction and at respecting the no-fabrication rules. |
| **OpenAI-compatible** | Works with OpenAI, Groq, Together, OpenRouter, or a local LM Studio server — just change the base URL. |
| **Ollama** | Free, fully local, nothing leaves your machine. Smaller models make more parsing mistakes, so review the confirm screen carefully. |

Keys are stored in the local SQLite database and are **write-only over the API** — once
saved, no endpoint will hand the value back out.

---

## How it works

```
┌──────────────────────────────────────────────────────┐
│  docker compose up  (your machine)                    │
│                                                       │
│   Next.js  ──/api rewrite──▶  FastAPI                 │
│                                 ├── internship boards │
│                                 ├── manual job import │
│                                 ├── tailor()          │
│                                 ├── guardrail  ◀── the important bit
│                                 └── docx + PDF render │
│                                        │              │
│                                   SQLite (1 file)     │
└──────────────────────────────────────────────────────┘
          │                              │
 employer ATS APIs              your LLM provider
```

**Resume format.** Stored as [JSON Resume](https://jsonresume.org) — a community
standard, so your data stays portable to other tooling.

**Outputs.** Every apply uses the compact, single-column
[Jake's Resume](https://github.com/jakegut/resume)-inspired visual system. The **PDF** is
always exactly one page, rendered with reportlab (pure Python, no system dependency) and
scaled to fit rather than truncated when content runs long. The **DOCX** is the safest
choice for ATS uploads: it has no tables and preserves a simple document reading order.
If PDF rendering ever fails, the apply degrades to DOCX-only for that one job with a
clear message rather than erroring.

After the exact final resume is selected, the configured model performs a separate ATS
review against the job description. The result screen shows its match level, supported
strengths, suggested wording or evidence improvements, and potential keyword gaps. A
keyword gap is never permission to claim experience the base resume does not support.

**Simplify Job Tracker.** The first sidebar item loads active listings from
[SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships).
The backend parses the repository's generated HTML tables, handles continuation rows,
and retains only direct employer application URLs. When Tailor Resume is selected, a
provider-agnostic scraper fetches the employer page, locates its Job Description section
(with JobPosting structured data as a fallback), caches it as a normal job, and sends it
through the same truthful tailoring and ATS-review pipeline as board listings. Results
are cached for 15 minutes, with stale-cache fallback when GitHub has a transient outage.

**Quick Apply.** Paste an HTTP(S) posting URL, title, company, location, and complete
description from LinkedIn, Indeed, an employer careers page, or another job site. The
posting is stored locally as a normal job and enters the same background tailoring,
fact-verification, one-page rendering, ATS-review, and application-tracking workflow.
SimplyApply does not sign into the job site or submit the final application for you.

---

## Project status

The full internship board → tailor → render → apply loop
works end to end.

**Verified:** backend and frontend tests cover the guardrail (including employer/title pairing,
dates, inflated metrics, and phantom skills), selective one-page tailoring, the ATS
review, Simplify tracker parsing and filtering, retry and fallback control flow, DOCX
text-extraction ordering, single-page PDF rendering (page count read back from the
generated file, including an oversized resume shrunk to fit), generic job imports, and
the complete apply loop through the real app.

**Verified:** `docker compose up`, including frontend-to-backend API proxying.

The generic multi-source search engine and aggregator connector were intentionally
removed. Discovery is organized as dedicated internship-only boards.

---

## Running the tests

```bash
cd backend
.venv/bin/python -m pytest        # Windows: .venv\Scripts\python -m pytest
```

If you touch `guardrail.py`, run these first. They're the difference between a tool that
tailors resumes and one that fabricates them.

---

## License

[AGPL-3.0](LICENSE). Chosen deliberately: you can run, modify, and share this freely, but
if you host a modified version as a service, you have to share your changes too.
