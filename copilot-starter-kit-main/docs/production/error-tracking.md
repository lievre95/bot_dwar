# Error Tracking Setup (Sentry)

Track production errors automatically so you know about issues before your users report them.

## Setup (5 minutes)

### 1. Create Sentry Account
- Go to [sentry.io](https://sentry.io) (free tier available for small apps)
- Create a new project and select "Next.js"

### 2. Install Next.js Integration
```bash
npx @sentry/wizard@latest -i nextjs
```
This automatically:
- Installs `@sentry/nextjs`
- Creates `sentry.client.config.ts` and `sentry.server.config.ts`
- Updates `next.config.ts` with Sentry webpack plugin

### 3. Add Environment Variables
Add to `.env.local` (local) and Vercel Dashboard (production):
```bash
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
NEXT_PUBLIC_SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
SENTRY_AUTH_TOKEN=sntrys_xxx  # For source maps upload
```

### 4. Verify Setup
Trigger a test error and check Sentry Dashboard:
```typescript
// Temporary test - remove after verification
throw new Error("Sentry test error")
```

## What You Get
- Automatic error capture (client + server)
- Stack traces with source maps
- Error grouping and deduplication
- Email alerts for new errors
- Performance monitoring (optional)

## Alternative
**Vercel Error Tracking** - Built-in, simpler, but fewer features. Available in Vercel Dashboard under "Monitoring".
