from amaranth import Module, Signal
from amaranth.asserts import Assert, Initial
from amaranth.lib import memory
from amaranth.lib.wiring import Component, In, Out, Signature
from usys.wishbone.interface import wishbone_signature, WishboneSlaveFormalChecker


class WishboneDualPortSram(Component):
    def __init__(self, depth: int = 4096):
        '''
        True Dual-Port Pipelined SRAM Block
        
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
        mem_r_a = mem.read_port(domain='sync')
        mem_w_a = mem.write_port(domain='sync')
        mem_r_b = mem.read_port(domain='sync')
        mem_w_b = mem.write_port(domain='sync')

        # ---------------------------------------------------------
        # COLLISION ARBITRATION MATRIX
        # ---------------------------------------------------------
        # Detect if both masters are attempting a write collision to the exact
        # same cell
        both_writing = port_a.stb & port_a.we & port_b.stb & port_b.we
        same_address = (port_a.addr == port_b.addr)
        write_collision = both_writing & same_address

        # ---------------------------------------------------------
        # DOMAIN A: CPU Execution Lane (Highest Priority)
        # ---------------------------------------------------------
        # Port A is the absolute master of its lane. It never stalls for Port B.
        # It only stalls if an external downstream system constraint sets
        # port_a.stall.
        # For this standalone module, downstream is always ready.
        m.d.comb += port_a.stall.eq(0)
        ready_a = ~port_a.stall
        tx_a = port_a.stb & ready_a
        w_tx_a = tx_a & port_a.we
        r_tx_a = tx_a & ~port_a.we

        m.d.comb += [
            mem_r_a.addr.eq(port_a.addr),
            mem_w_a.addr.eq(port_a.addr),
            mem_w_a.data.eq(port_a.dat_w),
            port_a.dat_r.eq(mem_r_a.data),
            mem_w_a.en.eq(w_tx_a),
            mem_r_a.en.eq(r_tx_a),
        ]

        # Port A Pipeline ACK Generator
        past_r_tx_a = Signal()
        m.d.sync += past_r_tx_a.eq(r_tx_a)

        with m.If(tx_a):
            with m.If(port_a.we):
                # Write ACK is immediate (0-cycle latency)
                m.d.comb += port_a.ack.eq(1)
            with m.Else():
                # Read ACK is pipelined (1-cycle latency)
                m.d.comb += port_a.ack.eq(past_r_tx_a)
        with m.Else():
            m.d.comb += port_a.ack.eq(0)

        # ---------------------------------------------------------
        # DOMAIN B: DMA Streaming Lane (Lower Priority)
        # ---------------------------------------------------------
        # Port B actively drives its STALL line to protect against collisions.
        # If a write collision occurs, we pull STALL high to freeze Port B's
        # pipeline, allowing Port A to execute its write cleanly this cycle.
        m.d.comb += port_b.stall.eq(write_collision)
        ready_b = ~port_b.stall
        tx_b = port_b.stb & ready_b
        w_tx_b = tx_b & port_b.we
        r_tx_b = tx_b & ~port_b.we

        m.d.comb += [
            mem_r_b.addr.eq(port_b.addr),
            mem_w_b.addr.eq(port_b.addr),
            mem_w_b.data.eq(port_b.dat_w),
            port_b.dat_r.eq(mem_r_b.data),
            mem_w_b.en.eq(w_tx_b),
            mem_r_b.en.eq(r_tx_b),
        ]

        # Port A Pipeline ACK Generator
        past_r_tx_b = Signal()
        m.d.sync += past_r_tx_b.eq(r_tx_b)

        with m.If(tx_b):
            with m.If(port_b.we):
                # Write ACK is immediate (0-cycle latency)
                m.d.comb += port_b.ack.eq(1)
            with m.Else():
                # Read ACK is pipelined (1-cycle latency)
                m.d.comb += port_b.ack.eq(past_r_tx_b)
        with m.Else():
            m.d.comb += port_b.ack.eq(0)


        if platform == "formal":
            m.submodules.port_a_verify = WishboneSlaveFormalChecker(port_a.signature)
            m.submodules.port_b_verify = WishboneSlaveFormalChecker(port_b.signature)

            # Rule: Port A and B may never write to the same address at the
            # same time.
            both_writing = mem_w_a.en & mem_w_b.en
            same_address = (mem_w_a.addr == mem_w_b.addr)
            
            with m.If(both_writing & same_address):
                m.d.comb += Assert(False)

        return m


if __name__ == '__main__':
    from usys.build.formal import run_formal
    sram = WishboneDualPortSram(depth=8)
    run_formal(sram)
