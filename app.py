from datetime import datetime, timezone

from flask import Flask, jsonify, request, url_for
from werkzeug.exceptions import HTTPException


app = Flask(__name__)
app.json.ensure_ascii = False

tasks = [
    {"id": 1, "title": "建立 API", "description": "完成任務管理 API"},
    {"id": 2, "title": "撰寫測試", "description": "驗證 API 回應與狀態碼"},
]
next_task_id = 3


def response(status, message, data, http_status):
    return jsonify({"status": status, "message": message, "data": data}), http_status


@app.get("/api/health")
def health_check():
    return response(
        "success",
        "伺服器運作正常",
        {
            "status": "running",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        200,
    )


@app.get("/api/tasks")
def get_tasks():
    return response("success", "任務清單取得成功", tasks, 200)


@app.post("/api/tasks")
def create_task():
    global next_task_id

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return response("error", "請提供合法的 JSON 物件", None, 400)

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return response("error", "必填欄位 title 不可缺少或為空", None, 400)

    task = {
        "id": next_task_id,
        "title": title.strip(),
        "description": payload.get("description", ""),
    }
    next_task_id += 1
    tasks.append(task)

    body, _ = response("success", "任務新增成功", task, 201)
    return body, 201, {"Location": url_for("get_task", task_id=task["id"])}


@app.get("/api/tasks/<int:task_id>")
def get_task(task_id):
    task = next((item for item in tasks if item["id"] == task_id), None)
    if task is None:
        return response("error", "找不到指定任務", None, 404)
    return response("success", "任務取得成功", task, 200)


@app.errorhandler(HTTPException)
def handle_http_exception(error):
    message = "找不到此路徑" if error.code == 404 else error.name
    return response("error", message, None, error.code)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)