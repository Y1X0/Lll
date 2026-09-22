"""
طبقة رصد/جرد USB — تولّد أحداثًا مبنيّة عن الاتصال/الفصل والتعريف.

⚖️ رصد فقط. **لا تنفّذ أي أوامر على الأجهزة المتصلة.** بيانات USB لا يُوثَق بها —
تُعقّم وتُتحقّق. الوضع الافتراضي محاكاة/جرد؛ أي تكامل حقيقي يكون عبر آلية موثّقة
ومصرّح بها منفصلة (غير مضمّنة هنا).
"""
from __future__ import annotations

from . import models as M
from . import validation as V

USB_EVENT_TYPES = ("USB_CONNECTED", "USB_DISCONNECTED", "DEVICE_IDENTIFIED",
                   "INTERFACE_DISCOVERED")


def _clean_usb_field(value, field):
    if value is None:
        return None
    # قيم USB لا يُوثق بها: تُعقّم كنص قصير بلا محارف تحكّم
    return V.clean_text(str(value), field, max_len=256, allow_none=True, allow_empty=True)


def make_usb_event(event_type: str, vid=None, pid=None, manufacturer=None,
                   product=None, interface=None, timestamp=None) -> dict:
    """يبني حدث USB مبنيًّا ومُعقّمًا. يرفع ValidationError لنوع غير معروف."""
    V.validate_choice(event_type, USB_EVENT_TYPES, "usb_event_type")
    return {
        "event_type": event_type,
        "usb_vid": _clean_usb_field(vid, "usb_vid"),
        "usb_pid": _clean_usb_field(pid, "usb_pid"),
        "manufacturer": _clean_usb_field(manufacturer, "manufacturer"),
        "product": _clean_usb_field(product, "product"),
        "interface": _clean_usb_field(interface, "interface"),
        "timestamp": timestamp or M.utcnow(),
    }


class USBObserver:
    """جامع أحداث USB (محاكاة/جرد). لا يلمس الأجهزة."""

    def __init__(self):
        self.events: list[dict] = []

    def record(self, event_type, **kw) -> dict:
        ev = make_usb_event(event_type, **kw)
        self.events.append(ev)
        return ev

    def connected(self, vid=None, pid=None, manufacturer=None, product=None):
        return self.record("USB_CONNECTED", vid=vid, pid=pid,
                           manufacturer=manufacturer, product=product)

    def disconnected(self, vid=None, pid=None):
        return self.record("USB_DISCONNECTED", vid=vid, pid=pid)

    def identified(self, vid=None, pid=None, manufacturer=None, product=None):
        return self.record("DEVICE_IDENTIFIED", vid=vid, pid=pid,
                           manufacturer=manufacturer, product=product)

    def interface(self, interface=None):
        return self.record("INTERFACE_DISCOVERED", interface=interface)

    def to_device(self, device_id, case_id=None, os_family="unknown",
                  connection_mode="usb") -> M.Device:
        """يشتقّ سجلّ Device من آخر حدث تعريف (حقول غير المتاحة = None صريح)."""
        ident = next((e for e in reversed(self.events)
                      if e["event_type"] == "DEVICE_IDENTIFIED"), None) or {}
        return M.Device(
            device_id=device_id, case_id=case_id, os_family=os_family,
            manufacturer=ident.get("manufacturer"), usb_vid=ident.get("usb_vid"),
            usb_pid=ident.get("usb_pid"), model=ident.get("product"),
            serial=None, connection_mode=connection_mode, transport="usb")
