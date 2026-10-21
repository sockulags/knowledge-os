// Runs under Node's built-in test runner (`npm test`).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { kebab } from "./text.ts";

type KebabCase = { input: string; limit?: number | null; fallback?: string; expected: string };

// Shared with tests/test_kebab.py, so the reader and the core make the same ids.
const fixture = new URL("../../../tests/fixtures/kebab_cases.json", import.meta.url);
const cases = JSON.parse(readFileSync(fixture, "utf-8")) as KebabCase[];

describe("kebab", () => {
  it("makes the same ids as the core for every shared case", () => {
    assert.ok(cases.length > 0);
    for (const { input, limit, fallback, expected } of cases) {
      assert.equal(kebab(input, limit === undefined ? 80 : limit, fallback ?? ""), expected, input);
    }
  });
});
