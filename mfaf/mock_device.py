"""
MockMobileDevice — جهاز محاكى حتمي، الأساس لكل الاختبارات الآلية.

⚖️ هدف اختبار مختبري فقط. **لا يحتوي أي آلية لتجاوز حماية.** يقيس سلوك الضوابط
(تأخّر متزايد، rate limit، lockout، تحوّلات الحالة، إعادة الإقلاع). كلمات المرور
اصطناعية عبر معرّفات مدخلات فقط — لا تُخزَّن كلمات مرور حقيقية إطلاقًا.

آلة الحالة (قابلة للضبط للاختبارات):
  DISCONNECTED → CONNECTED → LOCKED → AUTH_ATTEMPT → FAIL
              → RATE_LIMITED → LOCKOUT → RECOVERY → LOCKED/UNLOCKED
"""
from __future__ import annotations

from dataclasses import dataclass, field
from .errors import SafetyBoundaryError, ValidationError


@dataclass
class MockDeviceConfig:
    # معرّف المدخل الصحيح الاصطناعي الوحيد (ليس كلمة مرور — رمز اختبار)
    correct_input_id: str = "SYNTH-CORRECT"
    # عدد المحاولات الفاشلة قبل بدء تحديد المعدّل
    rate_limit_after: int = 3
    # عدد المحاولات الفاشلة قبل الإغلاق المؤقّت
    lockout_after: int = 5
    # تأخّر أساس (ms) وزيادته عند rate limit
    base_delay_ms: float = 5.0
    rate_limit_step_ms: float = 25.0
    # مدّة الإغلاق المؤقّت بعدد "خطوات" (recover_step calls)
    lockout_recovery_steps: int = 2
    # هل يمسح إعادة الإقلاع عدّاد المحاولات؟ (سلوك يُقاس، لا يُتجاوز)
    reboot_clears_attempts: bool = False
    metadata: dict = field(default_factory=dict)


class MockMobileDevice:
    def __init__(self, config: MockDeviceConfig | None = None, target_id="mock-target-1"):
        self.config = config or MockDeviceConfig()
        self.target_id = target_id
        self.reset_test_state()

    # --------------------------------------------------- دورة الاتصال
    def connect(self):
        if self.state == "DISCONNECTED":
            self.state = "LOCKED"
        return self.state

    def disconnect(self):
        self.state = "DISCONNECTED"
        return self.state

    def reboot(self):
        """يعيد الإقلاع ويقيس أثر ذلك على الحالة (لا يتجاوزها)."""
        if self.state == "DISCONNECTED":
            return self.state
        if self.config.reboot_clears_attempts:
            self.failed_attempts = 0
            self.state = "LOCKED"
        else:
            # الحالة الآمنة تبقى: جهاز مقفل يبقى مقفلًا بعد الإقلاع
            self.state = "LOCKED" if self.state != "UNLOCKED" else "LOCKED"
        self._rate_limited = False
        return self.state

    # --------------------------------------------------- واجهة AuthenticationTarget
    def get_state(self) -> dict:
        return {
            "target_id": self.target_id,
            "state": self.state,
            "failed_attempts": self.failed_attempts,
            "locked": self.state in ("LOCKED", "RATE_LIMITED", "LOCKOUT"),
            "lockout": self.state == "LOCKOUT",
            "rate_limited": self._rate_limited,
        }

    def submit_controlled_test_attempt(self, test_input_id: str) -> dict:
        """
        محاولة اختبار مضبوطة بمعرّف مدخل اصطناعي. تعيد بيانات وصف الاستجابة.
        ترفض أي محاولة على حالة غير اختبارية (حدّ المختبر).
        """
        if not isinstance(test_input_id, str) or not test_input_id.strip():
            raise ValidationError("test_input_id مطلوب (معرّف مدخل اصطناعي)")
        # حدّ الأمان: لا "تجاوز" — نحترم حالة الإغلاق ونُبلّغ عنها
        if self.state == "DISCONNECTED":
            raise SafetyBoundaryError("الهدف غير متصل")
        if self.state == "LOCKOUT":
            # لا نتجاوز الإغلاق — نُرجع الحالة كما هي (قياس لا كسر)
            return self._response("LOCKED_OUT", extra_delay=True)
        if self.state == "UNLOCKED":
            return self._response("SUCCESS")

        self.attempt_counter += 1
        if test_input_id == self.config.correct_input_id and not self._rate_limited_block():
            self.state = "UNLOCKED"
            self.failed_attempts = 0
            return self._response("SUCCESS")

        # فشل
        self.failed_attempts += 1
        result = "FAIL"
        # تحديد المعدّل
        if self.failed_attempts >= self.config.rate_limit_after:
            self._rate_limited = True
            self.state = "RATE_LIMITED"
            result = "RATE_LIMITED"
        # الإغلاق المؤقّت
        if self.failed_attempts >= self.config.lockout_after:
            self.state = "LOCKOUT"
            self._lockout_steps_left = self.config.lockout_recovery_steps
            result = "LOCKED_OUT"
        return self._response(result)

    def get_response_metadata(self) -> dict:
        return {
            "target_id": self.target_id,
            "last_delay_ms": self._last_delay_ms,
            "attempt_counter": self.attempt_counter,
            "state": self.state,
        }

    def recover_step(self):
        """خطوة استرداد من الإغلاق المؤقّت (يقيس سلوك الاسترداد الشرعي)."""
        if self.state == "LOCKOUT":
            self._lockout_steps_left -= 1
            if self._lockout_steps_left <= 0:
                self.state = "RECOVERY"
                self._rate_limited = False
        elif self.state == "RECOVERY":
            self.state = "LOCKED"
            self.failed_attempts = max(0, self.config.rate_limit_after - 1)
        return self.state

    def reset_test_state(self):
        self.state = "DISCONNECTED"
        self.failed_attempts = 0
        self.attempt_counter = 0
        self._rate_limited = False
        self._lockout_steps_left = 0
        self._last_delay_ms = 0.0

    # --------------------------------------------------- داخلي
    def _rate_limited_block(self) -> bool:
        return self.state == "RATE_LIMITED"

    def _current_delay_ms(self, extra=False) -> float:
        delay = self.config.base_delay_ms
        if self.failed_attempts >= self.config.rate_limit_after:
            over = self.failed_attempts - self.config.rate_limit_after + 1
            delay += over * self.config.rate_limit_step_ms
        if extra:
            delay += self.config.rate_limit_step_ms * 4
        return delay

    def _response(self, result: str, extra_delay=False) -> dict:
        self._last_delay_ms = self._current_delay_ms(extra_delay)
        st = self.get_state()
        return {
            "result": result,
            "response_time_ms": self._last_delay_ms,
            "target_state": st["state"],
            "lockout_state": st["lockout"],
            "rate_limit_state": st["rate_limited"],
            "attempt_number": self.attempt_counter,
        }
