# USoC: An IoT SoC for a WASM userspace.

A few weeks ago, I started researching and outlining a book called *The Whole
Machine*. The goal is to teach teenagers - specifically my son, when he gets a
bit older - how to build a computer entirely from scratch.

I don't mean "understand the concepts." True understanding only comes from
building, which means the goal of the book is to write every single line of code
and hardware description from scratch. No massive third-party libraries, no
closed-source IP blocks, no hand-waving.

To make it possible for a teenager to actually build a complete machine from the
ground up, you have to radically simplify everything. You have to aggressively
slice away the historical cruft and unnecessary complexity that plages modern
commercial architectures. But a funny thing happened during those first two
weeks of conceptual design: I looked at the blueprint and realized it wasn't
just an educational toy. By forcing myself to strip the architecture down to a
level where every single line could be built from scratch, I had accidentally
designed what I believe is the future of embedded computing.

I immediately shifted gears. Under the moniker AxiomFactory, I am turning that
blueprint into a next-generation, WebAssembly-based IoT platform.

The current architecture is split into clean, hardware boundaries designed to
run these sandboxed workloads at hardware speed:

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
pixi run test
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

