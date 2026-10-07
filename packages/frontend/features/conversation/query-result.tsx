type RecordValue = Record<string, unknown>;

export function asRecord(value: unknown): RecordValue | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as RecordValue)
    : null;
}

const labels: Record<string, string> = {
  device_id: '节点',
  device_type: '设备类型',
  firmware_version: '固件版本',
  bucket: '时间',
  avg: '平均值',
  min: '最小值',
  max: '最大值',
  count: '数量',
  sample_count: '有效样本数',
  temperature: '温度',
  rssi: '信号强度',
  received_at: '接收时间',
  timestamp: '日志时间',
  created_at: '诊断时间',
  level: '级别',
  module: '模块',
  message: '日志内容',
  fault_type: '故障类型',
  cause: '原因',
  confidence: '置信度',
  online: '在线',
};

function cell(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  if (
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  )
    return String(value);
  return '—';
}

export function queryData(content: unknown): RecordValue | null {
  const root = asRecord(content);
  const data = asRecord(root?.data);
  if (root?.ok === false || data?.execution_mode !== 'query_plan') return null;
  if (
    !Array.isArray(data.columns) ||
    !data.columns.every((c) => typeof c === 'string')
  )
    return null;
  if (!Array.isArray(data.rows) || !data.rows.every((row) => asRecord(row)))
    return null;
  return data;
}

export function QueryResult({ data }: { data: RecordValue }) {
  const columns = data.columns as string[];
  const rows = data.rows as RecordValue[];
  const metric = asRecord(data.metric_definition);
  const window = asRecord(data.time_window);
  const offset =
    typeof data.utc_offset_minutes === 'number' ? data.utc_offset_minutes : 0;
  const zone = `UTC${offset >= 0 ? '+' : '-'}${String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0')}:${String(Math.abs(offset) % 60).padStart(2, '0')}`;
  function time(value: unknown) {
    if (typeof value !== 'string' || !Number.isFinite(Date.parse(value)))
      return '不限';
    return new Date(Date.parse(value) + offset * 60_000)
      .toISOString()
      .replace('T', ' ')
      .slice(0, 19);
  }
  return (
    <div className="space-y-3" aria-label="历史数据查询结果">
      <p className="font-medium text-slate-700">
        数据查询 · {rows.length} 条结果
      </p>
      {typeof metric?.definition === 'string' ? (
        <p className="text-slate-500">{metric.definition}</p>
      ) : null}
      <p className="text-slate-500">
        节点范围：
        {typeof data.device_id === 'string' ? data.device_id : '全部节点'}
      </p>
      {window ? (
        <p className="text-slate-500">
          {window.kind === 'current'
            ? '当前状态'
            : `时间范围：${time(window.start_utc)} 至 ${time(window.end_utc)}（${zone}，结束时间不含）`}
        </p>
      ) : null}
      {rows.length ? (
        <div className="max-h-80 overflow-auto rounded border border-slate-200">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-50">
              <tr>
                {columns.map((column) => (
                  <th
                    key={column}
                    className="whitespace-nowrap px-3 py-2 font-medium text-slate-600"
                  >
                    {labels[column] ?? column}
                    {['avg', 'min', 'max', 'temperature', 'rssi'].includes(
                      column,
                    ) && typeof metric?.unit === 'string'
                      ? `（${metric.unit}）`
                      : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index} className="border-t border-slate-100">
                  {columns.map((column) => (
                    <td
                      key={column}
                      className="max-w-xs break-words px-3 py-2 text-slate-700"
                    >
                      {cell(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-slate-500">该范围内没有匹配数据。</p>
      )}
      {data.truncated === true ? (
        <p className="text-amber-700">
          结果已达到返回上限，请缩小时间或节点范围。
        </p>
      ) : null}
      {data.cells_truncated === true ? (
        <p className="text-amber-700">部分长文本已截断。</p>
      ) : null}
      <details className="text-slate-500">
        <summary className="cursor-pointer">查看查询 SQL 与参数</summary>
        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all text-[11px]">
          {cell(data.sql)}
          {'\n'}
          {JSON.stringify(data.parameters, null, 2)}
        </pre>
      </details>
    </div>
  );
}

export function RetrievalStatus({ content }: { content: unknown }) {
  const data = asRecord(asRecord(content)?.data);
  if (!data || typeof data.embedding_provider !== 'string') return null;
  const reranker = asRecord(data.reranker);
  const providers: Record<string, string> = {
    dashscope: 'API',
    dashscope_remote: 'API',
    qwen3_local: '本地 Qwen 0.6B',
    hash: 'Hash 兜底',
    weighted: '加权排序兜底',
    local_lexical: '本地关键词',
    disabled: '未启用',
  };
  const fallback =
    ['qwen3_local', 'hash', 'local_lexical'].includes(
      data.embedding_provider,
    ) || reranker?.fallback === true;
  return (
    <p
      className={fallback ? 'text-amber-700' : 'text-slate-500'}
      aria-label="检索服务状态"
    >
      向量检索：{providers[data.embedding_provider] ?? data.embedding_provider}
      {typeof reranker?.provider === 'string'
        ? ` · 重排：${providers[reranker.provider] ?? reranker.provider}`
        : ''}
      {fallback ? ' · 已使用兜底' : ''}
    </p>
  );
}
