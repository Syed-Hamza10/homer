const TAG = /<\/?untrusted>/gi

export function stripUntrusted(text: string): string {
  return text.replace(TAG, "")
}
