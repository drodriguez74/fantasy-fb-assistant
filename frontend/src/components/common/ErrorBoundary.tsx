import { Component, ErrorInfo, ReactNode } from 'react'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
}

// React error boundaries must be class components -- there is no hooks-based
// equivalent (getDerivedStateFromError / componentDidCatch have no hook
// counterpart). This catches render-time errors anywhere in the wrapped
// subtree and shows a calm, generic recovery UI instead of a blank screen.
// The real error is logged for developers, but never rendered to the user.
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Unhandled error caught by ErrorBoundary:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen px-4">
          <div className="max-w-md w-full bg-red-50 border border-red-200 rounded-md p-6 text-center">
            <ExclamationTriangleIcon className="h-10 w-10 text-red-400 mx-auto" />
            <h1 className="mt-4 text-lg font-medium text-red-800">Something went wrong</h1>
            <p className="mt-2 text-sm text-red-700">
              We hit an unexpected problem loading this page. You can try again, or head back to
              the home page.
            </p>
            <div className="mt-6 flex items-center justify-center space-x-3">
              <button
                onClick={this.handleReset}
                className="bg-volt text-volt-ink px-4 py-2 rounded-lg hover:bg-volt-dark"
              >
                Try again
              </button>
              <a
                href="/"
                className="text-sm font-medium text-muted hover:text-body"
              >
                Back to Home
              </a>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
