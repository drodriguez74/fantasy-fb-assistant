import { Link, useLocation } from 'react-router-dom'
import clsx from 'clsx'
import { useAuth } from '../../hooks/useAuth'
import { UserIcon, ArrowRightOnRectangleIcon } from '@heroicons/react/24/outline'

const navigation = [
  { name: 'Home', href: '/' },
  { name: 'Draft Assistant', href: '/draft' },
  { name: 'Post-Draft Analysis', href: '/post-draft' },
  { name: 'Live Draft', href: '/live-draft' },
  { name: 'Players', href: '/players' },
  { name: 'Leagues', href: '/leagues' },
  { name: 'Waiver Wire', href: '/waiver-wire' },
  { name: 'Content', href: '/content' },
  { name: 'Historical', href: '/historical' },
  { name: 'Analytics', href: '/analytics' },
  { name: 'Advanced Analysis', href: '/advanced-analysis' },
  { name: 'Blog', href: '/blog' },
]

export function Navbar() {
  const location = useLocation()
  const { user, logout } = useAuth()

  return (
    <nav className="bg-white shadow-sm border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex">
            <div className="flex-shrink-0 flex items-center">
              <Link to="/" className="text-xl font-bold text-blue-600">
                FF Assistant
              </Link>
            </div>
            <div className="ml-6 flex space-x-8">
              {navigation.map((item) => (
                <Link
                  key={item.name}
                  to={item.href}
                  className={clsx(
                    'inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium transition-colors',
                    location.pathname === item.href
                      ? 'border-blue-500 text-gray-900'
                      : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
                  )}
                >
                  {item.name}
                </Link>
              ))}
            </div>
          </div>
          
          <div className="flex items-center space-x-4">
            {user ? (
              <>
                <div className="flex items-center space-x-2">
                  <UserIcon className="h-5 w-5 text-gray-400" />
                  <span className="text-sm font-medium text-gray-700">
                    {user.full_name || user.username}
                  </span>
                </div>
                <button
                  onClick={logout}
                  className="flex items-center space-x-1 text-sm text-gray-500 hover:text-gray-700"
                >
                  <ArrowRightOnRectangleIcon className="h-4 w-4" />
                  <span>Sign Out</span>
                </button>
              </>
            ) : (
              <Link
                to="/auth"
                className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 transition-colors"
              >
                Sign In
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}