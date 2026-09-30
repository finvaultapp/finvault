// Accessibility checks: axe (WCAG 2.2 A and AA rules) on the main pages in both themes, plus the keyboard basics
// axe can't see: the skip link, focus moving into and out of a dialog, Escape, and <html lang>.
// Serious and critical violations fail the run.
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const PAGES = [
  ['/', 'To sort'], ['/transactions', 'Transactions'], ['/accounts', 'Accounts'], ['/import', 'Import a statement'],
  ['/import/move', 'Move from another app'], ['/categories', 'Categories'], ['/rules', 'Rules'], ['/payees', 'Payees'],
  ['/reports', 'Reports'], ['/budgets', 'Budgets'], ['/goals', 'Goals'], ['/bills', 'Bills'], ['/forecast', 'Cash-flow forecast'],
  ['/debts', 'Debt payoff'], ['/investments', 'Investments'], ['/assets', 'Assets'], ['/tax', 'Tax time'],
  ['/year-in-review', null], ['/people', 'Shared costs'], ['/settings', 'Settings'],
]

async function scan(page, include) {
  let builder = new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
  if (include) builder = builder.include(include)
  const { violations } = await builder.analyze()
  // One line per problem, so a failure says what and where.
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .flatMap((v) => v.nodes.map((n) => `${v.impact} ${v.id}: ${n.target.join(' ')} (${v.help})`))
}

for (const theme of ['light', 'dark']) {
  test.describe(`${theme} theme`, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((th) => localStorage.setItem('fv.theme', JSON.stringify(th)), theme)
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    })

    for (const [path, heading] of PAGES) {
      test(`axe finds nothing serious on ${path}`, async ({ page }) => {
        await page.goto(path)
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        if (heading) await expect(page.getByRole('heading', { name: heading }).first()).toBeVisible()
        else await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
        await page.waitForLoadState('networkidle')
        expect(await scan(page)).toEqual([])
      })
    }

    test('axe finds nothing serious in the transaction dialog and the search palette', async ({ page }) => {
      await page.goto('/transactions')
      await page.getByRole('button', { name: 'Add transaction' }).click()
      const dialog = page.getByRole('dialog', { name: 'Add transaction' })
      await expect(dialog).toBeVisible()
      await dialog.getByRole('combobox', { name: 'Tags' }).fill('v')
      expect(await scan(page, '[role="dialog"]')).toEqual([])
      await page.keyboard.press('Escape') // closes the tag suggestions
      await page.keyboard.press('Escape') // closes the dialog
      await expect(dialog).toBeHidden()

      await page.keyboard.press('Control+k')
      await expect(page.getByRole('combobox', { name: 'Search pages and transactions' })).toBeFocused()
      await page.keyboard.type('bud')
      expect(await scan(page, '.palette')).toEqual([])
    })
  })
}

test('the skip link is the first stop and moves focus to the main content', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'To sort' })).toBeVisible()
  await page.keyboard.press('Tab')
  const skip = page.getByRole('link', { name: 'Skip to main content' })
  await expect(skip).toBeFocused()
  await expect(skip).toBeInViewport()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
})

test('a dialog takes focus, keeps Tab inside, closes on Escape and gives focus back', async ({ page }) => {
  await page.goto('/transactions')
  const trigger = page.getByRole('button', { name: 'Add transaction' })
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: 'Add transaction' })
  await expect(dialog).toBeVisible()
  expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true)
  for (let i = 0; i < 30; i++) await page.keyboard.press('Tab')
  expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true)
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(trigger).toBeFocused()
})

test('the tray can be sorted from the keyboard and says so', async ({ page }) => {
  await page.goto('/')
  const tray = page.getByRole('region', { name: 'Transactions to sort' })
  const chip = tray.locator('.sort-chip').first()
  await chip.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('status').filter({ hasText: /^Sorted / })).toBeAttached()
  expect(await tray.evaluate((el) => el.contains(document.activeElement))).toBe(true)
})

test('<html lang> follows the chosen language', async ({ page }) => {
  await page.goto('/settings')
  await expect(page.locator('html')).toHaveAttribute('lang', 'en-CA')
  await page.getByLabel('Language').selectOption('fr')
  try {
    await expect(page.locator('html')).toHaveAttribute('lang', 'fr-CA')
    await expect(page.getByRole('link', { name: 'Passer au contenu principal' })).toBeAttached()
    expect(await scan(page)).toEqual([])
  } finally {
    await page.getByLabel('Langue').selectOption('en')
    await expect(page.locator('html')).toHaveAttribute('lang', 'en-CA')
  }
})
