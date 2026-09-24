import { useEffect } from 'react'
import AnalystProvider from './state/AnalystProvider'
import AppShell from './components/layout/AppShell'
import { usePath } from './lib/router'
import HomePage from './pages/HomePage'
import UploadPage from './pages/UploadPage'
import AskAIPage from './pages/AskAIPage'
import InsightsPage from './pages/InsightsPage'
import ExplorerPage from './pages/ExplorerPage'
import ScenariosPage from './pages/ScenariosPage'
import DecisionsPage from './pages/DecisionsPage'
import HistoryPage from './pages/HistoryPage'
import NotFoundPage from './pages/NotFoundPage'

const ROUTES = {
  '/': { page: HomePage, title: 'Home' },
  '/home': { page: HomePage, title: 'Home' },
  '/upload': { page: UploadPage, title: 'Upload Dataset' },
  '/ask-ai': { page: AskAIPage, title: 'Ask AI', fullBleed: true },
  '/insights': { page: InsightsPage, title: 'Insights' },
  '/explorer': { page: ExplorerPage, title: 'Explorer' },
  '/scenarios': { page: ScenariosPage, title: 'Scenarios' },
  '/decisions': { page: DecisionsPage, title: 'Decisions' },
  '/history': { page: HistoryPage, title: 'History' }
}

function App() {
  const path = usePath()
  const route = ROUTES[path] || { page: NotFoundPage, title: 'Not found' }
  const Page = route.page

  useEffect(() => {
    document.title = `${route.title} · QueryLens — Natural Language Data Analyst`
  }, [route.title])

  return (
    <AnalystProvider>
      <AppShell fullBleed={route.fullBleed}>
        <Page key={path} />
      </AppShell>
    </AnalystProvider>
  )
}

export default App
