import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'

const baseURL = process.env.FINVAULT_SCREENSHOT_URL ?? 'http://127.0.0.1:8765'
const outDir = path.resolve(process.cwd(), '..', 'docs', 'screenshots')

async function snap(page, name, url) {
  await page.goto(`${baseURL}${url}`, { waitUntil: 'networkidle' })
  await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: true })
}

await mkdir(outDir, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 })

await page.goto(baseURL, { waitUntil: 'networkidle' })
await page.getByLabel('Email').fill('demo@finvault.local')
await page.getByLabel('Password').fill('demo-password-123')
await page.getByRole('button', { name: 'Sign in' }).click()
await page.getByRole('link', { name: 'Import statement' }).waitFor({ timeout: 10000 })
await page.waitForLoadState('networkidle')

await snap(page, 'dashboard', '/')
await snap(page, 'transactions', '/transactions')
await snap(page, 'reports', '/reports')
await snap(page, 'import', '/import')

await browser.close()
