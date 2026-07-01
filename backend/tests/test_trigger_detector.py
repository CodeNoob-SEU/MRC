import unittest

from mrc_backend.hardware.daq import TriggerDetector


class TriggerDetectorTest(unittest.TestCase):
    def test_detects_rising_edges_across_batches(self) -> None:
        detector = TriggerDetector(threshold=2.5, debounce_seconds=0.010, sample_rate_hz=1000)
        self.assertEqual(detector.process([0, 0, 5, 5], 0)[0].sample_number, 2)
        self.assertEqual(detector.process([5, 0, 0, 5], 4), [])
        detections = detector.process([0, 0, 0, 5], 12)
        self.assertEqual([d.sample_number for d in detections], [15])

    def test_debounce_rejects_nearby_edges(self) -> None:
        detector = TriggerDetector(threshold=2.5, debounce_seconds=0.010, sample_rate_hz=1000)
        detections = detector.process([0, 5, 0, 5, 0, 0, 0, 0, 0, 0, 0, 5], 0)
        self.assertEqual([d.sample_number for d in detections], [1, 11])


if __name__ == "__main__":
    unittest.main()

