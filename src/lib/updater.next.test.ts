import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getName: vi.fn(), check: vi.fn() }));
vi.mock("@tauri-apps/api/app", () => ({
  getName: mocks.getName,
  getVersion: vi.fn().mockResolvedValue("4.0.14"),
}));
vi.mock("@tauri-apps/plugin-updater", () => ({ check: mocks.check }));
import { checkForUpdate } from "./updater";

beforeEach(() => vi.clearAllMocks());
it("never invokes the updater for Next and supplies its own release URL", async () => {
  mocks.getName.mockResolvedValue("CC Switch Next");
  await expect(checkForUpdate()).rejects.toThrow(
    "xue-ding-e/CC-Switch-Next/releases",
  );
  expect(mocks.check).not.toHaveBeenCalled();
});
it("preserves the upstream result for a non-Next test build", async () => {
  mocks.getName.mockResolvedValue("CC Switch");
  mocks.check.mockResolvedValue(null);
  await expect(checkForUpdate()).resolves.toEqual({ status: "up-to-date" });
  expect(mocks.check).toHaveBeenCalledOnce();
});
