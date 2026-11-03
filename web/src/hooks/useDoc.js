import { useEffect, useState } from 'react'
import { fetchDoc } from '../api'

const POLL_MS = 2000

/** Polls a single backend document every 2s - replaces Firestore's
 * onSnapshot real-time listener (see hooks/useCollection.js's comment). */
export function useDoc(collectionName, docId) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!docId) {
      setData(null)
      setLoading(false)
      return undefined
    }
    let cancelled = false
    setLoading(true)

    async function poll() {
      try {
        const doc = await fetchDoc(collectionName, docId)
        if (!cancelled) {
          setData(doc)
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
  }, [collectionName, docId])

  return { data, loading, error }
}
