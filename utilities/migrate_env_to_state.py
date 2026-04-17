import os
import sys

env_path = r'D:\git\dev\Kefirosphere\.env'
sys.path.append(r'D:\git\dev\Kefirosphere\utilities')
from state_manager import state

with open(env_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        new_lines.append(line)
        continue
    
    if '_LATEST_' in line or 'HOS_VERSION=' in line:
        key, val = stripped.split('=', 1)
        val = val.strip('"')
        state.set(key, val)
        print(f'Migrated {key} = {val}')
    else:
        new_lines.append(line)

with open(env_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Migration complete, .env cleaned.')
