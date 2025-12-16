# n8n-test

n8n + OpenAI で投資ニュースを要約し、Gmail に送信する自動化ツール。

- 仮想通貨系投資ニュースの RSS を監視（1時間に1回）
- 新着記事が出たら本文を取得
- OpenAI API を使って「そのまま読み上げられる口語要約」を生成
- Gmail に自動送信

※ ソース: https://jp.investing.com/rss/302.rss

## 全体構成（ワークフロー）

<img width="1736" height="871" alt="スクリーンショット 2025-12-17 0 32 36" src="https://github.com/user-attachments/assets/462451cd-bd50-4a47-a04c-411353dce343" />

```
RSS Feed Trigger（投資ニュースの RSS を監視）
→ Fetch Article Link（記事のリンクを取得）
→ Extract HTML Content（HTML の中身を抽出）
→ Extract Article Body（記事の本文を抽出）
→ Summarize Article（記事を口語要約）
→ Send Email（Gmail 宛にメール送信）
```

## 前提条件

- Docker がインストールされている
- OpenAI API Key を持っている
  - 参照: https://rishuntrading.co.jp/blog/programing/openai-api-keys_2025/
- Google アカウントを持っている


## 1. n8n を Docker で起動する

起動：

```bash
$ docker compose up -d
```

ブラウザで以下にアクセス：

```
$ open http://localhost:5678
```

## 2. RSS Feed Trigger を設定する

<img width="1730" height="845" alt="スクリーンショット 2025-12-17 0 35 34" src="https://github.com/user-attachments/assets/4c434b81-d2b4-4413-87b8-666ffce8c990" />

- Node: **RSS Feed Trigger**
  - Poll Times
    - Mode
      - `Every X`
    - Value
      - `1`
    - Unit
      - `Hours`
  - Feed URL
    - `https://jp.investing.com/rss/302.rss`


## 3. Fetch Article Link を設定する

<img width="1729" height="844" alt="スクリーンショット 2025-12-17 0 40 23" src="https://github.com/user-attachments/assets/b463a27a-fe38-495d-beee-eaf19340ba74" />

- Node: **HTTP Request**
  - Method
    - `GET`
  - URL
    - `{{$json.link}}`
  - Authentication
    - `None`
  - Header Parameters（2つ必要）
    - Name
      - `User-Agent`
    - Value
      - `Mozilla/5.0`
    - Accept-Language
      - `ja-JP,ja;q=0.9`
  - Response
    - Response Format
      - `Text`
    - Put Output in Field
      - `data`

## 4. Extract HTML Content を設定する

<img width="1734" height="849" alt="スクリーンショット 2025-12-17 0 46 23" src="https://github.com/user-attachments/assets/ef428f95-3123-40c7-a6a2-7254c9731d5e" />

- Node: **Extract HTML Content**
  - Source Data
    - `JSON`
  - JSON Property
    - `data`
  - Extraction Values
    - Key
      - `nextData`
    - CSS Selector
      - `script#__NEXT_DATA__`
    - Return Value
      - `Text`

※ https://jp.investing.com/ は Next.js で作られているぽいので `script#__NEXT_DATA__` で取得する必要がある。

## 5. Extract Article Body を設定

<img width="1728" height="853" alt="スクリーンショット 2025-12-17 1 05 28" src="https://github.com/user-attachments/assets/c0c50387-9795-498f-b90d-bc355af2975d" />

- Node: **Code**
  - Mode
    - `Run Once for All Items`
  - Language
    - `JavaScript`
  - JavaScript
    - 下記コードをコピペ

```js
const raw0 = items[0]?.json?.nextData;
if (!raw0) throw new Error("nextData が空です");

// JSON文字列に混ざる実改行などをエスケープして parse できる形にする
const normalized = String(raw0)
  .replace(/\u0000/g, "")
  .replace(/\r/g, "\\r")
  .replace(/\n/g, "\\n")
  .replace(/\t/g, "\\t");

const data = JSON.parse(normalized);

// ✅ 本文（HTML）
const articleBodyHtml =
  data?.props?.pageProps?.state?.analysisStore?._article?.body ?? "";

// HTMLタグを落として本文テキスト化（OpenAIに渡しやすい）
const articleBodyText = String(articleBodyHtml)
  .replace(/<script[\s\S]*?<\/script>/gi, "")
  .replace(/<style[\s\S]*?<\/style>/gi, "")
  .replace(/<br\s*\/?>/gi, "\n")
  .replace(/<\/p>/gi, "\n\n")
  .replace(/<\/li>/gi, "\n")
  .replace(/<[^>]+>/g, "")
  .replace(/&nbsp;/g, " ")
  .replace(/&amp;/g, "&")
  .replace(/&lt;/g, "<")
  .replace(/&gt;/g, ">")
  .replace(/\n{3,}/g, "\n\n")
  .trim();

return [
  {
    json: {
      ...items[0].json, // title/link/pubDate など RSS の値を残す
      articleBodyHtml,
      articleBody: articleBodyText,
      articleBodySourcePath: "props.pageProps.state.analysisStore._article.body",
    },
  },
];

```

## 6. Summarize Article を設定する

