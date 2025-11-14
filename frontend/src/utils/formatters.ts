// Utility functions for formatting data
import { formatDistanceToNow } from 'date-fns';

export function formatTime(date: Date): string {
  return formatDistanceToNow(date, { addSuffix: true });
}

export function formatTimestamp(date: Date): string {
  return date.toLocaleString();
}

export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '...';
}
