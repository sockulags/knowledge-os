import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Check, GitBranch, UserRound } from "lucide-react";
import { api } from "../api/client";
import type { SyncRemoteCheck, SyncSetup as SetupPayload, WriteFailure } from "../api/types";
import { syncSetup } from "../api/write";
import { Callout } from "./Callout";
import { ConfirmDialog } from "./ConfirmDialog";

/** States the guided setup walks through, in order. */
const STEPS = ["init", "remote", "publish"] as const;

function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => (key in values ? String(values[key]) : match));
}

/** Render `code` spans written with backticks in a sentence from the core. */
function withCode(text: string): ReactNode[] {
  return text.split(/(`[^`]+`)/).map((part, index) =>
    part.startsWith("`") && part.endsWith("`") ? <code key={index}>{part.slice(1, -1)}</code> : part,
  );
}

function Failure({ title, failure }: { title: string; failure: WriteFailure }) {
  return (
    <Callout tone="danger">
      <p className="font-medium">{title}</p>
      <p className="mt-1 whitespace-pre-wrap break-words">{withCode(failure.detail)}</p>
    </Callout>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "email";
}) {
  return (
    <div className="min-w-0 flex-1">
      <label htmlFor={id} className="mb-1.5 block text-[13px] font-medium text-(--color-text-muted)">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        onChange={(event) => onChange(event.target.value)}
        className="kos-input"
      />
    </div>
  );
}

function StepList({ setup }: { setup: SetupPayload }) {
  const L = setup.language;
  const current = STEPS.indexOf(setup.state as (typeof STEPS)[number]);
  const labels = [L.step_init, L.step_remote, L.step_publish];
  return (
    <ol className="mb-5 flex flex-wrap gap-x-5 gap-y-2 text-[13px]" aria-label={L.heading}>
      {labels.map((label, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li
            key={label}
            aria-current={active ? "step" : undefined}
            className={`flex items-center gap-1.5 ${active ? "font-medium text-(--color-text)" : "text-(--color-text-faint)"}`}
          >
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold ${
                done
                  ? "bg-(--color-accent-green-bg) text-(--color-accent-green-text)"
                  : active
                    ? "bg-(--color-accent) text-(--color-bg)"
                    : "border border-(--color-border) text-(--color-text-faint)"
              }`}
              aria-hidden="true"
            >
              {done ? <Check size={12} /> : index + 1}
            </span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}

/** Name and email for Git, stored in this repository only. Shown inside the
 * first step when Git has no identity, and as its own card later. */
export function IdentityFields({
  setup,
  name,
  email,
  onName,
  onEmail,
}: {
  setup: SetupPayload;
  name: string;
  email: string;
  onName: (value: string) => void;
  onEmail: (value: string) => void;
}) {
  const L = setup.language;
  return (
    <div className="mb-4 rounded-(--radius-card) border border-(--color-border) bg-(--color-bg-sidebar) p-4">
      <p className="mb-1 flex items-center gap-1.5 text-sm font-medium">
        <UserRound size={15} className="text-(--color-text-faint)" /> {L.identity_heading}
      </p>
      <p className="mb-3 text-sm text-(--color-text-muted)">{L.identity_missing}</p>
      <div className="flex flex-wrap gap-3">
        <Field id="setup-identity-name" label={L.identity_name} value={name} onChange={onName} />
        <Field id="setup-identity-email" label={L.identity_email} value={email} onChange={onEmail} type="email" />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-(--color-text-faint)">{withCode(L.identity_help)}</p>
    </div>
  );
}

function IdentityCard({ setup, onSaved }: { setup: SetupPayload; onSaved: (message: string) => void }) {
  const L = setup.language;
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<WriteFailure | null>(null);

  async function save() {
    setBusy(true);
    setFailure(null);
    const outcome = await syncSetup.identity(name, email);
    setBusy(false);
    if (outcome.ok) onSaved(fill(L.identity_saved, outcome.data.identity));
    else setFailure(outcome.failure);
  }

  return (
    <section className="kos-card mb-6 p-5" data-testid="sync-identity">
      {failure && <Failure title={L.failed} failure={failure} />}
      <IdentityFields setup={setup} name={name} email={email} onName={setName} onEmail={setEmail} />
      <button type="button" disabled={busy} onClick={save} className="kos-btn kos-btn-secondary">
        {busy ? L.working : L.identity_save}
      </button>
    </section>
  );
}

function InitStep({ setup, onDone }: { setup: SetupPayload; onDone: (message: string) => void }) {
  const L = setup.language;
  const needsIdentity = setup.identity === null;
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<WriteFailure | null>(null);

  async function start() {
    setBusy(true);
    setFailure(null);
    const outcome = await syncSetup.init(needsIdentity ? { name, email } : undefined);
    setBusy(false);
    setConfirming(false);
    if (outcome.ok) onDone(fill(L.init_done, { count: outcome.data.files }));
    else setFailure(outcome.failure);
  }

  return (
    <>
      <p className="mb-4 max-w-[70ch] text-sm leading-relaxed text-(--color-text-muted)">{L.init_body}</p>
      {needsIdentity && <IdentityFields setup={setup} name={name} email={email} onName={setName} onEmail={setEmail} />}
      {failure && <Failure title={L.failed} failure={failure} />}
      <button
        type="button"
        disabled={busy || (needsIdentity && (name.trim() === "" || email.trim() === ""))}
        onClick={() => setConfirming(true)}
        className="kos-btn kos-btn-primary"
      >
        {L.init_action}
      </button>
      {confirming && (
        <ConfirmDialog
          title={L.init_confirm_title}
          confirmLabel={L.init_confirm_action}
          cancelLabel={L.cancel}
          workingLabel={L.working}
          busy={busy}
          onConfirm={start}
          onCancel={() => setConfirming(false)}
        >
          {L.init_confirm_body}
        </ConfirmDialog>
      )}
    </>
  );
}

