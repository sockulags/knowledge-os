import { Link } from "react-router";
import type { Breadcrumb as BreadcrumbItem } from "../api/types";

export function Breadcrumb({ items, current }: { items: BreadcrumbItem[]; current?: string }) {
  if (items.length === 0 && !current) return null;
  return (
    <nav className="mb-3 flex flex-wrap items-center gap-1.5 text-sm text-(--color-text-muted)">
      {items.map((item, index) => (
        <span key={item.href} className="flex items-center gap-1.5">
          {index > 0 && <span className="text-(--color-text-faint)">/</span>}
          <Link to={item.href} className="hover:text-(--color-text) hover:underline">
            {item.label}
          </Link>
        </span>
      ))}
      {current && (
        <span className="flex items-center gap-1.5">
          {items.length > 0 && <span className="text-(--color-text-faint)">/</span>}
          <span>{current}</span>
        </span>
      )}
    </nav>
  );
}
