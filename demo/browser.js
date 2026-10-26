// Browser-only adapter, loaded exclusively by scripts/build_demo.py.
// ponytail: state lasts for one page session; use the documented server for shared, durable data.
(() => {
  const state = structuredClone(globalThis.DEMO_SEED);
  const fail = (message, status = 400) => {
    throw Object.assign(new Error(message), { status });
  };
  const text = (value, min = 1, max = 200) => {
    if (
      typeof value !== "string" ||
      value.trim().length < min ||
      value.trim().length > max
    )
      fail("Проверьте введённые данные");
    return value.trim();
  };
  const json = (value, status = 200) =>
    new Response(JSON.stringify(value), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  const originalFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = async (input, options = {}) => {
    const url = new URL(input, globalThis.location.href);
    if (
      url.origin !== globalThis.location.origin ||
      !url.pathname.startsWith("/api/")
    )
      return originalFetch(input, options);
    if (options.signal?.aborted)
      throw new DOMException("Aborted", "AbortError");
    try {
      return await handle(
        url,
        options.method || "GET",
        options.body ? JSON.parse(options.body) : {},
        new Headers(options.headers),
      );
    } catch (error) {
      return json(
        { message: error.message, detail: error.message },
        error.status || 400,
      );
    }
  };
  globalThis.PORTFOLIO_DEMO = true;
  async function handle(url, method, body, headers) {
    url.pathname = url.pathname.replace("/api/v1/workspaces/demo/", "/api/");
    const rows = state["/api/approval-requests"],
      actor = headers.get("X-User-Id") || "author";
    if (url.pathname === "/api/approval-requests" && method === "GET")
      return json(rows);
    if (url.pathname === "/api/events") return json(state.events);
    if (url.pathname === "/api/approval-requests" && method === "POST") {
      if (rows.length >= 30) fail("До 30 заявок на сессию");
      const row = {
        id: crypto.randomUUID(),
        title: text(body.title, 1, 512),
        description: body.description || "",
        status: "pending",
        createdBy: actor,
        reviewerUserIds: ["reviewer"],
      };
      rows.unshift(row);
      state.events.unshift({
        id: crypto.randomUUID(),
        action: "created",
        requestId: row.id,
        actor,
        status: "pending",
      });
      return json(row, 201);
    }
    const match = url.pathname.match(
      /^\/api\/approval-requests\/([^/]+)\/(approve|reject|cancel)$/,
    );
    if (match && method === "POST") {
      const row = rows.find((x) => x.id === match[1]);
      if (!row) fail("Не найдено", 404);
      const action = match[2];
      if (
        action === "cancel"
          ? row.createdBy !== actor
          : !row.reviewerUserIds.includes(actor)
      )
        fail("У этого участника нет права на действие", 403);
      if (row.status !== "pending") fail("По заявке уже принято решение", 409);
      if (action !== "approve") text(body.reason, 1, 2000);
      row.status = {
        approve: "approved",
        reject: "rejected",
        cancel: "cancelled",
      }[action];
      row.decidedBy = actor;
      state.events.unshift({
        id: crypto.randomUUID(),
        requestId: row.id,
        actor,
        action,
        status: row.status,
      });
      return json(row);
    }
    fail("Не найдено", 404);
  }
})();
