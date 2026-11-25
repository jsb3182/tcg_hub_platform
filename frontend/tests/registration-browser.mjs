// Run against a disposable loopback Spring database with a published YUGIOH card named 달빛 연습 카드.
// REGISTRATION_QA_ORIGIN, PLAYWRIGHT_MODULE and CHROME_PATH select the test server and browser.
import assert from 'node:assert/strict'
import { randomBytes, randomUUID } from 'node:crypto'
import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'

const base = new URL(process.env.REGISTRATION_QA_ORIGIN)
assert.equal(base.hostname, '127.0.0.1')
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined })
const password = ' ' + randomBytes(18).toString('hex') + '한 '
const suffix = randomUUID() + '@example.invalid'
const cardName = '달빛 연습 카드'
try {
  const context = await browser.newContext({ viewport: { width: 360, height: 800 }, deviceScaleFactor: 1,
    isMobile: true, hasTouch: true, locale: 'ko-KR', serviceWorkers: 'block' })
  await context.route('**/*', route => new URL(route.request().url()).origin === base.origin ? route.continue() : route.abort())
  const page = await context.newPage()
  page.setDefaultTimeout(9000)
  const pageErrors = []
  page.on('pageerror', e => pageErrors.push(e.name))
  const button = name => page.getByRole('button', { name, exact: true })
  const link = name => page.getByRole('link', { name, exact: true })
  const goto = path => page.goto(new URL(path, base).href)
  const email = page.getByLabel('이메일', { exact: true })
  const pass = page.getByLabel('비밀번호', { exact: true })
  const formAction = (method, path) => page.waitForResponse(r =>
    new URL(r.url()).pathname === '/api/v1/' + path && r.request().method() === method)
  async function signup(status) {
    const response = formAction('POST', 'auth/register')
    await button('회원가입').click()
    const result = await response
    assert.equal(result.status(), status)
    if (status === 201) assert.equal((await result.json()).role, 'ROLE_USER')
  }
  async function shot(name) {
    if (!process.env.QA_SCREENSHOTS) return
    await mkdir(process.env.QA_SCREENSHOTS, { recursive: true })
    await page.screenshot({ path: join(process.env.QA_SCREENSHOTS, name + '.png') })
  }

  await goto('/login?to=admin&mode=register')
  await page.getByRole('heading', { name: '관리자 로그인' }).waitFor()
  assert.equal(await link('회원가입').count(), 0)
  assert.equal(await button('회원가입').count(), 0)
  assert.equal(await pass.getAttribute('autocomplete'), 'current-password')
  await page.locator('.account-actions').getByRole('link', { name: '로그인' }).click()
  await page.getByRole('heading', { name: '관리자 로그인' }).waitFor()
  assert.equal(await link('회원가입').count(), 0)
  await goto('/binder')
  await link('회원가입').click()
  await page.getByRole('heading', { name: '회원가입' }).waitFor()
  assert.equal(new URL(page.url()).searchParams.get('next'), '/binder')
  assert.equal(await pass.getAttribute('autocomplete'), 'new-password')
  assert.equal(await page.title(), '회원가입 · TCG 허브')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 360)
  await shot('signup-360')
  await page.emulateMedia({ colorScheme: 'dark' })
  await shot('signup-dark-360')
  await page.emulateMedia({ colorScheme: 'light' })

  await email.fill('형식오류')
  await button('회원가입').click()
  await page.getByRole('alert').filter({ hasText: '이메일 주소' }).waitFor()
  assert.ok(await email.evaluate(el => el === document.activeElement))
  await email.fill('binder-' + suffix)
  await pass.fill('😃'.repeat(6))
  await button('회원가입').click()
  await page.getByRole('alert').filter({ hasText: '12자' }).waitFor()
  assert.ok(await pass.evaluate(el => el === document.activeElement))
  await pass.fill('한'.repeat(25))
  await button('회원가입').click()
  await page.getByRole('alert').filter({ hasText: '72바이트' }).waitFor()
  await pass.fill(password)
  await email.fill('fixture@invalid')
  await signup(400)
  await page.getByRole('alert').filter({ hasText: '이메일 주소와 비밀번호 조건' }).waitFor()
  await email.fill('binder-' + suffix)
  await page.route('**/api/v1/auth/register', route => route.fulfill({ status: 429, json: {} }), { times: 1 })
  await signup(429)
  await page.getByRole('alert').filter({ hasText: '잠시 뒤 다시 시도' }).waitFor()
  await signup(201)
  await page.waitForURL(url => url.pathname === '/binder')
  await button(cardName + ' 추가').click()
  await page.getByRole('dialog').getByRole('spinbutton').fill('2')
  await button('수량 저장').click()
  await page.getByText(cardName + ' 2장을 저장했습니다.').waitFor()
  const refresh = formAction('POST', 'auth/refresh')
  await page.reload()
  assert.equal((await refresh).status(), 200)
  await button(cardName + ' 수량 수정').waitFor()
  const cookie = (await context.cookies()).find(c => c.name === '__Secure-tcg_refresh')
  assert.ok(cookie?.httpOnly && cookie.secure && cookie.sameSite === 'Strict')
  await button('로그아웃').click()
  await link('회원가입').waitFor()

  const nextDeck = '/decks/new?game=YUGIOH&lang=en'
  await goto(nextDeck)
  await link('회원가입').click()
  await email.fill('binder-' + suffix)
  await pass.fill(password)
  await signup(409)
  await page.getByRole('alert').filter({ hasText: '이미 가입된 이메일' }).waitFor()
  assert.ok(await email.evaluate(el => el === document.activeElement))
  await email.fill('deck-' + suffix)
  await signup(201)
  await page.waitForURL(url => url.pathname + url.search === nextDeck)
  await page.getByLabel('덱 이름').fill('가입 검증 덱')
  await button(cardName + ' 추가').click()
  const save = formAction('POST', 'me/decks')
  await button('임시 저장').click()
  assert.equal((await save).status(), 201)
  await page.waitForURL(url => /^\/decks\/\d+$/.test(url.pathname))
  await button('로그아웃').click()
  await link('회원가입').waitFor()

  const nextPlay = '/play?game=POKEMON&lang=ja'
  await goto(nextPlay)
  await link('로그인').click()
  await link('회원가입').click()
  await email.fill('play-' + suffix)
  await pass.fill(password)
  await signup(201)
  await page.waitForURL(url => url.pathname + url.search === nextPlay)
  await page.getByRole('heading', { name: 'プレイ', exact: true }).waitFor()
  const logout = formAction('POST', 'auth/logout')
  await button('로그아웃').click()
  assert.equal((await logout).status(), 204)
  await link('로그인').click()
  await link('회원가입').click()
  await pass.fill('mode switch')
  await page.locator('.account-actions').getByRole('link', { name: '로그인' }).click()
  assert.equal(new URL(page.url()).searchParams.get('next'), nextPlay)
  assert.equal(await pass.inputValue(), '')
  assert.equal(await pass.getAttribute('autocomplete'), 'current-password')
  await email.fill('binder-' + suffix)
  await pass.fill(password)
  await button('로그인').click()
  await page.waitForURL(url => url.pathname + url.search === nextPlay)
  assert.deepEqual(pageErrors, [])
  console.log('360px Chrome: signup, validation, duplicate correction, rate-limit retry, refresh cookie, binder write, deck save, Japanese practice return, admin isolation and ordinary login passed.')
} finally {
  await browser.close()
}
