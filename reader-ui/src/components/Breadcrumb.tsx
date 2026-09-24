import { Link } from "react-router";
import { ChevronRight } from "lucide-react";
import type { Breadcrumb as BreadcrumbItem } from "../api/types";

function Separator() {
  return <ChevronRight size={13} className="shrink-0 text-(--color-text-faint)" aria-hidden="true" />;
}

export function Breadcrumb({ items, current }: { items: BreadcrumbItem[]; current?: string }) {
  if (items.length === 0 && !current) return null;
  return (
    <nav className="mb-4 flex min-w-0 flex-wrap items-center gap-1 text-[13px] text-(--color-text-muted)">
      {items.map((item, index) => (
        <span key={item.href} className="flex items-center gap-1">
          {index > 0 && <Separator />}
          <Link to={item.href} className="rounded-sm hover:text-(--color-text) hover:underline hover:underline-offset-[3px]">
            {item.label}
          </Link>
        </span>
      ))}
      {current && (
        <span className="flex min-w-0 items-center gap-1">
          {items.length > 0 && <Separator />}
          <span className="truncate text-(--color-text-faint)">{current}</span>
        </span>
      )}
    </nav>
  );
}
