/**
 * Time-of-day greeting copy. Keep each line close in length to the original
 * "晚上好，接下来交给我吧" so the hero heading does not jump between slots.
 */
export function greetingForHour(hour: number): string {
  const normalized = ((Math.floor(hour) % 24) + 24) % 24;
  if (normalized >= 5 && normalized < 9) return "早上好，今天从哪一步开始";
  if (normalized >= 9 && normalized < 12) return "上午好，今天先推进哪一步";
  if (normalized >= 12 && normalized < 14) return "中午好，今天先读哪一篇呢";
  if (normalized >= 14 && normalized < 18) return "下午好，接下来交给我吧";
  if (normalized >= 18 && normalized < 23) return "晚上好，接下来交给我吧";
  return "夜深了，把问题留给我吧";
}

export function currentGreeting(now: Date = new Date()): string {
  return greetingForHour(now.getHours());
}
