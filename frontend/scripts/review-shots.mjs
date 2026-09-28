// Capture review screenshots of the newer pages (desktop and phone) from a running server with demo data.
//   node scripts/review-shots.mjs http://127.0.0.1:8792 <outdir>
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const [base = 'http://127.0.0.1:8792', out = '../.impeccable/review'] = process.argv.slice(2)
mkdirSync(out, { recursive: true })

const PAGES = ['/', '/tax', '/bills', '/people', '/plans', '/forecast', '/debts', '/year-in-review', '/investments', '/categories', '/accounts']
const browser = await chromium.launch()

async function shoot(width, height, scheme, suffix, pages) {
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, deviceScaleFactor: 1 })
  const page = await ctx.newPage()
  await page.goto(`${base}/login`)
  await page.evaluate((s) => localStorage.setItem('fv.theme', JSON.stringify(s)), scheme)
  await page.getByLabel('Email').fill('demo@finvault.local')
  await page.getByLabel('Password').fill('demo-password-123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL(`${base}/`)
  for (const path of pages) {
    await page.goto(base + path)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(700) // let charts settle
    const name = (path === '/' ? 'dashboard' : path.slice(1)) + suffix
    await page.screenshot({ path: `${out}/${name}.png`, fullPage: false })
  }
  await ctx.close()
}

await shoot(1280, 800, 'light', '', PAGES)
await shoot(1280, 800, 'dark', '-dark', ['/', '/forecast', '/investments', '/year-in-review'])
await shoot(390, 844, 'light', '-mobile', ['/', '/bills', '/debts', '/investments'])
await browser.close()
console.log('saved to', out)
