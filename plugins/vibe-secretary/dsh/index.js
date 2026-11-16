// VibeSecretary DeepSeek Harness host plugin.
//
// Bridges the plugin's existing Python runtime to DSH:
//   - registers the four bundled skills through ctx.skills;
//   - SessionStart      -> agent/created     -> vibe-secretary-hook session-start
//   - UserPromptSubmit  -> agent/pre-step    -> vibe-secretary-hook user-prompt-submit
//   - PreToolUse        -> tools/pre-execute -> vibe-secretary-hook pre-tool-use
//
// `vibe-secretary-mcp` (declared in cordis.patch.yml) and `vibe-secretary-hook`
// must be on the harness process PATH; install the Python package with
// `pip install plugins/vibe-secretary` (or `pip install vibe-secretary`).

import { randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { readFile, readdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const PLUGIN_ROOT = join(HERE, '..')
const SKILLS_ROOT = join(PLUGIN_ROOT, 'skills')

const PROVIDER_NAME = 'vibe-secretary'
const HOOK_TIMEOUT_MS = 10_000
const SOURCE_KIND = 'vibe-secretary'

const GATED_TOOL = /^(pwsh|bash|read|write|edit|glob|grep|mcp__)/

// Cordis services accessed by this plugin; without a declaration, property
// access on `ctx` throws "cannot get property ... without inject".
export const inject = ['skills', 'workingDirectory', 'tools']

function userMessage(text) {
  // A complete user-role message. Both `agent.inject` and the `agent/pre-step`
  // enter decision require a stable `id` and the `role: 'user'` tag, matching
  // what `createUserMessage` from @deepseek-ai/dsh-llm supplies.
  return {
    id: randomUUID(),
    role: 'user',
    content: [{ type: 'text', text }],
    source: { kind: SOURCE_KIND },
  }
}

function parseJson(text) {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function parseFrontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(text)
  if (!match) return null
  const meta = {}
  for (const line of match[1].split(/\r?\n/)) {
    const index = line.indexOf(':')
    if (index === -1) continue
    meta[line.slice(0, index).trim()] = line.slice(index + 1).trim()
  }
  return { meta, content: match[2].replace(/^\r?\n/, '') }
}

function runHook(name, payload) {
  return new Promise((resolve) => {
    let child
    try {
      child = spawn('vibe-secretary-hook', [name], {
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      })
    } catch (error) {
      resolve({ ok: false, error: String(error) })
      return
    }
    let stdout = ''
    let stderr = ''
    let settled = false
    const finish = (value) => {
      if (settled) return
      settled = true
      resolve(value)
    }
    const timer = setTimeout(() => {
      try { child.kill() } catch {}
      finish({ ok: false, error: 'timeout' })
    }, HOOK_TIMEOUT_MS)
    child.stdout.on('data', (chunk) => { stdout += chunk })
    child.stderr.on('data', (chunk) => { stderr += chunk })
    child.on('error', (error) => {
      clearTimeout(timer)
      finish({ ok: false, error: String(error) })
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      finish({ ok: code === 0, stdout, stderr })
    })
    child.stdin.on('error', () => {})
    child.stdin.write(JSON.stringify(payload))
    child.stdin.end()
  })
}

function readCwd(ctx, agent) {
  try {
    if (ctx.workingDirectory) return ctx.workingDirectory.get(agent.session)
  } catch {}
  try {
    const cwd = agent.session && agent.session.header && agent.session.header.cwd
    if (cwd) return cwd
  } catch {}
  return process.cwd()
}

function extractAdditionalContext(stdout) {
  const parsed = parseJson(stdout)
  const context = parsed && parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext
  return typeof context === 'string' ? context : ''
}

function extractUserPrompt(messages) {
  const parts = []
  for (const message of messages) {
    if (!message || !message.source || message.source.kind !== 'user') continue
    for (const block of message.content || []) {
      if (block && block.type === 'text' && typeof block.text === 'string') parts.push(block.text)
    }
  }
  return parts.length > 0 ? parts.join('\n') : null
}

async function listSkills() {
  let entries
  try {
    entries = await readdir(SKILLS_ROOT, { withFileTypes: true })
  } catch {
    return []
  }
  const candidates = []
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const skillPath = join(SKILLS_ROOT, entry.name, 'SKILL.md')
    try {
      const parsed = parseFrontmatter(await readFile(skillPath, 'utf8'))
      if (!parsed || !parsed.meta.name || !parsed.meta.description) continue
      candidates.push({
        name: parsed.meta.name,
        description: parsed.meta.description,
        whenToUse: parsed.meta.whenToUse,
        invocation: { modelInvocable: true, userInvocable: true },
        source: 'bundled',
        provider: PROVIDER_NAME,
        resourceBase: { kind: 'directory', path: join(SKILLS_ROOT, entry.name) },
        path: skillPath,
        rank: 600,
        locator: skillPath,
      })
    } catch {
      // skip unreadable skill
    }
  }
  return candidates
}

async function getSkill(candidate) {
  try {
    const parsed = parseFrontmatter(await readFile(candidate.locator, 'utf8'))
    if (!parsed) return undefined
    return {
      name: candidate.name,
      description: candidate.description,
      whenToUse: candidate.whenToUse,
      invocation: candidate.invocation,
      source: candidate.source,
      provider: candidate.provider,
      resourceBase: candidate.resourceBase,
      path: candidate.path,
      content: parsed.content,
    }
  } catch {
    return undefined
  }
}

function registerSkills(ctx) {
  return ctx.skills.registerProvider(() => ({
    name: PROVIDER_NAME,
    list: listSkills,
    get: getSkill,
  }))
}

async function onCreated(ctx, payload) {
  const agent = payload.agent
  if (!agent) return
  const cwd = readCwd(ctx, agent)
  const result = await runHook('session-start', { cwd })
  if (!result.ok) return
  const context = extractAdditionalContext(result.stdout)
  if (!context) return
  const note = `Current project root is ${JSON.stringify(cwd)}. Pass this absolute path as \`project_root\` to every VibeSecretary MCP tool.`
  try {
    agent.inject(userMessage(`${context}\n\n${note}`))
  } catch {}
}

async function onPreStep(ctx, payload, next) {
  const decision = await next()
  if (!decision || decision.kind !== 'enter') return decision
  const prompt = extractUserPrompt(payload.messages)
  if (!prompt) return decision
  const cwd = readCwd(ctx, payload.agent)
  const result = await runHook('user-prompt-submit', { cwd, prompt })
  if (!result.ok || !result.stdout) return decision
  const context = result.stdout.trim()
  if (!context) return decision
  return { ...decision, messages: [...decision.messages, userMessage(context)] }
}

async function onPreTool(ctx, exec, next) {
  if (!GATED_TOOL.test(exec.name)) return next()
  if (!exec.agent) return next()
  const cwd = readCwd(ctx, exec.agent)
  const result = await runHook('pre-tool-use', {
    cwd,
    tool_name: exec.name,
    tool_input: exec.arguments,
  })
  if (!result.ok) return next()
  const parsed = parseJson(result.stdout)
  const output = parsed && parsed.hookSpecificOutput
  if (output && output.permissionDecision === 'deny') {
    return {
      kind: 'deny',
      reason: output.permissionDecisionReason || 'VibeSecretary denied an explicit path outside the confirmed project read scope.',
    }
  }
  return next()
}

export function apply(ctx) {
  const disposers = []
  if (ctx.skills) disposers.push(registerSkills(ctx))
  disposers.push(ctx.on('agent/created', (payload) => onCreated(ctx, payload)))
  disposers.push(ctx.on('agent/pre-step', (payload, next) => onPreStep(ctx, payload, next)))
  if (ctx.tools) disposers.push(ctx.on('tools/pre-execute', (exec, next) => onPreTool(ctx, exec, next)))
  return () => {
    for (const dispose of disposers.reverse()) {
      try { dispose() } catch {}
    }
  }
}
