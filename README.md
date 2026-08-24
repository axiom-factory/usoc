# USoC: An IoT SoC for a WASM userspace.

![](docs/architecture.png)

- **UMM (Userspace Memory Management):** Enforces WebAssembly linear memory bounds
checking and maps 64KB WASM pages directly into physical RAM. Because the translation
table is sized statically for `MAX_RAM / 64KB`, context switches require zero TLB
flushing - swapping tasks requires updating just four control registers alongside
the CPU registers and PC.
- **UMAC (Unified MAC):** A streamlined media access controller that does only
what a MAC should do. By stripping out legacy protocol bloat, it focuses strictly
on CRC checking and hardware retransmissions over a PHY-agnostic PIPE interface.
- **UBUS (Streaming DMA Matrix):** Our packet-driven DMA controller. It eliminates
traditional bus contention by routing data packets directly to peripheral FIFO
queues based on explicit flow credits and negotiated time slices.
- **USYS (System Fabric):** A formally verified, arbitration-free system interconnect.
Because every peripheral communicates over a standardized packet based FIFO interface,
individual hardware drivers are pushed entirely out of the kernel and run securely
inside sandboxed WASM user space.
- **USoC (The Complete SoC):** The concrete integration of this fabric, dropping
in a stock RV32IM core and targeting low-cost, accessible iCE40 and ECP5 FPGAs.

## 🗺️ The Horizon: Designed to Scale

While the initial focus is finalizing this single-core implementation, the
underlying USYS fabric was architected from day one to scale.

![](docs/smp-architecture.png)

## 🛰️ Follow the Journey & Progress Reports

This project is being designed, formally verified, and blogged about in real
time. If you want to see the dirty details of how the SoC and microkernel are
being built, follow along:

* **Read the deep-dives on the Blog:** [https://craven.ch]
* **Follow live progress updates:** [https://x.com/dvc94ch]

## 🛠️ Getting Started

You'll need some dependencies like yosys, nextpnr, sby, yices and gtkwave. Once
you have your toolchain ready you can clone and run formal verification and
timing tests yourself.

```bash
git clone https://github.com/axiom-factory/usys
cd usys
pixi install
pixi shell
```

Every component is in its own file and can be formally verified by running
it in python.

```
python usys/wishbone/fabric.py
```

Timing requires a wrapper to ensure all the inputs and outputs are driven
and yosys doesn't just optimize the design away.

```
python usys/wishbone/fabric_timing.py
```

## Licensing & Third Party Contributions
Copyright (C) 2026 David Craven. All rights reserved.

This gateware is dual-licensed. You may use it under the terms of:
1. The GNU General Public License v3.0 (see LICENSE-GPL.txt)
    OR
2. A commercial license obtained directly from `david@craven.ch`.

If you wish to use this IP in a proprietary product without disclosing
your top-level RTL source code, you must purchase a commercial license.

Shipping a binary bitstream, flashing an EEPROM on a sold PCB, or distributing
an ASIC containing IP from this repository counts as "distribution" under my
interpretation of the GPL.

At this time we do not accept external contributions due to not having a
CLA. Please open issues if you encounter a bug, and if there is a serious
commercial interest in contributing, contact me at `david@craven.ch` so we
may discuss creating a CLA.

