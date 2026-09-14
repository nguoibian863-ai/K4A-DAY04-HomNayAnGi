"""Streamlit UI cho IT Helpdesk Agent.

UI tái sử dụng `run_model_tool_loop` từ chat.py để CLI, eval và UI dùng chung
một agent loop. Phần lắp `messages` và cập nhật history được giữ giống hệt
`chat.main()`, vì logic multi-turn nằm ngoài loop chứ không nằm trong nó.

Giao diện khoá ở dark theme qua `.streamlit/config.toml`, nên bảng màu bên dưới
dùng màu cố định thay vì media query theo theme trình duyệt.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from chat import now_iso, run_model_tool_loop, safe_slug, trim_history, write_transcript
from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
SYSTEM_PROMPT_PATH = ARTIFACTS_DIR / "system_prompt.md"
TOOLS_PATH = ARTIFACTS_DIR / "tools.yaml"
TICKETS_DIR = ROOT / "tickets"
load_lab_env(ROOT)

st.set_page_config(page_title="IT Helpdesk Agent", page_icon="🛠️", layout="wide")

# Trạng thái trả về từ run_model_tool_loop, cộng thêm provider_error do UI tự gán.
STATUS_STYLE = {
    "answered": ("✅", "Đã trả lời", "ok"),
    "waiting_for_user": ("⏸️", "Đang chờ người dùng", "warn"),
    "max_tool_rounds": ("🔁", "Dừng vì chạm giới hạn vòng gọi tool", "warn"),
    "provider_error": ("❌", "Lỗi provider", "err"),
}

PROVIDER_AVATAR = {
    "openai": "🟢",
    "openrouter": "🟠",
    "anthropic": "🟣",
    "gemini": "🔵",
}

SUGGESTIONS = [
    "VPN ở môi trường staging có đang ổn không?",
    "Laptop của tôi không vào được VPN, kiểm tra giúp tôi",
    "Kiểm tra VPN trên LT-204 xem lỗi do máy hay do dịch vụ",
]

STYLES = """
<style>
:root {
    --mono: Consolas, "Cascadia Mono", "Segoe UI Mono", ui-monospace, monospace;
    --bg: #131314;
    --panel: #1c1d1f;
    --panel-2: #232427;
    --line: #2e3033;
    --fg: #e8eaed;
    --muted: #9aa0a6;
    --accent: #4d6bfe;
    --c-info: #79c0ff; --c-ok: #56d364; --c-warn: #e3b341; --c-err: #ff7b72;
    --bg-info: rgba(84,174,255,0.14);  --bd-info: rgba(84,174,255,0.34);
    --bg-ok: rgba(74,194,107,0.14);    --bd-ok: rgba(74,194,107,0.34);
    --bg-warn: rgba(212,167,44,0.14);  --bd-warn: rgba(212,167,44,0.34);
    --bg-err: rgba(255,129,130,0.14);  --bd-err: rgba(255,129,130,0.34);
    --bg-neutral: rgba(154,160,166,0.12); --bd-neutral: rgba(154,160,166,0.28);
}

