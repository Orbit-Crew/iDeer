"use client";

import { useState } from "react";

import { useDesktopLogin } from "@/core/devices/use-desktop-login";

export function DesktopLoginConfirmation({
  loginId,
  account,
}: {
  loginId: string;
  account: string;
}) {
  const [ownDevice, setOwnDevice] = useState(false);
  const { approval, confirmation } = useDesktopLogin(loginId);
  const device = approval.data;
  const busy = confirmation.isPending;
  const confirmed = confirmation.isSuccess;

  return (
    <main className="mx-auto max-w-lg space-y-6 p-8">
      <h1 className="type-page-title">绑定 iDeer Desktop</h1>
      <p>当前账号：{account}</p>
      {approval.isPending && <p role="status">正在读取设备请求…</p>}
      {(approval.isError || confirmation.isError) && (
        <p role="alert">
          登录请求已过期、已使用或属于其他账号，请从 Desktop 重新发起。
        </p>
      )}
      {device && !confirmed && (
        <>
          <p>设备：{device.name}</p>
          <p>
            设备校验码：<code>{device.verification}</code>
          </p>
          <p>
            请核对 Desktop
            上的设备名称和校验码。确认后，这台设备可按本机授权接收该账号的任务。
          </p>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={ownDevice}
              onChange={(event) => setOwnDevice(event.target.checked)}
            />
            我确认这是我本人发起登录并持有的设备
          </label>
          <button
            type="button"
            className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
            disabled={!ownDevice || busy || device.state !== "pending"}
            onClick={() => {
              if (ownDevice) confirmation.mutate();
            }}
          >
            {busy ? "确认中…" : "确认绑定本人设备"}
          </button>
          {device.state !== "pending" && (
            <p>此请求已确认或已使用，请返回 Desktop 查看结果。</p>
          )}
        </>
      )}
      {confirmed && (
        <p role="status">
          本人设备已确认。请返回 Desktop
          等待完成交换；浏览器登录本身不会建立桌面业务会话。
        </p>
      )}
    </main>
  );
}
