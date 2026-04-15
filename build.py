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

import os, sys, subprocess, logging, threading, re, time, shutil, argparse, zipfile
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

# Hardcoded estimation to avoid 30+ seconds of file traversal.
# Master branch compilation takes ~4690 files.
# The 3 variant branches (8gb_DRAM, oc, 40mb) compile roughly 1 file each.
_ESTIMATED_FILES = 4690

# ─────────────────────────────────────────────────────────────────────────────
# Interactive patch selection
# ─────────────────────────────────────────────────────────────────────────────

def interactive_select(patches: list) -> set:
    try:
        import msvcrt
        has_msvcrt = True
    except ImportError:
        import tty, termios
        has_msvcrt = False

    selected = set(patches)
    idx = 0
    lines_written = 0

    def draw():
        nonlocal lines_written
        if lines_written > 0:
            sys.stdout.write(f"\033[{lines_written}A")
        
        sys.stdout.write("\033[J")
        print(f"\033[1;36mInteractive Patch Selection\033[0m")
        print("Use \033[1mUP/DOWN\033[0m arrows to navigate, \033[1mSPACE\033[0m to toggle, \033[1mENTER\033[0m to confirm.")
        print("-" * 65)
        out = []
        for i, p in enumerate(patches):
            chk = "[x]" if p in selected else "[ ]"
            pointer = ">> " if i == idx else "   "
            color = "\033[1;32m" if p in selected else "\033[2m"
            out.append(f"{pointer}{color}{chk} {p}\033[0m")
        print("\n".join(out))
        lines_written = len(patches) + 3
        sys.stdout.flush()

    draw()
    while True:
        if has_msvcrt:
            c = msvcrt.getch()
            if c in (b'\x00', b'\xe0'):
                c2 = msvcrt.getch()
                if c2 == b'H': idx = max(0, idx - 1)
                elif c2 == b'P': idx = min(len(patches)-1, idx + 1)
            elif c == b' ':
                p = patches[idx]
                if p in selected: selected.remove(p)
                else: selected.add(p)
            elif c == b'\r':
                break
        else:
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                c = sys.stdin.read(1)
                if c == '\x1b':
                    c2 = sys.stdin.read(2)
                    if c2 == '[A': idx = max(0, idx - 1)
                    elif c2 == '[B': idx = min(len(patches)-1, idx + 1)
                elif c == ' ':
                    p = patches[idx]
                    if p in selected: selected.remove(p)
                    else: selected.add(p)
                elif c in ('\r', '\n'):
                    break
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        draw()
    
    if lines_written > 0:
        sys.stdout.write(f"\033[{lines_written}A\033[J")
        sys.stdout.flush()

    return set(patches) - selected

# ─────────────────────────────────────────────────────────────────────────────
# Live progress display
# ─────────────────────────────────────────────────────────────────────────────

_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_W    = 68


