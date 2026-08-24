from amaranth.sim import Period, Simulator, Tick
from unittest import TestCase
from usoc.build.formal import run_formal
from usoc.wishbone.sram import WishboneDualPortSram


class TestWishboneSram(TestCase):
    def test_wishbone_formal(self):
        sram = WishboneDualPortSram(depth=8, is_dut=True)
        run_formal(sram)


    def test_write_after_read_integrity(self):
        dut = WishboneDualPortSram(depth=8)
        sim = Simulator(dut)
        port_a = dut.port_a

        def proc():
            dut = port_a
            yield Tick()
            yield dut.cyc.eq(1)
            yield dut.stb.eq(1)
            yield dut.we.eq(1)
            yield dut.addr.eq(5)
            yield dut.dat_w.eq(0xABCDEFFF)
            yield dut.sel.eq(0b1111)
            #yield dut.sel.eq(0b1010)
            yield Tick()
            yield dut.stb.eq(0)
            yield dut.we.eq(0)
            yield Tick()
            yield Tick()
            ack_val = yield dut.ack
            print(f'ack = {ack_val}')
            self.assertEqual(ack_val, 1, "Error: No write ACK")
            yield dut.cyc.eq(0)
            yield Tick()
            yield dut.cyc.eq(1)
            yield dut.stb.eq(1)
            yield dut.we.eq(0)
            yield dut.addr.eq(5)
            yield Tick()
            yield dut.stb.eq(0)
            yield Tick()
            yield Tick()
            ack_val = yield dut.ack
            read_data = yield dut.dat_r
            self.assertEqual(ack_val, 1, "Error: No read ACK")
            self.assertEqual(read_data, 0xABCDEFFF, f"Expected 0xABCDEFFF, got {hex(read_data)}")

        sim.add_clock(Period(MHz=1))
        sim.add_process(proc)
        sim.run()
