import { relativeTime, shortId } from "@/lib/format";
import { stateTone, tickFor } from "@/lib/states";

export type TaskRowModel = {
  id: string;
  title: string;
  priority: string | null;
  state: string;
  updatedAt: string;
};

const TONE_CLASS = {
  pine: "text-pine",
  brick: "text-brick",
  ink: "text-ink",
} as const;

export function TaskRow({ task, now }: { task: TaskRowModel; now: Date }) {
  const tick = tickFor(task.state);
  const tone = stateTone(task.state);

  return (
    <li className="grid h-row grid-cols-[16px_4.5rem_minmax(0,1fr)_5.5rem_11.5rem_5.5rem] items-center gap-x-5 border-b border-hairline [grid-template-areas:'tick_id_title_priority_state_time'] hover:bg-surface max-[719px]:h-auto max-[719px]:grid-cols-[16px_repeat(4,max-content)] max-[719px]:justify-start max-[719px]:gap-y-1 max-[719px]:py-3 max-[719px]:[grid-template-areas:'tick_title_title_title_title'_'tick_id_priority_state_time']">
      <span
        className="flex items-center justify-center [grid-area:tick]"
        aria-hidden="true"
      >
        {tick === "none" ? null : (
          <span
            data-tick={tick}
            className={`block h-6 w-[2px] ${tick === "pine" ? "bg-pine" : "bg-brick"}`}
          />
        )}
      </span>
      <span className="font-courier text-meta tabular-nums text-graphite [grid-area:id]">
        {shortId(task.id)}
      </span>
      <a
        href={`/tasks/${task.id}`}
        className="truncate font-newsreader text-row-title font-medium text-ink [grid-area:title] max-[719px]:whitespace-normal"
      >
        {task.title}
      </a>
      <span className="font-sans text-meta text-graphite [grid-area:priority]">
        {task.priority ?? "—"}
      </span>
      <span
        data-state={task.state}
        className={`font-sans text-section font-semibold [grid-area:state] ${TONE_CLASS[tone]}`}
      >
        {task.state}
      </span>
      <time
        dateTime={task.updatedAt}
        title={task.updatedAt}
        className="text-right font-sans text-meta text-graphite [grid-area:time] max-[719px]:text-left"
      >
        {relativeTime(task.updatedAt, now)}
      </time>
    </li>
  );
}