/* ---------- khung chung ---------- */
[data-testid="stAppDeployButton"], [data-testid="stStatusWidget"] { display: none; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stMainBlockContainer"] { padding-top: 2.2rem; max-width: 920px; }
[data-testid="stSidebar"] { background: var(--panel); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.55rem; }
hr { border-color: var(--line) !important; margin: 0.9rem 0 !important; }

/* ---------- sidebar ---------- */
.sb-brand {
    display: flex; align-items: center; gap: 9px;
    font-size: 1.12rem; font-weight: 700; color: var(--fg);
    padding: 2px 0 10px 0;
}
.sb-label {
    font-size: 0.72rem; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.07em; margin: 12px 0 2px 0;
}
/* Nút chính "Hội thoại mới" — dạng viên thuốc nổi bật. */
[data-testid="stSidebar"] button[kind="primary"],
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
    width: 100%; border-radius: 999px; border: 1px solid var(--line);
    background: var(--panel-2); color: var(--fg); font-weight: 600;
    padding: 9px 14px; transition: background 0.15s, border-color 0.15s;
}
[data-testid="stSidebar"] button[kind="primary"]:hover,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover {
    background: #2c2e32; border-color: #3d4043; color: var(--fg);
}
[data-testid="stSidebar"] [data-testid="stDownloadButton"] > button {
    width: 100%; border-radius: 10px; border: 1px solid var(--line);
    background: transparent; color: var(--muted); font-size: 0.85rem;
}
[data-testid="stSidebar"] [data-testid="stDownloadButton"] > button:hover {
    background: var(--panel-2); color: var(--fg);
}
.sb-stat {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 5px 0; border-bottom: 1px solid var(--line); font-size: 0.84rem;
}
.sb-stat:last-child { border-bottom: none; }
.sb-stat .k { color: var(--muted); }
.sb-stat .v { font-family: var(--mono); font-weight: 700; color: var(--fg); }
.sb-stat .v.hot { color: var(--c-err); }
.sb-code {
    font-family: var(--mono); font-size: 0.74rem; color: var(--muted);
    background: var(--bg); border: 1px solid var(--line); border-radius: 8px;
    padding: 7px 9px; word-break: break-all; line-height: 1.5;
}
.sb-note { font-size: 0.78rem; color: var(--muted); line-height: 1.5; }
.sb-date {
    font-size: 0.72rem; color: var(--muted); font-weight: 600;
    margin: 10px 0 2px 2px;
}
.sb-danger {
    font-size: 0.78rem; line-height: 1.45; color: var(--c-err);
    background: var(--bg-err); border: 1px solid var(--bd-err);
    border-radius: 9px; padding: 8px 10px; margin-bottom: 5px;
}
/* Hai nút trong hàng lịch sử nằm sát nhau hơn mặc định. */
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] { gap: 4px; }
/* Mục lịch sử: canh trái, phẳng, cắt bớt tiêu đề dài.
   Kèm cả hai selector vì tên thuộc tính nút đổi giữa các bản Streamlit. */
[data-testid="stSidebar"] button[kind="secondary"],
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
    width: 100%; justify-content: flex-start; text-align: left; border-radius: 9px;
    background: transparent; border: 1px solid transparent; color: var(--muted);
    font-weight: 500; padding: 7px 10px; overflow: hidden; text-overflow: ellipsis;
}
[data-testid="stSidebar"] button[kind="secondary"]:hover,
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover {
    background: var(--panel-2); color: var(--fg); border-color: transparent;
}
[data-testid="stSidebar"] button[kind="secondary"]:disabled,
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:disabled {
    background: var(--panel-2); color: var(--fg); opacity: 1;
}
.pill-ok, .pill-alert {
    display: block; border-radius: 10px; padding: 9px 12px;
    font-size: 0.82rem; font-weight: 600;
}
.pill-ok { background: var(--bg-ok); color: var(--c-ok); border: 1px solid var(--bd-ok); }
.pill-alert { background: var(--bg-err); color: var(--c-err); border: 1px solid var(--bd-err); }

/* ---------- màn hình chào ---------- */
.hero { text-align: center; padding: 8vh 0 1.5rem 0; }
.hero-title { font-size: 1.85rem; font-weight: 700; color: var(--fg); margin-bottom: 10px; }
.hero-sub { font-size: 0.92rem; color: var(--muted); }

