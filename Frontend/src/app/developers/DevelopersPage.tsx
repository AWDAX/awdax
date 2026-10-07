import { useState } from 'react'
import { PageHeader } from '../workspace/PageHeader.tsx'
import { CodeBlock } from './CodeBlock.tsx'
import { EndpointList } from './EndpointList.tsx'
import { KeysPanel } from './KeysPanel.tsx'
import { claudeCodeCommand, claudeDesktopConfig, curlSnippet, researchSnippet } from './snippets.ts'

/**
 * API and MCP for this account: make a key, copy a working command, see every endpoint. The snippets show the key
 * just made (until the page is left); otherwise a placeholder to replace.
 */
export default function DevelopersPage() {
  const [key, setKey] = useState<string | null>(null)
  const origin = window.location.origin
  const k = key ?? undefined

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <PageHeader eyebrow="API and MCP" title="Use AWDAX from code, or from Claude" />

      <KeysPanel onCreated={setKey} />

      <section aria-labelledby="try-h" className="mt-10">
        <h2 id="try-h" className="font-display text-h3 font-extrabold">Try it</h2>
        <p className="mt-1 max-w-prose text-small text-ink-2">List your chats, then run a research request and read the table back.</p>
        <div className="mt-3 flex flex-col gap-3">
          <CodeBlock code={curlSnippet(origin, k)} label="list your chats with curl" />
          <CodeBlock code={researchSnippet(origin, k)} label="start a research run with curl" />
        </div>
      </section>

      <section aria-labelledby="mcp-h" className="mt-10">
        <h2 id="mcp-h" className="font-display text-h3 font-extrabold">Connect Claude (MCP)</h2>
        <p className="mt-1 max-w-prose text-small text-ink-2">
          Claude can start research, check progress, read the data and ask questions about it, as you. Use a read and write key to let it start runs.
        </p>
        <h3 className="mt-4 font-mono text-micro text-ink-3">Claude Code</h3>
        <div className="mt-1">
          <CodeBlock code={claudeCodeCommand(origin, k)} label="add AWDAX to Claude Code" />
        </div>
        <h3 className="mt-4 font-mono text-micro text-ink-3">Claude Desktop: add to claude_desktop_config.json</h3>
        <div className="mt-1">
          <CodeBlock code={claudeDesktopConfig(origin, k)} label="Claude Desktop configuration" />
        </div>
        <p className="mt-3 max-w-prose text-small text-ink-2">
          claude.ai’s Connectors accept this address only where an organisation owner can add a custom header; otherwise use Claude Code or Desktop for now.
        </p>
      </section>

      <EndpointList />
    </div>
  )
}