<img width="1736" height="855" alt="スクリーンショット 2025-12-17 1 04 11" src="https://github.com/user-attachments/assets/209efe16-974a-49c0-9abe-6b8e33c025fc" />

- Node: **AI → Open AI → Message a model**
  - Credential to connect with
    - Create new credentials
      - API キーを設定
  - Resource
    - `Text`
  - Operation
    - `Meesage a model`
  - Model
    - `任意（コストパフォーマンスに従って選択）`
  - Messages（2つ選択）
    - Type
      - `Text`
    - Role
      - `System`
    - Prompt
      - 後述
    - Type
      - `Text`
    - Role
      - `User`
    - Prompt
      - 後述

Role: System 向け Prompt
```text
あなたは金融ニュースを分かりやすく要約する専門家です。
日本語で、投資判断の参考になるように要点を整理してください。
```

Role: User 向け Prompt
```text
以下は投資ニュースの記事本文です。
内容を省略しすぎず、日本語で要約してください。

・スピーチでそのまま読み上げることを前提にしてください  
・口語的で自然な話し言葉にしてください  
・「ですね」「ええと」「〜なんですよね」「というわけです」などを適度に使ってください  
・話し言葉として自然なリズムを意識してください  
・一文が長くなりすぎる場合は、軽く区切ってください  
・聞き手が内容を理解しやすい流れを重視してください  
・原稿を棒読みしている印象にならないようにしてください  
・箇条書きではなく、ひと続きの文章にしてください  

【記事本文】
{{$json.articleBody}}
```

## 7. Send Email を設定する

### 事前準備（認証情報の取得）

OAuth2 認証用に

- Client ID
- Client Secret

の取得が必要。

#### Google Cloud にログイン

https://console.cloud.google.com/

#### クライアントの作成

<img width="1736" height="872" alt="スクリーンショット 2025-12-16 23 51 53" src="https://github.com/user-attachments/assets/46ffd180-e02c-484a-8c44-4179c6ec75d9" />

<img width="1735" height="849" alt="スクリーンショット 2025-12-16 23 52 27" src="https://github.com/user-attachments/assets/d042909d-ce68-474c-804e-c0229337f766" />

<img width="1739" height="871" alt="スクリーンショット 2025-12-16 23 53 05" src="https://github.com/user-attachments/assets/6c32f24e-5675-49a3-98d1-aaba6e9c2e46" />

<img width="1723" height="868" alt="スクリーンショット 2025-12-16 23 56 08" src="https://github.com/user-attachments/assets/d9e07bca-b74c-4b29-a3fd-e9eec5c0233b" />

<img width="1727" height="873" alt="スクリーンショット 2025-12-16 23 56 37" src="https://github.com/user-attachments/assets/a0a1f5a3-5f49-41d2-813c-b232279e8f31" />

1. 左サイドバー → 「API とサービス」 → 「有効な API とサービス」へと進む
2. 「Gmail API」で検索
3. 「管理」をクリック
4. 「クライアント」 → 「クライアントの作成」と進み、各種情報を入力し「作成」をクリック
5. 「クライアント ID」と「クライアントシークレット」を保存

※ クライアントの作成時の各項目
- アプリケーション種類
  - `ウェブアプリケーション`
- 名前
  - `任意`
- 承認済みのリダイレクト URI
  -  `http://localhost:5678/rest/oauth2-credential/callback`

### n8n 側の設定

<img width="1729" height="867" alt="スクリーンショット 2025-12-16 23 58 13" src="https://github.com/user-attachments/assets/31924533-e4a5-4175-8c85-9baf6f677f61" />

<img width="492" height="758" alt="スクリーンショット 2025-12-17 0 00 23" src="https://github.com/user-attachments/assets/3546d73b-1c23-4764-b54e-dd4a1bdfe1cf" />

<img width="489" height="929" alt="スクリーンショット 2025-12-17 0 00 46" src="https://github.com/user-attachments/assets/ef1d42b7-e176-4cab-bd74-e5c9325320d9" />

<img width="1725" height="862" alt="スクリーンショット 2025-12-17 0 01 04" src="https://github.com/user-attachments/assets/5d4542a3-6d4d-4fa2-9939-60394e3f4238" />

<img width="1724" height="856" alt="スクリーンショット 2025-12-17 1 33 50" src="https://github.com/user-attachments/assets/2c128452-7ead-4788-a21b-8fbd132d2467" />



- Node: **Gmail → Send a message**
  - Credential to connect with
    - Create new credentials
      - Connect Using
        - `OAuth2 (recommended)`
      - Auth Redirect URL
        - `http://localhost:5678/rest/oauth2-credential/callback`
      - Client ID
        - 先述
      - Client Secret
        - 先述
      - Allowed HTTP Request Domains
        - `all`
  - Resource
    - `Message`
  - Operation
    - `Send`
  - To
    - 自分のメールアドレス
  - Subject
    - `【投資ニュース要約】`
  - Email Type
    - `HTML`
  - Message
    - `{{$json.output[0].content[0].text}}`

自分のメールアドレスに記事を要約した内容が届けば成功。

<img width="1416" height="571" alt="スクリーンショット 2025-12-17 1 30 42" src="https://github.com/user-attachments/assets/e809f18b-1056-4e3c-9b4b-2adc5985f820" />

