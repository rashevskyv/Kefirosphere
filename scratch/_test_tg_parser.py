import sys
from pathlib import Path
sys.path.insert(0, 'utilities')
import telegram_post as tp

cfg = tp.load_env()
ver_path = Path(cfg['KEFIR_ROOT_DIR']) / "version"
ver = tp.get_current_kefir_version(cfg['KEFIR_ROOT_DIR'])

print(f"Reading from: {ver_path}")
print(f"Value: |{ver}|")

ukr, eng = tp.parse_localized_changelog(cfg['KEFIR_ROOT_DIR'], ver)

print(f"--- VERSION: {ver} ---")
print("--- UKR ---")
print(ukr)
print("--- ENG ---")
print(eng)
