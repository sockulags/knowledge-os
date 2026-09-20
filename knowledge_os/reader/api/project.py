"""``GET /api/projects/{project_id}`` — "what governs here": the project's
properties, its decisions grouped by meaning (in force / waiting on you /
replaced), its overview body, its full page tree, and its observations,
raw material, and related general knowledge.

All of the bucketing logic lives in ``grouping.py`` (pure, no I/O); this
module only resolves it against ``Library`` data and reshapes it into JSON.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import markdown, strings
from ..app import get_library, json_response, not_found
from ..grouping import ProjectGroups, group_project_records, related_general_records
from ..library import Library, Record, content_sha256, path_index
from .common import (
    breadcrumb_for_record,
    project_tree_json,
    properties_block,
    record_summary_with_sentence,
    technical_details,
)

#: Group slug -> JSON key, in the order the design brief lists them for the
#: project page ("In force now", "Waiting on you", "Replaced").
_GROUP_ORDER = ("governing", "proposed", "historical")


def _group_entries(library: Library, records: tuple[Record, ...]) -> list[dict[str, object]]:
    return [record_summary_with_sentence(library, record) for record in records]


async def view(request: Request) -> Response:
    library: Library = get_library(request)
    project_id = request.path_params["project_id"]
    groups: ProjectGroups = group_project_records(library.records, project_id)

    if groups.overview is None:
        return not_found(strings.PROJECT_NOT_FOUND.format(project_id=project_id))

    overview = groups.overview

    group_json = {
        slug: {
            "header": strings.PROJECT_GROUP_HEADERS[slug],
            "empty_text": strings.PROJECT_GROUP_EMPTY[slug],
            "records": _group_entries(library, getattr(groups, slug)),
        }
        for slug in _GROUP_ORDER
    }

    observations = {
        "header": strings.PROJECT_GROUP_HEADERS["observations"],
        "empty_text": strings.PROJECT_GROUP_EMPTY["observations"],
        "records": [
            {
                **record_summary_with_sentence(library, record),
                "sentence": strings.DISCOVERY_STATUS.get(record.status, strings.PROJECT_STATUS_UNKNOWN),
            }
            for record in groups.observations
        ],
    }
    raw_material = {
        "header": strings.PROJECT_GROUP_HEADERS["raw_material"],
        "empty_text": strings.PROJECT_GROUP_EMPTY["raw_material"],
        "records": [record_summary_with_sentence(library, record) for record in groups.raw_material],
    }

    general_records = related_general_records(library.records)
    related_general = {
        "header": strings.PROJECT_GROUP_HEADERS["related_general"],
        "empty_text": strings.PROJECT_GROUP_EMPTY["related_general"],
        "records": [record_summary_with_sentence(library, record) for record in general_records],
    }
    related_skills = [{"name": skill.name, "description": skill.description} for skill in library.skills]

    # The sidebar/page tree mirrors the whole project directory, decisions
    # included (unlike the meaning groups above, which exist to answer
    # "what governs" -- see api/common.py's project_tree_json docstring).
    all_project_records = [r for r in library.records if r.scope == f"project:{project_id}" and r.id != project_id]
    project_broken = [b for b in library.broken if b.path.startswith(f"projects/{project_id}/")]
    tree = project_tree_json(project_id, all_project_records, project_broken)

    body_html = markdown.render(overview.body, source_path=overview.path, resolve_link=path_index(library).get)
    headings = [h for h in markdown.headings(overview.body) if h[0] <= 3]

    return json_response(
        {
            "id": project_id,
            "title": overview.title,
            "breadcrumb": breadcrumb_for_record(library, overview)[:1],
            "properties": properties_block(library, overview),
            "technical_details": technical_details(overview, content_sha256(overview.abs_path)),
            "groups": group_json,
            "overview_body_html": body_html,
            "overview_headings": headings,
            "tree": tree,
            "observations": observations,
            "raw_material": raw_material,
            "related_general": related_general,
            "related_skills": related_skills,
        }
    )
