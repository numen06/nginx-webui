import type { Page, Route } from '@playwright/test'

export interface FixtureUser {
  id: number
  username: string
  is_active: boolean
  is_admin: boolean
  created_at: string
  is_default_password?: boolean
}

export async function installApiFixture(page: Page, user: FixtureUser) {
  const users = [user, {
    id: 2,
    username: 'viewer',
    is_active: true,
    is_admin: false,
    created_at: '2026-07-13T09:00:00',
  }]

  await page.route(url => url.pathname.startsWith('/api/'), async (route: Route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let body: unknown = { success: true }

    if (path.endsWith('/auth/login')) {
      body = { access_token: 'fixture-token', token_type: 'bearer', username: user.username, expires_in: 3600 }
    } else if (path.endsWith('/auth/me')) {
      body = { success: true, user }
    } else if (path === '/api/users/' && route.request().method() === 'GET') {
      body = { success: true, users, total: users.length }
    } else if (path.endsWith('/nginx/setup/check')) {
      body = { has_compiled_nginx: true, has_default_tar: true }
    } else if (path.endsWith('/system/version/check-update')) {
      body = { success: true, has_update: false, current_version: '1.0.3' }
    } else if (path.endsWith('/system/version')) {
      body = { version: '1.0.3' }
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
}

export async function login(page: Page) {
  await page.goto('/')
  await page.evaluate(() => localStorage.clear())
  await page.goto('/login')
  await page.locator('#username').fill('admin')
  await page.locator('#password').fill('fixture-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.waitForURL(url => url.pathname !== '/login')
}
