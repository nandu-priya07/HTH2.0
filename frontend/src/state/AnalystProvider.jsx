/**
 * Shared analyst session: conversations, active dataset, messages.
 *
 * This is the logic that previously lived inside ChatWorkspace.jsx, lifted
 * so every page (Upload, Ask AI, History, …) sees the same session.
 * API endpoints, methods and payloads are unchanged:
 *   GET    /api/conversations
 *   GET    /api/conversations/:id/messages
 *   PATCH  /api/conversations/:id
 *   DELETE /api/conversations/:id
 *   POST   /api/query
 *   POST   /api/upload
 *   GET    /api/dataset/:id
 *   GET    /api/dataset/:id/suggestions
 */
import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { AnalystContext } from './analystContext'
import { getDatasetStats } from '../lib/dataset'

const normalizeVis = (item) =>
  item?.visualization_type === 'decision_boundary' ? { ...item, visualization_type: 'line' } : item

// Helper to format backend messages into ChatMessage props
const formatApiMessage = (msg) => {
  const isAi = msg.role === 'assistant' || msg.role === 'system'
  const res = msg.result || {}
  const vis = msg.visualization

  return {
    id: msg.id,
    sender: isAi ? 'ai' : 'user',
    text: msg.content,
    result: msg.result,
    decision_analysis: res.decision_analysis,
    geo: res.geo,
    geo_result: res.result?.result || (res.analysis_type === 'geographic_analysis' ? res.result : null),
    geo_evidence: res.evidence,
    table: res.table || (res.tables && res.tables[0]),
    tables: res.tables,
    scalar: res.scalar || (res.scalars && res.scalars[0]),
    scalars: res.scalars,
    list: res.list,
    metadata: res.metadata,
    timing: res.timing || msg.timing,
    query_spec: msg.query_spec,
    intent: msg.intent,
    visualization: Array.isArray(vis) ? vis[0] : normalizeVis(vis),
    visualizations: Array.isArray(vis) ? vis.map(normalizeVis) : vis ? [normalizeVis(vis)] : [],
    created_at: msg.created_at
  }
}

