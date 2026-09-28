// Signs in as the demo user through the login form and saves the session for the other specs.
// The demo user comes from backend/scripts/demo_seed.py.
import { expect, test as setup } from '@playwright/test'

const DEMO = { email: 'demo@finvault.local', password: 'demo-password-123' }

setup('sign in as the demo user', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await page.getByLabel('Email').fill(DEMO.email)
  await page.getByLabel('Password').fill(DEMO.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'To sort' })).toBeVisible()
  await page.context().storageState({ path: 'e2e/.auth/demo.json' })
})
