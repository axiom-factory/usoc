import subprocess
from pathlib import Path
from amaranth.back import verilog
from amaranth.lib.wiring import Signal


def extract_raw_signals(obj):
    '''
    Recursively drills through components, interfaces, and signature bundles
    to extract only the base Signal primitives for the Verilog compiler.
    '''
    signals = []
    if isinstance(obj, Signal):
        signals.append(obj)
    elif hasattr(obj, "signature") and hasattr(obj.signature, "members"):
        for member_name in obj.signature.members.keys():
            signals.extend(extract_raw_signals(getattr(obj, member_name)))
    return signals


def _run_toolchain(top, family: str, nextpnr_cmd_args: list, target_dir: Path):
    '''
    Internal driver engine that compiles Amaranth component objects,
    runs Yosys synthesis, and executes nextpnr timing mapping.
    '''
    name = top.__class__.__name__
    build_dir = target_dir / family / name
    build_dir.mkdir(parents=True, exist_ok=True)

    v_file = build_dir / f'{name}.v'
    json_file = build_dir / f'{name}.json'
    config_file = build_dir / f'{name}.config'

    ports = extract_raw_signals(top)

    # 1. Compile Amaranth component definition straight to structural Verilog
    print(f'[*] Compiling Amaranth {name} to structural Verilog...')
    with open(v_file, 'w') as f:
        f.write(verilog.convert(top, ports=ports))

    # 2. Invoke Yosys Synthesis target mapping
    print(f'[*] Dispatching Yosys synthesis for {family} architecture...')
    yosys_synth_flag = 'synth_ecp5' if family == 'ecp5' else 'synth_ice40'
    yosys_cmd = [
        'yosys', '-p', 
        f'read_verilog {v_file}; {yosys_synth_flag} -json {json_file}'
    ]
    subprocess.run(yosys_cmd, check=True)

    # 3. Invoke nextpnr Place-and-Route backend engine
    print(f'[*] Dispatching nextpnr-{family} layout engine...')
    base_nextpnr_cmd = [
        f'nextpnr-{family}',
        '--json', str(json_file),
    ]
    # Append family-specific device package and constraint array arguments
    base_nextpnr_cmd.extend(nextpnr_cmd_args)
    
    # Run the compilation toolchain
    subprocess.run(base_nextpnr_cmd, check=True)
    print(f'[SUCCESS] {name} synthesis done on {family}. View logs in {build_dir}\n')


def build_ecp5(top, freq, target_dir=Path("target")):
    '''
    Synthesizes and routes a component targeting an ECP5-5G LFE5UM5G-85F chip.
    '''
    name = top.__class__.__name__
    build_dir = target_dir / 'ecp5' / name
    build_dir.mkdir(parents=True, exist_ok=True)

    lpf_path = build_dir / f'{name}.lpf'
    with open(lpf_path, 'w') as f:
        f.write(f'FREQUENCY NET "clk" {freq} MHz;\n')

    # Configure hardware parameters for standard ECP5 evaluation boards
    args = [
        '--um5g-85k',
        '--package', 'CABGA381',
        '--speed', '8',
        '--lpf', str(lpf_path),
        '--lpf-allow-unconstrained',
        '--textcfg', str(build_dir / f'{name}.config')
    ]
    _run_toolchain(top, "ecp5", args, target_dir)


def build_ice40(top, freq, target_dir=Path("target")):
    '''
    Synthesizes and routes a component targeting a iCE40 HX8K chip.
    '''
    name = top.__class__.__name__
    build_dir = target_dir / 'ice40' / name
    build_dir.mkdir(parents=True, exist_ok=True)

    pcf_path = build_dir / f'{name}.pcf'
    with open(pcf_path, 'w') as f:
        f.write(f'set_frequency clk {freq}\n')

    # Configure hardware parameters targeting a generic iCE40 HX8K CT256 break-out board
    args = [
        '--hx8k',
        '--package', 'ct256',
        '--pcf', str(pcf_path),
        '--pcf-allow-unconstrained',
        '--asc', str(build_dir / f'{name}.asc')
    ]
    _run_toolchain(top, 'ice40', args, target_dir)
