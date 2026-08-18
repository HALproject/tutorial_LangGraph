flowchart TD
    Start([ユーザー発話]) --> Classify[classify_intent<br/>意図推定]
    Classify -->|intent 判定| Route{route_after_intent}
    %% 予約フロー
    Route -->|book_restaurant| Extract[extract_slots<br/>スロット抽出<br/>with_structured_output]
    Extract --> Respond[respond<br/>応答生成]
    %% その他の意図は直接 respond
    Route -->|cancel_booking| Respond
    Route -->|weather| Respond
    Route -->|other| Respond
    Respond --> End([ボット応答 / END])

    %% スタイル
    classDef intent fill:#e1f5fe,stroke:#01579b
    classDef slot fill:#f3e5f5,stroke:#4a148c
    classDef resp fill:#e8f5e9,stroke:#1b5e20
    classDef decision fill:#fff3e0,stroke:#e65100

    class Classify intent
    class Extract slot
    class Respond resp
    class Route decision