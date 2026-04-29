import os
import sys
import subprocess
from pathlib import Path

try:
    import msvcrt
except ImportError:
    msvcrt = None

def get_current_version():
    """Read current Kefir version from version file."""
    try:
        # Try to find version file in parent directory (_kefir structure)
        version_paths = [
            Path(__file__).resolve().parent.parent / "_kefir" / "version",
            Path("D:/git/dev/_kefir/version"),
        ]
        for version_file in version_paths:
            if version_file.exists():
                return version_file.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return "unknown"


def renumber_selections(selected_order):
    """Renumber selections to be sequential (1, 2, 3, ...) based on current order."""
    if not selected_order:
        return {}

    # Sort by current order value
    sorted_items = sorted(selected_order.items(), key=lambda x: x[1])

    # Reassign sequential numbers
    return {idx: i + 1 for i, (idx, _) in enumerate(sorted_items)}


def get_latest_github_version():
    """Get latest release tag from GitHub."""
    try:
        # Load .env to get repo info
        env_file = Path(__file__).resolve().parent / ".env"
        if env_file.exists():
            env_vars = {}
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env_vars[key.strip()] = val.strip().strip("\"'")

            owner = env_vars.get("RELEASE_REPO_OWNER", "rashevskyv")
            repo = env_vars.get("RELEASE_REPO_NAME", "kefir")

            # Use git ls-remote to get latest tag (faster than API)
            result = subprocess.run(
                ["git", "ls-remote", "--tags", "--sort=-v:refname",
                 f"https://github.com/{owner}/{repo}.git"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0 and result.stdout:
                # Parse first tag (latest)
                for line in result.stdout.splitlines():
                    if "refs/tags/" in line and "^{}" not in line:
                        tag = line.split("refs/tags/")[1].strip()
                        # Remove 'v' prefix if present
                        return tag.lstrip("v")

    except Exception:
        pass
    return "unknown"

def get_key():
    if msvcrt is not None:
        key = msvcrt.getch()
        if key in (b'\xe0', b'\x00'):
            c2 = msvcrt.getch()
            if c2 == b'H': return 'UP'
            if c2 == b'P': return 'DOWN'
            if c2 == b'K': return 'LEFT'
            if c2 == b'M': return 'RIGHT'
            return None
        if key == b' ': return 'SPACE'
        if key == b'\r': return 'ENTER'
        if key == b'\x08': return 'BACKSPACE'
        if key == b'\x03': return 'CTRL_C'
        if key.isdigit() and key != b'0':
            return key.decode()
        if key.lower() == b'd': return 'D'
        if key.lower() == b'c': return 'C'
        return None
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                c2 = sys.stdin.read(2)
                if c2 == '[A': return 'UP'
                if c2 == '[B': return 'DOWN'
                if c2 == '[D': return 'LEFT'
                if c2 == '[C': return 'RIGHT'
                return None
            if ch == ' ': return 'SPACE'
            if ch in ('\r', '\n'): return 'ENTER'
            if ch in ('\x08', '\x7f'): return 'BACKSPACE'
            if ch == '\x03': return 'CTRL_C'
            if ch.isdigit() and ch != '0': return ch
            if ch.lower() == 'd': return 'D'
            if ch.lower() == 'c': return 'C'
            return None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

def main():
    # Detect the root directory where the script is located
    root_dir = Path(__file__).resolve().parent
    utils_dir = root_dir / "utilities"
    
    if not utils_dir.exists() or not utils_dir.is_dir():
        print(f"Error: Directory '{utils_dir}' not found.")
        sys.exit(1)

    # Exclude certain helper files that are modules, not runnable scripts
    excluded_scripts = {
        "__init__.py",
        "state_manager.py",
        "bmp_to_array.py",
        "insert_splash_screen.py",
        "changelog_manager.py"  # Main script with CLI args, use wrappers instead
    }
    
    # Get all python scripts in utilities directory
    script_files = [
        f for f in utils_dir.iterdir() 
        if f.is_file() and f.suffix == '.py' and f.name not in excluded_scripts
    ]
    
    # Add build.py from the root directory if it exists
    build_script = root_dir / "build.py"
    if build_script.exists() and build_script.is_file():
        script_files.append(build_script)

    # Define script groups and order
    script_groups = {
        "Build & Fetch": [
            "build.py",
            "build_package.py",
            "fetch_tools.py",
        ],
        "Version & Release": [
            "bump_version.py",
            "cover_builder.py",
            "github_release.py",
            "telegram_post.py",
        ],
        "Changelog Management": [
            "collect_changelogs.py",
            "update_changelog.py",
            "sort_changelog.py",
        ],
    }

    # Default pipeline (script_name -> order)
    default_pipeline = {
        "build.py": 1,
        "fetch_tools.py": 2,
        "cover_builder.py": 3,
        "update_changelog.py": 4,
        "sort_changelog.py": 5,
        "build_package.py": 6,
        "github_release.py": 7,
        "telegram_post.py": 8,
        "bump_version.py": 9,
    }

    # Create ordered list with group headers
    ordered_scripts = []
    group_headers = {}  # idx -> group name

    for group_name, group_scripts in script_groups.items():
        # Add group header marker
        group_start_idx = len(ordered_scripts)
        group_headers[group_start_idx] = group_name

        # Add scripts from this group
        for script_name in group_scripts:
            script_path = next((s for s in script_files if s.name == script_name), None)
            if script_path:
                ordered_scripts.append(script_path)

    # Add any remaining scripts not in groups (as "Other")
    remaining = [s for s in script_files if s not in ordered_scripts]
    if remaining:
        group_start_idx = len(ordered_scripts)
        group_headers[group_start_idx] = "Other"
        ordered_scripts.extend(sorted(remaining, key=lambda f: f.name))

    script_files = ordered_scripts

    if not script_files:
        print("No Python scripts found in the utilities directory.")
        sys.exit(0)

    # Initialize with default pipeline
    selected_order = {}  # idx -> order number
    for idx, script in enumerate(script_files):
        if script.name in default_pipeline:
            selected_order[idx] = default_pipeline[script.name]

    current_pos = 0

    # Get version info once at start
    current_version = get_current_version()
    latest_version = get_latest_github_version()

    while True:
        # Clear console
        os.system('cls' if os.name == 'nt' else 'clear')

        print("=" * 50)
        print("Available utility scripts:")
        print("=" * 50)
        print(f"  Current version: {current_version}")
        print(f"  Latest release:  {latest_version}")
        print("=" * 50)

        for idx, script in enumerate(script_files):
            # Print group header if this index has one
            if idx in group_headers:
                if idx > 0:  # Add spacing before group (except first)
                    print()
                print(f"\n  [{group_headers[idx]}]")
                print("  " + "-" * 46)

            cursor = " > " if idx == current_pos else "   "
            order_mark = f"[{selected_order[idx]}]" if idx in selected_order else "[ ]"
            print(f"{cursor}{order_mark} {script.name}")
            
        print("=" * 50)
        print("Use UP/DOWN arrows to navigate.")
        print("Press LEFT/RIGHT to change order of selected item.")
        print("Press SPACE to toggle selection and assign order.")
        print("Press a NUMBER (1-9) to manually assign order.")
        print("Press D to load default pipeline.")
        print("Press C to clear all selections.")
        print("Press ENTER to confirm and proceed.")
        print("Press Ctrl+C to abort.")

        try:
            key = get_key()
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(0)
            
        if key == 'UP':
            current_pos = max(0, current_pos - 1)
        elif key == 'DOWN':
            current_pos = min(len(script_files) - 1, current_pos + 1)
        elif key == 'LEFT':
            # Decrease order number (move earlier in sequence)
            if current_pos in selected_order and selected_order[current_pos] > 1:
                current_order = selected_order[current_pos]
                # Find item with order = current_order - 1 and swap
                for idx, order in selected_order.items():
                    if order == current_order - 1:
                        selected_order[idx] = current_order
                        break
                selected_order[current_pos] = current_order - 1
        elif key == 'RIGHT':
            # Increase order number (move later in sequence)
            if current_pos in selected_order:
                current_order = selected_order[current_pos]
                max_order = max(selected_order.values()) if selected_order else 1
                if current_order < max_order:
                    # Find item with order = current_order + 1 and swap
                    for idx, order in selected_order.items():
                        if order == current_order + 1:
                            selected_order[idx] = current_order
                            break
                    selected_order[current_pos] = current_order + 1
        elif key == 'SPACE':
            if current_pos not in selected_order:
                next_num = max(selected_order.values()) + 1 if selected_order else 1
                selected_order[current_pos] = next_num
            else:
                del selected_order[current_pos]
                # Renumber remaining selections
                selected_order = renumber_selections(selected_order)
        elif key == 'ENTER':
            if not selected_order:
                # If nothing selected, just exit
                os.system('cls' if os.name == 'nt' else 'clear')
                print("Exiting.")
                sys.exit(0)
            else:
                os.system('cls' if os.name == 'nt' else 'clear')
                break
        elif key == 'BACKSPACE':
            if current_pos in selected_order:
                del selected_order[current_pos]
                # Renumber remaining selections
                selected_order = renumber_selections(selected_order)
        elif key and key.isdigit():
            num = int(key)
            # Remove this number from any other selected script
            for k, v in list(selected_order.items()):
                if v == num:
                    del selected_order[k]
            selected_order[current_pos] = num
        elif key == 'D':
            # Load default pipeline
            selected_order.clear()
            for idx, script in enumerate(script_files):
                if script.name in default_pipeline:
                    selected_order[idx] = default_pipeline[script.name]
        elif key == 'C':
            # Clear all selections
            selected_order.clear()
        elif key == 'CTRL_C':
            print("\nAborted.")
            sys.exit(0)

    sorted_selection = sorted(selected_order.items(), key=lambda x: x[1])
    selected_scripts = [script_files[idx] for idx, _ in sorted_selection]

    print("\nExecution plan:")
    for idx, script in enumerate(selected_scripts, 1):
        print(f"  {idx}. {script.name}")


    # Run the selected scripts
    for script in selected_scripts:
        print(f"\n[>>>] Starting {script.name}...")
        print("-" * 50)
        try:
            # Setting the working directory to root_dir so tools run correctly
            subprocess.run([sys.executable, str(script)], cwd=root_dir, check=True)
            print("-" * 50)
            print(f"[OK] {script.name} finished successfully.")
        except subprocess.CalledProcessError as e:
            print("-" * 50)
            print(f"[FAIL] {script.name} failed with exit code {e.returncode}.")
            print("\nAborting the remaining sequence.")
            sys.exit(1)
        except Exception as e:
            print("-" * 50)
            print(f"[FAIL] Error starting {script.name}: {str(e)}")
            print("\nAborting the remaining sequence.")
            sys.exit(1)

if __name__ == "__main__":
    main()
