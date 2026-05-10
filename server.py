"""
Playwright Code Generator MCP Server
======================================
A world-class MCP server that captures accessibility snapshots of web pages
and generates production-ready Playwright TypeScript test code.

Transport: stdio (for VS Code Copilot / Claude Desktop)
Author   : Playwright Code Generator
"""

import asyncio
import json
import os
import re
import hashlib
import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

# ── Optional Playwright import (graceful if not installed) ──────────────────
try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
SNAPSHOT_DIR  = BASE_DIR / "snapshots"
OUTPUT_DIR    = BASE_DIR / "output"
SNAPSHOT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── MCP Server ───────────────────────────────────────────────────────────────
server = Server("playwright_code_generator")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOOL DEFINITIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="capture_snapshot",
            description=(
                "Capture an accessibility snapshot (aria tree) of any live web page. "
                "Returns a rich snapshot saved as both .html and .md that the agent "
                "reads to understand the page structure for code generation. "
                "Use this FIRST before generating any Playwright code."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL of the page to snapshot (e.g. https://example.com/register)"
                    },
                    "label": {
                        "type": "string",
                        "description": "Short label for the snapshot (e.g. 'register-page'). Used in filenames."
                    },
                    "wait_for": {
                        "type": "string",
                        "description": "Optional CSS selector to wait for before snapshotting (e.g. 'form#register')"
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full page screenshot alongside aria snapshot (default: false)",
                        "default": False
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="analyze_snapshot",
            description=(
                " Analyze a previously captured snapshot file to extract structured page intelligence: "
                "form fields, buttons, links, page type detection, and recommended locator strategies. "
                "Feed the snapshot filename (or raw snapshot text) to get a structured analysis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "snapshot_file": {
                        "type": "string",
                        "description": "Filename of a saved snapshot (e.g. 'register-page.md') OR raw snapshot text"
                    }
                },
                "required": ["snapshot_file"]
            }
        ),
        Tool(
            name="generate_code",
            description=(
                " Generate production-ready Playwright TypeScript code from a snapshot. "
                "The agent automatically chooses output style based on complexity:\n"
                "  Simple page  → raw test.ts with inline locators\n"
                "  Multi-step   → Page Object Model class + test file\n"
                "  Complex suite → POM + fixtures + test data helpers\n"
                "Includes best-fit locators, Faker.js data, assertions, waits, and Allure annotations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "snapshot_file": {
                        "type": "string",
                        "description": "Snapshot filename or raw snapshot text to generate code from"
                    },
                    "instruction": {
                        "type": "string",
                        "description": "Natural language instruction (e.g. 'fill all contact details and click register')"
                    },
                    "output_style": {
                        "type": "string",
                        "enum": ["auto", "raw_test", "pom", "full_suite"],
                        "description": "Force a specific output style (default: auto — agent decides)",
                        "default": "auto"
                    },
                    "test_type": {
                        "type": "string",
                        "enum": ["happy_path", "negative", "smoke", "regression", "e2e"],
                        "description": "Type of test to generate (default: happy_path)",
                        "default": "happy_path"
                    },
                    "include_assertions": {
                        "type": "boolean",
                        "description": "Add expect() assertions after each key action (default: true)",
                        "default": True
                    },
                    "use_faker": {
                        "type": "boolean",
                        "description": "Use @faker-js/faker for test data generation (default: true)",
                        "default": True
                    }
                },
                "required": ["snapshot_file", "instruction"]
            }
        ),
        Tool(
            name="clarify_intent",
            description=(
                "Ask the user a clarifying question before generating code. "
                "Use this when the snapshot reveals ambiguity — multiple forms, unclear flow, "
                "conditional steps, or missing context. Returns the question to show the user."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The clarifying question to ask the user"
                    },
                    "context": {
                        "type": "string",
                        "description": "Brief context about what was found in the snapshot"
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of choices to present to the user"
                    }
                },
                "required": ["question"]
            }
        ),
        Tool(
            name="diff_snapshots",
            description=(
                "Compare two snapshots to detect what changed between page states. "
                "Useful for multi-step flows — capture before and after an action "
                "to understand what DOM elements appeared, changed, or disappeared."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "snapshot_before": {
                        "type": "string",
                        "description": "Filename or text of the BEFORE snapshot"
                    },
                    "snapshot_after": {
                        "type": "string",
                        "description": "Filename or text of the AFTER snapshot"
                    }
                },
                "required": ["snapshot_before", "snapshot_after"]
            }
        ),
        Tool(
            name="save_snapshot",
            description=(
                " Save raw snapshot text (aria tree or HTML) to disk as .md and .html files. "
                "Use this when you already have snapshot content (e.g. pasted from browser devtools) "
                "and want to save it for repeated analysis without re-opening the browser."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Raw snapshot content (aria tree text or HTML)"
                    },
                    "label": {
                        "type": "string",
                        "description": "Label for the saved file (e.g. 'checkout-page')"
                    }
                },
                "required": ["content", "label"]
            }
        ),
        Tool(
            name="list_snapshots",
            description=(
                "List all saved snapshots in the snapshots directory. "
                "Returns filenames, sizes, and creation times."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
    ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOOL HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    try:
        if name == "capture_snapshot":
            result = await handle_capture_snapshot(arguments)
        elif name == "analyze_snapshot":
            result = await handle_analyze_snapshot(arguments)
        elif name == "generate_code":
            result = await handle_generate_code(arguments)
        elif name == "clarify_intent":
            result = await handle_clarify_intent(arguments)
        elif name == "diff_snapshots":
            result = await handle_diff_snapshots(arguments)
        elif name == "save_snapshot":
            result = await handle_save_snapshot(arguments)
        elif name == "list_snapshots":
            result = await handle_list_snapshots(arguments)
        else:
            result = f" Unknown tool: {name}"

        return CallToolResult(content=[TextContent(type="text", text=result)])

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f" Error in {name}: {str(e)}")],
            isError=True
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER: capture_snapshot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_capture_snapshot(args: dict) -> str:
    url       = args["url"]
    label     = args.get("label") or _slug(url)
    wait_for  = args.get("wait_for")
    full_page = args.get("full_page", False)

    if not PLAYWRIGHT_AVAILABLE:
        return _mock_snapshot(url, label)

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=True)
        try:
            page: Page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30_000)

            if wait_for:
                await page.wait_for_selector(wait_for, timeout=10_000)

            # Accessibility / aria snapshot
            snapshot_text = await page.accessibility.snapshot()
            aria_md = _aria_to_markdown(snapshot_text, url)

            # Also grab raw HTML (stripped)
            html = await page.content()

            # Screenshot
            screenshot_path = None
            if full_page:
                screenshot_path = SNAPSHOT_DIR / f"{label}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)

        finally:
            await browser.close()

    # Persist files
    md_path   = SNAPSHOT_DIR / f"{label}.md"
    html_path = SNAPSHOT_DIR / f"{label}.html"
    md_path.write_text(aria_md, encoding="utf-8")
    html_path.write_text(html,  encoding="utf-8")

    result = (
        f" Snapshot captured for: {url}\n\n"
        f" Saved files:\n"
        f"  {md_path.name}  ({md_path.stat().st_size:,} bytes)\n"
        f"  {html_path.name} ({html_path.stat().st_size:,} bytes)\n"
    )
    if screenshot_path:
        result += f"  • {screenshot_path.name}\n"

    result += f"\n---\n\n{aria_md}"
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER: analyze_snapshot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_analyze_snapshot(args: dict) -> str:
    content = _load_snapshot_content(args["snapshot_file"])
    analysis = _analyze_content(content)

    lines = [
        "##  Page Analysis\n",
        f"**Page type detected:** {analysis['page_type']}",
        f"**Complexity:** {analysis['complexity']}",
        f"**Recommended output:** {analysis['recommended_output']}\n",
        "###  Form Fields",
    ]
    if analysis["form_fields"]:
        for f in analysis["form_fields"]:
            lines.append(f"  - `{f['locator']}` — {f['type']} — label: \"{f['label']}\"")
    else:
        lines.append("  *(no form fields detected)*")

    lines.append("\n###  Actionable Buttons")
    if analysis["buttons"]:
        for b in analysis["buttons"]:
            lines.append(f"  - `{b['locator']}` — \"{b['text']}\"")
    else:
        lines.append("  *(no buttons detected)*")

    lines.append("\n###  Navigation Links")
    if analysis["links"]:
        for lnk in analysis["links"][:10]:
            lines.append(f"  - \"{lnk['text']}\"")
    else:
        lines.append("  *(no nav links detected)*")

    lines.append("\n###  Locator Strategy Recommendations")
    for tip in analysis["locator_tips"]:
        lines.append(f"  - {tip}")

    if analysis["clarifications_needed"]:
        lines.append("\n###  Clarifications Needed")
        for q in analysis["clarifications_needed"]:
            lines.append(f"  - {q}")

    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER: generate_code
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_generate_code(args: dict) -> str:
    content      = _load_snapshot_content(args["snapshot_file"])
    instruction  = args["instruction"]
    output_style = args.get("output_style", "auto")
    test_type    = args.get("test_type", "happy_path")
    with_asserts = args.get("include_assertions", True)
    use_faker    = args.get("use_faker", True)

    analysis = _analyze_content(content)

    # Auto-decide output style
    if output_style == "auto":
        output_style = analysis["recommended_output"]

    # Route to generator
    if output_style == "raw_test":
        code = _gen_raw_test(analysis, instruction, test_type, with_asserts, use_faker)
    elif output_style == "pom":
        code = _gen_pom(analysis, instruction, test_type, with_asserts, use_faker)
    else:
        code = _gen_full_suite(analysis, instruction, test_type, with_asserts, use_faker)

    # Save to output dir
    ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = OUTPUT_DIR / f"{_slug(instruction)}_{ts}.ts"
    out_file.write_text(code, encoding="utf-8")

    result = (
        f"##  Generated: `{output_style}` ({test_type})\n\n"
        f" Saved to: `output/{out_file.name}`\n\n"
        f"```typescript\n{code}\n```"
    )
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER: clarify_intent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_clarify_intent(args: dict) -> str:
    question = args["question"]
    context  = args.get("context", "")
    options  = args.get("options", [])

    lines = ["##  Clarification Needed\n"]
    if context:
        lines.append(f"**Context:** {context}\n")
    lines.append(f"**Question:** {question}\n")
    if options:
        lines.append("**Options:**")
        for i, opt in enumerate(options, 1):
            lines.append(f"  {i}. {opt}")
    lines.append("\n*Please reply and I'll generate the code right away!*")
    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER: diff_snapshots
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_diff_snapshots(args: dict) -> str:
    before = _load_snapshot_content(args["snapshot_before"])
    after  = _load_snapshot_content(args["snapshot_after"])

    before_lines = set(before.splitlines())
    after_lines  = set(after.splitlines())

    added   = [l for l in after_lines  - before_lines if l.strip()]
    removed = [l for l in before_lines - after_lines  if l.strip()]

    lines = ["##  Snapshot Diff\n"]
    lines.append(f"**Added elements** ({len(added)}):")
    for l in added[:20]:
        lines.append(f"  + {l.strip()}")
    if len(added) > 20:
        lines.append(f"  ... and {len(added)-20} more")

    lines.append(f"\n**Removed elements** ({len(removed)}):")
    for l in removed[:20]:
        lines.append(f"  - {l.strip()}")
    if len(removed) > 20:
        lines.append(f"  ... and {len(removed)-20} more")

    if not added and not removed:
        lines.append("  *(No differences found — pages appear identical)*")

    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER: save_snapshot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_save_snapshot(args: dict) -> str:
    content = args["content"]
    label   = args["label"]
    slug    = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")

    md_path   = SNAPSHOT_DIR / f"{slug}.md"
    html_path = SNAPSHOT_DIR / f"{slug}.html"

    md_path.write_text(content, encoding="utf-8")

    # Wrap in basic HTML if not already HTML
    if not content.strip().startswith("<"):
        html_wrap = f"<html><body><pre>{content}</pre></body></html>"
    else:
        html_wrap = content
    html_path.write_text(html_wrap, encoding="utf-8")

    return (
        f" Snapshot saved as `{slug}`\n"
        f"   {md_path}\n"
        f"   {html_path}\n\n"
        f"Use `analyze_snapshot` with `\"{slug}.md\"` to analyse it."
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER: list_snapshots
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_list_snapshots(_args: dict) -> str:
    files = sorted(SNAPSHOT_DIR.glob("*.md"))
    if not files:
        return " No snapshots saved yet. Use `capture_snapshot` or `save_snapshot` to create one."

    lines = [f"##  Saved Snapshots ({len(files)} found)\n"]
    for f in files:
        stat = f.stat()
        ts   = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"  • `{f.name}` — {stat.st_size:,} bytes — {ts}")
    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANALYSIS ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _analyze_content(content: str) -> dict:
    """
    Parse aria/html snapshot text and extract structured intelligence
    for code generation.
    """
    cl = content.lower()

    # ── Form fields ────────────────────────────────────────────────────────
    field_patterns = [
        (r'textbox["\s]+(?:name|label)["\s]*[=:]+\s*["\']([^"\']+)', "text"),
        (r'(?:name|label|placeholder)["\s]*[=:]+\s*["\']([^"\']+)["\'].*?(?:type=["\']?(text|email|password|tel|number|date))', "text"),
        (r'(?:input|textbox).*?(?:name|id|placeholder)[="\s]+["\']([^"\']+)', "text"),
    ]
    form_fields = []

    # Heuristic: detect common field labels in snapshot
    common_fields = [
        ("first.?name|given.?name|first name", "text", "First Name"),
        ("last.?name|surname|family.?name", "text", "Last Name"),
        ("email|e-mail", "email", "Email"),
        ("phone|mobile|telephone|contact.?no", "tel", "Phone"),
        ("password|passwd", "password", "Password"),
        ("confirm.?password|repeat.?password|retype", "password", "Confirm Password"),
        ("address|street", "text", "Address"),
        ("city|town", "text", "City"),
        ("state|province|region", "text", "State"),
        ("zip|postal|pincode|postcode", "text", "Zip Code"),
        ("country", "select", "Country"),
        ("dob|date.?of.?birth|birth.?date", "date", "Date of Birth"),
        ("gender|sex", "select", "Gender"),
        ("username|user.?name|login", "text", "Username"),
        ("company|organization|employer", "text", "Company"),
        ("website|url", "url", "Website"),
    ]
    for pattern, ftype, label in common_fields:
        if re.search(pattern, cl):
            locator = _best_locator(label)
            form_fields.append({"label": label, "type": ftype, "locator": locator})

    # ── Buttons ────────────────────────────────────────────────────────────
    btn_patterns = [
        r'button["\s]+(?:name|label)["\s]*[=:]+\s*["\']([^"\']+)',
        r'(?:submit|button).*?(?:value|name|label)[="\s]+["\']([^"\']{2,40})',
    ]
    buttons = []
    common_buttons = [
        ("register|sign.?up|create.?account", "Register"),
        ("login|sign.?in|log.?in", "Login"),
        ("submit|send|continue|proceed", "Submit"),
        ("cancel|back|close", "Cancel"),
        ("next|forward", "Next"),
        ("save|update|confirm", "Save"),
        ("search|find|look.?up", "Search"),
        ("add.?to.?cart|buy.?now|purchase", "Add to Cart"),
        ("checkout|place.?order", "Checkout"),
    ]
    for pattern, label in common_buttons:
        if re.search(pattern, cl):
            buttons.append({
                "text": label,
                "locator": f"page.getByRole('button', {{ name: '{label}' }})"
            })

    # ── Links ──────────────────────────────────────────────────────────────
    links = []
    for m in re.finditer(r'link["\s]+(?:name|label)["\s]*[=:]+\s*["\']([^"\']+)', content, re.I):
        links.append({"text": m.group(1)})

    # ── Page type ──────────────────────────────────────────────────────────
    page_type = "generic"
    if re.search(r"register|sign.?up|create.?account", cl):
        page_type = "registration"
    elif re.search(r"login|sign.?in|log.?in", cl):
        page_type = "login"
    elif re.search(r"checkout|payment|billing", cl):
        page_type = "checkout"
    elif re.search(r"search|filter|sort", cl):
        page_type = "search"
    elif re.search(r"contact|enquiry|feedback", cl):
        page_type = "contact_form"
    elif re.search(r"profile|account|settings", cl):
        page_type = "profile"
    elif re.search(r"dashboard|overview|analytics", cl):
        page_type = "dashboard"

    # ── Complexity → output style ──────────────────────────────────────────
    field_count = len(form_fields)
    if field_count <= 3 and len(buttons) <= 2:
        complexity = "simple"
        recommended = "raw_test"
    elif field_count <= 8:
        complexity = "medium"
        recommended = "pom"
    else:
        complexity = "complex"
        recommended = "full_suite"

    # ── Locator tips ───────────────────────────────────────────────────────
    locator_tips = [
        " getByRole('button', { name: 'Next' }) — BEST — works even if text is in nested <span>",
        " getByText('Next') — GOOD — finds visible text anywhere on page",
        " getByLabel('Email') — GOOD — for form inputs with associated label",
        " getByTestId('next-btn') — GOOD — if data-testid attribute exists",
        "  locator('.css-class') — OK — CSS selectors only as fallback",
        " Never use XPath unless absolutely necessary — brittle and unmaintainable",
    ]
    if any(f["type"] == "password" for f in form_fields):
        locator_tips.append(" Use `page.getByLabel('Password')` — don't use type=password selector")

    # ── Clarifications ─────────────────────────────────────────────────────
    clarifications_needed = []
    if field_count == 0 and "form" not in cl:
        clarifications_needed.append("No form fields detected — is this the correct page URL?")
    if len(buttons) > 3:
        clarifications_needed.append(f"Multiple buttons found ({len(buttons)}) — which one should be the final action?")

    return {
        "page_type":            page_type,
        "complexity":           complexity,
        "recommended_output":   recommended,
        "form_fields":          form_fields,
        "buttons":              buttons,
        "links":                links,
        "locator_tips":         locator_tips,
        "clarifications_needed": clarifications_needed,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CODE GENERATORS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _gen_raw_test(analysis: dict, instruction: str, test_type: str,
                  with_asserts: bool, use_faker: bool) -> str:
    fields  = analysis["form_fields"]
    buttons = analysis["buttons"]
    pt      = analysis["page_type"]

    faker_import = "import { faker } from '@faker-js/faker';\n" if use_faker else ""
    faker_data   = _faker_data_block(fields) if use_faker else _static_data_block(fields)
    fill_actions = _gen_fill_actions(fields, use_faker)
    btn_action   = _gen_button_action(buttons)
    assertions   = _gen_assertions(pt, analysis) if with_asserts else ""

    return f"""import {{ test, expect }} from '@playwright/test';
{faker_import}
/**
 * Test: {instruction}
 * Page: {pt}
 * Type: {test_type}
 * Generated by: playwright_code_generator MCP
 */
test.describe('{_title(pt)} — {test_type.replace("_", " ").title()}', () => {{

  test('{instruction}', async ({{ page }}) => {{
    // ── Test data ──────────────────────────────────────────────────────────
{faker_data}

    // ── Navigate ───────────────────────────────────────────────────────────
    await page.goto('/');   //  Replace with your actual URL

    // ── Fill form ──────────────────────────────────────────────────────────
{fill_actions}

    // ── Submit ─────────────────────────────────────────────────────────────
{btn_action}
{assertions}  }});
}});
"""


def _gen_pom(analysis: dict, instruction: str, test_type: str,
             with_asserts: bool, use_faker: bool) -> str:
    fields  = analysis["form_fields"]
    buttons = analysis["buttons"]
    pt      = analysis["page_type"]
    cls     = _class_name(pt)
    faker_import = "import { faker } from '@faker-js/faker';\n" if use_faker else ""
    pom_methods  = _gen_pom_methods(fields, buttons)
    fill_actions = _gen_fill_actions(fields, use_faker, indent=6)
    btn_action   = _gen_button_action(buttons, indent=6)
    assertions   = _gen_assertions(pt, analysis, indent=4) if with_asserts else ""
    faker_data   = _faker_data_block(fields, indent=4) if use_faker else _static_data_block(fields, indent=4)

    return f"""import {{ type Page, type Locator, expect }} from '@playwright/test';
import {{ test }} from '@playwright/test';
{faker_import}
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Page Object Model: {cls}
// Generated by: playwright_code_generator MCP
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export class {cls} {{
  readonly page: Page;

  // Locators
{_gen_locator_props(fields, buttons)}

  constructor(page: Page) {{
    this.page = page;
{_gen_locator_inits(fields, buttons)}  }}

  async goto(url: string = '/') {{
    await this.page.goto(url);
    await this.page.waitForLoadState('networkidle');
  }}

{pom_methods}}}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Test Suite
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

test.describe('{_title(pt)}', () => {{

  test('{instruction}', async ({{ page }}) => {{
    const {pt}Page = new {cls}(page);
    await {pt}Page.goto();   //  Replace with your actual URL

    // ── Test data ────────────────────────────────────────────────────────
{faker_data}

    // ── Actions ──────────────────────────────────────────────────────────
{fill_actions}
{btn_action}
{assertions}  }});
}});
"""


def _gen_full_suite(analysis: dict, instruction: str, test_type: str,
                    with_asserts: bool, use_faker: bool) -> str:
    """Full suite: fixtures file + POM + test file combined."""
    fields  = analysis["form_fields"]
    pt      = analysis["page_type"]
    cls     = _class_name(pt)

    faker_data   = _faker_data_block(fields, indent=4) if use_faker else _static_data_block(fields, indent=4)
    fill_actions = _gen_fill_actions(fields, use_faker, indent=4)
    btn_action   = _gen_button_action(analysis["buttons"], indent=4)
    assertions   = _gen_assertions(pt, analysis, indent=4) if with_asserts else ""
    pom_methods  = _gen_pom_methods(fields, analysis["buttons"])
    faker_import = "import { faker } from '@faker-js/faker';\n" if use_faker else ""

    return f"""/**
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *  FULL SUITE — {_title(pt)}
 *  Instruction : {instruction}
 *  Test type   : {test_type}
 *  Generated by: playwright_code_generator MCP
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 *  Files you would split this into in a real project:
 *    src/pages/{cls}.ts        ← Page Object Model
 *    src/fixtures/index.ts     ← Custom test fixtures
 *    tests/{pt}.spec.ts        ← Test suite
 */

import {{ type Page, type Locator, expect }} from '@playwright/test';
import {{ test as base }} from '@playwright/test';
{faker_import}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 1 · Page Object Model
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export class {cls} {{
  readonly page: Page;

{_gen_locator_props(fields, analysis["buttons"])}

  constructor(page: Page) {{
    this.page = page;
{_gen_locator_inits(fields, analysis["buttons"])}  }}

  async goto(url: string = '/') {{
    await this.page.goto(url);
    await this.page.waitForLoadState('networkidle');
  }}

{pom_methods}}}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 2 · Custom Fixtures
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

type Fixtures = {{ {pt}Page: {cls} }};

export const test = base.extend<Fixtures>({{
  {pt}Page: async ({{ page }}, use) => {{
    const po = new {cls}(page);
    await po.goto();   //  Replace with your actual URL
    await use(po);
  }},
}});

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 3 · Test Suite
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

test.describe('{_title(pt)} — Full Suite', () => {{

  test.beforeEach(async ({{ {pt}Page }}) => {{
    // Add any shared setup (e.g. mock APIs, auth tokens)
  }});

  test('{instruction}', async ({{ {pt}Page }}) => {{
    // ── Test data ────────────────────────────────────────────────────────
{faker_data}

    // ── Actions ──────────────────────────────────────────────────────────
{fill_actions}
{btn_action}
{assertions}  }});

  test('should show validation errors on empty submit', async ({{ {pt}Page, page }}) => {{
    // Click submit without filling any fields
    await {pt}Page.submitButton.click();

    // Verify validation messages appear
    await expect(page.getByRole('alert')).toBeVisible();
    //  Add specific validation error assertions here
  }});

  test('should show error for invalid email format', async ({{ {pt}Page }}) => {{
    await {pt}Page.emailField?.fill('not-a-valid-email');
    await {pt}Page.submitButton.click();
    //  Assert the specific error message
  }});

}});
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CODE GENERATION HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _best_locator(label: str) -> str:
    # Priority: getByLabel > getByPlaceholder > getByRole > CSS
    # Try getByLabel first (form inputs with associated label)
    return f"page.getByLabel('{label}')"

def _class_name(page_type: str) -> str:
    return "".join(w.title() for w in page_type.split("_")) + "Page"

def _title(page_type: str) -> str:
    return page_type.replace("_", " ").title()

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-")
    return s or hashlib.md5(text.encode()).hexdigest()[:8]

def _prop_name(label: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", label.lower()).split()
    return words[0] + "".join(w.title() for w in words[1:]) + "Field"

def _faker_data_block(fields: list[dict], indent: int = 4) -> str:
    pad = " " * indent
    lines = [f"{pad}const data = {{"]
    for f in fields:
        val = _faker_value(f["type"], f["label"])
        key = re.sub(r"[^a-z0-9]+", "_", f["label"].lower())
        lines.append(f"{pad}  {key}: {val},")
    lines.append(f"{pad}}};")
    return "\n".join(lines)

def _static_data_block(fields: list[dict], indent: int = 4) -> str:
    pad = " " * indent
    lines = [f"{pad}const data = {{"]
    for f in fields:
        val = _static_value(f["type"], f["label"])
        key = re.sub(r"[^a-z0-9]+", "_", f["label"].lower())
        lines.append(f"{pad}  {key}: '{val}',")
    lines.append(f"{pad}}};")
    return "\n".join(lines)

def _faker_value(ftype: str, label: str) -> str:
    label_l = label.lower()
    if "email" in label_l:              return "faker.internet.email()"
    if "phone" in label_l or "tel" in label_l: return "faker.phone.number()"
    if "password" in label_l:           return "faker.internet.password({ length: 12, memorable: true })"
    if "first" in label_l:             return "faker.person.firstName()"
    if "last" in label_l or "surname" in label_l: return "faker.person.lastName()"
    if "city" in label_l:               return "faker.location.city()"
    if "state" in label_l:              return "faker.location.state()"
    if "zip" in label_l or "postal" in label_l:  return "faker.location.zipCode()"
    if "country" in label_l:            return "faker.location.country()"
    if "address" in label_l:            return "faker.location.streetAddress()"
    if "company" in label_l:            return "faker.company.name()"
    if "website" in label_l or "url" in label_l: return "faker.internet.url()"
    if "dob" in label_l or "birth" in label_l:   return "faker.date.birthdate({ min: 18, max: 65, mode: 'age' }).toISOString().split('T')[0]"
    if ftype == "date":                 return "faker.date.recent().toISOString().split('T')[0]"
    if ftype == "number":               return "faker.number.int({ min: 1, max: 100 }).toString()"
    return "faker.lorem.word()"

def _static_value(ftype: str, label: str) -> str:
    label_l = label.lower()
    if "email" in label_l:   return "test@example.com"
    if "phone" in label_l:   return "+1-555-000-0001"
    if "password" in label_l: return "Test@123!"
    if "first" in label_l:   return "John"
    if "last" in label_l:    return "Doe"
    if "city" in label_l:    return "New York"
    if "state" in label_l:   return "NY"
    if "zip" in label_l:     return "10001"
    if "country" in label_l: return "United States"
    return "Test Value"

def _gen_fill_actions(fields: list[dict], use_faker: bool, indent: int = 4) -> str:
    if not fields:
        return " " * indent + "//  No form fields detected — add fill actions manually"
    pad  = " " * indent
    lines = []
    for f in fields:
        key  = re.sub(r"[^a-z0-9]+", "_", f["label"].lower())
        label = f["label"]
        ftype = f["type"]
        if ftype == "select":
            lines.append(f"{pad}await page.getByLabel('{label}').selectOption(data.{key});")
        elif ftype == "password":
            lines.append(f"{pad}await page.getByLabel('{label}').fill(data.{key});")
        else:
            lines.append(f"{pad}await page.getByLabel('{label}').fill(data.{key});")
    return "\n".join(lines)

def _gen_button_action(buttons: list[dict], indent: int = 4) -> str:
    pad = " " * indent
    if not buttons:
        return f"{pad}//  No submit button detected — add click action manually"
    # Pick the most likely submit button (last one, or 'submit'-named)
    btn = next((b for b in buttons if b["text"].lower() in ["register","submit","login","save","checkout"]), buttons[-1])
    return (
        f"{pad}// ── Submit ────────────────────────────────────────────────────────────\n"
        f"{pad}await page.getByRole('button', {{ name: '{btn['text']}' }}).click();"
    )

def _gen_assertions(page_type: str, analysis: dict, indent: int = 4) -> str:
    pad = " " * indent
    lines = [f"\n{pad}// ── Assertions ────────────────────────────────────────────────────────"]
    if page_type == "registration":
        lines += [
            f"{pad}// Adjust URL pattern or success message to match your app",
            f"{pad}await expect(page).toHaveURL(/success|confirm|dashboard/i);",
            f"{pad}// OR: await expect(page.getByText('Registration successful')).toBeVisible();",
        ]
    elif page_type == "login":
        lines += [
            f"{pad}await expect(page).toHaveURL(/dashboard|home|profile/i);",
            f"{pad}await expect(page.getByRole('navigation')).toBeVisible();",
        ]
    elif page_type == "checkout":
        lines += [
            f"{pad}await expect(page).toHaveURL(/confirmation|thank-you|order/i);",
            f"{pad}await expect(page.getByText(/order confirmed|thank you/i)).toBeVisible();",
        ]
    else:
        lines += [
            f"{pad}await expect(page).not.toHaveURL(/error|404/i);",
            f"{pad}//  Add specific success assertions here",
        ]
    lines.append("")
    return "\n".join(lines)

def _gen_locator_props(fields: list[dict], buttons: list[dict]) -> str:
    lines = []
    for f in fields:
        prop = _prop_name(f["label"])
        lines.append(f"  readonly {prop}: Locator;")
    for b in buttons:
        prop = re.sub(r"[^a-z0-9]+", "_", b["text"].lower()) + "Button"
        lines.append(f"  readonly {prop}: Locator;")
    return "\n".join(lines) or "  // No locator props detected"

def _gen_locator_inits(fields: list[dict], buttons: list[dict]) -> str:
    lines = []
    for f in fields:
        prop = _prop_name(f["label"])
        if f["type"] == "select":
            lines.append(f"    this.{prop} = page.getByLabel('{f['label']}');")
        else:
            lines.append(f"    this.{prop} = page.getByLabel('{f['label']}');")
    for b in buttons:
        prop = re.sub(r"[^a-z0-9]+", "_", b["text"].lower()) + "Button"
        lines.append(f"    this.{prop} = page.getByRole('button', {{ name: '{b['text']}' }});")
    return "\n".join(lines) + "\n"

def _gen_pom_methods(fields: list[dict], buttons: list[dict]) -> str:
    method_lines = []

    # fill<PageType>Form
    fill_body = []
    for f in fields:
        prop = _prop_name(f["label"])
        key  = re.sub(r"[^a-z0-9]+", "_", f["label"].lower())
        if f["type"] == "select":
            fill_body.append(f"    await this.{prop}.selectOption(formData.{key});")
        else:
            fill_body.append(f"    await this.{prop}.fill(formData.{key});")

    method_lines.append(
        "  async fillForm(formData: Record<string, string>) {\n"
        + "\n".join(fill_body or ["    //  No fields detected"])
        + "\n  }\n"
    )

    # submit
    if buttons:
        btn = buttons[-1]
        prop = re.sub(r"[^a-z0-9]+", "_", btn["text"].lower()) + "Button"
        method_lines.append(
            f"  async submit() {{\n"
            f"    await this.{prop}.click();\n"
            f"    await this.page.waitForLoadState('networkidle');\n"
            f"  }}\n"
        )

    return "\n".join(method_lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UTILITIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_snapshot_content(snapshot_ref: str) -> str:
    """Load snapshot from file or return raw text."""
    p = SNAPSHOT_DIR / snapshot_ref
    if p.exists():
        return p.read_text(encoding="utf-8")
    # Try adding extension
    for ext in [".md", ".html", ".txt"]:
        q = SNAPSHOT_DIR / (snapshot_ref + ext)
        if q.exists():
            return q.read_text(encoding="utf-8")
    # Treat as raw content
    return snapshot_ref

def _aria_to_markdown(snapshot: Any, url: str) -> str:
    """Convert Playwright accessibility snapshot object to Markdown."""
    lines = [f"# Accessibility Snapshot\n", f"**URL:** {url}\n", "---\n"]

    def walk(node, depth=0):
        if not isinstance(node, dict):
            return
        indent = "  " * depth
        role   = node.get("role", "")
        name   = node.get("name", "")
        value  = node.get("value", "")
        desc   = node.get("description", "")

        label_parts = [f"**{role}**" if role else ""]
        if name:   label_parts.append(f'name="{name}"')
        if value:  label_parts.append(f'value="{value}"')
        if desc:   label_parts.append(f'description="{desc}"')

        lines.append(f"{indent}- {' '.join(filter(None, label_parts))}")

        for child in node.get("children", []):
            walk(child, depth + 1)

    if isinstance(snapshot, dict):
        walk(snapshot)
    else:
        lines.append("*(snapshot format not parseable — raw content below)*\n")
        lines.append(str(snapshot))

    return "\n".join(lines)

def _mock_snapshot(url: str, label: str) -> str:
    """Return a mock snapshot when Playwright is not installed."""
    mock = f"""# Accessibility Snapshot (Mock — Playwright not installed)
**URL:** {url}
**Label:** {label}

>   Playwright is not installed. Install it with:
>     pip install playwright && playwright install chromium
>
> This is a mock snapshot for testing the MCP server tooling.

---

- **WebArea** name="Register | MyApp"
  - **banner**
    - **heading** name="Create Your Account" level=1
  - **main**
    - **form** name="Registration Form"
      - **group** name="Personal Details"
        - **textbox** name="First Name" required
        - **textbox** name="Last Name" required
        - **textbox** name="Email" type=email required
        - **textbox** name="Phone" type=tel
        - **textbox** name="Date of Birth" type=date
      - **group** name="Account Details"
        - **textbox** name="Username" required
        - **textbox** name="Password" type=password required
        - **textbox** name="Confirm Password" type=password required
      - **group** name="Address"
        - **textbox** name="Address"
        - **textbox** name="City"
        - **combobox** name="Country"
        - **textbox** name="Zip Code"
      - **checkbox** name="I agree to the Terms and Conditions"
      - **button** name="Register" type=submit
  - **contentinfo**
    - **link** name="Already have an account? Login"
    - **link** name="Privacy Policy"
"""
    md_path = SNAPSHOT_DIR / f"{label}.md"
    md_path.write_text(mock, encoding="utf-8")
    return (
        f"  Playwright not installed — returning MOCK snapshot.\n\n"
        f"Install with: `pip install playwright && playwright install chromium`\n\n"
        f"Saved mock to: `snapshots/{label}.md`\n\n---\n\n{mock}"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
