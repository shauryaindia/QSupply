import { describe, expect, it } from "vitest";
import { splitAtAntimeridian } from "./GlobalNetworkMap";

describe("splitAtAntimeridian", () => {
  it("splits eastward Pacific geometry at the map boundary", () => {
    expect(splitAtAntimeridian([[35, 170], [40, -170]])).toEqual([
      [[35, 170], [37.5, 180]],
      [[37.5, -180], [40, -170]],
    ]);
  });

  it("splits westward Pacific geometry at the map boundary", () => {
    expect(splitAtAntimeridian([[40, -170], [35, 170]])).toEqual([
      [[40, -170], [37.5, -180]],
      [[37.5, 180], [35, 170]],
    ]);
  });

  it("preserves ordinary segments and handles empty or single-point input", () => {
    expect(splitAtAntimeridian([[10, 20], [15, 25]])).toEqual([
      [[10, 20], [15, 25]],
    ]);
    expect(splitAtAntimeridian([])).toEqual([]);
    expect(splitAtAntimeridian([[10, 20]])).toEqual([[[10, 20]]]);
  });
});
