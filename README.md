# n8n-test

n8n + OpenAI で投資ニュースを口語要約し、TTSで音声化 → MP4動画化 → YouTube にアップロードする自動化ツール。

- 仮想通貨系投資ニュースの RSS を監視（1時間に1回）
- 新着記事が出たら記事本文を取得して整形
- OpenAI API を使って「そのまま読み上げられる口語要約」を生成
- Google Cloud Text-to-Speech で SSML から MP3 を生成
- 生成した音声 + アバター画像から MP4 を生成（ローカルで構築した video-api を利用）
- YouTube Data API v3 の Resumable Upload で動画を自動アップロード

※ ソース: https://jp.investing.com/rss/302.rss

## 全体構成（ワークフロー）

<img width="1730" height="839" alt="スクリーンショット 2025-12-17 22 59 15" src="https://github.com/user-attachments/assets/3503f48b-d599-44aa-bf9d-2bea166dff82" />

```
RSS Feed Trigger（投資ニュースの RSS を監視）
→ Fetch Article Link（記事のリンクを取得）
→ Extract HTML Content（HTML の中身を抽出）
→ Extract Article Body（記事本文を抽出・テキスト化）
→ Summarize Article（OpenAI で口語要約）
→ Create ssml（要約文を SSML に変換）
→ Generate TTS（Google TTS で MP3 生成）
→ Generate MP4（音声 + 画像から MP4 作成）
→ Fetch Upload YouTube Location（Resumable Upload の Location を取得）
→ Merge（MP4 と Location を結合）
→ YouTube Upload（MP4 を YouTube にアップロード）
```

## 前提条件

- Docker がインストールされている
- OpenAI API Key を持っている
  - 参照: https://rishuntrading.co.jp/blog/programing/openai-api-keys_2025/
- Google アカウントを持っている


## 1. n8n を Docker で起動する

起動：

```bash
$ chmod -R 755 assets
$ docker compose up -d
```

ブラウザで以下にアクセス：

```
$ open http://localhost:5678
```

<img width="1577" height="867" alt="スクリーンショット 2025-12-16 21 40 29" src="https://github.com/user-attachments/assets/4c782e9e-44f6-4663-a450-bc4c24f9965d" />

適当なメールアドレスとパスワードなどを入力してアカウントを作成。


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

## 7. Create ssml を設定する

<img width="1728" height="818" alt="スクリーンショット 2025-12-17 18 41 07" src="https://github.com/user-attachments/assets/fb748fc6-4f42-4700-b781-31a1d5d78ef7" />

- Node: **Code**
  - Mode
    - `Run Once for All Items`
  - Language
    - `JavaScript`
  - JavaScript
    - 下記コードをコピペ

```js
const text = $json.output?.[0]?.content?.[0]?.text ?? "";
if (!text) throw new Error("要約テキストが空です");

const escapeForSsml = (s) =>
  s
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

const safe = escapeForSsml(text).replace(/\n+/g, " ");
const ssml = `<speak>${safe.replace(/。/g, '。<break time="250ms"/>')}</speak>`;

// ★HTTP Requestでそのまま送れる「JSON文字列」を作る
const ttsBody = JSON.stringify({
  input: { ssml },
  voice: { languageCode: "ja-JP", name: "ja-JP-Neural2-B" },
  audioConfig: { audioEncoding: "MP3", speakingRate: 1.03 },
});

return [{ json: { ...$json, ssml, ttsBody } }];
```

## 8. Generate TTS を設定する

### 事前準備（認証情報の取得）

※ Google の 「Text-to-Speech AI」を使用するための「サービスアカウント」が必要

#### Google Cloud にログイン

https://console.cloud.google.com/

#### サービスアカウントを作成

<img width="1736" height="872" alt="スクリーンショット 2025-12-16 23 51 53" src="https://github.com/user-attachments/assets/46ffd180-e02c-484a-8c44-4179c6ec75d9" />

<img width="1731" height="815" alt="スクリーンショット 2025-12-17 18 44 48" src="https://github.com/user-attachments/assets/12e666a5-4f6d-4879-b20c-03b68cf0229b" />

<img width="1731" height="818" alt="スクリーンショット 2025-12-17 18 46 54" src="https://github.com/user-attachments/assets/8a3d015d-b8f4-44b0-be3c-d1be33ce11e9" />

<img width="565" height="393" alt="スクリーンショット 2025-12-17 18 54 59" src="https://github.com/user-attachments/assets/b4f7c61b-ce50-44ce-93c1-4c9b44de9340" />

