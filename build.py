#!/usr/bin/env python3
"""
Kefirosphere Build Script

1. Applies core patches to Atmosphere (current branch).
2. Creates variant branches (8gb_DRAM, oc, 40mb) and applies their patches.
3. Runs `make kefir` (full build pipeline).
4. On success: bumps version file and commits Kefirosphere.
5. Always restores Atmosphere to the original state.

Run via build.sh (which sources .env).
"""

import os, sys, subprocess, logging, threading, re, time
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR    = Path(__file__).resolve().parent
ATMOSPHERE_DIR = (SCRIPT_DIR / ".." / "Atmosphere").resolve()
PATCHES_DIR   = SCRIPT_DIR / "patches"
LOG_FILE      = SCRIPT_DIR / "build.log"

# ─────────────────────────────────────────────────────────────────────────────
# ANSI helpers
# ─────────────────────────────────────────────────────────────────────────────

IS_TTY = sys.stdout.isatty()
def _e(*c): return ("\033[" + ";".join(str(x) for x in c) + "m") if IS_TTY else ""

R   = _e(0);  B   = _e(1);  DIM = _e(2)
YL  = _e(33); RD  = _e(31)
BCY = _e(96); BGR = _e(92)

def _up(n): return f"\033[{n}A" if IS_TTY else ""
def _clr(): return "\033[2K\r"  if IS_TTY else ""

# ─────────────────────────────────────────────────────────────────────────────
# Logging – file + console; console suppressed during live display
# ─────────────────────────────────────────────────────────────────────────────

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
_fh  = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
_ch  = logging.StreamHandler(sys.stdout)
_fh.setFormatter(_fmt); _ch.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_fh, _ch])
log = logging.getLogger("kefir-build")

def _log_off(): logging.getLogger().removeHandler(_ch)
def _log_on():  logging.getLogger().addHandler(_ch)

# ─────────────────────────────────────────────────────────────────────────────
# Source file counting (for accurate progress)
# ─────────────────────────────────────────────────────────────────────────────

_BUILDS = 4          # master + 8gb + oc + 40mb
_ARCH_FACTOR = 1.15  # some files compile twice (arm + arm64)


def count_source_files() -> int:
    """Count compilable source files in Atmosphere. Returns estimated total compilations."""
    total = 0
    for ext in ("*.cpp", "*.c", "*.s", "*.S", "*.cc", "*.cxx"):
        # Exclude build output directories
        for p in ATMOSPHERE_DIR.rglob(ext):
            if "out" not in p.parts and "build" not in p.parts:
                total += 1
    # × 4 builds × arch overhead
    return max(int(total * _BUILDS * _ARCH_FACTOR), 2000)

# ─────────────────────────────────────────────────────────────────────────────
# Live progress display
# ─────────────────────────────────────────────────────────────────────────────

_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_W    = 68


class BuildProgress:
    _PATCH_WEIGHT  = 0.04   # 0-4%  : patching phase
    _PREBUILD_END  = 0.05   # 5%    : make starts

    def __init__(self, total_files: int):
        self._lk      = threading.Lock()
        self._total   = total_files
        self._phase   = "Initializing…"
        self._branch  = "—"
        self._module  = "—"
        self._label   = ""
        self._files   = 0
        self._base    = 0.0   # progress before make starts (patches)
        self._t0      = time.time()
        self._si      = 0
        self._alive   = True

    def set(self, *, phase=None, branch=None, module=None,
            label=None, file_delta=0, base_pct=None):
        with self._lk:
            if phase      is not None: self._phase  = phase
            if branch     is not None: self._branch = branch
            if module     is not None: self._module = module
            if label      is not None: self._label  = label
            if base_pct   is not None: self._base   = base_pct
            self._files += file_delta

    def _pct(self) -> float:
        """Progress 0..1: patches contribute _PATCH_WEIGHT, the rest from files."""
        file_pct  = min(self._files / self._total, 1.0)
        make_part = (1.0 - self._PREBUILD_END) * file_pct
        return min(self._base + self._PREBUILD_END + make_part, 1.0)

    def _elapsed(self):
        s = int(time.time() - self._t0); m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    def _tr(self, s, n):
        return s if len(s) <= n else "…" + s[-(n - 1):]

    def _bar(self, pct):
        bw   = _W - 12
        fill = int(bw * pct)
        bar  = f"{BGR}{'█' * fill}{DIM}{'░' * (bw - fill)}{R}"
        return f"  [{bar}] {int(pct * 100):3d}%"

    def _build_lines(self):
        sep = f"{DIM}{'─' * _W}{R}"
        sp  = _SPIN[self._si % len(_SPIN)]; self._si += 1
        pct = self._pct()
        return [
            sep,
            f"  {B}{BCY}Kefirosphere Build{R}   {sp}   {DIM}{self._elapsed()}{R}",
            sep,
            f"  {YL}Phase  {R}│ {self._tr(self._phase,  _W - 12)}",
            f"  {YL}Branch {R}│ {BGR}{self._tr(self._branch, _W - 12)}{R}",
            f"  {YL}Module {R}│ {self._tr(self._module, _W - 12)}",
            f"  {YL}Files  {R}│ {self._files:,} / ~{self._total:,}   {DIM}{self._tr(self._label, _W - 26)}{R}",
            sep,
            self._bar(pct),
            sep,
        ]

    def _draw(self, initial=False):
        if not IS_TTY:
            return
        lines = self._build_lines()
        if not initial:
            sys.stdout.write(_up(len(lines)))
        for ln in lines:
            sys.stdout.write(_clr() + ln + "\n")
        sys.stdout.flush()

    def _loop(self):
        with self._lk: self._draw(initial=True)
        while self._alive:
            time.sleep(0.12)
            with self._lk: self._draw()
        with self._lk: self._draw()

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        return t

    def stop(self, success: bool):
        with self._lk:
            self._phase = "Build complete ✓" if success else "BUILD FAILED ✗"
        self._alive = False
        time.sleep(0.25)
        mark  = f"{BGR}✓{R}" if success else f"{RD}✗{R}"
        label = "Success" if success else "Failed"
        print(f"\n  {B}{mark} {label}!{R}  ({self._elapsed()})\n")


