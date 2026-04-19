import os
import sys
import subprocess
from pathlib import Path

try:
    import msvcrt
except ImportError:
    msvcrt = None

def main():
    # Detect the root directory where the script is located
    root_dir = Path(__file__).resolve().parent
    utils_dir = root_dir / "utilities"
    
    if not utils_dir.exists() or not utils_dir.is_dir():
        print(f"Error: Directory '{utils_dir}' not found.")
        sys.exit(1)

    # Exclude certain helper files that are modules, not runnable scripts
    excluded_scripts = {"__init__.py", "state_manager.py", "bmp_to_array.py", "insert_splash_screen.py"}
    
    # Get all python scripts in utilities directory
    script_files = [
        f for f in utils_dir.iterdir() 
        if f.is_file() and f.suffix == '.py' and f.name not in excluded_scripts
    ]
    
    # Add build.py from the root directory if it exists
    build_script = root_dir / "build.py"
    if build_script.exists() and build_script.is_file():
        script_files.append(build_script)
        
    custom_order = {
        "build.py": 1,
        "fetch_tools.py": 2,
        "cover_builder.py": 3,
        "bump_version.py": 4
    }
    script_files = sorted(script_files, key=lambda f: custom_order.get(f.name, 99))
    
    if not script_files:
        print("No Python scripts found in the utilities directory.")
        sys.exit(0)

    selected_order = {}  # idx -> order number
    current_pos = 0

    while True:
        # Clear console
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("=" * 50)
        print("Available utility scripts:")
        print("=" * 50)
        
        for idx, script in enumerate(script_files):
            cursor = " > " if idx == current_pos else "   "
            order_mark = f"[{selected_order[idx]}]" if idx in selected_order else "[ ]"
            print(f"{cursor}{order_mark} {script.name}")
            
        print("=" * 50)
        print("Use UP/DOWN arrows to navigate.")
        print("Press SPACE to toggle selection and assign order.")
        print("Press a NUMBER (1-9) to manually assign order.")
        print("Press ENTER to confirm and proceed.")
        print("Press Ctrl+C to abort.")

        if msvcrt is None:
            # Fallback for non-Windows
            print("Error: msvcrt not available. This interactive menu requires Windows.")
            sys.exit(1)
            
        try:
            key = msvcrt.getch()
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(0)
            
        if key in (b'\xe0', b'\x00'): # special keys like arrows
            key = msvcrt.getch()
            if key == b'H': # UP
                current_pos = max(0, current_pos - 1)
            elif key == b'P': # DOWN
                current_pos = min(len(script_files) - 1, current_pos + 1)
        elif key == b' ': # Space
            if current_pos not in selected_order:
                next_num = max(selected_order.values()) + 1 if selected_order else 1
                selected_order[current_pos] = next_num
                current_pos = min(len(script_files) - 1, current_pos + 1)
            else:
                del selected_order[current_pos]
        elif key == b'\r': # Enter
            if not selected_order:
                # If nothing selected, just exit
                os.system('cls' if os.name == 'nt' else 'clear')
                print("Exiting.")
                sys.exit(0)
            else:
                os.system('cls' if os.name == 'nt' else 'clear')
                break
        elif key == b'\x08': # Backspace
            if current_pos in selected_order:
                del selected_order[current_pos]
        elif key.isdigit() and key != b'0': # 1-9
            num = int(key.decode())
            # Remove this number from any other selected script
            for k, v in list(selected_order.items()):
                if v == num:
                    del selected_order[k]
            selected_order[current_pos] = num
            current_pos = min(len(script_files) - 1, current_pos + 1)
        elif key == b'\x03': # Ctrl+C
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
