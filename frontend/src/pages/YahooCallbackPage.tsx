import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

export function YahooCallbackPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const authorizationCode = searchParams.get('code')
    const error = searchParams.get('error')
    const errorDescription = searchParams.get('error_description')

    if (error) {
      setStatus('error')
      setMessage(`Yahoo authentication failed: ${error}${errorDescription ? ` (${errorDescription})` : ''}`)
      
      // Send error message to parent window
      if (window.opener) {
        // targetOrigin must be the OPENER's origin, not this popup's own
        // (window.location.origin here would be the tunnel domain Yahoo
        // redirected through, e.g. an ngrok host -- not localhost:3001,
        // where the opener actually lives). A mismatched targetOrigin
        // makes the browser silently drop the message with no error, which
        // looked like "the popup just closes and nothing happens" -- the
        // OAuth code was arriving, it just never reached the opener.
        window.opener.postMessage({
          type: 'YAHOO_AUTH_ERROR',
          error: error,
          error_description: errorDescription
        }, '*')
        window.close()
      } else {
        // If no parent window, redirect after a delay
        setTimeout(() => navigate('/leagues'), 3000)
      }
      return
    }

    if (authorizationCode) {
      setStatus('success')
      setMessage('Authenticated with Yahoo. Importing your leagues…')
      
      // Send success message to parent window with authorization code
      if (window.opener) {
        window.opener.postMessage({
          type: 'YAHOO_AUTH_SUCCESS',
          code: authorizationCode
        }, '*')
        window.close()
      } else {
        // If no parent window, redirect after a delay
        setTimeout(() => navigate('/leagues'), 2000)
      }
    } else {
      setStatus('error')
      setMessage('No authorization code came back from Yahoo.')
      
      if (window.opener) {
        window.opener.postMessage({
          type: 'YAHOO_AUTH_ERROR',
          error: 'No authorization code'
        }, '*')
        window.close()
      } else {
        setTimeout(() => navigate('/leagues'), 3000)
      }
    }
  }, [searchParams, navigate])

  return (
    <div className="min-h-screen flex items-center justify-center bg-page px-4">
      <div className="max-w-md w-full bg-surface border border-line p-8 text-center">
        <div className="mb-5 flex justify-center">
          {status === 'processing' && (
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent-ink"></div>
          )}
          {status === 'success' && (
            <div className="w-10 h-10 bg-volt text-volt-ink flex items-center justify-center">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          )}
          {status === 'error' && (
            <div className="w-10 h-10 bg-danger-100 text-danger-700 flex items-center justify-center">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
          )}
        </div>

        <h2 className="font-display text-xl font-bold uppercase tracking-tight text-body">
          {status === 'processing' && 'Talking to Yahoo…'}
          {status === 'success' && 'Connected'}
          {status === 'error' && 'Connection failed'}
        </h2>

        <p className="mt-2 text-sm text-muted">{message}</p>

        {status !== 'error' ? (
          <p className="mt-4 font-stat text-xs text-faint">This window closes on its own.</p>
        ) : (
          <button
            onClick={() => { window.close(); navigate('/leagues'); }}
            className="mt-5 bg-surface-2 border border-line px-4 py-2 font-stat text-xs text-body hover:border-accent-ink transition-colors"
          >
            Close window
          </button>
        )}
      </div>
    </div>
  )
}