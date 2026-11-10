let counter = 0;

export function uid(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter.toString(36)}`;
}

export function clockTime(): string {
  return new Date().toISOString().slice(11, 19);
}

export function isoNow(): string {
  return new Date().toISOString().slice(0, 19);
}

export function isoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

export function isoDateOffset(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  if (sameDay) return date.toISOString().slice(11, 16);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

export function relativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes}分`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天`;
  return `${date.getMonth() + 1}/${date.getDate()}`;
}
