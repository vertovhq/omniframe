"""Custom scene components written by the model (design §9 step 5, requirement 11).

A plan scene `{"kind": "custom", "component": "ScoreBoard"}` is drawn by
`<project>/components/ScoreBoard.tsx`. The engine only knows components through
`engine/src/custom/registry.ts`, which is committed as an empty map. For one render:

1. `check_components` (quick, in `render_video` before any job): every named component
   exists, imports only what the contract allows (`engine/src/custom/README.md`), and has
   no network calls. Problems come back as `components/<File>.tsx:<line>: message`.
2. `EngineHold` (in the render job, around the bundling step): takes the engine lock
   (`engine/.render.lock`), copies the components into `engine/src/custom/job/`, writes the
   registry, and typechecks with a temporary tsconfig. Compiler errors are returned to the
   model and nothing is rendered.
3. `release` (as soon as the bundle is built, or on any failure): the committed
   `registry.ts` is written back, `custom/job/` is deleted, the lock is removed. The bundle
   is self-contained, so the engine folder is only needed up to that point.

Every render takes the lock while it bundles, with or without components, so a render
never bundles another render's components.

Style library (task 20.3): a component may also import a saved library entry,
`import Boat from './library/<entry>/<File>'`. The entry lives in `<OMNIFRAME_OUTPUT_DIR>/library/<entry>/`
(`tools/library.py`). Only the files that are imported, and what they import in turn, are copied
into `custom/job/library/<entry>/`; two small re-export files there make the entry's own
`../style` and `../kit` imports resolve, so an entry saved from a project works unchanged.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from ..ffmpeg import NO_WINDOW
from ..jobs import pid_alive
from ..plan import CustomScene, Plan

COMPONENTS_DIR = "components"
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
EXTENSIONS = (".tsx", ".ts")

LIBRARY_DIR = "library"          # folder name under OMNIFRAME_OUTPUT_DIR and, in a render, under custom/job/
# `./library/<entry>/<File>`: a library entry file, imported by a project component.
LIBRARY_IMPORT_RE = re.compile(r"^\./library/(?P<entry>[a-z0-9][a-z0-9-]*)/(?P<file>[A-Za-z][A-Za-z0-9_]*)$")
# Inside job/library/ the entry's own `../style` and `../kit` point here; these files re-export the engine's.
LIBRARY_SHIMS = {
    "style.ts": "export * from '../../style';\n",
    "kit.ts": "export * from '../../kit';\n",
}


class SourceFile(NamedTuple):
    """A file a render needs: where it is, and its path inside `custom/job/` (posix, no leading slash)."""

    path: Path
    rel: str

LOCK_NAME = ".render.lock"
LOCK_WAIT_S = 300.0              # another render is bundling; wait this long for it
LOCK_STALE_S = 2 * 3600.0        # a lock older than this is dropped even if its pid looks alive
TSC_TIMEOUT_S = 180.0
MAX_ERRORS = 25                  # compiler errors returned to the model

# Imports a component may use (engine/src/custom/README.md).
ALLOWED_PACKAGES = ("react", "react/jsx-runtime", "remotion")
STYLE_IMPORT = "../style"
KIT_IMPORT = "../kit"  # the motion kit, engine/src/kit (see engine/src/kit/KIT.md)

# What `engine/src/custom/registry.ts` holds when it is committed. Only used to repair a
# registry left behind by a crashed render; normally the file is restored byte for byte.
EMPTY_REGISTRY = """import type {ComponentType} from 'react';

