/**
 * Round ticks, and only ones the data reaches: a label shouldn't name a value nothing comes near. Zero is
 * always on the scale. A sum can go below it, because a ledger holds refunds.
 */
export function chartScale(max: number, min = 0): { top: number; bottom: number; ticks: number[] } {
  const reach = Math.max(max, -min);
  if (reach <= 0) return { top: 1, bottom: 0, ticks: [0] };
  const power = 10 ** Math.floor(Math.log10(reach));
  const step = [0.25, 0.5, 1, 2, 5].map((factor) => factor * power).find((candidate) => reach / candidate <= 4) ?? power;
  const above = Math.floor(Math.max(max, 0) / step);
  const below = min < 0 ? Math.floor(-min / step) : 0;
  const ticks = Array.from({ length: above + below + 1 }, (_, index) => (index - below) * step);
  return { top: Math.max(max, 0) * 1.05, bottom: Math.min(min, 0) * 1.05, ticks };
}

/**
 * Where each point falls along the axis, from 0 to 1. Evenly spaced unless every point says where it belongs,
 * because grouping by date gives one point per date that has data, and even spacing would hide the gaps.
 */
export function pointPositions(places: readonly (number | undefined)[]): number[] {
  const count = places.length;
  if (count < 2) return places.map(() => 0);
  const even = places.map((_, index) => index / (count - 1));
  const first = places[0];
  const last = places[count - 1];
  if (first === undefined || last === undefined || last <= first || places.some((place) => place === undefined)) return even;
  return places.map((place) => ((place as number) - first) / (last - first));
}

/**
 * Which points get a label under the axis, when they can't all fit. Walks back from the last, which matters
 * most, keeping each label that clears the one kept before it. Takes real positions, since dates can bunch.
 */
export function labelledPoints(xs: readonly number[], widths: readonly number[], gap = 8): Set<number> {
  const labelled = new Set<number>();
  let kept: number | undefined;
  for (let index = xs.length - 1; index >= 0; index -= 1) {
    const clear = kept === undefined || Math.abs((xs[index] ?? 0) - (xs[kept] ?? 0)) >= ((widths[index] ?? 0) + (widths[kept] ?? 0)) / 2 + gap;
    if (clear) {
      labelled.add(index);
      kept = index;
    }
  }
  return labelled;
}

/** About how wide a label is at the small size: Arabic letters join, and digits are wider than they look. */
export function labelWidth(label: string): number {
  return label.length * (/[\u0600-\u06ff]/.test(label) ? 6 : 8);
}

/** Runs of points that have a value, as indexes. A gap breaks the line rather than pretending to be zero. */
export function lineRuns(values: readonly (number | null)[]): number[][] {
  const runs: number[][] = [];
  let run: number[] = [];
  values.forEach((value, index) => {
    if (value === null) {
      if (run.length) runs.push(run);
      run = [];
    } else {
      run.push(index);
    }
  });
  if (run.length) runs.push(run);
  return runs;
}
