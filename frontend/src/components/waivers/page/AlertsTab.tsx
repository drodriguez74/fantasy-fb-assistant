import { BellIcon } from '@heroicons/react/24/outline'
import type { Notification } from '../../../types'

interface AlertsTabProps {
  alerts: Notification[]
}

export function AlertsTab({ alerts }: AlertsTabProps) {
  return (
      <div className="space-y-6">
        <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
          <h3 className="text-lg font-medium text-body mb-4">Waiver Wire Alerts</h3>
          <p className="text-sm text-muted mb-4">
            Real, backend-tracked notifications generated from genuine waiver-wire
            signal -- the same feed behind the bell icon in the navbar.
          </p>
          {alerts.length === 0 ? (
            <div className="text-center py-8">
              <BellIcon className="mx-auto h-12 w-12 text-faint" />
              <h3 className="mt-2 text-sm font-medium text-body">No alerts</h3>
              <p className="mt-1 text-sm text-muted">
                You'll see important waiver wire notifications here.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {alerts.map((alert) => (
                <div key={alert.id} className={`border-l-4 p-4 ${
                  alert.is_read ? 'border-line bg-surface-2' : 'border-accent-ink bg-highlight'
                }`}>
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <BellIcon className={`h-5 w-5 ${alert.is_read ? 'text-faint' : 'text-faint'}`} />
                    </div>
                    <div className="ml-3 flex-1">
                      <h4 className="text-sm font-medium text-body">{alert.title}</h4>
                      <p className="mt-1 text-sm text-muted">{alert.body}</p>
                      <div className="mt-2 flex items-center space-x-4 text-xs text-muted">
                        <span>{new Date(alert.created_at).toLocaleString()}</span>
                        {!alert.is_read && (
                          <>
                            <span>•</span>
                            <span className="font-medium text-accent-ink">Unread</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
  )
}
