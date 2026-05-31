import feed from "./channels/feed";
import noop from "./workflows/noop";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sequence(url: URL): number {
  const value = url.searchParams.get("seq");
  if (!value) return Date.now();
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : Date.now();
}

export default {
  async fetch(request: Request) {
    const url = new URL(request.url);

    if (url.pathname === "/channel-publish") {
      const seq = sequence(url);
      const message = await feed.publish({
        type: "tick",
        data: { seq, at: Date.now() },
      });
      return json({ ok: true, id: message.id });
    }

    if (url.pathname === "/workflow-enqueue") {
      const seq = sequence(url);
      const id = await noop.enqueue({ seq, at: Date.now() });
      return json({ ok: true, id });
    }

    if (url.pathname === "/status") {
      return json({ ok: true, app: "tako-feature-benchmark" });
    }

    return json({ error: "not_found" }, 404);
  },
};
