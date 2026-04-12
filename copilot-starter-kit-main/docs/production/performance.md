# Performance Monitoring

## Lighthouse Check (after every deployment)

1. Open Chrome DevTools (F12)
2. Go to Lighthouse tab
3. Select: Performance, Accessibility, Best Practices, SEO
4. Generate Report for both Mobile and Desktop
5. **Target: Score > 90** in all categories

## Common Performance Issues

### Unoptimized Images
```tsx
// Bad - unoptimized, no lazy loading
<img src="/large-image.jpg" />

// Good - Next.js Image component
import Image from 'next/image'
<Image src="/large-image.jpg" width={800} height={600} alt="Description" />
```
Next.js Image automatically: resizes, lazy-loads, serves WebP format.

### Large JavaScript Bundle
Use dynamic imports for heavy components that aren't needed on initial load:
```tsx
import dynamic from 'next/dynamic'

const HeavyChart = dynamic(() => import('./HeavyChart'), {
  loading: () => <p>Loading chart...</p>,
})
```

### Missing Loading States
Always show feedback during data fetching:
```tsx
// Use shadcn Skeleton component
import { Skeleton } from "@/components/ui/skeleton"

if (isLoading) return <Skeleton className="h-12 w-full" />
```

### No Caching Strategy
Cache slow database queries with `unstable_cache`:
```typescript
import { unstable_cache } from 'next/cache'

export const getStats = unstable_cache(
  async () => {
    const { data } = await supabase.from('stats').select('*')
    return data
  },
  ['dashboard-stats'],
  { revalidate: 3600 } // Refresh every hour
)
```

## Quick Wins Checklist
- [ ] All images use `next/image` component
- [ ] Heavy components use dynamic imports
- [ ] Loading states show skeleton/spinner
- [ ] Fonts loaded with `next/font`
- [ ] No unnecessary client-side JavaScript (`"use client"` only when needed)

## Automated Monitoring
- **Vercel Analytics** - Automatic on Pro plan, shows Core Web Vitals
- **Vercel Speed Insights** - Real user performance data
