"""Local semantic search next to full-text search (issue #102).

A small multilingual embedding model (``MODEL``, see the decision
``local-semantic-search``) turns each page, cut into passages, into a vector;
a query is embedded the same way and compared with every passage. Everything
runs on this computer, with no network once the model is installed.

- **The model** is downloaded once, on request, from this project's GitHub
  release that mirrors it (``.github/workflows/mirror-model.yml``). Every file
  is checked against its pinned sha256 before anything is kept, written to a
  staging folder, and renamed into place, so a folder that exists is a whole
  install. It lives outside any knowledge base, in ``models_root()``.
- **The index** is ``indexes/semantic.sqlite3``, disposable like the FTS
  catalog: one row per passage with its text hash and vector. Rebuilding reuses
  the vector of every passage whose text did not change, so only new or edited
  passages are embedded. It is written to a temporary file and renamed.
- **Search** is always best effort: without the model or the index, callers get
  no semantic results and full-text search works as before.

The optional runtime (``onnxruntime``, ``tokenizers``, ``numpy``) is the
``search`` extra; it is imported only when a model is used.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import sys
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .model import Document
from .workspace import Workspace


class SemanticError(RuntimeError):
    """The model or the semantic index cannot be used; full-text search still works."""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    #: The Hugging Face repository and commit the mirrored files come from.
    source: str
    revision: str
    #: Where the mirrored files are published, and each file's sha256.
    base_url: str
    files: dict[str, str]
    onnx_file: str
    tokenizer_file: str
    pooling: str  # "cls" or "mean"
    dimensions: int
    max_tokens: int
    query_prefix: str = ""
    passage_prefix: str = ""
    #: A passage counts as a match when its score stands at least this far above
    #: the median score of every passage for the query (see tooling/eval_search_models.py).
    min_margin: float = 0.11
    #: The download size of ``files`` together, for progress and the "about N MB" label.
    total_bytes: int = 0

    @property
    def key(self) -> str:
        return f"{self.name}-{self.revision[:12]}"

    @property
    def size(self) -> str:
        return f"about {round(self.total_bytes / 1e7) * 10} MB"


MODEL = ModelSpec(
    name="bge-m3",
    source="https://huggingface.co/Xenova/bge-m3",
    revision="4de13258303883538bd53b696b452bf8099f0858",
    base_url="https://github.com/sockulags/knowledge-os/releases/download/model-bge-m3-4de132583038",
    files={
        "onnx--model_quantized.onnx": "0826f8c1ab9edf1801db86c61919d4d108e8bfc0b809ec823ad366882ff0b77d",
        "tokenizer.json": "6710678b12670bc442b99edc952c4d996ae309a7020c1fa0096dd245c2faf790",
        "config.json": "734a79bf12d388c1467a4e3ab625f45de7f6906cffcfb93a1eca1787504bed95",
    },
    onnx_file="onnx--model_quantized.onnx",
    tokenizer_file="tokenizer.json",
    pooling="cls",
    dimensions=1024,
    max_tokens=512,
    total_bytes=569_694_530 + 17_082_821 + 770,
)

MARKER = ".complete"
INDEX_FILE = "semantic.sqlite3"
PASSAGE_CHARS = 1500
EMBED_BATCH = 8


# ---------------------------------------------------------------------------
# The model on this computer
# ---------------------------------------------------------------------------


def models_root(env: dict[str, str] | None = None) -> Path:
    """Where models are kept: ``KOS_MODELS_DIR``, else the user's cache folder."""

    env = dict(os.environ) if env is None else env
    if env.get("KOS_MODELS_DIR"):
        return Path(env["KOS_MODELS_DIR"]).expanduser()
    if sys.platform == "win32" and env.get("LOCALAPPDATA"):
        return Path(env["LOCALAPPDATA"]) / "knowledge-os" / "models"
    cache = env.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "knowledge-os" / "models"


def model_dir(spec: ModelSpec | None = None, root: Path | None = None) -> Path:
    spec = spec or MODEL
    return (root or models_root()) / spec.key


