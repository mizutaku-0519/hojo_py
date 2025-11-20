"""Streamlit UI for jGrants MCP Server"""

import streamlit as st
import httpx
from typing import Dict, Any, List, Optional
import asyncio
from datetime import datetime
import warnings
import urllib3

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


def format_date(date_str: Optional[str]) -> str:
    """日時文字列をフォーマット"""
    if not date_str:
        return "未設定"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日 %H:%M")
    except Exception:
        return date_str


def main():
    st.title("💰 Jグランツ補助金検索システム")
    st.markdown("---")

    # サイドバー: 検索条件
    with st.sidebar:
        st.header("🔍 検索条件")

        keyword = st.text_input(
            "キーワード",
            value="事業",
            help="補助金を検索するキーワード（2文字以上）"
        )

        # 詳細検索オプション
        with st.expander("詳細検索オプション"):
            industry_options = [
                "指定なし", "農業、林業", "漁業", "鉱業、採石業、砂利採取業", "建設業", "製造業",
                "電気・ガス・熱供給・水道業", "情報通信業", "運輸業、郵便業", "卸売業、小売業",
                "金融業、保険業", "不動産業、物品賃貸業", "学術研究、専門・技術サービス業",
                "宿泊業、飲食サービス業", "生活関連サービス業、娯楽業", "教育、学習支援業",
                "医療、福祉", "複合サービス事業", "サービス業（他に分類されないもの）"
            ]
            industry = st.selectbox("業種", industry_options)

            employee_options = [
                "指定なし", "従業員数の制約なし", "5名以下", "20名以下",
                "50名以下", "100名以下", "300名以下", "900名以下", "901名以上"
            ]
            employees = st.selectbox("従業員数", employee_options)

            area_options = [
                "指定なし", "全国", "北海道地方", "東北地方", "関東・甲信越地方",
                "東海・北陸地方", "近畿地方", "中国地方", "四国地方", "九州・沖縄地方"
            ]
            area = st.selectbox("対象地域", area_options)

            sort_options = {
                "募集終了日時": "acceptance_end_datetime",
                "募集開始日時": "acceptance_start_datetime",
                "作成日時": "created_date"
            }
            sort = st.selectbox("並び順", list(sort_options.keys()))

            order = st.radio("ソート順", ["昇順", "降順"])

            acceptance = st.checkbox("受付中のみ", value=True)

        search_button = st.button("🔍 検索", type="primary", use_container_width=True)

        st.markdown("---")

        # デバッグモード
        if 'debug_mode' not in st.session_state:
            st.session_state.debug_mode = False

        debug_mode = st.checkbox("🔧 デバッグモード", value=st.session_state.debug_mode)
        st.session_state.debug_mode = debug_mode

        if debug_mode:
            st.caption("API呼び出しの詳細情報を表示します")

    # メインエリア
    if search_button and keyword:
        params = {
            "keyword": keyword,
            "sort": sort_options[sort],
            "order": "ASC" if order == "昇順" else "DESC",
            "acceptance": str(1 if acceptance else 0)
        }

        # オプションパラメータの追加
        if industry != "指定なし":
            params["industry"] = industry
        if employees != "指定なし":
            params["target_number_of_employees"] = employees
        if area != "指定なし":
            params["target_area_search"] = area

        with st.spinner("検索中..."):
            result = asyncio.run(call_jgrants_api("/subsidies", params))
            if "error" in result:
                st.error(f"エラー: {result['error']}")
            else:
                # APIレスポンスを整形
                formatted_result = {
                    "total_count": len(result.get("result", [])),
                    "subsidies": result.get("result", [])
                }
                st.session_state.search_results = formatted_result

    # 統計情報の表示
    if 'statistics' in st.session_state:
        stats = st.session_state.statistics

        st.header("📊 補助金統計情報")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("総件数", stats.get("total_count", 0))
        with col2:
            st.metric("今月締切", stats.get("by_deadline_period", {}).get("this_month", 0))
        with col3:
            urgent = len(stats.get("urgent_deadlines", []))
            st.metric("緊急（14日以内）", urgent, delta="要注意" if urgent > 0 else None)

        # 締切期間別グラフ
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("締切期間別")
            deadline_data = stats.get("by_deadline_period", {})
            st.bar_chart({
                "今月": deadline_data.get("this_month", 0),
                "来月": deadline_data.get("next_month", 0),
                "再来月以降": deadline_data.get("after_next_month", 0)
            })

        with col2:
            st.subheader("金額規模別")
            amount_data = stats.get("by_amount_range", {})
            st.bar_chart({
                "100万円以下": amount_data.get("under_1m", 0),
                "1000万円以下": amount_data.get("under_10m", 0),
                "1億円以下": amount_data.get("under_100m", 0),
                "1億円超": amount_data.get("over_100m", 0)
            })

        # 緊急締切案件
        if stats.get("urgent_deadlines"):
            st.subheader("⚠️ 緊急締切案件（14日以内）")
            for item in stats["urgent_deadlines"]:
                st.warning(f"**{item['title']}** - 残り{item['days_left']}日 (ID: {item['id']})")

        st.markdown("---")

    # 詳細情報の表示（検索結果より先に表示）
    if st.session_state.subsidy_detail:
        detail = st.session_state.subsidy_detail

        st.markdown("---")
        st.header("📄 補助金詳細情報")

        # 閉じるボタン
        if st.button("❌ 閉じる"):
            st.session_state.subsidy_detail = None
            st.rerun()

        st.subheader(detail.get('title', '無題'))

        # ステータス判定
        end_raw = detail.get("acceptance_end_datetime")
        status = "受付終了"
        if end_raw:
            try:
                end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
                if end_dt >= datetime.now(end_dt.tzinfo):
                    status = "受付中"
            except:
                status = "受付中"

        if status == "受付中":
            st.success(f"✅ {status}")
        else:
            st.error(f"❌ {status}")

        # 基本情報
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**補助金ID:** {detail.get('id', 'N/A')}")
            st.write(f"**補助上限額:** {detail.get('subsidy_max_limit', '未設定')}")
            st.write(f"**受付開始:** {format_date(detail.get('acceptance_start_datetime'))}")
            st.write(f"**受付終了:** {format_date(detail.get('acceptance_end_datetime'))}")

        with col2:
            st.write(f"**対象地域:** {detail.get('target_area_search', '未設定')}")
            st.write(f"**対象業種:** {detail.get('target_industry', '未設定')}")
            st.write(f"**従業員数:** {detail.get('target_number_of_employees', '未設定')}")
            st.write(f"**利用目的:** {detail.get('use_purpose', '未設定')}")

        # 詳細説明
        if detail.get('detail'):
            st.subheader("📝 詳細説明")
            st.markdown(detail['detail'], unsafe_allow_html=True)

        # 添付ファイル（APIから直接取得したファイル情報を表示）
        file_types = {
            "application_guidelines": "📋 申請ガイドライン",
            "outline_of_grant": "📄 補助金概要",
            "application_form": "📝 申請書類"
        }

        has_files = False
        for file_key in file_types.keys():
            if detail.get(file_key):
                has_files = True
                break

        if has_files:
            st.subheader("📎 添付ファイル")
            st.info("ℹ️ ファイルはBASE64形式で提供されています。MCPサーバー経由でMarkdown変換が可能です。")

            for file_key, label in file_types.items():
                file_list = detail.get(file_key, [])
                if file_list:
                    st.write(f"**{label}**")
                    for file_data in file_list:
                        if isinstance(file_data, dict):
                            file_name = file_data.get('name', 'unknown')
                            st.write(f"- {file_name}")
                            st.caption("ファイルのダウンロード・変換にはMCPサーバーを使用してください")

        # 申請URL
        if detail.get('inquiry_url'):
            st.subheader("🔗 申請ページ")
            st.markdown(f"[申請ページを開く]({detail['inquiry_url']})")

        # 最終更新日時
        if detail.get('update_datetime'):
            st.caption(f"最終更新: {format_date(detail['update_datetime'])}")

    # 検索結果の表示
    elif st.session_state.search_results:
        results = st.session_state.search_results

        st.header(f"🔍 検索結果: {results.get('total_count', 0)}件")

        if results.get('total_count', 0) == 0:
            st.info("検索条件に一致する補助金が見つかりませんでした。")
        else:
            for idx, subsidy in enumerate(results.get('subsidies', [])):
                with st.expander(f"**{subsidy.get('title', '無題')}**"):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.write(f"**補助金ID:** {subsidy.get('id', 'N/A')}")

                        # 受付期間
                        start = format_date(subsidy.get('acceptance_start_datetime'))
                        end = format_date(subsidy.get('acceptance_end_datetime'))
                        st.write(f"**受付期間:** {start} 〜 {end}")

                        # 補助上限額
                        max_limit = subsidy.get('subsidy_max_limit')
                        if max_limit:
                            try:
                                amount = float(max_limit)
                                st.write(f"**補助上限額:** ¥{amount:,.0f}")
                            except:
                                st.write(f"**補助上限額:** {max_limit}")

                        # 対象地域
                        if subsidy.get('target_area_search'):
                            st.write(f"**対象地域:** {subsidy.get('target_area_search')}")

                        # 業種
                        if subsidy.get('target_industry'):
                            st.write(f"**対象業種:** {subsidy.get('target_industry')}")

                    with col2:
                        # 詳細表示ボタン
                        if st.button(f"詳細を表示", key=f"detail_{idx}"):
                            with st.spinner("詳細情報を取得中..."):
                                subsidy_id = subsidy.get('id')
                                detail_result = asyncio.run(call_jgrants_api(f"/subsidies/id/{subsidy_id}"))
                                if "error" in detail_result:
                                    st.error(f"エラー: {detail_result['error']}")
                                else:
                                    # APIレスポンスを整形
                                    result_data = detail_result.get("result", [])
                                    if result_data and len(result_data) > 0:
                                        st.session_state.subsidy_detail = result_data[0]
                                        st.rerun()
                                    else:
                                        st.error("詳細情報が取得できませんでした")


if __name__ == "__main__":
    main()
