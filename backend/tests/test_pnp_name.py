"""The DirectShow device name carries an instance suffix (" 0#") the PnP
FriendlyName lacks; the reset escape hatch must match on the stripped base."""

import unittest

from mrc_backend.hardware.device_reset import pnp_pattern_from_device_name


class PnpPatternTest(unittest.TestCase):
    def test_strips_instance_suffix(self) -> None:
        # The real device: DirectShow name vs PnP FriendlyName.
        self.assertEqual(
            pnp_pattern_from_device_name("ZhongAn US2000 Video Capture 0#"),
            "*ZhongAn US2000 Video Capture*",
        )
        self.assertEqual(
            pnp_pattern_from_device_name("ZhongAn US2000 Video Capture 1#"),
            "*ZhongAn US2000 Video Capture*",
        )

    def test_pattern_like_matches_real_pnp_name(self) -> None:
        import fnmatch

        pattern = pnp_pattern_from_device_name("ZhongAn US2000 Video Capture 0#")
        self.assertTrue(fnmatch.fnmatch("ZhongAn US2000 Video Capture", pattern))

    def test_preserves_name_without_suffix(self) -> None:
        self.assertEqual(
            pnp_pattern_from_device_name("ZhongAn US2000 Video Capture"),
            "*ZhongAn US2000 Video Capture*",
        )

    def test_does_not_strip_bare_trailing_digits(self) -> None:
        # A name that legitimately ends in digits (no space) must be kept.
        self.assertEqual(pnp_pattern_from_device_name("US2000"), "*US2000*")

    def test_empty(self) -> None:
        self.assertEqual(pnp_pattern_from_device_name(""), "")


if __name__ == "__main__":
    unittest.main()
