import { useState } from 'react'
import { auth, getErrorMessage } from '../../services/api'

interface LoginRequest {
  username: string
  password: string
}

interface LoginFormProps {
  onSuccess: (token: string) => void
  onSwitchToRegister: () => void
}

export function LoginForm({ onSuccess, onSwitchToRegister }: LoginFormProps) {
  const [formData, setFormData] = useState<LoginRequest>({
    username: '',
    password: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const response = await auth.login(formData)
      const { access_token } = response.data
      localStorage.setItem('access_token', access_token)
      onSuccess(access_token)
    } catch (err) {
      setError(getErrorMessage(err, 'Login failed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto bg-white rounded-lg shadow-sm border border-ink-200 p-6">
      <h2 className="text-2xl font-bold text-center text-ink-900 mb-6">Sign In</h2>

      {error && (
        <div className="bg-danger-50 border border-danger-200 text-danger-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="username" className="block text-sm font-medium text-ink-700 mb-1">
            Username or Email
          </label>
          <input
            type="text"
            id="username"
            value={formData.username}
            onChange={(e) => setFormData({ ...formData, username: e.target.value })}
            className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
            required
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-ink-700 mb-1">
            Password
          </label>
          <input
            type="password"
            id="password"
            value={formData.password}
            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
            required
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-accent-500 text-white py-2 px-4 rounded-md hover:bg-accent-600 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>

      <div className="mt-6 text-center">
        <p className="text-sm text-ink-600">
          Don't have an account?{' '}
          <button
            onClick={onSwitchToRegister}
            className="text-accent-600 hover:text-accent-800 font-medium"
          >
            Sign up
          </button>
        </p>
      </div>

      <div className="mt-4 text-center">
        <p className="text-xs text-ink-500">
          Demo account:<br />
          demo@test.com / Password123
        </p>
      </div>
    </div>
  )
}