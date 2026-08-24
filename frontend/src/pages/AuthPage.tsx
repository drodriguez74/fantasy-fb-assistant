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
  // existing user just logging in again). Send them to the Draft Assistant
  // -- it works with zero connected leagues -- with a one-time welcome
  // banner instead of the generic marketing homepage.
  const handleRegisterAutoLogin = async (token: string) => {
    await login(token)
    navigate('/draft?welcome=1')
  }

  // Account was created but the auto-login call itself failed (rare --
  // e.g. a network blip between the two requests). Fall back to asking the
  // user to sign in manually rather than pretending they're logged in.
  const handleRegisteredWithoutLogin = () => {
    setShowSuccess(true)
    setIsLogin(true)
  }

  return (
    <div className="min-h-screen bg-ink-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <h1 className="text-center font-display font-black uppercase tracking-tight text-3xl text-ink-900 mb-8">
          Fantasy Football Assistant
        </h1>

        {showSuccess && (
          <div className="bg-success-50 border border-success-200 text-success-700 px-4 py-3 rounded mb-4">
            Account created successfully! Please sign in.
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