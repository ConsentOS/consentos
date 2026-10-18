import type { User } from '../types/api';

/** Owners and admins can publish, roll back and discard; others only edit. */
export function canPublish(user: Pick<User, 'role'> | null | undefined): boolean {
  return user?.role === 'owner' || user?.role === 'admin';
}

/** Everyone but viewers can change a site and run checks on it. */
export function canEdit(user: Pick<User, 'role'> | null | undefined): boolean {
  return user?.role === 'owner' || user?.role === 'admin' || user?.role === 'editor';
}
