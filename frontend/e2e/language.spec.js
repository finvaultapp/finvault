import { expect, test } from '@playwright/test'

test('switch the language to French and back', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Settings' }).click()

  await page.getByLabel('Language').selectOption('fr')
  await expect(page.getByRole('link', { name: 'Paramètres' })).toBeVisible()
  await expect(page.getByLabel('Langue')).toHaveValue('fr')

  await page.getByLabel('Langue').selectOption('en')
  await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible()
  await expect(page.getByLabel('Language')).toHaveValue('en')
})
