import type { ReactNode } from "react";
import { Link } from "react-router";
import { Compass } from "lucide-react";

/** A friendly empty state for an unknown id/name/path, whether the route
 * itself is unmatched (client-side "not found") or the API answered 404. */
export function EmptyState({
  title,
  body,
  icon,
  action,
}: {
  title: string;
  body?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mx-auto flex max-w-[520px] flex-col items-center gap-3 px-6 py-24 text-center">
      <div className="mb-1 text-(--color-text-faint)">{icon ?? <Compass size={28} strokeWidth={1.5} />}</div>
      <h1 className="text-xl font-semibold">{title}</h1>
      {body && <p className="text-(--color-text-muted)">{body}</p>}
      {action ?? (
        <Link
          to="/"
          className="mt-2 rounded-md border border-(--color-border) px-3 py-1.5 text-sm hover:bg-(--color-bg-hover)"
        >
          Back home
        </Link>
      )}
    </div>
  );
}
