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

from ..jobs import pid_alive
from ..plan import CustomScene, Plan

COMPONENTS_DIR = "components"
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
EXTENSIONS = (".tsx", ".ts")

LOCK_NAME = ".render.lock"
LOCK_WAIT_S = 300.0              # another render is bundling; wait this long for it
LOCK_STALE_S = 2 * 3600.0        # a lock older than this is dropped even if its pid looks alive
TSC_TIMEOUT_S = 180.0
MAX_ERRORS = 25                  # compiler errors returned to the model

# Imports a component may use (engine/src/custom/README.md).
ALLOWED_PACKAGES = ("react", "react/jsx-runtime", "remotion")
STYLE_IMPORT = "../style"

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


def _source_file(project_root: Path, name: str) -> Path | None:
    folder = project_root / COMPONENTS_DIR
    for ext in EXTENSIONS:
        cand = folder / f"{name}{ext}"
        if cand.is_file():
            return cand
    return None


def _strip_comments(text: str) -> str:
    """The code without comments; line numbers stay the same."""
    blank = lambda m: "\n" * m.group().count("\n")  # noqa: E731
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub(blank, text))


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_source(path: Path, project_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Check one component file against the contract.

    Returns `(errors, warnings, local files it imports)`. Messages read
    `components/<File>:<line>: ...`.
    """
    label = f"{COMPONENTS_DIR}/{path.name}"
    errors: list[str] = []
    warnings: list[str] = []
    local: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{label}: cannot read the file ({exc})"], [], []
    code = _strip_comments(raw)

    specs = [(m.start(), m.group("spec")) for m in _IMPORT_FROM.finditer(code)]
    specs += [(m.start(), m.group("spec")) for m in _IMPORT_BARE.finditer(code)]
    for pos, spec in sorted(set(specs)):
        where = f"{label}:{_line_of(code, pos)}"
        if spec in ALLOWED_PACKAGES or spec == STYLE_IMPORT:
            continue
        if spec.startswith("./") and NAME_RE.fullmatch(Path(spec).name) and "/" not in spec[2:]:
            target = _source_file(project_root, spec[2:])
            if target is None:
                errors.append(f"{where}: import '{spec}' has no file {COMPONENTS_DIR}/{spec[2:]}.tsx")
            elif target.name not in local:
                local.append(target.name)
            continue
        errors.append(
            f"{where}: import '{spec}' is not allowed; a component may import only react, remotion, "
            f"'{STYLE_IMPORT}' and other files of {COMPONENTS_DIR}/ as './Name'"
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


def collect_files(project_root: Path, names: Iterable[str]) -> tuple[list[Path], list[str], list[str]]:
    """The source files a render needs: the named components plus the files they import.

    Returns `(files, errors, warnings)`; `errors` has `scenes`-independent messages only.
    """
    files: list[Path] = []
    errors: list[str] = []
    warnings: list[str] = []
    queue = list(names)
    seen: set[str] = set()
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        path = _source_file(project_root, name)
        if path is None:
            continue  # reported with the scene that names it
        files.append(path)
        e, w, local = scan_source(path, project_root)
        errors += e
        warnings += w
        queue += [Path(f).stem for f in local]
    return files, errors, warnings


def check_components(plan: Plan, project_root: Path) -> tuple[list[str], list[str]]:
    """`(errors, warnings)` for the custom scenes of a plan, before any job starts."""
    errors: list[str] = []
    warnings: list[str] = []
    for i, scene in enumerate(plan.scenes):
        if isinstance(scene, CustomScene) and _source_file(project_root, scene.component) is None:
            errors.append(
                f"scenes[{i}].component: file not found: {COMPONENTS_DIR}/{scene.component}.tsx "
                f"(write it in the project folder {project_root})"
            )
    _, e, w = collect_files(project_root, used_components(plan))
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
        files, errors, self.warnings = collect_files(self.project_root, self.names)
        if errors:
            return errors
        self.job_dir.mkdir(parents=True, exist_ok=True)
        for src in files:
            shutil.copy2(src, self.job_dir / src.name)
        by_name = {f.stem: f for f in files}
        missing = [n for n in self.names if n not in by_name]
        if missing:
            return [f"{COMPONENTS_DIR}/{n}.tsx: file not found" for n in missing]
        # registry.ts line numbers (1-based) -> component name, to point compiler errors at the right file
        self._line_names = {}
        lines = ["import type {ComponentType} from 'react';"]
        for i, n in enumerate(self.names):
            lines.append(f"import C{i} from './job/{by_name[n].stem}';")
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
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            proc = subprocess.run(
                [node, str(tsc), "--noEmit", "--pretty", "false", "-p", str(config)],
                cwd=self.engine, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=TSC_TIMEOUT_S, creationflags=creationflags, stdin=subprocess.DEVNULL,
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
                out.append(f"{COMPONENTS_DIR}/{path.name}({line},{m['col']}): {msg}")
            else:
                out.append(f"{path.name}({line},{m['col']}): {msg}")
        if len(out) > MAX_ERRORS:
            out = out[:MAX_ERRORS] + [f"... and {len(out) - MAX_ERRORS} more errors"]
        return out
