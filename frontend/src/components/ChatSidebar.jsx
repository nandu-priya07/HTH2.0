import { useState } from 'react'

export default function ChatSidebar({ onNewChat }) {
  const [selectedChatId, setSelectedChatId] = useState(null)

  // Static mock recent chats grouped by timeframe
  const recentChatGroups = [
    {
      group: 'Today',
      items: [
        { id: 1, title: 'Sales performance analysis' },
        { id: 2, title: 'Top revenue products' },
        { id: 3, title: 'Regional sales comparison' }
      ]
    },
    {
      group: 'Yesterday',
      items: [
        { id: 4, title: 'Monthly sales trend' },
        { id: 5, title: 'Customer segment analysis' },
        { id: 6, title: 'Profit margin analysis' }
      ]
    },
    {
      group: 'Older',
      items: [
        { id: 7, title: 'Dataset summary' },
        { id: 8, title: 'Discount analysis' }
      ]
    }
  ]

  const handleSelectChat = (id) => {
    setSelectedChatId(id)
  }

  return (
    <aside className="chat-sidebar">
      {/* Sidebar Header Branding */}
      <div className="sidebar-header">
        <div className="sidebar-logo">H</div>
        <div>
          <div className="sidebar-title">HTH2.0</div>
          <div className="sidebar-subtitle">AI Data Analyst</div>
        </div>
      </div>

      {/* Prominent New Chat Button */}
      <button className="new-chat-btn" onClick={onNewChat}>
        <span style={{ fontSize: '1.1rem', fontWeight: 400 }}>+</span>
        <span>New Chat</span>
      </button>

      {/* Static Mock Recent Chats History */}
      <div className="sidebar-history-section">
        {recentChatGroups.map((group, gIdx) => (
          <div key={gIdx}>
            <div className="history-group-title">{group.group}</div>
            <div className="history-list">
              {group.items.map((item) => (
                <button
                  key={item.id}
                  className={`history-item ${selectedChatId === item.id ? 'active' : ''}`}
                  onClick={() => handleSelectChat(item.id)}
                  title={item.title}
                >
                  <span className="history-icon">💬</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.title}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Sidebar Footer Placeholders */}
      <div className="sidebar-footer">
        <button className="sidebar-footer-btn" onClick={() => alert('Settings coming soon')}>
          <span>⚙️</span>
          <span>Settings</span>
        </button>
        <button className="sidebar-footer-btn" onClick={() => alert('Help & Support coming soon')}>
          <span>❓</span>
          <span>Help</span>
        </button>
      </div>
    </aside>
  )
}