# ─────────────────────────────────────────────────────────────────────────────
# Make output patterns
# ─────────────────────────────────────────────────────────────────────────────

_COMPILE_RE = re.compile(
    r"^([A-Za-z][\w.+-]*\.(?:cpp|cxx|cc|c|s|S|asm))\s*$"
    r"|^(linking\s+\S+\.\S+)"
    r"|^(built\s+\.\.\.\s+\S+)",
    re.IGNORECASE,
)
_ENTER_RE    = re.compile(r"Entering directory '(.+?)'")
# Permissive: match GIT_BRANCH= followed by any non-word, then capture word
_GBRANCH_RE  = re.compile(r'ATMOSPHERE_GIT_BRANCH[^\w]+(\w+)')
_CHECKOUT_RE = re.compile(r'^git checkout\s+(\S+)\s*$')


def _module_from_path(path: str) -> str:
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    try:
        idx  = next(i for i, p in enumerate(parts) if p.lower() == "atmosphere")
        tail = parts[idx + 1:]
    except StopIteration:
        tail = parts[-2:] if len(parts) >= 2 else parts
    return " » ".join(tail) if tail else "—"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def run(cmd, *, cwd=None, check=True):
    cwd = cwd or ATMOSPHERE_DIR
    res = subprocess.run([str(c) for c in cmd], cwd=str(cwd),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and res.returncode != 0:
        parts = []
        if res.stdout.strip(): parts.append("--- stdout ---\n" + res.stdout.strip())
        if res.stderr.strip(): parts.append("--- stderr ---\n" + res.stderr.strip())
        raise subprocess.CalledProcessError(
            res.returncode, cmd, "\n".join(parts) or "(no output)", res.stderr)
    return res


def run_capture(cmd, *, cwd=None):
    return run(cmd, cwd=cwd).stdout.strip()


def git(*args, cwd=None, check=True):
    return run(["git"] + list(args), cwd=cwd, check=check)


def git_out(*args, cwd=None):
    return run_capture(["git"] + list(args), cwd=cwd)


def env_require(name):
    val = os.environ.get(name)
    if not val:
        log.error("Required env variable '%s' is not set — check your .env", name)
        sys.exit(1)
    return val


# ─────────────────────────────────────────────────────────────────────────────
# run_make
# ─────────────────────────────────────────────────────────────────────────────

def run_make(cmd, *, cwd=None, progress: BuildProgress = None):
    cwd  = str(cwd or ATMOSPHERE_DIR)
    proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
    all_lines: list[str] = []
    cur_branch = "master"

    for raw in proc.stdout:
        line = raw.rstrip()
        all_lines.append(raw)

        if progress is None:
            continue

        # ── compiled file / link / artifact ──────────────────
        m = _COMPILE_RE.search(line)
        if m:
            matched = next((g for g in m.groups() if g), "")
            progress.set(label=matched.strip(), file_delta=1)
            continue

        # ── entering directory → module ───────────────────────
        em = _ENTER_RE.search(line)
        if em:
            progress.set(module=_module_from_path(em.group(1)))
            continue

        # ── explicit git checkout ─────────────────────────────
        cm = _CHECKOUT_RE.search(line)
        if cm:
            b = cm.group(1).strip("'\"")
            if b and b != "--":
                cur_branch = b
                progress.set(branch=cur_branch)
            continue

        # ── branch from compiler flags (most reliable) ────────
        bm = _GBRANCH_RE.search(line)
        if bm:
            b = bm.group(1)
            if b != cur_branch:
                cur_branch = b
                progress.set(branch=cur_branch)

    proc.wait()
    if proc.returncode != 0:
        captured = "".join(all_lines)
        raise subprocess.CalledProcessError(
            proc.returncode, cmd,
            "--- stdout ---\n" + captured.strip(), "")
    return proc.returncode


# ─────────────────────────────────────────────────────────────────────────────
# Environment
# ─────────────────────────────────────────────────────────────────────────────

def load_env():
    return {
        "KEFIR_ROOT_DIR":   env_require("KEFIR_ROOT_DIR"),
        "KEFIROSPHERE_DIR": env_require("KEFIROSPHERE_DIR"),
        "SPLASH_LOGO_PATH": env_require("SPLASH_LOGO_PATH"),
        "SPLASH_BMP_PATH":  env_require("SPLASH_BMP_PATH"),
        "LIBNX_DIR":        os.environ.get("LIBNX_DIR", "../libnx"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Version management
# ─────────────────────────────────────────────────────────────────────────────

def read_version(kefir_root: str) -> int:
    version_file = Path(kefir_root) / "version"
    try:
        return int(version_file.read_text().strip())
    except Exception:
        return 0


def bump_version(kefir_root: str) -> int:
    """Increment version file and commit changes. Returns new version."""
    version_file = Path(kefir_root) / "version"
    try:
        current = int(version_file.read_text().strip())
    except Exception:
        current = 0
    new_ver = current + 1
    version_file.write_text(str(new_ver) + "\n")
    log.info("Version bumped: %d → %d", current, new_ver)

    # Commit kefir_root branch
    try:
        git("add", "version", cwd=kefir_root)
        git("commit", "-m", f"build: bump version to {new_ver}", cwd=kefir_root)
        log.info("Kefir root version committed: %d", new_ver)
    except subprocess.CalledProcessError as e:
        log.warning("Could not commit Kefir root directory:\n%s", e.stdout)

    # Commit Kefirosphere
    try:
        git("add", "-A", cwd=SCRIPT_DIR)
        git("commit", "-m", f"build: bump version to {new_ver}", cwd=SCRIPT_DIR)
        log.info("Kefirosphere committed: build %d", new_ver)
    except subprocess.CalledProcessError as e:
        log.warning("Could not commit Kefirosphere:\n%s", e.stdout)

    return new_ver


# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight
# ─────────────────────────────────────────────────────────────────────────────

def reset_atmosphere():
    res = run(["git", "status", "--porcelain"], cwd=ATMOSPHERE_DIR, check=False)
    if res.stdout.strip():
        log.info("Atmosphere has local changes — resetting…")
        git("reset", "--hard", "HEAD")
        git("clean", "-fd", check=False)
        log.info("Atmosphere reset — OK")
    else:
        log.info("Atmosphere is clean — OK")


def save_state():
    branch = git_out("branch", "--show-current")
    head   = git_out("rev-parse", "HEAD")
    log.info("State saved — branch: %s  HEAD: %s", branch, head)
    return branch, head


# ─────────────────────────────────────────────────────────────────────────────
# Patch application
# ─────────────────────────────────────────────────────────────────────────────

def apply_patches(patch_dir: Path, label: str, progress: BuildProgress = None,
                  patch_idx: list = None, total_patches: int = 1):
    patches = sorted(patch_dir.glob("*.patch"))
    if not patches:
        log.warning("[%s] No patches found — skipping", label)
        return

    log.info("[%s] Applying %d patch(es)…", label, len(patches))
    for patch in patches:
        log.info("[%s]   %s", label, patch.name)
        if progress:
            progress.set(label=patch.name)
        try:
            git("am", str(patch))
        except subprocess.CalledProcessError as e:
            git("am", "--abort", check=False)
            log.error(
                "\n============================================================\n"
                "  PATCH FAILED\n  Variant : %s\n  File    : %s\n"
                "------------------------------------------------------------\n%s\n"
                "============================================================",
                label, patch.name, e.stdout,
            )
            raise RuntimeError(f"Patch failed: {patch.name}") from e

        if patch_idx is not None:
            patch_idx[0] += 1
            if progress:
                # Patch phase contributes up to PATCH_WEIGHT of total progress
                pct = progress._PATCH_WEIGHT * (patch_idx[0] / total_patches)
                progress.set(base_pct=pct)


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────

VARIANT_BRANCHES = ["8gb_DRAM", "oc", "40mb"]


def cleanup(orig_branch, orig_head):
    log.info("=== Cleanup: restoring Atmosphere ===")
    git("checkout", orig_branch, check=False)
    try:
        git("reset", "--hard", orig_head)
    except subprocess.CalledProcessError as e:
        log.error("git reset failed:\n%s", e.stdout)
    try:
        git("clean", "-fd")
    except subprocess.CalledProcessError as e:
        log.warning("git clean failed:\n%s", e.stdout)
    for branch in VARIANT_BRANCHES:
        git("branch", "-D", branch, check=False)
        log.info("Deleted branch: %s", branch)
    log.info("=== Cleanup complete ===")


# ─────────────────────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────────────────────

NPROCS = os.cpu_count() or 4


def build(env):
    # Count source files for accurate progress estimation
    log.info("Counting source files for progress estimation…")
    total_files = count_source_files()
    log.info("Estimated total compilations: ~%d", total_files)

    reset_atmosphere()
    orig_branch, orig_head = save_state()

    # Count total patches for patch-phase progress
    patch_dirs   = [PATCHES_DIR / "core", PATCHES_DIR / "8gb",
                    PATCHES_DIR / "oc",   PATCHES_DIR / "40mb"]
    total_patches = sum(len(list(d.glob("*.patch"))) for d in patch_dirs if d.exists()) or 1
    patch_idx = [0]

    make_vars = [
        f"KEFIROSPHERE_DIR={env['KEFIROSPHERE_DIR']}",
        f"KEFIR_ROOT_DIR={env['KEFIR_ROOT_DIR']}",
        f"SPLASH_LOGO_PATH={env['SPLASH_LOGO_PATH']}",
        f"SPLASH_BMP_PATH={env['SPLASH_BMP_PATH']}",
        f"LIBNX_DIR={env['LIBNX_DIR']}",
    ]

    prog = BuildProgress(total_files)
    _log_off()
    prog.start()

    success = False
    try:
        # Step 1 — core patches
        prog.set(phase="Step 1/3 — Applying core patches",
                 branch="master", module="patches/core")
        apply_patches(PATCHES_DIR / "core", "core", prog, patch_idx, total_patches)

        # Step 2 — variant branches
        for branch_name, patch_subdir in [("8gb_DRAM", "8gb"), ("oc", "oc"), ("40mb", "40mb")]:
            prog.set(phase=f"Step 2/3 — Branch: {branch_name}",
                     branch=branch_name, module=f"patches/{patch_subdir}")
            git("checkout", "-b", branch_name)
            apply_patches(PATCHES_DIR / patch_subdir, branch_name, prog,
                          patch_idx, total_patches)
            git("checkout", orig_branch)

        # Step 3 — make kefir
        prog.set(phase="Step 3/3 — make kefir", branch="master", module="—")
        try:
            run_make(["make", "kefir", f"-j{NPROCS}"] + make_vars, progress=prog)
        except subprocess.CalledProcessError as e:
            log.error(
                "\n============================================================\n"
                "  BUILD FAILED: make kefir\n"
                "------------------------------------------------------------\n%s\n"
                "============================================================",
                e.stdout,
            )
            return False

        log.info("=== Build completed successfully ===")
        success = True
        return True

    except RuntimeError:
        return False

    except subprocess.CalledProcessError as e:
        log.error("Unexpected failure (exit %d):\n%s", e.returncode, e.stdout)
        return False

    finally:
        prog.stop(success)
        _log_on()
        if success:
            new_ver = bump_version(env["KEFIR_ROOT_DIR"])
            log.info("Version after build: %d", new_ver)
        cleanup(orig_branch, orig_head)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("Kefirosphere Build — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("  Atmosphere : %s", ATMOSPHERE_DIR)
    log.info("  Patches    : %s", PATCHES_DIR)
    log.info("=" * 60)

    if not ATMOSPHERE_DIR.exists():
        log.error("Atmosphere directory not found: %s", ATMOSPHERE_DIR)
        sys.exit(1)

    env = load_env()
    ok  = build(env)
    log.info("Log: %s", LOG_FILE)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
