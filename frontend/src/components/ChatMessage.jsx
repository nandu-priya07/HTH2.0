export default function ChatMessage({ message }) {
  const { sender, text, table, attachment, isLoading } = message

  const formatFileSize = (bytes) => {
    if (!bytes) return ''
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
  }

  if (sender === 'user') {
    return (
      <div className="message-row user">
        <div className="message-bubble-wrapper">
          <div className="message-content">
            {/* Attachment preview inside user message */}
            {attachment && (
              <div className="user-message-attachment">
                <span className="attachment-icon">📎</span>
                <div>
                  <div style={{ fontWeight: 600 }}>{attachment.filename}</div>
                  {attachment.file_size && (
                    <div style={{ fontSize: '0.75rem', opacity: 0.8 }}>
                      {formatFileSize(attachment.file_size)}
                    </div>
                  )}
                </div>
              </div>
            )}
            {text && <div>{text}</div>}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="message-row ai">
      <div className="message-bubble-wrapper">
        <div className="ai-avatar-badge">AI</div>
        <div className="message-content">
          {isLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)' }}>
              <span style={{ animation: 'fadeIn 1s infinite alternate' }}>● ● ●</span>
              <span>Uploading file to server...</span>
            </div>
          ) : (
            <>
              {text && (
                <div style={{ marginBottom: table ? '12px' : '0' }}>
                  {text.split('\n').map((para, i) => (
                    <p key={i} style={{ marginBottom: '6px' }}>{para}</p>
                  ))}
                </div>
              )}

              {table && table.headers && table.rows && (
                <table className="mock-table">
                  <thead>
                    <tr>
                      {table.headers.map((h, i) => (
                        <th key={i}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {table.rows.map((row, rIdx) => (
                      <tr key={rIdx}>
                        {row.map((cell, cIdx) => (
                          <td key={cIdx}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
