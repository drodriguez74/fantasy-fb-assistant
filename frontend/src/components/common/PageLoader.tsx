// Suspense fallback for lazy-loaded route pages (see App.tsx). Reuses the
// same spinner markup/tokens already used for full-page loading states
// elsewhere (e.g. ProtectedRoute, PlayersPage) rather than inventing a new one.
export function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500"></div>
    </div>
  )
}