export default function AnalystProvider({ children }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [activeDataset, setActiveDataset] = useState(null)
  const [suggestions, setSuggestions] = useState([])

  const [conversations, setConversations] = useState([])
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [isLoadingConversations, setIsLoadingConversations] = useState(true)
  const [conversationsError, setConversationsError] = useState(null)

  // Refs keep async flows (upload → follow-up query) from reading stale state.
  const conversationIdRef = useRef(null)
  const datasetRef = useRef(null)
  useEffect(() => { conversationIdRef.current = activeConversationId }, [activeConversationId])
  useEffect(() => { datasetRef.current = activeDataset }, [activeDataset])

  const loadSuggestions = useCallback(async (datasetId) => {
    if (!datasetId) return
    try {
      const res = await fetch(`/api/dataset/${datasetId}/suggestions`)
      if (res.ok) {
        const data = await res.json()
        if (data.suggestions && data.suggestions.length > 0) setSuggestions(data.suggestions)
      }
    } catch (err) {
      console.warn('Could not fetch suggestions:', err)
    }
  }, [])

  const requestConversations = async () => {
    const res = await fetch('/api/conversations')
    if (!res.ok) throw new Error(`Server returned status ${res.status}`)
    const data = await res.json()
    return Array.isArray(data) ? data : []
  }

  const fetchConversations = useCallback(async () => {
    setIsLoadingConversations(true)
    setConversationsError(null)
    try {
      setConversations(await requestConversations())
    } catch (err) {
      console.error('Failed to load conversations:', err)
      setConversationsError('Failed to load conversations')
    } finally {
      setIsLoadingConversations(false)
    }
  }, [])

  // The provider is keyed by account identity in App, so this initial request
  // always belongs to one session and never mixes two accounts' chat state.
  useEffect(() => {
    let cancelled = false
    requestConversations()
      .then((list) => { if (!cancelled) setConversations(list) })
      .catch(() => { if (!cancelled) setConversationsError('Failed to load conversations') })
      .finally(() => { if (!cancelled) setIsLoadingConversations(false) })
    return () => { cancelled = true }
  }, [])

  const loadDataset = useCallback(async (datasetId) => {
    try {
      const dsRes = await fetch(`/api/dataset/${datasetId}`)
      if (dsRes.ok) {
        const dsData = await dsRes.json()
        setActiveDataset(dsData)
        loadSuggestions(datasetId)
      }
    } catch (e) {
      console.warn('Could not load dataset info:', e)
    }
  }, [loadSuggestions])

  const selectConversation = useCallback(async (conversationId) => {
    if (conversationId === conversationIdRef.current && messages.length > 0) return

    setActiveConversationId(conversationId)
    setIsLoadingMessages(true)
    setUploadError(null)

    try {
      const res = await fetch(`/api/conversations/${conversationId}/messages`)
      if (!res.ok) throw new Error('Failed to load conversation messages')
      const data = await res.json()
      setMessages((Array.isArray(data) ? data : []).map(formatApiMessage))

      // Strictly resolve dataset from this conversation
      const convMeta = conversations.find((c) => c.id === conversationId)
      if (convMeta?.dataset_id) {
        if (convMeta.dataset_id !== datasetRef.current?.dataset_id) await loadDataset(convMeta.dataset_id)
      } else {
        setActiveDataset(null)
        setSuggestions([])
      }
    } catch (err) {
      console.error('Error loading conversation:', err)
      setMessages([{ sender: 'ai', error: 'Failed to load conversation history. Please try clicking the conversation again.', errorKind: 'connection' }])
    } finally {
      setIsLoadingMessages(false)
    }
  }, [conversations, messages.length, loadDataset])

  const newChat = useCallback(() => {
    setActiveConversationId(null)
    conversationIdRef.current = null
    setActiveDataset(null)
    setSuggestions([])
    setMessages([])
    setInput('')
    setUploadError(null)
  }, [])

  const renameConversation = useCallback(async (conversationId, newTitle) => {
    try {
      const res = await fetch(`/api/conversations/${conversationId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle })
      })
      if (res.ok) {
        const updated = await res.json()
        setConversations((prev) =>
          prev.map((c) => (c.id === conversationId ? { ...c, title: updated.title, updated_at: updated.updated_at } : c))
        )
      }
    } catch (err) {
      console.error('Failed to rename conversation:', err)
    }
  }, [])

  const deleteConversation = useCallback(async (conversationId) => {
    try {
      const res = await fetch(`/api/conversations/${conversationId}`, { method: 'DELETE' })
      if (res.ok) {
        setConversations((prev) => prev.filter((c) => c.id !== conversationId))
        if (conversationIdRef.current === conversationId) newChat()
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err)
    }
  }, [newChat])

  const sendMessage = useCallback(async (textToSend) => {
    const cleanText = (textToSend ?? '').trim()
    if (!cleanText) return

    setMessages((prev) => [...prev, { sender: 'user', text: cleanText }])
    setInput('')
    setIsLoading(true)
    setUploadError(null)

    try {
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: cleanText,
          dataset_id: datasetRef.current?.dataset_id || null,
          conversation_id: conversationIdRef.current || null
        })
      })

      const data = await response.json()

      if (!response.ok) {
        setMessages((prev) => [
          ...prev,
          { sender: 'ai', question: cleanText, errorKind: 'server', error: data.error || data.detail || 'Server returned an error processing your query.' }
        ])
        return
      }

      if (data.conversation_id) {
        setActiveConversationId(data.conversation_id)
        conversationIdRef.current = data.conversation_id
        fetchConversations()
      }

      if (data.dataset_id && (!datasetRef.current || datasetRef.current.dataset_id !== data.dataset_id)) {
        await loadDataset(data.dataset_id)
      }

      setMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          question: cleanText,
          text: data.text,
          status: data.status,
          result_type: data.result_type || data.type,
          decision_analysis: data.decision_analysis,
          geo: data.geo,
          geo_result: data.result,
          geo_evidence: data.evidence,
          scalar: data.scalar,
          table: data.table,
          options: data.options,
          intent: data.intent,
          query_spec: data.query_spec || data.query,
          visualization: normalizeVis(data.visualization),
          visualizations: data.visualizations?.map(normalizeVis),
          metadata: data.metadata,
          timing: data.timing,
          error: data.error
        }
      ])
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          question: cleanText,
          errorKind: 'connection',
          error: 'Failed to connect to backend analytics engine. Please ensure the backend server is running on port 8000.'
        }
      ])
    } finally {
      setIsLoading(false)
    }
  }, [fetchConversations, loadDataset])

  /**
   * Upload a dataset via POST /api/upload.
   * `freshSession` starts a new analysis (used by the Upload page);
   * otherwise the file attaches to the current conversation (chat composer).
   */
  const uploadDataset = useCallback(async (file, { text = '', freshSession = false } = {}) => {
    if (!file) return { ok: false }
    if (freshSession) {
      setActiveConversationId(null)
      conversationIdRef.current = null
      setMessages([])
      setSuggestions([])
    }
    setIsLoading(true)
    setUploadError(null)

    const formData = new FormData()
    formData.append('file', file)
    if (conversationIdRef.current) formData.append('conversation_id', conversationIdRef.current)

    try {
      const response = await fetch('/api/upload', { method: 'POST', body: formData })
      const data = await response.json()

      if (!response.ok || !data.success) {
        const message = data.error || 'Upload failed. Only CSV and Excel files are allowed.'
        setUploadError(message)
        return { ok: false, error: message }
      }

      setActiveDataset(data)
      datasetRef.current = data
      if (data.conversation_id) {
        setActiveConversationId(data.conversation_id)
        conversationIdRef.current = data.conversation_id
      }
      loadSuggestions(data.dataset_id)
      fetchConversations()

      const stats = getDatasetStats(data)
      setMessages((prev) => [
        ...prev,
        {
          sender: 'user',
          text: text || '',
          attachment: { filename: data.filename, file_size: data.file_size, dataset_id: data.dataset_id, file_type: data.file_type }
        },
        {
          sender: 'ai',
          kind: 'dataset_ready',
          text: `Ingested **${data.filename}** (${stats.rows?.toLocaleString?.() ?? '—'} rows, ${stats.columns ?? '—'} columns).\n\nThe schema has been inferred and indexed. Ask a question in plain language to begin.`
        }
      ])
      setInput('')
      return { ok: true, data }
    } catch {
      const message = 'Failed to connect to backend server. Make sure FastAPI is running on port 8000.'
      setUploadError(message)
      return { ok: false, error: message }
    } finally {
      setIsLoading(false)
    }
  }, [fetchConversations, loadSuggestions])

  const sendFile = useCallback(async (file, optionalText) => {
    const result = await uploadDataset(file, { text: optionalText })
    if (result.ok && optionalText && optionalText.trim()) {
      setTimeout(() => sendMessage(optionalText.trim()), 300)
    }
  }, [uploadDataset, sendMessage])

  const clearDataset = useCallback(() => {
    setActiveDataset(null)
    setSuggestions([])
    setMessages((prev) => [
      ...prev,
      { sender: 'ai', text: 'Active dataset disconnected. Upload a new CSV or Excel file to analyze a new dataset.' }
    ])
  }, [])

  const value = useMemo(() => ({
    messages, input, setInput, isLoading, isLoadingMessages,
    uploadError, setUploadError,
    activeDataset, suggestions,
    conversations, activeConversationId, isLoadingConversations, conversationsError,
    fetchConversations, selectConversation, newChat, renameConversation, deleteConversation,
    sendMessage, sendFile, uploadDataset, clearDataset
  }), [
    messages, input, isLoading, isLoadingMessages, uploadError, activeDataset, suggestions,
    conversations, activeConversationId, isLoadingConversations, conversationsError,
    fetchConversations, selectConversation, newChat, renameConversation, deleteConversation,
    sendMessage, sendFile, uploadDataset, clearDataset
  ])

  return <AnalystContext.Provider value={value}>{children}</AnalystContext.Provider>
}
