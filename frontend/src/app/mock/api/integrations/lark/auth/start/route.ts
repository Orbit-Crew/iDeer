import {
  MOCK_API_UNAVAILABLE,
  mockApiDisabled,
} from "@/app/mock/api/mock-api-gate";
export function POST() {
  if (mockApiDisabled()) return MOCK_API_UNAVAILABLE;
  return Response.json({
    verification_url: "https://open.feishu.cn/auth/mock-device",
    device_code: "mock-device-code",
    expires_in: 600,
    user_code: null,
    hint: null,
  });
}
