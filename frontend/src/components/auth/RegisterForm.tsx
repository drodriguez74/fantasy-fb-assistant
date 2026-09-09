import { useState } from 'react'
import { auth, getErrorMessage } from '../../services/api'
import type { RegisterRequest } from '../../types'

interface RegisterFormProps {
  // Called once the account exists AND we were able to sign the user
  // straight in with the credentials they just typed -- this is the
  // reliable "just registered" moment onboarding hangs off of.
  onAutoLoginSuccess: (token: string) => void
  // Called when the account was created but the immediate follow-up login
  // call failed for some reason (network blip, etc). Falls back to the
  // previous "please sign in manually" flow rather than losing the account
  // creation or pretending the user is signed in when they aren't.
  onRegisteredWithoutLogin: () => void
  onSwitchToLogin: () => void
}

export function RegisterForm({ onAutoLoginSuccess, onRegisteredWithoutLogin, onSwitchToLogin }: RegisterFormProps) {
  const [formData, setFormData] = useState<RegisterRequest>({
    email: '',
    username: '',
    password: '',
    full_name: '',
  })
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    if (formData.password !== confirmPassword) {
      setError('Passwords do not match')
      setLoading(false)
      return
    }

    try {
      await auth.register(formData)
    } catch (err) {
      setError(getErrorMessage(err, 'Registration failed'))
      setLoading(false)
      return
    }

    // Registration succeeded. Sign the user straight in with the same
    // credentials so we can carry them into a real first moment of value
    // instead of dumping them back on a login form for an account they
    // just created. If this specific call fails, the account still
    // exists -- fall back to the old "please sign in" flow rather than
    // losing that or faking a signed-in state.
    try {
      const loginResponse = await auth.login({ username: formData.email, password: formData.password })
      onAutoLoginSuccess(loginResponse.data.access_token)
    } catch (err) {
      console.error('Auto-login after registration failed:', err)
      onRegisteredWithoutLogin()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto bg-surface rounded-lg border border-hairline p-6">
      <h2 className="text-2xl font-bold text-center text-body mb-6">Sign Up</h2>

      {error && (
        <div className="bg-danger-50 border border-danger-200 text-danger-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="full_name" className="block text-sm font-medium text-body mb-1">
            Full Name
          </label>
          <input
            type="text"
            id="full_name"
            value={formData.full_name}
            onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
            className="w-full px-3 py-2 border border-line rounded-md focus:outline-none focus:ring-2 focus:ring-volt"
            required
          />
        </div>

        <div>
          <label htmlFor="username" className="block text-sm font-medium text-body mb-1">
            Username
          </label>
          <input
            type="text"
            id="username"
            value={formData.username}
            onChange={(e) => setFormData({ ...formData, username: e.target.value })}
            className="w-full px-3 py-2 border border-line rounded-md focus:outline-none focus:ring-2 focus:ring-volt"
            required
          />
        </div>

        <div>
          <label htmlFor="email" className="block text-sm font-medium text-body mb-1">
            Email
          </label>
          <input
            type="email"
            id="email"
            value={formData.email}
            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            className="w-full px-3 py-2 border border-line rounded-md focus:outline-none focus:ring-2 focus:ring-volt"
            required
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-body mb-1">
            Password
          </label>
          <input
            type="password"
            id="password"
            value={formData.password}
            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            className="w-full px-3 py-2 border border-line rounded-md focus:outline-none focus:ring-2 focus:ring-volt"
            required
          />
        </div>

        <div>
          <label htmlFor="confirmPassword" className="block text-sm font-medium text-body mb-1">
            Confirm Password
          </label>
          <input
            type="password"
            id="confirmPassword"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full px-3 py-2 border border-line rounded-md focus:outline-none focus:ring-2 focus:ring-volt"
            required
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-volt text-volt-ink py-2 px-4 rounded-md hover:bg-volt-dark transition-colors focus:outline-none focus:ring-2 focus:ring-volt disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Creating account...' : 'Sign Up'}
        </button>
      </form>

      <div className="mt-6 text-center">
        <p className="text-sm text-muted">
          Already have an account?{' '}
          <button
            onClick={onSwitchToLogin}
            className="text-accent-ink hover:text-accent-ink font-medium"
          >
            Sign in
          </button>
        </p>
      </div>
    </div>
  )
}