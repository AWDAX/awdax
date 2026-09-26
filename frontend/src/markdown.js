import { marked } from "https://esm.sh/marked@15.0.6";

marked.setOptions({
  gfm: true,
  breaks: true,
});

/**
 * Render Gemini / bot plain-text (incl. markdown tables) to safe HTML.
 * @param {string} source
 * @returns {string}
 */
export function renderMarkdown(source) {
  if (!source) return "";
  const normalized = source.replace(/^=== (.+?) ===\s*$/gm, "## $1");
  return marked.parse(normalized, { async: false });
}
