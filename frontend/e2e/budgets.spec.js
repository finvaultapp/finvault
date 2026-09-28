import { expect, test } from '@playwright/test'

test('set a budget and see it on Budgets', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Budgets' }).click()
  await expect(page.getByRole('heading', { name: 'Budgets', level: 1 })).toBeVisible()

  await page.getByRole('button', { name: 'Set a budget' }).first().click()
  const dialog = page.getByRole('dialog', { name: 'Set a budget' })
  await dialog.getByLabel('Category').selectOption({ label: 'Health' })
  await dialog.getByLabel('Monthly limit').fill('175')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()

  await expect(page.getByRole('main').getByRole('link', { name: 'Health' })).toBeVisible()
  await expect(page.getByRole('button', { name: '$175.00' })).toBeVisible()
})
