import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/variables.css'
import './styles/global.css'
import './styles/shell.css'
import './styles/home.css'
import './styles/dataset.css'
import './styles/analytics.css'
import './styles/chat.css'
import './styles/visualization.css'
import './styles/pages.css'
import App from './App.jsx'
import AuthProvider from './state/AuthProvider.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)
