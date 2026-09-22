import unittest
from mfaf.usb_observer import USBObserver, make_usb_event
from mfaf.errors import ValidationError


class TestUSBObserver(unittest.TestCase):
    def test_event_types(self):
        o = USBObserver()
        o.connected(vid="18d1", pid="4ee7", manufacturer="Google", product="Pixel")
        o.identified(vid="18d1", pid="4ee7", manufacturer="Google", product="Pixel")
        o.disconnected(vid="18d1")
        self.assertEqual([e["event_type"] for e in o.events],
                         ["USB_CONNECTED", "DEVICE_IDENTIFIED", "USB_DISCONNECTED"])

    def test_unknown_event_type_rejected(self):
        with self.assertRaises(ValidationError):
            make_usb_event("USB_EXPLOIT")

    def test_malformed_metadata_sanitized(self):
        # محارف تحكّم في سلسلة جهاز لا يُوثق بها → ترفع خطأ (لا تخزّن خامًا)
        with self.assertRaises(ValidationError):
            make_usb_event("USB_CONNECTED", manufacturer="evil\x00\x1b[2J")

    def test_to_device_explicit_null_serial(self):
        o = USBObserver()
        o.identified(vid="18d1", pid="4ee7", manufacturer="Google", product="Pixel")
        dev = o.to_device("dev1", case_id="CASE-T", os_family="android")
        self.assertIsNone(dev.serial)          # serial غير متاح → null صريح
        self.assertEqual(dev.usb_vid, "18d1")


if __name__ == "__main__":
    unittest.main()
