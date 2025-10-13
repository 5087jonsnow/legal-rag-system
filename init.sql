-- Legal RAG System Database Schema
-- PostgreSQL initialization script

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Organizations (Law Firms)
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    subscription_tier VARCHAR(50) DEFAULT 'free',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'lawyer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- Documents
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    
    -- Legal metadata
    citation VARCHAR(255),
    court_name VARCHAR(255),
    court_level VARCHAR(50),
    state VARCHAR(100),
    bench_strength INTEGER,
    judges TEXT[],
    decision_date DATE,
    filing_date DATE,
    
    -- Content metadata
    party_names TEXT[],
    statutes_cited TEXT[],
    sections_cited TEXT[],
    case_numbers TEXT[],
    
    -- Processing status
    processing_status VARCHAR(50) DEFAULT 'pending',
    vector_indexed BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_org ON documents(organization_id);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_court ON documents(court_name);
CREATE INDEX IF NOT EXISTS idx_documents_date ON documents(decision_date);
CREATE INDEX IF NOT EXISTS idx_documents_citation ON documents(citation);

-- Queries (Search history)
CREATE TABLE IF NOT EXISTS queries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    
    query_text TEXT NOT NULL,
    query_intent VARCHAR(50),
    
    -- Results
    retrieved_document_ids UUID[],
    response_text TEXT,
    citations_used TEXT[],
    
    -- Performance metrics
    retrieval_latency_ms INTEGER,
    llm_latency_ms INTEGER,
    total_latency_ms INTEGER,
    tokens_used INTEGER,
    
    -- User feedback
    feedback_score INTEGER,
    feedback_text TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_queries_user ON queries(user_id);
CREATE INDEX IF NOT EXISTS idx_queries_org ON queries(organization_id);
CREATE INDEX IF NOT EXISTS idx_queries_created ON queries(created_at);

-- Insert demo data
INSERT INTO organizations (name, slug, subscription_tier) 
VALUES ('Demo Law Firm', 'demo-law-firm', 'pro')
ON CONFLICT (slug) DO NOTHING;

-- Insert demo user
INSERT INTO users (email, full_name, organization_id, role)
SELECT 'admin@demolawfirm.com', 'Admin User', id, 'admin'
FROM organizations WHERE slug = 'demo-law-firm'
ON CONFLICT (email) DO NOTHING;