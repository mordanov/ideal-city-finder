export function criterionConfidence(
  actualValue: number,
  threshold: number,
  tolerance: number
): number {
  if (tolerance <= 0) return actualValue <= threshold ? 1.0 : 0.0;
  if (actualValue <= threshold) return 1.0;
  if (actualValue >= threshold + tolerance) return 0.0;
  return 1.0 - (actualValue - threshold) / tolerance;
}