def is_installed(spec: ModelSpec | None = None, root: Path | None = None) -> bool:
    spec = spec or MODEL
    folder = model_dir(spec, root)
    return (folder / MARKER).is_file() and all((folder / name).is_file() for name in spec.files)


def runtime_available() -> bool:
    """Whether the optional search runtime (the ``search`` extra) is installed."""

    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        return False
    return True


def _download(url: str, destination: Path, expected: str, progress: Callable[[int], None] | None) -> None:
    if not url.startswith("https://"):
        raise SemanticError(f"refusing a model file that is not served over https: {url}")
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as out:  # noqa: S310
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                out.write(chunk)
                if progress:
                    progress(len(chunk))
    except OSError as exc:
        raise SemanticError(f"could not download {url}: {exc}") from exc
    if digest.hexdigest() != expected:
        raise SemanticError(f"{destination.name} does not match its pinned sha256; nothing was installed")


def install_model(
    spec: ModelSpec | None = None,
    root: Path | None = None,
    *,
    progress: Callable[[int], None] | None = None,
    fetch: Callable[[str, Path, str, Callable[[int], None] | None], None] = _download,
) -> Path:
    """Download and check every file of ``spec``; returns the installed folder."""

    spec = spec or MODEL

    target = model_dir(spec, root)
    if is_installed(spec, root):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{spec.key}.staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    try:
        for name, expected in spec.files.items():
            fetch(f"{spec.base_url}/{name}", staging / name, expected, progress)
        (staging / MARKER).write_text(spec.revision + "\n", encoding="utf-8")
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    # Earlier versions of the same model are no longer used.
    for other in target.parent.glob(f"{spec.name}-*"):
        if other != target and other.is_dir():
            shutil.rmtree(other, ignore_errors=True)
    return target


def remove_model(spec: ModelSpec | None = None, root: Path | None = None) -> None:
    spec = spec or MODEL
    shutil.rmtree(model_dir(spec, root), ignore_errors=True)


