import '@testing-library/jest-dom/vitest';

// api.ts 从 sessionStorage 读取 CSRF token；测试中提供空实现兜底。
if (!window.sessionStorage.getItem) {
  window.sessionStorage.getItem = () => null;
}
