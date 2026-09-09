import { env } from 'cloudflare:workers';

type RuntimeEnvironment = {
  BACKEND_BASE_URL?: string;
};

const FORWARDED_REQUEST_HEADERS = [
  'accept',
  'content-type',
  'cookie',
  'last-event-id',
  'x-csrf-token',
  'x-request-id',
];

const FORWARDED_RESPONSE_HEADERS = [
  'cache-control',
  'content-disposition',
  'content-type',
  'set-cookie',
  'x-request-id',
];

function backendBaseUrl() {
  const runtime = env as unknown as RuntimeEnvironment;
  return runtime.BACKEND_BASE_URL ?? process.env.BACKEND_BASE_URL;
}

async function proxy(request: Request) {
  const baseUrl = backendBaseUrl();
  if (!baseUrl) {
    return Response.json(
      {
        error: {
          code: 'BACKEND_NOT_CONFIGURED',
          message: '线上后端尚未配置',
          retryable: true,
        },
      },
      { status: 503 },
    );
  }

  const incomingUrl = new URL(request.url);
  const upstreamPath = incomingUrl.pathname.replace(/^\/api\/backend/, '');
  const upstreamUrl = new URL(
    `${upstreamPath}${incomingUrl.search}`,
    `${baseUrl.replace(/\/$/, '')}/`,
  );
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body:
        request.method === 'GET' || request.method === 'HEAD'
          ? undefined
          : request.body,
      redirect: 'manual',
    });
  } catch {
    return Response.json(
      {
        error: {
          code: 'BACKEND_UNREACHABLE',
          message: '后端服务暂时不可用',
          retryable: true,
        },
      },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
