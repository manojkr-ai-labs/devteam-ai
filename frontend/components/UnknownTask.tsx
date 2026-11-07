import React from "react";

export function UnknownTask() {
  return (
    <div className="py-12">
      <h1 className="font-newsreader text-display font-normal tracking-[-0.02em] text-ink">
        This task is not in the room.
      </h1>
      <p className="mt-8">
        <a
          href="/"
          className="font-sans text-section font-semibold text-pine underline decoration-pine decoration-1 underline-offset-4"
        >
          Open work
        </a>
      </p>
    </div>
  );
}