class Embedder:
    """The model loaded for embedding (onnxruntime on the CPU)."""

    def __init__(self, spec: ModelSpec | None = None, root: Path | None = None) -> None:
        spec = spec or MODEL
        if not is_installed(spec, root):
            raise SemanticError("the search model is not installed")
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise SemanticError("the search runtime is not installed (the 'search' extra)") from exc
        folder = model_dir(spec, root)
        self.spec = spec
        self._np = np
        self._tokenizer = Tokenizer.from_file(str(folder / spec.tokenizer_file))
        self._tokenizer.enable_truncation(spec.max_tokens)
        self._tokenizer.enable_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) // 2))
        self._session = ort.InferenceSession(
            str(folder / spec.onnx_file), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {item.name for item in self._session.get_inputs()}
        self._lock = threading.Lock()

    def embed(self, texts: Sequence[str]) -> Any:
        """Unit-length float32 vectors, one row per text."""

        np = self._np
        rows = []
        for start in range(0, len(texts), EMBED_BATCH):
            encoded = self._tokenizer.encode_batch(list(texts[start : start + EMBED_BATCH]))
            ids = np.array([item.ids for item in encoded], dtype=np.int64)
            mask = np.array([item.attention_mask for item in encoded], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            with self._lock:
                hidden = self._session.run(None, feed)[0]
            if self.spec.pooling == "cls":
                vectors = hidden[:, 0]
            else:
                vectors = (hidden * mask[..., None]).sum(1) / mask.sum(1, keepdims=True)
            vectors = vectors.astype(np.float32)
            rows.append(vectors / np.linalg.norm(vectors, axis=1, keepdims=True))
        return np.concatenate(rows) if rows else np.zeros((0, self.spec.dimensions), dtype=np.float32)

    def embed_query(self, text: str) -> Any:
        return self.embed([self.spec.query_prefix + text])[0]

    def embed_passages(self, texts: Sequence[str]) -> Any:
        return self.embed([self.spec.passage_prefix + text for text in texts])


_embedder: Embedder | None = None
_embedder_lock = threading.Lock()


def shared_embedder() -> Embedder | None:
    """The process's embedder, loaded once (several seconds); None without
    the model or runtime."""

    global _embedder
    with _embedder_lock:
        if _embedder is None and is_installed() and runtime_available():
            try:
                _embedder = Embedder()
            except SemanticError:
                return None
        return _embedder


def loaded_embedder() -> Embedder | None:
    """The process's embedder if it is already loaded; never waits for it."""

    return _embedder


def preload_in_background() -> bool:
    """Load the embedder in a thread so the first search does not wait for it;
    returns whether there is a model to load."""

    if _embedder is not None or not (is_installed() and runtime_available()):
        return _embedder is not None
    threading.Thread(target=shared_embedder, name="kos-semantic-load", daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Installing from a running core
# ---------------------------------------------------------------------------


@dataclass
class InstallState:
    running: bool = False
    done_bytes: int = 0
    error: str | None = None


_install = InstallState()
_install_lock = threading.Lock()


def install_state() -> InstallState:
    with _install_lock:
        return InstallState(_install.running, _install.done_bytes, _install.error)


def install_in_background(after: Callable[[], None] | None = None) -> bool:
    """Start installing ``MODEL`` in a thread (see ``install_state``), then load
    it and call ``after``; returns whether an install is running."""

    if is_installed():
        return False
    with _install_lock:
        if _install.running:
            return True
        _install.running, _install.done_bytes, _install.error = True, 0, None

    def progress(count: int) -> None:
        with _install_lock:
            _install.done_bytes += count

    def run() -> None:
        try:
            install_model(progress=progress)
        except Exception as exc:
            with _install_lock:
                _install.running, _install.error = False, str(exc) or type(exc).__name__
            return
        with _install_lock:
            _install.running = False
        shared_embedder()
        if after is not None:
            after()

    threading.Thread(target=run, name="kos-semantic-install", daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Passages
# ---------------------------------------------------------------------------

_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")


def _plain(text: str) -> str:
    return _LINK.sub(r"\1", text).replace("**", "").replace("__", "").strip()


def passages(title: str, body: str, limit: int = PASSAGE_CHARS) -> list[str]:
    """A page as passages of at most ``limit`` characters, each starting with the
    page title and the heading it is under, split at blank lines."""

    blocks: list[tuple[str, str]] = []
    heading = ""
    in_fence = False
    for block in re.split(r"\n\s*\n", body):
        stripped = block.strip()
        if not stripped:
            continue
        # A heading inside a fenced code block is code, not a heading.
        was_in_fence = in_fence
        if (stripped.count("```") + stripped.count("~~~")) % 2 == 1:
            in_fence = not in_fence
        match = re.match(r"^#{1,6}\s+(.+)$", stripped.splitlines()[0])
        if match and not was_in_fence:
            # A page's own H1 repeats its title, which every passage already starts with.
            heading = "" if match.group(1).strip() == title.strip() else match.group(1).strip()
            rest = "\n".join(stripped.splitlines()[1:]).strip()
            if not rest:
                continue
            stripped = rest
        blocks.append((heading, _plain(stripped)))

    result: list[str] = []
    current_heading: str | None = None
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            prefix = f"{title}\n{current_heading}\n" if current_heading else f"{title}\n"
            result.append(prefix + current.strip())
        current = ""

    for block_heading, text in blocks:
        if block_heading != current_heading or len(current) + len(text) + 2 > limit:
            flush()
            current_heading = block_heading
        while len(text) > limit:  # one very long paragraph, cut at a space
            cut = text.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            current = text[:cut]
            flush()
            text = text[cut:].lstrip()
        current = f"{current}\n\n{text}" if current else text
    flush()
    return result or [title]


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------


def index_path(workspace: Workspace) -> Path:
    path = workspace.root / "indexes" / INDEX_FILE
    workspace.assert_safe_path(path)
    return path


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _wanted(documents: Iterable[Document]) -> list[tuple[str, int, str]]:
    rows = []
    for document in documents:
        if document.metadata["type"] == "source":
            continue  # raw material stays out of search, as in context
        for ordinal, text in enumerate(passages(str(document.metadata["title"]), document.body)):
            rows.append((str(document.metadata["id"]), ordinal, text))
    return rows


def _existing(path: Path, spec: ModelSpec) -> dict[str, bytes]:
    if not path.is_file():
        return {}
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            model = connection.execute("SELECT value FROM meta WHERE key = 'model'").fetchone()
            if model is None or model[0] != spec.key:
                return {}
            return {row[0]: row[1] for row in connection.execute("SELECT text_sha, vector FROM passages")}
        finally:
            connection.close()
    except sqlite3.Error:
        return {}


def update_index(
    workspace: Workspace,
    documents: Sequence[Document],
    embedder: Embedder,
    *,
    source_stamp: str = "",
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    """Bring ``indexes/semantic.sqlite3`` in line with ``documents``, embedding
    only passages whose text is new; returns counts. ``source_stamp`` records
    which catalog it was built from (see ``is_current``)."""

    np = embedder._np
    path = index_path(workspace)
    wanted = _wanted(documents)
    known = _existing(path, embedder.spec)
    missing = sorted({_text_hash(text): text for _, _, text in wanted if _text_hash(text) not in known}.items())
    for start in range(0, len(missing), 32):
        batch = missing[start : start + 32]
        vectors = embedder.embed_passages([text for _, text in batch])
        for (digest, _), vector in zip(batch, vectors):
            known[digest] = np.asarray(vector, dtype=np.float32).tobytes()
        if progress:
            progress(min(start + 32, len(missing)), len(missing))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{INDEX_FILE}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE passages (
                    record_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    text_sha TEXT NOT NULL, text TEXT NOT NULL, vector BLOB NOT NULL
                );
                """
            )
            connection.executemany(
                "INSERT INTO meta VALUES (?, ?)", [("model", embedder.spec.key), ("source", source_stamp)]
            )
            connection.executemany(
                "INSERT INTO passages VALUES (?, ?, ?, ?, ?)",
                [(record_id, ordinal, _text_hash(text), text, known[_text_hash(text)]) for record_id, ordinal, text in wanted],
            )
            connection.commit()
        finally:
            connection.close()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    _cache.clear()
    return {"passages": len(wanted), "embedded": len(missing)}


def catalog_stamp(workspace: Workspace) -> str:
    """Identifies the FTS catalog's current build (rebuilt after every write)."""

    catalog = workspace.root / "indexes" / "catalog.sqlite3"
    try:
        stat = catalog.stat()
    except OSError:
        return ""
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def is_current(workspace: Workspace, spec: ModelSpec | None = None) -> bool:
    """Whether the semantic index was built by ``spec`` from the current catalog."""

    spec = spec or MODEL

    path = index_path(workspace)
    if not path.is_file():
        return False
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return meta.get("model") == spec.key and meta.get("source") == catalog_stamp(workspace)


# Vectors of the index, loaded once per build of the file.
_cache: dict[str, tuple[str, Any, list[tuple[str, str]]]] = {}


def _load(path: Path, np: Any, spec: ModelSpec) -> tuple[Any, list[tuple[str, str]]] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    cached = _cache.get(str(path))
    if cached is not None and cached[0] == stamp:
        return cached[1], cached[2]
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            model = connection.execute("SELECT value FROM meta WHERE key = 'model'").fetchone()
            if model is None or model[0] != spec.key:
                return None
            rows = connection.execute("SELECT record_id, text, vector FROM passages ORDER BY record_id, ordinal").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    if not rows:
        return None
    matrix = np.stack([np.frombuffer(row[2], dtype=np.float32) for row in rows])
    meta = [(row[0], row[1]) for row in rows]
    _cache[str(path)] = (stamp, matrix, meta)
    return matrix, meta


@dataclass(frozen=True)
class Match:
    record_id: str
    score: float
    #: How far above the median passage score it stands.
    margin: float
    passage: str


def search(workspace: Workspace, query: str, embedder: Embedder, limit: int = 20) -> list[Match]:
    """Pages whose best passage matches ``query`` clearly better than most, best first."""

    np = embedder._np
    loaded = _load(index_path(workspace), np, embedder.spec)
    if loaded is None or not query.strip():
        return []
    matrix, meta = loaded
    scores = matrix @ embedder.embed_query(query.strip())
    median = float(np.median(scores))
    best: dict[str, Match] = {}
    for position in np.argsort(-scores):
        margin = float(scores[position]) - median
        if margin < embedder.spec.min_margin:
            break
        record_id, text = meta[position]
        if record_id not in best:
            best[record_id] = Match(record_id, float(scores[position]), margin, text)
            if len(best) >= limit:
                break
    return list(best.values())


# ---------------------------------------------------------------------------
# Keeping it current in a running core
# ---------------------------------------------------------------------------

_refreshing: set[str] = set()
_refresh_lock = threading.Lock()


def refresh_in_background(workspace: Workspace, load_documents: Callable[[], Sequence[Document]]) -> bool:
    """Start updating the index in a thread when it is behind the catalog;
    returns whether an update is running. Search never waits for it."""

    if not (is_installed() and runtime_available()) or is_current(workspace):
        return False
    key = str(workspace.root)
    with _refresh_lock:
        if key in _refreshing:
            return True
        _refreshing.add(key)

    def run() -> None:
        try:
            embedder = shared_embedder()
            if embedder is None:
                return
            stamp = catalog_stamp(workspace)
            update_index(workspace, load_documents(), embedder, source_stamp=stamp)
        except Exception:  # a failed refresh leaves the previous index; the next search tries again
            pass
        finally:
            with _refresh_lock:
                _refreshing.discard(key)

    threading.Thread(target=run, name="kos-semantic-index", daemon=True).start()
    return True


def refreshing(workspace: Workspace) -> bool:
    with _refresh_lock:
        return str(workspace.root) in _refreshing


# ---------------------------------------------------------------------------
# Combining with full-text search
# ---------------------------------------------------------------------------

#: Reciprocal rank fusion's damping constant (the usual value).
RRF_K = 60


def fuse(text_ids: Sequence[str], matches: Sequence[Match], limit: int) -> list[tuple[str, str]]:
    """Merge full-text hits (best first) with semantic ``matches`` by reciprocal
    rank fusion; returns ``(record_id, how)`` best first, where ``how`` is
    ``"text"``, ``"meaning"``, or ``"both"``. On equal scores a full-text hit
    comes first, so an exact hit is never pushed below a match by meaning of
    the same rank."""

    scores: dict[str, float] = {}
    how: dict[str, str] = {}
    for rank, record_id in enumerate(text_ids):
        if record_id in how:
            continue
        scores[record_id] = 1 / (RRF_K + rank + 1) + 1e-9
        how[record_id] = "text"
    for rank, match in enumerate(matches):
        scores[match.record_id] = scores.get(match.record_id, 0.0) + 1 / (RRF_K + rank + 1)
        how[match.record_id] = "both" if how.get(match.record_id) == "text" else "meaning"
    order = sorted(scores, key=lambda record_id: -scores[record_id])
    return [(record_id, how[record_id]) for record_id in order[: max(limit, 0)]]


def passage_snippet(passage: str, limit: int = 220) -> str:
    """The text of a matched passage without the title and heading lines it
    starts with, cut at a word to about ``limit`` characters."""

    lines = passage.split("\n")
    body = " ".join(" ".join(lines[1:]).split()) if len(lines) > 1 else " ".join(passage.split())
    if len(body) <= limit:
        return body
    cut = body.rfind(" ", 0, limit)
    return body[: cut if cut > limit // 2 else limit] + " ..."
