import { Fragment, useCallback, useEffect, useState } from 'react'
import { Menu, Transition } from '@headlessui/react'
import { BellIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { notifications as notificationsApi } from '../../services/api'
import type { Notification } from '../../types'

// In-app notification center: a bell icon that shows real, backend-tracked
// alerts (see backend/app/services/notification_service.py for how they're
// generated -- from a live Sleeper trending-add spike, never fabricated).
// This is intentionally NOT device/browser push -- no service worker, no
// permission prompt, nothing fires when the tab is closed. It only surfaces
// what's already been recorded server-side when the user opens the panel.

const TYPE_LABEL: Record<string, string> = {
  trending_add: 'Trending',
  injury_update: 'Injury',
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  const diffMs = Date.now() - date.getTime()
  const diffMin = Math.round(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.round(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.round(diffHr / 24)
  return `${diffDay}d ago`
}

const UNREAD_POLL_INTERVAL_MS = 60_000

export function NotificationBell() {
  const [items, setItems] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)

  const refreshUnreadCount = useCallback(async () => {
    try {
      const response = await notificationsApi.getUnreadCount()
      setUnreadCount(response.data.unread_count)
    } catch (error) {
      console.error('Failed to load unread notification count:', error)
    }
  }, [])

  const loadNotifications = useCallback(async () => {
    setLoading(true)
    try {
      const response = await notificationsApi.list({ page_size: 10 })
      setItems(response.data.notifications)
    } catch (error) {
      console.error('Failed to load notifications:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshUnreadCount()
    const interval = setInterval(refreshUnreadCount, UNREAD_POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [refreshUnreadCount])

  const handleMarkRead = async (id: number) => {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    setUnreadCount((prev) => Math.max(0, prev - 1))
    try {
      await notificationsApi.markRead(id)
    } catch (error) {
      console.error('Failed to mark notification as read:', error)
    }
  }

  const handleMarkAllRead = async () => {
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })))
    setUnreadCount(0)
    try {
      await notificationsApi.markAllRead()
    } catch (error) {
      console.error('Failed to mark all notifications as read:', error)
    }
  }

  return (
    <Menu as="div" className="relative inline-block text-left">
      {() => (
        <>
          <Menu.Button
            onClick={() => loadNotifications()}
            aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
            className="relative inline-flex items-center justify-center rounded-full p-2 text-muted transition-colors hover:bg-surface-2 hover:text-body focus:outline-none focus-visible:ring-2 focus-visible:ring-volt focus-visible:ring-offset-2"
          >
            <BellIcon className="h-5 w-5" aria-hidden="true" />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-danger-500 px-1 text-[10px] font-semibold leading-none text-white">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
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
              <Menu.Items className="absolute right-0 top-full z-20 mt-1 w-80 origin-top-right rounded-md bg-surface ring-1 ring-black ring-opacity-5 focus:outline-none">
                <div className="flex items-center justify-between border-b border-hairline px-4 py-2">
                  <span className="text-sm font-semibold text-body">Notifications</span>
                  {items.some((n) => !n.is_read) && (
                    <button
                      type="button"
                      onClick={handleMarkAllRead}
                      className="text-xs font-medium text-accent-ink hover:text-accent-ink"
                    >
                      Mark all as read
                    </button>
                  )}
                </div>
                <div className="max-h-96 overflow-y-auto">
                  {loading ? (
                    <p className="px-4 py-6 text-center text-sm text-muted">Loading...</p>
                  ) : items.length === 0 ? (
                    <p className="px-4 py-6 text-center text-sm text-muted">
                      No notifications yet. Check the Waiver Wire tab to pick up new trending-add alerts.
                    </p>
                  ) : (
                    items.map((notification) => (
                      <button
                        key={notification.id}
                        type="button"
                        onClick={() => !notification.is_read && handleMarkRead(notification.id)}
                        className={clsx(
                          'block w-full border-b border-hairline px-4 py-3 text-left last:border-b-0 hover:bg-surface-2',
                          !notification.is_read && 'bg-highlight/50'
                        )}
                      >
                        <div className="flex items-start gap-2">
                          {!notification.is_read && (
                            <span
                              className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent-500"
                              aria-hidden="true"
                            />
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <p
                                className={clsx(
                                  'truncate text-sm',
                                  !notification.is_read ? 'font-semibold text-body' : 'font-medium text-body'
                                )}
                              >
                                {notification.title}
                              </p>
                              <span className="flex-shrink-0 text-xs text-faint">
                                {formatRelativeTime(notification.created_at)}
                              </span>
                            </div>
                            <p className="mt-0.5 line-clamp-2 text-xs text-muted">{notification.body}</p>
                            <span className="mt-1 inline-block rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted">
                              {TYPE_LABEL[notification.type] ?? notification.type}
                            </span>
                          </div>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </Menu.Items>
            </Transition>
        </>
      )}
    </Menu>
  )
}
