'use client';

import { useEffect, useState } from 'react';
import {
  Boxes,
  CheckCircle2,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  TriangleAlert,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ApiError,
  createMCPServer,
  deleteMCPServer,
  ensureDemoSession,
  getModelConfiguration,
  listMCPServers,
  listMCPTools,
  refreshMCPTools,
  saveModelConfiguration,
  testMCPServer,
  testModelConfiguration,
  updateMCPServer,
  updateMCPTool,
  type MCPServer as MCPServerType,
  type MCPTool,
  type ModelConfiguration,
} from '@/lib/api';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

const emptyModel: ModelConfiguration = {
  provider_name: 'OpenAI',
  base_url: 'https://api.openai.com/v1',
  model_name: 'gpt-5.4-mini',
  api_mode: 'responses',
  api_key_configured: false,
  api_key_hint: null,
  enabled: false,
};

const purposeLabels: Record<MCPServerType['purpose'], string> = {
  knowledge: '知识库',
  iot: '物联网',
  generic: '通用',
};

function errorText(error: unknown) {
  if (error instanceof ApiError) return `${error.message}（${error.code}）`;
  return error instanceof Error ? error.message : '请求失败';
}

export function SettingsSheet({ open, onOpenChange }: Props) {
  const [tab, setTab] = useState('model');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{
    kind: 'success' | 'error';
    text: string;
  } | null>(null);
  const [model, setModel] = useState<ModelConfiguration>(emptyModel);
  const [apiKey, setApiKey] = useState('');
  const [servers, setServers] = useState<MCPServerType[]>([]);
  const [canManageMCP, setCanManageMCP] = useState(true);
  const [tools, setTools] = useState<Record<string, MCPTool[]>>({});
  const [expandedServer, setExpandedServer] = useState<string | null>(null);
  const [addingServer, setAddingServer] = useState(false);
  const [newServer, setNewServer] = useState({
    server_key: '',
    name: '',
    url: '',
    purpose: 'generic' as MCPServerType['purpose'],
    credential: '',
  });

  async function loadSettings() {
    setLoading(true);
    setNotice(null);
    try {
      await ensureDemoSession();
      const modelConfig = await getModelConfiguration();
      setModel(modelConfig);
      try {
        const serverPage = await listMCPServers();
        setServers(serverPage.items);
        setCanManageMCP(true);
      } catch (error) {
        if (error instanceof ApiError && error.code === 'ADMIN_REQUIRED') {
          setServers([]);
          setCanManageMCP(false);
        } else {
          throw error;
        }
      }
    } catch (error) {
      setNotice({ kind: 'error', text: errorText(error) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => void loadSettings(), 0);
    return () => window.clearTimeout(timer);
  }, [open]);

  async function saveModel() {
    setBusy('model-save');
    setNotice(null);
    try {
      const saved = await saveModelConfiguration({
        provider_name: model.provider_name,
        base_url: model.base_url,
        model_name: model.model_name,
        api_mode: model.api_mode,
        api_key: apiKey || undefined,
        enabled: model.enabled,
      });
      setModel(saved);
      setApiKey('');
      setNotice({
        kind: 'success',
        text: '模型配置已保存，下次对话开始生效。',
      });
      return true;
    } catch (error) {
      setNotice({ kind: 'error', text: errorText(error) });
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function testModel() {
    setBusy('model-test');
    setNotice(null);
    try {
      if (apiKey && !(await saveModel())) return;
      const result = await testModelConfiguration();
      setNotice({
        kind: result.model_available ? 'success' : 'error',
        text: result.model_available
          ? `连接成功，已找到 ${result.model_name}。`
          : `连接成功，但模型列表中没有 ${result.model_name}。`,
      });
    } catch (error) {
      setNotice({ kind: 'error', text: errorText(error) });
    } finally {
      setBusy(null);
    }
  }

  async function reloadServers() {
    const page = await listMCPServers();
    setServers(page.items);
  }

  async function addServer() {
    setBusy('server-add');
    setNotice(null);
    try {
      const created = await createMCPServer({
        ...newServer,
        credential: newServer.credential || undefined,
      });
      setServers((current) => [created, ...current]);
      setNewServer({
        server_key: '',
        name: '',
        url: '',
        purpose: 'generic',
        credential: '',
      });
      setAddingServer(false);
      setNotice({
        kind: 'success',
        text: 'MCP 服务已添加，请先测试连接并刷新工具。',
      });
    } catch (error) {
      setNotice({ kind: 'error', text: errorText(error) });
    } finally {
      setBusy(null);
    }
  }

  async function runServerAction(
    server: MCPServerType,
    action: 'test' | 'refresh',
  ) {
    setBusy(`${action}-${server.id}`);
    setNotice(null);
    try {
      if (action === 'test') {
        const result = await testMCPServer(server.id);
        setNotice({
          kind: 'success',
          text: `连接成功，发现 ${result.tool_count} 个工具。`,
        });
      } else {
        const result = await refreshMCPTools(server.id);
        setTools((current) => ({ ...current, [server.id]: result.items }));
        setExpandedServer(server.id);
        setNotice({
          kind: 'success',
          text: `工具目录已刷新，共 ${result.items.length} 个。`,
        });
      }
      await reloadServers();
    } catch (error) {
      setNotice({ kind: 'error', text: errorText(error) });
    } finally {
      setBusy(null);
    }
  }

  async function toggleServer(server: MCPServerType, enabled: boolean) {
    setBusy(`toggle-${server.id}`);
    try {
      const updated = await updateMCPServer(server.id, { enabled });
      setServers((current) =>
        current.map((item) => (item.id === server.id ? updated : item)),
      );
    } catch (error) {
      setNotice({ kind: 'error', text: errorText(error) });
    } finally {
      setBusy(null);
    }
  }

  async function showTools(server: MCPServerType) {
    if (expandedServer === server.id) {
      setExpandedServer(null);
      return;
    }
    setBusy(`tools-${server.id}`);
    try {
      const page = await listMCPTools(server.id);
      setTools((current) => ({ ...current, [server.id]: page.items }));
      setExpandedServer(server.id);
    } catch (error) {
      setNotice({ kind: 'error', text: errorText(error) });
    } finally {
      setBusy(null);
    }
  }

  async function changeTool(
    server: MCPServerType,
    tool: MCPTool,
    enabled: boolean,
    riskPolicy = tool.risk_policy,
  ) {
    const effectivePolicy = enabled
      ? riskPolicy === 'disabled'
        ? 'read_only'
        : riskPolicy
      : 'disabled';
    setBusy(`tool-${tool.id}`);
    try {
      const updated = await updateMCPTool(server.id, tool.id, {
        enabled,
        risk_policy: effectivePolicy,
      });
      setTools((current) => ({
        ...current,
        [server.id]: (current[server.id] ?? []).map((item) =>
          item.id === tool.id ? updated : item,
        ),
      }));
    } catch (error) {
      setNotice({ kind: 'error', text: errorText(error) });
    } finally {
      setBusy(null);
    }
  }

  async function removeServer(server: MCPServerType) {
    if (
      !window.confirm(`删除 MCP 服务“${server.name}”？相关待执行授权会失效。`)
    )
      return;
    setBusy(`delete-${server.id}`);
    try {
      await deleteMCPServer(server.id);
      setServers((current) => current.filter((item) => item.id !== server.id));
      setNotice({ kind: 'success', text: 'MCP 服务已删除。' });
    } catch (error) {
      setNotice({ kind: 'error', text: errorText(error) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 sm:max-w-2xl">
        <SheetHeader className="border-b border-slate-200 px-6 py-5">
          <SheetTitle>设置</SheetTitle>
          <SheetDescription>配置小yi使用的模型和可调用工具。</SheetDescription>
        </SheetHeader>
        <Tabs
          value={tab}
          onValueChange={(value) => setTab(String(value))}
          className="min-h-0 flex-1"
        >
          <TabsList
            variant="line"
            className="mx-6 mt-3 w-[calc(100%-3rem)] justify-start border-b border-slate-200"
          >
            <TabsTrigger value="model" className="flex-none px-3">
              <KeyRound />
              模型 API
            </TabsTrigger>
            <TabsTrigger value="mcp" className="flex-none px-3">
              <Boxes />
              MCP 服务
            </TabsTrigger>
          </TabsList>

          {notice ? (
            <div
              className={`mx-6 mt-4 flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm ${notice.kind === 'success' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}
            >
              {notice.kind === 'success' ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
              ) : (
                <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              )}
              {notice.text}
            </div>
          ) : null}

          {loading ? (
            <div className="grid flex-1 place-items-center">
              <Loader2 className="size-5 animate-spin text-slate-400" />
            </div>
          ) : (
            <>
              <TabsContent
                value="model"
                className="min-h-0 overflow-y-auto px-6 py-5"
              >
                <div className="space-y-5">
                  <div className="flex items-center justify-between rounded-lg border border-slate-200 p-4">
                    <div>
                      <p className="font-medium text-slate-900">
                        启用自定义模型
                      </p>
                      <p className="mt-1 text-sm text-slate-500">
                        关闭时使用服务器默认运行模式。
                      </p>
                    </div>
                    <Switch
                      checked={model.enabled}
                      onCheckedChange={(checked) =>
                        setModel((current) => ({
                          ...current,
                          enabled: checked,
                        }))
                      }
                    />
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="provider-name">提供商名称</Label>
                      <Input
                        id="provider-name"
                        value={model.provider_name}
                        onChange={(event) =>
                          setModel((current) => ({
                            ...current,
                            provider_name: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>接口模式</Label>
                      <Select
                        value={model.api_mode}
                        onValueChange={(value) =>
                          setModel((current) => ({
                            ...current,
                            api_mode: value as ModelConfiguration['api_mode'],
                          }))
                        }
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="responses">
                            Responses API
                          </SelectItem>
                          <SelectItem value="chat_completions">
                            Chat Completions
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="base-url">API 地址</Label>
                    <Input
                      id="base-url"
                      value={model.base_url}
                      placeholder="https://api.openai.com/v1"
                      onChange={(event) =>
                        setModel((current) => ({
                          ...current,
                          base_url: event.target.value,
                        }))
                      }
                    />
                    <p className="text-xs text-slate-400">
                      支持 HTTPS 的 OpenAI 兼容接口；本地开发可使用 localhost。
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="model-name">模型名称</Label>
                    <Input
                      id="model-name"
                      value={model.model_name}
                      placeholder="gpt-5.4-mini"
                      onChange={(event) =>
                        setModel((current) => ({
                          ...current,
                          model_name: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="api-key">API Key</Label>
                    <Input
                      id="api-key"
                      type="password"
                      value={apiKey}
                      placeholder={model.api_key_hint ?? '输入 API Key'}
                      autoComplete="new-password"
                      onChange={(event) => setApiKey(event.target.value)}
                    />
                    <p className="text-xs text-slate-400">
                      {model.api_key_configured
                        ? `已安全保存 ${model.api_key_hint}，留空不会覆盖。`
                        : '密钥仅加密保存在后端，不会显示在页面或发送给 MCP。'}
                    </p>
                  </div>
                  <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
                    <Button
                      variant="outline"
                      disabled={
                        busy !== null || (!model.api_key_configured && !apiKey)
                      }
                      onClick={() => void testModel()}
                    >
                      {busy === 'model-test' ? (
                        <Loader2 className="animate-spin" />
                      ) : null}
                      测试连接
                    </Button>
                    <Button
                      disabled={
                        busy !== null ||
                        !model.provider_name ||
                        !model.base_url ||
                        !model.model_name
                      }
                      onClick={() => void saveModel()}
                    >
                      {busy === 'model-save' ? (
                        <Loader2 className="animate-spin" />
                      ) : null}
                      保存配置
                    </Button>
                  </div>
                </div>
              </TabsContent>

              <TabsContent
                value="mcp"
                className="min-h-0 overflow-y-auto px-6 py-5"
              >
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <p className="font-medium text-slate-900">MCP 服务</p>
                    <p className="mt-1 text-sm text-slate-500">
                      添加服务、发现工具并配置调用权限。
                    </p>
                  </div>
                  {canManageMCP ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setAddingServer((value) => !value)}
                    >
                      <Plus />
                      添加
                    </Button>
                  ) : null}
                </div>
                {addingServer ? (
                  <div className="mb-4 space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label htmlFor="server-name">显示名称</Label>
                        <Input
                          id="server-name"
                          value={newServer.name}
                          onChange={(event) =>
                            setNewServer((current) => ({
                              ...current,
                              name: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="server-key">服务标识</Label>
                        <Input
                          id="server-key"
                          placeholder="my-mcp-server"
                          value={newServer.server_key}
                          onChange={(event) =>
                            setNewServer((current) => ({
                              ...current,
                              server_key: event.target.value.toLowerCase(),
                            }))
                          }
                        />
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="server-url">Streamable HTTP 地址</Label>
                      <Input
                        id="server-url"
                        placeholder="https://example.com/mcp"
                        value={newServer.url}
                        onChange={(event) =>
                          setNewServer((current) => ({
                            ...current,
                            url: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label>用途</Label>
                        <Select
                          value={newServer.purpose}
                          onValueChange={(value) =>
                            setNewServer((current) => ({
                              ...current,
                              purpose: value as MCPServerType['purpose'],
                            }))
                          }
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="generic">通用</SelectItem>
                            <SelectItem value="knowledge">知识库</SelectItem>
                            <SelectItem value="iot">物联网</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="server-token">
                          Bearer Token（可选）
                        </Label>
                        <Input
                          id="server-token"
                          type="password"
                          value={newServer.credential}
                          onChange={(event) =>
                            setNewServer((current) => ({
                              ...current,
                              credential: event.target.value,
                            }))
                          }
                        />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setAddingServer(false)}
                      >
                        取消
                      </Button>
                      <Button
                        size="sm"
                        disabled={
                          busy !== null ||
                          !newServer.name ||
                          !newServer.server_key ||
                          !newServer.url
                        }
                        onClick={() => void addServer()}
                      >
                        {busy === 'server-add' ? (
                          <Loader2 className="animate-spin" />
                        ) : null}
                        保存服务
                      </Button>
                    </div>
                  </div>
                ) : null}

                <div className="space-y-3">
                  {servers.map((server) => (
                    <section
                      key={server.id}
                      className="rounded-lg border border-slate-200 bg-white"
                    >
                      <div className="flex items-start gap-3 p-4">
                        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600">
                          <Server className="size-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium text-slate-900">
                              {server.name}
                            </p>
                            <Badge variant="outline" className="font-normal">
                              {purposeLabels[server.purpose]}
                            </Badge>
                            <span
                              className={`size-2 rounded-full ${server.connection_status === 'connected' ? 'bg-emerald-500' : server.connection_status === 'failed' ? 'bg-red-500' : 'bg-slate-300'}`}
                            />
                          </div>
                          <p className="mt-1 truncate text-xs text-slate-400">
                            {server.url}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            {server.server_key} · 工具目录 v
                            {server.tools_version}
                          </p>
                        </div>
                        <Switch
                          checked={server.enabled}
                          disabled={busy !== null}
                          onCheckedChange={(checked) =>
                            void toggleServer(server, checked)
                          }
                        />
                      </div>
                      <div className="flex flex-wrap items-center gap-1 border-t border-slate-100 px-3 py-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy !== null}
                          onClick={() => void runServerAction(server, 'test')}
                        >
                          {busy === `test-${server.id}` ? (
                            <Loader2 className="animate-spin" />
                          ) : null}
                          测试
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy !== null}
                          onClick={() =>
                            void runServerAction(server, 'refresh')
                          }
                        >
                          <RefreshCw />
                          刷新工具
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy !== null}
                          onClick={() => void showTools(server)}
                        >
                          工具权限
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="ml-auto text-red-600 hover:text-red-700"
                          disabled={busy !== null}
                          onClick={() => void removeServer(server)}
                        >
                          <Trash2 />
                          删除
                        </Button>
                      </div>
                      {expandedServer === server.id ? (
                        <div className="border-t border-slate-100 bg-slate-50 px-4 py-3">
                          {(tools[server.id] ?? []).length ? (
                            (tools[server.id] ?? []).map((tool) => (
                              <div
                                key={tool.id}
                                className="flex items-center gap-3 border-b border-slate-200/70 py-3 last:border-0"
                              >
                                <div className="min-w-0 flex-1">
                                  <p className="truncate text-sm font-medium text-slate-700">
                                    {tool.original_name}
                                  </p>
                                  <p className="mt-0.5 line-clamp-1 text-xs text-slate-400">
                                    {tool.description || '暂无描述'}
                                  </p>
                                </div>
                                <Select
                                  value={tool.risk_policy}
                                  disabled={!tool.enabled || busy !== null}
                                  onValueChange={(value) =>
                                    void changeTool(
                                      server,
                                      tool,
                                      true,
                                      value as MCPTool['risk_policy'],
                                    )
                                  }
                                >
                                  <SelectTrigger size="sm" className="w-32">
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="read_only">
                                      只读
                                    </SelectItem>
                                    <SelectItem value="proposal_only">
                                      仅提案
                                    </SelectItem>
                                    <SelectItem value="approval_required">
                                      需审批
                                    </SelectItem>
                                  </SelectContent>
                                </Select>
                                <Switch
                                  size="sm"
                                  checked={tool.enabled}
                                  disabled={busy !== null}
                                  onCheckedChange={(checked) =>
                                    void changeTool(server, tool, checked)
                                  }
                                />
                              </div>
                            ))
                          ) : (
                            <p className="py-3 text-center text-sm text-slate-400">
                              还没有工具，请先刷新工具目录。
                            </p>
                          )}
                        </div>
                      ) : null}
                    </section>
                  ))}
                  {!servers.length ? (
                    <div className="rounded-lg border border-dashed border-slate-300 px-5 py-10 text-center text-sm text-slate-400">
                      {canManageMCP
                        ? '还没有 MCP 服务'
                        : '只有管理员可以配置 MCP 服务。你的模型 API 设置仍可独立使用。'}
                    </div>
                  ) : null}
                </div>
              </TabsContent>
            </>
          )}
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}
