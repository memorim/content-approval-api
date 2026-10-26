const events = [];
function showError(error) {
  document.querySelector("#feedback").textContent = error.message;
}
async function call(path, method = "GET", body) {
  const headers = {
    "Content-Type": "application/json",
    "X-User-Id": document.querySelector("#actor")?.value || "author",
  };
  const response = await fetch(path, {
    method,
    headers,
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const payload = await response.json();
  if (method !== "GET") {
    document.querySelector("#request").textContent =
      method +
      " " +
      path.replace(
        "/api/approval-requests",
        "/api/v1/workspaces/demo/approval-requests",
      ) +
      "\n" +
      JSON.stringify(body || {}, null, 2);
    document.querySelector("#response").textContent =
      response.status + "\n" + JSON.stringify(payload, null, 2);
    events.unshift({
      path,
      method,
      status: response.status,
      time: new Date().toLocaleTimeString("ru-RU"),
    });
    const history = document.querySelector("#history");
    history.replaceChildren();
    for (const event of events.slice(0, 10)) {
      const row = document.createElement("div");
      row.className = "event";
      row.textContent =
        event.time + " · " + event.method + " · " + event.status;
      history.append(row);
    }
    document.querySelector("#feedback").textContent = response.ok
      ? "Изменения сохранены в текущей вкладке."
      : "";
  }
  if (!response.ok) throw Error(payload.message || payload.detail);
  return payload;
}
async function render() {
  const records = await call("/api/approval-requests"),
    root = document.querySelector("#records");
  root.replaceChildren();
  for (const row of records) {
    const article = document.createElement("article");
    const title = document.createElement("h3");
    title.textContent = row.title;
    const description = document.createElement("p");
    description.textContent = row.description;
    const badge = document.createElement("span");
    badge.className = "status";
    badge.textContent = {
      pending: "Ожидает решения",
      approved: "Одобрено",
      rejected: "Отклонено",
      cancelled: "Отменено",
    }[row.status];
    article.append(title, description, badge);
    const actions = document.createElement("div");
    actions.className = "actions";
    for (const [label, action] of [
      ["Одобрить", "approve"],
      ["Отклонить", "reject"],
      ["Отменить", "cancel"],
    ]) {
      const button = document.createElement("button");
      button.textContent = label;
      button.disabled = row.status !== "pending";
      button.onclick = async () => {
        try {
          const reason =
            action === "approve" ? undefined : prompt("Причина решения");
          if (action !== "approve" && reason === null) return;
          await call(
            "/api/approval-requests/" + row.id + "/" + action,
            "POST",
            reason === undefined ? {} : { reason },
          );
          await render();
        } catch (error) {
          showError(error);
        }
      };
      actions.append(button);
    }
    article.append(actions);
    root.append(article);
  }
}
document.querySelector("#editor").onsubmit = async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await call("/api/approval-requests", "POST", {
      title: form.elements.title.value,
      description: form.elements.description.value,
    });
    form.elements.title.value = "";
    form.elements.description.value = "";
    await render();
  } catch (error) {
    showError(error);
  }
};
render().catch(showError);
