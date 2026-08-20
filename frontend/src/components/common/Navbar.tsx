import { Fragment, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import clsx from 'clsx'
import { Menu, Transition } from '@headlessui/react'
import { useAuth } from '../../hooks/useAuth'
import {
  UserIcon,
  ArrowRightOnRectangleIcon,
  ChevronDownIcon,
  Bars3Icon,
  XMarkIcon,
} from '@heroicons/react/24/outline'

const primaryNavigation = [
  { name: 'Home', href: '/' },
  { name: 'Draft Assistant', href: '/draft' },
  { name: 'Leagues', href: '/leagues' },
  { name: 'Players', href: '/players' },
]

const moreNavigation = [
  { name: 'Post-Draft Analysis', href: '/post-draft' },
  { name: 'Live Draft', href: '/live-draft' },
  { name: 'Waiver Wire', href: '/waiver-wire' },
  { name: 'Content', href: '/content' },
  { name: 'Historical', href: '/historical' },
  { name: 'Analytics', href: '/analytics' },
  { name: 'Advanced Analysis', href: '/advanced-analysis' },
  { name: 'Blog', href: '/blog' },
]

const allNavigation = [...primaryNavigation, ...moreNavigation]

export function Navbar() {
  const location = useLocation()
  const { user, logout } = useAuth()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const isMoreActive = moreNavigation.some((item) => item.href === location.pathname)

  return (
    <nav className="bg-white shadow-sm border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex min-w-0">
            <div className="flex-shrink-0 flex items-center">
              <Link to="/" className="text-xl font-bold text-blue-600">
                FF Assistant
              </Link>
            </div>
            <div className="hidden md:ml-6 md:flex md:items-center md:space-x-6">
              {primaryNavigation.map((item) => (
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

              <Menu as="div" className="relative inline-block text-left h-16 flex items-center">
                {({ open }) => (
                  <>
                    <Menu.Button
                      className={clsx(
                        'inline-flex items-center gap-1 px-1 pt-1 border-b-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 rounded-sm',
                        open || isMoreActive
                          ? 'border-blue-500 text-gray-900'
                          : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
                      )}
                    >
                      More
                      <ChevronDownIcon
                        className={clsx('h-4 w-4 transition-transform', open && 'rotate-180')}
                        aria-hidden="true"
                      />
                    </Menu.Button>
                    <Transition
                      as={Fragment}
                      enter="transition ease-out duration-100"
                      enterFrom="transform opacity-0 scale-95"
                      enterTo="transform opacity-100 scale-100"
                      leave="transition ease-in duration-75"
                      leaveFrom="transform opacity-100 scale-100"
                      leaveTo="transform opacity-0 scale-95"
                    >
                      <Menu.Items className="absolute left-0 top-full z-20 mt-1 w-56 origin-top-left rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none py-1">
                        {moreNavigation.map((item) => (
                          <Menu.Item key={item.name}>
                            {({ active }) => (
                              <Link
                                to={item.href}
                                className={clsx(
                                  'block px-4 py-2 text-sm transition-colors',
                                  location.pathname === item.href
                                    ? 'text-blue-600 font-medium'
                                    : 'text-gray-700',
                                  active && 'bg-gray-100'
                                )}
                              >
                                {item.name}
                              </Link>
                            )}
                          </Menu.Item>
                        ))}
                      </Menu.Items>
                    </Transition>
                  </>
                )}
              </Menu>
            </div>
          </div>

          <div className="hidden md:flex items-center space-x-4">
            {user ? (
              <>
                <div className="flex items-center space-x-2 min-w-0">
                  <UserIcon className="h-5 w-5 text-gray-400 flex-shrink-0" />
                  <span className="text-sm font-medium text-gray-700 truncate max-w-[10rem]">
                    {user.full_name || user.username}
                  </span>
                </div>
                <button
                  onClick={logout}
                  className="flex items-center space-x-1 text-sm text-gray-500 hover:text-gray-700 flex-shrink-0"
                >
                  <ArrowRightOnRectangleIcon className="h-4 w-4" />
                  <span>Sign Out</span>
                </button>
              </>
            ) : (
              <Link
                to="/auth"
                className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 transition-colors flex-shrink-0"
              >
                Sign In
              </Link>
            )}
          </div>

          <div className="flex items-center md:hidden">
            <button
              type="button"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-nav-panel"
              aria-label={mobileMenuOpen ? 'Close main menu' : 'Open main menu'}
              className="inline-flex items-center justify-center p-2 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              {mobileMenuOpen ? (
                <XMarkIcon className="h-6 w-6" aria-hidden="true" />
              ) : (
                <Bars3Icon className="h-6 w-6" aria-hidden="true" />
              )}
            </button>
          </div>
        </div>
      </div>

      {mobileMenuOpen && (
        <div id="mobile-nav-panel" className="md:hidden border-t border-gray-200">
          <div className="px-2 pt-2 pb-3 space-y-1">
            {allNavigation.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className={clsx(
                  'block rounded-md px-3 py-2 text-base font-medium transition-colors',
                  location.pathname === item.href
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                )}
              >
                {item.name}
              </Link>
            ))}
          </div>
          <div className="border-t border-gray-200 px-4 py-3">
            {user ? (
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center space-x-2 min-w-0">
                  <UserIcon className="h-5 w-5 text-gray-400 flex-shrink-0" />
                  <span className="text-sm font-medium text-gray-700 truncate">
                    {user.full_name || user.username}
                  </span>
                </div>
                <button
                  onClick={() => {
                    setMobileMenuOpen(false)
                    logout()
                  }}
                  className="flex items-center space-x-1 text-sm text-gray-500 hover:text-gray-700 flex-shrink-0"
                >
                  <ArrowRightOnRectangleIcon className="h-4 w-4" />
                  <span>Sign Out</span>
                </button>
              </div>
            ) : (
              <Link
                to="/auth"
                onClick={() => setMobileMenuOpen(false)}
                className="block w-full text-center bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 transition-colors"
              >
                Sign In
              </Link>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}
