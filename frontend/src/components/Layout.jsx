import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowLeftRight, BarChart3, Bot, ChevronDown, Eye, EyeOff, Landmark, LayoutDashboard, LogOut, Menu, Moon, PiggyBank,
  Plug, Repeat, Search, Settings, Shield, SlidersHorizontal, Sun, Tag, Target, Upload, Wallet,
  CalendarDays, FileText, Users, BadgeDollarSign, LineChart,
  CreditCard, Sparkles, TrendingUp, Store,
} from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { date } from '../lib/format'
import { useData, useToast } from './ui'
import { Money } from './ui'
import Logo from './Logo'
import CommandPalette from './CommandPalette'
import OfflineBanner from './OfflineBanner'
import { clearOfflineData } from '../lib/offline'

// `hidden` items stay out of the sidebar but can still be found from the command palette.
export const NAV = [
  { group: null, items: [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight, badge: 'uncategorized' },
  ] },
  { group: 'Bring in and sort', items: [
    { to: '/accounts', label: 'Accounts', icon: Wallet },
    { to: '/import', label: 'Import', icon: Upload },
    { to: '/sync', label: 'Bank sync', icon: Plug, needsSync: true },
    { to: '/categories', label: 'Categories', icon: Tag },
    { to: '/rules', label: 'Rules', icon: SlidersHorizontal },
    { to: '/payees', label: 'Payees', icon: Store },
  ] },
  { group: 'Look back', items: [
    { to: '/reports', label: 'Reports', icon: BarChart3 },
    { to: '/investments', label: 'Investments', icon: LineChart },
    { to: '/assets', label: 'Assets', icon: Landmark },
    { to: '/tax', label: 'Tax time', icon: FileText },
    { to: '/year-in-review', label: 'Year in review', icon: Sparkles },
    { to: '/chat', label: 'Ask AI', icon: Bot, needsAi: true },
  ] },
  { group: 'Plan ahead', items: [
    { to: '/budgets', label: 'Budgets', icon: PiggyBank },
    { to: '/goals', label: 'Goals', icon: Target },
    { to: '/plans', label: 'Registered accounts', icon: BadgeDollarSign },
    { to: '/forecast', label: 'Forecast', icon: TrendingUp },
    { to: '/debts', label: 'Debt payoff', icon: CreditCard },
    { to: '/bills', label: 'Bills', icon: CalendarDays },
    { to: '/recurring', label: 'Recurring', icon: Repeat, hidden: true },
  ] },
]

