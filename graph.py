# graph.py
import os
import uuid
from typing import Annotated, TypedDict, Optional, Literal, List
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field, field_validator

load_dotenv()

# ========== Pydantic スロット ==========
class BookingSlots(BaseModel):
    """予約に必要なスロット。未取得は None のままにする。"""
    date: Optional[str] = Field(
        None,
        description="予約日。例: 明日, 8月20日, 2026-08-20。まだ分からなければ null"
    )
    time: Optional[str] = Field(
        None,
        description="予約時間。例: 19時, 19:00, 午後7時。まだ分からなければ null"
    )
    party_size: Optional[int] = Field(
        None,
        description="人数（整数）。例: 4。まだ分からなければ null"
    )
    name: Optional[str] = Field(
        None,
        description="予約者の名前。まだ分からなければ null"
    )

    @field_validator("party_size", mode="before")
    @classmethod
    def parse_party_size(cls, v):
        if v is None or v == "" or (isinstance(v, str) and v.lower() == "null"):
            return None
        if isinstance(v, str):
            digits = "".join(c for c in v if c.isdigit())
            return int(digits) if digits else None
        return int(v)

    def missing_slots(self) -> List[str]:
        return [k for k, v in self.model_dump().items() if v is None]

    def is_complete(self) -> bool:
        return len(self.missing_slots()) == 0

    def merge(self, other: "BookingSlots") -> "BookingSlots":
        """既存の値を優先し、新しい値で None の部分だけ埋める"""
        data = self.model_dump()
        other_data = other.model_dump()
        for k, v in other_data.items():
            if data.get(k) is None and v is not None:
                data[k] = v
        return BookingSlots(**data)


# ========== 状態定義 ==========
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: Optional[str]
    slots: Optional[BookingSlots]
    current_slot: Optional[str]
    completed: bool
    booking_id: Optional[str]
    cancelled: bool


SLOT_QUESTIONS = {
    "date": "ご希望の日付を教えてください（例: 明日、8月20日）",
    "time": "ご希望の時間を教えてください（例: 19時）",
    "party_size": "何名様でのご予約ですか？",
    "name": "ご予約のお名前を教えてください",
}


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def mock_weather_response(user_text: str) -> str:
    return "今日の天気は晴れです。気温は28度前後で、過ごしやすい一日になりそうです！"


# ========== 意図推定用 ==========
class IntentResult(BaseModel):
    intent: Literal["book_restaurant", "cancel_booking", "weather", "other"]
    confidence: float = Field(ge=0.0, le=1.0)


# ========== ノード ==========
def classify_intent(state: ChatState) -> dict:
    last_message = state["messages"][-1].content
    current_intent = state.get("intent")
    completed = state.get("completed", False)
    cancelled = state.get("cancelled", False)

    # 予約フロー中は「キャンセル」以外は意図を維持
    if current_intent == "book_restaurant" and not completed and not cancelled:
        if any(kw in last_message for kw in ["キャンセル", "やめ", "中止", "やっぱり"]):
            return {"intent": "cancel_booking"}
        return {}

    structured_llm = llm.with_structured_output(IntentResult)
    prompt = f"""
あなたはレストラン予約ボットの意図分類器です。
ユーザーの発話を以下のいずれかに分類してください。

- book_restaurant : 新しく予約したい / 予約の続き
- cancel_booking  : 予約をキャンセルしたい（途中でも完了後でも）
- weather         : 天気について聞いている
- other           : 上記以外

発話: {last_message}
"""
    result = structured_llm.invoke(prompt)
    return {"intent": result.intent}


