import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router";
import {
  Bot,
  Check,
  Copy,
  Download,
  FileText,
  History,
  Loader2,
  NotebookPen,
  Pencil,
  RotateCcw,
  Send,
  Square,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";
import type { NavPayload } from "../api/types";
import { write } from "../api/write";
import type { AgentContext, AgentMode } from "../lib/agentPrompt";
import { pagesUsed, permissionQuestion, toolLabel } from "../lib/agentPrompt";
import { agentStore, useAgent, type TranscriptItem } from "../lib/agentStore";
import { AgentReview } from "./AgentReview";
import { Markdown } from "./Markdown";

/** How often a streaming answer is rendered again, at most. */
const STREAM_RENDER_MS = 200;

/**
 * An agent answer as Markdown, rendered by the core exactly like a page body
 * (issue #101): while it streams, at most every STREAM_RENDER_MS, and once
 * more when it is complete, so nothing jumps when it ends. The last render
 * stays up until a newer one arrives; an older answer arriving late is dropped.
 */
function AgentMarkdown({ text, done }: { text: string; done: boolean }) {
  const [html, setHtml] = useState<string | null>(null);
  const sent = useRef({ at: 0, seq: 0, applied: 0 });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (text.trim() === "") return;
    const render = () => {
      timer.current = null;
      const seq = ++sent.current.seq;
      sent.current.at = Date.now();
      // No page path: the agent links pages as /r/<id>, which stay as written.
      void write.preview(text).then((outcome) => {
        if (!outcome.ok || seq < sent.current.applied) return;
        sent.current.applied = seq;
        setHtml(outcome.data.html);
      });
    };
    if (timer.current !== null) clearTimeout(timer.current);
    const wait = done ? 0 : Math.max(0, STREAM_RENDER_MS - (Date.now() - sent.current.at));
    timer.current = setTimeout(render, wait);
  }, [text, done]);

  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );

  if (html !== null) return <Markdown html={html} className="prose-sm" />;
  return <p className="whitespace-pre-wrap text-sm leading-relaxed text-(--color-text)">{text}</p>;
}

function PageChips({ label, ids, titles }: { label: string; ids: string[]; titles: Map<string, string> }) {
  if (ids.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-(--color-text-faint)">
      <span>{label}</span>
      {ids.map((id) => (
        <Link key={id} to={`/r/${id}`} className="kos-chip inline-flex items-center gap-1" title={id}>
          <FileText size={11} />
          {titles.get(id) ?? id}
        </Link>
      ))}
    </div>
  );
}

