sequenceDiagram
    actor User
    participant WS as FastAPI WebSocket
    participant Graph as LangGraph
    participant CI as classify_intent
    participant ES as extract_slots
    participant RE as respond
    participant LLM as LLM (structured)

    User->>WS: 「明日の夜4人で予約したい」
    WS->>Graph: ainvoke (thread_id付き)
    Graph->>CI: State (messages)
    CI->>LLM: 意図分類 (IntentResult)
    LLM-->>CI: book_restaurant
    CI-->>Graph: intent 更新

    Graph->>ES: State
    ES->>LLM: スロット抽出 (BookingSlots)
    LLM-->>ES: date=明日, party_size=4 ...
    ES-->>Graph: slots / current_slot 更新

    Graph->>RE: State
    RE-->>Graph: 「ご希望の時間は？」
    Graph-->>WS: AIMessage
    WS-->>User: ボット応答

    Note over User,RE: 途中でキャンセルした場合
    User->>WS: 「やっぱりキャンセル」
    WS->>Graph: ainvoke
    Graph->>CI: 
    CI-->>Graph: intent = cancel_booking
    Graph->>RE: 
    RE-->>Graph: 途中キャンセル処理 + slots リセット
    Graph-->>WS: 「予約手続きを中止しました」
    WS-->>User: ボット応答