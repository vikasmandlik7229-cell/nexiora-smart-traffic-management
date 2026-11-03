import { useEffect, useState } from 'react'
import { fetchCollection } from '../api'

const POLL_MS = 2000

/** Polls a backend collection every 2s - replaces Firestore's onSnapshot
 * real-time listener (removed along with Firestore/Firebase; see
 * backend/db/sql_client.py and api/server.py's /api/collection endpoint).
 * `queryConstraints` is an array built with lib/query.js's limit()/orderBy()
 * - pass a `limit` constraint explicitly so polling stays cheap. */
export function useCollection(collectionName, queryConstraints = []) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const constraintsKey = JSON.stringify(queryConstraints)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    async function poll() {
      try {
        const docs = await fetchCollection(collectionName, queryConstraints)
        if (!cancelled) {
          setData(docs)
          setLoading(false)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err)
          setLoading(false)
        }
      }
    }

    poll()
    const id = setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionName, constraintsKey])

  return { data, loading, error }
}
