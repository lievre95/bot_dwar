# Rate Limiting

Prevent abuse, DDoS attacks, and excessive API usage.

## When to Add Rate Limiting
- **MVP:** Optional (focus on features first)
- **Production with users:** Recommended on auth endpoints and public APIs
- **Public-facing APIs:** Required

## Setup with Upstash Redis

### 1. Install Dependencies
```bash
npm install @upstash/ratelimit @upstash/redis
```

### 2. Create Upstash Account
- Go to [upstash.com](https://upstash.com) (free tier: 10k requests/day)
- Create a Redis database
- Copy REST URL and token

### 3. Add Environment Variables
```bash
# .env.local
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxx
```

### 4. Create Rate Limiter
```typescript
// src/lib/rate-limit.ts
import { Ratelimit } from '@upstash/ratelimit'
import { Redis } from '@upstash/redis'

export const ratelimit = new Ratelimit({
  redis: Redis.fromEnv(),
  limiter: Ratelimit.slidingWindow(10, '10 s'), // 10 requests per 10 seconds
})
```

### 5. Use in API Routes
```typescript
// src/app/api/example/route.ts
import { ratelimit } from '@/lib/rate-limit'
import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  const ip = request.headers.get('x-forwarded-for') ?? 'anonymous'
  const { success, limit, remaining } = await ratelimit.limit(ip)

  if (!success) {
    return NextResponse.json(
      { error: 'Too many requests' },
      {
        status: 429,
        headers: {
          'X-RateLimit-Limit': limit.toString(),
          'X-RateLimit-Remaining': remaining.toString(),
        },
      }
    )
  }

  // Process request normally...
}
```

### 6. Use in Middleware (Global)
```typescript
// middleware.ts
import { ratelimit } from '@/lib/rate-limit'
import { NextRequest, NextResponse } from 'next/server'

export async function middleware(request: NextRequest) {
  // Only rate limit API routes
  if (request.nextUrl.pathname.startsWith('/api/')) {
    const ip = request.headers.get('x-forwarded-for') ?? 'anonymous'
    const { success } = await ratelimit.limit(ip)

    if (!success) {
      return NextResponse.json({ error: 'Too Many Requests' }, { status: 429 })
    }
  }
}

export const config = {
  matcher: '/api/:path*',
}
```

## Recommended Limits

| Endpoint Type | Limit | Window |
|--------------|-------|--------|
| Login/Register | 5 requests | 1 minute |
| Password Reset | 3 requests | 5 minutes |
| General API | 30 requests | 10 seconds |
| File Upload | 5 requests | 1 minute |

## Alternative
**Vercel Edge Config** - Simpler but less flexible. Built into Vercel, no external service needed.