/**
 * Custom scene components by name, for `{"kind": "custom", "component": "<name>"}`.
 *
 * This committed file is an empty map and must stay that way. `render_video` writes the real
 * map for the duration of one render (see ./README.md) and restores this file afterwards.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const registry: Record<string, ComponentType<any>> = {};
"""

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?<![:\w'\"`])//[^\n]*")
_IMPORT_FROM = re.compile(r"""\b(?:import|export)\b[^'";]*?\bfrom\s*(['"])(?P<spec>[^'"]+)\1""", re.S)
_IMPORT_BARE = re.compile(r"""\bimport\s*(['"])(?P<spec>[^'"]+)\1""")
_IMPORT_DYNAMIC = re.compile(r"\bimport\s*\(")
_REQUIRE = re.compile(r"\brequire\s*\(")
_NETWORK = re.compile(r"\b(fetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon)")
_URL = re.compile(r"https?://(?!www\.w3\.org/)", re.I)
_NONDETERMINISTIC = re.compile(r"\b(Math\.random\s*\(|Date\.now\s*\(|new\s+Date\s*\(|performance\.now\s*\()")
_TSC_LINE = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\): (?P<msg>(?:error|warning) TS\d+: .*)$")


class ComponentError(RuntimeError):
    """The engine could not be prepared for the render (not a problem in the model's code)."""


# ------------------------------------------------------------------ the plan side

def used_components(plan: Plan) -> list[str]:
    """Names of the custom components the scenes use, once each, in order of first use."""
    names: list[str] = []
    for scene in plan.scenes:
        if isinstance(scene, CustomScene) and scene.component not in names:
            names.append(scene.component)
    return names


def _find_in(folder: Path, name: str) -> Path | None:
    for ext in EXTENSIONS:
        cand = folder / f"{name}{ext}"
        if cand.is_file():
            return cand
    return None


def _source_file(project_root: Path, name: str) -> Path | None:
    return _find_in(project_root / COMPONENTS_DIR, name)


def _library_files(library_root: Path | None, entry: str) -> str:
    """The component names of a library entry, for an error message."""
    folder = None if library_root is None else library_root / entry
    if folder is None or not folder.is_dir():
        return "there is no such entry"
    names = sorted({p.stem for p in folder.iterdir() if p.suffix in EXTENSIONS})
    return "the entry has: " + ", ".join(names) if names else "the entry has no component files"


def _strip_comments(text: str) -> str:
    """The code without comments; line numbers stay the same."""
    blank = lambda m: "\n" * m.group().count("\n")  # noqa: E731
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub(blank, text))


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_source(
    path: Path,
    project_root: Path,
    library_root: Path | None = None,
    entry: str | None = None,
) -> tuple[list[str], list[str], list[SourceFile]]:
    """Check one component file against the contract.

    A project component is `<project>/components/<File>`; with `entry` set the file is
    `<library_root>/<entry>/<File>` and `./Name` means a file of the same entry.
    Returns `(errors, warnings, the files it imports)`. Messages read
    `components/<File>:<line>: ...` (`library/<entry>/<File>:<line>: ...` for an entry).
    """
    label = f"{COMPONENTS_DIR}/{path.name}" if entry is None else f"{LIBRARY_DIR}/{entry}/{path.name}"
    errors: list[str] = []
    warnings: list[str] = []
    local: list[SourceFile] = []
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{label}: cannot read the file ({exc})"], [], []
    code = _strip_comments(raw)

    specs = [(m.start(), m.group("spec")) for m in _IMPORT_FROM.finditer(code)]
    specs += [(m.start(), m.group("spec")) for m in _IMPORT_BARE.finditer(code)]
    for pos, spec in sorted(set(specs)):
        where = f"{label}:{_line_of(code, pos)}"
        if spec in ALLOWED_PACKAGES or spec in (STYLE_IMPORT, KIT_IMPORT):
            continue
        if spec.startswith("./") and NAME_RE.fullmatch(Path(spec).name) and "/" not in spec[2:]:
            if entry is None:
                target = _source_file(project_root, spec[2:])
                where_files = f"{COMPONENTS_DIR}/{spec[2:]}.tsx"
                rel = target.name if target else ""
            else:
                target = None if library_root is None else _find_in(library_root / entry, spec[2:])
                where_files = f"{LIBRARY_DIR}/{entry}/{spec[2:]}.tsx"
                rel = f"{LIBRARY_DIR}/{entry}/{target.name}" if target else ""
            if target is None:
                errors.append(f"{where}: import '{spec}' has no file {where_files}")
            elif all(item.path != target for item in local):
                local.append(SourceFile(target, rel))
            continue
        lib = LIBRARY_IMPORT_RE.fullmatch(spec)
        if lib is not None and entry is None:
            folder = None if library_root is None else library_root / lib["entry"]
            target = None if folder is None else _find_in(folder, lib["file"])
            if target is None:
                errors.append(
                    f"{where}: import '{spec}' has no file in the style library "
                    f"({_library_files(library_root, lib['entry'])})"
                )
            elif all(item.path != target for item in local):
                local.append(SourceFile(target, f"{LIBRARY_DIR}/{lib['entry']}/{target.name}"))
            continue
        if entry is None:
            errors.append(
                f"{where}: import '{spec}' is not allowed; a component may import only react, remotion, "
                f"'{STYLE_IMPORT}', '{KIT_IMPORT}', other files of {COMPONENTS_DIR}/ as './Name' "
                f"and style library files as './{LIBRARY_DIR}/<entry>/<File>'"
            )
        else:
            errors.append(
                f"{where}: import '{spec}' is not allowed in a library entry; it may import only react, "
                f"remotion, '{STYLE_IMPORT}', '{KIT_IMPORT}' and other files of the same entry as './Name'"
            )
    for pattern, what in (
        (_IMPORT_DYNAMIC, "dynamic import() is not allowed"),
        (_REQUIRE, "require() is not allowed"),
        (_NETWORK, "network access is not allowed in a component"),
        (_URL, "a web URL is not allowed in a component; use files of the plan through resolveMedia()"),
    ):
        for m in pattern.finditer(code):
            errors.append(f"{label}:{_line_of(code, m.start())}: {what} ({m.group().strip()!r})")
    for m in _NONDETERMINISTIC.finditer(code):
        warnings.append(
            f"{label}:{_line_of(code, m.start())}: {m.group().strip()!r} gives different values in parallel "
            "render workers; use random('seed') and useCurrentFrame() instead"
        )
    return errors, warnings, local


def collect_files(
    project_root: Path,
    names: Iterable[str],
    library_root: Path | None = None,
) -> tuple[list[SourceFile], list[str], list[str]]:
    """The source files a render needs: the named components plus the files they import.

    Files of style library entries are included when a component imports them.
    Returns `(files, errors, warnings)`; `errors` has `scenes`-independent messages only.
    """
    files: list[SourceFile] = []
    errors: list[str] = []
    warnings: list[str] = []
    queue: list[SourceFile] = []
    for name in names:
        path = _source_file(project_root, name)
        if path is not None:  # a missing file is reported with the scene that names it
            queue.append(SourceFile(path, path.name))
    seen: set[Path] = set()
    while queue:
        item = queue.pop(0)
        if item.path in seen:
            continue
        seen.add(item.path)
        files.append(item)
        entry = item.rel.split("/")[1] if item.rel.startswith(f"{LIBRARY_DIR}/") else None
        e, w, local = scan_source(item.path, project_root, library_root, entry)
        errors += e
        warnings += w
        queue += local
    return files, errors, warnings


def check_components(
    plan: Plan, project_root: Path, library_root: Path | None = None
) -> tuple[list[str], list[str]]:
    """`(errors, warnings)` for the custom scenes of a plan, before any job starts."""
    errors: list[str] = []
    warnings: list[str] = []
    for i, scene in enumerate(plan.scenes):
        if isinstance(scene, CustomScene) and _source_file(project_root, scene.component) is None:
            errors.append(
                f"scenes[{i}].component: file not found: {COMPONENTS_DIR}/{scene.component}.tsx "
                f"(write it in the project folder {project_root})"
            )
    _, e, w = collect_files(project_root, used_components(plan), library_root)
    return errors + e, warnings + w


# ------------------------------------------------------------------ the engine side

def _lock_path(engine: Path) -> Path:
    return engine / LOCK_NAME


def _lock_is_stale(path: Path) -> bool:
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        pid, created = int(info.get("pid", 0)), float(info.get("time", 0))
    except (OSError, ValueError, TypeError):
        try:  # unreadable: the owner may be mid-write, give it a moment
            return time.time() - path.stat().st_mtime > 10
        except OSError:
            return False
    return not pid_alive(pid) or time.time() - created > LOCK_STALE_S


def _take_lock(engine: Path, wait_s: float) -> None:
    path = _lock_path(engine)
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _lock_is_stale(path):
                path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise ComponentError(
                    f"another render has been using the engine for more than {wait_s:.0f} s ({path}); "
                    "try again when it is done"
                ) from None
            time.sleep(0.4)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "time": time.time()}, fh)
        return


@dataclass
class EngineHold:
    """The engine folder, reserved for one render until its bundle is built.

    `acquire()` returns the compile errors (empty list: ready). `release()` can be called
    any number of times; it always leaves the committed engine behind.
    """

    engine: Path
    project_root: Path
    names: list[str]
    work: Path
    lock_wait_s: float = LOCK_WAIT_S
    library_root: Path | None = None
    warnings: list[str] = field(default_factory=list)
    _locked: bool = False
    _registry_bytes: bytes | None = None
    _line_names: dict[int, str] = field(default_factory=dict)

    @property
    def registry(self) -> Path:
        return self.engine / "src" / "custom" / "registry.ts"

    @property
    def job_dir(self) -> Path:
        return self.engine / "src" / "custom" / "job"

    def acquire(self) -> list[str]:
        _take_lock(self.engine, self.lock_wait_s)
        self._locked = True
        try:
            self._remember_registry()
            shutil.rmtree(self.job_dir, ignore_errors=True)  # left by a render that was killed
            if not self.names:
                return []
            return self._install_and_check()
        except BaseException:
            self.release()
            raise

    def release(self) -> None:
        if not self._locked:
            return
        try:
            if self._registry_bytes is not None:
                self.registry.write_bytes(self._registry_bytes)
            shutil.rmtree(self.job_dir, ignore_errors=True)
        finally:
            self._locked = False
            _lock_path(self.engine).unlink(missing_ok=True)

    # -- internals

    def _remember_registry(self) -> None:
        data = self.registry.read_bytes()
        if b"./job/" in data:  # a crashed render left its registry: go back to the committed text
            data = EMPTY_REGISTRY.encode("utf-8")
        self._registry_bytes = data

    def _install_and_check(self) -> list[str]:
        files, errors, self.warnings = collect_files(self.project_root, self.names, self.library_root)
        if errors:
            return errors
        self.job_dir.mkdir(parents=True, exist_ok=True)
        for src in files:
            target = self.job_dir / src.rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src.path, target)
        used = sorted({src.rel.split("/")[1] for src in files if src.rel.startswith(f"{LIBRARY_DIR}/")})
        if used:
            for shim, text in LIBRARY_SHIMS.items():
                (self.job_dir / LIBRARY_DIR / shim).write_text(text, encoding="utf-8", newline="\n")
            if self.library_root is not None:
                from . import library  # local import: library.py imports this module

                library.count_use(self.library_root, used)  # `times used` in each entry's card
        by_name = {Path(f.rel).stem: f for f in files if "/" not in f.rel}
        missing = [n for n in self.names if n not in by_name]
        if missing:
            return [f"{COMPONENTS_DIR}/{n}.tsx: file not found" for n in missing]
        # registry.ts line numbers (1-based) -> component name, to point compiler errors at the right file
        self._line_names = {}
        lines = ["import type {ComponentType} from 'react';"]
        for i, n in enumerate(self.names):
            lines.append(f"import C{i} from './job/{Path(by_name[n].rel).stem}';")
            self._line_names[len(lines)] = n
        lines += ["", "// Generated for one render by argus.tools.components; the committed file is an empty map."]
        lines += ["// eslint-disable-next-line @typescript-eslint/no-explicit-any"]
        lines += ["export const registry: Record<string, ComponentType<any>> = {"]
        for i, n in enumerate(self.names):
            lines.append(f"  {json.dumps(n)}: C{i},")
            self._line_names[len(lines)] = n
        lines += ["};", ""]
        self.registry.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        return self._typecheck()

    def _typecheck(self) -> list[str]:
        tsc = self.engine / "node_modules" / "typescript" / "bin" / "tsc"
        node = shutil.which("node")
        if node is None or not tsc.is_file():
            raise ComponentError("cannot typecheck components: needs Node.js and `npm install` in the engine folder")
        self.work.mkdir(parents=True, exist_ok=True)
        config = self.work / "tsconfig.components.json"
        src = (self.engine / "src").as_posix()
        config.write_text(json.dumps({
            "extends": (self.engine / "tsconfig.json").as_posix(),
            "compilerOptions": {"typeRoots": [(self.engine / "node_modules" / "@types").as_posix()]},
            "include": [f"{src}/custom/registry.ts", f"{src}/custom/job/**/*"],
        }), encoding="utf-8")
        try:
            proc = subprocess.run(
                [node, str(tsc), "--noEmit", "--pretty", "false", "-p", str(config)],
                cwd=self.engine, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=TSC_TIMEOUT_S, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            raise ComponentError(f"the typecheck of the components took longer than {TSC_TIMEOUT_S:.0f} s") from None
        if proc.returncode == 0:
            return []
        errors = self._parse_tsc(proc.stdout)
        if not errors:
            raise ComponentError("the typecheck failed without a readable message:\n" + (proc.stdout + proc.stderr)[-1500:])
        return errors

    def _parse_tsc(self, output: str) -> list[str]:
        out: list[str] = []
        for raw in output.splitlines():
            m = _TSC_LINE.match(raw)
            if m is None:
                if raw.startswith((" ", "\t")) and out:
                    out[-1] += " " + raw.strip()  # continuation of the previous message
                continue
            path = (self.engine / m["file"]).resolve() if not Path(m["file"]).is_absolute() else Path(m["file"]).resolve()
            line, msg = int(m["line"]), m["msg"]
            if path == self.registry.resolve():
                name = self._line_names.get(line, "?")
                out.append(f"{COMPONENTS_DIR}/{name}.tsx: the default export is not a React component ({msg})")
            elif self.job_dir.resolve() in path.parents:
                rel = path.relative_to(self.job_dir.resolve()).as_posix()
                shown = rel if rel.startswith(f"{LIBRARY_DIR}/") else f"{COMPONENTS_DIR}/{rel}"
                out.append(f"{shown}({line},{m['col']}): {msg}")
            else:
                out.append(f"{path.name}({line},{m['col']}): {msg}")
        if len(out) > MAX_ERRORS:
            out = out[:MAX_ERRORS] + [f"... and {len(out) - MAX_ERRORS} more errors"]
        return out
