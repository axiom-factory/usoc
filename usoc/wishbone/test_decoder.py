from unittest import TestCase
from usoc.build.formal import run_formal
from usoc.wishbone.decoder import WishboneDecoder


class TestWishboneDecoder(TestCase):
    def test_wishbone_formal(self):
        decoder = WishboneDecoder(
            is_dut=True,
            slave0_addr=0x00000000, slave0_size=8,
            slave1_addr=0x10000000, slave1_size=8,
        )
        run_formal(decoder)
