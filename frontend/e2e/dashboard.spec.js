import { expect, test } from '@playwright/test'

const tray = (page) => page.getByRole('region', { name: 'Transactions to sort' })
// The tray header shows the number of uncategorized lines as a bare number.
const trayCount = async (page) => Number(await tray(page).getByText(/^\d+$/).first().textContent())

test('dashboard shows the "To sort" tray and the "Where it went" wall', async ({ page }) => {
  await page.goto('/')
  await expect(tray(page).getByRole('heading', { name: 'To sort' })).toBeVisible()
  const wall = page.getByRole('region', { name: 'Spending by category' })
  await expect(wall.getByRole('heading', { name: 'Where it went' })).toBeVisible()
  await expect(wall.getByRole('link').first()).toBeVisible()
})

test('sorting a tray item with a chip lowers the tray count', async ({ page }) => {
  await page.goto('/')
  await expect(tray(page).getByRole('heading', { name: 'To sort' })).toBeVisible()
  const before = await trayCount(page)
  expect(before, 'the demo data leaves some lines uncategorized').toBeGreaterThan(0)

  // The first button in the tray is the first item's top category chip.
  await tray(page).getByRole('button').first().click()
  await expect.poll(() => trayCount(page)).toBe(before - 1)
})