<img width="570" height="358" alt="スクリーンショット 2025-12-17 18 53 09" src="https://github.com/user-attachments/assets/0079565f-0e79-44ac-b447-42a5c9dcf749" />

<img width="566" height="340" alt="スクリーンショット 2025-12-17 18 55 52" src="https://github.com/user-attachments/assets/6ff386ef-1266-4672-b2c9-df1d8fee6ab0" />

<img width="1735" height="810" alt="スクリーンショット 2025-12-17 18 58 09" src="https://github.com/user-attachments/assets/992cfa1e-a7b4-4b90-a8c1-2c00389c219a" />


1. 左サイドバー → 「API とサービス」 → 「有効な API とサービス」へと進む
2. 「Clout Text-to-Speech API」で検索
3. 「有効にする」をクリック
4. 「認証情報」 → 「サービスアカウントを管理」→「サービスアカウントを作成」へと進み、各種情報を入力し「作成」をクリック
5. 作成されたサービスアカウントの詳細ページを開き、「鍵」→「キーを追加」→「新しい鍵を作成」→「JSON」→「作成」をクリック
6. PC にダウンロードされた `.json` ファイルから「private_key」と「client_email」をコピー

```json
{
  "type": "service_account",
  "project_id": "**********",
  "private_key_id": "**********",
  "private_key": "-----BEGIN PRIVATE KEY-----\n**********=\n-----END PRIVATE KEY-----\n",
  "client_email": "*********@***************.iam.gserviceaccount.com",
  "client_id": "**********",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/**********.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

```

### n8n 側の設定

<img width="1731" height="808" alt="スクリーンショット 2025-12-17 18 41 35" src="https://github.com/user-attachments/assets/72e7bba3-2e13-4fb7-bf91-aaf83d59edef" />

- Node: **HTTP Request**
  - Method
    - `POST`
  - URL
    - `https://texttospeech.googleapis.com/v1/text:synthesize`
  - Authentication
    - `Authentication`
      - `Predefined Credential Type`
  - Credential Type
    - `Google Service Account API`
  - Google Service Account API
    - `Create new credentials`
      - Region
        - `Asia Pacific (Tokyo) - asia-northeast1`
      - Service Account Email
        - 先述
      - Private Key
        - 先述
      - Set up for use in HTTP Request node
        - `On`
      - Scope(s)
        - `https://www.googleapis.com/auth/cloud-platform`
      - Allowed HTTP Request Domains
        - `All`
  - Send Headers
    - `On`
  - Header Parameters
    - Name
      - `Content-Type`
    - Value
      - `application/json; charset=utf-8`
  - Send Body
    - `On`
  - Body Content Type
    - `RAW`
  - Content Type
    - `application/json`
  - Body
    - `{{$json.ttsBody}}`


## 9. Generate MP4  を設定する

<img width="1715" height="847" alt="スクリーンショット 2025-12-17 20 58 00" src="https://github.com/user-attachments/assets/152c0390-fb27-47cc-86c5-5e1dacf8eca3" />


- Node: **HTTP Request**
  - Method
    - `POST`
  - Authentication
    - `None`
  - URL
    - `http://video-api:8000/generate`
  - Send Body
    - `On`
  - Body Content Type
    - `JSON`
  - Specify Body
    - `Using JSON`
  - JSON
    - 下記

```json
{
  "audioContent": "{{$json.audioContent}}",
  "imagePath": "/assets/avatar.png"
}
```

## 10. Fetch Upload YouTube Location を設定する

※ 動画ファイルアップロード先の Location を取得するためのノード

### 事前準備（OAuth2 認証情報の取得）

OAuth2 認証用に

- Client ID
- Client Secret

の取得が必要。

#### Google Cloud にログイン

https://console.cloud.google.com/

#### クライアントの作成

<img width="1737" height="861" alt="スクリーンショット 2025-12-17 21 05 05" src="https://github.com/user-attachments/assets/3e35cd02-0ce3-4f0f-8390-163c7e4d3123" />

<img width="1736" height="872" alt="スクリーンショット 2025-12-16 23 51 53" src="https://github.com/user-attachments/assets/46ffd180-e02c-484a-8c44-4179c6ec75d9" />

<img width="1727" height="857" alt="スクリーンショット 2025-12-17 21 05 42" src="https://github.com/user-attachments/assets/5c03d553-1933-4531-ae40-aaa4f6f52f78" />

<img width="1723" height="868" alt="スクリーンショット 2025-12-16 23 56 08" src="https://github.com/user-attachments/assets/d9e07bca-b74c-4b29-a3fd-e9eec5c0233b" />

