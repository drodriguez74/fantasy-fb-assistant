import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LoginForm } from '../components/auth/LoginForm'
import { RegisterForm } from '../components/auth/RegisterForm'
import { useAuth } from '../hooks/useAuth'

export function AuthPage() {
  const [isLogin, setIsLogin] = useState(true)
  const [showSuccess, setShowSuccess] = useState(false)
  const navigate = useNavigate()
  const { login } = useAuth()

  const handleLoginSuccess = async (token: string) => {
    await login(token)
    navigate('/')
  }

  // Fresh registration + immediate auto-login: this is the one reliable
  // signal we have for "genuinely new user, right now" (as opposed to an
  // existing user just logging in again). Send them to the Leagues page to
  // connect a platform -- the first real step for a new user -- with a
  // one-time welcome banner instead of the generic marketing homepage.
  const handleRegisterAutoLogin = async (token: string) => {
    await login(token)
    navigate('/leagues?welcome=1')
  }

  // Account was created but the auto-login call itself failed (rare --
  // e.g. a network blip between the two requests). Fall back to asking the
  // user to sign in manually rather than pretending they're logged in.
  const handleRegisteredWithoutLogin = () => {
    setShowSuccess(true)
    setIsLogin(true)
  }

  return (
    <div className="min-h-screen bg-page flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="text-center mb-8">
          <span className="inline-flex h-8 w-8 items-center justify-center bg-volt font-display text-lg font-bold text-volt-ink">FF</span>
          <h1 className="mt-3 font-display font-bold uppercase tracking-tight text-3xl text-body">
            FF Assistant
          </h1>
          <p className="mt-2 font-stat text-xs text-faint">Sign in to grade your roster and set your lineup.</p>
        </div>

        {showSuccess && (
          <div className="bg-success-50 border border-success-100 text-success-700 px-4 py-3 rounded mb-4 text-sm">
            Account created. Sign in below.
          </div>
        )}
        
        {isLogin ? (
          <LoginForm
            onSuccess={handleLoginSuccess}
            onSwitchToRegister={() => {
              setIsLogin(false)
              setShowSuccess(false)
            }}
          />
        ) : (
          <RegisterForm
            onAutoLoginSuccess={handleRegisterAutoLogin}
            onRegisteredWithoutLogin={handleRegisteredWithoutLogin}
            onSwitchToLogin={() => setIsLogin(true)}
          />
        )}
      </div>
    </div>
  )
}