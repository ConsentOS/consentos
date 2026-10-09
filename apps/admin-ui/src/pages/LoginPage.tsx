import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { useAuthStore } from '../stores/auth';
import { getAuthUiProvider } from '../extensions/registry';
import { Button } from '../components/ui/button.tsx';
import { Input } from '../components/ui/input.tsx';
import { FormField } from '../components/ui/form-field.tsx';
import { Alert } from '../components/ui/alert.tsx';
import { Card, CardContent } from '../components/ui/card.tsx';

export default function LoginPage() {
  const { isAuthenticated, isLoading, login, providerSessionUnprovisioned } =
    useAuthStore();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  if (isAuthenticated) {
    return <Navigate to="/sites" replace />;
  }

  const provider = getAuthUiProvider();
  if (provider) {
    const ProviderLogin = provider.LoginComponent;
    return <ProviderLogin unprovisioned={providerSessionUnprovisioned} />;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await login(email, password);
      navigate('/sites');
    } catch {
      setError('Invalid email or password');
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-md">
        <Card>
          <CardContent className="px-8 py-10">
            <div className="mb-2 flex items-center justify-center gap-3">
              <img src="/logo-mark.svg" alt="" width="32" height="32" aria-hidden="true" />
              <h1 className="font-heading text-2xl font-semibold text-foreground">
                <span className="text-primary">Consent</span>
                <span className="text-action">OS</span>
              </h1>
            </div>
            <p className="mb-8 text-center text-sm text-text-secondary">
              Sign in to manage your consent platform
            </p>

            <form onSubmit={handleSubmit} className="space-y-5">
              {error && <Alert variant="error">{error}</Alert>}

              <FormField label="Email address" htmlFor="email">
                <Input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </FormField>

              <FormField label="Password" htmlFor="password">
                <Input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                />
              </FormField>

              <Button type="submit" disabled={isLoading} className="w-full">
                {isLoading ? 'Signing in...' : 'Sign in'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