<img width="1727" height="873" alt="スクリーンショット 2025-12-16 23 56 37" src="https://github.com/user-attachments/assets/a0a1f5a3-5f49-41d2-813c-b232279e8f31" />

1. 左サイドバー → 「API とサービス」 → 「有効な API とサービス」へと進む
2. 「YouTube Data API v3」で検索
3. 「有効にする」をクリック
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

<img width="1725" height="841" alt="スクリーンショット 2025-12-17 22 04 20" src="https://github.com/user-attachments/assets/a8320dbc-f93a-4711-9217-987dbdf3cb22" />

<img width="1669" height="804" alt="スクリーンショット 2025-12-17 22 09 23" src="https://github.com/user-attachments/assets/66cc9382-4ea6-4e1d-9f6a-c8bb53ec3ace" />

<img width="1714" height="833" alt="スクリーンショット 2025-12-17 22 11 18" src="https://github.com/user-attachments/assets/737c4c92-a4dc-4db5-b778-6070e2354d99" />

- Node: **HTTP Request**
  - Method
    - `POST`
  - URL
    - `https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status`
  - Authentication
    - `Generic Credential Type`
  - Generic Auth Type
    - OAuth2 API
  - OAuth2 API
    - OAuth Redirect URL
      - `http://localhost:5678/rest/oauth2-credential/callback`
    - Grant Type
      - `Authorization Code`
    - Authorization URL
      - `https://accounts.google.com/o/oauth2/v2/auth`
    - Access Token URL *
      - `https://oauth2.googleapis.com/token`
    - Client ID
      - 先述
    - Client Secret
      - 先述
    - Scope
      - `https://www.googleapis.com/auth/youtube.upload`
    - Auth URI Query Parameters
      - `access_type=offline`
    - Authentication
      - `Header`
    - Allowed HTTP Request Domains
      - All
  - Send Headers
    - `On`
  - Specify Headers
    - `Using Fields Below`
  - Header Parameters
    - Name
      - `Content-Type`
    - Value
      - `application/json; charset=utf-8`
    - Name
      - `X-Upload-Content-Type`
    - Value
      - `video/mp4`
  - Send Body
    - `On`
  - Body Content Type
    - `JSON`
  - Specify Body
    - `Using JSON`
  - JSON
    - 下記
  - Options
    - Response
      - Include Response Headers and Status
        - `On`

11. Merge を設定する

※ 9で取得した MP4 データと10で取得した動画ファイルアップロード先の Location を一つの情報として一元化し、後続に繋げるためのノード。

<img width="1719" height="844" alt="スクリーンショット 2025-12-17 22 19 20" src="https://github.com/user-attachments/assets/e798de1b-af46-4e72-8b20-3a1a077186d1" />

- Node: **Merge**
  - Mode
    - `Combine`
  - Combine By
    - `Position`
  - Number of Inputs
    - `2`

あとはノードの右にある「○」をクリックし、「Input1」「Input2」にそれぞれ接続。


https://github.com/user-attachments/assets/1b8285e9-afb9-460a-a2d5-8b4edb16a9de





12. YouTube Upload を設定する

<img width="1719" height="838" alt="スクリーンショット 2025-12-17 22 28 54" src="https://github.com/user-attachments/assets/b3897da5-ec29-41bf-b207-740ab905d466" />

- Node: **HTTP Request**
  - Method
    - `PUT`
  - URL
    - `{{$node["Fetch Upload YouTube Location"].json.headers.location}}`
  - Authentication
    - `None`
  - Send Headers
    - `On`
  - Specify Headers
    - `Using Fields Below`
  - Header Parameters
    - Name
      - `Content-Type`
    - Value
      - `video/mp4`
    - Name
      - `X-Upload-Content-Type`
    - Value
      - `video/mp4`
  - Send Body
    - `On`
  - Body Content Type
    - `n8n Binary File`
  - Input Data Field Name
    - `data`

## Excecute Workflow を実行する

<img width="1730" height="839" alt="スクリーンショット 2025-12-17 22 59 15" src="https://github.com/user-attachments/assets/3503f48b-d599-44aa-bf9d-2bea166dff82" />

「Excecute Workflow」ボタンをクリックし、ワークフローが完了するのを待つ。

<img width="1728" height="842" alt="スクリーンショット 2025-12-17 23 01 04" src="https://github.com/user-attachments/assets/05e60edd-1862-4e6a-8440-f8a39a92fe64" />

Youtube に動画が作成されていれば成功。
