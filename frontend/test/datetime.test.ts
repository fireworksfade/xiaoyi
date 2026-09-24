import { describe, expect, it } from 'vitest';

import { parseApiDate } from '@/lib/datetime';

describe('API datetime parsing', () => {
  it('treats timezone-less API timestamps as UTC', () => {
    expect(parseApiDate('2026-09-23T17:46:47')?.toISOString()).toBe(
      '2026-09-23T17:46:47.000Z',
    );
  });

  it('preserves explicit timezone offsets', () => {
    expect(parseApiDate('2026-09-23T17:46:47+08:00')?.toISOString()).toBe(
      '2026-09-23T09:46:47.000Z',
    );
  });
});
