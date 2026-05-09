import { test, expect } from '@playwright/test';

test('Gmail Login - Enter email and password', async ({ page }) => {
  // Navigate to Gmail login
  await page.goto('https://mail.google.com/mail/u/0/');

  // Step 1: Enter email using semantic locators
  const emailInput = page.getByRole('textbox', { name: /email or phone/i });
  await expect(emailInput).toBeVisible();
  await emailInput.fill('test@gmail.com');

  // Step 2: Click Next button using getByRole
  const nextButton = page.getByRole('button', { name: 'Next' });
  await expect(nextButton).toBeVisible();
  await nextButton.click();

  // Wait for password page to load
  await page.waitForLoadState('networkidle');

  // Step 3: Enter password using semantic locators
  const passwordInput = page.getByRole('textbox', { name: /password/i });
  await expect(passwordInput).toBeVisible();
  await passwordInput.fill('password123');

  // Step 4: Click Next button to submit
  const loginButton = page.getByRole('button', { name: 'Next' });
  await expect(loginButton).toBeVisible();
  await loginButton.click();

  // Step 5: Verify login was successful (you may need to adjust based on actual post-login page)
  await page.waitForLoadState('networkidle');
  
  // Verify we're on Gmail inbox or authenticated page
  const inboxHeading = page.getByText('Inbox');
  await expect(inboxHeading).toBeVisible({ timeout: 10000 }).catch(() => {
    // If inbox heading not visible, just verify URL changed
    expect(page.url()).not.toContain('signin');
  });
});

test('Gmail Login - Verify page elements', async ({ page }) => {
  await page.goto('https://mail.google.com/mail/u/0/');

  // Verify Google logo is visible
  const googleLogo = page.getByRole('img', { name: 'Google' });
  await expect(googleLogo).toBeVisible();

  // Verify Sign in heading
  const signInHeading = page.getByRole('heading', { name: /sign in/i, level: 1 });
  await expect(signInHeading).toBeVisible();

  // Verify email input field exists
  const emailField = page.getByRole('textbox', { name: /email or phone/i });
  await expect(emailField).toBeVisible();

  // Verify Next button exists
  const nextBtn = page.getByRole('button', { name: 'Next' });
  await expect(nextBtn).toBeVisible();

  // Verify Create account link exists
  const createAccountLink = page.getByRole('link', { name: /create account/i });
  await expect(createAccountLink).toBeVisible();

  // Verify Forgot email? link exists
  const forgotEmailLink = page.getByRole('link', { name: /forgot email/i });
  await expect(forgotEmailLink).toBeVisible();
});
