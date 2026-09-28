import { useEffect, useRef } from 'react'
import { CloudOff } from 'lucide-react'
import { useApp } from '../context'
import { t } from '../i18n'
import { currentLocale } from '../lib/format'
import { useSavedDataTime } from '../lib/offline'

// Shown while any data on screen came from the copy saved on this device (see sw/sw.js).
export default function OfflineBanner() {
  const savedAt = useSavedDataTime()
  const { bump } = useApp()
  const bumpRef = useRef(bump)
  bumpRef.current = bump
  useEffect(() => {
    const back = () => bumpRef.current() // reload what's on screen once the connection returns
    window.addEventListener('online', back)
    return () => window.removeEventListener('online', back)
  }, [])
  if (!savedAt) return null
  return (
    <div className="banner warn offline-banner" role="status">
      <CloudOff />
      <div className="banner-body">{t('Offline, showing saved data from {time}', { time: when(savedAt) })}</div>
    </div>
  )
}

function when(iso) {
  const d = new Date(iso)
  const sameDay = d.toDateString() === new Date().toDateString()
  return sameDay
    ? d.toLocaleTimeString(currentLocale(), { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleString(currentLocale(), { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