function Item({
  item,
  titles,
  onSave,
  review = false,
}: {
  item: TranscriptItem;
  titles: Map<string, string>;
  onSave: (agentId: number) => void;
  /** An answer to a Review request: its items get Decide's actions. */
  review?: boolean;
}) {
  if (item.kind === "user") {
    return (
      <div className="ml-8 rounded-(--radius-card) bg-(--color-accent-ink-bg) px-3 py-2 text-sm text-(--color-text)">
        <span className="mb-0.5 block text-[11px] font-medium uppercase tracking-wide text-(--color-accent-ink-text)">
          {MODE_LABELS[item.mode]}
        </span>
        <span className="whitespace-pre-wrap">{item.text}</span>
      </div>
    );
  }
  if (item.kind === "notice") {
    return (
      <p
        className={`rounded-(--radius-card) px-3 py-2 text-sm ${
          item.tone === "error" ? "bg-(--color-accent-red-bg) text-(--color-accent-red-text)" : "text-(--color-text-muted)"
        }`}
        role={item.tone === "error" ? "alert" : undefined}
      >
        {item.text}
      </p>
    );
  }
  const used = pagesUsed(item.tools);
  const answered = item.permissions.filter((ask) => ask.answer !== null);
  const waiting = item.permissions.filter((ask) => ask.answer === null);
  const toolIds = new Set(item.tools.map((tool) => tool.id));
  // An answered question shows on its tool's row; one without a row gets its own.
  const loose = answered.filter((ask) => ask.toolCallId === null || !toolIds.has(ask.toolCallId));
  return (
    <div data-testid="agent-message">
      {(item.tools.length > 0 || loose.length > 0) && (
        <ul className="mb-1.5 space-y-0.5">
          {item.tools.map((tool) => {
            const ask = answered.find((candidate) => candidate.toolCallId === tool.id);
            return (
              <li key={tool.id} className="flex items-center gap-1.5 text-xs text-(--color-text-faint)">
                {tool.status === "completed" ? (
                  <Check size={12} className="text-(--color-accent-green-text)" />
                ) : tool.status === "failed" || ask?.answer === "refused" ? (
                  <X size={12} className="text-(--color-accent-red-text)" />
                ) : (
                  <Loader2 size={12} className="animate-spin" />
                )}
                {toolLabel(tool.title)}
                {ask && <span className="text-(--color-text-muted)">· {ask.answer}</span>}
              </li>
            );
          })}
          {loose.map((ask) => (
            <li key={ask.requestId} className="flex items-center gap-1.5 text-xs text-(--color-text-faint)">
              {ask.answer === "refused" ? (
                <X size={12} className="text-(--color-accent-red-text)" />
              ) : (
                <Check size={12} className="text-(--color-accent-green-text)" />
              )}
              {toolLabel(ask.title)}
              <span className="text-(--color-text-muted)">· {ask.answer}</span>
            </li>
          ))}
        </ul>
      )}
      {item.text !== "" && <AgentMarkdown text={item.text} done={item.done} />}
      {waiting.map((ask) => (
        // Where the agent is waiting: after what it has said so far.
        <div key={ask.requestId} className="kos-card mt-2 px-3 py-2.5 text-sm" data-testid="agent-permission">
          <p className="font-medium text-(--color-text)">{permissionQuestion(ask.title)}</p>
          <p className="mt-0.5 text-xs text-(--color-text-faint)">{ask.title}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ask.options.map((option) => (
              <button
                key={option.id}
                type="button"
                className={`kos-btn kos-btn-sm ${option.kind.startsWith("allow") ? "kos-btn-primary" : "kos-btn-secondary"}`}
                onClick={() => void agentStore.answer(ask.requestId, option.id)}
              >
                {option.name}
              </button>
            ))}
          </div>
        </div>
      ))}
      {item.done && (
        <>
          <PageChips label="Pages used:" ids={used.read} titles={titles} />
          <PageChips label="Written:" ids={used.written} titles={titles} />
          {item.text.trim() !== "" && (
            <button
              type="button"
              className="mt-1.5 inline-flex items-center gap-1 text-xs text-(--color-text-faint) hover:text-(--color-text)"
              onClick={() => onSave(item.id)}
              title="Save this answer as a draft note"
            >
              <NotebookPen size={12} />
              Save as note
            </button>
          )}
          {review && <AgentReview text={item.text} />}
        </>
      )}
    </div>
  );
}

function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="mt-2 inline-flex items-center gap-1.5 rounded-[5px] bg-(--color-bg-sidebar) px-2 py-1 font-mono text-xs text-(--color-text)"
      onClick={() => {
        void navigator.clipboard?.writeText(command).then(() => setCopied(true));
      }}
      title="Copy"
    >
      {command}
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  );
}

