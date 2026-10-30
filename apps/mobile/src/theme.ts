// Shared colors, kept semantically consistent with apps/admin's badge
// palette (grey = neutral/unknown, amber = caution/unverified, green =
// good/verified/completed, blue = needs-review, red = conflict/escalated).

export const colors = {
  background: '#f7f7f8',
  card: '#ffffff',
  border: '#e2e2e6',
  text: '#1a1a1f',
  textMuted: '#6b7280',
  primary: '#1d4ed8',
  danger: '#b42318',
  warningBg: '#fff3cd',
  warningBorder: '#e3a008',
  warningText: '#664d03',
}

export const statusColors: Record<string, { bg: string; fg: string }> = {
  // Case review status
  pending: { bg: '#fef3c7', fg: '#92650a' },
  in_review: { bg: '#dbeafe', fg: '#1d4ed8' },
  reviewed: { bg: '#dcfce7', fg: '#15803d' },
  escalated: { bg: '#fee2e2', fg: '#b42318' },
  // Fact verification status
  unknown: { bg: '#e5e7eb', fg: '#6b7280' },
  unverified: { bg: '#fef3c7', fg: '#92650a' },
  verified: { bg: '#dcfce7', fg: '#15803d' },
  conflict: { bg: '#fee2e2', fg: '#b42318' },
  // Section 479 evaluation outcome
  REVIEW_THRESHOLD_REACHED: { bg: '#dbeafe', fg: '#1d4ed8' },
  THRESHOLD_NOT_REACHED: { bg: '#e5e7eb', fg: '#6b7280' },
  BLOCKED_MISSING_FACTS: { bg: '#fef3c7', fg: '#92650a' },
  ESCALATED_LEGAL_REVIEW: { bg: '#fee2e2', fg: '#b42318' },
  // Follow-up status (pending reuses the case-status color above)
  in_progress: { bg: '#dbeafe', fg: '#1d4ed8' },
  completed: { bg: '#dcfce7', fg: '#15803d' },
  cancelled: { bg: '#fee2e2', fg: '#b42318' },
}

export const DEFAULT_BADGE_COLOR = { bg: '#e5e7eb', fg: '#374151' }
