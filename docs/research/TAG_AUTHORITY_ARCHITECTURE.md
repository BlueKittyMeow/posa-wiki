# Tag Authority Architecture Analysis

## Current System (JSON-based)

### ✅ **Pros:**
- **Simple**: Easy to read/edit manually
- **Portable**: Single file, easy to backup/version
- **Fast**: No DB queries for authority lookup
- **Version controlled**: Changes tracked in git

### ❌ **Cons:**
- **Manual process**: Adding authorities requires code changes
- **No web interface**: Can't manage through wiki UI
- **Rigid structure**: Hard to add metadata or relationships
- **Re-validation needed**: Every change requires database re-run
- **No audit trail**: Can't track who changed what when

## Proposed Database System

### 🗄️ **Tag Authority Tables:**

```sql
-- Core authority table
CREATE TABLE tag_authorities (
    authority_id INTEGER PRIMARY KEY,
    canonical_name VARCHAR NOT NULL UNIQUE,
    category VARCHAR NOT NULL, -- 'activity', 'location', 'weather', etc.
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR DEFAULT 'system',
    is_active BOOLEAN DEFAULT TRUE
);

-- Aliases table (many-to-one)
CREATE TABLE tag_aliases (
    alias_id INTEGER PRIMARY KEY,
    authority_id INTEGER REFERENCES tag_authorities(authority_id),
    alias_text VARCHAR NOT NULL,
    confidence DECIMAL DEFAULT 1.0, -- How confident are we in this mapping?
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR DEFAULT 'system',
    UNIQUE(alias_text)
);

-- Authority usage tracking
CREATE TABLE tag_authority_usage (
    authority_id INTEGER REFERENCES tag_authorities(authority_id),
    total_videos INTEGER DEFAULT 0,
    total_instances INTEGER DEFAULT 0,
    last_seen TIMESTAMP,
    PRIMARY KEY (authority_id)
);
```

### 🚀 **Benefits of DB Approach:**

1. **Web Management Interface:**
   ```sql
   -- Add new authority via web form
   INSERT INTO tag_authorities (canonical_name, category, description) 
   VALUES ('Backcountry Camping', 'activity', 'Remote wilderness camping');
   
   -- Add aliases dynamically
   INSERT INTO tag_aliases (authority_id, alias_text) 
   VALUES (43, 'backcountry camping'), (43, 'wilderness camping');
   ```

2. **Real-time Validation:**
   - No regeneration needed
   - Instant authority updates
   - Live tag suggestion as you type

3. **Analytics & Insights:**
   ```sql
   -- Find most impactful missing authorities
   SELECT unvalidated_tag, COUNT(*) as frequency 
   FROM unvalidated_tag_analysis 
   WHERE frequency > 10 
   ORDER BY frequency DESC;
   
   -- Authority effectiveness
   SELECT canonical_name, total_videos, total_instances 
   FROM tag_authorities 
   JOIN tag_authority_usage USING(authority_id)
   ORDER BY total_instances DESC;
   ```

4. **Collaborative Management:**
   - Track who added what authority
   - Approval workflows for new authorities
   - Confidence scoring for uncertain mappings

## Migration Strategy

### Phase 1: **Hybrid Approach**
- Keep JSON for core authorities (proven stable)
- Add DB table for "experimental" authorities
- Validation checks both sources

### Phase 2: **Full Migration**
- Import all JSON authorities to DB
- Build web management interface
- Retire JSON system

### Phase 3: **Advanced Features**
- Machine learning suggestions for new authorities
- Community contribution system
- Authority relationship mapping

## Immediate Recommendation

**For now**: Let's add the high-impact authorities manually (backcountry camping, outdoorsman, etc.) to JSON, then design the DB system properly.

**High-impact additions needed:**
- Backcountry Camping (109 uses)
- Outdoorsman (117 uses) 
- Wilderness Camping (59 uses)
- Captain Teeny Trout (4 uses, important character)

This would bring us from **58.6%** to likely **65%+** tag coverage - a massive improvement for minimal effort.