function RemoteStep({ setup, onDone }: { setup: SetupPayload; onDone: (message: string) => void }) {
  const L = setup.language;
  const existing = setup.state === "publish";
  const [url, setUrl] = useState(existing ? (setup.remote_url ?? "") : "");
  const [checked, setChecked] = useState<{ url: string; check: SyncRemoteCheck } | null>(null);
  const [busy, setBusy] = useState<"check" | "connect" | null>(null);
  const [failure, setFailure] = useState<WriteFailure | null>(null);

  // An existing remote is addressed by name, so its stored URL (which Git
  // may have redacted) is never sent back.
  const target = existing && url === (setup.remote_url ?? "") ? undefined : url;
  const current = checked !== null && checked.url === url ? checked.check : null;
  const usable = current !== null && (current.empty || current.related === true);

  async function check() {
    setBusy("check");
    setFailure(null);
    setChecked(null);
    const outcome = await syncSetup.check(target);
    setBusy(null);
    if (outcome.ok) setChecked({ url, check: outcome.data.check });
    else setFailure(outcome.failure);
  }

  async function connect() {
    setBusy("connect");
    setFailure(null);
    const outcome = await syncSetup.connect(target);
    setBusy(null);
    if (outcome.ok) {
      const shown = current?.url ?? url;
      onDone(fill(outcome.data.state === "published" ? L.published : L.connected, { url: shown }));
    } else {
      setFailure(outcome.failure);
    }
  }

  return (
    <>
      <p className="mb-4 max-w-[70ch] text-sm leading-relaxed text-(--color-text-muted)">
        {existing ? fill(L.publish_body, { branch: setup.branch ?? "" }) : L.remote_body}
      </p>
      <form
        className="mb-4 flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void check();
        }}
      >
        <Field id="setup-remote-url" label={L.url_label} value={url} onChange={setUrl} placeholder={L.url_placeholder} />
        <button type="submit" disabled={busy !== null || url.trim() === ""} className="kos-btn kos-btn-secondary">
          {busy === "check" ? L.checking : L.check_action}
        </button>
      </form>
      {failure && <Failure title={L.failed} failure={failure} />}
      {current !== null && (
        <Callout tone={usable ? "neutral" : "danger"} icon={usable ? <Check size={16} /> : undefined}>
          <p data-testid="setup-check-result">
            {current.empty
              ? L.check_empty
              : current.related
                ? fill(L.check_related, { branch: current.branch ?? "" })
                : L.check_unrelated}
          </p>
        </Callout>
      )}
      <button
        type="button"
        disabled={!usable || busy !== null}
        onClick={connect}
        className="kos-btn kos-btn-primary"
      >
        {busy === "connect" ? L.publishing : current !== null && !current.empty ? L.connect_action : L.publish_action}
      </button>
    </>
  );
}

/** The guided setup on the sync page: initialise Git, connect a remote, and
 * publish the branch, one step at a time. `version` changes whenever the
 * repository status does, so the panel re-reads where the setup stands. */
export function SyncSetupPanel({ version, onDone }: { version: string; onDone: (message: string) => void }) {
  const [setup, setSetup] = useState<SetupPayload | null>(null);

  const load = useCallback(() => {
    api
      .syncSetup()
      .then(setSetup)
      .catch(() => setSetup(null));
  }, []);

  useEffect(() => {
    load();
  }, [load, version]);

  if (setup === null) return null;
  const L = setup.language;
  const done = (message: string) => {
    onDone(message);
    load();
  };

  if (!STEPS.includes(setup.state as (typeof STEPS)[number])) {
    // Sync works (or cannot be set up here); only a missing identity is left to fix.
    return setup.state === "ready" && setup.identity === null ? <IdentityCard setup={setup} onSaved={done} /> : null;
  }

  return (
    <>
      <section className="kos-card mb-6 p-5" data-testid="sync-setup" data-state={setup.state}>
        <h2 className="kos-heading mb-1 flex items-center gap-2">
          <GitBranch size={19} className="text-(--color-accent-text)" /> {L.heading}
        </h2>
        <p className="mb-1 text-sm font-medium">{setup.sentence}</p>
        <p className="mb-5 max-w-[70ch] text-sm leading-relaxed text-(--color-text-muted)">{L.intro}</p>
        <StepList setup={setup} />
        {setup.state === "init" ? (
          <InitStep key="init" setup={setup} onDone={done} />
        ) : (
          <RemoteStep key={setup.state} setup={setup} onDone={done} />
        )}
      </section>
      {setup.state !== "init" && setup.identity === null && <IdentityCard setup={setup} onSaved={done} />}
    </>
  );
}
