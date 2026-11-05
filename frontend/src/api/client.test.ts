import { describe, expect, it } from "vitest";
import { distanceChartValue, formatDistance } from "./client";

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
