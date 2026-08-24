from amaranth import Module, Signal
from amaranth.hdl import Assert, Cover
from amaranth.lib import wiring
from amaranth.lib.wiring import Component, In, Out, Signature
from usoc.wishbone.interface import wishbone_master, wishbone_slave, WishboneFormal


class WishboneArbiter(Component):
    def __init__(self, is_dut=False):
        '''
        Combinatorial 2-Port Wishbone Arbiter.
        '''
        self.is_dut = is_dut
        wb_sig = wishbone_master()
        signature = Signature({
            'master0':  In(wb_sig),
            'master1':  In(wb_sig),
            'slave':    Out(wb_sig),
        })
        super().__init__(signature)

    def elaborate(self, platform):
        m = Module()
        master0 = self.master0
        master1 = self.master1
        slave = self.slave

        m.d.comb += [
            master0.stall.eq(slave.stall),
            master0.dat_r.eq(slave.dat_r),
            master0.ack.eq(0),
            master1.stall.eq(slave.stall),
            master1.dat_r.eq(slave.dat_r),
            master1.ack.eq(0),
        ]

        active_master = Signal(2)

        with m.If(master0.cyc & ((active_master == 0) | (active_master == 1))):
            m.d.sync += active_master.eq(1)
            m.d.comb += [
                slave.cyc.eq(master0.cyc),
                slave.stb.eq(master0.stb),
                slave.we.eq(master0.we),
                slave.addr.eq(master0.addr),
                slave.sel.eq(master0.sel),
                slave.dat_w.eq(master0.dat_w),
                master0.ack.eq(slave.ack),
                master1.stall.eq(1),
            ]
        with m.Elif(master1.cyc & ((active_master == 0) | (active_master == 2))):
            m.d.sync += active_master.eq(2)
            m.d.comb += [
                slave.cyc.eq(master1.cyc),
                slave.stb.eq(master1.stb),
                slave.we.eq(master1.we),
                slave.addr.eq(master1.addr),
                slave.sel.eq(master1.sel),
                slave.dat_w.eq(master1.dat_w),
                master1.ack.eq(slave.ack),
                master0.stall.eq(1),
            ]
        with m.Else():
            m.d.sync += active_master.eq(0)
            with m.If(active_master != 0):
                m.d.comb += [
                    master0.stall.eq(1),
                    master1.stall.eq(1),
                ]

        if platform == "formal":
            master0_verify = m.submodules.master0_verify = WishboneFormal(master0.signature.flip(), self.is_dut)
            master1_verify = m.submodules.master1_verify = WishboneFormal(master1.signature.flip(), self.is_dut)
            slave_verify = m.submodules.slave_verify = WishboneFormal(slave.signature.flip(), self.is_dut)
            wiring.connect(m, master0_verify, master0)
            wiring.connect(m, master1_verify, master1)
            wiring.connect(m, slave_verify, slave)

        return m
