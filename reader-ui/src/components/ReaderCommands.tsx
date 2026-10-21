import { useEffect } from "react";
import { useNavigate } from "react-router";
import { onReaderCommand } from "../lib/agentBridge";
import { useStructure } from "./Structure";

/** Handles the desktop menu's New Page (Ctrl+N) and Agent (Ctrl+J).
 *
 * New Page opens a new page in `projectId`. Without any project it opens the
 * New project dialog instead, and the new page follows: pages always live in
 * a project, so a fresh knowledge base still gets somewhere to write.
 * `projectId` is undefined while that is not known yet, and New Page then
 * does nothing. */
export function ReaderCommands({
  projectId,
  onToggleAgent,
}: {
  projectId: string | null | undefined;
  onToggleAgent: () => void;
}) {
  const navigate = useNavigate();
  const structure = useStructure();
  useEffect(
    () =>
      onReaderCommand((command) => {
        if (command === "toggle-agent") onToggleAgent();
        if (command === "new-page") {
          if (projectId === undefined) return;
          if (projectId !== null) navigate(`/p/${encodeURIComponent(projectId)}/new`);
          else structure.newProject({ thenNewPage: true });
        }
      }),
    [navigate, onToggleAgent, projectId, structure],
  );
  return null;
}
