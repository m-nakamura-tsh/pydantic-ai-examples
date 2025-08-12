import asyncio
from pydantic import BaseModel
from typing import Literal, Set, Union, List, Optional
import json
import os
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class UpdateTask(BaseModel):
    """更新が必要なコンピューターと更新対象のソフトウェア名"""
    computer_name: str
    last_logon_user: str
    software_to_be_updated: Set[Literal["windows update", "Google Chrome", "Firefox", "Thunderbird", "Adobe Reader", "SKYSEA"]]

class UpdateTasksList(BaseModel):
    """更新が必要なコンピューターのリスト"""
    tasks: List[UpdateTask]
    total_count: int

class Failed(BaseModel):
    """適切な情報を見つけられない"""
    reason: str


# Google Sheets APIのスコープ
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def get_google_sheets_service():
    """Google Sheets APIサービスを取得"""
    creds = None
    
    # トークンファイルが存在する場合は読み込む
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # 有効な認証情報がない場合
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # credentials.jsonファイルから認証フローを開始
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError(
                    "credentials.jsonファイルが見つかりません。"
                    "Google Cloud ConsoleからOAuth2認証情報をダウンロードしてください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # トークンを保存して次回以降の実行を高速化
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    service = build('sheets', 'v4', credentials=creds)
    return service


def get_sheet_data_in_batches(spreadsheet_id: str, sheet_name: str, start_row: int, end_row: int, batch_size: int = 10):
    """バッチ処理でシートデータを取得（Google Sheets API直接使用）"""
    all_data = []
    service = get_google_sheets_service()
    
    # 列インデックスのマッピング
    column_mapping = {
        0: "update_date",        # D列
        3: "computer_name",      # B列
        4: "last_logon_user",    # C列
        8: "windows_update",     # K列
        9: "chrome",            # L列
        18: "firefox",           # M列
        11: "thunderbird",       # N列
        12: "adobe_reader",      # O列
        13: "skysea"             # P列
    }
    
    try:
        for batch_start in range(start_row, end_row + 1, batch_size):
            batch_end = min(batch_start + batch_size - 1, end_row)
            range_str = f"{sheet_name}!B{batch_start}:P{batch_end}"
            
            print(f"Fetching rows {batch_start} to {batch_end}...")
            
            # Google Sheets APIを直接呼び出し
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_str
            ).execute()
            
            values = result.get('values', [])
            print(values)
            
            if not values:
                print(f"No data found for batch {batch_start}-{batch_end}")
                continue
            
            # データを構造化
            for row_idx, row in enumerate(values):
                row_data = {
                    "row_number": batch_start + row_idx
                }
                
                # 各列のデータをマッピング
                for col_idx, field_name in column_mapping.items():
                    if col_idx < len(row):
                        row_data[field_name] = row[col_idx] if row[col_idx] else ""
                    else:
                        row_data[field_name] = ""
                
                all_data.append(row_data)
                
    except HttpError as error:
        print(f"An error occurred: {error}")
        return []
    
    return all_data


async def analyze_update_tasks(sheet_data: List[dict]) -> Union[UpdateTasksList, Failed]:
    """取得したデータから更新が必要なタスクを解析（純粋なPython処理）"""
    
    # アップデート対応日が空欄の行のみフィルター
    filtered_data = [
        row for row in sheet_data 
        if not row.get("update_date") or row.get("update_date") == ""
    ]
    
    if not filtered_data:
        return Failed(reason="更新が必要なコンピューターが見つかりませんでした")
    
    # 全データをPythonで処理
    tasks = []
    for row in filtered_data:
        software_updates = set()
        
        # 各ソフトウェアの更新チェック
        if row.get("windows_update"):
            software_updates.add("windows update")
        if row.get("chrome"):
            software_updates.add("Google Chrome")
        if row.get("firefox"):
            software_updates.add("Firefox")
        if row.get("thunderbird"):
            software_updates.add("Thunderbird")
        if row.get("adobe_reader"):
            software_updates.add("Adobe Reader")
        if row.get("skysea"):
            software_updates.add("SKYSEA")
        
        # 必要な情報が揃っていればタスクを追加
        if software_updates and row.get("computer_name") and row.get("last_logon_user"):
            tasks.append(UpdateTask(
                computer_name=row["computer_name"],
                last_logon_user=row["last_logon_user"],
                software_to_be_updated=software_updates
            ))
    
    if not tasks:
        return Failed(reason="更新が必要なタスクが見つかりませんでした")
    
    return UpdateTasksList(tasks=tasks, total_count=len(tasks))


async def main():
    """メイン処理"""
    spreadsheet_id = "1Xsfuf96REAlmPRXUfrgkaKYZdoy994BmL4REtHX9nvI"
    sheet_name = "未更新端末一覧"
    
    try:
        # Step 1: バッチ処理でデータを取得（同期関数を呼び出し）
        print("Step 1: Fetching sheet data in batches...")
        sheet_data = get_sheet_data_in_batches(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            start_row=13,
            end_row=89,
            batch_size=10
        )
        
        print(f"Total rows fetched: {len(sheet_data)}")
        
        # Step 2: データを解析
        print("Step 2: Analyzing update tasks...")
        result = await analyze_update_tasks(sheet_data)
        
        # 結果を表示
        if isinstance(result, UpdateTasksList):
            print(f"\n=== 更新が必要なコンピューター: {result.total_count}台 ===")
            for i, task in enumerate(result.tasks, 1):
                print(f"\n{i}. {task.computer_name}")
                print(f"   ユーザー: {task.last_logon_user}")
                print(f"   更新対象: {', '.join(task.software_to_be_updated)}")
        elif isinstance(result, Failed):
            print(f"\n処理失敗: {result.reason}")
            
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()



async def test_with_mock_data():
    """モックデータを使用したテスト"""
    # モックデータの作成
    mock_data = [
        {
            "row_number": 13,
            "computer_name": "PC-001",
            "last_logon_user": "user1",
            "update_date": "",  # 空欄 = 更新必要
            "windows_update": "要更新",
            "chrome": "要更新",
            "firefox": "",
            "thunderbird": "",
            "adobe_reader": "要更新",
            "skysea": ""
        },
        {
            "row_number": 14,
            "computer_name": "PC-002",
            "last_logon_user": "user2",
            "update_date": "2024/01/15",  # 更新済み
            "windows_update": "",
            "chrome": "",
            "firefox": "",
            "thunderbird": "",
            "adobe_reader": "",
            "skysea": ""
        },
        {
            "row_number": 15,
            "computer_name": "PC-003",
            "last_logon_user": "user3",
            "update_date": "",  # 空欄 = 更新必要
            "windows_update": "",
            "chrome": "",
            "firefox": "要更新",
            "thunderbird": "要更新",
            "adobe_reader": "",
            "skysea": "要更新"
        }
    ]
    
    print("=== Testing with mock data ===")
    result = await analyze_update_tasks(mock_data)
    
    if isinstance(result, UpdateTasksList):
        print(f"\n更新が必要なコンピューター: {result.total_count}台")
        for i, task in enumerate(result.tasks, 1):
            print(f"\n{i}. {task.computer_name}")
            print(f"   ユーザー: {task.last_logon_user}")
            print(f"   更新対象: {', '.join(task.software_to_be_updated)}")
    elif isinstance(result, Failed):
        print(f"\n処理失敗: {result.reason}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # テストモード
        asyncio.run(test_with_mock_data())
    else:
        # 本番モード
        asyncio.run(main())
