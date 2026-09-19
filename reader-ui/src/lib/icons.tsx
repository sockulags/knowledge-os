import {
  FileText,
  Gavel,
  Eye,
  Layers,
  BookOpen,
  FolderClosed,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

/** One small icon per record/page kind, used in the sidebar tree and
 * quick-find results (design brief: "a small lucide icon for its kind:
 * decision a gavel or scale; ordinary record a file-text icon"). */
export function iconFor(kind: string, isDecision?: boolean): LucideIcon {
  if (isDecision || kind === "decision") return Gavel;
  switch (kind) {
    case "discovery":
      return Eye;
    case "source":
      return Layers;
    case "skill":
      return BookOpen;
    case "doc":
      return FolderClosed;
    case "project":
      return Sparkles;
    default:
      return FileText;
  }
}
