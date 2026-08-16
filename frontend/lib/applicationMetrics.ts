import type { ApplicationOut } from "./api";

export const METRIC_STATUSES = [
  "prepared",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
] as const;

export type MetricStatus = (typeof METRIC_STATUSES)[number];
export type MetricsRange = 7 | 30 | 90;

export type DailyApplicationMetric = {
  key: string;
  date: Date;
  total: number;
  statuses: Record<MetricStatus, number>;
};

export type ApplicationMetrics = {
  days: DailyApplicationMetric[];
  total: number;
  dailyAverage: number;
  statuses: Record<MetricStatus, number>;
  busiestDay: DailyApplicationMetric | null;
  activePipeline: number;
  decidedOutcomes: number;
  rejectionRate: number | null;
};

function emptyStatusCounts(): Record<MetricStatus, number> {
  return {
    prepared: 0,
    applied: 0,
    interviewing: 0,
    offer: 0,
    rejected: 0,
    withdrawn: 0,
  };
}

function localDayKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function applicationDate(value: string): Date {
  // SQLite stores these timestamps as timezone-less UTC. FastAPI therefore serializes
  // them without a trailing Z, so add it before converting to the user's local day.
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasTimezone ? value : `${value}Z`);
}

function knownStatus(value: string): MetricStatus {
  return METRIC_STATUSES.includes(value as MetricStatus)
    ? (value as MetricStatus)
    : "prepared";
}

export function buildApplicationMetrics(
  applications: ApplicationOut[],
  range: MetricsRange,
  now = new Date(),
): ApplicationMetrics {
  const end = new Date(now);
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - range + 1);

  const days: DailyApplicationMetric[] = Array.from({ length: range }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return { key: localDayKey(date), date, total: 0, statuses: emptyStatusCounts() };
  });
  const byDay = new Map(days.map((day) => [day.key, day]));

  for (const application of applications) {
    const date = applicationDate(application.applied_at);
    if (Number.isNaN(date.getTime()) || date < start || date > end) continue;

    const day = byDay.get(localDayKey(date));
    if (!day) continue;
    const status = knownStatus(application.status);
    day.total += 1;
    day.statuses[status] += 1;
  }

  const statuses = emptyStatusCounts();
  for (const day of days) {
    for (const status of METRIC_STATUSES) statuses[status] += day.statuses[status];
  }

  const total = days.reduce((sum, day) => sum + day.total, 0);
  const busiestDay = days.reduce<DailyApplicationMetric | null>((busiest, day) => {
    if (day.total === 0) return busiest;
    if (!busiest || day.total > busiest.total) return day;
    return busiest;
  }, null);
  const decidedOutcomes = statuses.offer + statuses.rejected;

  return {
    days,
    total,
    dailyAverage: total / range,
    statuses,
    busiestDay,
    activePipeline: statuses.applied + statuses.interviewing,
    decidedOutcomes,
    rejectionRate:
      decidedOutcomes === 0 ? null : (statuses.rejected / decidedOutcomes) * 100,
  };
}
