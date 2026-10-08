/** The URL prefix the browser uses for every backend call. */
export const API_PREFIX = "/api";

/**
 * Turn a browser path into the backend path: "/api/documents" -> "/documents".
 *
 * The backend routes have no "/api" prefix, but the frontend uses one so the
 * dev server can tell API calls apart from its own files. Only an exact "/api"
 * segment is removed, so a path like "/apiary" is left alone.
 */
export function stripApiPrefix(path: string): string {
  if (path === API_PREFIX) {
    return "/";
  }
  if (path.startsWith(API_PREFIX + "/") || path.startsWith(API_PREFIX + "?")) {
    return path.slice(API_PREFIX.length);
  }
  return path;
}
