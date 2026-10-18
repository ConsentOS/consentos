import type { User } from '../types/api';

/** Owners and admins can publish, roll back and discard; others only edit. */
export function canPublish(user: Pick<User, 'role'> | null | undefined): boolean {
  return user?.role === 'owner' || user?.role === 'admin';
}
