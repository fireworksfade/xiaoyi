import { csrfToken, request, setCsrfToken, ApiError } from './client';

export async function ensureDemoSession() {
  const token = csrfToken();
  if (token) {
    try {
      await request('/auth/me');
      return;
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
    }
  }

  const data = await request<{ csrf_token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
  });
  setCsrfToken(data.csrf_token);
}
