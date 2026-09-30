/** Private MessagePort per request; backend credentials stay in the Harness Host. */
export function harnessBridge() {
  if (typeof window === 'undefined' || window.parent === window) return null;
  const query = new URLSearchParams(window.location.search);
  const nonce = query.get('xiaoyi_harness_bridge');
  const origin = query.get('xiaoyi_parent_origin');
  if (!nonce || !origin) return null;
  // Desktop's custom scheme may serialize its origin as "null".
  if (origin !== 'null' && origin !== 'dsh-app://app') {
    try {
      const url = new URL(origin);
      if (!['http:', 'https:'].includes(url.protocol) || url.origin !== origin) return null;
    } catch { return null; }
  }
  return { nonce, origin };
}

async function encodeBody(body: BodyInit | null | undefined) {
  if (body == null) return {};
  if (typeof body === 'string') return { body };
  if (body instanceof URLSearchParams) return { body: body.toString() };
  if (!(body instanceof FormData)) throw new Error('Harness 请求正文格式不支持');
  const form = [];
  for (const [name, value] of body.entries()) {
    if (typeof value === 'string') form.push({ name, value });
    else {
      const bytes = new Uint8Array(await value.arrayBuffer());
      let binary = '';
      for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
      form.push({ name, file: { name: value.name, type: value.type, base64: btoa(binary) } });
    }
  }
  return { form };
}

export async function bridgeFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const bridge = harnessBridge();
  if (!bridge) throw new Error('Harness bridge unavailable');
  const request = { path, method: init.method ?? 'GET', ...await encodeBody(init.body) };
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    let controller: ReadableStreamDefaultController<Uint8Array> | undefined;
    let received = false;
    let queuedAck = false;
    const timeout = window.setTimeout(() => cancel(new Error('Harness 请求超时')), 30000);
    const cleanup = () => { clearTimeout(timeout); init.signal?.removeEventListener('abort', abort); channel.port1.close(); };
    const cancel = (error: Error) => {
      channel.port1.postMessage({ type: 'cancel' });
      if (received) controller?.error(error); else reject(error);
      cleanup();
    };
    const abort = () => cancel(new Error('请求已取消'));
    if (init.signal?.aborted) { abort(); return; }
    init.signal?.addEventListener('abort', abort, { once: true });
    channel.port1.onmessage = event => {
      const data = event.data;
      if (data.type === 'headers') {
        received = true;
        clearTimeout(timeout);
        const stream = new ReadableStream<Uint8Array>({
          start(value) { controller = value; },
          pull() { if (queuedAck) { queuedAck = false; channel.port1.postMessage({ type: 'ack' }); } },
          cancel() { channel.port1.postMessage({ type: 'cancel' }); cleanup(); },
        });
        resolve(new Response(stream, { status: data.status, headers: data.headers }));
      } else if (data.type === 'chunk') {
        controller?.enqueue(data.bytes);
        if ((controller?.desiredSize ?? 0) > 0) channel.port1.postMessage({ type: 'ack' });
        else queuedAck = true;
      } else if (data.type === 'end') { controller?.close(); cleanup(); }
      else if (data.type === 'error') cancel(new Error(data.message));
    };
    channel.port1.start();
    window.parent.postMessage({ type: 'xiaoyi-harness-request', nonce: bridge.nonce, request }, bridge.origin === 'null' ? '*' : bridge.origin, [channel.port2]);
  });
}
