"""Streamlit UI for jGrants MCP Server"""

import streamlit as st
import httpx
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime
import warnings
import urllib3
import os
from openai import OpenAI
import json
from dotenv import load_dotenv
import pathlib

# .env 読み込み
env_path = pathlib.Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

warnings.filterwarnings('ignore', message='Unverified HTTPS request')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="Jグランツ補助金検索",
    page_icon="💰",
    layout="wide"
)

if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'subsidy_detail' not in st.session_state:
    st.session_state.subsidy_detail = None

API_BASE_URL = "https://api.jgrants-portal.go.jp/exp/v1/public"

# OpenAI キー読込
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
except:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not OPENAI_API_KEY:
    print("⚠ OPENAI_API_KEY が存在しません (.env or secrets から読めていません)")

#
# ① Jグランツ API 呼び出し
#
async def call_jgrants_api(endpoint: str, params: Dict[str, Any] = None, max_retries: int = 3) -> Dict[str, Any]:
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60, verify=False, follow_redirects=True) as client:
                url = f"{API_BASE_URL}{endpoint}"
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"error": f"APIエラー: {str(e)}"}

#
# ② LLM によるパラメータ抽出（structured outputs）
#
def extract_search_params_with_llm(natural_query: str) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        return {"keyword": natural_query}

    client = OpenAI(api_key=OPENAI_API_KEY)

    try:
        response = client.responses.create(
            model="gpt-4.1",
            reasoning={"effort": "medium"},
            input=f"""
ユーザーの検索意図を読み取り、Jグランツ検索API用のパラメータを抽出してください。

ユーザー入力：
{natural_query}

抽出ルール：
- keyword は文章から最も重要な名詞を抽出して短くまとめる
- 林業・製造業・情報通信業など職種が含まれる場合 → industry を設定
- 「デジタル化」「DX」→ use_purpose = "設備整備・IT導入"
- 「環境」「脱炭素」→ use_purpose = "エコ・SDGs活動支援"
- 都道府県名・地方名があれば target_area_search
- 中小企業 → 300名以下、小規模 → 20名以下
- 当てはまらない項目は None
""",
            structured_outputs=[
                {
                    "type": "json_schema",
                    "name": "search_params",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "keyword": {"type": "string"},
                            "industry": {"type": ["string", "null"]},
                            "target_number_of_employees": {"type": ["string", "null"]},
                            "target_area_search": {"type": ["string", "null"]},
                            "use_purpose": {"type": ["string", "null"]}
                        },
                        "required": ["keyword"]
                    }
                }
            ]
        )

        data = response.output[0].content[0].json

        if not data.get("keyword"):
            data["keyword"] = natural_query

        return data

    except Exception as e:
        st.error(f"LLMエラー: {str(e)}")
        return {"keyword": natural_query}

#
# ③ 各種ユーティリティ
#
def format_date(date_str: Optional[str]) -> str:
    if not date_str:
        return "未設定"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日 %H:%M")
    except:
        return date_str

def format_amount(amount_str: Optional[str]) -> str:
    if not amount_str:
        return "金額未定"
    try:
        clean = str(amount_str).replace(",", "").replace("円", "").replace("¥", "").strip()
        if not clean:
            return "金額未定"
        return f"{float(clean):,.0f}円"
    except:
        return str(amount_str)
