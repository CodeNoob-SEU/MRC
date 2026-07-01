import unittest

from mrc_backend.hardware.camera import format_sdk_code, signed_u32
from mrc_backend.hardware.daq import USB3000_ERROR_CODES


class SdkCodesTest(unittest.TestCase):
    def test_signed_u32_formats_vendor_error(self) -> None:
        self.assertEqual(signed_u32(4294967293), -3)
        self.assertEqual(format_sdk_code(4294967293), "-3 (unsigned=4294967293, hex=0xFFFFFFFD)")

    def test_usb3000_code_labels(self) -> None:
        self.assertEqual(USB3000_ERROR_CODES[-3], "Bad_Firmware")


if __name__ == "__main__":
    unittest.main()
