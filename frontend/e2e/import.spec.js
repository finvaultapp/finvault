import { expect, test } from '@playwright/test'

// TD's CSV export has no header row: date, description, withdrawal, deposit, balance (MM/DD/YYYY).
// A run-specific tag keeps the lines new if the suite is re-run against the same database.
const tag = Date.now().toString(36).toUpperCase()
const rows = [
  ['09/02/2026', `E2E BAKERY ${tag}`, '12.50', '', '4187.50'],
  ['09/03/2026', `E2E REFUND ${tag}`, '', '40.00', '4227.50'],
  ['09/04/2026', `E2E HARDWARE ${tag}`, '63.25', '', '4164.25'],
]
const csv = rows.map((r) => r.join(',')).join('\n') + '\n'

test('import a TD CSV into Joint Chequing', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Import statement' }).click()
  await expect(page.getByRole('heading', { name: 'Import a statement' })).toBeVisible()

  await page.getByLabel('Import into').selectOption({ label: 'Joint Chequing · TD Canada Trust' })
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Drop your statement file here/ }).click()
  await (await chooser).setFiles({ name: 'accountactivity.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })

  // Preview: every line is listed with the right sign, and all three are new.
  await expect(page.getByRole('heading', { name: 'Preview' })).toBeVisible()
  for (const [, desc] of rows) await expect(page.getByRole('cell', { name: desc })).toBeVisible()
  await expect(page.getByRole('cell', { name: '−$12.50' })).toBeVisible()
  await expect(page.getByRole('cell', { name: '+$40.00' })).toBeVisible()

  // Commit and check the success card.
  await page.getByRole('button', { name: 'Import 3 transactions' }).click()
  await expect(page.getByRole('heading', { name: 'Imported 3 transactions' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Import another' })).toBeVisible()
})
