import { redirect } from "next/navigation";

import { QueryClientProvider } from "@/components/query-client-provider";
import { getServerSideUser } from "@/core/auth/server";

import { DesktopLoginConfirmation } from "./confirmation";

export const dynamic = "force-dynamic";

export default async function DesktopLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ login_id?: string }>;
}) {
  const { login_id: loginId } = await searchParams;
  if (!loginId || !/^[A-Za-z0-9-]{1,64}$/.test(loginId)) {
    return (
      <main className="mx-auto max-w-lg p-8">
        登录请求无效，请从 iDeer Desktop 重新发起。
      </main>
    );
  }
  const result = await getServerSideUser();
  if (result.tag === "unauthenticated") {
    redirect(
      `/login?next=${encodeURIComponent(`/desktop-login?login_id=${loginId}`)}`,
    );
  }
  if (result.tag === "needs_setup" || result.tag === "system_setup_required") {
    redirect("/setup");
  }
  if (result.tag !== "authenticated") {
    return (
      <main className="mx-auto max-w-lg p-8">
        平台认证暂不可用，请稍后刷新。此设备尚未绑定。
      </main>
    );
  }
  return (
    <QueryClientProvider>
      <DesktopLoginConfirmation loginId={loginId} account={result.user.email} />
    </QueryClientProvider>
  );
}
