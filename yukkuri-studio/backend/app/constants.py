"""感情(=立ち絵の表情)の種類。DB・API・画面で同じキーを使う。"""
EMOTIONS = ("neutral", "happy", "angry", "surprised", "sad")
EMOTION_LABELS_JA = {"neutral": "通常", "happy": "笑顔", "angry": "怒り", "surprised": "驚き", "sad": "悲しみ"}

# ユーザーがアップロードできるキャラクター画像の形式(SVGはスクリプトを含められるため受け付けない)
UPLOAD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024

# キャラクター画面の「音声を試聴」で読み上げるサンプル文
SAMPLE_VOICE_TEXT = "こんにちは。これは音声のサンプルです。"

# 外見設定の入力項目(キー: 画面の表示名)。画像生成の指示文を組み立てるときの順序でもある
APPEARANCE_FIELDS = {
    "gender": "性別・外見のイメージ",
    "hair_style": "髪型",
    "hair_color": "髪色",
    "outfit": "服装",
    "eye_color": "目の色",
    "mood": "雰囲気",
    "other": "その他の特徴",
}

# ---- タイミング配置(Phase 3) ----
DEFAULT_GAP_MS = 300  # セリフとセリフの間の無音
ESTIMATE_MS_PER_CHAR = 170  # 音声が未生成のセリフの長さを文字数から見積もるときの目安
ESTIMATE_MIN_MS = 800
MIN_DURATION_MS = 100

# タイムライン上の行(track_type)
TRACK_AUDIO = "audio"
TRACK_CHARACTER = "character"  # 立ち絵
TRACK_SUBTITLE = "subtitle"

# ---- 動画編集(Phase 4) ----
HISTORY_LIMIT = 100  # プロジェクトごとに残す編集履歴の件数
