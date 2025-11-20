"""Streamlit UI for jGrants MCP Server - Simple Version"""

import streamlit as st
import requests
from typing import Dict, Any, Optional
from datetime import datetime
import json

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

# MCP Server URL（ローカルのMCPサーバーを使用）
MCP_BASE_URL = "http://127.0.0.1:8000"


class MCPClient:
    """MCPサーバーとの通信を管理するクライアント"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session_id = None
        self.session = requests.Session()

    def initialize(self):
        """MCPセッションを初期化"""
        try:
            response = self.session.post(
                f"{self.base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "streamlit-ui",
                            "version": "1.0.0"
                        }
                    }
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                },
                timeout=10
            )

            if response.status_code == 200:
                self.session_id = response.headers.get("mcp-session-id")
                return True
            return False
        except Exception as e:
            st.error(f"初期化エラー: {str(e)}")
            return False

    def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """MCPツールを呼び出す"""
        try:
            if not self.session_id:
                if not self.initialize():
                    return {"error": "MCPサーバーに接続できません"}

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
            if self.session_id:
                headers["mcp-session-id"] = self.session_id

            response = self.session.post(
                f"{self.base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": params
                    }
                },
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    content = result["result"].get("content", [])
                    if content and len(content) > 0:
                        text_content = content[0].get("text", "{}")
                        return json.loads(text_content)
                elif "error" in result:
                    return {"error": result["error"].get("message", "不明なエラー")}
            else:
                return {"error": f"HTTPエラー: {response.status_code}"}
        except requests.ConnectionError:
            return {"error": "MCPサーバーに接続できません。サーバーが起動しているか確認してください。"}
        except Exception as e:
            return {"error": f"エラー: {str(e)}"}


# グローバルMCPクライアント
if 'mcp_client' not in st.session_state:
    st.session_state.mcp_client = MCPClient(MCP_BASE_URL)


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
                "指定なし", "農業、林業", "漁業", "製造業", "建設業",
                "情報通信業", "運輸業、郵便業", "卸売業、小売業",
                "宿泊業、飲食サービス業", "医療、福祉"
            ]
            industry = st.selectbox("業種", industry_options)

            employee_options = [
                "指定なし", "従業員数の制約なし", "5名以下", "20名以下",
                "50名以下", "100名以下", "300名以下"
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

        # MCPサーバー接続テスト
        if st.button("🔌 接続テスト", use_container_width=True):
            with st.spinner("接続確認中..."):
                result = st.session_state.mcp_client.call_tool("ping", {})
                if "error" in result:
                    st.error(f"❌ {result['error']}")
                else:
                    st.success(f"✅ 接続成功: {result.get('status', 'ok')}")

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
            result = st.session_state.mcp_client.call_tool("search_subsidies", params)
            if "error" in result:
                st.error(f"エラー: {result['error']}")
            else:
                st.session_state.search_results = result

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

                    with col2:
                        # 詳細表示ボタン
                        if st.button(f"詳細を表示", key=f"detail_{idx}"):
                            with st.spinner("詳細情報を取得中..."):
                                detail = st.session_state.mcp_client.call_tool(
                                    "get_subsidy_detail",
                                    {"subsidy_id": subsidy.get('id')}
                                )
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
                            st.write(f"- {file_info.get('name', 'unknown')}")
                            st.caption(f"サイズ: {file_info.get('size', 0):,} bytes")

                            # ファイルアクセス情報
                            mcp_access = file_info.get('mcp_access', {})
                            if mcp_access:
                                st.caption(f"💡 get_file_content({mcp_access['params']}) で内容を取得できます")
                        else:
                            st.error(f"- {file_info.get('name', 'unknown')}: {file_info.get('error')}")

        # 申請URL
        if detail.get('application_url'):
            st.subheader("🔗 申請ページ")
            st.markdown(f"[申請ページを開く]({detail['application_url']})")

        # 保存先
        if detail.get('save_directory'):
            st.info(f"📁 ファイル保存先: {detail['save_directory']}")


if __name__ == "__main__":
    main()
