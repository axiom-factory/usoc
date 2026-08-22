import os
from pathlib import Path
import subprocess
from amaranth.back import rtlil


def build_rtlil(top, platform='formal', target_dir=Path('target')):
    '''
    Compiles the Amaranth to Yosys RTLIL. If the platform == 'formal' it
    generates a sby script.
    '''

    name = top.__class__.__name__
    build_dir = target_dir / platform / name
    os.makedirs(build_dir, exist_ok=True)
    
    print(f'[*] Generating Yosys RTLIL for platform {platform}...')
    rtlil_text = rtlil.convert(top, platform=platform, ports=[])
    
    rtlil_path = build_dir / f'{name}.il'
    with open(rtlil_path, 'w') as f:
        f.write(rtlil_text)

    print(f'[+] Successfully wrote target/{platform}/{name}/{name}.il')
    return build_dir


def build_formal(top, target_dir=Path('target')):
    name = top.__class__.__name__
    build_dir = build_rtlil(top, platform='formal', target_dir=target_dir)
    sby_script = f'''
[tasks]
bmc
cover

[options]
bmc: mode bmc
cover: mode cover
depth 20

[engines]
smtbmc yices

[script]
read_rtlil {name}.il
prep -top top

[files]
{name}.il
'''
    sby_path = build_dir / f'{name}.sby'
    with open(sby_path, 'w') as f:
        f.write(sby_script)
    print(f'[+] Successfully wrote target/formal/{name}/{name}.sby')
    return sby_path


def _run_sby_task(sby_path, task):
    name = sby_path.name
    print(f'[*] Running {task}...')
    result = subprocess.run(['sby', '-f', '-d', task, '-T', task, f'{name}'], cwd=str(sby_path.parent))
    print("-" * 60)
    if result.returncode == 0:
        print(f'[SUCCESS] {task}')
    else:
        print(f'[FAIL] {task}')
        print(f"[*] Inspect the '{sby_path}' directory for failure traces.")
    print("-" * 60)


def run_formal(top, target_dir=Path('target')):
    '''
    Invokes sby directly from the shell environment.
    '''
    sby_path = build_formal(top, target_dir=target_dir)
    _run_sby_task(sby_path, 'bmc')
    _run_sby_task(sby_path, 'cover')
