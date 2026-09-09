import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Last-resort recovery for a browser that has retained an incompatible client
 * bundle from a previous deployment. Query failures render in their own cards;
 * this boundary is specifically for a render-time crash that would otherwise
 * leave the page entirely blank.
 */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep diagnostics available to the browser console without exposing them
    // in the UI or sending user data to a third party.
    console.error("APIx application render failed", error, info.componentStack);
  }

  private recover = async () => {
    try {
      for (let index = window.localStorage.length - 1; index >= 0; index -= 1) {
        const key = window.localStorage.key(index);
        if (key?.startsWith("apix-")) window.localStorage.removeItem(key);
      }
      for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
        const key = window.sessionStorage.key(index);
        if (key?.startsWith("apix-")) window.sessionStorage.removeItem(key);
      }
      // There is no current service worker, but unregistering an old one makes
      // upgrades from earlier deployments recoverable instead of incognito-only.
      const registrations = await navigator.serviceWorker?.getRegistrations();
      await Promise.all(registrations?.map((registration) => registration.unregister()) ?? []);
      const keys = await window.caches?.keys();
      await Promise.all(keys?.filter((key) => key.toLowerCase().includes("apix")).map((key) => window.caches.delete(key)) ?? []);
    } catch {
      // Storage can be disabled by privacy settings. A cache-busted navigation
      // is still the best possible recovery path.
    }

    const url = new URL(window.location.href);
    url.searchParams.set("apix_reload", String(Date.now()));
    window.location.replace(url.toString());
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <main className="flex min-h-screen items-center justify-center bg-page p-6">
        <section className="card w-full max-w-lg p-6" role="alert">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-6 w-6 shrink-0 text-amber-600" />
            <div>
              <h1 className="text-lg font-bold text-ink-900">The dashboard needs a clean reload</h1>
              <p className="mt-2 text-sm leading-relaxed text-ink-600">
                This can happen when the browser has an older cached deployment while the API has been updated.
                Reloading will clear only APIx browser data and fetch the current version.
              </p>
              <button type="button" className="btn btn-primary mt-4" onClick={() => void this.recover()}>
                <RefreshCw className="h-4 w-4" /> Clear APIx cache and reload
              </button>
            </div>
          </div>
        </section>
      </main>
    );
  }
}