export default function Layout() {
  const { user, setUser, theme, toggleTheme, hidden, toggleHidden, version, status } = useApp()
  const [navOpen, setNavOpen] = useState(false)
  const [palette, setPalette] = useState(false)
  const [showAllAccounts, setShowAllAccounts] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const accounts = useData(() => api.get('/accounts'), [version])
  const dash = useData(() => api.get('/transactions?uncategorized=true&page_size=1'), [version])
  const sync = useData(() => api.get('/sync/status').catch(() => null), [])

  useEffect(() => setNavOpen(false), [location.pathname])
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(true) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const toast = useToast()
  const logout = async () => {
    clearOfflineData() // even offline, so the next person on this phone can't see saved data
    try { await api.post('/auth/logout') } catch (e) {
      toast(e.status === 0 ? t('Saved data on this device was cleared. Connect to the internet to finish signing out.') : e.message, 'error')
      return
    }
    setUser(null)
    navigate('/login')
  }

  const items = accounts.data?.items.filter((a) => !a.is_archived) ?? []
  const base = accounts.data?.base_currency ?? user.base_currency
  const total = items.reduce((s, a) => s + (a.balance_converted ?? 0), 0)
  const shown = showAllAccounts ? items : items.slice(0, 4)
  const uncategorized = dash.data?.total ?? 0
  const aiOn = status?.ai_enabled
  const syncOn = sync.data?.enabled

  return (
    <div className={`shell ${navOpen ? 'nav-open' : ''}`}>
      {navOpen && <div className="nav-scrim" onClick={() => setNavOpen(false)} />}
      <aside className="sidebar" aria-label={t('Main navigation')}>
        <div className="sidebar-head">
          <Link to="/" className="brand"><Logo />FinVault</Link>
        </div>
        <button className="search-trigger" onClick={() => setPalette(true)}>
          <Search size={15} /> {t('Search everything…')} <kbd>Ctrl K</kbd>
        </button>
        <nav className="nav">
          {NAV.map((g) => (
            <div className="nav-group" key={g.group ?? 'top'}>
              {g.group && <div className="nav-label">{t(g.group)}</div>}
              {g.items.filter((i) => !i.hidden && (!i.needsAi || aiOn) && (!i.needsSync || syncOn)).map((i) => (
                <NavLink key={i.to} to={i.to} end={i.end}>
                  <i.icon />{t(i.label)}
                  {i.badge === 'uncategorized' && uncategorized > 0 && <span className="count" title={t('Need a category')}>{uncategorized}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {items.length > 0 && (
          <div className="side-accounts">
            <div className="side-accounts-head">
              <span className="nav-label" style={{ padding: 0 }}>{t('Your accounts')}</span>
              <strong><Money value={total} currency={base} /></strong>
            </div>
            {shown.map((a) => (
              <Link key={a.id} to={`/transactions?account=${a.id}`} className="side-account">
                <div><div className="name">{a.name}</div><small className={fresh(a.last_transaction).stale ? 'stale' : ''}>{fresh(a.last_transaction).text}</small></div>
                <Money value={a.balance} currency={a.currency} />
              </Link>
            ))}
            {items.length > 4 && (
              <button className="link-btn small" style={{ padding: '6px 10px' }} onClick={() => setShowAllAccounts((v) => !v)}>
                {showAllAccounts ? t('Show fewer') : t('+{n} more', { n: items.length - 4 })} <ChevronDown size={14} style={{ transform: showAllAccounts ? 'rotate(180deg)' : '' }} />
              </button>
            )}
          </div>
        )}

        {/* Household sits by the member at the foot, so the account list starts inside a laptop-height window. */}
        <nav className="nav nav-household" aria-label={t('Household')}>
          <div className="nav-group">
            <div className="nav-label">{t('Household')}</div>
            <NavLink to="/people"><Users />{t('Shared costs')}</NavLink>
            <NavLink to="/settings"><Settings />{t('Settings')}</NavLink>
            {user.is_admin && <NavLink to="/admin"><Shield />{t('Admin')}</NavLink>}
          </div>
        </nav>

        <div className="sidebar-foot">
          <span className="avatar">{(user.name || user.email)[0].toUpperCase()}</span>
          <div className="who">
            <div>{user.name || user.email.split('@')[0]}</div>
            <small>{user.email}{user.is_admin ? ` · ${t('admin')}` : ''}</small>
          </div>
          <button className="icon-btn" onClick={toggleHidden} aria-label={hidden ? t('Show amounts') : t('Hide amounts')} title={hidden ? t('Show amounts') : t('Hide amounts')}>{hidden ? <EyeOff /> : <Eye />}</button>
          <button className="icon-btn" onClick={toggleTheme} aria-label={t('Toggle dark mode')} title={t('Toggle dark mode')}>{theme === 'dark' ? <Sun /> : <Moon />}</button>
          <button className="icon-btn" onClick={logout} aria-label={t('Sign out')} title={t('Sign out')}><LogOut /></button>
        </div>
      </aside>

      <div>
        <div className="mobile-bar">
          <button className="icon-btn" onClick={() => setNavOpen(true)} aria-label={t('Open menu')}><Menu /></button>
          <Link to="/" className="brand"><Logo />FinVault</Link>
          <span className="spacer" />
          <button className="icon-btn" onClick={() => setPalette(true)} aria-label={t('Search')}><Search /></button>
          <button className="icon-btn" onClick={toggleHidden} aria-label={hidden ? t('Show amounts') : t('Hide amounts')}>{hidden ? <EyeOff /> : <Eye />}</button>
        </div>
        <main className="main"><div className="page"><OfflineBanner /><Outlet /></div></main>
      </div>
      {palette && <CommandPalette onClose={() => setPalette(false)} aiOn={aiOn} />}
    </div>
  )
}

function fresh(last) {
  if (!last) return { text: t('nothing imported yet'), stale: true }
  const [y, m, d] = last.split('-').map(Number)
  const days = Math.round((new Date(new Date().toDateString()) - new Date(y, m - 1, d)) / 86400000)
  const stale = days > 35
  if (days <= 0) return { text: t('latest today'), stale }
  if (days === 1) return { text: t('latest yesterday'), stale }
  if (days < 45) return { text: t('latest {n} days ago', { n: days }), stale }
  return { text: t('latest {date}', { date: date(last, { month: 'short', day: 'numeric' }) }), stale }
}

function typeLabel(type) {
  return t({ checking: 'Chequing', savings: 'Savings', credit_card: 'Credit card', investment: 'Investment', cash: 'Cash', loan: 'Loan' }[type] ?? 'Account')
}
