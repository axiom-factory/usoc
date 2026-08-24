from amaranth import Module, Signal
from amaranth.asserts import AnySeq
from amaranth.hdl import Assert, Assume, Cover
from amaranth.lib import wiring
from amaranth.lib.wiring import Component, In, Out, Signature


def wishbone_master(addr_width=30, data_width=32):
    '''
    Wishbone Internal Bus Signature

    The `err` line is not required. It should only be used to
    signal invalid addresses, but our decoder will expose the
    `err` line directly for mapping into the `mstatus` and
    `mcause` registers.
    '''
    return Signature({
        "cyc":   Out(1),
        "stb":   Out(1),
        "we":    Out(1),
        "addr":  Out(addr_width),
        "sel":   Out(data_width // 8),
        "dat_w": Out(data_width),
        "dat_r": In(data_width),
        "ack":   In(1),
        "stall": In(1),
        #"err":  Out(1),
    })


def wishbone_slave(addr_width=30, data_width=32):
    return wishbone_master(addr_width, data_width).flip()


class WishboneFormal(Component):
    def __init__(self, wb: Signature, is_dut=False):
        self.is_dut = is_dut
        self.is_master = wb.members['cyc'].flow == wiring.Flow.Out
        super().__init__(wb)

    def assert_master(self):
        return Assert if not self.is_master else Assume

    def assert_slave(self):
        return Assume if not self.is_master else Assert

    def elaborate(self, platform):
        m = Module()

        # Rule 0: Drive the outputs
        if self.is_dut:
            if self.is_master:
                m.d.comb += [
                    self.cyc.eq(AnySeq(1)),
                    self.stb.eq(AnySeq(1)),
                    self.we.eq(AnySeq(1)),
                    self.addr.eq(AnySeq(32)),
                    self.sel.eq(AnySeq(4)),
                    self.dat_w.eq(AnySeq(32)),
                ]
            else:
                m.d.comb += [
                    self.ack.eq(AnySeq(1)),
                    self.stall.eq(AnySeq(1)),
                    self.dat_r.eq(AnySeq(32)),
                ]

        # Rule 1: Power-On Reset Invariant
        initial = Signal(init=1)
        m.d.sync += initial.eq(0)
        with m.If(initial):
            m.d.comb += [
                self.assert_master()(~self.cyc),
                self.assert_master()(~self.stb),
                self.assert_slave()(~self.ack),
                self.assert_slave()(~self.stall),
            ]

        # Rule 2: Transaction envelope
        with m.If(self.stb):
            m.d.comb += self.assert_master()(self.cyc)

        # Rule 3: Pipelined Stability Property
        # If the master attempts a transfer and the slave stalls, the master
        # cannot change its mind or alter the payload. It must hold `stb`,
        # `addr`, `we`, `dat_w` and `sel` prefectly stable until the stall
        # clears OR abort the transaction.
        past_cyc   = Signal()
        past_stb   = Signal()
        past_stall = Signal()
        past_addr  = Signal(len(self.addr))
        past_we    = Signal()
        past_dat_w = Signal(len(self.dat_w))
        past_sel   = Signal(len(self.sel))
        m.d.sync += [
            past_cyc.eq(self.cyc),
            past_stb.eq(self.stb),
            past_stall.eq(self.stall),
            past_addr.eq(self.addr),
            past_we.eq(self.we),
            past_dat_w.eq(self.dat_w),
            past_sel.eq(self.sel)
        ]
        with m.If(past_stb & past_stall & self.cyc & ~initial):
            m.d.comb += [
                self.assert_master()(self.stb),
                self.assert_master()(self.addr  == past_addr),
                self.assert_master()(self.we    == past_we),
                self.assert_master()(self.dat_w == past_dat_w),
                self.assert_master()(self.sel   == past_sel),
            ]

        # Rule 4: Anti-Spurious Response
        outstanding = Signal(8)
        req_issued = self.cyc & self.stb & ~self.stall
        res_rcvd   = self.cyc & self.ack
        with m.If(~self.cyc):
            m.d.sync += outstanding.eq(0)
        with m.Else():
            m.d.sync += outstanding.eq(outstanding + req_issued - res_rcvd)
        with m.If(outstanding == 0):
            m.d.comb += self.assert_slave()(~self.ack)

        # Rule 5: Bounded Response Timeout
        res_timeout_count = Signal(2)
        with m.If(~self.cyc | self.ack | (~self.stall & self.stb)):
            m.d.sync += res_timeout_count.eq(0)
        with m.Else():
            with m.If(outstanding):
                m.d.sync += res_timeout_count.eq(res_timeout_count + 1)
        m.d.comb += self.assert_slave()(res_timeout_count < 2)

        # Rule 6: Bounded Request Timeout
        with m.If(~self.stb & (outstanding == 0)):
            m.d.comb += self.assert_master()(~self.cyc)

        # Rule 7: Pipelined Transaction Coverage
        if platform == 'formal':
            m.d.comb += Cover(self.cyc & self.stb & self.ack)

        return m
