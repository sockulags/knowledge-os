import { useState } from "react";
import { Link, useLocation } from "react-router";
import { ChevronRight, Folder } from "lucide-react";
import type { TreeNode } from "../api/types";
import { iconFor } from "../lib/icons";

function RecordLink({ id, title, isDecision, kind }: { id: string; title: string; isDecision: boolean; kind: string }) {
  const location = useLocation();
  const href = `/r/${id}`;
  const active = location.pathname === href;
  const Icon = iconFor(kind, isDecision);
  return (
    <Link
      to={href}
      className={`flex items-center gap-2 rounded-md px-2 py-1 text-sm truncate ${
        active ? "bg-(--color-bg-hover) font-medium text-(--color-text)" : "text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
      }`}
      title={title}
    >
      <Icon size={14} className="shrink-0 opacity-70" />
      <span className="truncate">{title}</span>
    </Link>
  );
}

export function TreeNodeView({ node, depth }: { node: TreeNode; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildContent = node.records.length > 0 || node.children.length > 0 || node.broken.length > 0;

  return (
    <div>
      {node.overview ? (
        <div className="flex items-center">
          {hasChildContent ? (
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              className="flex h-6 w-5 shrink-0 items-center justify-center text-(--color-text-faint)"
              aria-label={open ? "Collapse" : "Expand"}
            >
              <ChevronRight size={13} className={open ? "rotate-90 transition-transform" : "transition-transform"} />
            </button>
          ) : (
            <span className="w-5 shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <RecordLink id={node.overview.id} title={node.overview.title} isDecision={node.overview.is_decision} kind={node.overview.type} />
          </div>
        </div>
      ) : (
        <div className="flex items-center">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="flex h-6 w-5 shrink-0 items-center justify-center text-(--color-text-faint)"
            aria-label={open ? "Collapse" : "Expand"}
          >
            <ChevronRight size={13} className={open ? "rotate-90 transition-transform" : "transition-transform"} />
          </button>
          <span className="flex min-w-0 flex-1 items-center gap-2 truncate px-2 py-1 text-sm text-(--color-text-muted)">
            <Folder size={14} className="shrink-0 opacity-70" />
            <span className="truncate capitalize">{node.name || "root"}</span>
          </span>
        </div>
      )}

      {open && hasChildContent && (
        <div className="ml-5 border-l border-(--color-border) pl-1.5">
          {node.records.map((record) => (
            <RecordLink key={record.id} id={record.id} title={record.title} isDecision={record.is_decision} kind={record.type} />
          ))}
          {node.broken.map((entry) => (
            <div key={entry.path} className="truncate px-2 py-1 text-xs text-(--color-accent-red-text)" title={entry.message}>
              {entry.path.split("/").pop()}
            </div>
          ))}
          {node.children.map((child) => (
            <TreeNodeView key={child.name} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
