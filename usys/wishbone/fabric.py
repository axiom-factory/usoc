from amaranth import Module, Signal, Mux
from amaranth.hdl import Assert
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from usys.wishbone.interface import wishbone_signature, WishboneSlaveFormalChecker
from usys.wishbone.decoder import WishboneDecoder
from usys.wishbone.sram import WishboneDualPortSram


class UsysFabric(wiring.Component):
    def __init__(self, depth_i_sram: int = 4096, depth_d_sram: int = 4096):
        """
        The Complete Zero-Arbiter USYS Routing Fabric.
        
        Coordinates a completely non-blocking memory network mapping:
          - CPU I-Bus straight to I-SRAM Port A
          - CPU D-Bus to a Decoder splitting out to D-SRAM Port A and UBUS CSR MMIO
          - UBUS Master to an Ingress Decoder splitting out to I-SRAM/D-SRAM Port B
        """
        self.depth_i = depth_i_sram
        self.depth_d = depth_d_sram

        wb_sig = wishbone_signature()

        super().__init__(wiring.Signature({
            "cpu_ibus":      In(wb_sig),
            "cpu_dbus":      In(wb_sig),
            "ubus_master":   In(wb_sig),
            "ubus_slave":    Out(wb_sig),
            "cpu_bus_error": Out(1)
        }))

    def elaborate(self, platform):
        m = Module()

        # ---------------------------------------------------------
        # 1. HARDWARE STORAGE INITIALIZATION
        # ---------------------------------------------------------
        m.submodules.i_sram = i_sram = WishboneDualPortSram(depth=self.depth_i)
        m.submodules.d_sram = d_sram = WishboneDualPortSram(depth=self.depth_d)

        # ---------------------------------------------------------
        # 2. DEFINING THE SOVEREIGN MEMORY WORD MAP
        # ---------------------------------------------------------
        # We split our 30-bit Word address space cleanly:
        # D-SRAM Address Range: 0x0000_0000 to Word Depth
        # UBUS-CSR MMIO Range:  0x1000_0000 upwards (Fixed 64-word window)
        D_SRAM_WORD_MIN   = 0x00000000
        UBUS_CSR_WORD_MIN = 0x10000000
        UBUS_CSR_SIZE     = 64

        # ---------------------------------------------------------
        # 3. DOMAIN 1: INTERFACE ROUTING (CPU I-Bus -> I-SRAM Port A)
        # ---------------------------------------------------------
        # Pure wire passthrough. No decoders, no arbiters.
        m.d.comb += [
            i_sram.port_a.cyc.eq(self.cpu_ibus.cyc),
            i_sram.port_a.stb.eq(self.cpu_ibus.stb),
            i_sram.port_a.we.eq(self.cpu_ibus.we),
            i_sram.port_a.addr.eq(self.cpu_ibus.addr),
            i_sram.port_a.sel.eq(self.cpu_ibus.sel),
            i_sram.port_a.dat_w.eq(self.cpu_ibus.dat_w),
            self.cpu_ibus.dat_r.eq(i_sram.port_a.dat_r),
            self.cpu_ibus.ack.eq(i_sram.port_a.ack),
            self.cpu_ibus.stall.eq(i_sram.port_a.stall)
        ]

        # ---------------------------------------------------------
        # 4. DOMAIN 2: DATA ROUTING (CPU D-Bus Decoder Installation)
        # ---------------------------------------------------------
        m.submodules.dbus_decoder = dbus_decoder = WishboneDecoder(
            slave0_addr=D_SRAM_WORD_MIN,   slave0_size=self.depth_d,
            slave1_addr=UBUS_CSR_WORD_MIN, slave1_size=UBUS_CSR_WORD_MIN + UBUS_CSR_SIZE
        )

        # Connect the CPU D-Bus inputs directly to the Decoder Master input gate
        m.d.comb += [
            dbus_decoder.master.cyc.eq(self.cpu_dbus.cyc),
            dbus_decoder.master.stb.eq(self.cpu_dbus.stb),
            dbus_decoder.master.we.eq(self.cpu_dbus.we),
            dbus_decoder.master.addr.eq(self.cpu_dbus.addr),
            dbus_decoder.master.sel.eq(self.cpu_dbus.sel),
            dbus_decoder.master.dat_w.eq(self.cpu_dbus.dat_w),
            self.cpu_dbus.dat_r.eq(dbus_decoder.master.dat_r),
            self.cpu_dbus.ack.eq(dbus_decoder.master.ack),
            self.cpu_dbus.stall.eq(dbus_decoder.master.stall),
            
            # Map the Decoder's trap signal natively out to the top-level CPU fault pin
            self.cpu_bus_error.eq(dbus_decoder.bus_error)
        ]

        # Wire Decoder Slave 0 Output directly to D-SRAM Port A
        m.d.comb += [
            d_sram.port_a.cyc.eq(dbus_decoder.slave0.cyc),
            d_sram.port_a.stb.eq(dbus_decoder.slave0.stb),
            d_sram.port_a.we.eq(dbus_decoder.slave0.we),
            d_sram.port_a.addr.eq(dbus_decoder.slave0.addr),
            d_sram.port_a.sel.eq(dbus_decoder.slave0.sel),
            d_sram.port_a.dat_w.eq(dbus_decoder.slave0.dat_w),
            dbus_decoder.slave0.dat_r.eq(d_sram.port_a.dat_r),
            dbus_decoder.slave0.ack.eq(d_sram.port_a.ack),
            dbus_decoder.slave0.stall.eq(d_sram.port_a.stall)
        ]

        # Wire Decoder Slave 1 Output directly to the System UBUS Register Slave Interface
        m.d.comb += [
            self.ubus_slave.cyc.eq(dbus_decoder.slave1.cyc),
            self.ubus_slave.stb.eq(dbus_decoder.slave1.stb),
            self.ubus_slave.we.eq(dbus_decoder.slave1.we),
            self.ubus_slave.addr.eq(dbus_decoder.slave1.addr),
            self.ubus_slave.sel.eq(dbus_decoder.slave1.sel),
            self.ubus_slave.dat_w.eq(dbus_decoder.slave1.dat_w),
            dbus_decoder.slave1.dat_r.eq(self.ubus_slave.dat_r),
            dbus_decoder.slave1.ack.eq(self.ubus_slave.ack),
            dbus_decoder.slave1.stall.eq(self.ubus_slave.stall)
        ]

        # ---------------------------------------------------------
        # 5. DOMAIN 3: NETWORK ROUTING (UBUS Ingress Decoder Installation)
        # ---------------------------------------------------------
        # The UBUS Master Engine needs to stream blocks straight to execution
        # or packet storage.
        # Address bit 29 acts as a static crossover switch token:
        #   - 0: Targets packet data storage (D-SRAM Port B)
        #   - 1: Targets zero-copy code bootstrap ingress (I-SRAM Port B)
        ubus_to_isram = (self.ubus_master.addr[29] == 1)

        # Wire up a combinatorial routing switch to manage the network data flow
        m.d.comb += [
            # Ingress to Instruction SRAM Port B
            i_sram.port_b.stb.eq(Mux(ubus_to_isram, self.ubus_master.stb, 0)),
            i_sram.port_b.we.eq(Mux(ubus_to_isram, self.ubus_master.we, 0)),
            i_sram.port_b.addr.eq(self.ubus_master.addr[0:14]), # Strip routing bits
            i_sram.port_b.sel.eq(self.ubus_master.sel),
            i_sram.port_b.dat_w.eq(self.ubus_master.dat_w),

            # Ingress to Data SRAM Port B
            d_sram.port_b.stb.eq(Mux(~ubus_to_isram, self.ubus_master.stb, 0)),
            d_sram.port_b.we.eq(Mux(~ubus_to_isram, self.ubus_master.we, 0)),
            d_sram.port_b.addr.eq(self.ubus_master.addr[0:14]),
            d_sram.port_b.sel.eq(self.ubus_master.sel),
            d_sram.port_b.dat_w.eq(self.ubus_master.dat_w),

            # Unify response readback multiplexing back up to the UBUS master engine
            self.ubus_master.dat_r.eq(Mux(ubus_to_isram, i_sram.port_b.dat_r, d_sram.port_b.dat_r)),
            self.ubus_master.ack.eq(Mux(ubus_to_isram, i_sram.port_b.ack, d_sram.port_b.ack)),
            self.ubus_master.stall.eq(Mux(ubus_to_isram, i_sram.port_b.stall, d_sram.port_b.stall))
        ]

        return m
