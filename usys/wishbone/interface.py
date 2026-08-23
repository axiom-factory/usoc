from amaranth import Module, Signal
from amaranth.asserts import AnySeq
from amaranth.hdl import Assert, Assume, Cover
from amaranth.lib import wiring
from amaranth.lib.wiring import Component, In, Out, Signature
from amaranth.sim import Period, Simulator, Tick
import unittest


def wishbone_signature(addr_width=30, data_width=32):
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


class WishboneMasterFormal(Component):
    def __init__(self, wb: Signature, is_dut=False):
        self.is_dut = is_dut
        super().__init__(wb)

    def elaborate(self, platform):
        m = Module()

        initial = Signal(init=1)
        m.d.sync += initial.eq(0)

        # Track outstanding requests
        outstanding = Signal(8)
        req_issued = self.cyc & self.stb & ~self.stall
        res_rcvd   = self.cyc & self.ack

        with m.If(~self.cyc):
            m.d.sync += outstanding.eq(0)
        with m.Else():
            m.d.sync += outstanding.eq(outstanding + req_issued - res_rcvd)

        # Store last state
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

        if platform == 'formal':
            m.d.comb += Cover(self.cyc & self.stb & self.ack)

        # Make sure slave outputs are driven
        if self.is_dut:
            m.d.comb += [
                self.ack.eq(AnySeq(1)),
                self.stall.eq(AnySeq(1)),
                self.dat_r.eq(AnySeq(32)),
            ]

        # Rule 1: Assert Power-On Reset Invariant
        with m.If(initial):
            m.d.comb += [
                Assert(~self.cyc),
                Assert(~self.stb),
                Assume(~self.ack),
                Assume(~self.stall),
            ]

        # Rule 2: Transaction envelope
        with m.If(self.stb):
            m.d.comb += Assert(self.cyc)
    
        # Rule 3: Assume Anti-Spurious Response
        with m.If(outstanding == 0):
            m.d.comb += Assume(~self.ack)

        # Rule 4: Pipelined Stability Property
        # When a slave stalls, the master must hold its address, data, and
        # strobe stable.
        with m.If(past_stb & past_stall & self.cyc & ~initial):
            m.d.comb += [
                Assert(self.stb),
                Assert(self.addr  == past_addr),
                Assert(self.we    == past_we),
                Assert(self.dat_w == past_dat_w),
                Assert(self.sel   == past_sel),
            ]

        # Rule 5: Every transaction must complete on the next cycle
        timeout_count = Signal(2)
        with m.If(~self.cyc | self.ack | (~self.stall & self.stb)):
            m.d.sync += timeout_count.eq(0)
        with m.Else():
            with m.If(outstanding > 0):
                m.d.sync += timeout_count.eq(timeout_count + 1)
        m.d.comb += Assume(timeout_count < 2)

        return m


