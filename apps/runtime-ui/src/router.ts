/**
 * The address bar is the app's only navigation state. That's what lets a person reload, share a link, and land
 * back on their page after signing in again. A library would add weight for what these few paths need.
 */
import { useMemo, useSyncExternalStore } from "react";

export type Route =
  | { name: "home" }
  | { name: "view"; view: string; q: string; page: number }
  | { name: "new"; entity: string; from: string | undefined }
  | { name: "record"; entity: string; id: string; from: string | undefined }
  | { name: "edit"; entity: string; id: string; from: string | undefined }
  | { name: "calculator"; calculator: string }
  | { name: "more" }
  | { name: "missing" };

function parts(pathname: string): string[] | null {
  try {
    return pathname.split("/").filter(Boolean).map(decodeURIComponent);
  } catch {
    return null;
  }
}

export function parseRoute(pathname: string, search: string): Route {
  const query = new URLSearchParams(search);
  const path = parts(pathname);
  const from = query.get("from") ?? undefined;
  if (!path) return { name: "missing" };
  if (path.length === 0) return { name: "home" };
  if (path.length === 1 && path[0] === "more") return { name: "more" };
  if (path.length === 2 && path[0] === "v" && path[1]) {
    const page = Number(query.get("page") ?? 1);
    return { name: "view", view: path[1], q: query.get("q") ?? "", page: Number.isInteger(page) && page > 0 ? page : 1 };
  }
  if (path.length === 2 && path[0] === "c" && path[1]) return { name: "calculator", calculator: path[1] };
  if (path[0] === "e" && path[1]) {
    if (path.length === 3 && path[2] === "new") return { name: "new", entity: path[1], from };
    if (path.length === 3 && path[2]) return { name: "record", entity: path[1], id: path[2], from };
    if (path.length === 4 && path[2] && path[3] === "edit") return { name: "edit", entity: path[1], id: path[2], from };
  }
  return { name: "missing" };
}

export function pathOf(route: Route): string {
  const key = encodeURIComponent;
  const withQuery = (path: string, query: Record<string, string | undefined>): string => {
    const params = new URLSearchParams(Object.entries(query).filter((entry): entry is [string, string] => Boolean(entry[1])));
    const text = params.toString();
    return text ? `${path}?${text}` : path;
  };
  switch (route.name) {
    case "home":
    case "missing":
      return "/";
    case "more":
      return "/more";
    case "view":
      return withQuery(`/v/${key(route.view)}`, { q: route.q, page: route.page > 1 ? String(route.page) : undefined });
    case "new":
      return withQuery(`/e/${key(route.entity)}/new`, { from: route.from });
    case "record":
      return withQuery(`/e/${key(route.entity)}/${key(route.id)}`, { from: route.from });
    case "edit":
      return withQuery(`/e/${key(route.entity)}/${key(route.id)}/edit`, { from: route.from });
    case "calculator":
      return `/c/${key(route.calculator)}`;
  }
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

const address = (): string => `${location.pathname}${location.search}`;

export function useRoute(): Route {
  // The address is what this memo depends on: `current` is a copy of it, taken at the right moment.
  const current = useSyncExternalStore(subscribe, address);
  return useMemo(() => {
    const url = new URL(current, location.origin);
    return parseRoute(url.pathname, url.search);
  }, [current]);
}

export function navigate(route: Route, options: { replace?: boolean } = {}): void {
  // Replacing an entry keeps what it knows about how it was reached.
  if (options.replace) history.replaceState(history.state, "", pathOf(route));
  else history.pushState({ inApp: true }, "", pathOf(route));
  listeners.forEach((listener) => listener());
}

/**
 * Back within the app returns to the very page a person left, with its search and page number. An address that
 * came from outside, such as a shared link, has nowhere to return to, so it goes up to `fallback` instead.
 */
export function goBack(fallback: Route): void {
  if ((history.state as { inApp?: boolean } | null)?.inApp) history.back();
  else navigate(fallback, { replace: true });
}
