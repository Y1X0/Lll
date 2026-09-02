-- MIFTAH — Vehicle Knowledge Database
-- PostgreSQL 15+ (cloud master).  Subset is exported to SQLite on-device.
-- Version 0.1.0

BEGIN;

CREATE TYPE protocol_t AS ENUM (
    'CAN_ISOTP_11B_500K', 'CAN_ISOTP_29B_500K', 'CAN_FD',
    'KLINE_ISO9141', 'KLINE_KWP2000_SLOW', 'KLINE_KWP2000_FAST', 'DOIP'
);

CREATE TYPE key_state_t AS ENUM (
    'ADD_KEY',            -- عميل يملك مفتاحًا عاملاً ويريد نسخة إضافية
    'ALL_KEYS_LOST',      -- فقدان كامل
    'ECU_REPLACEMENT',    -- استبدال وحدة يتطلب اقترانًا
    'KEY_REMOVAL'         -- شطب مفتاح مفقود من الذاكرة
);

CREATE TYPE proc_path_t AS ENUM (
    'SELF',            -- ينفّذها جهازنا بالكامل (لا يتجاوز أي حماية)
    'OEM_PASSTHRU',    -- برنامج OEM مرخّص عبر جهازنا كواجهة J2534
    'REMOTE_TECH',     -- فنّي معتمد ينفّذها عن بُعد
    'DEALER_ONLY',     -- الوكالة حصرًا
    'NOT_SUPPORTED'    -- غير مدعوم / غير معروف
);

CREATE TYPE proc_status_t AS ENUM (
    'VERIFIED',            -- مؤكّد على مركبة حقيقية من قِبلنا
    'COMMUNITY_REPORTED',  -- من تقارير الفنّيين، غير مؤكّد داخليًا
    'UNTESTED',            -- استدلال — لا يُعرض كقابل للتنفيذ
    'DEPRECATED',
    'BLOCKED'              -- محظور عمدًا (قانوني/سلامة)
);

CREATE TYPE key_system_t AS ENUM (
    'MECHANICAL',
    'TRANSPONDER_FIXED',      -- 4C-class
    'TRANSPONDER_CRYPTO_40',  -- 4D-class
    'TRANSPONDER_CRYPTO_80',  -- G-class
    'TRANSPONDER_AES',        -- H-class
    'SMART_KEY_CRYPTO_80',
    'SMART_KEY_AES',
    'SMART_KEY_HARDENED'      -- أجيال 2020+ ذات قيود AKL إضافية
);

-- ---------------------------------------------------------------- taxonomy
CREATE TABLE makes (
    id           SMALLSERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    name_ar      TEXT NOT NULL,
    oem_portal   TEXT,             -- بوابة البيانات الفنية الرسمية
    oem_notes    TEXT
);

