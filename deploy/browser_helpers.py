"""Shared UI checks; no credentials or drafts may be persisted in browser storage."""
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def dismiss_guide(page):
    try:
        page.get_by_role('button', name='跳过使用引导', exact=True).wait_for(timeout=2500)
    except PlaywrightTimeoutError:
        return
    page.get_by_role('button', name='跳过使用引导', exact=True).click()
    page.locator('.studio-guide').wait_for(state='detached')


def assert_safe_storage(page):
    assert page.evaluate('''sessionStorage.length === 0 && Object.keys(localStorage).every(
        key => key.startsWith('frame.guide.v1.') && localStorage.getItem(key) === 'seen'
    )'''), 'Only onboarding seen flags may be stored in the browser'