class BuildProgress:
    _PATCH_WEIGHT  = 0.04   # 0-4%  : patching phase
    _PREBUILD_END  = 0.05   # 5%    : make starts

    def __init__(self, total_files: int, all_patches: list = None, skipped_patches: set = None):
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
        
        self._all_patches = all_patches or []
        self._patch_statuses = {p: "waiting" for p in self._all_patches}
        if skipped_patches:
            for p in skipped_patches:
                self._patch_statuses[p] = "skipped"

    def set_patch_status(self, patch_name: str, status: str):
        with self._lk:
            self._patch_statuses[patch_name] = status

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
        if self._phase == "Build complete ✓":
            return 1.0
        file_pct  = min(self._files / self._total, 1.0)
        make_part = (1.0 - self._PREBUILD_END) * file_pct
        pct = self._base + self._PREBUILD_END + make_part
        return min(pct, 0.99)

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
        lines = []
        if self._all_patches:
            for p in self._all_patches:
                st = self._patch_statuses.get(p, "waiting")
                cb = " "
                if st == "done":
                    cb = f"{BGR}✓{R}"
                elif st == "skipped":
                    cb = f"{B}\033[34m✗{R}"
                elif st == "processing":
                    sp = _SPIN[self._si % len(_SPIN)]
                    cb = f"{YL}{sp}{R}"
                
                color = DIM if st in ("waiting", "skipped") else ""
                lines.append(f"  [{cb}] {color}{p}{R}")
            lines.append(f"{DIM}{'─' * _W}{R}")

        sep = f"{DIM}{'─' * _W}{R}"
        sp  = _SPIN[self._si % len(_SPIN)]; self._si += 1
        pct = self._pct()
        
        lines.extend([
            f"  {B}{BCY}Kefirosphere Build{R}   {sp}   {DIM}{self._elapsed()}{R}",
            sep,
            f"  {YL}Phase  {R}│ {self._tr(self._phase,  _W - 12)}",
            f"  {YL}Branch {R}│ {BGR}{self._tr(self._branch, _W - 12)}{R}",
            f"  {YL}Module {R}│ {self._tr(self._module, _W - 12)}",
            f"  {YL}Files  {R}│ {self._files:,} / ~{self._total:,}   {DIM}{self._tr(self._label, _W - 26)}{R}",
            sep,
            self._bar(pct),
            sep,
        ])
        return lines

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
    # Load .env locally if run directly
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip("\"'"))

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
    version_file.write_text(str(new_ver))
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
                  patch_idx: list = None, total_patches: int = 1, skipped_patches: set = None):
    if skipped_patches is None: skipped_patches = set()
    patches = sorted(patch_dir.glob("*.patch"))
    if not patches:
        log.warning("[%s] No patches found — skipping", label)
        return

    log.info("[%s] Applying %d patch(es)…", label, len(patches))
    for patch in patches:
        if patch.name in skipped_patches:
            log.info("[%s]   %s (SKIPPED)", label, patch.name)
            continue
            
        log.info("[%s]   %s", label, patch.name)
        if progress:
            progress.set_patch_status(patch.name, "processing")
            progress.set(label=patch.name)
        try:
            git("am", str(patch))
            if progress:
                progress.set_patch_status(patch.name, "done")
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
# Splash screen .inc generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_splash_inc(env: dict):
    """Run bmp_to_array.py to create boot_splash_kefir.inc in Atmosphere sources.

    This replaces the old approach of shipping the generated .inc inside the
    git patch (0001-KEFIR-Changed-bootscreen.patch).  The file is large (~11 MB)
    and depends on the user's custom splash image, so generating it at build
    time keeps the patch lean and makes the splash easily swappable.
    """
    splash_src = Path(env["SPLASH_BMP_PATH"])
    out_dir    = ATMOSPHERE_DIR / "stratosphere" / "boot" / "source"
    script     = SCRIPT_DIR / "utilities" / "bmp_to_array.py"

    log.info("Generating boot_splash_kefir.inc from %s", splash_src)

    if not splash_src.exists():
        raise FileNotFoundError(
            f"SPLASH_BMP_PATH not found: {splash_src}\n"
            "Check your .env — SPLASH_BMP_PATH must point to a valid BMP/PNG file."
        )
    if not out_dir.exists():
        raise FileNotFoundError(
            f"Atmosphere boot source dir not found: {out_dir}\n"
            "Make sure core patches were applied before calling generate_splash_inc()."
        )

    run(
        ["python3", str(script), str(splash_src), "SplashScreen", str(out_dir)],
        cwd=SCRIPT_DIR,
        check=True,
    )
    log.info("boot_splash_kefir.inc written to %s", out_dir)


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
# Deploy
# ─────────────────────────────────────────────────────────────────────────────

