# main.py
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from langchain_core.messages import HumanMessage
from graph import graph

app = FastAPI(title="LangGraph Chatbot Hands-on")

# 簡易HTML（ブラウザで直接対話可能）
HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>レストラン予約ボット</title>
    <style>
        body { font-family: sans-serif; max-width: 600px; margin: 40px auto; }
        #chat { border: 1px solid #ccc; height: 400px; overflow-y: auto; padding: 10px; }
        .user { color: #0066cc; margin: 8px 0; }
        .bot { color: #009900; margin: 8px 0; }
        input { width: 80%; padding: 8px; }
        button { padding: 8px 16px; }
    </style>
</head>
<body>
    <h2>🍽️ レストラン予約ボット（LangGraphハンズオン）</h2>
    <div id="chat"></div>
    <input id="msg" placeholder="メッセージを入力..." onkeypress="if(event.key==='Enter') send()">
    <button onclick="send()">送信</button>

    <script>
        const threadId = crypto.randomUUID();
        const ws = new WebSocket(`ws://\( {location.host}/ws/ \){threadId}`);
        const chat = document.getElementById("chat");

        ws.onmessage = (e) => {
            const data = JSON.parse(e.data);
            const div = document.createElement("div");
            div.className = data.role;
            div.textContent = (data.role === "user" ? "あなた: " : "ボット: ") + data.content;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        };

        function send() {
            const input = document.getElementById("msg");
            const text = input.value.trim();
            if (!text) return;
            ws.send(text);
            input.value = "";
        }
    </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(HTML)

@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    await websocket.accept()
    config = {"configurable": {"thread_id": thread_id}}

    # 初回挨拶
    await websocket.send_json({
        "role": "bot",
        "content": "こんにちは！レストランの予約をお手伝いします。ご希望を教えてください。"
    })

    try:
        while True:
            user_text = await websocket.receive_text()
            await websocket.send_json({"role": "user", "content": user_text})

            # LangGraphを実行
            result = await graph.ainvoke(
                {
                    "messages": [HumanMessage(content=user_text)],
                    "intent": None,
                    "slots": {},
                    "current_slot": None,
                    "completed": False,
                },
                config=config,
            )

            bot_reply = result["messages"][-1].content
            await websocket.send_json({"role": "bot", "content": bot_reply})

    except WebSocketDisconnect:
        print(f"Client disconnected: {thread_id}")

# uvicorn main:app --reload --port 8000