-- Scheme Intel — Payment + Authorization + Entitlement System
-- Migration: 20261004_scheme_intel_auth_payment_system.sql
-- Description: Creates users, schemes, access_keys, key_entitlements, user_scheme_entitlements,
-- products, orders, payment_events, and audit_events tables with RLS and seed data.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id TEXT UNIQUE NOT NULL,
    telegram_chat_id TEXT,
    username TEXT,
    first_name TEXT,
    status TEXT NOT NULL DEFAULT 'LOCKED' CHECK (status IN ('LOCKED', 'ACTIVE', 'SUSPENDED')),
    last_selected_scheme TEXT DEFAULT 'gobardhan',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_user_id ON users(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

-- 2. SCHEMES TABLE
CREATE TABLE IF NOT EXISTS schemes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'COMING_SOON')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_schemes_scheme_id ON schemes(scheme_id);

-- 3. ACCESS KEYS TABLE
CREATE TABLE IF NOT EXISTS access_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash TEXT UNIQUE NOT NULL,
    key_prefix TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'REVOKED', 'EXPIRED')),
    max_uses INT NOT NULL DEFAULT 1,
    used_count INT NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ,
    entitlement_duration_days INT NOT NULL DEFAULT 365,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL DEFAULT 'admin'
);

CREATE INDEX IF NOT EXISTS idx_access_keys_key_hash ON access_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_access_keys_status ON access_keys(status);

-- 4. KEY ENTITLEMENTS TABLE
CREATE TABLE IF NOT EXISTS key_entitlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    access_key_id UUID NOT NULL REFERENCES access_keys(id) ON DELETE CASCADE,
    scheme_id TEXT NOT NULL REFERENCES schemes(scheme_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(access_key_id, scheme_id)
);

CREATE INDEX IF NOT EXISTS idx_key_entitlements_access_key ON key_entitlements(access_key_id);

-- 5. USER SCHEME ENTITLEMENTS TABLE
CREATE TABLE IF NOT EXISTS user_scheme_entitlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scheme_id TEXT NOT NULL REFERENCES schemes(scheme_id) ON DELETE CASCADE,
    source TEXT NOT NULL DEFAULT 'KEY' CHECK (source IN ('KEY', 'PAYMENT', 'ADMIN')),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
    starts_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, scheme_id)
);

CREATE INDEX IF NOT EXISTS idx_user_entitlements_user_id ON user_scheme_entitlements(user_id);
CREATE INDEX IF NOT EXISTS idx_user_entitlements_scheme_id ON user_scheme_entitlements(scheme_id);
CREATE INDEX IF NOT EXISTS idx_user_entitlements_status ON user_scheme_entitlements(status);

-- 6. PRODUCTS TABLE
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    price_inr NUMERIC(10, 2) NOT NULL,
    duration_days INT NOT NULL,
    schemes JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_code ON products(product_code);

