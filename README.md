# PlayWright_TS_Code_Generator_MCP

## ✨ Features

| Feature | Detail |
|---|---|
|  Aria snapshot capture | Uses Playwright's accessibility tree — best for stable locators |
|  Agent-driven output | Auto-picks raw test, POM, or full suite based on page complexity |
|  Smart locators | Prefers `getByRole` → `getByLabel` → `getByPlaceholder` (Playwright best practice) |
|  Faker.js data | Generates realistic test data for every field type |
|  Built-in assertions | Adds `expect()` checks after every key action |
|  Screenshot hooks | Inserts `toHaveScreenshot()` at strategic points |
|  Clarification agent | Asks before generating when intent is ambiguous |
|  Snapshot diffing | Compare before/after states to understand multi-step flows |
|  Persistent snapshots | Save snapshots to disk, reuse across sessions |
