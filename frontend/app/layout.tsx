import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '小yi',
  description: '通过对话调用知识、设备与其他 MCP 工具的通用智能体小yi',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