/** Choosing the agent, installing its adapter, and signing in, before the first request. */
function Setup() {
  const state = useAgent();
  const providers = state.providers;
  if (providers === null) return <p className="text-sm text-(--color-text-muted)">Looking for agents on this computer…</p>;
  if (providers.length === 0) return <p className="text-sm text-(--color-text-muted)">No agents are available.</p>;
  const chosen = providers.find((item) => item.id === state.providerId) ?? providers[0];
  const installing = state.install?.providerId === chosen.id ? state.install : null;
  return (
    <div className="space-y-3 text-sm">
      <fieldset>
        <legend className="mb-1.5 text-[13px] font-medium text-(--color-text-muted)">Agent</legend>
        <div className="space-y-1.5" role="radiogroup">
          {providers.map((provider) => (
            <label key={provider.id} className="flex cursor-pointer items-start gap-2 rounded-md px-1 py-1 hover:bg-(--color-bg-sidebar)">
              <input
                type="radio"
                name="agent-provider"
                className="mt-1 accent-(--color-accent)"
                checked={provider.id === chosen.id}
                onChange={() => agentStore.choose(provider.id)}
                disabled={state.session !== "none" && state.session !== "closed"}
              />
              <span>
                <span className="block font-medium text-(--color-text)">{provider.displayName}</span>
                <span className="block text-xs text-(--color-text-faint)">{provider.message}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {chosen.state === "ready" && !chosen.adapterInstalled && (
        <div className="kos-card px-3 py-2.5">
          <p className="text-(--color-text)">
            The app talks to {chosen.displayName} through a small adapter ({chosen.adapterVersion}), which is downloaded
            from npm the first time and checked against the version Knowledge OS was tested with.
          </p>
          {installing ? (
            <p className="mt-2 flex items-center gap-2 text-xs text-(--color-text-muted)">
              <Loader2 size={12} className="animate-spin" />
              Installing… {installing.total > 0 ? `${installing.done} of ${installing.total} packages` : ""}
            </p>
          ) : (
            <button type="button" className="kos-btn kos-btn-primary kos-btn-sm mt-2 inline-flex items-center gap-1.5" onClick={() => void agentStore.install(chosen.id)}>
              <Download size={13} />
              Install adapter
            </button>
          )}
        </div>
      )}
    </div>
  );
}

const MODE_LABELS: Record<AgentMode, string> = { ask: "Ask", draft: "Draft", review: "Review" };
const DEFAULT_REVIEW_REQUEST = "Go through everything that waits for me in Decide.";

function formatWhen(stamp: string): string {
  const date = new Date(stamp);
  const today = new Date();
  return date.toDateString() === today.toDateString()
    ? date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: date.getFullYear() === today.getFullYear() ? undefined : "numeric" });
}

/** The chat list (issue #100): past conversations in this knowledge base, newest first. */
function ConversationList({ onOpen }: { onOpen: (id: string) => void }) {
  const state = useAgent();
  useEffect(() => {
    void agentStore.loadConversations();
  }, []);
  const conversations = state.conversations;
  if (conversations === null) return <p className="text-sm text-(--color-text-muted)">Loading conversations…</p>;
  if (conversations.length === 0)
    return <p className="text-sm text-(--color-text-muted)">No conversations yet. They are kept on this computer after every answer.</p>;
  return (
    <ul className="space-y-1" data-testid="agent-conversations">
      {conversations.map((conversation) => (
        <li
          key={conversation.id}
          className={`group flex items-start gap-1 rounded-(--radius-control) px-2 py-1.5 hover:bg-(--color-bg-sidebar) ${
            conversation.id === state.conversationId ? "bg-(--color-bg-sidebar)" : ""
          }`}
        >
          <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(conversation.id)}>
            <span className="block truncate text-sm text-(--color-text)">{conversation.title}</span>
            <span className="block truncate text-xs text-(--color-text-faint)">
              {formatWhen(conversation.updatedAt)}
              {conversation.about ? ` · ${conversation.about}` : ""}
            </span>
          </button>
          <button
            type="button"
            className="kos-icon-btn opacity-60 group-hover:opacity-100"
            aria-label={`Rename ${conversation.title}`}
            title="Rename"
            onClick={() => {
              const title = window.prompt("Rename the conversation", conversation.title);
              if (title !== null) void agentStore.renameConversation(conversation.id, title);
            }}
          >
            <Pencil size={13} />
          </button>
          <button
            type="button"
            className="kos-icon-btn opacity-60 group-hover:opacity-100"
            aria-label={`Delete ${conversation.title}`}
            title="Delete"
            onClick={() => {
              if (window.confirm(`Delete “${conversation.title}”? It is removed from this computer.`))
                void agentStore.deleteConversation(conversation.id);
            }}
          >
            <Trash2 size={13} />
          </button>
        </li>
      ))}
    </ul>
  );
}

