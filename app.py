"""Streamlit UI for jGrants MCP Server"""

import streamlit as st
import httpx
from typing import Dict, Any, List, Optional
import asyncio
from datetime import datetime
import warnings
import urllib3
import os
from openai import OpenAI
import json
from dotenv import load_dotenv

# 環境変数の読み込み
# スクリプトのディレクトリを取得して.envファイルのパスを指定
import pathlib
env_path = pathlib.Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# SSL警告を抑制（企業プロキシ環境対応）
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ページ設定
st.set_page_config(
    page_title="Jグランツ補助金検索",
    page_icon="💰",
    layout="wide"
)

# セッション状態の初期化
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'subsidy_detail' not in st.session_state:
    st.session_state.subsidy_detail = None

# JグランツAPI URL（MCPサーバーを経由せず直接APIを呼び出す）
API_BASE_URL = "https://api.jgrants-portal.go.jp/exp/v1/public"

# OpenAI API設定
try:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", "")
except:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# デバッグ: APIキーの存在確認（キーの値は表示しない）
if not OPENAI_API_KEY:
    import sys
    print(f"警告: OPENAI_API_KEYが設定されていません", file=sys.stderr)
    print(f".envファイルパス: {env_path}", file=sys.stderr)
    print(f".envファイル存在: {env_path.exists()}", file=sys.stderr)


async def call_jgrants_api(endpoint: str, params: Dict[str, Any] = None, max_retries: int = 3) -> Dict[str, Any]:
    """Jグランツ公開APIを直接呼び出す（リトライ機能付き）"""

    for attempt in range(max_retries):
        try:
            # SSL証明書検証を無効化（企業プロキシ環境対応）
            async with httpx.AsyncClient(
                timeout=60.0,  # タイムアウトを60秒に延長
                verify=False,
                follow_redirects=True
            ) as client:
                url = f"{API_BASE_URL}{endpoint}"

                # デバッグ情報（開発環境のみ）
                if st.session_state.get('debug_mode', False):
                    st.info(f"🔍 API呼び出し (試行 {attempt + 1}/{max_retries}): {url}")
                    st.code(f"パラメータ: {params}")

                response = await client.get(url, params=params)

                # デバッグ情報
                if st.session_state.get('debug_mode', False):
                    st.info(f"📡 ステータスコード: {response.status_code}")

                response.raise_for_status()

                # レスポンスの内容を確認
                try:
                    data = response.json()
                    return data
                except Exception as json_error:
                    return {"error": f"JSONパースエラー: {str(json_error)}, レスポンス: {response.text[:200]}"}

        except httpx.ConnectTimeout:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 指数バックオフ
                continue
            return {"error": "接続タイムアウト: JグランツAPIサーバーへの接続に時間がかかりすぎています"}

        except httpx.ReadTimeout:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"error": "読み取りタイムアウト: APIからのレスポンスに時間がかかりすぎています"}

        except httpx.ConnectError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"error": f"JグランツAPIに接続できません: {str(e)}"}

        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = f" - {e.response.text[:200]}"
            except:
                pass

            # 4xxエラーはリトライしない
            if 400 <= e.response.status_code < 500:
                return {"error": f"HTTPエラー: {e.response.status_code}{error_detail}"}

            # 5xxエラーはリトライ
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"error": f"HTTPエラー: {e.response.status_code}{error_detail}"}

        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"error": f"予期しないエラー: {str(e)}"}

    return {"error": "最大リトライ回数に達しました"}


