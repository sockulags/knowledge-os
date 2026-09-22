"""The ``kos`` command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .capture import capture_record
from .context import ContextRequest, build_context
from .context_policy import trust_label
from .context_verify import verify_context_package
from .documentation_init import DocumentationInitError, init_global, init_repo
from .init_workspace import init_workspace
from .discovery import (
    add_discovery,
    inspect_discovery,
    promote_discovery,
    reject_discovery,
    retain_discovery,
    review_packet,
)
from .index import rebuild_indexes, search_index
from .ingest import ingest_source
from .model import MetadataError, content_sha256
from .mutations import accept_decision, supersede_decision, update_record, withdraw_decision
from .workspace import Workspace, WorkspaceError, validate_workspace


def _root_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="workspace root (default: discover from cwd)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kos", description="Knowledge OS local knowledge tools")
    _root_option(parser)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a new, empty, valid workspace")
    init.add_argument("path", type=Path, help="folder to create the workspace in")
    init.add_argument("--name", help="workspace name (default: derived from the folder name)")
    init.add_argument("--json", action="store_true", dest="as_json")

    ingest = commands.add_parser("ingest", help="ingest one local Markdown or text file")
    ingest.add_argument("path", type=Path)
    _root_option(ingest)

    index = commands.add_parser("index", help="validate and rebuild the indexes")
    _root_option(index)

    lint = commands.add_parser("lint", help="validate all managed records")
    _root_option(lint)

    search = commands.add_parser("search", help="search the existing FTS index")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--json", action="store_true", dest="as_json")
    _root_option(search)

    inspect = commands.add_parser("inspect", help="inspect one record")
    inspect.add_argument("id")
    inspect.add_argument("--full", action="store_true")
    _root_option(inspect)

    context = commands.add_parser("context", help="export or verify a deterministic Markdown context package")
    context.add_argument("context_action", nargs="?", choices=("verify",))
    context.add_argument("package", nargs="?", type=Path, help="package path for context verify")
    context.add_argument("--project", help="project ID")
    context.add_argument("--task", help="task description")
    context.add_argument("--work-item", help="optional work-item description")
    context.add_argument("--budget", type=int, help="maximum estimated tokens")
    context.add_argument("--require", action="append", default=[], dest="required_ids", help="mandatory record ID")
    context.add_argument("--json", action="store_true", dest="as_json", help="JSON output for context verify")
    _root_option(context)

    capture = commands.add_parser("capture", help="create one approved durable record")
    capture.add_argument("path", type=Path, help="approved candidate Markdown record")
    capture.add_argument(
        "--project-path",
        type=Path,
        help="optional path below projects/<project-id>/ for a project record",
    )
    capture.add_argument("--json", action="store_true", dest="as_json")
    _root_option(capture)

    update = commands.add_parser("update", help="conflict-safe editorial or evidence update")
    update.add_argument("path", type=Path, help="complete replacement Markdown record")
    update.add_argument("--expected-sha256", required=True)
    update.add_argument("--confirm-non-material", action="store_true")
    update.add_argument("--change-reference")
    update.add_argument("--json", action="store_true", dest="as_json")
    _root_option(update)

    decision = commands.add_parser("decision", help="accept a proposed decision")
    _root_option(decision)
    decision_commands = decision.add_subparsers(dest="decision_command", required=True)
    decision_accept = decision_commands.add_parser("accept", help="make a draft decision active")
    decision_accept.add_argument("id")
    decision_accept.add_argument("--expected-sha256", required=True)
    decision_accept.add_argument("--acceptance-reference", required=True)
    decision_accept.add_argument("--json", action="store_true", dest="as_json")
    _root_option(decision_accept)
    decision_withdraw = decision_commands.add_parser(
        "withdraw", help="archive a draft decision that will not be accepted"
    )
    decision_withdraw.add_argument("id")
    decision_withdraw.add_argument("--expected-sha256", required=True)
    decision_withdraw.add_argument("--reason", required=True)
    decision_withdraw.add_argument("--json", action="store_true", dest="as_json")
    _root_option(decision_withdraw)

    supersede = commands.add_parser("supersede", help="activate a draft replacement and retire its prior decision")
    supersede.add_argument("old_id")
    supersede.add_argument("new_id")
    supersede.add_argument("--expected-old-sha256", required=True)
    supersede.add_argument("--expected-new-sha256", required=True)
    supersede.add_argument("--acceptance-reference", required=True)
    supersede.add_argument("--json", action="store_true", dest="as_json")
    _root_option(supersede)

    discovery = commands.add_parser("discovery", help="record, review, and promote discoveries")
    _root_option(discovery)
    discovery_commands = discovery.add_subparsers(dest="discovery_command", required=True)

    discovery_add = discovery_commands.add_parser("add", help="add a proposed structured discovery")
    discovery_add.add_argument("path", type=Path)
    _root_option(discovery_add)

    discovery_inspect = discovery_commands.add_parser("inspect", help="inspect one discovery")
    discovery_inspect.add_argument("id")
    _root_option(discovery_inspect)

    discovery_review = discovery_commands.add_parser("review", help="render a read-only discovery review packet")
    discovery_review.add_argument("id")
    _root_option(discovery_review)

    discovery_retain = discovery_commands.add_parser("retain", help="retain a project-scoped discovery")
    discovery_retain.add_argument("id")
    discovery_retain.add_argument("--reviewer")
    discovery_retain.add_argument("--reason")
    _root_option(discovery_retain)

    discovery_reject = discovery_commands.add_parser("reject", help="reject a discovery with a reason")
    discovery_reject.add_argument("id")
    discovery_reject.add_argument("--reason")
    discovery_reject.add_argument("--reviewer")
    _root_option(discovery_reject)

    discovery_promote = discovery_commands.add_parser("promote", help="promote a discovery into a new draft record")
    discovery_promote.add_argument("id")
    discovery_promote.add_argument("--target-id")
    discovery_promote.add_argument("--title")
    discovery_promote.add_argument("--scope")
    discovery_promote.add_argument("--reviewer")
    discovery_promote.add_argument("--reason")
    discovery_promote.add_argument("--acknowledge-related", action="store_true")
    discovery_promote.add_argument("--allow-scope-broadening", action="store_true")
    _root_option(discovery_promote)

    documentation = commands.add_parser("documentation", help="initialize Knowledge OS documentation integration")
    documentation_commands = documentation.add_subparsers(dest="documentation_command", required=True)

    init_global_parser = documentation_commands.add_parser("init-global", help="initialize global harness configuration")
    init_global_parser.add_argument("--workspace", required=True, type=Path)
    init_global_parser.add_argument("--host", action="append", choices=("codex", "claude"))
    init_global_parser.add_argument("--user-home", type=Path)
    init_global_parser.add_argument("--replace", action="store_true")
    init_global_parser.add_argument("--json", action="store_true", dest="as_json")

    init_repo_parser = documentation_commands.add_parser("init-repo", help="initialize a repository project binding")
    init_repo_parser.add_argument("--repo", required=True, type=Path)
    init_repo_parser.add_argument("--project", action="append", required=True)
    init_repo_parser.add_argument("--user-home", type=Path)
    init_repo_parser.add_argument("--replace", action="store_true")
    init_repo_parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _workspace(args: argparse.Namespace) -> Workspace:
    return Workspace.discover(getattr(args, "root", None))


def _write_stdout(text: str) -> None:
    stdout_buffer = getattr(sys.stdout, "buffer", None)
    if stdout_buffer is None:
        sys.stdout.write(text)
    else:
        stdout_buffer.write(text.encode("utf-8"))


def _lint(workspace: Workspace) -> int:
    documents, issues = validate_workspace(workspace)
    if issues:
        for issue in issues:
            print(f"ERROR {issue.path}: {issue.message}", file=sys.stderr)
        print(f"Lint failed: {len(issues)} issue(s)", file=sys.stderr)
        return 1
    print(f"Lint OK: {len(documents)} managed record(s)")
    return 0


def _inspect(workspace: Workspace, record_id: str, full: bool) -> int:
    documents, issues = validate_workspace(workspace)
    if issues:
        raise ValueError("cannot inspect an invalid corpus; run 'kos lint' for details")
    document = next((item for item in documents if item.metadata["id"] == record_id), None)
    if document is None:
        raise ValueError(f"record not found: {record_id}")
    result = {
        "id": document.metadata["id"],
        "title": document.metadata["title"],
        "type": document.metadata["type"],
        "status": document.metadata["status"],
        "scope": document.metadata["scope"],
        "path": workspace.relative(document.path),
        "content_sha256": content_sha256(document.path),
        "provenance": document.metadata["provenance"],
        "excerpt": " ".join(document.body.strip().split())[:600],
        "trust": trust_label(document),
    }
    if document.metadata["type"] in {"knowledge", "project"}:
        result["record_kind"] = document.metadata.get("record_kind", "ordinary")
    if "verified" in document.metadata:
        verified = document.metadata["verified"]
        result["verified"] = verified.isoformat() if hasattr(verified, "isoformat") else verified
    if full:
        result["content"] = document.body
    print(json.dumps(result, ensure_ascii=False, indent=2, default=lambda value: value.isoformat()))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "documentation":
            if args.documentation_command == "init-global":
                result = init_global(
                    args.workspace,
                    hosts=args.host,
                    user_home=args.user_home,
                    replace=args.replace,
                )
            else:
                result = init_repo(
                    args.repo,
                    args.project,
                    user_home=args.user_home,
                    replace=args.replace,
                )
            if args.as_json:
                print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            else:
                print(f"Initialized {args.documentation_command}: {len(result['changed_paths'])} file(s) changed")
            return 0
        if args.command == "init":
            created = init_workspace(args.path, name=args.name)
            if args.as_json:
                print(json.dumps({"root": str(created)}, ensure_ascii=False, sort_keys=True))
            else:
                print(f"Initialized workspace at {created}")
            return 0
        workspace = _workspace(args)
        if args.command == "lint":
            return _lint(workspace)
        if args.command == "index":
            count = rebuild_indexes(workspace)
            print(f"Index refreshed: {count} record(s); catalog.md and catalog.sqlite3 rebuilt")
            return 0
        if args.command == "ingest":
            record_id, created, count = ingest_source(workspace, args.path)
            action = "Ingested" if created else "Already ingested"
            print(f"{action} {record_id}")
            print(f"Index refreshed: {count} record(s)")
            return 0
        if args.command == "search":
            if args.limit < 1:
                raise ValueError("--limit must be at least 1")
            results = search_index(workspace, args.query, args.limit)
            if args.as_json:
                print(json.dumps(results, ensure_ascii=False))
            else:
                for result in results:
                    print(
                        f"{result['id']}\t{result['title']}\t{result['type']}\t"
                        f"{result['record_kind']}\t{result['status']}\t{result['scope']}\t"
                        f"{result['path']}\t{result['snippet']}"
                    )
            return 0
        if args.command == "inspect":
            return _inspect(workspace, args.id, args.full)
        if args.command == "context":
            if args.context_action == "verify":
                if args.package is None:
                    raise ValueError("context verify requires a package path")
                if any((args.project, args.task, args.work_item, args.budget, args.required_ids)):
                    raise ValueError("context export options are not valid with 'context verify'")
                report = verify_context_package(workspace, args.package)
                if args.as_json:
                    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
                else:
                    print(f"Workspace: {'unchanged' if report['workspace']['matches'] else 'changed'}")
                    for item in report["items"]:
                        print(f"{item['id']}\t{item['status']}")
                return 0 if report["ok"] else 1
            if args.package is not None:
                raise ValueError("context package path is only valid with 'context verify'")
            if args.as_json:
                raise ValueError("--json is only valid with 'context verify'")
            if args.project is None or args.task is None or args.budget is None:
                raise ValueError("context export requires --project, --task, and --budget")
            package = build_context(
                ContextRequest(
                    project=args.project,
                    task=args.task,
                    work_item=args.work_item,
                    budget=args.budget,
                    required_ids=tuple(args.required_ids),
                ),
                workspace,
            )
            _write_stdout(package)
            return 0
        if args.command == "capture":
            result = capture_record(workspace, args.path, project_path=args.project_path)
            if args.as_json:
                print(
                    json.dumps(
                        {
                            "id": result.id,
                            "type": result.type,
                            "scope": result.scope,
                            "path": result.path,
                            "status": result.status,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            else:
                print(f"Captured {result.id} ({result.type}, {result.scope}, {result.status})")
                print(f"Index refreshed: {result.index_count} record(s)")
            return 0
        if args.command == "update":
            result = update_record(
                workspace,
                args.path,
                expected_sha256=args.expected_sha256,
                confirm_non_material=args.confirm_non_material,
                change_reference=args.change_reference,
            )
            payload = {
                "id": result.id,
                "path": result.path,
                "sha256": result.sha256,
                "status": result.status,
            }
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                print(f"Updated {result.id} ({result.status})")
                print(f"SHA-256: {result.sha256}")
                print(f"Index refreshed: {result.index_count} record(s)")
            return 0
        if args.command == "decision" and args.decision_command == "accept":
            result = accept_decision(
                workspace,
                args.id,
                expected_sha256=args.expected_sha256,
                acceptance_reference=args.acceptance_reference,
            )
            payload = {
                "id": result.id,
                "path": result.path,
                "sha256": result.sha256,
                "status": result.status,
            }
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                print(f"Accepted decision {result.id}")
                print(f"SHA-256: {result.sha256}")
                print(f"Index refreshed: {result.index_count} record(s)")
            return 0
        if args.command == "decision" and args.decision_command == "withdraw":
            result = withdraw_decision(
                workspace,
                args.id,
                expected_sha256=args.expected_sha256,
                reason=args.reason,
            )
            payload = {
                "id": result.id,
                "path": result.path,
                "sha256": result.sha256,
                "status": result.status,
            }
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                print(f"Withdrew decision {result.id}")
                print(f"SHA-256: {result.sha256}")
                print(f"Index refreshed: {result.index_count} record(s)")
            return 0
        if args.command == "supersede":
            result = supersede_decision(
                workspace,
                args.old_id,
                args.new_id,
                expected_old_sha256=args.expected_old_sha256,
                expected_new_sha256=args.expected_new_sha256,
                acceptance_reference=args.acceptance_reference,
            )
            payload = {
                "new_id": result.new_id,
                "new_sha256": result.new_sha256,
                "new_status": result.new_status,
                "old_id": result.old_id,
                "old_sha256": result.old_sha256,
                "old_status": result.old_status,
            }
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                print(f"Superseded {result.old_id} with accepted decision {result.new_id}")
                print(f"Index refreshed: {result.index_count} record(s)")
            return 0
        if args.command == "discovery":
            if args.discovery_command == "add":
                record_id, created, count = add_discovery(workspace, args.path)
                action = "Added" if created else "Already present"
                print(f"{action} discovery {record_id}")
                print(f"Index refreshed: {count} record(s)")
                return 0
            if args.discovery_command == "inspect":
                print(inspect_discovery(workspace, args.id))
                return 0
            if args.discovery_command == "review":
                _write_stdout(review_packet(workspace, args.id))
                return 0
            if args.discovery_command == "retain":
                status, count = retain_discovery(
                    workspace,
                    args.id,
                    reviewer=args.reviewer,
                    reason=args.reason,
                )
                print(f"Discovery {args.id} is now {status}")
                print(f"Index refreshed: {count} record(s)")
                return 0
            if args.discovery_command == "reject":
                status, count = reject_discovery(
                    workspace,
                    args.id,
                    reason=args.reason,
                    reviewer=args.reviewer,
                )
                print(f"Discovery {args.id} is now {status}")
                print(f"Index refreshed: {count} record(s)")
                return 0
            if args.discovery_command == "promote":
                target_id, count, related_ids = promote_discovery(
                    workspace,
                    args.id,
                    target_id=args.target_id,
                    title=args.title,
                    scope=args.scope,
                    reviewer=args.reviewer,
                    reason=args.reason,
                    acknowledge_related=args.acknowledge_related,
                    allow_scope_broadening=args.allow_scope_broadening,
                )
                print(f"Promoted discovery {args.id} to new draft {target_id}")
                if related_ids:
                    print(f"Acknowledged related records: {', '.join(related_ids)}")
                print(f"Index refreshed: {count} record(s)")
                return 0
    except (DocumentationInitError, MetadataError, WorkspaceError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 2
