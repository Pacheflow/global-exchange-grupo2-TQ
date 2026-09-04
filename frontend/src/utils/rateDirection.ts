export type RateDirection = "up" | "down" | "flat";

export function getRateDirection(variation: number): RateDirection {
  if (variation > 0) return "up";
  if (variation < 0) return "down";
  return "flat";
}