CREATE TABLE models (
    id           SERIAL PRIMARY KEY,
    make_id      SMALLINT NOT NULL REFERENCES makes(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    name_ar      TEXT NOT NULL,
    UNIQUE (make_id, name)
);

CREATE TABLE generations (
    id              SERIAL PRIMARY KEY,
    model_id        INT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    code            TEXT NOT NULL,          -- 'XA40'
    name_ar         TEXT,
    year_from       SMALLINT NOT NULL,
    year_to         SMALLINT,               -- NULL = لا يزال في الإنتاج
    UNIQUE (model_id, code)
);

-- التنويعة = الوحدة الحقيقية للسلوك (جيل + سوق + نافذة إنتاج)
CREATE TABLE variants (
    id              SERIAL PRIMARY KEY,
    generation_id   INT NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    market          TEXT NOT NULL,          -- 'GCC','EU','US','JP','GLOBAL'
    production_from DATE NOT NULL,
    production_to   DATE,
    key_system      key_system_t NOT NULL,
    transponder_family TEXT,                -- وصف حرّ: '4D-72 (G)', 'DST-AES (H)'
    has_smart_key   BOOLEAN NOT NULL DEFAULT FALSE,
    notes_ar        TEXT,
    notes_en        TEXT
);
CREATE INDEX ON variants (generation_id, market);

-- ------------------------------------------------------- VIN presumption
CREATE TABLE vin_patterns (
    id           SERIAL PRIMARY KEY,
    variant_id   INT NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
    wmi          CHAR(3) NOT NULL,       -- World Manufacturer Identifier
    vds_regex    TEXT,                   -- نمط لموضع 4..8
    year_code    CHAR(1),                -- موضع 10
    plant_code   CHAR(1),                -- موضع 11
    confidence   SMALLINT NOT NULL DEFAULT 70 CHECK (confidence BETWEEN 0 AND 100)
);
CREATE INDEX ON vin_patterns (wmi);

-- ------------------------------------------------- confirmation by scan
-- تأكيد التنويعة من بصمة الوحدات الفعلية — يتفوّق دائمًا على ترجيح VIN
CREATE TABLE ecu_fingerprints (
    id              SERIAL PRIMARY KEY,
    variant_id      INT NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
    ecu_role        TEXT NOT NULL,       -- 'ECM','CERTIFICATION','IMMOBILIZER','BODY','GATEWAY'
    request_id      INT,                 -- عنوان CAN للطلب (يُملأ بالقياس فقط)
    response_id     INT,                 -- عنوان CAN للردّ
    part_number_re  TEXT,                -- نمط رقم القطعة المتوقّع
    required_dids   TEXT[],              -- DIDs يجب أن تكون موجودة
    forbidden_dids  TEXT[],              -- DIDs يجب ألا تكون موجودة
    weight          SMALLINT NOT NULL DEFAULT 10,
    verified_on     DATE,                -- تاريخ التأكيد على مركبة حقيقية
    verified_by     TEXT
);
CREATE INDEX ON ecu_fingerprints (variant_id);

-- ------------------------------------------------- transport profile
CREATE TABLE vehicle_profiles (
    id              SERIAL PRIMARY KEY,
    variant_id      INT NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
    protocol        protocol_t NOT NULL,
    bitrate         INT NOT NULL DEFAULT 500000,
    isotp_padding   BOOLEAN NOT NULL DEFAULT TRUE,
    isotp_pad_byte  SMALLINT NOT NULL DEFAULT 0,
    stmin_ms        SMALLINT NOT NULL DEFAULT 0,
    block_size      SMALLINT NOT NULL DEFAULT 0,
    p2_timeout_ms   INT NOT NULL DEFAULT 50,
    p2star_timeout_ms INT NOT NULL DEFAULT 5000,
    tester_present_ms INT NOT NULL DEFAULT 2000,
    safe_read_dids  TEXT[] NOT NULL DEFAULT '{}',  -- DIDs مؤكّد أنها آمنة للقراءة
    UNIQUE (variant_id, protocol)
);

-- ------------------------------------------------------- procedures
CREATE TABLE procedures (
    id                  SERIAL PRIMARY KEY,
    variant_id          INT NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
    key_state           key_state_t NOT NULL,
    path                proc_path_t NOT NULL,
    status              proc_status_t NOT NULL DEFAULT 'UNTESTED',
    -- الحدود الأمنية: توثيق صريح لما لا نفعله
    requires_security_access BOOLEAN NOT NULL DEFAULT FALSE,
    requires_oem_code        BOOLEAN NOT NULL DEFAULT FALSE,
    -- التقديرات المعروضة للفنّي
    est_duration_min    SMALLINT,
    est_oem_cost_usd    NUMERIC(8,2),
    est_service_price_usd NUMERIC(8,2),
    min_firmware        TEXT NOT NULL DEFAULT '1.0.0',
    min_app_version     TEXT NOT NULL DEFAULT '1.0.0',
    success_count       INT NOT NULL DEFAULT 0,
    failure_count       INT NOT NULL DEFAULT 0,
    notes_ar            TEXT,
    notes_en            TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (variant_id, key_state)
);
CREATE INDEX ON procedures (status, path);

-- قيد صريح: أي إجراء يتطلب Security Access لا يجوز أن يكون مساره SELF
ALTER TABLE procedures ADD CONSTRAINT no_self_security_bypass
    CHECK (NOT (requires_security_access AND path = 'SELF'));
ALTER TABLE procedures ADD CONSTRAINT no_self_oem_code
    CHECK (NOT (requires_oem_code AND path = 'SELF'));

CREATE TABLE procedure_steps (
    id              SERIAL PRIMARY KEY,
    procedure_id    INT NOT NULL REFERENCES procedures(id) ON DELETE CASCADE,
    step_no         SMALLINT NOT NULL,
    kind            TEXT NOT NULL,   -- 'INSTRUCTION','DEVICE_ACTION','USER_CONFIRM','OEM_HANDOFF','CHECK'
    title_ar        TEXT NOT NULL,
    title_en        TEXT NOT NULL,
    body_ar         TEXT,
    body_en         TEXT,
    image_ref       TEXT,
    timeout_s       SMALLINT,
    UNIQUE (procedure_id, step_no)
);

CREATE TABLE required_equipment (
    id              SERIAL PRIMARY KEY,
    procedure_id    INT NOT NULL REFERENCES procedures(id) ON DELETE CASCADE,
    item            TEXT NOT NULL,   -- 'KEY_CUTTING_MACHINE','TRANSPONDER_WRITER','BATTERY_SUPPORT','WINDOWS_PC'
    mandatory       BOOLEAN NOT NULL DEFAULT TRUE,
    notes_ar        TEXT
);

CREATE TABLE authorization_requirements (
    id              SERIAL PRIMARY KEY,
    procedure_id    INT NOT NULL REFERENCES procedures(id) ON DELETE CASCADE,
    requirement     TEXT NOT NULL,   -- 'OWNERSHIP_PROOF','ID_MATCH','TECH_CERTIFICATION','OEM_ACCOUNT','SIGNED_DECLARATION'
    jurisdiction    TEXT NOT NULL DEFAULT 'GLOBAL',   -- 'JO','SA','US','EU'
    mandatory       BOOLEAN NOT NULL DEFAULT TRUE,
    notes_ar        TEXT
);

-- ------------------------------------------------------- data packaging
CREATE TABLE data_releases (
    id              SERIAL PRIMARY KEY,
    version         TEXT NOT NULL UNIQUE,   -- semver
    published_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    signature       BYTEA NOT NULL,          -- Ed25519 على مانفست الحزمة
    manifest_sha256 BYTEA NOT NULL,
    channel         TEXT NOT NULL DEFAULT 'stable'  -- 'stable','beta','internal'
);

-- ------------------------------------------------------- feedback loop
CREATE TABLE procedure_reports (
    id              BIGSERIAL PRIMARY KEY,
    procedure_id    INT REFERENCES procedures(id) ON DELETE SET NULL,
    device_id       UUID NOT NULL,
    outcome         TEXT NOT NULL,   -- 'SUCCESS','FAILED','ABORTED','MISMATCH'
    failure_reason  TEXT,
    detected_variant_id INT REFERENCES variants(id),
    vin_hash        BYTEA,           -- SHA-256(VIN + pepper) — لا نخزّن VIN خامًا
    firmware        TEXT,
    app_version     TEXT,
    reported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON procedure_reports (procedure_id, outcome);
CREATE INDEX ON procedure_reports (reported_at DESC);

COMMIT;
