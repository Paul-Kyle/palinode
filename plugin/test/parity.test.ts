/**
 * Plugin-side cross-surface parity test — ADR-010 forcing function for the
 * OpenClaw plugin (TypeScript surface).
 *
 * Mirrors ``tests/test_surface_parity.py``: for every operation in the
 * canonical registry that has a ``plugin_tool`` set, asserts that each
 * canonical parameter is declared in the plugin's TypeBox schema, OR that
 * ``("plugin", param)`` is recorded in ``known_drift`` with a tracking
 * issue.  Once the drift is resolved (the plugin schema declares the
 * param), the matching ``known_drift`` entry must be removed — this test
 * fails loudly when that hasn't happened, which is exactly the point.
 *
 * The registry is loaded from ``plugin/parity-registry.json``, regenerated
 * before each ``npm test`` run by the ``pretest`` script invoking
 * ``scripts/dump-parity-registry.py``.  No checked-in artifact; the
 * single source of truth stays at ``palinode/core/parity.py``.
 *
 * Plugin schema introspection: we instantiate the default-exported plugin
 * with a minimal ``OpenClawPluginApi`` shim that captures every
 * ``registerTool({ name, parameters })`` call.  The plugin's ``register()``
 * does no real I/O during registration (just ``path.resolve`` for safety
 * checks), so the shim is a faithful but cheap simulation.
 */

import { describe, expect, it, beforeAll } from "vitest";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

import palinodePlugin from "../index";

// Vitest's Vite resolver picks up "../index" → "../index.ts" automatically.
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ---------------------------------------------------------------------------
// Registry loading
// ---------------------------------------------------------------------------

type Surface = "cli" | "mcp" | "api" | "plugin";

interface CanonicalParam {
  name: string;
  type: string;
  required: boolean;
  default_key: string | null;
  enum: string[] | null;
  notes: string;
}

interface DriftEntry {
  surface: Surface;
  param: string;
  issue: number;
}

interface RegistryOperation {
  name: string;
  canonical_params: CanonicalParam[];
  cli_command: string | null;
  mcp_tool: string | null;
  api_endpoint: [string, string] | null;
  plugin_tool: string | null;
  exempt_surfaces: Surface[];
  known_drift: DriftEntry[];
}

interface ParityRegistry {
  operations: RegistryOperation[];
  admin_exempt: string[];
  categories: string[];
  memory_types: string[];
  prompt_tasks: string[];
}

const REGISTRY_PATH = path.resolve(__dirname, "..", "parity-registry.json");

function loadRegistry(): ParityRegistry {
  if (!fs.existsSync(REGISTRY_PATH)) {
    throw new Error(
      `parity-registry.json missing at ${REGISTRY_PATH} — run 'npm test' (the 'pretest' hook regenerates it from palinode/core/parity.py).`,
    );
  }
  const raw = fs.readFileSync(REGISTRY_PATH, "utf-8");
  return JSON.parse(raw) as ParityRegistry;
}

// ---------------------------------------------------------------------------
// Plugin tool introspection — minimal OpenClawPluginApi shim
// ---------------------------------------------------------------------------

interface CapturedTool {
  name: string;
  /** Raw TypeBox schema for the tool's parameters (Type.Object output). */
  parameters: { type: string; properties: Record<string, unknown>; required?: string[] };
}

function captureRegisteredTools(): Map<string, CapturedTool> {
  const tools = new Map<string, CapturedTool>();

  const fakeApi: any = {
    pluginConfig: {
      // Use a plausible directory under HOME so resolveWithin's relative
      // check passes; no filesystem reads happen during register().
      palinodeDir: path.join(process.env.HOME || "/tmp", "palinode"),
      promptsDir: "specs/prompts",
      autoRecall: false, // Skip event handlers; we only care about tool schemas.
      autoCapture: false,
      midTurnMode: "none",
    },
    logger: {
      info: () => undefined,
      warn: () => undefined,
      error: () => undefined,
    },
    registerTool: (toolDef: any, _meta?: any) => {
      if (!toolDef || typeof toolDef.name !== "string") return;
      tools.set(toolDef.name, {
        name: toolDef.name,
        parameters: toolDef.parameters,
      });
    },
    on: () => undefined,
    registerCli: () => undefined,
    registerService: () => undefined,
  };

  palinodePlugin.register(fakeApi);
  return tools;
}

