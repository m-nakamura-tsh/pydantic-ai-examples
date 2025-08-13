import asyncio
from pydantic import BaseModel, Json
from pydantic_ai import Agent, RunContext
from typing import Literal, Set, Optional, List, Any, Dict
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
    date_of_update: Optional[str]
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
    'openai:gpt-4o-mini',
    deps_type=str,
    output_type=UpdateTasksList,
    retries=2
    )

filter_agent = Agent(  
    #'openai:gpt-4o',
    'openai:gpt-4o-mini',
    deps_type=UpdateTasksList,
    output_type=UpdateTasksList,
    retries=2
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


@filter_agent.tool
def filter_update_tasks(ctx: RunContext[UpdateTasksList]) -> UpdateTasksList:
    """アップデート対応日（date_of_update)が指定されていないUpdateTaskのみをフィルターして返す

    Returns:
        UpdateTasksList: フィルターした結果のUpdateTaskのList
    """
    breakpoint()
    update_task_list = ctx.deps.tasks
    filtered_update_task_list = [task for task in update_task_list if (task.date_of_update == "" or task.date_of_update is None)]
    result = UpdateTasksList(tasks=filtered_update_task_list, total_count=len(filtered_update_task_list))
    return result


async def main():
    """メイン処理"""
    spreadsheet_id = "1Xsfuf96REAlmPRXUfrgkaKYZdoy994BmL4REtHX9nvI"
    #sheet_range = "未更新端末一覧!B13:O89"
    sheet_range = "未更新端末一覧!B13:O16"
    prompt_get_all_tasks = (f""" spreadsheet_id = {spreadsheet_id}, ranges = {sheet_range} のGoogle Sheet に記載されている、まだ完了していないセキュリティ更新タスクを全件取得してください。

取得したセキュリティ更新タスクの情報を、UpdateTask に変換する際のポイントについて、例を交えて説明します。"""

        '以下のセキュリティ更新タスク情報があった場合、\n'
        '> {"アップデート対応日":"","端末機№":"977","部署名":"CH","コンピューター名":"HOPC127","最終ログオンユーザ":"jinji","最終ログオンユーザ\\n 表示名":"人事PC","OS":"Windows 10","IEまたはOSビルドのバージョン":"22H2(19045.4651)","Windows Update\\n／WithSecure":"×","Google Chrome":"127.0.6533.089","Mozilla Firefox":"","Mozilla Thunderbird":"","Adobe Reader":"24.002.20895","SKYSEA":"19.300.09h"}\n'
        '対応するUpdateTaskは下記の通りです。\n'
        '（たとえば、"Mozilla Firefox" に対応する値が空文字なので、software_to_be_updatedには"Firefox"は含まれません。）\n'
        '> UpdateTask(date_of_update="", computer_name="HOPC127", last_logon_user="jinji", software_to_be_updated=("Google Chrome", "Adobe Reader", "SKYSEA"))\n\n'
        'また、以下のセキュリティ更新タスク情報があった場合、\n'
        '> {"アップデート対応日":"2025-08-13","端末機№":"977","部署名":"CH","コンピューター名":"HOPC127","最終ログオンユーザ":"jinji","最終ログオンユーザ\\n 表示名":"人事PC","OS":"Windows 10","IEまたはOSビルドのバージョン":"22H2(19045.4651)","Windows Update\\n／WithSecure":"×","Google Chrome":"127.0.6533.089","Mozilla Firefox":"","Mozilla Thunderbird":"","Adobe Reader":"24.002.20895","SKYSEA":"19.300.09h"}\n'
        '対応するUpdateTaskは存在しません。アップデート対応日に"2025-08-13"という具体的な日付が指定されているためです。'
        )

    print(prompt_get_all_tasks)
    
    try:
        # breakpoint()
        tasks = await sheet_agent.run(prompt_get_all_tasks, deps="hogehoge")
        breakpoint()
        final_tasks = await filter_agent.run("アップデート対応日（date_of_update）が指定されていないUpdateTaskのみをフィルターして下さい。フィルターした結果、0件の場合もあり得ます。",
                                             deps=tasks.output)
        print(final_tasks)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
        asyncio.run(main())
