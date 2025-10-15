-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- Create main database schema
CREATE TABLE IF NOT EXISTS categorizers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    categorizer_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    description TEXT,
    categories JSONB,
    fallback_category VARCHAR(100),
    layers JSONB,
    config JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS training_samples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    categorizer_id UUID REFERENCES categorizers(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    category VARCHAR(100) NOT NULL,
    is_new BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    categorizer_id UUID REFERENCES categorizers(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    predicted_category VARCHAR(100),
    confidence FLOAT,
    method VARCHAR(50),
    is_fallback BOOLEAN DEFAULT FALSE,
    processing_time_ms FLOAT,
    cascade_results JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS hil_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    categorizer_id UUID REFERENCES categorizers(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    suggested_category VARCHAR(255),
    suggested_confidence FLOAT,
    context JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    human_category VARCHAR(255),
    human_notes TEXT,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);


-- Indexes
CREATE INDEX IF NOT EXISTS idx_training_samples_categorizer ON training_samples(categorizer_id);
CREATE INDEX IF NOT EXISTS idx_training_samples_is_new ON training_samples(is_new);
CREATE INDEX IF NOT EXISTS idx_classifications_categorizer ON classifications(categorizer_id);
CREATE INDEX IF NOT EXISTS idx_classifications_created ON classifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hil_reviews_categorizer ON hil_reviews(categorizer_id);
CREATE INDEX IF NOT EXISTS idx_hil_reviews_status ON hil_reviews(status);
CREATE INDEX IF NOT EXISTS idx_hil_reviews_created ON hil_reviews(created_at DESC);


-- Future tables (for Evaluator - TIER 2)
CREATE TABLE IF NOT EXISTS sample_quality (
    sample_id UUID PRIMARY KEY REFERENCES training_samples(id) ON DELETE CASCADE,
    informativeness FLOAT CHECK (informativeness BETWEEN 0 AND 1),
    standardness FLOAT CHECK (standardness BETWEEN 0 AND 1),
    originality FLOAT CHECK (originality BETWEEN 0 AND 1),
    diversity FLOAT CHECK (diversity BETWEEN 0 AND 1),
    complexity FLOAT CHECK (complexity BETWEEN 0 AND 1),
    overall_score FLOAT,
    evaluated_at TIMESTAMP DEFAULT NOW()
);


-- User setup
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'ucas_user') THEN
        CREATE USER ucas_user WITH PASSWORD 'ucas_password_123';
    END IF;
END
$$;


GRANT ALL PRIVILEGES ON DATABASE ucas_db TO ucas_user;
ALTER DATABASE ucas_db OWNER TO ucas_user;


SELECT 'Database initialized successfully!' as message;