def extract_slots(state: ChatState) -> dict:
    """スロット抽出を with_structured_output で行う"""
    if state.get("intent") != "book_restaurant":
        return {}

    current_slots = state.get("slots") or BookingSlots()
    last_message = state["messages"][-1].content

    # すでに埋まっている情報をプロンプトに渡して「上書きしない」ようにする
    already = current_slots.model_dump(exclude_none=True)
    already_text = "\n".join(f"- {k}: {v}" for k, v in already.items()) or "なし"

    structured_llm = llm.with_structured_output(BookingSlots)

    prompt = f"""
あなたはレストラン予約の情報抽出器です。
ユーザーの最新発話から、予約に必要な情報を抽出してください。

【すでに分かっている情報】（これらは変更しないでください）
{already_text}

【抽出ルール】
- 新しい情報だけを埋める
- まだ分からない項目は必ず null にする
- 推測で埋めない
- party_size は整数で返す

ユーザーの最新発話:
{last_message}
"""

    extracted: BookingSlots = structured_llm.invoke(prompt)

    # 既存スロットとマージ（既存優先）
    merged = current_slots.merge(extracted)

    missing = merged.missing_slots()
    next_slot = missing[0] if missing else None

    return {
        "slots": merged,
        "current_slot": next_slot,
        "completed": merged.is_complete(),
    }


def respond(state: ChatState) -> dict:
    intent = state.get("intent")
    slots = state.get("slots") or BookingSlots()
    completed = state.get("completed", False)
    cancelled = state.get("cancelled", False)
    booking_id = state.get("booking_id")
    last_user = state["messages"][-1].content

    # ----- キャンセル -----
    if intent == "cancel_booking":
        if cancelled:
            return {"messages": [AIMessage(content="すでにキャンセル済みです。")]}

        if completed and booking_id:
            # 予約後キャンセル
            return {
                "messages": [AIMessage(
                    content=f"予約ID `{booking_id}` のキャンセルを承りました。またのご利用をお待ちしております。"
                )],
                "cancelled": True,
                "completed": False,
                "booking_id": None,
                "slots": BookingSlots(),
                "intent": None,
            }
        else:
            # 途中キャンセル
            return {
                "messages": [AIMessage(
                    content="承知しました。予約手続きを中止しました。また何かあればお気軽にどうぞ。"
                )],
                "cancelled": True,
                "intent": None,
                "slots": BookingSlots(),
                "current_slot": None,
                "completed": False,
            }

    # ----- 天気（モック） -----
    if intent == "weather":
        return {"messages": [AIMessage(content=mock_weather_response(last_user))]}

    # ----- 予約 -----
    if intent == "book_restaurant":
        if completed and not cancelled:
            new_id = str(uuid.uuid4())[:8].upper()
            confirmation = (
                f"ご予約を承りました！\n"
                f"・予約ID: {new_id}\n"
                f"・日付: {slots.date}\n"
                f"・時間: {slots.time}\n"
                f"・人数: {slots.party_size}名\n"
                f"・お名前: {slots.name}\n"
                f"ご来店をお待ちしております。\n"
                f"（キャンセルしたい場合は「キャンセル」とお伝えください）"
            )
            return {
                "messages": [AIMessage(content=confirmation)],
                "booking_id": new_id,
            }

        next_slot = state.get("current_slot") or (
            slots.missing_slots()[0] if slots.missing_slots() else None
        )
        if next_slot:
            question = SLOT_QUESTIONS.get(next_slot, f"{next_slot}を教えてください")
            return {"messages": [AIMessage(content=question)]}
        return {"messages": [AIMessage(content="予約に必要な情報を教えてください。")]}

    # ----- その他 -----
    return {
        "messages": [AIMessage(
            content="申し訳ありません。予約・キャンセル・天気以外のご用件でしたら、もう少し詳しく教えてください。"
        )]
    }


def route_after_intent(state: ChatState) -> str:
    if state.get("intent") == "book_restaurant":
        return "extract_slots"
    return "respond"


def build_graph():
    builder = StateGraph(ChatState)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("extract_slots", extract_slots)
    builder.add_node("respond", respond)

    builder.add_edge(START, "classify_intent")
    builder.add_conditional_edges(
        "classify_intent",
        route_after_intent,
        {"extract_slots": "extract_slots", "respond": "respond"},
    )
    builder.add_edge("extract_slots", "respond")
    builder.add_edge("respond", END)

    return builder.compile(checkpointer=MemorySaver())


graph = build_graph()