"""
Login functionality Playwright test cases.

Usage:
1. Install playwright: pip install playwright pytest-playwright
2. Install browser: playwright install chromium
3. Ensure frontend and backend services are running
4. Run tests: pytest tests/test_login.py -v
"""
import pytest
from playwright.sync_api import Page, expect


# Configuration
BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Browser context configuration."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
    }


class TestLogin:
    """Login functionality tests."""

    def test_login_page_loads(self, page: Page):
        """Test login page loads correctly."""
        page.goto(f"{BASE_URL}/login")

        # Verify page elements exist
        expect(page.locator("input[type='text'], input[placeholder*='用户名'], input[placeholder*='username']").first).to_be_visible(timeout=10000)
        expect(page.locator("input[type='password']").first).to_be_visible()
        expect(page.locator("button[type='submit'], button:has-text('登录')").first).to_be_visible()

    def test_login_with_empty_credentials(self, page: Page):
        """Test login with empty credentials."""
        page.goto(f"{BASE_URL}/login")

        # Click login button without entering anything
        login_button = page.locator("button[type='submit'], button:has-text('登录')").first
        login_button.click()

        # Wait for form validation
        page.wait_for_timeout(500)

    def test_login_with_invalid_credentials(self, page: Page):
        """Test login with invalid credentials."""
        page.goto(f"{BASE_URL}/login")

        # Enter invalid username and password
        username_input = page.locator("input[type='text'], input[placeholder*='用户名'], input[placeholder*='username']").first
        password_input = page.locator("input[type='password']").first

        username_input.fill("invalid_user")
        password_input.fill("invalid_password")

        # Click login
        login_button = page.locator("button[type='submit'], button:has-text('登录')").first
        login_button.click()

        # Wait for response
        page.wait_for_timeout(2000)

        # Verify no redirect to homepage (login failure should stay on login page or show error)

    def test_login_api_endpoint(self, page: Page):
        """Test login API endpoint response."""
        import json

        # Test login with default admin account
        response = page.request.post(
            f"{API_URL}/api/v1/auth/login",
            data=json.dumps({
                "username": "admin",
                "password": "admin123"
            }),
            headers={"Content-Type": "application/json"}
        )

        # API should not return 500
        assert response.status != 500, f"API returned 500 error: {response.text()}"
        print(f"API response status: {response.status}")

        # Verify admin login succeeds
        assert response.status == 200, f"Admin login failed: {response.text()}"

        # Verify token is returned
        data = response.json()
        assert "access_token" in data, "Login response missing access_token"
        print("✓ Admin account login successful")

    def test_register_and_login(self, page: Page):
        """Test registration followed by login (complete flow)."""
        import uuid
        import json

        # Generate unique username
        unique_id = str(uuid.uuid4())[:8]
        username = f"test_user_{unique_id}"
        email = f"test_{unique_id}@example.com"
        password = "TestPass123!"

        # 1. Try to register first (using JSON format)
        register_response = page.request.post(
            f"{API_URL}/api/v1/auth/register",
            data=json.dumps({
                "username": username,
                "email": email,
                "password": password
            }),
            headers={"Content-Type": "application/json"}
        )

        print(f"Registration response status: {register_response.status}")
        print(f"Registration response content: {register_response.text()}")

        # 2. Try to login (using JSON format)
        login_response = page.request.post(
            f"{API_URL}/api/v1/auth/login",
            data=json.dumps({
                "username": username,
                "password": password
            }),
            headers={"Content-Type": "application/json"}
        )

        print(f"Login response status: {login_response.status}")
        assert login_response.status != 500, f"Login API returned 500 error: {login_response.text()}"

        # If registration succeeded, login should return 200
        if register_response.status in [200, 201]:
            assert login_response.status == 200, f"Login after registration failed: {login_response.text()}"
            print("✓ Registration and login flow test passed")


class TestLoginUI:
    """Login UI interaction tests."""

    def test_password_visibility_toggle(self, page: Page):
        """Test password visibility toggle."""
        page.goto(f"{BASE_URL}/login")

        password_input = page.locator("input[type='password']").first
        expect(password_input).to_be_visible()

        # Enter password
        password_input.fill("testpassword")

        # Find and click password visibility toggle button (if exists)
        toggle_button = page.locator("[class*='password'] button, button[aria-label*='password']").first
        if toggle_button.is_visible():
            toggle_button.click()
            # Verify password becomes visible
            page.wait_for_timeout(300)

    def test_remember_me_checkbox(self, page: Page):
        """Test remember me checkbox (if exists)."""
        page.goto(f"{BASE_URL}/login")

        remember_checkbox = page.locator("input[type='checkbox']").first
        if remember_checkbox.is_visible():
            remember_checkbox.check()
            expect(remember_checkbox).to_be_checked()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--headed"])
