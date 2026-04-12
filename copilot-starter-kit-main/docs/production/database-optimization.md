# Database Optimization

## 1. Indexing

Create indexes on columns used in WHERE, ORDER BY, or JOIN clauses:

```sql
-- Without index: ~500ms at 100k rows
SELECT * FROM tasks WHERE user_id = 'abc123' ORDER BY created_at DESC;

-- After creating index: <10ms
CREATE INDEX idx_tasks_user_id_created ON tasks(user_id, created_at DESC);
```

**Rule of thumb:** If a column appears in WHERE or ORDER BY and the table will have >1000 rows, add an index.

Always include indexes in your migration SQL alongside CREATE TABLE.

## 2. Avoid N+1 Queries

The most common performance problem with ORMs and query builders:

```typescript
// Bad: N+1 (1 query for users + N queries for tasks)
const { data: users } = await supabase.from('users').select('*')
for (const user of users) {
  const { data: tasks } = await supabase
    .from('tasks')
    .select('*')
    .eq('user_id', user.id)
}

// Good: Single query with join (1 query total)
const { data } = await supabase
  .from('users')
  .select('*, tasks(*)')
```

## 3. Always Limit Results

Never return unbounded results from the database:

```typescript
// Bad: Returns ALL rows
const { data } = await supabase.from('tasks').select('*')

// Good: Returns max 50 rows
const { data } = await supabase.from('tasks').select('*').limit(50)

// Better: Paginated
const { data } = await supabase
  .from('tasks')
  .select('*')
  .range(0, 49)  // First 50 rows
```

## 4. Caching Strategy

For data that changes rarely (dashboard stats, config, categories):

```typescript
import { unstable_cache } from 'next/cache'

export const getCategories = unstable_cache(
  async () => {
    const { data } = await supabase.from('categories').select('*')
    return data
  },
  ['categories'],          // Cache key
  { revalidate: 3600 }    // Refresh every hour
)
```

**When to cache:**
- Data that changes less than once per hour
- Expensive aggregation queries
- Data shared across all users (not user-specific)

**When NOT to cache:**
- User-specific data that changes frequently
- Real-time data (use Supabase Realtime instead)

## 5. Select Only What You Need

```typescript
// Bad: Fetches all columns
const { data } = await supabase.from('users').select('*')

// Good: Fetches only needed columns
const { data } = await supabase.from('users').select('id, name, avatar_url')
```
