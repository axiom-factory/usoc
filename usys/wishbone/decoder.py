from amaranth import Module, Signal
from amaranth.hdl import Assert, Cover
from amaranth.lib import wiring
from amaranth.lib.wiring import Component, In, Out, Signature
import math
from usys.wishbone.interface import (
    wishbone_signature,
    WishboneMasterFormal,
    WishboneSlaveFormal,
)


class WishboneDecoder(Component):
    def __init__(self, slave0_addr: int, slave0_size: int, slave1_addr: int, slave1_size: int, is_dut=False):
        """
        Combinatorial 2-Port Wishbone Decoder.
        
        Parameters:
            slave0_addr: Starting 30-bit Word Address for Slave 0
            slave0_size: Range size in 32-bit Words
            slave1_addr: Starting 30-bit Word Address for Slave 1
            slave1_size: Range size in 32-bit Words
        """
        self.is_dut = is_dut
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

        # Default all outputs to zero
        m.d.comb += [
            master.stall.eq(0),
            master.ack.eq(0),
            master.dat_r.eq(0),
            bus_error.eq(0),
            slave0.cyc.eq(0),
            slave0.stb.eq(0),
            slave0.we.eq(0),
            slave0.addr.eq(0),
            slave0.sel.eq(0),
            slave0.dat_w.eq(0),
            slave1.cyc.eq(0),
            slave1.stb.eq(0),
            slave1.we.eq(0),
            slave1.addr.eq(0),
            slave1.sel.eq(0),
            slave1.dat_w.eq(0),
        ]

        outstanding = Signal(8)
        active_slave = Signal(2)
        req_issued = master.cyc & master.stb & ~master.stall
        res_rcvd   = master.cyc & master.ack

        slave0_bits = int(math.log2(self.slave0_size))
        slave1_bits = int(math.log2(self.slave1_size))

        slave0_match = (master.addr >= self.slave0_addr) & (master.addr < (self.slave0_addr + self.slave0_size))
        slave1_match = (master.addr >= self.slave1_addr) & (master.addr < (self.slave1_addr + self.slave1_size))

        with m.If(master.cyc):
            m.d.sync += outstanding.eq(outstanding + req_issued - res_rcvd)
            with m.If(slave0_match & ((active_slave == 1) | (active_slave == 0))):
                m.d.sync += active_slave.eq(1)
                m.d.comb += [
                    slave0.cyc.eq(master.cyc),
                    slave0.stb.eq(master.stb),
                    slave0.we.eq(master.we),
                    slave0.addr.eq(master.addr[:slave0_bits]),
                    slave0.sel.eq(master.sel),
                    slave0.dat_w.eq(master.dat_w),
                    master.dat_r.eq(slave0.dat_r),
                    master.ack.eq(slave0.ack),
                    master.stall.eq(slave0.stall),
                ]
            with m.Elif(slave1_match & ((active_slave == 2) | (active_slave == 0))):
                m.d.sync += active_slave.eq(2)
                m.d.comb += [
                    slave1.cyc.eq(master.cyc),
                    slave1.stb.eq(master.stb),
                    slave1.we.eq(master.we),
                    slave1.addr.eq(master.addr[:slave1_bits]),
                    slave1.sel.eq(master.sel),
                    slave1.dat_w.eq(master.dat_w),
                    master.dat_r.eq(slave1.dat_r),
                    master.ack.eq(slave1.ack),
                    master.stall.eq(slave1.stall),
                ]
            with m.Else():
                m.d.sync += active_slave.eq(3)
                # Assert ACK to complete the invalid transaction and prevent
                # bus deadlock
                m.d.comb += [
                    master.ack.eq(outstanding > 0),
                    bus_error.eq(1),
                ]
        with m.Else():
            m.d.sync += outstanding.eq(0)
            m.d.sync += active_slave.eq(0)

        if platform == "formal":
            if self.is_dut:
                master_verify = m.submodules.master_verify = WishboneSlaveFormal(master.signature.flip(), self.is_dut)
                slave0_verify = m.submodules.slave0_verify = WishboneMasterFormal(slave0.signature.flip(), self.is_dut)
                slave1_verify = m.submodules.slave1_verify = WishboneMasterFormal(slave1.signature.flip(), self.is_dut)
                wiring.connect(m, master_verify, master)
                wiring.connect(m, slave0_verify, slave0)
                wiring.connect(m, slave1_verify, slave1)

            past_cyc = Signal()
            past_bus_error = Signal()
            past_slave0_match = Signal()
            past_slave1_match = Signal()
            m.d.sync += [
                past_cyc.eq(master.cyc),
                past_slave0_match.eq(slave0_match),
                past_slave1_match.eq(slave1_match),
                past_bus_error.eq(bus_error),
            ]

            # Rule A: Cross-Bleed Routing Invariant
            # Prove that the master can NEVER physically activate both slaves
            # at the same time.
            with m.If(master.stb):
                m.d.comb += Assert(~(slave0.stb & slave1.stb))

            # Rule B: Destination Separation Guarantee
            # Prove that if an address targets Slave 0, Slave 1 must hear
            # absolute silence.
            with m.If(master.cyc & slave0_match):
                m.d.comb += Assert(~slave1.cyc)

            # Rule C: Destination Separation Guarantee (Inverse)
            with m.If(master.cyc & slave1_match):
                m.d.comb += Assert(~slave0.cyc)

            # Rule D: Out-of-bounds Trap Isolation Invariant
            with m.If(bus_error & ~past_cyc):
                m.d.comb += [
                    Assert(master.cyc),
                    Assert(~slave0_match),
                    Assert(~slave1_match),
                ]

            # Rule E: Ensure that device doesn't change during a transaction
            with m.If(~past_bus_error & bus_error & past_cyc):
                m.d.comb += [
                    Assert(master.cyc),
                    Assert((slave0_match != past_slave0_match) | (slave1_match != past_slave1_match)),
                ]

        return m


if __name__ == '__main__':
    from usys.build.formal import run_formal
    decoder = WishboneDecoder(
        is_dut=True,
        slave0_addr=0x00000000, slave0_size=8,
        slave1_addr=0x10000000, slave1_size=8,
    )
    run_formal(decoder)
