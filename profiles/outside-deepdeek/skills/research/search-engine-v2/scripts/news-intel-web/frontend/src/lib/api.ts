// lib/api.ts — API client for FastAPI backend
// Uses relative URL: works through nginx proxy at same origin

async function fetchAPI<T>(path: string): Promise<T> {
  const res = await fetch(`/api/v1${path}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export { fetchAPI };
