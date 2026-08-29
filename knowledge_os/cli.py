"""The ``kos`` command line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

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
    return parser


def _workspace(args: argparse.Namespace) -> Workspace:
    return Workspace.discover(getattr(args, "root", None))


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
    except (MetadataError, WorkspaceError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 2
