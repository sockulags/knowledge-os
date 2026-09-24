// Runs under Node's built-in test runner (`npm test`).

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  browserStore,
  clampWidth,
  DEFAULT_WIDTH,
  desktopStore,
  KEY_STEP,
  KEY_STEP_LARGE,
  loadWidth,
  MAX_WIDTH,
  maxWidthFor,
  MIN_WIDTH,
  parseStoredWidth,
  saveWidth,
  STORAGE_KEY,
  widthForKey,
} from "./sidebarWidth.ts";

function memoryStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
    removeItem: (key: string) => void values.delete(key),
  };
}

function throwingStorage() {
  const fail = () => {
    throw new Error("SecurityError");
  };
  return { getItem: fail, setItem: fail, removeItem: fail };
}

describe("clampWidth", () => {
  it("keeps a width inside the limits", () => {
    assert.equal(clampWidth(100), MIN_WIDTH);
    assert.equal(clampWidth(5000), MAX_WIDTH);
    assert.equal(clampWidth(300.4), 300);
  });

  it("leaves the reading column its minimum in a narrow window", () => {
    assert.equal(maxWidthFor(900), 480);
    assert.equal(clampWidth(560, 900), 480);
    // Never below the sidebar's own minimum, however narrow the window.
    assert.equal(maxWidthFor(500), MIN_WIDTH);
  });

  it("turns a non-number into the default", () => {
    assert.equal(clampWidth(Number.NaN), DEFAULT_WIDTH);
  });
});

describe("parseStoredWidth", () => {
  it("accepts a number or numeric text in range", () => {
    assert.equal(parseStoredWidth("320"), 320);
    assert.equal(parseStoredWidth(320.6), 321);
  });

  it("rejects anything missing, damaged, or out of range", () => {
    for (const value of [null, undefined, "", "wide", "12", "9000", {}, Number.POSITIVE_INFINITY]) {
      assert.equal(parseStoredWidth(value), null, String(value));
    }
  });
});

describe("widthForKey", () => {
  it("steps with the arrows and takes a larger step with Shift", () => {
    assert.equal(widthForKey(300, "ArrowRight", false, 1600), 300 + KEY_STEP);
    assert.equal(widthForKey(300, "ArrowLeft", true, 1600), 300 - KEY_STEP_LARGE);
  });

  it("stops at the limits and jumps to them with Home and End", () => {
    assert.equal(widthForKey(MIN_WIDTH, "ArrowLeft", false, 1600), MIN_WIDTH);
    assert.equal(widthForKey(400, "Home", false, 1600), MIN_WIDTH);
    assert.equal(widthForKey(400, "End", false, 900), 480);
  });

  it("ignores other keys", () => {
    assert.equal(widthForKey(300, "Enter", false, 1600), null);
  });
});

describe("remembering the width", () => {
  it("round-trips through browser storage and forgets the default", () => {
    const storage = memoryStorage();
    const store = browserStore(() => storage);
    saveWidth([store], 360);
    assert.equal(storage.values.get(STORAGE_KEY), "360");
    assert.equal(loadWidth([store]), 360);
    saveWidth([store], DEFAULT_WIDTH);
    assert.equal(storage.values.has(STORAGE_KEY), false);
    assert.equal(loadWidth([store]), null);
  });

  it("works without storage when reading or writing throws", () => {
    const store = browserStore(throwingStorage);
    assert.equal(loadWidth([store]), null);
    assert.doesNotThrow(() => saveWidth([store], 360));
    const missing = browserStore(() => {
      throw new Error("no localStorage");
    });
    assert.equal(loadWidth([missing]), null);
  });

  it("prefers the desktop app's setting and writes to every store", () => {
    let desktopValue: unknown = 420;
    const desktop = desktopStore({
      getSidebarWidth: () => desktopValue,
      setSidebarWidth: (width) => {
        desktopValue = width;
      },
    });
    const storage = memoryStorage({ [STORAGE_KEY]: "300" });
    const browser = browserStore(() => storage);
    assert.equal(loadWidth([desktop, browser]), 420);
    desktopValue = null;
    assert.equal(loadWidth([desktop, browser]), 300);
    saveWidth([desktop, browser], 512);
    assert.equal(desktopValue, 512);
    assert.equal(storage.values.get(STORAGE_KEY), "512");
  });

  it("ignores a desktop bridge that throws", () => {
    const desktop = desktopStore({
      getSidebarWidth: () => {
        throw new Error("gone");
      },
      setSidebarWidth: () => {
        throw new Error("gone");
      },
    });
    assert.equal(loadWidth([desktop]), null);
    assert.doesNotThrow(() => saveWidth([desktop], 300));
  });
});
