import { afterEach, describe, expect, it, vi } from "vitest";
import { api, distanceChartValue, formatDistance } from "./client";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("exact CVRP distance presentation", () => {
  it("formats exact rational values with fixed decimal precision", () => {
    const distance = "96809073396948901/562949953421312";
    expect(formatDistance(distance)).toBe("171.967");
    expect(distanceChartValue(distance)).toBe(171.967);
  });

  it("preserves large integer digits while adding grouping and decimals", () => {
    expect(formatDistance("96809073396948901")).toBe(
      "96,809,073,396,948,901.000",
    );
  });

  it("rounds rational values half up to three decimal places", () => {
    expect(formatDistance("2/3")).toBe("0.667");
    expect(formatDistance("1999/2000")).toBe("1.000");
  });
});

describe("API transient failure handling", () => {
  it("retries a transient GET network failure and returns the real response", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError("network unavailable"))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok", service: "q-supply-api" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = api.health();
    await vi.runAllTimersAsync();

    await expect(result).resolves.toMatchObject({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries transient server responses but does not retry client errors", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response("warming", { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok", service: "q-supply-api" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const recovered = api.health();
    await vi.runAllTimersAsync();
    await expect(recovered).resolves.toMatchObject({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const clientErrorFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "invalid request" }), { status: 422 }));
    vi.stubGlobal("fetch", clientErrorFetch);
    await expect(api.health()).rejects.toThrow("invalid request");
    expect(clientErrorFetch).toHaveBeenCalledTimes(1);
  });

  it("never retries optimization POST requests after a network error", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("connection reset"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.createRun({
      instance_id: "synthetic-5",
      solver: "nearest-neighbor",
      include_exact_reference: false,
    })).rejects.toThrow("QSupply API is unreachable");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("stops after the bounded number of GET attempts", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("service unavailable"));
    vi.stubGlobal("fetch", fetchMock);
    const request = api.health();
    const rejected = expect(request).rejects.toThrow("QSupply API is unreachable");
    await vi.runAllTimersAsync();
    await rejected;
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