#
# ④ Streamlit メイン画面
#
def main():
    # Material Icons
    st.markdown("""
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    """, unsafe_allow_html=True)

    # タイトル
    st.markdown("""
        <div style='text-align: center; padding: 2rem 0 3rem 0;'>
            <h2 style='font-size: 2rem; font-weight: bold;'>補助金検索</h2>
            <p>検索したい文言を入力してください</p>
        </div>
    """, unsafe_allow_html=True)

    # 中央検索
    c1, c2, c3 = st.columns([1,3,1])
    with c2:
        natural_query = st.text_input("", placeholder="例: 東京都の中小企業向けのDX補助金")
        search_clicked = st.button("検索", type="primary")

        if search_clicked and natural_query:
            with st.spinner("AIによる検索中..."):
                extracted = extract_search_params_with_llm(natural_query)

                api_params = {
                    "keyword": extracted["keyword"],
                    "sort": "acceptance_end_datetime",
                    "order": "ASC",
                    "acceptance": "1"
                }

                optional_map = [
                    "industry", "target_number_of_employees",
                    "target_area_search", "use_purpose"
                ]
                for key in optional_map:
                    if extracted.get(key):
                        api_params[key] = extracted[key]

                result = asyncio.run(call_jgrants_api("/subsidies", api_params))

                if "error" in result:
                    st.error(result["error"])
                else:
                    st.session_state.search_results = {
                        "total_count": len(result.get("result", [])),
                        "subsidies": result.get("result", [])
                    }
                    st.rerun()

        elif search_clicked:
            st.warning("検索ワードを入力してください")

    st.markdown("<br>", unsafe_allow_html=True)

    #
    # サイドバー UI
    #
    with st.sidebar:
        st.markdown("<h3>詳細検索</h3>", unsafe_allow_html=True)

        keyword = st.text_input("キーワード", "事業")
        industry = st.selectbox("業種", ["指定なし", "製造業", "情報通信業", "卸売業、小売業", "宿泊業、飲食サービス業"])
        employees = st.selectbox("従業員数", ["指定なし", "20名以下", "300名以下"])
        acceptance = st.checkbox("受付中のみ", True)

        if st.button("詳細検索を実行"):
            params = {
                "keyword": keyword,
                "sort": "acceptance_end_datetime",
                "order": "ASC",
                "acceptance": "1" if acceptance else "0"
            }
            if industry != "指定なし":
                params["industry"] = industry
            if employees != "指定なし":
                params["target_number_of_employees"] = employees

            result = asyncio.run(call_jgrants_api("/subsidies", params))

            if "error" not in result:
                st.session_state.search_results = {
                    "total_count": len(result.get("result", [])),
                    "subsidies": result.get("result", [])
                }
                st.rerun()

    #
    # 検索結果
    #
    if st.session_state.search_results:
        results = st.session_state.search_results

        st.markdown(f"### 検索結果 ({results['total_count']}件)")
        st.markdown("---")

        subsidies = results["subsidies"]

        for subsidy in subsidies:
            subsidy_id = subsidy.get("id")

            cols = st.columns([6,2,2,1])

            with cols[0]:
                st.markdown(f"**{subsidy.get('title', '無題')}**")

            with cols[1]:
                st.write(format_date(subsidy.get("acceptance_end_datetime")))

            with cols[2]:
                st.write(format_amount(subsidy.get("subsidy_max_limit")))

            with cols[3]:
                if st.button("詳細", key=f"detail_{subsidy_id}"):
                    with st.spinner("取得中..."):
                        detail = asyncio.run(call_jgrants_api(f"/subsidies/id/{subsidy_id}"))
                        if "error" not in detail:
                            data = detail.get("result", [])
                            if data:
                                st.session_state.subsidy_detail = data[0]
                                st.rerun()

        st.markdown("---")

    #
    # 詳細表示（モーダル）
    #
    if st.session_state.subsidy_detail:
        detail = st.session_state.subsidy_detail

        if st.button("← 閉じる"):
            st.session_state.subsidy_detail = None
            st.rerun()

        st.markdown(f"## {detail.get('title')}")

        st.write("受付期間:", format_date(detail.get("acceptance_start_datetime")), "〜", format_date(detail.get("acceptance_end_datetime")))
        st.write("対象地域:", detail.get("target_area_search"))
        st.write("上限額:", format_amount(detail.get("subsidy_max_limit")))
        st.write("対象業種:", detail.get("target_industry"))
        st.write("---")
        st.write(detail.get("detail") or "詳細説明はありません")

        if detail.get("inquiry_url"):
            st.markdown(f"[申請ページを開く]({detail['inquiry_url']})")


if __name__ == "__main__":
    main()