def deploy_core_artifacts(env: dict):
    """Copy core Atmosphere build output (atmosphere-out/) to KEFIR_ROOT_DIR/kefir/.

    Called immediately after `make nx_release`, before variant builds (8gb_DRAM,
    oc, 40mb) which each start with `make clean` and wipe the entire out/ tree.

    The output directory is out/<board>_<arch>_<sub>/release/atmosphere-out
    (ATMOSPHERE_VERSION := out => DIST_DIR = ATMOSPHERE_OUT_DIR/atmosphere-out).
    We search for it dynamically since ATMOSPHERE_OUT_DIR depends on board/arch.
    """
    log.info("=== Deploying core Atmosphere artifacts ===")
    out_base   = ATMOSPHERE_DIR / "out"
    candidates = list(out_base.rglob("atmosphere-out")) if out_base.exists() else []
    dist_dir   = next((c for c in candidates if c.is_dir()), None)
    kefir_dest = Path(env["KEFIR_ROOT_DIR"]) / "kefir"

    if not dist_dir:
        log.error("atmosphere-out not found under %s — core artifacts NOT deployed", out_base)
        return

    log.info("Core deploy source : %s", dist_dir)
    log.info("Core deploy target : %s", kefir_dest)

    try:
        kefir_dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        for src in dist_dir.rglob("*"):
            if src.is_file():
                rel  = src.relative_to(dist_dir)
                dst  = kefir_dest / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                log.info("  [deploy] %s  ->  %s", src, dst)
                copied += 1
        log.info("Core deploy complete: %d file(s) -> %s", copied, kefir_dest)
    except Exception as exc:
        log.error("Core deployment failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────────────────────

try:
    # sched_getaffinity(0) returns CPUs actually available to this process
    # (more accurate than os.cpu_count() in containers/WSL2/cgroups)
    NPROCS = len(os.sched_getaffinity(0))
except AttributeError:
    # Windows or systems without sched_getaffinity
    NPROCS = os.cpu_count() or 4


def build(env, patches_to_apply, adv_flag):
    # Use hardcoded estimation instead of slow source file counting
    total_files = _ESTIMATED_FILES

    reset_atmosphere()
    orig_branch, orig_head = save_state()

    # Count total patches for patch-phase progress
    patch_dirs = []
    if "core" in patches_to_apply: patch_dirs.append(PATCHES_DIR / "core")
    if "8gb" in patches_to_apply: patch_dirs.append(PATCHES_DIR / "8gb")
    if "oc" in patches_to_apply: patch_dirs.append(PATCHES_DIR / "oc")
    if "40mb" in patches_to_apply: patch_dirs.append(PATCHES_DIR / "40mb")
    
    all_patches = []
    for d in patch_dirs:
        if d.exists():
            for p in sorted(d.glob("*.patch")):
                all_patches.append(p.name)

    skipped_patches = set()
    if adv_flag and all_patches:
        skipped_patches = interactive_select(all_patches)

    active_variants = []
    for variant in patches_to_apply:
        variant_dir = PATCHES_DIR / variant
        if variant_dir.exists():
            variant_patches = {p.name for p in variant_dir.glob("*.patch")}
            if variant_patches and variant_patches.issubset(skipped_patches) and variant != "core":
                continue
        active_variants.append(variant)
    patches_to_apply = active_variants

    total_patches = max(1, len([p for p in all_patches if p not in skipped_patches]))
    patch_idx = [0]

    kef_version = read_version(env["KEFIR_ROOT_DIR"])
    make_vars = [
        f"KEFIROSPHERE_DIR={env['KEFIROSPHERE_DIR']}",
        f"KEFIR_ROOT_DIR={env['KEFIR_ROOT_DIR']}",
        f"SPLASH_LOGO_PATH={env['SPLASH_LOGO_PATH']}",
        f"SPLASH_BMP_PATH={env['SPLASH_BMP_PATH']}",
        f"LIBNX_DIR={env['LIBNX_DIR']}",
        f"NPROCS={NPROCS}",   # override Makefile's $(shell nproc) with our detected value
        f"KEF_VERSION={kef_version}",  # pass clean integer → patch uses ifdef KEF_VERSION branch, no shell cat
    ]

    prog = BuildProgress(total_files, all_patches, skipped_patches)
    _log_off()
    prog.start()

    success = False
    try:
        # Step 1 — core patches
        if "core" in patches_to_apply:
            prog.set(phase="Step 1/3 — Applying core patches",
                     branch="master", module="patches/core")
            apply_patches(PATCHES_DIR / "core", "core", prog, patch_idx, total_patches, skipped_patches)

        # Step 1b — generate splash .inc from user BMP (after core patches applied)
        if "core" in patches_to_apply:
            prog.set(phase="Step 1b/3 — Generating splash screen",
                     branch="master", module="bmp_to_array")
            generate_splash_inc(env)

        # Step 2 — variant branches
        for branch_name, patch_subdir in [("8gb_DRAM", "8gb"), ("oc", "oc"), ("40mb", "40mb")]:
            if patch_subdir not in patches_to_apply:
                continue
            prog.set(phase=f"Step 2/3 — Branch: {branch_name}",
                     branch=branch_name, module=f"patches/{patch_subdir}")
            git("checkout", "-b", branch_name)
            apply_patches(PATCHES_DIR / patch_subdir, branch_name, prog,
                          patch_idx, total_patches, skipped_patches)
            git("checkout", orig_branch)

        # Step 3 — compilation
        prog.set(phase="Step 3/3 — Compiling targets", branch="master", module="—")
        try:
            if "core" in patches_to_apply:
                # Run fetch_tools (kef_8gb_dir = KEFIR_ROOT_DIR/kefir/config/8gb, same as KEF_8GB_DIR in Makefile)
                kef_8gb_dir = str(Path(env["KEFIR_ROOT_DIR"]) / "kefir" / "config" / "8gb")
                run(["python3", str(SCRIPT_DIR / "utilities" / "fetch_tools.py"),
                     env["KEFIR_ROOT_DIR"], kef_8gb_dir], check=True)
                run_make(["make", "clean", f"-j{NPROCS}"] + make_vars, progress=prog)
                run_make(["make", "nx_release", f"-j{NPROCS}"] + make_vars, progress=prog)

                # Deploy core files NOW — before variant builds which run 'make clean'
                # and wipe out/ entirely (8gb_DRAM/oc/40mb targets start with make clean)
                deploy_core_artifacts(env)

                if "8gb" in patches_to_apply:
                    run_make(["make", "8gb_DRAM", "SKIP_FETCH=1", f"-j{NPROCS}"] + make_vars, progress=prog)
                if "oc" in patches_to_apply:
                    run_make(["make", "oc", f"-j{NPROCS}"] + make_vars, progress=prog)
                if "40mb" in patches_to_apply:
                    run_make(["make", "40mb", f"-j{NPROCS}"] + make_vars, progress=prog)
            else:
                # Without core patches, we just build pure atmosphere
                run_make(["make", "clean", f"-j{NPROCS}"] + make_vars, progress=prog)
                run_make(["make", "nx_release", f"-j{NPROCS}"] + make_vars, progress=prog)
                deploy_core_artifacts(env)
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

def parse_args():
    parser = argparse.ArgumentParser(description="Kefirosphere Build Script")
    parser.add_argument("--patches", nargs="*", default=["core", "8gb", "oc", "40mb"],
                        help="Which patches to apply and build. E.g. --patches core 8gb. Pass empty (e.g. without arguments if using a wrapper) for clean Atmosphere.")
    parser.add_argument("--adv", action="store_true", help="Advanced options. Interactive TUI patch selection.")
    return parser.parse_args()


def main():
    args = parse_args()

    log.info("=" * 60)
    log.info("Kefirosphere Build — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("  Atmosphere : %s", ATMOSPHERE_DIR)
    log.info("  Patches    : %s", PATCHES_DIR)
    log.info("  Variants   : %s", args.patches if args.patches else "None (Clean)")
    log.info("  CPU cores  : %d (parallel jobs)", NPROCS)
    log.info("=" * 60)

    if not ATMOSPHERE_DIR.exists():
        log.error("Atmosphere directory not found: %s", ATMOSPHERE_DIR)
        sys.exit(1)

    env = load_env()
    ok  = build(env, args.patches, args.adv)
    log.info("Log: %s", LOG_FILE)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
