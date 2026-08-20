import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './hooks/useAuth'
import { Navbar } from './components/common/Navbar'
import { ProtectedRoute } from './components/common/ProtectedRoute'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { HomePage } from './pages/HomePage'
import { AuthPage } from './pages/AuthPage'
import { DraftPage } from './pages/DraftPage'
import { PlayersPage } from './pages/PlayersPage'
import { BlogPage } from './pages/BlogPage'
import { BlogPostPage } from './pages/BlogPostPage'
import { LeaguesPage } from './pages/LeaguesPage'
import { LeagueDetailPage } from './pages/LeagueDetailPage'
import { YahooCallbackPage } from './pages/YahooCallbackPage'
import { LiveDraftPage } from './pages/LiveDraftPage'
import { ContentPage } from './pages/ContentPage'
import { HistoricalPage } from './pages/HistoricalPage'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { WaiverWirePage } from './pages/WaiverWirePage'
import { AdvancedAnalysisPage } from './pages/AdvancedAnalysisPage'
import { PostDraftAnalysisPage } from './pages/PostDraftAnalysisPage'
import { TradeAnalyzerPage } from './pages/TradeAnalyzerPage'

function App() {
  return (
    <AuthProvider>
      <Router>
        <ErrorBoundary>
        <div className="min-h-screen bg-ink-50">
          <Navbar />
          <main className="container mx-auto px-4 py-8">
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/auth" element={<AuthPage />} />
              <Route path="/players" element={<PlayersPage />} />
              <Route path="/blog" element={<BlogPage />} />
              <Route path="/blog/:id" element={<BlogPostPage />} />
              <Route path="/yahoo/callback" element={<YahooCallbackPage />} />
              <Route 
                path="/draft" 
                element={
                  <ProtectedRoute>
                    <DraftPage />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/leagues" 
                element={
                  <ProtectedRoute>
                    <LeaguesPage />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/leagues/:leagueId" 
                element={
                  <ProtectedRoute>
                    <LeagueDetailPage />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/live-draft" 
                element={
                  <ProtectedRoute>
                    <LiveDraftPage />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/content" 
                element={
                  <ProtectedRoute>
                    <ContentPage />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/historical" 
                element={
                  <ProtectedRoute>
                    <HistoricalPage />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/analytics" 
                element={
                  <ProtectedRoute>
                    <AnalyticsPage />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/waiver-wire" 
                element={
                  <ProtectedRoute>
                    <WaiverWirePage />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/advanced-analysis" 
                element={
                  <ProtectedRoute>
                    <AdvancedAnalysisPage />
                  </ProtectedRoute>
                } 
              />
              <Route
                path="/post-draft"
                element={
                  <ProtectedRoute>
                    <PostDraftAnalysisPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/trade-analyzer"
                element={
                  <ProtectedRoute>
                    <TradeAnalyzerPage />
                  </ProtectedRoute>
                }
              />
            </Routes>
          </main>
        </div>
        </ErrorBoundary>
      </Router>
    </AuthProvider>
  )
}

export default App