-- 7. ORDERS TABLE
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_code TEXT UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    provider TEXT NOT NULL DEFAULT 'razorpay' CHECK (provider IN ('razorpay', 'telegram_stars', 'manual_upi')),
    provider_order_id TEXT,
    provider_payment_id TEXT,
    amount NUMERIC(10, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    status TEXT NOT NULL DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'PENDING', 'PAID', 'FAILED', 'REFUNDED', 'EXPIRED')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_orders_order_code ON orders(order_code);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_provider_order_id ON orders(provider_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

-- 8. PAYMENT EVENTS TABLE
CREATE TABLE IF NOT EXISTS payment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,
    event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    signature_valid BOOLEAN NOT NULL DEFAULT false,
    processed BOOLEAN NOT NULL DEFAULT false,
    processing_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payment_events_event_id ON payment_events(event_id);
CREATE INDEX IF NOT EXISTS idx_payment_events_processed ON payment_events(processed);

-- 9. AUDIT EVENTS TABLE
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    telegram_user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    scheme_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_telegram_user ON audit_events(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at);

-- ---------------------------------------------------------------------------
-- SEED DATA
-- ---------------------------------------------------------------------------

-- Schemes
INSERT INTO schemes (scheme_id, name, description, status)
VALUES
    ('gobardhan', 'GOBARdhan', 'National Circular Bioenergy Scheme & SATAT Initiative', 'ACTIVE'),
    ('samudra_manthan', 'Samudra Manthan', 'Deepwater & Ultra-Deepwater E&P Mission', 'ACTIVE'),
    ('green_hydrogen', 'Green Hydrogen', 'National Green Hydrogen Mission', 'COMING_SOON'),
    ('solar_mission', 'Solar Mission', 'PM Surya Ghar & National Solar Mission', 'COMING_SOON')
ON CONFLICT (scheme_id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    status = EXCLUDED.status,
    updated_at = now();

-- Products
INSERT INTO products (product_code, name, description, price_inr, duration_days, schemes, status)
VALUES
    ('GOBARDHAN_MONTHLY', 'GOBARdhan — Monthly', 'Full access to GOBARdhan bioenergy intelligence for 30 days', 499.00, 30, '["gobardhan"]'::jsonb, 'ACTIVE'),
    ('GOBARDHAN_YEARLY', 'GOBARdhan — Yearly', 'Full access to GOBARdhan bioenergy intelligence for 365 days', 4999.00, 365, '["gobardhan"]'::jsonb, 'ACTIVE'),
    ('SAMUDRA_MONTHLY', 'Samudra Manthan — Monthly', 'Full access to Samudra Manthan deepwater intelligence for 30 days', 499.00, 30, '["samudra_manthan"]'::jsonb, 'ACTIVE'),
    ('SAMUDRA_YEARLY', 'Samudra Manthan — Yearly', 'Full access to Samudra Manthan deepwater intelligence for 365 days', 4999.00, 365, '["samudra_manthan"]'::jsonb, 'ACTIVE'),
    ('ALL_ACCESS_MONTHLY', 'All Access — Monthly', 'Unrestricted access to all current and future intelligence schemes for 30 days', 799.00, 30, '["gobardhan", "samudra_manthan"]'::jsonb, 'ACTIVE'),
    ('ALL_ACCESS_YEARLY', 'All Access — Yearly', 'Unrestricted access to all current and future intelligence schemes for 365 days', 7999.00, 365, '["gobardhan", "samudra_manthan"]'::jsonb, 'ACTIVE')
ON CONFLICT (product_code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    price_inr = EXCLUDED.price_inr,
    duration_days = EXCLUDED.duration_days,
    schemes = EXCLUDED.schemes,
    status = EXCLUDED.status,
    updated_at = now();

-- ---------------------------------------------------------------------------
-- ROW LEVEL SECURITY (RLS)
-- ---------------------------------------------------------------------------
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE schemes ENABLE ROW LEVEL SECURITY;
ALTER TABLE access_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE key_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_scheme_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

-- Allow service_role key full administrative bypass
DROP POLICY IF EXISTS service_role_all_users ON users;
CREATE POLICY service_role_all_users ON users TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_schemes ON schemes;
CREATE POLICY service_role_all_schemes ON schemes TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_access_keys ON access_keys;
CREATE POLICY service_role_all_access_keys ON access_keys TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_key_entitlements ON key_entitlements;
CREATE POLICY service_role_all_key_entitlements ON key_entitlements TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_user_entitlements ON user_scheme_entitlements;
CREATE POLICY service_role_all_user_entitlements ON user_scheme_entitlements TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_products ON products;
CREATE POLICY service_role_all_products ON products TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_orders ON orders;
CREATE POLICY service_role_all_orders ON orders TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_payment_events ON payment_events;
CREATE POLICY service_role_all_payment_events ON payment_events TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_audit_events ON audit_events;
CREATE POLICY service_role_all_audit_events ON audit_events TO service_role USING (true) WITH CHECK (true);
