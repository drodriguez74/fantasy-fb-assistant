import { Fragment, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import clsx from 'clsx'
import { Menu, Transition } from '@headlessui/react'
import { useAuth } from '../../hooks/useAuth'
import { NotificationBell } from './NotificationBell'
import { ThemeToggle } from './ThemeToggle'
import {
  UserIcon,
  ArrowRightOnRectangleIcon,
  ChevronDownIcon,
  Bars3Icon,
  XMarkIcon,
} from '@heroicons/react/24/outline'

// The in-season core: what a user touches every week during the season.
const primaryNavigation = [
  { name: 'This Week', href: '/this-week' },
  { name: 'Leagues', href: '/leagues' },
  { name: 'Waivers', href: '/waiver-wire' },
  { name: 'Trades', href: '/trade-analyzer' },
  { name: 'Players', href: '/players' },
]

// Everything else — analysis surfaces and the look-back Reports hub.
const moreNavigation = [
  { name: 'Reports', href: '/reports' },
  { name: 'Content', href: '/content' },
  { name: 'Analytics', href: '/analytics' },
  { name: 'Advanced Analysis', href: '/advanced-analysis' },
]

const allNavigation = [...primaryNavigation, ...moreNavigation]

/**
 * The navbar is the "broadcast bug" — it stays dark (ink-950) in both light
 * and dark mode, the fixed anchor the rest of the theme moves around.
 */
export function Navbar() {
  const location = useLocation()
  const { user, logout } = useAuth()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const isMoreActive = moreNavigation.some((item) => item.href === location.pathname)

  return (
    <nav className="bg-ink-950 text-ink-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex min-w-0">
            <div className="flex-shrink-0 flex items-center">
              <Link to="/" className="flex items-center gap-2.5">
                <span className="flex h-6 w-6 items-center justify-center bg-volt font-display text-base font-bold leading-none text-volt-ink">
                  FF
                </span>
                <span className="font-display text-xl font-bold uppercase tracking-[0.06em] text-ink-50">
                  Assistant
                </span>
              </Link>
            </div>
            <div className="hidden md:ml-8 md:flex md:items-center md:space-x-6">
              {primaryNavigation.map((item) => (
                <Link
                  key={item.name}
                  to={item.href}
                  className={clsx(
                    'inline-flex items-center px-1 pt-1 border-b-2 font-stat text-xs tracking-wide transition-colors',
                    location.pathname === item.href
                      ? 'border-volt text-ink-50'
                      : 'border-transparent text-ink-400 hover:border-ink-600 hover:text-ink-100'
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
                        'inline-flex items-center gap-1 px-1 pt-1 border-b-2 font-stat text-xs tracking-wide transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-volt rounded-sm',
                        open || isMoreActive
                          ? 'border-volt text-ink-50'
                          : 'border-transparent text-ink-400 hover:border-ink-600 hover:text-ink-100'
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
                      <Menu.Items className="absolute left-0 top-full z-20 mt-1 w-56 origin-top-left border border-ink-700 bg-ink-900 shadow-lg focus:outline-none py-1">
                        {moreNavigation.map((item) => (
                          <Menu.Item key={item.name}>
                            {({ active }) => (
                              <Link
                                to={item.href}
                                className={clsx(
                                  'block px-4 py-2 font-stat text-xs transition-colors',
                                  location.pathname === item.href
                                    ? 'text-volt'
                                    : 'text-ink-300',
                                  active && 'bg-ink-800 text-ink-50'
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
            <ThemeToggle />
            {user ? (
              <>
                <NotificationBell />
                <div className="flex items-center space-x-2 min-w-0">
                  <UserIcon className="h-5 w-5 text-ink-500 flex-shrink-0" />
                  <span className="text-sm font-medium text-ink-200 truncate max-w-[10rem]">
                    {user.full_name || user.username}
                  </span>
                </div>
                <button
                  onClick={logout}
                  className="flex items-center space-x-1 text-sm text-ink-400 hover:text-ink-100 flex-shrink-0"
                >
                  <ArrowRightOnRectangleIcon className="h-4 w-4" />
                  <span>Sign Out</span>
                </button>
              </>
            ) : (
              <Link
                to="/auth"
                className="bg-volt text-volt-ink px-4 py-2 font-stat text-xs font-medium hover:bg-volt-dark transition-colors flex-shrink-0"
              >
                Sign In
              </Link>
            )}
          </div>

          <div className="flex items-center gap-1 md:hidden">
            <ThemeToggle />
            {user && <NotificationBell />}
            <button
              type="button"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-nav-panel"
              aria-label={mobileMenuOpen ? 'Close main menu' : 'Open main menu'}
              className="inline-flex items-center justify-center p-2 rounded-sm text-ink-400 hover:text-ink-100 hover:bg-ink-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-volt"
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

      <div className="yard-divider" aria-hidden="true" />

      {mobileMenuOpen && (
        <div id="mobile-nav-panel" className="md:hidden bg-ink-950 border-t border-ink-800">
          <div className="px-2 pt-2 pb-3 space-y-1">
            {allNavigation.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className={clsx(
                  'block px-3 py-2 font-stat text-sm transition-colors',
                  location.pathname === item.href
                    ? 'bg-ink-800 text-volt'
                    : 'text-ink-300 hover:bg-ink-800 hover:text-ink-50'
                )}
              >
                {item.name}
              </Link>
            ))}
          </div>
          <div className="border-t border-ink-800 px-4 py-3">
            {user ? (
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center space-x-2 min-w-0">
                  <UserIcon className="h-5 w-5 text-ink-500 flex-shrink-0" />
                  <span className="text-sm font-medium text-ink-200 truncate">
                    {user.full_name || user.username}
                  </span>
                </div>
                <button
                  onClick={() => {
                    setMobileMenuOpen(false)
                    logout()
                  }}
                  className="flex items-center space-x-1 text-sm text-ink-400 hover:text-ink-100 flex-shrink-0"
                >
                  <ArrowRightOnRectangleIcon className="h-4 w-4" />
                  <span>Sign Out</span>
                </button>
              </div>
            ) : (
              <Link
                to="/auth"
                onClick={() => setMobileMenuOpen(false)}
                className="block w-full text-center bg-volt text-volt-ink px-4 py-2 font-stat text-sm font-medium hover:bg-volt-dark transition-colors"
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
