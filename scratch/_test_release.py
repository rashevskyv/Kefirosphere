import sys
sys.path.insert(0, 'utilities')
import github_release as gr

# Mock run_gh to not actually call GitHub
import subprocess
def mock_run_gh(*args, **kwargs):
    return subprocess.CompletedProcess(args, 0, stdout='813', stderr='')
gr.run_gh = mock_run_gh

cfg = gr.load_env()
ver = gr.get_kefir_version(cfg['KEFIR_ROOT_DIR'])
atmo = gr.get_atmosphere_version()
state = gr.read_state().get('ATMOSPHERE_LATEST_VERSION')
hekate = gr.get_hekate_version()

print(f'Kefir ver       : {ver}')
print(f'Atmosphere live : {atmo}')
print(f'Atmosphere state: {state}')
print(f'Hekate          : {hekate}')
print(f'Mode            : {"NEW" if atmo != state else "EDIT"}')

assets = gr.collect_assets(cfg['KEFIR_ROOT_DIR'])
print(f'Assets ({len(assets)}):')
for a in assets:
    print(f'  {a.name}')

body = gr.build_release_body(ver, cfg['RELEASE_REPO_OWNER'], cfg['RELEASE_REPO_NAME'], atmo, hekate, '...')
print(f'Body length     : {len(body)} chars')
print('DRY RUN OK')
