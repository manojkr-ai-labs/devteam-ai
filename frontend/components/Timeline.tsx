import React from "react";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

export type TimelineEvent = {
  id: string;
  at: string;
  actor: string;
  line: string;
  failed: boolean;
};

function clock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = date.getUTCDate();
  const month = MONTHS[date.getUTCMonth()];
  const hours = String(date.getUTCHours()).padStart(2, "0");
  const minutes = String(date.getUTCMinutes()).padStart(2, "0");
  return `${day} ${month} ${hours}:${minutes}`;
}

export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) return null;

  return (
    <section id="timeline" className="mt-12" aria-labelledby="timeline-title">
      <div className="border-b border-hairline pb-3">
        <h2
          id="timeline-title"
          className="font-sans text-section font-semibold text-graphite"
        >
          01 / TIMELINE
        </h2>
      </div>
      <ol className="mt-2 border-l border-hairline">
        {events.map((event) => (
          <li
            key={event.id}
            className={`grid grid-cols-[8.5rem_9rem_minmax(0,1fr)] gap-x-6 border-b border-hairline py-3 pl-6 max-[719px]:grid-cols-1 max-[719px]:gap-y-1 ${
              event.failed ? "text-brick" : "text-ink"
            }`}
          >
            <time
              dateTime={event.at}
              title={event.at}
              className={`font-courier text-meta ${event.failed ? "text-brick" : "text-graphite"}`}
            >
              {clock(event.at)}
            </time>
            <span className="font-sans text-meta">{event.actor}</span>
            <span className="font-sans text-prose">{event.line}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
