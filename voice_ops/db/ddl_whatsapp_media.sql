-- voice_ops.whatsapp — W16 WhatsApp Media Library + delivery tracking.
-- FORCE-RLS, tenant-isolated. Applied at mount alongside config/booking/gcal DDL.
-- ZERO secrets here; WA creds live in the encrypted key store (config.keys).

-- ── Media library: one row per uploaded/saved asset (banner/image/video/PDF) ──
CREATE TABLE IF NOT EXISTS wa_media (
    id            text NOT NULL,
    org_id        text NOT NULL,
    kind          text NOT NULL DEFAULT 'image',   -- banner|image|video|brochure
    media_type    text NOT NULL DEFAULT 'image',   -- image|video|document (Meta media category)
    title         text NOT NULL DEFAULT '',
    storage_key   text NOT NULL,                    -- object key under wa_media/<org>/<id>.<ext>
    content_type  text NOT NULL DEFAULT '',
    size_bytes    bigint NOT NULL DEFAULT 0,
    width         int    NOT NULL DEFAULT 0,
    height        int    NOT NULL DEFAULT 0,
    duration_s    int    NOT NULL DEFAULT 0,
    page_count    int    NOT NULL DEFAULT 0,        -- PDF brochures
    source        text NOT NULL DEFAULT 'uploaded', -- uploaded|generated
    tags          jsonb NOT NULL DEFAULT '[]'::jsonb,
    used_count    int  NOT NULL DEFAULT 0,
    status        text NOT NULL DEFAULT 'ready',    -- ready|archived
    created_by    text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id)
);
ALTER TABLE wa_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE wa_media FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS wa_media_rls ON wa_media;
CREATE POLICY wa_media_rls ON wa_media
    USING (org_id = current_setting('app.tenant_id', true)
           OR current_setting('app.is_admin', true) = 'true')
    WITH CHECK (org_id = current_setting('app.tenant_id', true)
           OR current_setting('app.is_admin', true) = 'true');
CREATE INDEX IF NOT EXISTS wa_media_kind_idx ON wa_media (org_id, kind, status);

-- ── Delivery tracking: one row per dispatched message, latest-wins by message_id ──
CREATE TABLE IF NOT EXISTS wa_delivery (
    org_id        text NOT NULL,
    message_id    text NOT NULL,                    -- our local id pre-send; Meta wamid post-ack
    campaign_id   text NOT NULL DEFAULT '',
    template      text NOT NULL DEFAULT '',
    phone_masked  text NOT NULL DEFAULT '',
    lead_id       text NOT NULL DEFAULT '',
    status        text NOT NULL DEFAULT 'queued',   -- queued|sent|delivered|read|failed|opted_out|skipped_no_config
    reason        text NOT NULL DEFAULT '',         -- Meta's failure message, verbatim
    media_count   int  NOT NULL DEFAULT 0,
    sent_at       timestamptz,
    delivered_at  timestamptz,
    read_at       timestamptz,
    failed_at     timestamptz,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, message_id)
);
ALTER TABLE wa_delivery ENABLE ROW LEVEL SECURITY;
ALTER TABLE wa_delivery FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS wa_delivery_rls ON wa_delivery;
CREATE POLICY wa_delivery_rls ON wa_delivery
    USING (org_id = current_setting('app.tenant_id', true)
           OR current_setting('app.is_admin', true) = 'true')
    WITH CHECK (org_id = current_setting('app.tenant_id', true)
           OR current_setting('app.is_admin', true) = 'true');
CREATE INDEX IF NOT EXISTS wa_delivery_campaign_idx ON wa_delivery (org_id, campaign_id, status);
