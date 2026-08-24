from unittest import TestCase
from usoc.build.formal import run_formal
from usoc.wishbone.arbiter import WishboneArbiter


class TestWishboneArbiter(TestCase):
    def test_wishbone_formal(self):
        run_formal(WishboneArbiter(is_dut=True))
