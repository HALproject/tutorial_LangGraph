flowchart TD
    Respond[respond ノード] --> CheckIntent{intent は？}

    %% キャンセル
    CheckIntent -->|cancel_booking| CancelCheck{状態確認}
    CancelCheck -->|cancelled == true| Already[すでにキャンセル済み]
    CancelCheck -->|completed かつ booking_id あり| AfterCancel[予約後キャンセル<br/>booking_id でキャンセル処理<br/>slots リセット]
    CancelCheck -->|それ以外 途中| MidCancel[途中キャンセル<br/>slots / intent リセット]

    %% 天気
    CheckIntent -->|weather| Weather[モック天気応答]

    %% 予約
    CheckIntent -->|book_restaurant| BookCheck{completed？}
    BookCheck -->|Yes| Confirm[予約完了メッセージ<br/>booking_id 発行]
    BookCheck -->|No| AskSlot{current_slot / missing}
    AskSlot -->|次のスロットあり| Question[該当スロットを質問]
    AskSlot -->|なし| Fallback[情報を教えてください]

    %% その他
    CheckIntent -->|other| Other[汎用応答]

    Already --> Out([AIMessage])
    AfterCancel --> Out
    MidCancel --> Out
    Weather --> Out
    Confirm --> Out
    Question --> Out
    Fallback --> Out
    Other --> Out