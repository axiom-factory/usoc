from amaranth import Module, Mux, Signal
from amaranth.asserts import Assert, Assume, Cover
from amaranth.lib import memory, wiring
from amaranth.lib.wiring import Component, In, Out, Signature
from amaranth.sim import Simulator
from usys.wishbone.interface import wishbone_signature, WishboneSlaveFormalChecker
import unittest


class WishboneDualPortSram(Component):
    def __init__(self, depth: int = 4096):
        '''
        Dual-Port Pipelined SRAM Block
        
        Parameters:
            depth: Storage depth in 32-bit Words (e.g., 4096 Words = 16KB SRAM)
        '''
        self.depth = depth
        wb_sig = wishbone_signature()
        super().__init__(Signature({
            "port_a": In(wb_sig),
            "port_b": In(wb_sig),
        }))

    def elaborate(self, platform):
        m = Module()

        port_a = self.port_a
        port_b = self.port_b
        mem = m.submodules.ram_core = memory.Memory(shape=32, depth=self.depth, init=[])

        # Port A:
        mem_r_a = mem.read_port(domain='sync')
        mem_w_a = mem.write_port(domain='sync')
        ack_a = Signal()
        x_ack_a = Signal()
        m.d.comb += [
            port_a.stall.eq(0),
            port_a.ack.eq(port_a.cyc & ack_a),
            port_a.dat_r.eq(mem_r_a.data),
        ]
        m.d.sync += [
            mem_w_a.addr.eq(port_a.addr),
            mem_r_a.addr.eq(port_a.addr),
            mem_w_a.data.eq(port_a.dat_w),
            mem_w_a.en.eq(port_a.cyc & port_a.stb & port_a.we),
            mem_r_a.en.eq(port_a.cyc & port_a.stb & ~port_a.we),
            ack_a.eq(port_a.cyc & x_ack_a),
            x_ack_a.eq(port_a.cyc & port_a.stb),
        ]

        # Port B:
        mem_r_b = mem.read_port(domain='sync')
        mem_w_b = mem.write_port(domain='sync')
        ack_b = Signal()
        x_ack_b = Signal()
        m.d.comb += [
            port_b.stall.eq(0),
            port_b.ack.eq(port_b.cyc & ack_b),
            port_b.dat_r.eq(mem_r_b.data),
        ]
        m.d.sync += [
            mem_w_b.addr.eq(port_b.addr),
            mem_r_b.addr.eq(port_b.addr),
            mem_w_b.data.eq(port_b.dat_w),
            mem_w_b.en.eq(port_b.cyc & port_b.stb & port_b.we),
            mem_r_b.en.eq(port_b.cyc & port_b.stb & ~port_b.we),
            ack_b.eq(port_b.cyc & x_ack_b),
            x_ack_b.eq(port_b.cyc & port_b.stb),
        ]

        if platform == "formal":
            port_a_verify = m.submodules.port_a_verify = WishboneSlaveFormalChecker(port_a.signature)
            port_b_verify = m.submodules.port_b_verify = WishboneSlaveFormalChecker(port_b.signature)
            wiring.connect(m, wiring.flipped(port_a_verify), port_a)
            wiring.connect(m, wiring.flipped(port_b_verify), port_b)

            m.d.comb += Assume(port_a.addr < self.depth)
            m.d.comb += Assume(port_b.addr < self.depth)

            # Rule: Port A and B may never write to the same address at the
            # same time.
            both_writing = mem_w_a.en & mem_w_b.en
            same_address = mem_w_a.addr == mem_w_b.addr
            
            with m.If(both_writing & same_address):
                m.d.comb += Assume(False)

        return m


class TestSramPipeline(unittest.TestCase):
    def test_write_after_read_integrity(self):
        dut = WishboneDualPortSram()
        sim = Simulator(dut)

        def proc():
            yield dut.cyc.eq(1)
            yield dut.stb.eq(1)
            yield dut.we.eq(1)
            yield dut.addr.eq(5)
            yield dut.dat_w.eq(0xABCDEFFF)
            yield
            yield dut.stb.eq(0)
            yield dut.we.eq(0)
            yield
            ack_val = yield dut.ack
            self.assertEqual(ack_val, 1, "Error: No write ACK")
            yield dut.cyc.eq(0)
            yield
            yield dut.cyc.eq(1)
            yield dut.stb.eq(1)
            yield dut.we.eq(0)
            yield dut.addr.eq(5)
            yield
            yield dut.stb.eq(0)
            yield
            ack_val = yield dut.ack
            read_data = yield dut.dat_r
            self.assertEqual(ack_val, 1, "Error: No read ACK")
            self.assertEqual(read_data, 0xABCDEFFF, f"Expected 0xABCDEFFF, got {hex(read_data)}")


if __name__ == '__main__':
    from usys.build.formal import run_formal
    sram = WishboneDualPortSram(depth=8)
    run_formal(sram)
