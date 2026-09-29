import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useApp } from './context'
import Layout from './components/Layout'
import { Loading } from './components/ui'
import Auth from './pages/Auth'
import Dashboard from './pages/Dashboard'

const Transactions = lazy(() => import('./pages/Transactions'))
const Accounts = lazy(() => import('./pages/Accounts'))
const Import = lazy(() => import('./pages/Import'))
const Migrate = lazy(() => import('./pages/Migrate'))
const Reports = lazy(() => import('./pages/Reports'))
const Assets = lazy(() => import('./pages/Assets'))
const Budgets = lazy(() => import('./pages/Budgets'))
const Goals = lazy(() => import('./pages/Goals'))
const Recurring = lazy(() => import('./pages/Recurring'))
const Categories = lazy(() => import('./pages/Categories'))
const Rules = lazy(() => import('./pages/Rules'))
const Settings = lazy(() => import('./pages/Settings'))
const Admin = lazy(() => import('./pages/Admin'))
const Sync = lazy(() => import('./pages/Sync'))
const Chat = lazy(() => import('./pages/Chat'))
const Plans = lazy(() => import('./pages/Plans'))
const Tax = lazy(() => import('./pages/Tax'))
const People = lazy(() => import('./pages/People'))
const Bills = lazy(() => import('./pages/Bills'))
const Forecast = lazy(() => import('./pages/Forecast'))
const Debts = lazy(() => import('./pages/Debts'))
const YearReview = lazy(() => import('./pages/YearReview'))
const Investments = lazy(() => import('./pages/Investments'))
const ResetPassword = lazy(() => import('./pages/ResetPassword'))
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'))
const Payees = lazy(() => import('./pages/Payees'))

export default function App() {
  const { user } = useApp()
  if (user === undefined) return null
  if (!user) {
    return (
      <Suspense fallback={null}>
        <Routes>
          <Route path="/register" element={<Auth mode="register" />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="*" element={<Auth mode="login" />} />
        </Routes>
      </Suspense>
    )
  }
  return (
    <Suspense fallback={<div className="main"><Loading /></div>}>
      <Routes>
        <Route path="reset-password" element={<ResetPassword />} />
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="transactions" element={<Transactions />} />
          <Route path="accounts" element={<Accounts />} />
          <Route path="import" element={<Import />} />
          <Route path="import/move" element={<Migrate />} />
          <Route path="reports" element={<Reports />} />
          <Route path="assets" element={<Assets />} />
          <Route path="budgets" element={<Budgets />} />
          <Route path="goals" element={<Goals />} />
          <Route path="recurring" element={<Recurring />} />
          <Route path="categories" element={<Categories />} />
          <Route path="rules" element={<Rules />} />
          <Route path="settings" element={<Settings />} />
          <Route path="sync" element={<Sync />} />
          <Route path="chat" element={<Chat />} />
          <Route path="plans" element={<Plans />} />
          <Route path="tax" element={<Tax />} />
          <Route path="people" element={<People />} />
          <Route path="bills" element={<Bills />} />
          <Route path="forecast" element={<Forecast />} />
          <Route path="debts" element={<Debts />} />
          <Route path="year-in-review" element={<YearReview />} />
          <Route path="investments" element={<Investments />} />
          <Route path="payees" element={<Payees />} />
          {user.is_admin && <Route path="admin" element={<Admin />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
