"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { confirmDesktopLogin, getDesktopLoginApproval } from "./api";

export function useDesktopLogin(loginId: string) {
  const approval = useQuery({
    queryKey: ["desktop-login", loginId],
    queryFn: () => getDesktopLoginApproval(loginId),
    retry: false,
    refetchOnWindowFocus: false,
    gcTime: 0,
  });
  const confirmation = useMutation({
    mutationFn: () => confirmDesktopLogin(loginId),
  });
  return { approval, confirmation };
}
