import { TaskRow, type TaskRowModel } from "@/components/TaskRow";
import { isTerminal } from "@/lib/states";

export const dynamic = "force-dynamic";

function stamp(ms: number): string {
  return new Date(ms).toISOString();
}

function openWorkFixture(now: Date): TaskRowModel[] {
  const yesterday = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate() - 1,
    15,
    0,
    0,
  );

  return [
    {
      id: "8f3c1a2b-4c5d-4e6f-a7b8-c9d0e1f20001",
      title: "Checkout API returns HTTP 500 after user login",
      priority: "high",
      state: "AWAITING_APPROVAL",
      updatedAt: stamp(now.getTime() - 2 * 60_000),
    },
    {
      id: "1c02e93a-4b5c-4d6e-8f70-112233445501",
      title: "Login never writes cart_id onto the session",
      priority: "medium",
      state: "INVESTIGATING",
      updatedAt: stamp(now.getTime() - 18 * 60_000),
    },
    {
      id: "9ab14d77-1111-4222-8333-444455556601",
      title: "Payment webhook signature mismatch",
      priority: "low",
      state: "PR_CREATED",
      updatedAt: stamp(yesterday),
    },
    {
      id: "44e0b7aa-bbbb-4ccc-8ddd-eeeeffff0001",
      title: "Checkout suite killed at the sandbox timeout",
      priority: "critical",
      state: "FAILED",
      updatedAt: stamp(yesterday),
    },
  ];
}

function subtitle(tasks: TaskRowModel[]): string {
  const active = tasks.filter((task) => !isTerminal(task.state)).length;
  const decision = "Decisions happen in Switch.";
  if (active === 1) return `One active task in the room. ${decision}`;
  if (active > 1) return `${active} active tasks in the room. ${decision}`;
  return decision;
}

function entryCount(count: number): string {
  return `${count} ${count === 1 ? "ENTRY" : "ENTRIES"}`;
}

export default function Page() {
  const now = new Date();
  const tasks = openWorkFixture(now);

  return (
    <div className="py-12">
      <h1 className="font-newsreader text-display font-normal tracking-[-0.02em] text-ink">
        Open work.
      </h1>
      {tasks.length === 0 ? (
        <div className="mt-8 max-w-[40rem]">
          <p className="font-sans text-[15px] leading-6 text-ink">
            No tasks in this room yet.
          </p>
          <p className="mt-4 font-sans text-prose text-graphite">
            Mention <span className="font-courier text-ink">@devteam</span> in
            Switch with a repository and the error.
          </p>
        </div>
      ) : (
        <>
          <p className="mt-3 font-sans text-prose text-graphite">{subtitle(tasks)}</p>
          <section className="mt-12" aria-labelledby="active-queue">
            <div className="flex items-baseline justify-between gap-6 border-b border-hairline pb-3">
              <h2
                id="active-queue"
                className="font-sans text-section font-semibold text-graphite"
              >
                01 / ACTIVE DOSSIER QUEUE
              </h2>
              <p className="font-sans text-section font-semibold text-graphite">
                {entryCount(tasks.length)}
              </p>
            </div>
            <ul>
              {tasks.map((task) => (
                <TaskRow key={task.id} task={task} now={now} />
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
