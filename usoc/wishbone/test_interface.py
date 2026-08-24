from amaranth import Module
from amaranth.hdl import Elaboratable
from amaranth.lib import wiring
from amaranth.sim import Period, Simulator, Tick
from unittest import TestCase
from usoc.build.formal import run_formal
from usoc.wishbone.interface import wishbone_master, wishbone_slave, WishboneFormal


class WishboneFormalBench(Elaboratable):
    def __init__(self):
        self.wb = wishbone_master()

    def elaborate(self, platform):
        m = Module()
        master = m.submodules.master = WishboneFormal(self.wb, is_dut=True)
        slave = m.submodules.slave = WishboneFormal(self.wb.flip(), is_dut=True)
        wiring.connect(m, master, slave)
        return m


class TestWishboneFormal(TestCase):
    def test_valid_one_wait_state_transaction(self):
        '''Verifies that a well-behaved 1-wait-state read passes with no issues.'''

        dut = WishboneFormal(wishbone_slave())
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

        dut = WishboneFormal(wishbone_slave())
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

    def test_wishbone_formal(self):
        run_formal(WishboneFormalBench())
