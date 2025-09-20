-- emotion_opensmileテーブルにcreated_atカラムを追加
-- timestamptz型（タイムゾーン付きタイムスタンプ）で作成

-- カラムが存在しない場合のみ追加
ALTER TABLE public.emotion_opensmile 
ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT NOW();

-- 既存レコードのcreated_atをNULLから現在時刻に更新（必要に応じて）
UPDATE public.emotion_opensmile 
SET created_at = NOW() 
WHERE created_at IS NULL;

-- インデックスを作成して検索パフォーマンスを向上
CREATE INDEX IF NOT EXISTS idx_emotion_opensmile_created_at 
ON public.emotion_opensmile(created_at DESC);

-- 確認用：テーブル構造を表示
-- \d public.emotion_opensmile