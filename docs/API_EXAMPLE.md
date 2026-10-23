# Пример API

Фактический ответ локального запуска на демоданных.

```http
GET /api/v1/workspaces/demo/approval-requests HTTP/1.1
Host: 127.0.0.1:8030
X-Workspace-Id: demo
X-User-Id: demo
X-Actions: approval:read
```

```http
HTTP/1.1 200
Content-Type: application/json

{
  "items": [],
  "limit": 50,
  "offset": 0,
  "total": 0
}
```
