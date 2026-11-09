# HN Video Archive

繁體中文、公開瀏覽的 Hacker News 重複推薦 YouTube 影片索引網站。可直接部署至 Vercel，無需 Node.js、API Key 或資料庫。

## 快速部署

1. 將**整個專案資料夾**推送到 GitHub repository（建議公開，方便 GitHub Actions 使用）。
2. 登入 [Vercel](https://vercel.com/)，選擇 **Add New → Project → Import Git Repository**。
3. Framework Preset 選 **Other**；Root Directory 保持專案根目錄；Build Command 留空；Output Directory 留空（以 repository 根目錄為靜態網站）。按 **Deploy**。
4. 此時首頁可開啟，但**初始影片索引為空**，這是刻意設計：沒有驗證過的歷史推薦影片就不顯示假資料。
5. 到 GitHub repository 的 **Actions** 頁面，手動執行 **Backfill HN history (resumable)**。它每次處理最多 24 個時間窗，完成後提交 `data/`；每次最多處理 24 個時間窗；重複執行直到 `data/index_state.json` 的 `backfill_complete` 為 `true`。Vercel 連動 GitHub 後會隨提交重新部署。
6. **Update HN video index** 會每日於 UTC 02:23（台灣時間 10:23）排程更新最近四天資料；亦可手動執行。GitHub Actions 排程可能延遲，且需依 GitHub 政策保持啟用。

**重要：** 歷史回填執行時間可能很長、GitHub Actions 與 Algolia API 有用量或速率限制。大型 `posts.json` / `videos.json` 可能超過 GitHub 或 Vercel 實務容量；正式大規模營運應遷移到 SQLite/Postgres 或物件儲存與分頁 API。不要在未檢查資料量與 API 回應前宣稱歷史收錄完整。

## 本機測試

```bash
python -m unittest discover -s tests
python -m http.server 8000
# 開啟 http://localhost:8000
```

## 手動索引

```bash
python scripts/index_hn.py --mode recent --days 4
python scripts/index_hn.py --mode backfill --max-windows 24
python scripts/index_hn.py --mode build
```

索引使用標準 Python 函式庫，不需要安裝套件。索引需要網路連線；網頁使用 `/data/videos.json`，必須由 HTTP server 提供，不支援直接以 `file://` 開啟。

## 資料口徑與限制

- 範圍從 2007-02-01 開始；歷史回填截至**本月月初**，最近四天由每日更新處理。每月 2 日會自動再執行回填以補上前一個月（可視情況多次手動執行）；在前一個月完成回填之前，月初至最近四天之間可能有缺口。
- 查詢 Hacker News Algolia Search API 的 `story` 記錄，尋找 YouTube 網域 URL，並將 watch、youtu.be、embed、shorts、live URL 標準化為 11 字元影片 ID。
- 以不同 HN `objectID` 去重。至少兩篇 HN story 連到同一影片 ID 才收錄。
- API 搜尋是否涵蓋所有外部 URL 取決於 Algolia 搜尋索引與分頁能力。這是**最佳努力索引**，不保證完整涵蓋 HN 所有歷史資料；要嚴格全量，應改以完整 HN 事件資料集或官方 Firebase item 掃描與驗證。
- 不檢索留言、文字內的 YouTube 連結、其他影片平台，也不檢查 YouTube 影片是否仍可播放。分類依 HN 貼文標題關鍵字推定。
- 影片縮圖與嵌入播放由 YouTube 提供，HN 討論來源可逐筆點開查核。

## 索引檔案

- `data/posts.json`: 以 HN story ID 為 key 的已發現來源。
- `data/index_state.json`: 已完成的歷史查詢時間窗，用於中斷續跑。
- `data/videos.json`: 前端讀取的影片索引與狀態。
- `scripts/index_hn.py`: 可重試、時間窗拆分與持久化的索引程式。
- `.github/workflows/`: 每日更新及手動歷史回填。

## 上線前檢查

檢查 `data/videos.json` 的 `metadata.post_count`、`metadata.video_count`、`metadata.backfill_complete`，並抽查至少 20 筆影片的 HN 來源與 YouTube ID。若要宣稱「歷年全部」，需進一步做獨立資料來源覆蓋率比對。
