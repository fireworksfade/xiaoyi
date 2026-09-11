'use client';

import { type SyntheticEvent, useState } from 'react';
import { BookCheck, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { addVerifiedFaultCase, ensureDemoSession, type ToolSource } from '@/lib/api';

type CaseForm = {
  deviceId: string;
  faultType: string;
  faultName: string;
  symptoms: string;
  logs: string;
  cause: string;
  solution: string;
};

const EMPTY_FORM: CaseForm = {
  deviceId: 'ESP32_05',
  faultType: '',
  faultName: '',
  symptoms: '',
  logs: '',
  cause: '',
  solution: '',
};

export function CaseDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  toolSources: ToolSource[];
}) {
  const [serverId, setServerId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [form, setForm] = useState<CaseForm>(EMPTY_FORM);

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    const serviceId = serverId || props.toolSources[0]?.id;
    if (!serviceId) {
      setError('没有可用的诊断 MCP 服务');
      return;
    }
    const symptoms = form.symptoms
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    const logs = form.logs
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!symptoms.length || !logs.length) {
      setError('现象和日志至少各填写一行');
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await ensureDemoSession();
      const result = await addVerifiedFaultCase(serviceId, {
        device_id: form.deviceId.trim(),
        fault_type: form.faultType.trim(),
        fault_name: form.faultName.trim(),
        symptoms,
        logs,
        cause: form.cause.trim(),
        solution: form.solution.trim(),
        verified: true,
      });
      setSuccess(`案例 ${result.fault_id} 已写入并加入检索`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '案例写入失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        if (!busy) props.onOpenChange(open);
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>录入已验证故障案例</DialogTitle>
            <DialogDescription>
              仅录入已经人工复核的原因和解决方案，提交后会参与后续诊断检索。
            </DialogDescription>
          </DialogHeader>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label htmlFor="case-service" className="text-sm font-medium text-slate-700">
                诊断服务
              </label>
              <Select
                value={serverId || null}
                onValueChange={(value) => setServerId(String(value ?? ''))}
              >
                <SelectTrigger id="case-service" className="mt-1.5 w-full">
                  <SelectValue placeholder="选择诊断 MCP 服务" />
                </SelectTrigger>
                <SelectContent align="start">
                  {props.toolSources.map((source) => (
                    <SelectItem key={source.id} value={source.id}>
                      {source.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label htmlFor="case-device" className="text-sm font-medium text-slate-700">
                设备编号
              </label>
              <Input
                id="case-device"
                required
                className="mt-1.5"
                value={form.deviceId}
                onChange={(event) =>
                  setForm((current) => ({ ...current, deviceId: event.target.value }))
                }
              />
            </div>
            <div>
              <label htmlFor="case-type" className="text-sm font-medium text-slate-700">
                故障类型
              </label>
              <Input
                id="case-type"
                required
                className="mt-1.5"
                placeholder="例如 mqtt_timeout"
                value={form.faultType}
                onChange={(event) =>
                  setForm((current) => ({ ...current, faultType: event.target.value }))
                }
              />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="case-name" className="text-sm font-medium text-slate-700">
                案例名称
              </label>
              <Input
                id="case-name"
                required
                className="mt-1.5"
                value={form.faultName}
                onChange={(event) =>
                  setForm((current) => ({ ...current, faultName: event.target.value }))
                }
              />
            </div>
            <div>
              <label htmlFor="case-symptoms" className="text-sm font-medium text-slate-700">
                已确认现象
              </label>
              <Textarea
                id="case-symptoms"
                required
                className="mt-1.5 min-h-24"
                placeholder="每行一条"
                value={form.symptoms}
                onChange={(event) =>
                  setForm((current) => ({ ...current, symptoms: event.target.value }))
                }
              />
            </div>
            <div>
              <label htmlFor="case-logs" className="text-sm font-medium text-slate-700">
                关键日志
              </label>
              <Textarea
                id="case-logs"
                required
                className="mt-1.5 min-h-24"
                placeholder="每行一条"
                value={form.logs}
                onChange={(event) =>
                  setForm((current) => ({ ...current, logs: event.target.value }))
                }
              />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="case-cause" className="text-sm font-medium text-slate-700">
                已验证原因
              </label>
              <Textarea
                id="case-cause"
                required
                className="mt-1.5 min-h-20"
                value={form.cause}
                onChange={(event) =>
                  setForm((current) => ({ ...current, cause: event.target.value }))
                }
              />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="case-solution" className="text-sm font-medium text-slate-700">
                已验证解决方案
              </label>
              <Textarea
                id="case-solution"
                required
                className="mt-1.5 min-h-20"
                value={form.solution}
                onChange={(event) =>
                  setForm((current) => ({ ...current, solution: event.target.value }))
                }
              />
            </div>
          </div>
          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
          {success ? <p className="mt-3 text-sm text-emerald-700">{success}</p> : null}
          <DialogFooter className="mt-5">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => props.onOpenChange(false)}
            >
              关闭
            </Button>
            <Button type="submit" disabled={busy || !serverId}>
              {busy ? <Loader2 className="animate-spin" /> : <BookCheck />}
              确认已人工验证并写入
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
