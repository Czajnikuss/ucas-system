-- Set up error handling
DO $$ 
BEGIN
    -- Create user if not exists
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'ucas_user') THEN
        CREATE USER ucas_user WITH PASSWORD 'ucas_password_123';
    END IF;
    
    -- Grant database ownership
    ALTER DATABASE ucas_db OWNER TO ucas_user;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Error during user setup: %', SQLERRM;
END $$;


-- Enable extensions (as superuser)
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
    embedding VECTOR(384),
    
    -- Quality Scoring Fields
    quality_score FLOAT DEFAULT NULL,
    quality_scored_at TIMESTAMP,
    quality_reasoning TEXT,
    quality_metrics JSONB,
    
    -- Curation Fields
    is_active BOOLEAN DEFAULT TRUE,
    archived_at TIMESTAMP,
    archive_reason VARCHAR(100),
    
    -- Legacy field (kept for backwards compatibility)
    is_new BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    source VARCHAR(50) DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT NOW()
);



CREATE TABLE IF NOT EXISTS classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    categorizer_id UUID REFERENCES categorizers(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    predicted_category VARCHAR(100),
    confidence FLOAT,
    method VARCHAR(50),
    reasoning TEXT,
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



-- Curation Runs (tracking history)
CREATE TABLE IF NOT EXISTS curation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    categorizer_id UUID REFERENCES categorizers(id) ON DELETE CASCADE,
    run_at TIMESTAMP DEFAULT NOW(),
    trigger_reason VARCHAR(50),
    iteration_number INT,
    
    -- Stats
    total_samples_before INT,
    total_samples_after INT,
    archived_count INT,
    removed_low_quality_count INT,
    avg_quality_before FLOAT,
    avg_quality_after FLOAT,
    
    -- Config snapshot
    config JSONB,
    
    -- Re-evaluation tracking
    triggered_reevaluation BOOLEAN DEFAULT FALSE,
    
    processing_time_ms INT
);



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



-- Indexes
CREATE INDEX IF NOT EXISTS idx_categorizers_id ON categorizers(categorizer_id);
CREATE INDEX IF NOT EXISTS idx_categorizers_name ON categorizers(name);

CREATE INDEX IF NOT EXISTS idx_training_samples_categorizer ON training_samples(categorizer_id);
CREATE INDEX IF NOT EXISTS idx_training_samples_is_new ON training_samples(is_new);
CREATE INDEX IF NOT EXISTS idx_training_samples_embedding ON training_samples USING ivfflat (embedding vector_cosine_ops);

-- New indexes for quality scoring & curation
CREATE INDEX IF NOT EXISTS idx_training_samples_unscored 
    ON training_samples(categorizer_id, quality_score) 
    WHERE quality_score IS NULL AND is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_training_samples_active_quality 
    ON training_samples(categorizer_id, quality_score DESC) 
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_classifications_categorizer ON classifications(categorizer_id);
CREATE INDEX IF NOT EXISTS idx_classifications_created ON classifications(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hil_reviews_categorizer ON hil_reviews(categorizer_id);
CREATE INDEX IF NOT EXISTS idx_hil_reviews_status ON hil_reviews(status);
CREATE INDEX IF NOT EXISTS idx_hil_reviews_created ON hil_reviews(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_curation_runs_categorizer ON curation_runs(categorizer_id, run_at DESC);



-- Grant privileges on all objects to ucas_user
DO $$ 
BEGIN
    -- Grant privileges on all existing tables
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ucas_user;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ucas_user;
    
    -- Grant privileges on future tables
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ucas_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ucas_user;
    
    -- Grant schema usage
    GRANT USAGE ON SCHEMA public TO ucas_user;
    
    -- Grant execute on functions
    GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO ucas_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO ucas_user;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Error during privilege setup: %', SQLERRM;
END $$;


SELECT format(
    'Database initialized successfully at %s. User ucas_user %s.', 
    NOW()::text,
    CASE 
        WHEN EXISTS (SELECT FROM pg_user WHERE usename = 'ucas_user') 
        THEN 'exists and has proper privileges'
        ELSE 'could not be verified - check logs'
    END
) as message;



-- Similarity search function for embeddings (updated for active samples)
CREATE OR REPLACE FUNCTION search_similar_samples(
    query_embedding VECTOR(384),
    categorizer_uuid UUID,
    similarity_threshold FLOAT DEFAULT 0.7,
    limit_count INT DEFAULT 5
) RETURNS TABLE (
    id UUID,
    text TEXT,
    category VARCHAR(100),
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ts.id,
        ts.text,
        ts.category,
        1 - (ts.embedding <=> query_embedding) AS similarity
    FROM training_samples ts
    WHERE ts.categorizer_id = categorizer_uuid
        AND ts.embedding IS NOT NULL
        AND ts.is_active = TRUE
        AND (1 - (ts.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY ts.embedding <=> query_embedding
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;



-- Helper function: Count unscored samples
CREATE OR REPLACE FUNCTION count_unscored_samples(cat_id UUID) 
RETURNS INT AS $$
    SELECT COUNT(*)::INT 
    FROM training_samples 
    WHERE categorizer_id = cat_id 
      AND quality_score IS NULL 
      AND is_active = TRUE;
$$ LANGUAGE SQL;



-- Helper function: Get curation iteration count
CREATE OR REPLACE FUNCTION get_curation_iteration(cat_id UUID) 
RETURNS INT AS $$
    SELECT COALESCE(MAX(iteration_number), 0)::INT 
    FROM curation_runs 
    WHERE categorizer_id = cat_id;
$$ LANGUAGE SQL;



-- Helper function: Check if re-evaluation needed
CREATE OR REPLACE FUNCTION needs_reevaluation(cat_id UUID, max_iterations INT DEFAULT 8) 
RETURNS BOOLEAN AS $$
    SELECT 
        CASE 
            WHEN COUNT(*) = 0 THEN FALSE
            WHEN MAX(iteration_number) - COALESCE(
                (SELECT MAX(iteration_number) 
                 FROM curation_runs 
                 WHERE categorizer_id = cat_id AND triggered_reevaluation = TRUE), 0
            ) >= max_iterations THEN TRUE
            ELSE FALSE
        END
    FROM curation_runs
    WHERE categorizer_id = cat_id;
$$ LANGUAGE SQL;


-- Webhooks table
CREATE TABLE IF NOT EXISTS webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    url VARCHAR(2048) NOT NULL UNIQUE,
    
    -- v1.0 placeholders
    categorizer_filter VARCHAR(255),
    role_required VARCHAR(50),
    
    is_active BOOLEAN DEFAULT TRUE,
    last_triggered_at TIMESTAMP,
    failed_attempts INT DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Webhook delivery history
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id UUID REFERENCES webhooks(id) ON DELETE CASCADE,
    
    hil_review_id UUID NOT NULL,
    categorizer_id VARCHAR(255) NOT NULL,
    
    status VARCHAR(50) DEFAULT 'pending',
    response_code INT,
    response_body TEXT,
    error_message TEXT,
    
    created_at TIMESTAMP DEFAULT NOW(),
    sent_at TIMESTAMP
);

CREATE INDEX idx_webhooks_active ON webhooks(is_active);
CREATE INDEX idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);
CREATE INDEX idx_webhook_deliveries_status ON webhook_deliveries(status);


