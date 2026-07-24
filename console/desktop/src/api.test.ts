import { invoke, isTauri } from "@tauri-apps/api/core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { connectGateway } from "./api";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
  isTauri: vi.fn(),
}));

describe("gateway bootstrap", () => {
  beforeEach(() => {
    vi.mocked(invoke).mockReset();
    vi.mocked(isTauri).mockReset();
  });

  it("uses the Rust command in a packaged Tauri application", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue({
      baseUrl: "http://127.0.0.1:41000",
      token: "native-token",
      workspace: "/workspace",
    });

    await expect(connectGateway()).resolves.toMatchObject({
      token: "native-token",
    });
    expect(invoke).toHaveBeenCalledWith("start_gateway");
  });

  it("uses development configuration in a normal browser", async () => {
    vi.mocked(isTauri).mockReturnValue(false);

    await expect(connectGateway()).resolves.toMatchObject({
      baseUrl: expect.stringMatching(/^http:\/\/127\.0\.0\.1:/),
    });
    expect(invoke).not.toHaveBeenCalled();
  });
});
