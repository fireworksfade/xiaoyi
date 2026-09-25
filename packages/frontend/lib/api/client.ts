const API_ROOT = process.env.NEXT_PUBLIC_API_BASE_URL ?? '/api/backend/api/v1';

const CSRF_STORAGE_KEY = 'xiaoyi.csrf-token';

type Envelope<T> = {
  data: T;
  request_id: string;
};

type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
  };
};

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

export function csrfToken() {
  return window.sessionStorage.getItem(CSRF_STORAGE_KEY);
}

export function setCsrfToken(token: string) {
  window.sessionStorage.setItem(CSRF_STORAGE_KEY, token);
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  csrf = false,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  if (csrf) {
    const token = csrfToken();
    if (!token) throw new ApiError('CSRF_TOKEN_MISSING', '登录状态已失效', 401);
    headers.set('X-CSRF-Token', token);
  }

  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });
  const body = (await response.json().catch(() => ({}))) as
    | Envelope<T>
    | ApiErrorBody;

  if (!response.ok) {
    const error = 'error' in body ? body.error : undefined;
    throw new ApiError(
      error?.code ?? `HTTP_${response.status}`,
      error?.message ?? '请求失败',
      response.status,
    );
  }

  return (body as Envelope<T>).data;
}

export const API_BASE_URL = API_ROOT;
