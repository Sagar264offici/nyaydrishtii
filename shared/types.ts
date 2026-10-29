// Shared TypeScript shapes used by apps/admin and apps/mobile.
// Placeholder entity shapes only — no business logic, no AI/legal reasoning yet.
// Not wired into either app via a package/workspace yet: nothing imports these
// shapes across apps today, so skipping that plumbing until it's actually needed.

export type CaseStatus = 'open' | 'in_review' | 'closed';

export interface Case {
  id: string;
  title: string;
  status: CaseStatus;
  createdAt: string;
}

export interface User {
  id: string;
  name: string;
  role: 'admin' | 'citizen';
}
