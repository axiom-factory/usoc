from amaranth import Module, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import Component, In, Out
from usoc.wishbone.decoder import WishboneDecoder
from usoc.wishbone.interface import wishbone_master, WishboneFormal
from usoc.wishbone.sram import WishboneDualPortSram


class UsysFabric(Component):
    def __init__(self, depth_i_sram: int = 4096, depth_d_sram: int = 4096, depth_mmio: int = 64, is_dut=False):
        '''
        USYS Routing Fabric

        Coordinates a completely non-blocking memory network mapping:
          - CPU I-Bus to I-SRAM Port A
          - CPU D-Bus to a Decoder splitting out to D-SRAM Port A and UBUS CSR MMIO
          - UBUS Master to a Decoder splitting out to I-SRAM/D-SRAM Port B
        '''
        self.is_dut = is_dut
        self.depth_i = depth_i_sram
        self.depth_d = depth_d_sram
        self.depth_mmio = depth_mmio
        wb_sig = wishbone_master()
        super().__init__(wiring.Signature({
            'cpu_ibus':      In(wb_sig),
            'cpu_dbus':      In(wb_sig),
            'ubus_master':   In(wb_sig),
            'ubus_slave':    Out(wb_sig),
            'cpu_bus_error': Out(1)
        }))

    def elaborate(self, platform):
        m = Module()

        I_SRAM_ADDR = 0x10000000
        D_SRAM_ADDR = 0x20000000
        MMIO_ADDR   = 0x30000000

        m.submodules.i_sram = i_sram = WishboneDualPortSram(depth=self.depth_i)
        m.submodules.d_sram = d_sram = WishboneDualPortSram(depth=self.depth_d)
        m.submodules.dbus_decoder = dbus_decoder = WishboneDecoder(
            slave0_addr=D_SRAM_ADDR, slave0_size=self.depth_d,
            slave1_addr=MMIO_ADDR,   slave1_size=self.depth_mmio,
        )
        m.submodules.ubus_decoder = ubus_decoder = WishboneDecoder(
            slave0_addr=I_SRAM_ADDR, slave0_size=self.depth_i,
            slave1_addr=D_SRAM_ADDR, slave1_size=self.depth_d,
        )

        wiring.connect(m, i_sram.port_a, wiring.flipped(self.cpu_ibus))
        wiring.connect(m, dbus_decoder.master, wiring.flipped(self.cpu_dbus))
        wiring.connect(m, ubus_decoder.master, wiring.flipped(self.ubus_master))
        wiring.connect(m, d_sram.port_a, dbus_decoder.slave0)
        wiring.connect(m, wiring.flipped(self.ubus_slave), dbus_decoder.slave1)
        wiring.connect(m, i_sram.port_b, ubus_decoder.slave0)
        wiring.connect(m, d_sram.port_b, ubus_decoder.slave1)
        m.d.comb += self.cpu_bus_error.eq(dbus_decoder.bus_error)

        if platform == 'formal':
            if self.is_dut:
                ibus_verify = m.submodules.ibus_verify = WishboneFormal(self.cpu_ibus.signature.flip(), self.is_dut)
                dbus_verify = m.submodules.dbus_verify = WishboneFormal(self.cpu_dbus.signature.flip(), self.is_dut)
                ubus_m_verify = m.submodules.ubus_m_verify = WishboneFormal(self.ubus_master.signature.flip(), self.is_dut)
                ubus_s_verify = m.submodules.ubus_s_verify = WishboneFormal(self.ubus_slave.signature.flip(), self.is_dut)
                wiring.connect(m, ibus_verify, self.cpu_ibus)
                wiring.connect(m, dbus_verify, self.cpu_dbus)
                wiring.connect(m, ubus_m_verify, self.ubus_master)
                wiring.connect(m, ubus_s_verify, self.ubus_slave)

        return m
