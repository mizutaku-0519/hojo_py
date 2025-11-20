"""Streamlit UI for jGrants MCP Server"""

import streamlit as st
import httpx
from typing import Dict, Any, List, Optional
import asyncio
from datetime import datetime

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

# MCP Server URL
MCP_BASE_URL = "http://127.0.0.1:8000"


async def call_mcp_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP サーバーのツールを呼び出す"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # MCPプロトコルに従ったリクエストを送信
            mcp_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": params
                }
            }

            response = await client.post(
                f"{MCP_BASE_URL}/mcp",
                json=mcp_request,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }
            )
            response.raise_for_status()
            result = response.json()

            # MCPレスポンスから結果を抽出
            if "result" in result:
                content = result["result"].get("content", [])
                if content and len(content) > 0:
                    # テキストコンテンツからJSONをパース
                    import json
                    text_content = content[0].get("text", "{}")
                    return json.loads(text_content)
                return {"error": "空のレスポンス"}
            elif "error" in result:
                return {"error": result["error"].get("message", "不明なエラー")}

            return result
    except httpx.ConnectError:
        return {"error": "MCPサーバーに接続できません。サーバーが起動しているか確認してください。"}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTPエラー: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"エラーが発生しました: {str(e)}"}


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

        # 統計情報ボタン
        if st.button("📊 統計情報を表示", use_container_width=True):
            with st.spinner("統計情報を取得中..."):
                result = asyncio.run(call_mcp_tool("get_subsidy_overview", {"output_format": "json"}))
                if "error" in result:
                    st.error(f"エラー: {result['error']}")
                else:
                    st.session_state.statistics = result

    # メインエリア
    if search_button and keyword:
        params = {
            "keyword": keyword,
            "sort": sort_options[sort],
            "order": "ASC" if order == "昇順" else "DESC",
            "acceptance": 1 if acceptance else 0
        }

        # オプションパラメータの追加
        if industry != "指定なし":
            params["industry"] = industry
        if employees != "指定なし":
            params["target_number_of_employees"] = employees
        if area != "指定なし":
            params["target_area_search"] = area

        with st.spinner("検索中..."):
            result = asyncio.run(call_mcp_tool("search_subsidies", params))
            if "error" in result:
                st.error(f"エラー: {result['error']}")
            else:
                st.session_state.search_results = result

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

    # 検索結果の表示
    if st.session_state.search_results:
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
                                detail = asyncio.run(call_mcp_tool(
                                    "get_subsidy_detail",
                                    {"subsidy_id": subsidy.get('id')}
                                ))
                                if "error" in detail:
                                    st.error(f"エラー: {detail['error']}")
                                else:
                                    st.session_state.subsidy_detail = detail
                                    st.rerun()

    # 詳細情報の表示
    if st.session_state.subsidy_detail:
        detail = st.session_state.subsidy_detail

        st.markdown("---")
        st.header("📄 補助金詳細情報")

        # 閉じるボタン
        if st.button("❌ 閉じる"):
            st.session_state.subsidy_detail = None
            st.rerun()

        st.subheader(detail.get('title', '無題'))

        # ステータス表示
        status = detail.get('status', '不明')
        if status == "受付中":
            st.success(f"✅ {status}")
        else:
            st.error(f"❌ {status}")

        # 基本情報
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**補助金ID:** {detail.get('id', 'N/A')}")
            st.write(f"**補助上限額:** {detail.get('subsidy_max_limit', '未設定')}")
            st.write(f"**受付開始:** {format_date(detail.get('acceptance_start'))}")
            st.write(f"**受付終了:** {format_date(detail.get('acceptance_end'))}")

        with col2:
            target = detail.get('target', {})
            st.write(f"**対象地域:** {target.get('area', '未設定')}")
            st.write(f"**対象業種:** {target.get('industry', '未設定')}")
            st.write(f"**従業員数:** {target.get('employees', '未設定')}")
            st.write(f"**利用目的:** {target.get('purpose', '未設定')}")

        # 詳細説明
        if detail.get('description'):
            st.subheader("📝 詳細説明")
            st.markdown(detail['description'], unsafe_allow_html=True)

        # 添付ファイル
        files = detail.get('files', {})
        if any(files.values()):
            st.subheader("📎 添付ファイル")

            file_type_labels = {
                "application_guidelines": "📋 申請ガイドライン",
                "outline_of_grant": "📄 補助金概要",
                "application_form": "📝 申請書類"
            }

            for file_type, file_list in files.items():
                if file_list:
                    st.write(f"**{file_type_labels.get(file_type, file_type)}**")
                    for file_info in file_list:
                        if "error" not in file_info:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"- {file_info.get('name', 'unknown')}")
                                st.caption(f"サイズ: {file_info.get('size', 0):,} bytes")
                            with col2:
                                # ファイル内容表示ボタン
                                if st.button(f"内容表示", key=f"file_{file_info.get('name')}"):
                                    with st.spinner("ファイルを読み込み中..."):
                                        mcp_access = file_info.get('mcp_access', {})
                                        params = mcp_access.get('params', {})
                                        content = asyncio.run(call_mcp_tool(
                                            "get_file_content",
                                            params
                                        ))
                                        if "error" in content:
                                            st.error(f"エラー: {content['error']}")
                                        elif "content_markdown" in content:
                                            st.markdown("---")
                                            st.markdown(f"### 📄 {file_info.get('name')}")
                                            st.markdown(content['content_markdown'])
                                        else:
                                            st.info("このファイルはMarkdown形式で表示できません")
                        else:
                            st.error(f"- {file_info.get('name', 'unknown')}: {file_info.get('error')}")

        # 申請URL
        if detail.get('application_url'):
            st.subheader("🔗 申請ページ")
            st.markdown(f"[申請ページを開く]({detail['application_url']})")

        st.info(f"ファイル保存先: {detail.get('save_directory', 'N/A')}")


if __name__ == "__main__":
    main()