export function AgentPanel({
  open,
  onClose,
  context,
  nav,
}: {
  open: boolean;
  onClose: () => void;
  context: AgentContext;
  nav: NavPayload | null;
}) {
  const state = useAgent();
  const [mode, setMode] = useState<AgentMode>("ask");
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const [showList, setShowList] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const navigate = useNavigate();
  const titles = new Map((nav?.record_index ?? []).map((entry) => [entry.id, entry.title]));
  const saveNote = async (agentId: number | null) => {
    setSaved(null);
    const result = await agentStore.saveAsNote(agentId, context, titles);
    if (result === "held") setSaved("The note waits for review in Decide.");
    else if (result !== null) navigate(`/r/${encodeURIComponent(result.id)}/edit`);
  };
  const hasAnswer = state.transcript.some((item) => item.kind === "agent" && item.done && item.text.trim() !== "");
  // The answers to Review requests: the agent messages after a Review request.
  const reviewAnswers = new Set<number>();
  let lastMode: AgentMode | null = null;
  for (const item of state.transcript) {
    if (item.kind === "user") lastMode = item.mode;
    else if (item.kind === "agent" && lastMode === "review") reviewAnswers.add(item.id);
  }

  useEffect(() => {
    if (open) {
      void agentStore.refresh();
      inputRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [state.transcript]);

  if (!open || !state.available) return null;

  const chosen = state.providers?.find((item) => item.id === state.providerId) ?? null;
  const canChat = chosen !== null && chosen.state === "ready" && chosen.adapterInstalled && state.session !== "auth-required";
  const send = () => {
    const request = text.trim() || (mode === "review" ? DEFAULT_REVIEW_REQUEST : "");
    if (!canChat || request === "" || state.busy) return;
    setText("");
    void agentStore.send(mode, request, context);
  };
  const onKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };
  const scope = context.page?.title ?? context.project?.title ?? null;

  return (
    <aside
      className="fixed right-0 top-(--frame-top) bottom-0 z-40 flex w-full flex-col border-l border-(--color-border) bg-(--color-bg) shadow-[-8px_0_24px_rgb(0_0_0/0.06)] sm:w-[400px]"
      aria-label="Agent"
      data-testid="agent-panel"
    >
      <header className="flex items-center gap-2 border-b border-(--color-border) px-3 py-2">
        <Bot size={16} className="text-(--color-accent-text)" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-(--color-text)">Agent</p>
          <p className="truncate text-xs text-(--color-text-faint)">
            {state.sessionProvider !== null ? `${chosen?.displayName ?? ""} · ${state.session}` : "Not started"}
          </p>
        </div>
        <button
          type="button"
          className="kos-icon-btn"
          onClick={() => setShowList((value) => !value)}
          aria-label="Conversations"
          aria-pressed={showList}
          title="Conversations"
        >
          <History size={15} />
        </button>
        <button
          type="button"
          className="kos-icon-btn"
          onClick={() => void saveNote(null)}
          disabled={!hasAnswer || state.busy}
          aria-label="Save the conversation as a note"
          title="Save the conversation as a draft note"
        >
          <NotebookPen size={15} />
        </button>
        <button
          type="button"
          className="kos-icon-btn"
          onClick={() => {
            setShowList(false);
            void agentStore.clear();
          }}
          aria-label="New conversation"
          title="New conversation"
        >
          <SquarePen size={15} />
        </button>
        <button type="button" className="kos-icon-btn" onClick={onClose} aria-label="Close the agent panel" title="Close (Ctrl+J)">
          <X size={16} />
        </button>
      </header>

      {showList ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
          <ConversationList
            onOpen={(id) => {
              setShowList(false);
              void agentStore.openConversation(id);
            }}
          />
        </div>
      ) : (
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {state.conversationTitle && (
          <p className="truncate text-xs font-medium text-(--color-text-faint)" title={state.conversationTitle}>
            {state.conversationTitle}
          </p>
        )}
        {state.transcript.length === 0 && <Setup />}
        {state.transcript.length === 0 && canChat && (
          <p className="text-sm text-(--color-text-muted)">
            Ask about the knowledge base, or switch to Draft to have the agent write a note or propose a decision.
            It uses the same tools as agents outside the app: it cannot accept, withdraw, or delete anything, and what
            it writes is marked as the agent's.
          </p>
        )}
        {state.transcript.map((item) => (
          <Item
            key={item.id}
            item={item}
            titles={titles}
            onSave={(agentId) => void saveNote(agentId)}
            review={item.kind === "agent" && reviewAnswers.has(item.id)}
          />
        ))}
        {state.session === "auth-required" && state.auth !== null && (
          <div className="kos-card px-3 py-2.5 text-sm" role="alert">
            <p className="text-(--color-text)">{state.auth.message}</p>
            {state.auth.command && <CopyCommand command={state.auth.command} />}
            <button type="button" className="kos-btn kos-btn-secondary kos-btn-sm mt-2 flex items-center gap-1.5" onClick={() => void agentStore.restart()}>
              <RotateCcw size={13} />
              Try again
            </button>
          </div>
        )}
        {state.session === "crashed" && (
          <button type="button" className="kos-btn kos-btn-secondary kos-btn-sm flex items-center gap-1.5" onClick={() => void agentStore.restart()}>
            <RotateCcw size={13} />
            Restart the agent
          </button>
        )}
        {state.error && (
          <p className="rounded-(--radius-card) bg-(--color-accent-red-bg) px-3 py-2 text-sm text-(--color-accent-red-text)" role="alert">
            {state.error}
          </p>
        )}
        {saved && <p className="text-sm text-(--color-text-muted)">{saved}</p>}
        <div ref={endRef} />
      </div>
      )}

      <footer className="border-t border-(--color-border) px-3 py-2.5">
        <div className="mb-2 flex items-center gap-1" role="radiogroup" aria-label="Mode">
          {(["ask", "draft", "review"] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={mode === value}
              onClick={() => setMode(value)}
              className={`rounded-[5px] px-2.5 py-1 text-[13px] ${
                mode === value
                  ? "bg-(--color-accent-ink-bg) font-medium text-(--color-accent-ink-text)"
                  : "text-(--color-text-muted) hover:text-(--color-text)"
              }`}
            >
              {MODE_LABELS[value]}
            </button>
          ))}
          {scope && <span className="ml-auto truncate pl-2 text-xs text-(--color-text-faint)">About: {scope}</span>}
        </div>
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKey}
            rows={2}
            disabled={!canChat}
            placeholder={
              mode === "ask"
                ? "Ask the knowledge base…"
                : mode === "draft"
                  ? "What should the agent write?"
                  : "Press Enter to go through Decide, or say what to look at"
            }
            aria-label={mode === "ask" ? "Question" : "Request"}
            className="kos-input min-h-[2.75rem] flex-1 resize-none text-sm"
          />
          {state.busy ? (
            <button type="button" className="kos-btn kos-btn-secondary" onClick={() => void agentStore.cancel()} aria-label="Stop" title="Stop">
              <Square size={14} />
            </button>
          ) : (
            <button type="button" className="kos-btn kos-btn-primary" onClick={send} disabled={!canChat || (text.trim() === "" && mode !== "review")} aria-label="Send" title="Send (Enter)">
              <Send size={14} />
            </button>
          )}
        </div>
      </footer>
    </aside>
  );
}