def extract_search_params_with_llm(natural_query: str) -> Dict[str, Any]:
    """自然言語クエリからLLMを使って検索パラメータを抽出"""

    if not OPENAI_API_KEY:
        return {"error": "OpenAI APIキーが設定されていません"}

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)

        prompt = f"""
以下のユーザーの自然言語クエリから、Jグランツ補助金検索APIのパラメータを抽出してください。

ユーザーのクエリ: "{natural_query}"

以下のJSON形式で返してください：
{{
  "keyword": "抽出したキーワード（必須、2文字以上）",
  "industry": "業種（該当する場合のみ。選択肢: 農業、林業 / 漁業 / 製造業 / 建設業 / 情報通信業 / 運輸業、郵便業 / 卸売業、小売業 / 宿泊業、飲食サービス業 / 医療、福祉）",
  "target_number_of_employees": "従業員数（該当する場合のみ。選択肢: 従業員数の制約なし / 5名以下 / 20名以下 / 50名以下 / 100名以下 / 300名以下）",
  "target_area_search": "対象地域（該当する場合のみ。都道府県名または地方名）",
  "use_purpose": "利用目的（該当する場合のみ。選択肢: 新たな事業を行いたい / 販路拡大・海外展開をしたい / 研究開発・実証事業を行いたい / 設備整備・IT導入をしたい / エコ・SDGs活動支援がほしい）"
}}

注意:
- keywordは必ず含めてください
- 該当しないパラメータは含めないでください
- 中小企業 = 300名以下、小規模事業者 = 20名以下
- DX、デジタル化 = IT導入
- 環境、脱炭素 = エコ・SDGs活動支援

JSONのみを返してください（説明文は不要）。
"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは補助金検索の専門家です。ユーザーの自然言語クエリから適切な検索パラメータを抽出します。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        params_text = response.choices[0].message.content
        params = json.loads(params_text)

        # キーワードが必須なので、なければエラー
        if "keyword" not in params or not params["keyword"]:
            params["keyword"] = natural_query[:50]  # フォールバック

        return params

    except Exception as e:
        st.error(f"LLM処理エラー: {str(e)}")
        # フォールバック: クエリをそのままキーワードとして使用
        return {"keyword": natural_query[:50]}


def format_date(date_str: Optional[str]) -> str:
    """日時文字列をフォーマット"""
    if not date_str:
        return "未設定"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日 %H:%M")
    except Exception:
        return date_str


def format_amount(amount_str: Optional[str]) -> str:
    """金額を3桁区切りの円表示にフォーマット"""
    if not amount_str:
        return "金額未定"
    try:
        # 数値に変換できる場合
        # まず文字列から数値以外を除去
        clean_str = str(amount_str).replace(',', '').replace('円', '').replace('¥', '').replace(' ', '').strip()

        # 空文字列チェック
        if not clean_str:
            return "金額未定"

        amount = float(clean_str)
        return f"{amount:,.0f}円"
    except Exception as e:
        # デバッグ: エラーの場合は元の値を返す
        if st.session_state.get('debug_mode', False):
            st.warning(f"⚠️ 金額フォーマットエラー: {amount_str} -> {str(e)}")
        return str(amount_str)


def main():
    # URLパラメータから補助金IDを取得して詳細表示
    if "subsidy_id" in st.query_params and not st.session_state.get('subsidy_detail'):
        subsidy_id = st.query_params["subsidy_id"]
        detail_result = asyncio.run(call_jgrants_api(f"/subsidies/id/{subsidy_id}"))
        if "error" not in detail_result:
            result_data = detail_result.get("result", [])
            if result_data and len(result_data) > 0:
                st.session_state.subsidy_detail = result_data[0]

    # デバッグ情報を最初に表示
    if st.session_state.get('debug_mode', False):
        st.info(f"🔍 Streamlitバージョン: {st.__version__}")
        st.info(f"🔍 セッション状態: {list(st.session_state.keys())}")

    # Material Icons読み込み
    st.markdown("""
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    """, unsafe_allow_html=True)

    # ヘッダー
    st.markdown("""
        <div style='text-align: center; padding: 2rem 0 3rem 0;'>
            <h2 style='font-size: 2rem; font-weight: bold; color: #1F2937; margin-bottom: 0.5rem;'>補助金検索</h2>
            <p style='color: #6B7280;'>以下に検索したい文言を入力してください</p>
        </div>
    """, unsafe_allow_html=True)

    # 検索ボックス（中央配置）
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        natural_query = st.text_input(
            label="",
            placeholder="例: 東京都の中小企業向けDX補助金",
            key="natural_query"
        )

        # 検索ボタン（Material Icons使用）
        search_clicked = st.button("検索", type="primary", use_container_width=True, key="search_btn")

        if search_clicked:
            if natural_query:
                with st.spinner("検索中..."):
                    extracted_params = extract_search_params_with_llm(natural_query)

                    if "error" not in extracted_params:
                        # JグランツAPIのパラメータに変換
                        api_params = {
                            "keyword": extracted_params.get("keyword", "事業"),
                            "sort": "acceptance_end_datetime",
                            "order": "ASC",
                            "acceptance": "1"
                        }

                        # オプションパラメータを追加
                        if "industry" in extracted_params and extracted_params["industry"]:
                            api_params["industry"] = extracted_params["industry"]
                        if "target_number_of_employees" in extracted_params and extracted_params["target_number_of_employees"]:
                            api_params["target_number_of_employees"] = extracted_params["target_number_of_employees"]
                        if "target_area_search" in extracted_params and extracted_params["target_area_search"]:
                            api_params["target_area_search"] = extracted_params["target_area_search"]
                        if "use_purpose" in extracted_params and extracted_params["use_purpose"]:
                            api_params["use_purpose"] = extracted_params["use_purpose"]

                        # 検索実行
                        result = asyncio.run(call_jgrants_api("/subsidies", api_params))
                        if "error" in result:
                            st.error(f"エラー: {result['error']}")
                        else:
                            formatted_result = {
                                "total_count": len(result.get("result", [])),
                                "subsidies": result.get("result", [])
                            }
                            st.session_state.search_results = formatted_result
                            st.rerun()
                    else:
                        st.error(f"{extracted_params['error']}")
            else:
                st.warning("検索キーワードを入力してください")

    st.markdown("<br>", unsafe_allow_html=True)

    # カスタムスタイル
    st.markdown("""
        <style>
        /* サイドバースタイル */
        [data-testid="stSidebar"] {
            background-color: #F5F5F5;
        }
        [data-testid="stSidebar"] * {
            color: #333333;
        }
        [data-testid="stSidebar"] .stTextInput input,
        [data-testid="stSidebar"] .stSelectbox select {
            background-color: white;
            border: 1px solid #D1D5DB;
            color: #333333;
        }
        [data-testid="stSidebar"] input[type="checkbox"] {
            accent-color: #1F2937 !important;
        }

        /* サイドバーボタン */
        [data-testid="stSidebar"] button {
            background-color: #1F2937 !important;
            color: white !important;
            font-weight: 600;
            padding: 0.5rem 1rem;
            border-radius: 6px;
        }
        [data-testid="stSidebar"] button:hover {
            background-color: #111827 !important;
        }
        [data-testid="stSidebar"] button p {
            color: white !important;
        }

        /* サイドバー閉じるボタン */
        [data-testid="collapsedControl"] {
            display: block !important;
            background-color: transparent !important;
        }
        [data-testid="collapsedControl"] svg {
            color: black !important;
        }

        /* テーブル行の中央揃え */
        [data-testid="column"] > div[data-testid="stVerticalBlock"] > div[data-testid="element-container"] {
            display: flex;
            align-items: center;
            min-height: 60px;
            padding: 0.75rem 0;
        }
        [data-testid="column"] > div[data-testid="stVerticalBlock"] > div[data-testid="element-container"] p {
            margin: 0;
            line-height: normal;
        }

        /* テーブル列の中央揃え */
        .st-emotion-cache-wfksaw {
            justify-content: center;
        }

        /* 区切り線 */
        hr {
            margin: 0.75rem 0;
        }

        /* 詳細ボタン */
        button[key^="detail_"] {
            background-color: #1F2937 !important;
            color: white !important;
            font-weight: 600;
            padding: 0.5rem 1rem;
            border-radius: 6px;
        }
        button[key^="detail_"]:hover {
            background-color: #111827 !important;
        }
        button[key^="detail_"] p,
        button[key^="detail_"] div {
            color: white !important;
            margin: 0;
        }

        /* 検索ボタン */
        button[kind="primary"] {
            background-color: #1F2937 !important;
            color: white !important;
            font-weight: 600;
            border-radius: 6px;
            border: none !important;
        }
        button[kind="primary"]:hover {
            background-color: #111827 !important;
        }
        button[kind="primary"]:focus {
            border: none !important;
            box-shadow: none !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # デバッグ情報を視覚的に表示
    if st.session_state.get('debug_mode', False):
        st.success("✅ CSSスタイルブロックが読み込まれました")
        st.info(f"📊 赤い枠が画面全体に表示されていればCSSが適用されています")
        st.code("""
デバッグチェックリスト:
1. 画面全体に赤い枠が表示されているか？
2. サイドバーの背景が青いグラデーションか？
3. サイドバーのボタンが金色(#FFD700)か？
4. Material Iconsが表示されているか？
        """, language="text")

    with st.sidebar:
        st.markdown("""
            <div style='display: flex; align-items: center; margin-bottom: 1.5rem;'>
                <span class="material-icons" style='font-size: 24px; color: #333333; margin-right: 0.5rem;'>tune</span>
                <h3 style='margin: 0; color: #333333;'>詳細検索</h3>
            </div>
        """, unsafe_allow_html=True)

        keyword = st.text_input("キーワード", value="事業")

        industry_options = ["指定なし", "製造業", "情報通信業", "卸売業、小売業", "宿泊業、飲食サービス業"]
        industry = st.selectbox("業種", industry_options)

        employee_options = ["指定なし", "20名以下", "300名以下"]
        employees = st.selectbox("従業員数", employee_options)

        acceptance = st.checkbox("受付中のみ", value=True)

        if st.button("詳細検索を実行", use_container_width=True):
            params = {
                "keyword": keyword,
                "sort": "acceptance_end_datetime",
                "order": "ASC",
                "acceptance": str(1 if acceptance else 0)
            }
            if industry != "指定なし":
                params["industry"] = industry
            if employees != "指定なし":
                params["target_number_of_employees"] = employees

            with st.spinner("検索中..."):
                result = asyncio.run(call_jgrants_api("/subsidies", params))
                if "error" not in result:
                    formatted_result = {
                        "total_count": len(result.get("result", [])),
                        "subsidies": result.get("result", [])
                    }
                    st.session_state.search_results = formatted_result
                    st.rerun()

        if 'debug_mode' not in st.session_state:
            st.session_state.debug_mode = False

        st.markdown("<br>", unsafe_allow_html=True)
        st.session_state.debug_mode = st.checkbox("デバッグモード", value=st.session_state.debug_mode)

    # モーダル風の詳細情報表示
    if st.session_state.subsidy_detail:
        detail = st.session_state.subsidy_detail

        # オーバーレイ背景
        st.markdown("""
            <style>
            .modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 999;
            }
            .modal-content {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                border-radius: 16px;
                padding: 2rem;
                max-width: 800px;
                width: 90%;
                max-height: 90vh;
                overflow-y: auto;
                z-index: 1000;
                box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
            }
            </style>
        """, unsafe_allow_html=True)

        # 閉じるボタン
        if st.button("← 閉じる", use_container_width=False):
            st.session_state.subsidy_detail = None
            # URLパラメータをクリア
            if "subsidy_id" in st.query_params:
                del st.query_params["subsidy_id"]
            st.rerun()

        # ステータスバッジ計算
        end_raw = detail.get("acceptance_end_datetime")
        status = "受付終了"
        status_color = "#EF4444"
        if end_raw:
            try:
                end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
                if end_dt >= datetime.now(end_dt.tzinfo):
                    status = "受付中"
                    status_color = "#10B981"
            except:
                status = "受付中"
                status_color = "#10B981"

        # タイトルとステータスバッジを横並び（アンカー付き）
        st.markdown(f"""
            <div id='subsidy-detail-title' style='display: flex; align-items: center; margin-top: 1rem; margin-bottom: 1.5rem; gap: 0.75rem;'>
                <div style='
                    display: inline-block;
                    padding: 0.375rem 0.75rem;
                    background-color: {status_color};
                    color: white;
                    border-radius: 4px;
                    font-size: 0.875rem;
                    font-weight: 600;
                    white-space: nowrap;
                '>
                    {status}
                </div>
                <h2 style='margin: 0; font-size: 1.5rem; font-weight: 600; color: #1F2937;'>{detail.get('title', '無題')}</h2>
            </div>
            <script>
                // ページロード時にタイトル位置にスクロール
                document.getElementById('subsidy-detail-title').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            </script>
        """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

        # 基本情報カード
        st.markdown("""
            <div style='
                background-color: #F9FAFB;
                border-radius: 8px;
                padding: 1.25rem;
                margin-bottom: 1.5rem;
            '>
        """, unsafe_allow_html=True)

        # 基本情報（2カラム）
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
                <div style='margin-bottom: 1rem;'>
                    <div style='font-size: 0.75rem; color: #6B7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.25rem;'>受付期間</div>
                    <div style='color: #1F2937; font-size: 0.95rem;'>
            """, unsafe_allow_html=True)
            st.markdown(f"{format_date(detail.get('acceptance_start_datetime'))}<br>〜 {format_date(detail.get('acceptance_end_datetime'))}", unsafe_allow_html=True)
            st.markdown("</div></div>", unsafe_allow_html=True)

            if detail.get('target_area_search'):
                st.markdown("""
                    <div style='margin-top: 1rem;'>
                        <div style='font-size: 0.75rem; color: #6B7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.25rem;'>対象地域</div>
                        <div style='color: #1F2937; font-size: 0.95rem;'>
                """, unsafe_allow_html=True)
                st.markdown(detail.get('target_area_search'), unsafe_allow_html=True)
                st.markdown("</div></div>", unsafe_allow_html=True)

        with col2:
            if detail.get('subsidy_max_limit'):
                st.markdown("""
                    <div style='margin-bottom: 1rem;'>
                        <div style='font-size: 0.75rem; color: #6B7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.25rem;'>補助上限額</div>
                        <div style='color: #1F2937; font-size: 1.125rem; font-weight: 600;'>
                """, unsafe_allow_html=True)
                st.markdown(format_amount(detail.get('subsidy_max_limit')), unsafe_allow_html=True)
                st.markdown("</div></div>", unsafe_allow_html=True)

            if detail.get('target_industry'):
                st.markdown("""
                    <div style='margin-top: 1rem;'>
                        <div style='font-size: 0.75rem; color: #6B7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.25rem;'>対象業種</div>
                        <div style='color: #1F2937; font-size: 0.95rem;'>
                """, unsafe_allow_html=True)
                st.markdown(detail.get('target_industry'), unsafe_allow_html=True)
                st.markdown("</div></div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # 詳細説明
        if detail.get('detail'):
            st.markdown("""
                <h3 style='font-size: 1.125rem; font-weight: 600; color: #1F2937; margin-top: 1.5rem; margin-bottom: 0.75rem;'>詳細説明</h3>
            """, unsafe_allow_html=True)
            st.markdown(f"<div style='color: #4B5563; line-height: 1.6;'>{detail['detail']}</div>", unsafe_allow_html=True)

        # 申請ボタン
        if detail.get('inquiry_url'):
            st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)
            st.markdown(f"""
                <a href='{detail['inquiry_url']}' target='_blank' style='
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    padding: 0.75rem 2rem;
                    background-color: #1F2937;
                    color: white;
                    font-weight: 600;
                    border-radius: 6px;
                    text-decoration: none;
                    transition: background-color 0.2s;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
                ' onmouseover="this.style.backgroundColor='#111827'" onmouseout="this.style.backgroundColor='#1F2937'">
                    <span class="material-icons" style='margin-right: 0.5rem; font-size: 20px;'>open_in_new</span>
                    申請ページを開く
                </a>
            """, unsafe_allow_html=True)

    # 検索結果の表示
    elif st.session_state.search_results:
        results = st.session_state.search_results

        st.markdown(f"### 検索結果 ({results.get('total_count', 0)}件)")
        st.markdown("<br>", unsafe_allow_html=True)

        # デバッグ: 検索結果の確認
        if st.session_state.get('debug_mode', False):
            st.warning(f"🔍 検索結果データ: {len(results.get('subsidies', []))}件の補助金")
            if results.get('subsidies', []):
                first = results['subsidies'][0]
                st.code(f"""
サンプルデータ:
title: {first.get('title', 'N/A')[:50]}...
subsidy_max_limit: {first.get('subsidy_max_limit', 'N/A')}
formatted: {format_amount(first.get('subsidy_max_limit'))}
                """, language="text")

        if results.get('total_count', 0) == 0:
            st.info("検索条件に一致する補助金が見つかりませんでした")
        else:
            # 表形式で表示
            subsidies = results.get('subsidies', [])

            # ソートオプション
            sort_col1, sort_col2, sort_col3 = st.columns([2, 2, 8])
            with sort_col1:
                sort_by = st.selectbox("並び替え", ["締切日", "上限額"], key="sort_by")
            with sort_col2:
                sort_order = st.selectbox("順序", ["昇順", "降順"], key="sort_order")

            # ソート処理
            def get_sort_key(subsidy):
                if sort_by == "締切日":
                    date_str = subsidy.get('acceptance_end_datetime', '')
                    if date_str:
                        try:
                            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        except:
                            return datetime.min
                    return datetime.min
                else:  # 上限額
                    amount_str = subsidy.get('subsidy_max_limit', '')
                    if amount_str:
                        try:
                            clean_str = str(amount_str).replace(',', '').replace('円', '').replace('¥', '').replace(' ', '').strip()
                            return float(clean_str) if clean_str else 0
                        except:
                            return 0
                    return 0

            reverse = (sort_order == "降順")
            subsidies_sorted = sorted(subsidies, key=get_sort_key, reverse=reverse)

            st.markdown("<br>", unsafe_allow_html=True)

            # テーブルヘッダー
            header_cols = st.columns([6, 2, 2, 1])
            with header_cols[0]:
                st.markdown("**事業名**")
            with header_cols[1]:
                st.markdown("**締切日**")
            with header_cols[2]:
                st.markdown("**上限額**")
            with header_cols[3]:
                st.markdown("")

            st.markdown("---")

            # 表の各行を表示
            for idx, subsidy in enumerate(subsidies_sorted):
                subsidy_id = subsidy.get('id')

                cols = st.columns([6, 2, 2, 1])

                with cols[0]:
                    st.markdown(f"<div style='display: flex; align-items: center; height: 100%;'>{subsidy.get('title', '無題')}</div>", unsafe_allow_html=True)

                with cols[1]:
                    st.markdown(f"<div style='display: flex; align-items: center; height: 100%;'>{format_date(subsidy.get('acceptance_end_datetime'))}</div>", unsafe_allow_html=True)

                with cols[2]:
                    st.markdown(f"<div style='display: flex; align-items: center; height: 100%;'>{format_amount(subsidy.get('subsidy_max_limit'))}</div>", unsafe_allow_html=True)

                with cols[3]:
                    if st.button("詳細", key=f"detail_{idx}", use_container_width=True):
                        with st.spinner("読込中..."):
                            detail_result = asyncio.run(call_jgrants_api(f"/subsidies/id/{subsidy_id}"))
                            if "error" not in detail_result:
                                result_data = detail_result.get("result", [])
                                if result_data and len(result_data) > 0:
                                    st.session_state.subsidy_detail = result_data[0]
                                    # URLにsubsidy_idを追加
                                    st.query_params["subsidy_id"] = subsidy_id
                                    st.rerun()

                # 区切り線
                st.markdown("---")


if __name__ == "__main__":
    main()
