export function MemoryContent({
  content,
  applicability,
}: {
  content: Record<string, unknown>;
  applicability: Record<string, unknown>;
}) {
  function valueText(value: unknown): string {
    if (typeof value === 'string') return value;
    if (typeof value === 'number' || typeof value === 'boolean')
      return String(value);
    if (Array.isArray(value)) return value.map(valueText).join('；');
    if (value && typeof value === 'object') {
      const row = value as Record<string, unknown>;
      if (typeof row.text === 'string') return row.text;
      return Object.entries(row)
        .map(([key, val]) => `${key}：${valueText(val)}`)
        .join('；');
    }
    return '—';
  }
  const labels: Record<string, string> = {
    claims: '认识',
    procedure: '步骤',
    limitations: '限制',
    observations: '观察事实',
    actions: '已执行动作',
    outcome: '动作结果',
    root_cause_status: '根因状态',
    unresolved_items: '未解决项',
  };
  const states: Record<string, string> = {
    hypothesis: '假设',
    observed: '观察事实',
    user_asserted: '用户陈述',
    corroborated: '有证据支持',
    contradicted: '有反例',
    unknown: '未确认',
    succeeded: '验证成功',
    failed: '明确失败',
    pending: '待确认结果',
    inconclusive: '结果不明',
    not_executed: '未执行',
  };
  return (
    <dl className="space-y-2">
      <div>
        <dt className="font-medium">适用条件</dt>
        <dd>{valueText(applicability)}</dd>
      </div>
      {Object.entries(labels)
        .filter(([key]) => key in content)
        .map(([key, label]) => (
          <div key={key}>
            <dt className="font-medium">{label}</dt>
            <dd>
              {Array.isArray(content[key]) ? (
                <ul className="space-y-1">
                  {(content[key] as unknown[]).map((value, index) => {
                    const status =
                      value && typeof value === 'object'
                        ? (value as Record<string, unknown>).epistemic_status
                        : null;
                    return (
                      <li key={index}>
                        {valueText(value)}
                        {typeof status === 'string'
                          ? `（${states[status] ?? status}）`
                          : ''}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                (states[valueText(content[key])] ?? valueText(content[key]))
              )}
            </dd>
          </div>
        ))}
    </dl>
  );
}
