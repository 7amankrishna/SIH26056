// Per-route document titles: "Routes · APIx" etc.
import { useEffect } from "react";

export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · APIx`;
  }, [title]);
}
