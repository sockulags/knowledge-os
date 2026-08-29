"""The ``kos`` command line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .context import ContextRequest, build_context
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
from .model import MetadataError
from .workspace import Workspace, WorkspaceError, validate_workspace


def _root_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="workspace root (default: discover from cwd)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kos", description="Knowledge OS local knowledge tools")
    _root_option(parser)
    commands = parser.add_subparsers(dest="command", required=True)

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

    context = commands.add_parser("context", help="export a deterministic Markdown context package")
    context.add_argument("--project", required=True, help="project ID")
    context.add_argument("--task", required=True, help="task description")
    context.add_argument("--work-item", help="optional work-item description")
    context.add_argument("--budget", required=True, type=int, help="maximum estimated tokens")
    _root_option(context)

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
        "provenance": document.metadata["provenance"],
        "excerpt": " ".join(document.body.strip().split())[:600],
    }
    if full:
        result["content"] = document.body
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
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
                        f"{result['status']}\t{result['scope']}\t{result['path']}\t{result['snippet']}"
                    )
            return 0
        if args.command == "inspect":
            return _inspect(workspace, args.id, args.full)
        if args.command == "context":
            package = build_context(
                ContextRequest(
                    project=args.project,
                    task=args.task,
                    work_item=args.work_item,
                    budget=args.budget,
                ),
                workspace,
            )
            _write_stdout(package)
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
    except (MetadataError, WorkspaceError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 2
