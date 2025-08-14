isms_securitycheck_tool.py を書いて得られたヒント
===================================================

* 最初は `Json[List[Dict[str, Any]]]` という型を返すように Agent の output_type を定義していたが、validation error が起きてまともに動かなかった。
そこで、Pydantic BaseModel を使って型を定義し、プロンプト内で tool から返ってくる `List[Dict[str, Any]]` をどのように Pydantic Model にマップするかを、few-shotプロンプトで例を書いたところ、うまく動いた。

* logfire によるパラメーターやプロンプトの分析はとても有用。Logger でログを確認することもできるが、見にくい。。

agent 間でのパラメーターの受け渡しについて
---------------------------------------------------
result.output で agent の run 結果が取得できるが、agent の run にパラメーターを渡す方法は一般的な function と異なる。

こうすれば良いかな、と思った方法は以下の通り。

1. Agent 定義時に指定する deps_type と同じ型の変数を作成し、 run 時の deps 引数に与える
2. tool でその引数を使いたい場合は、ctx.deps でアクセスできる
3. agent の prompt/instruction は、ctx を引数とする function を decorate して、dependency injection できる。その関数の中で、ctx.deps にアクセスし、json.dumps するか、pydantic_ai.format_as_xml を使って、prompt/instruction に埋め込む。

その他
===================================================
[12-factor-agents/README.md at main · humanlayer/12-factor-agents](https://github.com/humanlayer/12-factor-agents/blob/main/README.md) が面白い。


