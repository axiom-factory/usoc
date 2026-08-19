from amaranth import Module, Signal
from amaranth.lib.wiring import Component, Out, Signature
from usys.build.nextpnr import build_ecp5, build_ice40
from usys.wishbone.fabric import UsysFabric


class UsysFabricTimingWrapper(Component):
    """
    Buries 32-bit parallel bus lines inside the silicon fabric to bypass physical pin limits,
    forcing nextpnr to evaluate 100% of the internal timing paths without crashing.
    """
    def __init__(self):
        super().__init__(Signature({
           'canary_out': Out(1),
        }))

    def elaborate(self, platform):
        m = Module()

        # Instantiate your 32-bit non-blocking distributed matrix fabric
        m.submodules.fabric = fabric = UsysFabric(depth_i_sram=1024, depth_d_sram=1024)

        # 1. FREELY RUNNING DYNAMIC STIMULUS GENERATORS
        # We create a wide counter to generate a pseudo-random, continuous stream 
        # of changing addresses and control flags.
        stimulus = Signal(32)
        m.d.sync += stimulus.eq(stimulus + 1)

        # Unpack bits of our counter to act as completely independent control wires
        m.d.comb += [
            # CPU I-Bus Inputs (Toggling state every cycle)
            fabric.cpu_ibus.addr.eq(stimulus[0:30]),
            fabric.cpu_ibus.stb.eq(stimulus[30]),  # Dynamic Strobe!
            fabric.cpu_ibus.we.eq(0),              # Instruction is read-only
            fabric.cpu_ibus.sel.eq(0b1111),
            fabric.cpu_ibus.dat_w.eq(0),
            
            # CPU D-Bus Inputs (Toggling address, writes, and byte enables)
            fabric.cpu_dbus.addr.eq(stimulus[1:31]),
            fabric.cpu_dbus.stb.eq(stimulus[29]),  # Dynamic Strobe!
            fabric.cpu_dbus.we.eq(stimulus[28]),   # Dynamic Write/Read switching!
            fabric.cpu_dbus.sel.eq(stimulus[24:28]),# Dynamic Byte Granularity masks!
            fabric.cpu_dbus.dat_w.eq(stimulus),
            
            # UBUS Master Network Inputs
            fabric.ubus_master.addr.eq(stimulus[2:32]),
            fabric.ubus_master.stb.eq(stimulus[27]), # Dynamic Strobe!
            fabric.ubus_master.we.eq(stimulus[26]),  # Dynamic Write/Read switching!
            fabric.ubus_master.sel.eq(0b1111),
            fabric.ubus_master.dat_w.eq(stimulus)
        ]

        # 2. HARDENED ROUTING FLIP-FLOPS
        # Capture the raw output buses into synchronous registers right before the pin compress.
        # This locks down the wide internal routing paths across the physical SRAM columns.
        latched_ibus_data = Signal(32)
        latched_dbus_data = Signal(32)
        latched_ubus_data = Signal(32)
        latched_bus_error = Signal()
        
        m.d.sync += [
            latched_ibus_data.eq(fabric.cpu_ibus.dat_r),
            latched_dbus_data.eq(fabric.cpu_dbus.dat_r),
            latched_ubus_data.eq(fabric.ubus_master.dat_r),
            latched_bus_error.eq(fabric.cpu_bus_error)
        ]
        
        # 3. Secure Reduction Output (.xor() method call)
        m.d.comb += self.canary_out.eq(
            latched_ibus_data.xor() ^ 
            latched_dbus_data.xor() ^ 
            latched_ubus_data.xor() ^
            latched_bus_error
        )
        
        return m


if __name__ == "__main__":
    from usys.build.nextpnr import build_ecp5, build_ice40
    fabric = UsysFabricTimingWrapper()

    # 1. Profile on the large high-performance ECP5-5G chip
    build_ecp5(fabric)
    
    # 2. Profile on the tiny cheap ultra-low-resource iCE40 chip
    #build_ice40(fabric)
