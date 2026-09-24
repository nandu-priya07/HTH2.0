import { useState, useRef, useEffect } from 'react'
import ChatSidebar from './ChatSidebar'
import ChatMessage from './ChatMessage'
import SuggestedQuestions from './SuggestedQuestions'
import ChatInput from './ChatInput'

export default function ChatWorkspace() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [activeDataset, setActiveDataset] = useState(null)
  const scrollEndRef = useRef(null)

  // Auto-scroll chat view when messages change
  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const generateMockAIResponse = (userQuery) => {
    const q = userQuery.toLowerCase()

    if (q.includes('top') || q.includes('product') || q.includes('revenue')) {
      return {
        sender: 'ai',
        text: 'Based on your dataset, here are the top 5 products by total revenue:',
        table: {
          headers: ['Product Name', 'Category', 'Units Sold', 'Revenue (INR)'],
          rows: [
            ['Pro Laptop 15"', 'Electronics', '120', '₹12,40,000'],
            ['Flagship Phone 5G', 'Smartphones', '215', '₹10,80,000'],
            ['Pro Tablet 11"', 'Electronics', '140', '₹9,70,000'],
            ['4K Ultra Monitor', 'Electronics', '95', '₹8,90,000'],
            ['Noise-Canceling Pods', 'Audio', '300', '₹8,20,000']
          ]
        }
      }
    } else if (q.includes('trend') || q.includes('month')) {
      return {
        sender: 'ai',
        text: 'Here is the monthly revenue performance trend from your dataset:',
        table: {
          headers: ['Month', 'Orders', 'Revenue (INR)', 'Growth'],
          rows: [
            ['January', '840', '₹9,20,000', 'Baseline'],
            ['February', '910', '₹10,50,000', '+14.1%'],
            ['March', '1,120', '₹12,80,000', '+21.9%'],
            ['April', '1,280', '₹15,10,000', '+17.9%'],
            ['May', '1,390', '₹16,40,000', '+8.6%'],
            ['June', '1,540', '₹18,40,000', '+12.1%']
          ]
        }
      }
    } else if (q.includes('region') || q.includes('geography')) {
      return {
        sender: 'ai',
        text: 'Regional breakdown of total sales:',
        table: {
          headers: ['Region', 'Order Count', 'Total Sales (INR)', 'Share'],
          rows: [
            ['North Region', '3,840', '₹32,50,000', '38.4%'],
            ['West Region', '2,650', '₹24,80,000', '29.3%'],
            ['South Region', '2,100', '₹16,40,000', '19.4%'],
            ['East Region', '1,410', '₹10,90,000', '12.9%']
          ]
        }
      }
    } else {
      return {
        sender: 'ai',
        text: `Here is the analysis based on your question "${userQuery}":\n\nThe dataset shows clean metrics across all categories. You can ask for specific product rankings, revenue trends, regional share, or summary stats.`
      }
    }
  }

  const handleSendMessage = (textToSend) => {
    if (!textToSend.trim() || isLoading) return

    const userMessage = { sender: 'user', text: textToSend.trim() }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    // Simulate AI loading delay
    setTimeout(() => {
      const mockResponse = generateMockAIResponse(textToSend)
      setMessages((prev) => [...prev, mockResponse])
      setIsLoading(false)
    }, 750)
  }

  // Handle real backend file upload flow (POST /api/upload)
  const handleSendFile = async (file, optionalText) => {
    if (!file || isLoading) return

    setIsLoading(true)
    setUploadError(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()

      if (!response.ok || !data.success) {
        setUploadError(data.error || 'Upload failed. Only CSV and Excel files are allowed.')
        setIsLoading(false)
        return
      }

      // Add user message with attachment details
      const userMsg = {
        sender: 'user',
        text: optionalText || '',
        attachment: {
          filename: data.filename,
          file_size: data.file_size,
          dataset_id: data.dataset_id,
          file_type: data.file_type
        }
      }

      // Add assistant response
      const aiMsg = {
        sender: 'ai',
        text: 'File uploaded successfully.'
      }

      setActiveDataset(data)
      setMessages((prev) => [...prev, userMsg, aiMsg])
      setInput('')
    } catch (err) {
      setUploadError('Failed to connect to backend server. Make sure backend is running.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleNewChat = () => {
    setMessages([])
    setInput('')
    setUploadError(null)
    setActiveDataset(null)
  }

  const handleSelectSuggestion = (suggestionText) => {
    setInput(suggestionText)
  }

  return (
    <div className="chat-workspace-container">
      {/* 1. LEFT SIDEBAR */}
      <ChatSidebar onNewChat={handleNewChat} />

      {/* 2. MIDDLE CHAT AREA */}
      <main className="chat-main-area">
        <div className="chat-scroll-container">
          {messages.length === 0 ? (
            <SuggestedQuestions onSelectSuggestion={handleSelectSuggestion} />
          ) : (
            messages.map((msg, index) => (
              <ChatMessage key={index} message={msg} />
            ))
          )}

          {isLoading && (
            <ChatMessage
              message={{
                sender: 'ai',
                isLoading: true
              }}
            />
          )}

          <div ref={scrollEndRef} />
        </div>

        {/* 3. BOTTOM CHAT INPUT */}
        <ChatInput
          input={input}
          setInput={setInput}
          onSendMessage={handleSendMessage}
          onSendFile={handleSendFile}
          isLoading={isLoading}
          uploadError={uploadError}
          setUploadError={setUploadError}
        />
      </main>
    </div>
  )
}
