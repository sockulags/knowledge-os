"""``GET /p/{project_id}`` -- a project's overview plus content grouped by
meaning: governing now, proposed, historical, observations, raw material,
and a side group of general knowledge, memory, and skills that does not
belong to the project. The project's own ordinary content is reachable
through a directory tree that follows the accepted
``project-directory-layout`` decision, kept separate from the meaning
groups so nothing is shown twice.

All of the actual bucketing lives in ``grouping.py`` (pure, no I/O, no
``knowledge_os.*`` import) so it is directly unit-testable; this module only
resolves display strings against ``Library`` data (replacement titles/dates
for a superseded record, trust labels, ``content_sha256``) and renders the
template.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import language, strings
from ..app import get_library, render
from ..grouping import (
    ProjectGroups,
    ProjectTreeNode,
    build_project_tree,
    group_project_records,
    related_general_records,
)
from ..library import Library, Record, content_sha256

#: Thin wrappers over ``language.py``'s consolidated translation rules
#: (task 3): the meaning-facing status sentence for a decision or an
#: ordinary durable record, and the single accent badge a record card
#: shows. ``language.record_accent`` also folds this view's own discovery
#: rule ("raw unless retained") into the one rule ``language.py`` settled
#: on (see that module's docstring) -- a deliberate behaviour change, but
#: not one any test in this suite pinned.
_badge_class = language.record_accent


def _status_text(record: Record, library: Library) -> str:
    sentence, _accent = language.status_sentence(library, record)
    return sentence


def _observation_text(record: Record) -> str:
    return strings.DISCOVERY_STATUS.get(record.status, strings.PROJECT_STATUS_UNKNOWN)


def _raw_material_text(record: Record) -> str:
    # Goes through language.trust_sentence rather than a bare
    # strings.TRUST_LABELS lookup so a verified raw-material record's
    # "{date}" placeholder is filled in (sources are never verified in
    # practice, so this previously latent gap never surfaced).
    sentence, _accent = language.trust_sentence(record)
    return sentence


def _entry(record: Record, text: str) -> dict[str, object]:
    accent = _badge_class(record)
    return {
        "record": record,
        "text": text,
        "badge_class": f"badge--{accent}" if accent else None,
        "badge_label": strings.PROJECT_BADGE_LABELS.get(accent) if accent else None,
    }


def _decision_entries(records: tuple[Record, ...], library: Library) -> list[dict[str, object]]:
    return [_entry(record, _status_text(record, library)) for record in records]


def _observation_entries(records: tuple[Record, ...]) -> list[dict[str, object]]:
    return [_entry(record, _observation_text(record)) for record in records]


def _raw_material_entries(records: tuple[Record, ...]) -> list[dict[str, object]]:
    return [_entry(record, _raw_material_text(record)) for record in records]


def _tree_has_content(node: ProjectTreeNode) -> bool:
    return not node.is_empty()


async def view(request: Request) -> Response:
    library: Library = get_library(request)
    project_id = request.path_params["project_id"]
    groups: ProjectGroups = group_project_records(library.records, project_id)

    if groups.overview is None:
        return render(
            request,
            "project.html",
            page_title=strings.PAGE_TITLES["project"],
            found=False,
            project_id=project_id,
            library=library,
            status_code=404,
        )

    overview = groups.overview

    governing = _decision_entries(groups.governing, library)
    proposed = _decision_entries(groups.proposed, library)
    historical = _decision_entries(groups.historical, library)
    observations = _observation_entries(groups.observations)
    raw_material = _raw_material_entries(groups.raw_material)

    general_records = related_general_records(library.records)
    related_general = [_entry(record, _status_text(record, library)) for record in general_records]

    tree = build_project_tree(project_id, groups.ordinary, library.broken)

    overview_status_text = _status_text(overview, library)
    # Sec.5: the technical-details disclosure holds *exact* contract
    # vocabulary (status, scope, trust label, path, content_sha256) -- the
    # friendly overview_status_text above is what the reading path shows.
    overview_details = {
        "status": overview.status,
        "scope": overview.scope,
        "trust_label": overview.trust_label,
        "path": overview.path,
        "content_sha256": content_sha256(overview.abs_path),
    }

    return render(
        request,
        "project.html",
        page_title=overview.title,
        found=True,
        project_id=project_id,
        overview=overview,
        overview_status_text=overview_status_text,
        overview_details=overview_details,
        groups=groups,
        governing=governing,
        proposed=proposed,
        historical=historical,
        observations=observations,
        raw_material=raw_material,
        related_general=related_general,
        related_skills=library.skills,
        tree=tree,
        tree_has_content=_tree_has_content(tree),
        library=library,
    )
