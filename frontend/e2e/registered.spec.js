// A TFSA statement from import to the Registered accounts page, with axe checks on the preview (per-line
// plan types) and on the Plans page once it holds imported lines, in both themes.
// The statement is made up: a Wealthsimple-style monthly CSV with a run-specific tag so re-runs stay new.
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const tag = Date.now().toString(36).toUpperCase()
const accountName = `E2E TFSA ${tag}`
const csv = [
  'date,transaction,description,amount,balance,currency',
  `2026-01-05,CONT,Contribution ${tag},4500.00,4500.00,CAD`,
  `2026-01-06,BUY,XEQT SAMPLE ${tag}: Bought 100 shares,-3000.00,1500.00,CAD`,
  `2026-03-28,DIV,XEQT SAMPLE ${tag}: Cash distribution,12.40,1512.40,CAD`,
  `2026-04-02,WD,Withdrawal ${tag},-500.00,1012.40,CAD`,
].join('\n') + '\n'

async function scan(page, include) {
  let builder = new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
  if (include) builder = builder.include(include)
  const { violations } = await builder.analyze()
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .flatMap((v) => v.nodes.map((n) => `${v.impact} ${v.id}: ${n.target.join(' ')} (${v.help})`))
}

test.describe.serial('registered statements', () => {
  test('import a TFSA statement: each line gets a type, and the result says what counted', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const r = await page.request.post('/api/accounts', { data: { name: accountName, type: 'investment', registered_kind: 'tfsa' }, headers: { 'X-FinVault': '1' } })
    expect(r.ok()).toBeTruthy()

    await page.goto('/import')
    await expect(page.getByRole('heading', { name: 'Import a statement' })).toBeVisible()
    await page.getByLabel('Import into').selectOption({ label: accountName })
    const chooser = page.waitForEvent('filechooser')
    await page.getByRole('button', { name: /Drop your statement file here/ }).click()
    await (await chooser).setFiles({ name: 'TFSA-monthly-statement.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })

    await expect(page.getByRole('heading', { name: 'Preview' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Plan type' })).toBeVisible()
    await expect(page.getByLabel(new RegExp(`^Plan type for Contribution ${tag}`))).toHaveValue('contribution')
    await expect(page.getByLabel(new RegExp(`^Plan type for XEQT SAMPLE ${tag}: Bought`))).toHaveValue('trade')
    await expect(page.getByLabel(new RegExp(`^Plan type for Withdrawal ${tag}`))).toHaveValue('withdrawal')
    // The member can correct a type before importing.
    await page.getByLabel(new RegExp(`^Plan type for XEQT SAMPLE ${tag}: Cash`)).selectOption('growth')
    await page.waitForLoadState('networkidle')
    expect(await scan(page)).toEqual([])

    await page.getByRole('button', { name: 'Import 4 transactions' }).click()
    await expect(page.getByRole('heading', { name: 'Imported 4 transactions' })).toBeVisible()
    await expect(page.getByText('1 contribution ($4,500.00) and 1 withdrawal ($500.00) counted toward your 2026 TFSA.', { exact: false })).toBeVisible()
    await expect(page.getByText("2 lines of growth, fees, trades or transfers don't use room.", { exact: false })).toBeVisible()
    await expect(page.getByText('Enter your 2026 TFSA room from CRA My Account', { exact: false })).toBeVisible()
    await page.getByRole('link', { name: 'Open registered accounts' }).click()
    await expect(page.getByRole('heading', { name: 'Registered accounts', level: 1 })).toBeVisible()
    const card = page.getByRole('article', { name: 'TFSA 2026' })
    await expect(card.getByText('Room not entered yet')).toBeVisible()
    await expect(card.getByText(accountName, { exact: false })).toBeVisible()
  })

  for (const theme of ['light', 'dark']) {
    test(`axe finds nothing serious on /plans with imported lines (${theme})`, async ({ page }) => {
      await page.addInitScript((th) => localStorage.setItem('fv.theme', JSON.stringify(th)), theme)
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.goto('/plans')
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      const card = page.getByRole('article', { name: 'TFSA 2026' })
      await expect(card).toBeVisible()
      await card.locator('details.entries summary').click()
      await expect(card.getByText(`Contribution ${tag}`)).toBeVisible()
      await page.waitForLoadState('networkidle')
      expect(await scan(page)).toEqual([])
    })
  }

  test('entering the CRA room shows what is left and an estimate for next year', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' }) // the dialog's pop-in fade would read as low contrast
    await page.goto('/plans')
    const card = page.getByRole('article', { name: 'TFSA 2026' })
    await card.getByRole('button', { name: 'Enter CRA room' }).click()
    const dialog = page.getByRole('dialog', { name: 'Edit room' })
    await dialog.getByLabel('Room from CRA').fill('20000')
    expect(await scan(page, '[role="dialog"]')).toEqual([])
    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(card.getByText('room left')).toBeVisible()
    await expect(card.getByText('Estimate', { exact: true })).toBeVisible()
    await expect(card.getByText("An estimate from the lines FinVault has seen. CRA's figure always wins.")).toBeVisible()
  })
})
