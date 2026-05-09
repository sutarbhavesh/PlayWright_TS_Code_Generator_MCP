# 🎭 Playwright Code Generator — Semantic Locator Strategy

## Overview

This MCP (Model Context Protocol) server generates **production-ready Playwright TypeScript test code** with a **semantic locator strategy**. All locators follow Playwright best practices, prioritizing accessible role-based selectors over brittle CSS or XPath.

**Key Customization**: This workspace is configured to **use semantic locators** in this priority order:
1. `getByRole()` — BEST
2. `getByText()` — GOOD
3. `getByLabel()` — GOOD
4. `getByTestId()` — GOOD
5. `locator('.css-class')` — OK (fallback only)

---

## 🎯 Locator Priority & When to Use

| Strategy | Syntax | When to Use | Reliability |
|----------|--------|------------|-------------|
| **getByRole** | `getByRole('button', { name: 'Next' })` | Buttons, links, headings (semantic elements) | ⭐⭐⭐⭐⭐ BEST |
| **getByText** | `getByText('Next')` | Find visible text anywhere | ⭐⭐⭐⭐ Good |
| **getByLabel** | `getByLabel('Email')` | Form inputs with `<label>` | ⭐⭐⭐⭐ Good |
| **getByTestId** | `getByTestId('next-btn')` | When `data-testid` exists | ⭐⭐⭐⭐ Good |
| **CSS locator** | `locator('.next-button')` | Only if semantic fails | ⭐⭐ OK |
| **XPath** | `locator('//button')` | ❌ AVOID - brittle, unmaintainable | ⭐ Worst |

---

## 🚀 How to Use

### 1. Capture a Snapshot

Tell the agent to capture an accessibility snapshot of your target page:

```
/playwright_code_generator capture a snapshot of https://myapp.com/register
```

This creates a snapshot file (e.g., `register.md`) that documents the page structure.

### 2. Generate Code

Use the snapshot to generate Playwright test code:

```
/playwright_code_generator use register.md — write code to fill the form and click submit
```

### 3. Run Your Test

All generated locators will use semantic strategies:

```typescript
// Input field - uses getByLabel (best for forms with labels)
await page.getByLabel('Email').fill('test@example.com');

// Button - uses getByRole (works even with nested HTML)
await page.getByRole('button', { name: 'Submit' }).click();

// Heading - uses getByRole with level
await expect(page.getByRole('heading', { level: 1 })).toContainText('Welcome');
```

---

## 📋 Generated Locator Examples

### Form Input with Label
```typescript
// HTML
<label for="email">Email</label>
<input id="email" type="email" />

// Generated locator
page.getByLabel('Email')
```

### Button with Nested Elements
```typescript
// HTML
<button>
  <span>Submit</span>
  <span>→</span>
</button>

// Generated locator (getByRole finds it!)
page.getByRole('button', { name: 'Submit' })

// ✅ Works! getByRole finds the button even with nested HTML
// ❌ XPath would be: //button[contains(., 'Submit')]
```

### Fallback: CSS Selector
```typescript
// If no semantic attributes available
page.locator('.submit-button')

// ⚠️ Only if getByRole/getByLabel fail!
```

---

## 🔧 Configuration

### Current Settings

- **Locator Strategy**: Semantic (getByRole → getByText → getByLabel)
- **Snapshot Format**: Accessibility tree (.md + .html)
- **Test Style**: Raw tests, POM classes, or full suites based on complexity
- **Data Generation**: Faker.js for realistic test values
- **Assertions**: Automatic `expect()` statements

### Switching Back to XPath (Not Recommended)

To revert to XPath locators:

1. Open `server.py`
2. Find the `_best_locator()` function (line ~855)
3. Change the return statement:

```python
# Current (semantic)
return f"page.getByLabel('{label}')"

# Back to XPath (not recommended)
return f"page.locator(\"//input[@aria-label='{label}']\")"
```

---

## 📁 Workspace Structure

```
playwrightTsDev/
├── server.py                    # MCP server (semantic locators)
├── mcp_config.json             # MCP server configuration
├── SKILL.md                    # This file
├── README.md                   # Feature documentation
├── testing/
│   └── gmail-login.spec.ts    # Generated test with semantic locators
├── *.spec.ts                   # Generated Playwright test files
├── *-snapshot.md              # Saved page snapshots
└── pyproject.toml             # Python project config
```

---

## ✅ Best Practices

1. **Always try getByRole first** — works with semantic HTML and ARIA
2. **Use getByLabel for forms** — matches `<label>` elements
3. **Fallback to getByText** — finds visible text anywhere
4. **Use getByTestId last** — only if semantic fails and you control the code
5. **Never use XPath** — unless absolutely forced to by legacy code

### Why Semantic Locators?

- ✅ **Resilient**: Work even if HTML structure changes
- ✅ **Accessible**: Align with how screen readers work
- ✅ **Maintainable**: Easy to read and understand
- ✅ **Fast**: Playwright optimizes these strategies
- ❌ XPath is fragile and hard to maintain

---

## 📝 Example Workflow

### Step 1: Capture
```
/playwright_code_generator capture a snapshot of https://example.com/login
```

Output: `login-snapshot.md`

### Step 2: Generate
```
/playwright_code_generator use login-snapshot.md — generate code to log in
```

### Generated Code
```typescript
import { test, expect } from '@playwright/test';

test('logs in successfully', async ({ page }) => {
  await page.goto('https://example.com/login');

  // ✅ Semantic locators - works even if HTML changes
  await page.getByLabel('Email').fill('test@example.com');
  await page.getByLabel('Password').fill('password123');
  await page.getByRole('button', { name: 'Login' }).click();

  // Verify redirect
  await expect(page).toHaveURL('/dashboard');
});
```

---

## 🐛 Troubleshooting

### "Element not found"
1. Check if the element has accessible attributes (role, aria-label, label)
2. Try `getByText()` if the element has visible text
3. Inspect HTML to see if `data-testid` exists
4. Last resort: use CSS selector

### Button not clicking?
```typescript
// ✅ CORRECT - finds button by visible text
await page.getByRole('button', { name: 'Submit' }).click();

// ❌ WRONG - too specific
await page.locator("//button[@class='btn-primary']").click();
```

### Form input not filling?
```typescript
// ✅ CORRECT - uses label association
await page.getByLabel('Email').fill('test@example.com');

// ❌ WRONG - relies on naming conventions
await page.locator("input[name='email']").fill('test@example.com');
```

---

## 📚 Resources

- [Playwright Locators Guide](https://playwright.dev/docs/locators)
- [ARIA Accessibility](https://www.w3.org/WAI/ARIA/)
- [Testing Library Philosophy](https://testing-library.com/docs/queries/about)
- [MCP Protocol](https://modelcontextprotocol.io/)

---

**Last Updated**: May 7, 2026  
**Version**: 2.0.0 — Semantic Locator Strategy
