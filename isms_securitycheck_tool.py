import asyncio
from pydantic import BaseModel, Json
from pydantic_ai import Agent, RunContext
from typing import Literal, Set, Union, List, Any, Dict
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
import json
import logfire

logfire.configure()  
logfire.instrument_pydantic_ai()


# ロギングの基本設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# pydantic_aiのロガーを取得
logger = logging.getLogger('pydantic_ai')
logger.setLevel(logging.DEBUG)


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

sheet_agent = Agent(  
    #'openai:gpt-4o',
    'anthropic:claude-sonnet-4-0',
    deps_type=str,
    output_type=Json[List[Dict[str, Any]]],
    retries=5
    )

summary_agent = Agent(  
    #'openai:gpt-4o',
    'anthropic:claude-sonnet-4-0',
    deps_type=List[Dict[str, Any]],
    output_type=Json[List[Dict[str, Any]]],
    retries=5
    )

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


def _convert_to_dict(input_list: list) -> list[dict]:
    # 1行目をヘッダーとする
    if not input_list or len(input_list) < 2:
        return []
    header = input_list[0]
    output_ : list[dict]  = [dict(zip(header, row)) for row in input_list[1:]]
    return output_

@sheet_agent.tool
def get_sheet_data(ctx: RunContext[str], spreadsheet_id: str, ranges: List[str]) -> List[dict]:
    """Google Sheet 上のセキュリティ更新タスク情報を取得（Google Sheets API直接使用）
    
    Args:
        spreadsheet_id (str): Google SheetsのスプレッドシートID
        ranges (List[str]): 取得する範囲のリスト（例: ["Sheet1!A1:C10", "Sheet1!D1:F10"]）
    
    Returns:
        List[dict]: 取得したセキュリティ更新タスク情報のリスト    
    Raises:
        HttpError: Google Sheets APIからのエラー
    """
    all_data = []
    service = get_google_sheets_service()
    
    try:
        # バッチリクエストで複数範囲を一度に取得
        print(f"Fetching {len(ranges)} ranges in batch...")
        
        result = service.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=ranges
        ).execute()
        
        value_ranges = result.get('valueRanges', [])
        
        for range_idx, value_range in enumerate(value_ranges):
            values = value_range.get('values', [])
            
            if not values:
                print(f"No data found for range: {ranges[range_idx]}")
                continue
            
            # データを構造化
            for row in values:
                all_data.append(row)
                
    except HttpError as error:
        print(f"An error occurred: {error}")
        raise
    
    return _convert_to_dict(all_data)

@summary_agent.tool
def tasks_not_completed(ctx: RunContext[List[Dict[str, Any]]], tasks: List[dict], key: str) -> List[dict]:
    """まだ完了していないセキュリティ更新タスクを抽出する

    Args:
        tasks(List[dict]): 取得したセキュリティ更新タスク情報のリスト。1つのタスクはdictで表現される。 
        key (str): 完了したタスクと完了していないタスクを区別するキー。このキーに対応する値が空のタスク（dict）は、完了していないものと見做す
    
    Returns:
        List[dict]: まだ完了していないセキュリティ更新タスクのリスト

    """
    return [task for task in tasks if task[key] == "" or task[key] is None]


@summary_agent.instructions
def all_tasks(ctx: RunContext[List[Dict[str, Any]]]):
    all_tasks: List[Dict[str, Any]] = ctx.deps
    return f"セキュリティ更新タスク情報の全件は下記の通り。この json は復元すると List[dict] の形になる。 \n ------ \n {json.dumps(all_tasks)}"


async def main():
    """メイン処理"""
    spreadsheet_id = "1Xsfuf96REAlmPRXUfrgkaKYZdoy994BmL4REtHX9nvI"
    sheet_range = "未更新端末一覧!B13:O89"
    prompt_get_all_tasks = f""" spreadsheet_id = {spreadsheet_id}, ranges = {sheet_range} のGoogle Sheet に記載されている、まだ完了していないセキュリティ更新タスクをJson形式で全件取得してください。"""
    prompt_filter_remained_tasks = """抽出に利用するkeyは、「アップデート対応日」です。結果はJson形式で出力して下さい"""
    
    try:
        # breakpoint()
        all_tasks = await sheet_agent.run(prompt_get_all_tasks, deps="hogehoge")
        # breakpoint()
        remained_tasks = await summary_agent.run(prompt_filter_remained_tasks, deps=all_tasks.output)
        print(remained_tasks)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
        asyncio.run(main())