function pluginParamNames(tool: CapturedTool | undefined): Set<string> {
  if (!tool || !tool.parameters || !tool.parameters.properties) {
    return new Set();
  }
  return new Set(Object.keys(tool.parameters.properties));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

let registry: ParityRegistry;
let pluginTools: Map<string, CapturedTool>;

beforeAll(() => {
  registry = loadRegistry();
  pluginTools = captureRegisteredTools();
});

describe("ADR-010 plugin parity", () => {
  it("loads at least one operation from the registry", () => {
    expect(registry.operations.length).toBeGreaterThan(0);
  });

  it("captures at least one tool from the plugin", () => {
    expect(pluginTools.size).toBeGreaterThan(0);
  });

  it("known_drift entries reference real canonical params", () => {
    // Mirrors test_known_drift_references_a_canonical_param in the Python
    // suite — drift entries must point at a param that actually exists in
    // canonical_params, otherwise refactor renames create dangling drift.
    const bad: string[] = [];
    for (const op of registry.operations) {
      const canonicalNames = new Set(op.canonical_params.map((cp) => cp.name));
      for (const drift of op.known_drift) {
        if (!canonicalNames.has(drift.param)) {
          bad.push(`${op.name}: known_drift[("${drift.surface}", "${drift.param}")]`);
        }
      }
    }
    expect(bad).toEqual([]);
  });
});

// Build the case list at module scope so vitest can render one test per
// (operation, param) pair, matching the Python suite's parametrization.
function buildCases(): Array<{
  op: RegistryOperation;
  param: CanonicalParam;
  driftIssue: number | null;
}> {
  // Need to load the registry synchronously here (before beforeAll runs)
  // for vitest to enumerate test names at collection time.
  const reg = loadRegistry();
  const cases: Array<{
    op: RegistryOperation;
    param: CanonicalParam;
    driftIssue: number | null;
  }> = [];
  for (const op of reg.operations) {
    if (!op.plugin_tool) continue; // Only ops that target the plugin.
    if (op.exempt_surfaces.includes("plugin")) continue;
    for (const param of op.canonical_params) {
      const drift = op.known_drift.find(
        (d) => d.surface === "plugin" && d.param === param.name,
      );
      cases.push({
        op,
        param,
        driftIssue: drift ? drift.issue : null,
      });
    }
  }
  return cases;
}

describe("ADR-010 plugin canonical params", () => {
  const cases = buildCases();

  if (cases.length === 0) {
    it("registry contains no plugin-bound operations", () => {
      // If the registry stops listing plugin tools entirely, the test
      // suite shouldn't silently turn into a no-op — surface it.
      expect.fail("expected at least one registry operation with plugin_tool set");
    });
    return;
  }

  for (const { op, param, driftIssue } of cases) {
    const caseId = `${op.name}/plugin/${param.name}`;
    it(caseId, () => {
      const tool = pluginTools.get(op.plugin_tool!);
      const params = pluginParamNames(tool);

      if (driftIssue !== null) {
        // Drift was tracked: if the surface NOW exposes the param, the
        // drift entry should be removed.  Failing here is the point —
        // the test forces drift cleanup.
        if (params.has(param.name)) {
          expect.fail(
            `${op.name}/plugin: param "${param.name}" is now present; ` +
              `remove known_drift[("plugin", "${param.name}")] from ` +
              `palinode/core/parity.py and close issue #${driftIssue}.`,
          );
        }
        // Drift is current and the param is missing as expected — passes.
        return;
      }

      expect(
        params.has(param.name),
        `${op.name}/plugin: canonical param "${param.name}" not exposed ` +
          `(found: ${[...params].sort().join(", ") || "none"}). ` +
          `If this is intentional drift, add ` +
          `known_drift[("plugin", "${param.name}")] = <issue> on the ` +
          `Operation in palinode/core/parity.py.`,
      ).toBe(true);
    });
  }
});
