// Tiny query-constraint builders, replacing `import { limit, orderBy } from
// 'firebase/firestore'` - same names/shape so every page that used them
// only needs its import line changed, not its query logic. The only
// ordering ever used anywhere in this app is orderBy('timestamp', 'desc'),
// so that's the only field the backend's /api/collection endpoint supports.
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function limit(n) {
  return { type: 'limit', n }
}

export function orderBy(field, dir = 'asc') {
  return { type: 'orderBy', field, dir }
}

/** Turns a constraints array into backend query-string params. */
export function constraintsToParams(constraints = []) {
  const params = new URLSearchParams()
  for (const c of constraints) {
    if (c.type === 'limit') params.set('limit', String(c.n))
    else if (c.type === 'orderBy') {
      params.set('order_by', c.field)
      params.set('dir', c.dir)
    }
  }
  return params
}
