import { expect, test } from '@playwright/test'
import { installApiFixture, login } from './fixtures'

test('administrator can sign in and open user management', async ({ page }) => {
  await installApiFixture(page, {
    id: 1,
    username: 'admin',
    is_active: true,
    is_admin: true,
    created_at: '2026-07-13T08:00:00',
  })
  await login(page)
  await page.goto('/users')
  await expect(page.locator('.page-title', { hasText: '用户管理' })).toBeVisible()
  await expect(page.getByText('viewer', { exact: true }).filter({ visible: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '新增用户' })).toBeVisible()
})

test('ordinary users are redirected away from user management', async ({ page }) => {
  await installApiFixture(page, {
    id: 2,
    username: 'viewer',
    is_active: true,
    is_admin: false,
    created_at: '2026-07-13T09:00:00',
  })
  await login(page)
  await page.goto('/users')
  await expect(page).toHaveURL(/\/dashboard$/)
})

test('default password users are forced into their profile', async ({ page }) => {
  await installApiFixture(page, {
    id: 1,
    username: 'admin',
    is_active: true,
    is_admin: true,
    is_default_password: true,
    created_at: '2026-07-13T08:00:00',
  })
  await login(page)
  await expect(page).toHaveURL(/\/profile$/)
  await expect(page.locator('.page-title', { hasText: '用户中心' })).toBeVisible()
})
