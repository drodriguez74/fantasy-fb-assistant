import { lazy, Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './hooks/useAuth'
import { Navbar } from './components/common/Navbar'
import { ProtectedRoute } from './components/common/ProtectedRoute'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { PageLoader } from './components/common/PageLoader'

// Route-level code splitting: each page becomes its own chunk that's only
// downloaded when a user actually navigates to it, instead of all pages
// (plus their dependencies, e.g. recharts/d3 pulled in only by
// AdvancedAnalysisPage) being bundled into one ~1MB chunk loaded upfront.
const HomePage = lazy(() => import('./pages/HomePage').then(m => ({ default: m.HomePage })))
const AuthPage = lazy(() => import('./pages/AuthPage').then(m => ({ default: m.AuthPage })))
const PlayersPage = lazy(() => import('./pages/PlayersPage').then(m => ({ default: m.PlayersPage })))
const PlayerDetailPage = lazy(() => import('./pages/PlayerDetailPage').then(m => ({ default: m.PlayerDetailPage })))
const BlogPage = lazy(() => import('./pages/BlogPage').then(m => ({ default: m.BlogPage })))
const BlogPostPage = lazy(() => import('./pages/BlogPostPage').then(m => ({ default: m.BlogPostPage })))
const LeaguesPage = lazy(() => import('./pages/LeaguesPage').then(m => ({ default: m.LeaguesPage })))
const LeagueDetailPage = lazy(() => import('./pages/LeagueDetailPage').then(m => ({ default: m.LeagueDetailPage })))
const YahooCallbackPage = lazy(() => import('./pages/YahooCallbackPage').then(m => ({ default: m.YahooCallbackPage })))
const ContentPage = lazy(() => import('./pages/ContentPage').then(m => ({ default: m.ContentPage })))
const HistoricalPage = lazy(() => import('./pages/HistoricalPage').then(m => ({ default: m.HistoricalPage })))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage').then(m => ({ default: m.AnalyticsPage })))
const WaiverWirePage = lazy(() => import('./pages/WaiverWirePage').then(m => ({ default: m.WaiverWirePage })))
const AdvancedAnalysisPage = lazy(() => import('./pages/AdvancedAnalysisPage').then(m => ({ default: m.AdvancedAnalysisPage })))
const PostDraftAnalysisPage = lazy(() => import('./pages/PostDraftAnalysisPage').then(m => ({ default: m.PostDraftAnalysisPage })))
const TradeAnalyzerPage = lazy(() => import('./pages/TradeAnalyzerPage').then(m => ({ default: m.TradeAnalyzerPage })))
const DraftHistoryPage = lazy(() => import('./pages/DraftHistoryPage').then(m => ({ default: m.DraftHistoryPage })))
const ReportsPage = lazy(() => import('./pages/ReportsPage').then(m => ({ default: m.ReportsPage })))
const ThisWeekRedirectPage = lazy(() => import('./pages/ThisWeekRedirectPage').then(m => ({ default: m.ThisWeekRedirectPage })))

function App() {
  return (
    <AuthProvider>
      <Router>
        <ErrorBoundary>
        <div className="min-h-screen bg-page text-body">
          <Navbar />
          <main className="container mx-auto px-4 py-8">
            <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/auth" element={<AuthPage />} />
              <Route path="/players" element={<PlayersPage />} />
              <Route path="/players/:playerId" element={<PlayerDetailPage />} />
              <Route path="/blog" element={<BlogPage />} />
              <Route path="/blog/:id" element={<BlogPostPage />} />
              <Route path="/yahoo/callback" element={<YahooCallbackPage />} />
              <Route path="/draft" element={<Navigate to="/leagues" replace />} />
              <Route path="/live-draft" element={<Navigate to="/leagues" replace />} />
              <Route
                path="/this-week"
                element={
                  <ProtectedRoute>
                    <ThisWeekRedirectPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/reports"
                element={
                  <ProtectedRoute>
                    <ReportsPage />
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
              <Route
                path="/draft-history"
                element={
                  <ProtectedRoute>
                    <DraftHistoryPage />
                  </ProtectedRoute>
                }
              />
            </Routes>
            </Suspense>
          </main>
        </div>
        </ErrorBoundary>
      </Router>
    </AuthProvider>
  )
}

export default App
