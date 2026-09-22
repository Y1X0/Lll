# MFAF — Laboratory Forensic Workflow

مثال دورة كاملة على مجموعة بيانات اصطناعية (بلا جهاز فعلي).

```bash
DB=mfaf.db
# 1) الفاحص والقضية (التفويض يُدخَل يدويًا — المنصّة لا تخترعه)
python3 -m mfaf.cli --db $DB examiner add --id ex1 --name "Examiner A" --org "Lab"
python3 -m mfaf.cli --db $DB case create --id CASE-2026-001 --title "Test acquisition" \
    --examiner ex1 --authority "WARRANT/REF-manual"

# 2) تعريف الجهاز (الحقول غير المتاحة = null)
python3 -m mfaf.cli --db $DB device detect --id dev1 --case CASE-2026-001 \
    --os android --vid 18d1 --pid 4ee7 --manufacturer Google --model Pixel

# 3) اقتناء مصرّح به (mock/filesystem). المنصّة الحقيقية تُرجِع NOT_AVAILABLE بأمان.
python3 -m mfaf.cli --db $DB acquisition start --case CASE-2026-001 --device dev1 \
    --provider mock --store ./evidence_store --examiner ex1

# 4) جرد الأدلّة والتحقّق من السلامة
python3 -m mfaf.cli --db $DB evidence list --case CASE-2026-001
python3 -m mfaf.cli --db $DB evidence verify --id <EVIDENCE_ID>

# 5) تجربة مصادقة مضبوطة على المحاكي (قياس، لا كسر)
python3 -m mfaf.cli --db $DB experiment create --id X1 --case CASE-2026-001 --code EXP-005
python3 -m mfaf.cli --db $DB experiment run --id X1 --attempts 6

# 6) الخطّ الزمني والتقرير
python3 -m mfaf.cli --db $DB timeline show --case CASE-2026-001
python3 -m mfaf.cli --db $DB report generate --case CASE-2026-001 --format markdown \
    --out report.md
```

**تشغيل الاختبارات:** `python3 -m unittest discover -s mfaf/tests -p 'test_*.py'`