class WishboneSlaveFormal(Component):
    def __init__(self, wb: Signature, is_dut=False):
        self.is_dut = is_dut
        super().__init__(wb)

    def elaborate(self, platform):
        m = Module()

        initial = Signal(init=1)
        m.d.sync += initial.eq(0)

        # Track outstanding requests
        outstanding = Signal(8)
        req_issued  = self.cyc & self.stb & ~self.stall
        res_rcvd    = self.ack

        with m.If(initial | ~self.cyc):
            m.d.sync += outstanding.eq(0)
        with m.Else():
            m.d.sync += outstanding.eq(outstanding + req_issued - res_rcvd)

        # Store last state
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
            past_sel.eq(self.sel),
        ]

        if platform == 'formal':
            m.d.comb += Cover(self.cyc & self.ack)

        # Make sure master outputs are driven
        if self.is_dut:
            m.d.comb += [
                self.cyc.eq(AnySeq(1)),
                self.stb.eq(AnySeq(1)),
                self.we.eq(AnySeq(1)),
                self.addr.eq(AnySeq(32)),
                self.sel.eq(AnySeq(4)),
                self.dat_w.eq(AnySeq(32)),
            ]

        # Rule 1: Assert Power-On Reset Invariant
        with m.If(initial):
            m.d.comb += [
                Assume(~self.cyc),
                Assume(~self.stb),
                Assert(~self.ack),
                Assert(~self.stall),
            ]

        # Rule 2: Transaction envelope
        with m.If(self.stb):
            m.d.comb += Assume(self.cyc)

        # Rule 3: Anti-Spurious Response
        with m.If(outstanding == 0):
            m.d.comb += Assert(~self.ack)

        # Rule 4: Pipelined Stability Property
        # When a slave stalls, the master must hold its address, data, and
        # strobe stable.
        with m.If(past_stb & past_stall & self.cyc & ~initial):
            m.d.comb += [
                Assume(self.stb),
                Assume(self.addr  == past_addr),
                Assume(self.we    == past_we),
                Assume(self.dat_w == past_dat_w),
                Assume(self.sel   == past_sel),
            ]

        # Rule 5: Every transaction must complete on the next cycle
        timeout_count = Signal(2)
        with m.If(~self.cyc | self.ack | (~self.stall & self.stb)):
            m.d.sync += timeout_count.eq(0)
        with m.Else():
            with m.If(outstanding > 0):
                m.d.sync += timeout_count.eq(timeout_count + 1)
        m.d.comb += Assert(timeout_count < 2)

        return m


class TestWishboneChecker(unittest.TestCase):
    def test_valid_one_wait_state_transaction(self):
        '''Verifies that a well-behaved 1-wait-state read passes with no issues.'''

        dut = WishboneMasterFormal(wishbone_signature())
        sim = Simulator(dut)

        def proc():
            # Power-on state
            yield dut.cyc.eq(0)
            yield dut.stb.eq(0)
            yield dut.stall.eq(0)
            yield dut.ack.eq(0)
            yield Tick()

            # Cycle 1: Master starts transaction
            yield dut.cyc.eq(1)
            yield dut.stb.eq(1)
            yield dut.stall.eq(1) # Slave stalls the first cycle
            yield Tick()

            # Cycle 2: Slave clears stall, master holds signals stable
            yield dut.stall.eq(0)
            yield Tick()

            # Cycle 3: Master waits for data, slave drops ACK
            yield dut.stb.eq(0)
            yield dut.ack.eq(1)
            yield Tick()

            # Cycle 4: Clean termination
            yield dut.cyc.eq(0)
            yield dut.ack.eq(0)
            yield Tick()

        sim.add_clock(Period(MHz=1))
        sim.add_process(proc)
        sim.run()

    def test_invalid_stb_leak_fails(self):
        '''Triggers the exact multi-cycle loop bug to prove the checker catches it.'''

        dut = WishboneMasterFormal(wishbone_signature())
        sim = Simulator(dut)

        def proc():
            yield dut.cyc.eq(0)
            yield dut.stb.eq(0)
            yield Tick()

            # STB without pulling CYC high
            yield dut.cyc.eq(0)
            yield dut.stb.eq(1)
            yield Tick()

        sim.add_clock(Period(MHz=1))
        sim.add_process(proc)

        # The simulator MUST raise an error because Rule 2 or Rule 5 was violated
        with self.assertRaises(AssertionError):
            sim.run()


class FormalChecker(Component):
    def __init__(self):
        self.wb = wishbone_signature()

    def elaborate(self, platform):
        m = Module()
        master = m.submodules.master = WishboneSlaveFormal(self.wb)
        slave = m.submodules.slave = WishboneMasterFormal(self.wb)

        m.d.comb += [
            slave.cyc.eq(master.cyc),
            slave.stb.eq(master.stb),
            slave.addr.eq(master.addr),
            slave.we.eq(master.we),
            slave.sel.eq(master.sel),
            slave.dat_w.eq(master.dat_w),
            master.ack.eq(slave.ack),
            master.stall.eq(slave.stall),
            master.dat_r.eq(slave.dat_r),
        ]

        return m


if __name__ == "__main__":
    from usys.build.formal import run_formal
    run_formal(FormalChecker())