/* ---------- badge & chip ---------- */
.badge, .tool-chip {
    display: inline-block; font-weight: 600; white-space: nowrap;
    margin: 0 6px 5px 0; border: 1px solid transparent;
}
.badge { padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; }
.tool-chip { padding: 3px 11px; border-radius: 7px; font-family: var(--mono); font-size: 0.82rem; }
.badge.info, .tool-chip.info { color: var(--c-info); background: var(--bg-info); border-color: var(--bd-info); }
.badge.ok,   .tool-chip.ok   { color: var(--c-ok);   background: var(--bg-ok);   border-color: var(--bd-ok); }
.badge.warn, .tool-chip.warn { color: var(--c-warn); background: var(--bg-warn); border-color: var(--bd-warn); }
.badge.err,  .tool-chip.err  { color: var(--c-err);  background: var(--bg-err);  border-color: var(--bd-err); }
.badge.neutral { color: var(--muted); background: var(--bg-neutral); border-color: var(--bd-neutral); }
.badge.provider { font-weight: 700; }
.badge.p-openai     { color: #3fb950; background: rgba(48,164,108,0.16); border-color: rgba(48,164,108,0.4); }
.badge.p-openrouter { color: #ffa657; background: rgba(251,143,68,0.16); border-color: rgba(251,143,68,0.4); }
.badge.p-anthropic  { color: #d2a8ff; background: rgba(163,113,247,0.16); border-color: rgba(163,113,247,0.4); }
.badge.p-gemini     { color: #79c0ff; background: rgba(84,174,255,0.16); border-color: rgba(84,174,255,0.4); }

/* ---------- bóng chat ---------- */
[data-testid="stChatMessage"] {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 16px; padding: 14px 18px; margin-bottom: 10px;
}
[data-testid="stChatMessageAvatarUser"] + div { color: var(--fg); }

/* ---------- dấu vết tool ---------- */
.round-head {
    font-size: 0.72rem; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.07em; margin: 12px 0 6px 0;
}
.argtable {
    width: 100%; border-collapse: collapse; margin: 4px 0 10px 0;
    font-size: 0.84rem; font-family: var(--mono);
}
.argtable td {
    border: 1px solid var(--line); padding: 6px 10px;
    vertical-align: top; color: var(--fg);
}
.argtable td.k { background: var(--bg-neutral); font-weight: 700; width: 30%; color: var(--muted); }
.argtable td.v { word-break: break-word; }
.empty-args { color: var(--muted); font-style: italic; font-size: 0.84rem; }
[data-testid="stExpander"] {
    border: 1px solid var(--line); border-radius: 12px; background: var(--bg);
}

/* ---------- ô nhập ---------- */
[data-testid="stChatInput"] {
    border-radius: 22px; border: 1px solid var(--line);
    background: var(--panel-2);
}
[data-testid="stChatInput"]:focus-within { border-color: var(--accent); }
[data-testid="stBottomBlockContainer"] { max-width: 920px; padding-bottom: 1.4rem; }
</style>
"""


@st.cache_resource(show_spinner=False)
def get_provider(name: str):
    """Provider giữ nguyên giữa các lần rerun; cache theo tên nên đổi provider là tạo mới."""
    return make_provider(name)


def badge(text: str, kind: str = "neutral") -> str:
    """kind: info | ok | warn | err | neutral — màu lấy từ CSS."""
    return f'<span class="badge {kind}">{html.escape(text)}</span>'


def provider_badge(provider_name: str | None) -> str:
    """Chỉ hiện provider. Tên model vẫn được ghi vào transcript làm evidence."""
    name = provider_name or "(không rõ)"
    css = f"p-{name}" if name in PROVIDER_AVATAR else "neutral"
    icon = PROVIDER_AVATAR.get(name, "🤖")
    return f'<span class="badge provider {css}">{icon} {html.escape(name)}</span>'


def resolve_model(provider_name: str) -> str:
    """Model mặc định của provider, giống cách chat.main() tính `selected_model`,
    để transcript không ghi None."""
    try:
        return getattr(get_provider(provider_name), "default_model", None) or "(không rõ)"
    except Exception:  # noqa: BLE001 — thiếu key không được làm hỏng phần render
        return "(không rõ)"


def stat_row(label: str, value: Any, hot: bool = False) -> str:
    cls = "v hot" if hot else "v"
    return (f'<div class="sb-stat"><span class="k">{html.escape(label)}</span>'
            f'<span class="{cls}">{html.escape(str(value))}</span></div>')


def new_transcript(
    version: str,
    provider_name: str,
    model: str | None,
    artifact_version,
    history_window: int,
    max_tool_rounds: int,
) -> dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([safe_slug(version), safe_slug(provider_name), "ui", timestamp])
    return {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact_version),
        "provider": provider_name,
        "model": model,
        "interface": "streamlit_ui",
        "system_prompt": str(SYSTEM_PROMPT_PATH),
        "tools": str(TOOLS_PATH),
        "history_window": history_window,
        "max_tool_rounds": max_tool_rounds,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }


def reset_session() -> None:
    for key in ("history", "turns", "transcript", "pending"):
        st.session_state.pop(key, None)


def transcript_title(transcript: dict[str, Any]) -> str:
    """Lấy câu hỏi đầu tiên làm tiêu đề, giống cách các app chat đặt tên phiên."""
    for turn in transcript.get("turns") or []:
        text = (turn.get("user") or "").strip()
        if text:
            return text if len(text) <= 38 else text[:37] + "…"
    return "(phiên chưa có lượt nào)"


def list_transcripts(limit: int = 40) -> list[dict[str, Any]]:
    """Quét thư mục transcripts/ thành danh sách phiên, mới nhất trước.

    File hỏng hoặc đang ghi dở bị bỏ qua thay vì làm sập UI.
    """
    directory = ROOT / "transcripts"
    if not directory.exists():
        return []

    sessions: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.transcript.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        try:
            created = datetime.fromisoformat(data.get("created_at", ""))
        except (TypeError, ValueError):
            created = datetime.fromtimestamp(path.stat().st_mtime)
        sessions.append({
            "path": path,
            "transcript_id": data.get("transcript_id", path.stem),
            "title": transcript_title(data),
            "created": created,
            "turn_count": len(data.get("turns") or []),
            "version": data.get("version", "?"),
            "provider": data.get("provider"),
        })
    return sessions


def date_group(moment: datetime) -> str:
    today = datetime.now().date()
    delta = (today - moment.date()).days
    if delta == 0:
        return "Hôm nay"
    if delta == 1:
        return "Hôm qua"
    return moment.strftime("%Y-%m-%d")


def rebuild_history(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Dựng lại history cho model từ các lượt đã lưu.

    Bỏ qua lượt provider_error vì chat.main() cũng không đưa chúng vào history.
    """
    history: list[dict[str, str]] = []
    for turn in turns:
        if turn.get("status") == "provider_error":
            continue
        history.append({"role": "user", "content": turn.get("user", "")})
        history.append({"role": "assistant", "content": turn.get("assistant_text") or ""})
    return history


def delete_transcript(path: Path, transcript_id: str) -> bool:
    """Xoá hẳn file transcript khỏi đĩa. Không khôi phục được.

    Nếu đang mở chính phiên vừa xoá thì bắt đầu một phiên trống, vì transcript
    trong session_state không còn file tương ứng để ghi tiếp.
    """
    try:
        path.unlink()
    except OSError:
        return False
    st.session_state.pop("confirm_delete", None)
    if (st.session_state.get("transcript") or {}).get("transcript_id") == transcript_id:
        reset_session()
    return True


def open_transcript(path: Path) -> bool:
    """Nạp một transcript cũ vào phiên hiện tại để xem lại và nói tiếp."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    turns = data.get("turns") or []
    st.session_state.transcript = data
    st.session_state.turns = turns
    st.session_state.history = rebuild_history(turns)
    st.session_state.pop("pending", None)
    return True


def turn_duration(turn: dict[str, Any]) -> str:
    try:
        started = datetime.fromisoformat(turn["started_at"])
        ended = datetime.fromisoformat(turn["ended_at"])
    except (KeyError, TypeError, ValueError):
        return ""
    return f"{(ended - started).total_seconds():.1f}s"


def result_state(result: Any) -> str:
    """Phân loại kết quả tool để tô màu: lỗi, đang chờ người dùng, hay bình thường."""
    if isinstance(result, dict):
        if result.get("error"):
            return "err"
        if result.get("awaiting_user"):
            return "wait"
    return "ok"


def render_args(args: dict[str, Any] | None) -> None:
    """Bảng key/value dễ soi sai argument hơn là một khối JSON thô."""
    if not args:
        st.markdown('<div class="empty-args">(không có argument)</div>', unsafe_allow_html=True)
        return
    rows = []
    for key, value in args.items():
        shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        rows.append(
            f'<tr><td class="k">{html.escape(str(key))}</td>'
            f'<td class="v">{html.escape(str(shown))}</td></tr>'
        )
    st.markdown(f'<table class="argtable">{"".join(rows)}</table>', unsafe_allow_html=True)


def strip_code_fence(text: str) -> str:
    """Model không ổn định: có lúc trả JSON trần, có lúc bọc trong ```json ... ```."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2:
        return stripped
    body = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
    return "\n".join(body).strip()


def render_assistant_text(text: str | None) -> None:
    """Prompt yêu cầu model trả về JSON envelope (intent/action/reply/evidence_ids).

    Envelope có thể đổi khi A sửa system_prompt qua v1..v3, nên parse best-effort:
    tách được thì render `reply` cho dễ đọc, không tách được thì in nguyên văn.
    """
    if not text:
        st.markdown("_(model không trả về text)_")
        return

    try:
        envelope = json.loads(strip_code_fence(text))
    except (json.JSONDecodeError, TypeError):
        st.markdown(text)
        return

    if not isinstance(envelope, dict) or "reply" not in envelope:
        st.markdown(text)
        return

    st.markdown(str(envelope.get("reply") or ""))

    chips = [
        badge(f"{key}: {envelope[key]}", "info")
        for key in ("intent", "action")
        if envelope.get(key)
    ]
    evidence = envelope.get("evidence_ids")
    if isinstance(evidence, list):
        if evidence:
            chips.append(badge(f"evidence: {', '.join(map(str, evidence))}", "ok"))
        else:
            chips.append(badge("evidence: trống", "warn"))
    if chips:
        st.markdown("".join(chips), unsafe_allow_html=True)

    extra = {k: v for k, v in envelope.items()
             if k not in {"intent", "action", "reply", "evidence_ids"}}
    if extra:
        st.caption("Trường nằm ngoài envelope đã khai báo")
        st.json(extra, expanded=False)


def render_tool_round(round_record: dict[str, Any]) -> None:
    calls = round_record.get("tool_calls") or []
    results = round_record.get("tool_results") or []

    st.markdown(
        f'<div class="round-head">Vòng {round_record.get("round")} · '
        f'{len(calls)} lời gọi tool</div>',
        unsafe_allow_html=True,
    )

    for index, call in enumerate(calls):
        name = str(call.get("name", "?"))
        result = results[index].get("result") if index < len(results) else None
        state = result_state(result) if index < len(results) else "wait"

        chip_kind = {"ok": "info", "err": "err", "wait": "warn"}[state]
        st.markdown(
            f'<span class="tool-chip {chip_kind}">{html.escape(name)}</span>',
            unsafe_allow_html=True,
        )
        render_args(call.get("args"))

        if index >= len(results):
            # Loop đã dừng trước khi lời gọi này chạy (ví dụ một clarify đứng trước).
            st.info("Không có kết quả — loop dừng trước khi tool này được gọi.")
            continue

        if state == "err":
            st.error(
                f"**{result.get('error')}** — {result.get('message', '')}"
                if isinstance(result, dict) else "Tool trả về lỗi"
            )
        elif state == "wait":
            st.warning("Tool dừng hội thoại để chờ người dùng trả lời.")

        with st.expander("Xem kết quả tool đầy đủ", expanded=False):
            st.json(result, expanded=True)


def render_turn(turn: dict[str, Any]) -> None:
    with st.chat_message("user", avatar="🧑"):
        st.markdown(turn.get("user", ""))

    turn_provider = turn.get("provider")
    avatar = PROVIDER_AVATAR.get(turn_provider or "", "🤖")

    with st.chat_message("assistant", avatar=avatar):
        status = turn.get("status", "")
        icon, label, kind = STATUS_STYLE.get(status, ("•", status or "không rõ", "neutral"))

        rounds = turn.get("rounds") or []
        tool_count = sum(len(r.get("tool_calls") or []) for r in rounds)
        meta = [
            # Provider đứng đầu: đây là thứ phân biệt ai đã trả lời lượt này.
            provider_badge(turn_provider),
            badge(f"{icon} {label}", kind),
            badge(f"{len(rounds)} vòng"),
            badge(f"{tool_count} tool"),
        ]
        duration = turn_duration(turn)
        if duration:
            meta.append(badge(duration))
        meta.append(badge(str(turn.get("artifact_version", "?"))))
        st.markdown("".join(meta), unsafe_allow_html=True)

        if status == "provider_error":
            st.error(turn.get("error", "Lỗi provider không xác định"))
        else:
            render_assistant_text(turn.get("assistant_text"))

        if rounds:
            with st.expander(f"🔍 Dấu vết gọi tool ({tool_count} lời gọi)", expanded=True):
                for round_record in rounds:
                    render_tool_round(round_record)


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
st.markdown(STYLES, unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="sb-brand">🛠️ IT Helpdesk Agent</div>', unsafe_allow_html=True)
    start_new = st.button("＋  Hội thoại mới", use_container_width=True, type="primary")

    st.markdown('<div class="sb-label">Cấu hình</div>', unsafe_allow_html=True)
    provider_name = st.selectbox("Provider", ["openai", "openrouter", "anthropic", "gemini"],
                                 label_visibility="collapsed")
    version_label = st.text_input("Nhãn version", value="v0",
                                  help="Ghi vào transcript làm evidence")
    col_a, col_b = st.columns(2)
    with col_a:
        history_window = st.number_input("History", min_value=1, max_value=20, value=5)
    with col_b:
        max_tool_rounds = st.number_input("Max rounds", min_value=1, max_value=10, value=4)

if start_new:
    reset_session()
    st.rerun()

# Đọc artifact ở mỗi lần rerun để hash luôn phản ánh file trên đĩa tại thời điểm gọi.
system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
tool_declarations = load_tool_declarations(TOOLS_PATH)
openai_tools = to_openai_tools(tool_declarations)
artifact_version = build_artifact_version(version_label, SYSTEM_PROMPT_PATH, TOOLS_PATH)
effective_model = resolve_model(provider_name)

st.session_state.setdefault("history", [])
st.session_state.setdefault("turns", [])
if "transcript" not in st.session_state:
    st.session_state.transcript = new_transcript(
        version_label, provider_name, effective_model, artifact_version,
        int(history_window), int(max_tool_rounds),
    )
transcript_path = ROOT / "transcripts" / f"{st.session_state.transcript['transcript_id']}.transcript.json"

turns: list[dict[str, Any]] = st.session_state.turns
total_tool_calls = sum(
    len(r.get("tool_calls") or []) for t in turns for r in (t.get("rounds") or [])
)
total_errors = sum(
    1 for t in turns for event in (t.get("tool_events") or [])
    if isinstance(event.get("result"), dict) and event["result"].get("error")
)
provider_errors = sum(1 for t in turns if t.get("status") == "provider_error")
ticket_files = sorted(TICKETS_DIR.glob("*.json")) if TICKETS_DIR.exists() else []

with st.sidebar:
    st.markdown('<div class="sb-label">Phiên hiện tại</div>', unsafe_allow_html=True)
    st.markdown(
        stat_row("Lượt hội thoại", len(turns))
        + stat_row("Lời gọi tool", total_tool_calls)
        + stat_row("Tool trả lỗi", total_errors, hot=total_errors > 0)
        + stat_row("Lỗi provider", provider_errors, hot=provider_errors > 0),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sb-label">Artifact version</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="sb-code">{html.escape(artifact_version.artifact_version)}<br>'
        f'prompt {artifact_version.prompt_hash[:12]}<br>'
        f'tools&nbsp; {artifact_version.tools_hash[:12]}<br>'
        f'{len(tool_declarations)} tool được khai báo</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sb-label">Ticket đã tạo</div>', unsafe_allow_html=True)
    if ticket_files:
        names = "<br>".join(html.escape(p.name) for p in ticket_files)
        st.markdown(
            f'<div class="pill-alert">{len(ticket_files)} ticket trong tickets/<br>{names}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="sb-note">Mỗi ticket phải ứng với một xác nhận rõ ràng.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="pill-ok">Chưa có ticket nào được tạo</div>',
                    unsafe_allow_html=True)

    st.markdown('<div class="sb-label">Transcript</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-code">{html.escape(transcript_path.name)}</div>',
                unsafe_allow_html=True)
    if transcript_path.exists():
        st.download_button(
            "⬇  Tải transcript làm evidence",
            data=transcript_path.read_bytes(),
            file_name=transcript_path.name,
            mime="application/json",
            use_container_width=True,
        )

    st.markdown('<div class="sb-label">Lịch sử hội thoại</div>', unsafe_allow_html=True)
    sessions = list_transcripts()
    current_id = st.session_state.transcript.get("transcript_id")
    if not sessions:
        st.markdown('<div class="sb-note">Chưa có phiên nào được lưu.</div>',
                    unsafe_allow_html=True)
    else:
        last_group = None
        for session in sessions:
            group = date_group(session["created"])
            if group != last_group:
                st.markdown(f'<div class="sb-date">{html.escape(group)}</div>',
                            unsafe_allow_html=True)
                last_group = group

            session_id = session["transcript_id"]
            is_current = session_id == current_id

            # Đang hỏi xác nhận cho đúng phiên này thì thay dòng bằng hai nút.
            if st.session_state.get("confirm_delete") == session_id:
                st.markdown(
                    f'<div class="sb-danger">Xoá “{html.escape(session["title"])}”?<br>'
                    'File evidence sẽ mất vĩnh viễn.</div>',
                    unsafe_allow_html=True,
                )
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Xoá", key=f"delyes_{session_id}", use_container_width=True):
                        if delete_transcript(session["path"], session_id):
                            st.rerun()
                        else:
                            st.error("Không xoá được file.")
                with col_no:
                    if st.button("Huỷ", key=f"delno_{session_id}", use_container_width=True):
                        st.session_state.pop("confirm_delete", None)
                        st.rerun()
                continue

            icon = PROVIDER_AVATAR.get(session["provider"] or "", "🤖")
            label = f"{'▸ ' if is_current else ''}{icon}  {session['title']}"
            col_open, col_del = st.columns([0.8, 0.2])
            with col_open:
                if st.button(
                    label,
                    key=f"hist_{session_id}",
                    use_container_width=True,
                    help=(f"{session_id} · {session['turn_count']} lượt · "
                          f"version {session['version']}"),
                    disabled=is_current,
                ):
                    if open_transcript(session["path"]):
                        st.rerun()
                    else:
                        st.error("Không đọc được transcript này.")
            with col_del:
                if st.button("🗑", key=f"del_{session_id}", use_container_width=True,
                             help="Xoá phiên này"):
                    st.session_state.confirm_delete = session_id
                    st.rerun()

# --------------------------------------------------------------------------
# Main — chat
# --------------------------------------------------------------------------
if not turns:
    st.markdown(
        '<div class="hero">'
        '<div class="hero-title">🛠️ Xin chào, tôi có thể giúp gì cho bạn?</div>'
        '<div class="hero-sub">Hỏi về VPN, email, SSO, Wi-Fi, máy in, thiết bị được cấp '
        'hoặc chính sách IT nội bộ.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(SUGGESTIONS))
    for col, suggestion in zip(cols, SUGGESTIONS):
        with col:
            if st.button(suggestion, use_container_width=True, key=f"sg_{suggestion[:18]}"):
                st.session_state.pending = suggestion
                st.rerun()

for past_turn in turns:
    render_turn(past_turn)

# Câu gợi ý được đưa vào đúng luồng xử lý như khi người dùng tự gõ.
user_text = st.chat_input("Nhập yêu cầu hỗ trợ IT…") or st.session_state.pop("pending", None)
if user_text:
    # Lắp messages giống hệt chat.main(): system + history đã cắt + user hiện tại.
    messages = [
        {"role": "system", "content": system_prompt},
        *trim_history(st.session_state.history, int(history_window)),
        {"role": "user", "content": user_text},
    ]

    turn_record: dict[str, Any] = {
        "turn_index": len(turns) + 1,
        "started_at": now_iso(),
        "user": user_text,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
        # Ghi provider/model theo từng lượt, không dựa vào header transcript:
        # người dùng có thể đổi provider giữa phiên và các lượt cũ phải giữ đúng gốc.
        "provider": provider_name,
        "model": effective_model,
        # Ghi artifact version theo từng lượt: file có thể đổi giữa chừng phiên.
        **artifact_version_dict(artifact_version),
    }

    with st.spinner("Agent đang chọn tool…"):
        try:
            result = run_model_tool_loop(
                provider=get_provider(provider_name),
                messages=messages,
                tools=openai_tools,
                model=None,
                max_tool_rounds=int(max_tool_rounds),
            )
            turn_record.update(result)
            # Câu hỏi clarify cũng vào history như assistant message — giống chat.main().
            st.session_state.history.append({"role": "user", "content": user_text})
            st.session_state.history.append({"role": "assistant", "content": result["assistant_text"]})
        except Exception as exc:  # noqa: BLE001 — khớp hành vi provider_error của chat.main()
            turn_record.update({
                "status": "provider_error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            # Provider lỗi thì không đưa lượt này vào history, giống chat.main().

    turn_record["ended_at"] = now_iso()
    turns.append(turn_record)
    st.session_state.transcript["turns"] = turns
    write_transcript(transcript_path, st.session_state.transcript)
    st.rerun()
