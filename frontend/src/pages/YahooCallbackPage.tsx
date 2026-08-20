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

    if (error) {
      setStatus('error')
      setMessage('Yahoo authentication was cancelled or failed')
      
      // Send error message to parent window
      if (window.opener) {
        window.opener.postMessage({
          type: 'YAHOO_AUTH_ERROR',
          error: error
        }, window.location.origin)
        window.close()
      } else {
        // If no parent window, redirect after a delay
        setTimeout(() => navigate('/leagues'), 3000)
      }
      return
    }

    if (authorizationCode) {
      setStatus('success')
      setMessage('Successfully authenticated with Yahoo! Importing your leagues...')
      
      // Send success message to parent window with authorization code
      if (window.opener) {
        window.opener.postMessage({
          type: 'YAHOO_AUTH_SUCCESS',
          code: authorizationCode
        }, window.location.origin)
        window.close()
      } else {
        // If no parent window, redirect after a delay
        setTimeout(() => navigate('/leagues'), 2000)
      }
    } else {
      setStatus('error')
      setMessage('No authorization code received from Yahoo')
      
      if (window.opener) {
        window.opener.postMessage({
          type: 'YAHOO_AUTH_ERROR',
          error: 'No authorization code'
        }, window.location.origin)
        window.close()
      } else {
        setTimeout(() => navigate('/leagues'), 3000)
      }
    }
  }, [searchParams, navigate])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full bg-white rounded-lg shadow-md p-6 text-center">
        <div className="mb-4">
          {status === 'processing' && (
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
          )}
          {status === 'success' && (
            <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mx-auto">
              <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          )}
          {status === 'error' && (
            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto">
              <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
          )}
        </div>

        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          {status === 'processing' && 'Processing Yahoo Authentication...'}
          {status === 'success' && 'Authentication Successful!'}
          {status === 'error' && 'Authentication Failed'}
        </h2>

        <p className="text-gray-600 mb-4">{message}</p>

        {status === 'processing' && (
          <p className="text-sm text-gray-500">
            Please wait while we process your Yahoo authentication...
          </p>
        )}

        {status === 'success' && (
          <p className="text-sm text-gray-500">
            This window will close automatically. Your leagues are being imported.
          </p>
        )}

        {status === 'error' && (
          <div>
            <p className="text-sm text-gray-500 mb-4">
              This window will close automatically, or you can close it manually.
            </p>
            <button
              onClick={() => { window.close(); navigate('/leagues'); }}
              className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
            >
              Close Window
            </button>
          </div>
        )}
      </div>
    </div>
  )
}