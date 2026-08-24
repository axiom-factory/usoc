from amaranth import Module, Mux, Signal
from amaranth.lib import memory, wiring
from amaranth.lib.wiring import Component, In, Out, Signature
from usoc.wishbone.interface import wishbone_master, WishboneFormal


class WishboneDualPortSram(Component):
    def __init__(self, depth: int = 4096, is_dut=False):
        '''
        Dual-Port Pipelined SRAM Block
        
        Parameters:
            depth: Storage depth in 32-bit Words (e.g., 4096 Words = 16KB SRAM)
        '''
        self.depth = depth
        self.is_dut = is_dut
        wb_sig = wishbone_master()
        super().__init__(Signature({
            'port_a': In(wb_sig),
            'port_b': In(wb_sig),
        }))

    def elaborate(self, platform):
        m = Module()

        port_a = self.port_a
        port_b = self.port_b
        mem = m.submodules.ram_core = memory.Memory(shape=32, depth=self.depth, init=[])

        # Port A:
        mem_r_a = mem.read_port(domain='sync')
        mem_w_a = mem.write_port(domain='sync', granularity=8)
        ack_a = Signal()
        x_ack_a = Signal()
        m.d.comb += [
            port_a.stall.eq(0),
            port_a.ack.eq(port_a.cyc & ack_a),
            port_a.dat_r.eq(mem_r_a.data),
            mem_w_a.addr.eq(port_a.addr),
            mem_r_a.addr.eq(port_a.addr),
            mem_w_a.data.eq(port_a.dat_w),
            mem_w_a.en.eq(Mux(port_a.cyc & port_a.stb & port_a.we, port_a.sel, 0)),
            mem_r_a.en.eq(port_a.cyc & port_a.stb & ~port_a.we),
        ]
        m.d.sync += [
            ack_a.eq(port_a.cyc & x_ack_a),
            x_ack_a.eq(port_a.cyc & port_a.stb),
        ]

        # Port B:
        mem_r_b = mem.read_port(domain='sync')
        mem_w_b = mem.write_port(domain='sync', granularity=8)
        ack_b = Signal()
        x_ack_b = Signal()
        m.d.comb += [
            port_b.stall.eq(0),
            port_b.ack.eq(port_b.cyc & ack_b),
            port_b.dat_r.eq(mem_r_b.data),
            mem_w_b.addr.eq(port_b.addr),
            mem_r_b.addr.eq(port_b.addr),
            mem_w_b.data.eq(port_b.dat_w),
            mem_w_b.en.eq(Mux(port_b.cyc & port_b.stb & port_b.we, port_b.sel, 0)),
            mem_r_b.en.eq(port_b.cyc & port_b.stb & ~port_b.we),
        ]
        m.d.sync += [
            ack_b.eq(port_b.cyc & x_ack_b),
            x_ack_b.eq(port_b.cyc & port_b.stb),
        ]

        if platform == 'formal':
            if self.is_dut:
                port_a_verify = m.submodules.port_a_verify = WishboneFormal(port_a.signature.flip(), self.is_dut)
                port_b_verify = m.submodules.port_b_verify = WishboneFormal(port_b.signature.flip(), self.is_dut)
                wiring.connect(m, port_a_verify, port_a)
                wiring.connect(m, port_b_verify, port_b)

        return m
