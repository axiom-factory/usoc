from amaranth import Module, Signal
from amaranth.asserts import Assert, Assume, Initial
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, Signature


def wishbone_signature(addr_width=30, data_width=32):
    """
    Wishbone Internal Bus Signature

    Since our SoC doesn't contain any arbiters, remove `cyc`,
    making `stb` instead of `cyc` & `stb` the transaction valid
    line.

    The `err` line is not required. It should only be used to
    signal invalid addresses, but our decoder will expose the
    `err` line directly for mapping into the `mstatus` and
    `mcause` registers.
    """
    return Signature({
        #"cyc":   Out(1),
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


class WishboneMasterFormalChecker(wiring.Component):
    def __init__(self, wb: Signature):
        super().__init__(wb)

    def elaborate(self, platform):
        m = Module()

        # Track outstanding requests
        outstanding = Signal(8)
        req_issued = self.stb & ~self.stall
        res_rcvd   = self.ack

        with m.If(Initial()):
            m.d.sync += outstanding.eq(0)
        with m.Else():
            m.d.sync += outstanding.eq(outstanding + req_issued - res_rcvd)

        # Store last state
        past_stb   = Signal()
        past_stall = Signal()
        past_addr  = Signal(len(self.addr))
        past_we    = Signal()
        past_dat_w = Signal(len(self.dat_w))
        past_sel   = Signal(len(self.sel))

        m.d.sync += [
            past_stb.eq(self.stb),
            past_stall.eq(self.stall),
            past_addr.eq(self.addr),
            past_we.eq(self.we),
            past_dat_w.eq(self.dat_w),
            past_sel.eq(self.sel)
        ]

        # Rule 1: Assert Power-On Reset Invariant
        with m.If(Initial()):
            m.d.comb += Assert(~self.stb)
    
        # Rule 2: Assert Pipelined Stability Property
        # If the slave pulls STALL high, the master is strictly forbidden
        # from changing its mind. It must hold its address, data, and strobe
        # perfectly stable.
        with m.If(past_stb & past_stall & ~Initial()):
            m.d.comb += [
                Assert(self.stb),
                Assert(self.addr  == past_addr),
                Assert(self.we    == past_we),
                Assert(self.dat_w == past_dat_w),
                Assert(self.sel   == past_sel),
            ]

        # Rule 3: Assume Anti-Spurious Response
        with m.If(outstanding == 0):
            m.d.comb += Assume(~self.ack)

        return m


class WishboneSlaveFormalChecker(wiring.Component):
    def __init__(self, wb: Signature):
        super().__init__(wb)

    def elaborate(self, platform):
        m = Module()

        # Track outstanding requests
        outstanding = Signal(16)
        req_issued  = self.stb & ~self.stall
        res_rcvd    = self.ack

        with m.If(Initial()):
            m.d.sync += outstanding.eq(0)
        with m.Else():
            m.d.sync += outstanding.eq(outstanding + req_issued - res_rcvd)

        # Store last state
        past_stb   = Signal()
        past_stall = Signal()
        past_addr  = Signal(len(self.addr))
        past_we    = Signal()
        past_dat_w = Signal(len(self.dat_w))
        past_sel   = Signal(len(self.sel))

        m.d.sync += [
            past_stb.eq(self.stb),
            past_stall.eq(self.stall),
            past_addr.eq(self.addr),
            past_we.eq(self.we),
            past_dat_w.eq(self.dat_w),
            past_sel.eq(self.sel),
        ]

        # Rule 1: Assert Power-On Reset Invariant
        with m.If(Initial()):
            m.d.comb += [
                Assert(~self.ack),
                Assert(~self.stall)
            ]

        # Rule 2: Assume Pipelined Stability Property
        with m.If(past_stb & past_stall & ~Initial()):
            m.d.comb += [
                Assume(self.stb),
                Assume(self.addr  == past_addr),
                Assume(self.we    == past_we),
                Assume(self.dat_w == past_dat_w),
                Assume(self.sel   == past_sel),
            ]

        # Rule 3: Assert Anti-Spurious Response
        with m.If(outstanding == 0):
            m.d.comb += Assert(~self.ack)

        return m
