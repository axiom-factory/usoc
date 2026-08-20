# USYS & USoC: A Wasm-Native, Zero-Arbitration Silicon Architecture

<!--[![Fabric Verification](https://shields.io)](#)
[![Fmax ECP5](https://shields.io)](#)
[![Fmax iCE40](https://shields.io)](#)-->

Welcome to the future of deterministic, sandboxed edge computing. 

**USYS** is a formally verified, completely arbitration-free system fabric
written in Amaranth HDL. By treating memory and peripheral I/O as structured,
isolated streams, it eliminates the "legacy tax" of traditional microcontrollers. 

**USoC** is the flagship implementation of this fabric: an ultra-lean, secure
RISC-V microcontroller built from the ground up to execute sandboxed WebAssembly
applications at hardware speed.

---

## ⚡ The Phase 1 MVP Features

We are currently executing **Phase 1** of our architecture roadmap, focusing on
a high-frequency, rock-solid hardware foundation paired with a minimal microkernel.

* **Arbitration-Free Dual-Port RAM:** The CPU owns Port A of the I-RAM and D-RAM
with zero wait-states. The streaming DMA engine owns Port B. Bus matrix contention
is entirely eliminated.
* **Blistering Clock Speeds:** Because of our lean, un-arbitrated routing paths,
the fabric closes timing at a phenomenal **253 MHz on a Lattice ECP5** and
**137 MHz on an iCE40**.
* **Hardware-Accelerated Wasm Sandboxing (UMM):** Address translation, boundary
checks, and memory expansion (`memory.grow`) are enforced directly in the memory
pipeline via single-cycle bitwise masking. 
* **Packet-Based, Stream-Driven Peripherals:** All peripheral I/O is handled via
structured packet streams over our custom DMA (**UBUS**). We have completely
eliminated the need for external interrupt controllers like a PLIC or APLIC.
* **Leanest Software Driver Stack:** Because peripherals use packet-based network
protocols, the Machine-Mode microkernel is ultra-tiny. Drivers can be written in
safe languages (Rust, C, Zig) and run completely inside sandboxed Wasm user space.

---

## 🏗️ Architecture Overview

![](docs/architecture.png)

### The USYS vs. USoC Boundary
1. **USYS (The System Fabric):** The core invariant infrastructure. It houses
the dual-port memory boundaries, the **UMM** memory management hardware, the
**UBUS** streaming matrix, and our unified data-link layer (**UMAC**).
2. **USoC (The Complete SoC):** A concrete instance of the fabric. For the Phase
1 MVP, it drops in a reliable, stock **RV32IM core** and wires up our first
packet-based protocol translation cores:
   * `blk` ──► **QSPI Flash** (Block-to-SPI command streaming)
   * `input` ──► **UART** (Emulate a keyboard device over UART)

---

## 🗺️ The Horizon: Designed to Scale

While we are laser-focused on finalizing the Phase 1 MVP, the USYS fabric was
architected from day one to scale.

![](docs/smp-architecture.png)

Our internal blueprints detail a clear evolutionary path from this single-core
edge node to a multi-core, cache-coherent SMP cluster utilizing an advanced vector
and bit-manipulation core matrix. Later stages of our private roadmap introduce
unified software-defined radio physical layers (`SdrPhy`) to natively obsolete
legacy connectivity bloat, alongside a completely sandboxed userspace storage
engine.

We are building this piece by piece, proving the math and the timing closures
at every single step.

---

## 🛰️ Follow the Journey & Progress Reports

This project is being designed, formally verified, and blogged about in real
time. If you want to see the dirty details of how we closed timing at 253 MHz,
how the formal verification properties are structured, or how the microkernel
context switcher is written, follow along:

* **Read the deep-dives on the Blog:** [https://craven.ch]
* **Follow live progress updates:** [https://x.com/dvc94ch]

---

## 🛠️ Getting Started (Phase 1 Prototyping)

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

