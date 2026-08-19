from amaranth import Module
from amaranth.asserts import Assert
from amaranth.lib import wiring
from amaranth.lib.wiring import Component, In, Out, Signature
from usys.wishbone.interface import (
    wishbone_signature, 
    WishboneMasterFormalChecker, 
    WishboneSlaveFormalChecker
)


class WishboneDecoder(Component):
    def __init__(self, slave0_addr: int, slave0_size: int, slave1_addr: int, slave1_size: int):
        """
        Combinatorial 2-Port Wishbone Decoder.
        
        Parameters:
            slave0_addr: Starting 30-bit Word Address for Slave 0
            slave0_size: Range size in 32-bit Words
            slave1_addr: Starting 30-bit Word Address for Slave 1
            slave1_size: Range size in 32-bit Words
        """
        self.slave0_addr = slave0_addr
        self.slave0_size = slave0_size
        self.slave1_addr = slave1_addr
        self.slave1_size = slave1_size

        wb_sig = wishbone_signature()
        signature = Signature({
            "master":    In(wb_sig),
            "slave0":    Out(wb_sig),
            "slave1":    Out(wb_sig),
            "bus_error": Out(1) # Out-of-band trap pin back to the RISC-V Core
        })
        super().__init__(signature)

    def elaborate(self, platform):
        m = Module()
        master = self.master
        slave0 = self.slave0
        slave1 = self.slave1
        bus_error = self.bus_error

        # 1. Address Match Decoding (Combinatorial evaluation on 30-bit Word bounds)
        slave0_match = (master.addr >= self.slave0_addr) & (master.addr < (self.slave0_addr + self.slave0_size))
        slave1_match = (master.addr >= self.slave1_addr) & (master.addr < (self.slave1_addr + self.slave1_size))

        # 2. Pure Combinatorial Multiplexing and Gating Matrix
        with m.If(master.stb):
            with m.If(slave0_match):
                # Route cleanly to Slave 0 (D-SRAM Port A)
                m.d.comb += [
                    slave0.stb.eq(master.stb),
                    slave0.we.eq(master.we),
                    slave0.addr.eq(master.addr - self.slave0_addr),
                    slave0.sel.eq(master.sel),
                    slave0.dat_w.eq(master.dat_w),
                    master.dat_r.eq(slave0.dat_r),
                    master.ack.eq(slave0.ack),
                    master.stall.eq(slave0.stall),
                    bus_error.eq(0),
                ]
            with m.Elif(slave1_match):
                # Route cleanly to Slave 1 (UBUS-CSR MMIO)
                m.d.comb += [
                    slave1.stb.eq(master.stb),
                    slave1.we.eq(master.we),
                    slave1.addr.eq(master.addr - self.slave1_addr),
                    slave1.sel.eq(master.sel),
                    slave1.dat_w.eq(master.dat_w),
                    master.dat_r.eq(slave1.dat_r),
                    master.ack.eq(slave1.ack),
                    master.stall.eq(slave1.stall),
                    bus_error.eq(0),
                ]
            with m.Else():
                # TRAP ZONE: Catches unmapped lookups instantly on the active
                # strobe cycle.
                # Auto-assert ACK to let the transaction finish instantly
                # (no bus freeze).
                # force DEADBEEF down the line, and assert the out-of-band CPU
                # fault trap line.
                m.d.comb += [
                    master.ack.eq(1),
                    master.dat_r.eq(0xDEADBEEF),
                    master.stall.eq(0),
                    bus_error.eq(1),
                ]
        with m.Else():
            # If the master is quiet, the whole fabric is quiet
            m.d.comb += master.ack.eq(0)
            m.d.comb += bus_error.eq(0)

        # ---------------------------------------------------------
        # FORMAL CONTRACT INTEGRITY PROOFS
        # ---------------------------------------------------------
        if platform == "formal":
            # Instantiate our formal checkers to verify the decoder's
            # interfaces.
            m.submodules.master_verify = WishboneMasterFormalChecker(master.signature)
            m.submodules.slave0_verify = WishboneSlaveFormalChecker(slave0.signature)
            m.submodules.slave1_verify = WishboneSlaveFormalChecker(slave1.signature)

            # Rule A: Cross-Bleed Routing Invariant
            # Prove that the master can NEVER physically activate both slaves
            # at the same time.
            with m.If(master.stb):
                m.d.comb += Assert(~(slave0.stb & slave1.stb))

            # Rule B: Destination Separation Guarantee
            # Prove that if an address targets Slave 0, Slave 1 must hear
            # absolute silence.
            with m.If(master.stb & slave0_match):
                m.d.comb += Assert(slave1.stb == 0)

            # Rule C: Destination Separation Guarantee (Inverse)
            with m.If(master.stb & slave1_match):
                m.d.comb += Assert(slave0.stb == 0)

            # Rule D: Out-of-bounds Trap Isolation Invariant
            # Prove that the bus_error line can only be raised if an invalid
            # strobe fired.
            with m.If(bus_error):
                m.d.comb += [
                    Assert(master.stb),
                    Assert(~slave0_match),
                    Assert(~slave1_match)
                ]

        return m


if __name__ == '__main__':
    from usys.build.formal import run_formal
    decoder = WishboneDecoder(
        slave0_addr=0x00000000, slave0_size=4096,
        slave1_addr=0x10000000, slave1_size=64
    )
    run_formal(decoder)
